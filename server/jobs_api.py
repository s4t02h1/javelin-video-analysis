"""
server/jobs_api.py — Javelin Video Analysis: ジョブ管理 FastAPI ルーター (Phase 7)

エンドポイント:
    POST   /v1/jobs                           ジョブ作成（ローカル）
    GET    /v1/jobs                           ジョブ一覧
    GET    /v1/jobs/{job_id}                  ジョブ詳細
    POST   /v1/jobs/{job_id}/enqueue          キューに投入
    POST   /v1/jobs/{job_id}/cancel           キャンセル
    POST   /v1/jobs/{job_id}/retry            リトライ
    GET    /v1/jobs/{job_id}/queue-status     キュー状態
    GET    /v1/jobs/{job_id}/artifacts        成果物一覧
    GET    /v1/jobs/{job_id}/delivery         納品情報

    POST   /v1/comparisons/{comparison_id}/enqueue    比較ジョブをキューに投入
    GET    /v1/comparisons/{comparison_id}/queue-status
    GET    /v1/comparisons/{comparison_id}/delivery

認証: X-JVA-API-Key ヘッダー または Authorization: Bearer {key}
"""
from __future__ import annotations

import logging
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

# ── パス設定 ─────────────────────────────────────────────────────────────────
_SERVER_DIR = Path(__file__).resolve().parent
_REPO_ROOT  = _SERVER_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import job_manager as jm
from src.queue_manager import (
    JOB_TYPES,
    QUEUE_STATUS_LABELS,
    QUEUE_STATUSES,
    cancel_queue_job,
    create_queue_job,
    fail_queue_job,
    find_active_queue_job_for_job,
    find_queue_job_for_job,
    get_queue_counts,
    list_queue_jobs,
    load_queue_job,
    retry_queue_job,
)

logger = logging.getLogger("jva.jobs_api")

# ── 設定 ─────────────────────────────────────────────────────────────────────
# _API_KEY はモジュールロード時の警告のみに使用。
# 認証チェックは毎回 os.getenv() で読む（テスト・再設定に対応）。
_JOBS_API_ENABLED: bool = os.getenv("JVA_ENABLE_JOBS_API", "true").lower() == "true"

if not os.getenv("JVA_API_KEY", ""):
    logger.warning(
        "[jobs_api] JVA_API_KEY が未設定です。本番環境では必ず設定してください。"
    )

# ── ルーター ──────────────────────────────────────────────────────────────────
jobs_router = APIRouter(tags=["jobs"])

# ── 認証 ─────────────────────────────────────────────────────────────────────

def _verify_api_key(
    x_jva_api_key: Optional[str] = None,
    authorization: Optional[str] = None,
) -> None:
    """APIキーを検証する。"""
    if not _JOBS_API_ENABLED:
        raise HTTPException(status_code=503, detail="Jobs API は無効です。")

    # 毎回 os.getenv() を呼ぶことで、モジュールロード後の環境変数変更にも対応する
    _key = os.getenv("JVA_API_KEY", "")
    if not _key:
        logger.warning("[jobs_api] 開発モード: APIキー認証をスキップしました。")
        return

    if x_jva_api_key and secrets.compare_digest(x_jva_api_key, _key):
        return

    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and secrets.compare_digest(parts[1], _key):
            return

    logger.warning("[jobs_api] 認証失敗")
    raise HTTPException(status_code=401, detail="APIキーが無効です。")


# ── レスポンス整形 ─────────────────────────────────────────────────────────────

_JOB_RESPONSE_EXCLUDE = frozenset()   # 現在はすべてのジョブフィールドを返す


def _job_response(job: Dict[str, Any]) -> Dict[str, Any]:
    """ジョブ dict からAPIレスポンス用 dict を作る。"""
    return dict(job)


