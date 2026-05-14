from __future__ import annotations

import logging
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, Header, UploadFile
from fastapi.responses import JSONResponse

_SERVER_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SERVER_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.upload_receipts import (
    UPLOADS_DIR,
    append_receipt,
    build_saved_filename,
    ensure_storage_dirs,
    generate_receipt_id,
    list_upload_receipts,
    receipt_template,
    to_relative_path,
    sanitize_ext,
)

logger = logging.getLogger("jva.upload_api")

upload_router = APIRouter(tags=["upload"])

MAX_UPLOAD_MB = int(os.getenv("JVA_MAX_UPLOAD_MB", "300"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ADMIN_TOKEN = os.getenv("JVA_ADMIN_TOKEN", "")


@upload_router.post("/api/upload")
async def api_upload_video(
    name: str = Form(...),
    sns: str = Form(...),
    event: str = Form("javelin"),
    snsConsent: str = Form("unknown"),
    agree: str = Form("false"),
    file: UploadFile = File(...),
) -> JSONResponse:
    if file is None:
        return JSONResponse({"error": "動画ファイルが選択されていません。"}, status_code=400)

    original_filename = file.filename or "upload.bin"
    try:
        ext = sanitize_ext(original_filename)
    except ValueError as ve:
        return JSONResponse({"error": str(ve)}, status_code=400)

    agree_bool = str(agree).lower() in {"true", "1", "yes", "on"}
    if not agree_bool:
        return JSONResponse({"error": "注意事項への同意が必要です。"}, status_code=400)

    ensure_storage_dirs()

    try:
        rows = list_upload_receipts()
        receipt_id = generate_receipt_id(rows)
        day_dir = UPLOADS_DIR / datetime.now().strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        saved_filename = build_saved_filename(receipt_id, ext)
        save_path = day_dir / saved_filename

        total = 0
        try:
            with open(save_path, "wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        out.close()
                        try:
                            save_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                        return JSONResponse(
                            {"error": f"ファイルサイズ上限は{MAX_UPLOAD_MB}MBです。"},
                            status_code=413,
                        )
                    out.write(chunk)
        except OSError:
            return JSONResponse({"error": "動画ファイルの保存に失敗しました。"}, status_code=500)

        row = receipt_template()
        row.update(
            {
                "receiptId": receipt_id,
                "createdAt": datetime.now().isoformat(timespec="seconds"),
                "name": name.strip(),
                "sns": sns.strip(),
                "event": (event or "javelin").strip(),
                "originalFilename": original_filename,
                "savedFilename": saved_filename,
                "filePath": to_relative_path(save_path),
                "fileSize": total,
                "snsConsent": (snsConsent or "unknown").strip(),
                "agree": agree_bool,
                "status": "uploaded",
                "note": "",
                "errorMessage": "",
            }
        )
        try:
            append_receipt(row)
        except Exception:
            logger.exception("受付データ保存に失敗: receiptId=%s", receipt_id)
            try:
                save_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("孤立ファイルの削除に失敗: %s", save_path)
            return JSONResponse({"error": "受付データの保存に失敗しました。"}, status_code=500)
        return JSONResponse({"ok": True, "receiptId": receipt_id}, status_code=201)

    except Exception as exc:
        logger.exception("アップロード処理中にエラー: %s", exc)
        return JSONResponse(
            {"error": "アップロード中にエラーが発生しました。時間をおいて再度お試しください。"},
            status_code=500,
        )
    finally:
        try:
            await file.close()
        except Exception:
            pass


@upload_router.get("/api/upload-receipts")
def api_upload_receipts(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> JSONResponse:
    """Simple list endpoint for admin/debug use."""
    if not ADMIN_TOKEN:
        return JSONResponse(
            {"error": "管理者トークンが未設定です。JVA_ADMIN_TOKEN を設定してください。"},
            status_code=503,
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, ADMIN_TOKEN):
        return JSONResponse({"error": "forbidden"}, status_code=403)

    try:
        rows = list_upload_receipts()
        return JSONResponse(rows)
    except Exception as exc:
        logger.exception("受付一覧の取得エラー: %s", exc)
        return JSONResponse({"error": "受付一覧の取得に失敗しました。"}, status_code=500)
