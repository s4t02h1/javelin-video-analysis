from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = _REPO_ROOT / "uploads"
OUTPUTS_DIR = _REPO_ROOT / "outputs"
DATA_DIR = _REPO_ROOT / "data" / "upload_receipts"
RECEIPTS_JSON = DATA_DIR / "receipts.json"

_ALLOWED_EXTS = {"mp4", "mov"}

WEB_RECEIPT_STATUSES = [
    "uploaded",
    "checking",
    "processing",
    "completed",
    "failed",
    "needs_resubmission",
    "delivered",
]

WEB_RECEIPT_STATUS_LABELS = {
    "uploaded": "受付済み",
    "checking": "確認中",
    "processing": "解析中",
    "completed": "解析完了",
    "failed": "解析失敗",
    "needs_resubmission": "再投稿依頼",
    "delivered": "送付済み",
}


def ensure_storage_dirs() -> None:
    """Create local storage folders if missing."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_receipts() -> List[Dict[str, Any]]:
    if not RECEIPTS_JSON.exists():
        return []
    with open(RECEIPTS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return []


def _save_receipts(rows: List[Dict[str, Any]]) -> None:
    ensure_storage_dirs()
    tmp_path = RECEIPTS_JSON.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    tmp_path.replace(RECEIPTS_JSON)


def _next_sequence_for_day(rows: List[Dict[str, Any]], ymd: str) -> int:
    pat = re.compile(rf"^JMA-{ymd}-(\d{{4}})$")
    max_seq = 0
    for row in rows:
        rid = str(row.get("receiptId", ""))
        m = pat.match(rid)
        if m:
            max_seq = max(max_seq, int(m.group(1)))
    return max_seq + 1


def generate_receipt_id(rows: List[Dict[str, Any]] | None = None) -> str:
    now = datetime.now()
    ymd = now.strftime("%Y%m%d")
    if rows is None:
        rows = _load_receipts()
    seq = _next_sequence_for_day(rows, ymd)
    return f"JMA-{ymd}-{seq:04d}"


def sanitize_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in _ALLOWED_EXTS:
        raise ValueError("対応形式は .mp4 / .mov / .MOV のみです。")
    return ext


def build_saved_filename(receipt_id: str, ext: str) -> str:
    return f"{receipt_id}_{uuid.uuid4().hex[:10]}.{ext}"


def to_relative_path(path: Path | str) -> str:
    """Return a repository-relative POSIX path string for stored metadata."""
    p = Path(path)
    try:
        return p.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    except Exception:
        return p.as_posix()


def resolve_receipt_file_path(path_str: str) -> Path:
    """Resolve receipt filePath into an absolute path for local file operations."""
    p = Path(path_str)
    if p.is_absolute():
        return p
    resolved = (_REPO_ROOT / p).resolve()
    # Ensure relative paths stay inside repository root.
    if _REPO_ROOT.resolve() not in resolved.parents and resolved != _REPO_ROOT.resolve():
        raise ValueError("無効な相対パスです。")
    return resolved


def resolve_upload_path(file_path: str) -> Path:
    """Resolve upload filePath (relative or absolute) into a safe absolute path."""
    return resolve_receipt_file_path(file_path)


def resolve_output_dir(receipt_id: str) -> Path:
    """Return outputs/{receiptId} absolute path."""
    rid = str(receipt_id or "").strip()
    if not rid:
        raise ValueError("receiptId が不正です。")
    return (OUTPUTS_DIR / rid).resolve()


def append_receipt(row: Dict[str, Any]) -> None:
    rows = _load_receipts()
    receipt_id = str(row.get("receiptId", "")).strip()
    if receipt_id and any(str(r.get("receiptId", "")).strip() == receipt_id for r in rows):
        raise ValueError(f"receiptId が重複しています: {receipt_id}")
    rows.append(row)
    _save_receipts(rows)


def list_upload_receipts() -> List[Dict[str, Any]]:
    rows = _load_receipts()
    rows.sort(key=lambda r: str(r.get("createdAt", "")), reverse=True)
    return rows


def get_upload_receipt(receipt_id: str) -> Dict[str, Any] | None:
    rows = _load_receipts()
    for row in rows:
        if str(row.get("receiptId", "")).strip() == receipt_id.strip():
            return row
    return None


def get_receipt(receipt_id: str) -> Dict[str, Any] | None:
    """Compatibility API: get one receipt by receiptId."""
    return get_upload_receipt(receipt_id)


_UPDATABLE_FIELDS = {
    "status",
    "note",
    "errorMessage",
    "outputDir",
    "resultZipPath",
    "completedAt",
    "deliveredAt",
}


def update_upload_receipt(receipt_id: str, **updates: Any) -> Dict[str, Any]:
    rows = _load_receipts()
    rid = receipt_id.strip()
    for idx, row in enumerate(rows):
        if str(row.get("receiptId", "")).strip() == rid:
            safe_updates = {k: v for k, v in updates.items() if k in _UPDATABLE_FIELDS}
            merged = {**row, **safe_updates}
            # status は定義済みのみ許可。未定義はそのまま元の値を維持。
            if "status" in safe_updates and safe_updates["status"] not in WEB_RECEIPT_STATUSES:
                merged["status"] = row.get("status", "uploaded")

            # status 連動タイムスタンプ
            now = datetime.now().isoformat(timespec="seconds")
            if merged.get("status") == "completed" and not merged.get("completedAt"):
                merged["completedAt"] = now
            if merged.get("status") == "delivered" and not merged.get("deliveredAt"):
                merged["deliveredAt"] = now

            # outputDir / resultZipPath は保存時に相対パスへ正規化
            if "outputDir" in merged and merged.get("outputDir"):
                merged["outputDir"] = to_relative_path(str(merged.get("outputDir")))
            if "resultZipPath" in merged and merged.get("resultZipPath"):
                merged["resultZipPath"] = to_relative_path(str(merged.get("resultZipPath")))

            rows[idx] = merged
            _save_receipts(rows)
            return merged
    raise ValueError(f"receiptId が見つかりません: {receipt_id}")


def update_receipt(receipt_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibility API: update receipt fields with a dict payload."""
    if not isinstance(updates, dict):
        raise ValueError("updates は dict で指定してください。")
    return update_upload_receipt(receipt_id, **updates)


def receipt_template() -> Dict[str, Any]:
    return {
        "receiptId": "",
        "createdAt": "",
        "name": "",
        "sns": "",
        "event": "javelin",
        "originalFilename": "",
        "savedFilename": "",
        "filePath": "",
        "fileSize": 0,
        "snsConsent": "unknown",
        "agree": False,
        "status": "uploaded",
        "note": "",
        "errorMessage": "",
        "outputDir": "",
        "resultZipPath": "",
        "completedAt": "",
        "deliveredAt": "",
    }
