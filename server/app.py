"""
server/app.py — Javelin Video Analysis: Minimal SaaS API (FastAPI + S3)

起動例:
    uvicorn server.app:app --host 0.0.0.0 --port 8000

環境変数:
    AWS_REGION      (default: ap-northeast-1)
    JVA_BUCKET      S3バケット名 (default: your-bucket-name)
    JVA_RUN_PY      run.py への絶対パス (default: このファイルの親ディレクトリの run.py)
    JVA_PYTHON      Python 実行ファイルのパス (default: sys.executable)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from subprocess import CalledProcessError, run as subprocess_run
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger("jva.server")

# ── 設定 ─────────────────────────────────────────────────────────────────────

APP_REGION: str = os.getenv("AWS_REGION", "ap-northeast-1")
BUCKET: str = os.getenv("JVA_BUCKET", "your-bucket-name")
_REPO_ROOT: Path = Path(__file__).resolve().parent.parent
RUN_PY: str = os.getenv("JVA_RUN_PY", str(_REPO_ROOT / "run.py"))
PYTHON_BIN: str = os.getenv("JVA_PYTHON", sys.executable)

# ── S3 クライアント（AWS 認証情報なしの場合は None のまま起動を継続）────────

try:
    import boto3
    import botocore.exceptions as _botocore_exc

    _s3_client = boto3.client("s3", region_name=APP_REGION)
except ImportError:
    logger.warning("boto3 がインストールされていません。S3 機能は無効です。")
    _s3_client = None  # type: ignore[assignment]
    _botocore_exc = None  # type: ignore[assignment]

# ── FastAPI アプリ ─────────────────────────────────────────────────────────

app = FastAPI(title="JVA Minimal SaaS")

# ── CORS（フロントエンド開発サーバー対応） ────────────────────────────────────
_CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("JVA_CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["X-JVA-API-Key", "Authorization", "Content-Type"],
)

# ── Jobs API ルーター（Phase 7） ───────────────────────────────────────────────
try:
    from server.jobs_api import jobs_router
    app.include_router(jobs_router, prefix="/v1")
    logger.info("Jobs API ルーターを読み込みました。")
except ImportError as _ie:
    logger.warning("Jobs API ルーターの読み込みに失敗しました: %s", _ie)

# ── intake API ルーター ────────────────────────────────────────────────────────
try:
    from server.intake_api import intake_router
    app.include_router(intake_router, prefix="/v1")
    logger.info("Intake API ルーターを読み込みました。")
except ImportError as _ie:
    logger.warning("Intake API ルーターの読み込みに失敗しました: %s", _ie)

# ── パブリックダッシュボード API ルーター（Phase 14） ──────────────────────────
try:
    from server.public_dashboard_api import public_dashboard_router
    app.include_router(public_dashboard_router, prefix="/v1/public")
    logger.info("Public Dashboard API ルーターを読み込みました。")
except ImportError as _ie:
    logger.warning("Public Dashboard API ルーターの読み込みに失敗しました: %s", _ie)

# ── フィードバック API ルーター（Phase 15） ───────────────────────────────────
try:
    from server.feedback_api import feedback_router
    app.include_router(feedback_router, prefix="/v1/public")
    logger.info("Feedback API ルーターを読み込みました。")
except ImportError as _ie:
    logger.warning("Feedback API ルーターの読み込みに失敗しました: %s", _ie)


# ── S3 ユーティリティ ────────────────────────────────────────────────────────

def _s3() -> Any:
    """S3 クライアントを返す。未初期化の場合は RuntimeError を送出する。"""
    if _s3_client is None:
        raise RuntimeError("S3 クライアントが初期化されていません（boto3 未インストール）。")
    return _s3_client


def _status_key(job_id: str) -> str:
    return f"results/{job_id}/status.json"


def _result_prefix(job_id: str) -> str:
    return f"results/{job_id}/"


def _presign_put(
    key: str,
    content_type: str = "application/octet-stream",
    expiry: int = 3600,
) -> Dict[str, Any]:
    return _s3().generate_presigned_post(
        BUCKET,
        key,
        Fields={"Content-Type": content_type},
        Conditions=[["content-length-range", 0, 1024 * 1024 * 1024]],
        ExpiresIn=expiry,
    )


def _put_status(job_id: str, status: Dict[str, Any]) -> None:
    """status.json を S3 へアップロードする。失敗時はログのみ。"""
    try:
        body = json.dumps(status, ensure_ascii=False).encode("utf-8")
        _s3().put_object(
            Bucket=BUCKET,
            Key=_status_key(job_id),
            Body=body,
            ContentType="application/json",
        )
    except Exception as exc:
        logger.error("[%s] status.json のアップロードに失敗: %s", job_id, exc)


def _upload_results(job_id: str, local_out_dir: str) -> Dict[str, Any]:
    """
    local_out_dir 以下のファイルをすべて S3 へアップロードし、
    主要ファイルのキーを含む dict を返す。

    Returns
    -------
    dict with keys:
        result_prefix           : str
        report_pdf_key          : str | None
        analysis_summary_json_key: str | None
        deliverable_zip_keys    : list[str]
    """
    prefix = _result_prefix(job_id)
    report_pdf_key: Optional[str] = None
    summary_key: Optional[str] = None
    zip_keys: List[str] = []

    for root, _, files in os.walk(local_out_dir):
        for fname in files:
            local_path = os.path.join(root, fname)
            rel = os.path.relpath(local_path, local_out_dir).replace("\\", "/")
            s3_key = prefix + rel
            try:
                _s3().upload_file(local_path, BUCKET, s3_key)
                logger.debug("[%s] uploaded: %s", job_id, s3_key)
            except Exception as exc:
                logger.warning("[%s] アップロード失敗 %s: %s", job_id, s3_key, exc)
                continue
            # 主要ファイルの分類
            lower = fname.lower()
            if lower.endswith(".pdf"):
                report_pdf_key = s3_key
            elif lower == "analysis_summary.json":
                summary_key = s3_key
            elif lower.endswith(".zip"):
                zip_keys.append(s3_key)

    return {
        "result_prefix": prefix,
        "report_pdf_key": report_pdf_key,
        "analysis_summary_json_key": summary_key,
        "deliverable_zip_keys": zip_keys,
    }


# ── バックグラウンドジョブ ─────────────────────────────────────────────────────

def _run_job(job_id: str, input_key: str) -> None:
    """S3から入力動画をダウンロードし、解析を実行して結果を S3 へアップロードする。"""
    now_iso = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ── 解析開始: status = running を先に保存 ────────────────────────────────
    _put_status(job_id, {
        "status":    "running",
        "job_id":    job_id,
        "updated_at": now_iso(),
    })

    tmpdir = tempfile.mkdtemp(prefix=f"jva-{job_id}-")
    local_in = os.path.join(tmpdir, "input.mp4")
    local_out_dir = os.path.join(tmpdir, "out")
    os.makedirs(local_out_dir, exist_ok=True)

    try:
        # ── S3 からダウンロード ───────────────────────────────────────────────
        try:
            _s3().download_file(BUCKET, input_key, local_in)
        except Exception as dl_err:
            raise RuntimeError(f"入力動画のダウンロードに失敗: {dl_err}") from dl_err

        # ── 解析実行（標準形式） ──────────────────────────────────────────────
        cmd = [
            PYTHON_BIN, RUN_PY,
            "--input",      local_in,
            "--output-dir", local_out_dir,
            "--all-variants",
        ]
        logger.info("[%s] 解析開始: %s", job_id, " ".join(cmd))
        subprocess_run(cmd, check=True)
        logger.info("[%s] 解析完了", job_id)

        # ── 結果を S3 へアップロード ─────────────────────────────────────────
        keys = _upload_results(job_id, local_out_dir)
        status: Dict[str, Any] = {
            "status":    "completed",
            "job_id":    job_id,
            "updated_at": now_iso(),
            "error":     None,
            **keys,
        }

    except CalledProcessError as cpe:
        logger.error("[%s] 解析プロセスが非ゼロ終了: %s", job_id, cpe)
        status = {
            "status":    "failed",
            "job_id":    job_id,
            "updated_at": now_iso(),
            "error":     f"CalledProcessError: returncode={cpe.returncode}",
            "result_prefix":             _result_prefix(job_id),
            "report_pdf_key":            None,
            "analysis_summary_json_key": None,
            "deliverable_zip_keys":      [],
        }
    except Exception as exc:
        logger.exception("[%s] 解析中に予期しないエラー: %s", job_id, exc)
        status = {
            "status":    "failed",
            "job_id":    job_id,
            "updated_at": now_iso(),
            "error":     str(exc),
            "result_prefix":             _result_prefix(job_id),
            "report_pdf_key":            None,
            "analysis_summary_json_key": None,
            "deliverable_zip_keys":      [],
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # ── 成否に関わらず status.json を保存 ────────────────────────────────────
    _put_status(job_id, status)


# ── エンドポイント ────────────────────────────────────────────────────────────
# POST /v1/jobs, GET /v1/jobs/{job_id} は jobs_api ルーターに移行済み（Phase 7）


# ── ヘルスチェックエンドポイント（Phase 8） ───────────────────────────────────

@app.get("/health", tags=["System"])
def health_check() -> JSONResponse:
    """稼働確認。常に 200 を返す。ロードバランサー・k8s の liveness probe に使用。"""
    return JSONResponse({"status": "ok", "app": "javelin-video-analysis"})


@app.get("/ready", tags=["System"])
def ready_check() -> JSONResponse:
    """準備状態確認。依存リソースが揃っているか確認する。

    HTTP 200: 正常（全チェック通過）
    HTTP 503: degraded（必須チェック失敗）
    """
    try:
        from src.config import cfg
        data_ok = cfg.DATA_DIR.exists()
        queue_ok = cfg.QUEUE_DIR.exists()
        log_ok = cfg.LOG_DIR.exists()
        s3_ok = cfg.S3_CONFIGURED
    except Exception as exc:
        logger.error("/ready チェック中にエラー: %s", exc)
        return JSONResponse(
            {"status": "error", "app": "javelin-video-analysis", "error": str(exc)},
            status_code=503,
        )

    checks = {
        "data_dir": data_ok,
        "queue_dir": queue_ok,
        "log_dir": log_ok,
        "s3_configured": s3_ok,
    }
    # 必須チェック: data_dir と queue_dir
    ready = data_ok and queue_ok
    return JSONResponse(
        {
            "status": "ok" if ready else "degraded",
            "app": "javelin-video-analysis",
            "env": os.getenv("JVA_ENV", "local"),
            "checks": checks,
        },
        status_code=200 if ready else 503,
    )


