"""
server/intake_api.py — Javelin Video Analysis: 受付 (intake) FastAPI ルーター

エンドポイント:
    POST   /v1/intakes                    受付情報を作成
    GET    /v1/intakes                    受付一覧取得（フィルタ対応）
    GET    /v1/intakes/{intake_id}        受付詳細取得
    PATCH  /v1/intakes/{intake_id}        受付情報更新
    POST   /v1/intakes/{intake_id}/convert-to-job   ジョブ化
    POST   /v1/intakes/{intake_id}/archive           アーカイブ
    POST   /v1/intakes/{intake_id}/reject            対応不可

認証:
    X-JVA-API-Key ヘッダー または Authorization: Bearer {key} で認証
    JVA_API_KEY 未設定時は開発用として警告（本番運用不可）
    JVA_ENABLE_INTAKE_API=false の場合は 503 を返す

起動例 (server/app.py からインクルード):
    from server.intake_api import intake_router
    app.include_router(intake_router, prefix="/v1")
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

# ── パス設定 ─────────────────────────────────────────────────────────────────
_SERVER_DIR = Path(__file__).resolve().parent    # server/
_REPO_ROOT  = _SERVER_DIR.parent                 # project root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.intake_manager import (
    INTAKE_SOURCES,
    INTAKE_STATUSES,
    append_intake_audit_log,
    archive_intake,
    check_all_consents,
    convert_intake_to_job,
    create_intake,
    list_intakes,
    load_intake,
    missing_consents,
    reject_intake,
    update_intake,
)

logger = logging.getLogger("jva.intake_api")

# ── 設定 ─────────────────────────────────────────────────────────────────────

_API_KEY: str           = os.getenv("JVA_API_KEY", "")
_INTAKE_API_ENABLED: bool = os.getenv("JVA_ENABLE_INTAKE_API", "true").lower() == "true"
_LOG_PATH: Path         = _REPO_ROOT / "logs" / "intake_audit.log"

if not _API_KEY:
    logger.warning(
        "[intake_api] JVA_API_KEY が未設定です。本番環境では必ず設定してください。"
    )

# ── ルーター ──────────────────────────────────────────────────────────────────

intake_router = APIRouter(tags=["intakes"])


# ── 認証 ─────────────────────────────────────────────────────────────────────

def _verify_api_key(
    x_jva_api_key: Optional[str] = None,
    authorization: Optional[str] = None,
) -> None:
    """APIキーを検証する。

    X-JVA-API-Key ヘッダーまたは Authorization: Bearer {key} を受け付ける。
    JVA_API_KEY 未設定時は開発用として認証をスキップ（警告あり）。
    """
    if not _INTAKE_API_ENABLED:
        raise HTTPException(status_code=503, detail="Intake API は無効です。")

    if not _API_KEY:
        # 未設定時は開発モード（警告のみ）
        logger.warning("[intake_api] 開発モード: APIキー認証をスキップしました。")
        return

    # X-JVA-API-Key ヘッダー
    if x_jva_api_key and x_jva_api_key == _API_KEY:
        return

    # Authorization: Bearer {key}
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1] == _API_KEY:
            return

    logger.warning("[intake_api] 認証失敗")
    _try_log_auth_failure()
    raise HTTPException(status_code=401, detail="APIキーが無効です。")


def _try_log_auth_failure() -> None:
    try:
        append_intake_audit_log(
            _LOG_PATH,
            intake_id="—",
            source="api",
            action="auth_failed",
            success=False,
            error="invalid_api_key",
        )
    except Exception:
        pass


def _check_enabled() -> None:
    if not _INTAKE_API_ENABLED:
        raise HTTPException(status_code=503, detail="Intake API は無効です。")


# ── エンドポイント ────────────────────────────────────────────────────────────

@intake_router.post("/intakes", status_code=201)
async def api_create_intake(
    request: Request,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """受付情報を作成する。

    リクエストボディ (JSON, 全フィールド任意):
    ```json
    {
      "source": "google_form",
      "name_or_nickname": "...",
      "contact": "...",
      "main_request": "...",
      ...
      "raw_payload": { ...フォーム全体 }
    }
    ```
    """
    _check_enabled()
    _verify_api_key(x_jva_api_key, authorization)

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    # raw_payload 未指定なら body 全体（source を含む）を保存する。
    # source を pop する前に捕捉することで、元のフォームデータを完全に記録する。
    if "raw_payload" not in body:
        body["raw_payload"] = dict(body)

    source = body.pop("source", "unknown")
    if source not in INTAKE_SOURCES:
        source = "api"

    try:
        intake = create_intake(source=source, **body)
    except Exception as exc:
        logger.error("[intake_api] 作成エラー: %s", exc)
        _try_log_audit(intake_id="—", source=source, action="create", success=False, error=str(exc))
        raise HTTPException(status_code=500, detail=f"作成に失敗しました: {exc}") from exc

    _try_log_audit(intake["intake_id"], source, "create", True)
    # 個人情報を含むフィールドを除いたレスポンス
    return JSONResponse(_safe_response(intake), status_code=201)


@intake_router.get("/intakes")
def api_list_intakes(
    status: Optional[str]  = Query(default=None),
    source: Optional[str]  = Query(default=None),
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """受付一覧を返す（フィルタ対応）。"""
    _check_enabled()
    _verify_api_key(x_jva_api_key, authorization)

    intakes = list_intakes(status=status, source=source)
    # リスト表示では raw_payload を除外してレスポンスサイズを抑える
    return JSONResponse([_safe_response(i, exclude_raw_payload=True) for i in intakes])


# ── ヘルスチェック（{intake_id} より前に登録する必要がある）──────────────────

@intake_router.get("/intakes/health")
def api_intake_health() -> JSONResponse:
    """Intake API のヘルスチェック（認証不要）。"""
    return JSONResponse({
        "status":  "ok",
        "enabled": _INTAKE_API_ENABLED,
        "api_key_configured": bool(_API_KEY),
    })


@intake_router.get("/intakes/{intake_id}")
def api_get_intake(
    intake_id: str,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """受付詳細を返す。"""
    _check_enabled()
    _verify_api_key(x_jva_api_key, authorization)

    try:
        intake = load_intake(intake_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="intake が見つかりません。")
    # 詳細取得では raw_payload も含める
    return JSONResponse(_safe_response(intake, exclude_raw_payload=False))


@intake_router.patch("/intakes/{intake_id}")
async def api_update_intake(
    intake_id: str,
    request: Request,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """受付情報を部分更新する。"""
    _check_enabled()
    _verify_api_key(x_jva_api_key, authorization)

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSONが不正です。")

    # intake_id / created_at / raw_payload は外部から上書き不可
    for protected in ("intake_id", "created_at"):
        body.pop(protected, None)

    try:
        intake = update_intake(intake_id, **body)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="intake が見つかりません。")
    except Exception as exc:
        logger.error("[intake_api] 更新エラー intake_id=%s: %s", intake_id, exc)
        _try_log_audit(intake_id, intake.get("source", "unknown"), "update", False, str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _try_log_audit(intake["intake_id"], intake.get("source", "unknown"), "update", True)
    return JSONResponse(_safe_response(intake, exclude_raw_payload=False))


@intake_router.post("/intakes/{intake_id}/convert-to-job", status_code=201)
def api_convert_to_job(
    intake_id: str,
    force: bool = Query(default=False),
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """intake から新規ジョブを作成する。

    Parameters
    ----------
    force : True の場合、すでに converted_job_id があっても再変換を許可
    """
    _check_enabled()
    _verify_api_key(x_jva_api_key, authorization)

    try:
        intake = load_intake(intake_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="intake が見つかりません。")

    try:
        import job_manager as jm
        result = convert_intake_to_job(intake_id, jm, force=force)
    except ValueError as ve:
        raise HTTPException(status_code=409, detail=str(ve))
    except Exception as exc:
        logger.error("[intake_api] ジョブ変換エラー intake_id=%s: %s", intake_id, exc)
        _try_log_audit(intake_id, intake.get("source", "unknown"), "convert_to_job", False, str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _try_log_audit(
        intake_id,
        result["intake"].get("source", "unknown"),
        "convert_to_job",
        True,
    )
    return JSONResponse({
        "intake_id": intake_id,
        "job_id":    result["job"]["job_id"],
        "status":    "converted",
    }, status_code=201)


@intake_router.post("/intakes/{intake_id}/archive")
def api_archive_intake(
    intake_id: str,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """intake をアーカイブする。"""
    _check_enabled()
    _verify_api_key(x_jva_api_key, authorization)

    try:
        intake = archive_intake(intake_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="intake が見つかりません。")

    _try_log_audit(intake["intake_id"], intake.get("source", "unknown"), "archive", True)
    return JSONResponse({"intake_id": intake_id, "status": "archived"})


@intake_router.post("/intakes/{intake_id}/reject")
async def api_reject_intake(
    intake_id: str,
    request: Request,
    x_jva_api_key: Optional[str] = Header(default=None, alias="X-JVA-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """intake を対応不可にする。"""
    _check_enabled()
    _verify_api_key(x_jva_api_key, authorization)

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    note = body.get("note", "")
    try:
        intake = reject_intake(intake_id, note=note)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="intake が見つかりません。")

    _try_log_audit(intake["intake_id"], intake.get("source", "unknown"), "reject", True)
    return JSONResponse({"intake_id": intake_id, "status": "rejected"})


# ── 内部ユーティリティ ────────────────────────────────────────────────────────

# ログに出さないフィールド（個人情報）
_PII_FIELDS = {"name_or_nickname", "contact", "line_user_id", "email", "instagram_account"}

def _safe_response(intake: Dict[str, Any], exclude_raw_payload: bool = True) -> Dict[str, Any]:
    """APIレスポンス用 dict を返す。

    exclude_raw_payload=True (デフォルト)の場合、raw_payload を除外しレスポンスサイズを抑える。
    詳細取得エンドポイントでは exclude_raw_payload=False を指定すること。
    PII (個人情報) は認証済み管理者向けに返すため、レスポンスに含める。
    ログには PII を出力しない。
    """
    if exclude_raw_payload:
        return {k: v for k, v in intake.items() if k != "raw_payload"}
    return dict(intake)


def _try_log_audit(
    intake_id: str,
    source: str,
    action: str,
    success: bool,
    error: str = "",
) -> None:
    """監査ログを安全に追記する（例外を握りつぶす）。"""
    try:
        append_intake_audit_log(_LOG_PATH, intake_id, source, action, success, error)
    except Exception as exc:
        logger.warning("[intake_api] 監査ログ書き込み失敗: %s", exc)