def _queue_response(qjob: Dict[str, Any]) -> Dict[str, Any]:
    """キュージョブからAPIレスポンス用 dict を作る。"""
    return {
        "queue_id":      qjob.get("queue_id"),
        "job_id":        qjob.get("job_id"),
        "job_type":      qjob.get("job_type"),
        "status":        qjob.get("status"),
        "status_label":  QUEUE_STATUS_LABELS.get(qjob.get("status", ""), ""),
        "priority":      qjob.get("priority"),
        "created_at":    qjob.get("created_at"),
        "updated_at":    qjob.get("updated_at"),
        "started_at":    qjob.get("started_at"),
        "finished_at":   qjob.get("finished_at"),
        "retry_count":   qjob.get("retry_count"),
        "max_retries":   qjob.get("max_retries"),
        "current_step":  qjob.get("current_step"),
        "last_error":    qjob.get("last_error"),
        "failed_step":   qjob.get("failed_step"),
        "steps":         qjob.get("steps", []),
        "cancel_requested": qjob.get("cancel_requested"),
        "source":        qjob.get("source", ""),
    }


# ── ヘルスチェック ────────────────────────────────────────────────────────────

@jobs_router.get("/jobs/health")
def jobs_health() -> JSONResponse:
    """Jobs API ヘルスチェック（認証不要）。"""
    counts = get_queue_counts()
    return JSONResponse({
        "status": "ok",
        "api":    "jobs",
        "queue":  counts,
    })


# ── ジョブ CRUD ────────────────────────────────────────────────────────────────

