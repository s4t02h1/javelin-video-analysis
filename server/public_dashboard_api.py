"""
server/public_dashboard_api.py — Phase 14: パブリックダッシュボード API

認証不要（トークンベース）の読み取り専用 API。
job_id を URL に直接含めず、dashboard_token でアクセスする。

エンドポイント:
    GET /v1/public/dashboards/{dashboard_token}
        → ダッシュボードマニフェスト JSON を返す
        → 404: トークン不明  410: トークン期限切れ
        → presigned URL が期限切れの場合は S3 設定済みならば再生成

    GET /v1/public/healthz
        → ヘルスチェック（認証不要）
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger("jva.public_dashboard_api")

# ── パス設定 ─────────────────────────────────────────────────────────────────
_SERVER_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SERVER_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import job_manager as jm

try:
    from src.dashboard_manifest import (
        find_job_id_by_token,
        is_token_expired,
        load_dashboard_manifest,
        refresh_manifest_urls,
    )
    _MANIFEST_AVAILABLE = True
except ImportError as _e:
    logger.warning("[public_dashboard_api] dashboard_manifest モジュール読み込み失敗: %s", _e)
    _MANIFEST_AVAILABLE = False

# ── 設定 ─────────────────────────────────────────────────────────────────────

_PUBLIC_DASHBOARD_ENABLED: bool = (
    os.getenv("JVA_PUBLIC_DASHBOARD_ENABLED", "true").lower() == "true"
)

# ── ルーター ──────────────────────────────────────────────────────────────────

public_dashboard_router = APIRouter(tags=["public-dashboards"])


# ── ヘルパー ──────────────────────────────────────────────────────────────────


def _is_url_expired(manifest: Dict[str, Any]) -> bool:
    """manifest 内の url_expires_at が過去かどうかを返す。"""
    expires = manifest.get("url_expires_at", "")
    if not expires:
        return False
    try:
        exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > exp_dt
    except Exception:
        return False


def _sanitize_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """
    フロントエンドに返すマニフェストから内部情報を除去する。

    除去する項目:
    - ダウンロード項目の relative_path（内部パス露出防止）
    - 各 item の s3_key（S3 キー露出防止）
    - job_id は inquiry_info の文脈でのみ残す
    """
    import copy
    m = copy.deepcopy(manifest)

    # ダウンロードの internal fields を除去
    downloads = m.get("downloads", {})
    for cat, items in downloads.items():
        for item in items:
            item.pop("relative_path", None)
            item.pop("s3_key", None)

    # videos / phase_images / graphs の s3_key を除去
    for section_key in ("videos", "phase_images", "graphs"):
        for item in m.get(section_key, []):
            item.pop("s3_key", None)

    # job_id は残すが、raw な内部パスは返さない
    return m


def _get_job_dir(job_id: str) -> Optional[Path]:
    """job_id から job_dir を返す。"""
    try:
        return jm.get_job_dir(job_id)
    except Exception:
        return None


# ── ヘルスチェック ────────────────────────────────────────────────────────────


@public_dashboard_router.get("/healthz")
def public_health() -> JSONResponse:
    """パブリックダッシュボード API ヘルスチェック。"""
    return JSONResponse({
        "status": "ok",
        "api": "public-dashboards",
        "enabled": _PUBLIC_DASHBOARD_ENABLED,
        "manifest_module": _MANIFEST_AVAILABLE,
    })


# ── ダッシュボード取得 ────────────────────────────────────────────────────────


@public_dashboard_router.get("/dashboards/{dashboard_token}")
def get_dashboard(dashboard_token: str) -> JSONResponse:
    """
    dashboard_token に対応するダッシュボードマニフェストを返す。

    Responses:
        200: マニフェスト JSON
        400: トークン形式不正
        404: トークンが見つからない
        410: トークン期限切れ
        503: API 無効または依存モジュール不可
    """
    if not _PUBLIC_DASHBOARD_ENABLED:
        return JSONResponse({"detail": "パブリックダッシュボード API は無効です。"}, status_code=503)
    if not _MANIFEST_AVAILABLE:
        return JSONResponse({"detail": "ダッシュボードモジュールが利用できません。"}, status_code=503)

    # トークン形式チェック（インジェクション対策）
    if not dashboard_token or not dashboard_token.startswith("dash_") or len(dashboard_token) > 80:
        return JSONResponse({"detail": "トークンが見つかりません。"}, status_code=404)

    # トークン → job_id 解決
    result = find_job_id_by_token(dashboard_token)
    if result is None:
        return JSONResponse({"detail": "ダッシュボードが見つかりません。"}, status_code=404)

    job_id, token_type = result
    if not job_id:
        return JSONResponse({"detail": "ダッシュボードが見つかりません。"}, status_code=404)

    # job_dir 解決
    job_dir = _get_job_dir(job_id)
    if job_dir is None or not job_dir.exists():
        return JSONResponse({"detail": "ジョブディレクトリが見つかりません。"}, status_code=404)

    # マニフェスト読み込み
    manifest = load_dashboard_manifest(job_dir)
    if manifest is None:
        return JSONResponse({"detail": "マニフェストが生成されていません。"}, status_code=404)

    # 期限切れチェック
    if is_token_expired(manifest):
        return JSONResponse(
            {
                "detail": "このダッシュボードの公開期限が切れています。",
                "token_expires_at": manifest.get("token_expires_at"),
                "code": "token_expired",
            },
            status_code=410,
        )

    # presigned URL が期限切れの場合は再生成を試みる
    if _is_url_expired(manifest):
        logger.info("[public_dashboard_api] presigned URL 期限切れ → 再生成試行: %s", job_id)
        manifest = refresh_manifest_urls(manifest, job_id)

    # 内部情報を除去してレスポンス
    return JSONResponse(_sanitize_manifest(manifest))