@jobs_router.post("/jobs", status_code=201)
async def api_create_job(
    request: Request,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """新規解析ジョブを作成する（ローカルファイルベース）。

    リクエストボディ (JSON, 全フィールド任意):
    ```json
    {
      "height_m": 1.85,
      "mode": "all_variants",
      "enqueue": true
    }
    ```
    `enqueue=true` の場合は作成と同時にキューに投入する。
    """
    _verify_api_key(x_jva_api_key, authorization)

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    height_m: Optional[float] = body.get("height_m")
    mode: str = body.get("mode", "all_variants")
    enqueue: bool = bool(body.get("enqueue", False))
    job_type: str = body.get("job_type", "full_pipeline")
    priority: int = int(body.get("priority", 5))
    requested_by: str = str(body.get("requested_by", "api"))

    try:
        job = jm.create_job(height_m=height_m, mode=mode)
    except Exception as exc:
        logger.error("[jobs_api] ジョブ作成エラー: %s", exc)
        raise HTTPException(status_code=500, detail=f"ジョブ作成に失敗しました: {exc}") from exc

    job_id = job["job_id"]
    result: Dict[str, Any] = {"job_id": job_id, "status": job["status"], "created_at": job["created_at"]}

    if enqueue:
        try:
            qjob = create_queue_job(
                job_id,
                job_type=job_type,
                priority=priority,
                requested_by=requested_by,
                source="api",
            )
            jm.update_job(job_id, status="queued")
            result["queue_id"] = qjob["queue_id"]
            result["status"] = "queued"
        except Exception as exc:
            logger.warning("[jobs_api] キュー投入エラー: %s", exc)
            result["queue_warning"] = str(exc)[:200]

    logger.info("[jobs_api] ジョブ作成: job_id=%s enqueue=%s", job_id, enqueue)
    return JSONResponse(result, status_code=201)


@jobs_router.get("/jobs")
def api_list_jobs(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """ジョブ一覧を返す。"""
    _verify_api_key(x_jva_api_key, authorization)

    try:
        jobs = jm.list_jobs()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if status:
        jobs = [j for j in jobs if j.get("status") == status]

    jobs = jobs[:limit]
    return JSONResponse([_job_response(j) for j in jobs])


@jobs_router.get("/jobs/{job_id}")
def api_get_job(
    job_id: str,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """ジョブ詳細を返す。"""
    _verify_api_key(x_jva_api_key, authorization)

    try:
        job = jm.load_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"ジョブが見つかりません: {job_id}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(_job_response(job))


# ── キュー操作 ────────────────────────────────────────────────────────────────

@jobs_router.post("/jobs/{job_id}/enqueue", status_code=201)
async def api_enqueue_job(
    job_id: str,
    request: Request,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """ジョブをキューに投入する。

    すでに pending/running のキュージョブがある場合は 409 を返す。
    """
    _verify_api_key(x_jva_api_key, authorization)

    # ジョブの存在確認
    try:
        job = jm.load_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"ジョブが見つかりません: {job_id}")

    # 二重投入チェック
    existing = find_active_queue_job_for_job(job_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"このジョブはすでにキューに入っています (queue_id={existing['queue_id']}, status={existing['status']})。"
        )

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    job_type = str(body.get("job_type", "full_pipeline"))
    priority = int(body.get("priority", 5))
    requested_by = str(body.get("requested_by", "api"))

    try:
        qjob = create_queue_job(
            job_id,
            job_type=job_type,
            priority=priority,
            requested_by=requested_by,
            source="api",
        )
        jm.update_job(job_id, status="queued")
    except Exception as exc:
        logger.error("[jobs_api] キュー投入エラー: job_id=%s error=%s", job_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("[jobs_api] キュー投入: job_id=%s queue_id=%s", job_id, qjob["queue_id"])
    return JSONResponse(_queue_response(qjob), status_code=201)


@jobs_router.post("/jobs/{job_id}/cancel")
async def api_cancel_job(
    job_id: str,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """ジョブのキュータスクをキャンセルする。

    - pending: 即時キャンセル
    - running: cancel_requested フラグを立てる（ワーカーが次ステップで中断）
    """
    _verify_api_key(x_jva_api_key, authorization)

    qjob = find_active_queue_job_for_job(job_id)
    if qjob is None:
        raise HTTPException(
            status_code=404,
            detail=f"キャンセル可能なキュータスクが見つかりません: job_id={job_id}"
        )

    try:
        updated = cancel_queue_job(qjob["queue_id"])
    except ValueError as ve:
        raise HTTPException(status_code=409, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if updated.get("status") == "cancelled":
        try:
            jm.update_job(job_id, status="cancelled")
        except Exception:
            pass

    return JSONResponse({
        "queue_id": updated["queue_id"],
        "job_id":   job_id,
        "status":   updated["status"],
        "cancel_requested": updated.get("cancel_requested", False),
    })


@jobs_router.post("/jobs/{job_id}/retry")
async def api_retry_job(
    job_id: str,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """failed または cancelled のジョブをリトライする（pending に戻す）。"""
    _verify_api_key(x_jva_api_key, authorization)

    # 最新のキュージョブを取得（failed/cancelled のもの）
    qjob = find_queue_job_for_job(job_id)
    if qjob is None:
        raise HTTPException(
            status_code=404,
            detail=f"リトライ対象のキュータスクが見つかりません: job_id={job_id}"
        )

    if qjob.get("status") not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"ステータス '{qjob.get('status')}' のジョブはリトライできません。"
        )

    try:
        updated = retry_queue_job(qjob["queue_id"])
        jm.update_job(job_id, status="queued")
    except ValueError as ve:
        raise HTTPException(status_code=409, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    max_retries = updated.get("max_retries", 1)
    retry_count = updated.get("retry_count", 0)

    return JSONResponse({
        "queue_id":    updated["queue_id"],
        "job_id":      job_id,
        "status":      updated["status"],
        "retry_count": retry_count,
        "max_retries": max_retries,
        "warning":     f"リトライ上限（{max_retries}回）を超えています。" if retry_count > max_retries else None,
    })


@jobs_router.get("/jobs/{job_id}/queue-status")
def api_get_queue_status(
    job_id: str,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """ジョブのキュー状態を返す。"""
    _verify_api_key(x_jva_api_key, authorization)

    qjob = find_queue_job_for_job(job_id)
    if qjob is None:
        return JSONResponse({"job_id": job_id, "queued": False, "queue_entry": None})

    return JSONResponse({
        "job_id":      job_id,
        "queued":      True,
        "queue_entry": _queue_response(qjob),
    })


@jobs_router.get("/jobs/{job_id}/artifacts")
def api_get_artifacts(
    job_id: str,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """ジョブの成果物一覧を返す（ローカルファイルパス）。"""
    _verify_api_key(x_jva_api_key, authorization)

    try:
        jm.load_job(job_id)  # 存在確認
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"ジョブが見つかりません: {job_id}")

    job_dir = jm.get_job_dir(job_id)
    artifacts: List[Dict[str, Any]] = []

    for sub in ("output", "report", "deliverables"):
        sub_dir = job_dir / sub
        if not sub_dir.exists():
            continue
        for p in sorted(sub_dir.rglob("*")):
            if p.is_file():
                artifacts.append({
                    "relative_path": str(p.relative_to(job_dir)).replace("\\", "/"),
                    "filename":      p.name,
                    "size_bytes":    p.stat().st_size,
                    "directory":     sub,
                })

    return JSONResponse({
        "job_id":    job_id,
        "count":     len(artifacts),
        "artifacts": artifacts,
    })


@jobs_router.get("/jobs/{job_id}/delivery")
def api_get_delivery(
    job_id: str,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """ジョブの納品情報を返す（S3 URL を含む）。

    presigned URL はレスポンスに含めるが、ログには出力しない。
    """
    _verify_api_key(x_jva_api_key, authorization)

    try:
        job = jm.load_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"ジョブが見つかりません: {job_id}")

    s3_status = jm.get_job_s3_status(job)

    return JSONResponse({
        "job_id":                    job_id,
        "job_status":                job.get("status"),
        "upload_status":             s3_status["upload_status"],
        "uploaded_artifacts_count":  s3_status["uploaded_artifacts_count"],
        "delivery_page_url":         s3_status["delivery_page_url"],
        "delivery_url_expires_at":   s3_status["delivery_url_expires_at"],
        "last_uploaded_at":          s3_status["last_uploaded_at"],
    })


# ── キュー管理 API ────────────────────────────────────────────────────────────

@jobs_router.get("/queue")
def api_get_queue(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """キュー一覧を返す。"""
    _verify_api_key(x_jva_api_key, authorization)

    if status and status not in QUEUE_STATUSES:
        raise HTTPException(status_code=400, detail=f"不正なステータス: {status}")

    qjobs = list_queue_jobs(status=status)[:limit]
    counts = get_queue_counts()

    return JSONResponse({
        "counts":  counts,
        "total":   len(qjobs),
        "entries": [_queue_response(q) for q in qjobs],
    })


# ── 比較ジョブ API ────────────────────────────────────────────────────────────

@jobs_router.post("/comparisons/{comparison_id}/enqueue", status_code=201)
async def api_enqueue_comparison(
    comparison_id: str,
    request: Request,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """比較ジョブをキューに投入する。"""
    _verify_api_key(x_jva_api_key, authorization)

    # 比較ジョブの存在確認
    comparisons_dir = _REPO_ROOT / "comparisons"
    comp_json = comparisons_dir / comparison_id / "comparison.json"
    if not comp_json.exists():
        raise HTTPException(status_code=404,
                            detail=f"比較ジョブが見つかりません: {comparison_id}")

    # 二重投入チェック
    existing = find_active_queue_job_for_job(comparison_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"この比較ジョブはすでにキューに入っています (queue_id={existing['queue_id']})。"
        )

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    try:
        qjob = create_queue_job(
            comparison_id,
            job_type="comparison_analysis",
            priority=int(body.get("priority", 5)),
            requested_by=str(body.get("requested_by", "api")),
            source="api",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(_queue_response(qjob), status_code=201)


@jobs_router.get("/comparisons/{comparison_id}/queue-status")
def api_comparison_queue_status(
    comparison_id: str,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """比較ジョブのキュー状態を返す。"""
    _verify_api_key(x_jva_api_key, authorization)

    qjob = find_queue_job_for_job(comparison_id)
    return JSONResponse({
        "comparison_id": comparison_id,
        "queued":        qjob is not None,
        "queue_entry":   _queue_response(qjob) if qjob else None,
    })


@jobs_router.get("/comparisons/{comparison_id}/delivery")
def api_comparison_delivery(
    comparison_id: str,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """比較ジョブの納品情報を返す。"""
    _verify_api_key(x_jva_api_key, authorization)

    comparisons_dir = _REPO_ROOT / "comparisons"
    comp_json = comparisons_dir / comparison_id / "comparison.json"
    if not comp_json.exists():
        raise HTTPException(status_code=404,
                            detail=f"比較ジョブが見つかりません: {comparison_id}")

    try:
        import json
        comp = json.loads(comp_json.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse({
        "comparison_id":   comparison_id,
        "status":          comp.get("status"),
        "delivery_page_url": comp.get("delivery_page_url"),
        "delivery_url_expires_at": comp.get("delivery_url_expires_at"),
    })
