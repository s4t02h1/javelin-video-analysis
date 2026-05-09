"""
src/storage/s3_storage.py — Javelin Video Analysis S3ストレージユーティリティ

成果物を S3 にアップロードし、presigned URL を生成するユーティリティ。

環境変数 (.env または OS 環境変数):
    AWS_REGION                          (default: ap-northeast-1)
    JVA_BUCKET                          S3バケット名
    JVA_S3_PREFIX                       S3キープレフィックス (default: javelin-analysis)
    JVA_PRESIGNED_URL_EXPIRES_SECONDS   presigned URL 有効期限秒 (default: 604800 = 7日)

セキュリティ:
    - S3バケットは非公開 (Block All Public Access) のまま使用する
    - 共有には presigned URL を使用する
    - ログに個人情報・URLを出力しない
    - AWSクレデンシャルはコードに直書きしない

Usage:
    from src.storage.s3_storage import (
        is_s3_configured, upload_file_to_s3,
        generate_presigned_url, build_s3_key_for_job,
    )
    if is_s3_configured():
        result = upload_file_to_s3(Path("report.pdf"), "javelin-analysis/jobs/xxx/reports/report.pdf")
        url = generate_presigned_url("javelin-analysis/jobs/xxx/reports/report.pdf")
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("javelin.s3_storage")

# ── 設定 ─────────────────────────────────────────────────────────────────────

_DEFAULT_BUCKET_PLACEHOLDER = "your-bucket-name"
_DEFAULT_PREFIX = "javelin-analysis"
_DEFAULT_EXPIRES_SECONDS = 604800  # 7日

# Content-Type マッピング（拡張子 → MIME type）
_CONTENT_TYPE_MAP: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".mp4":  "video/mp4",
    ".mov":  "video/quicktime",
    ".avi":  "video/x-msvideo",
    ".mkv":  "video/x-matroska",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".csv":  "text/csv",
    ".json": "application/json",
    ".zip":  "application/zip",
    ".txt":  "text/plain",
    ".html": "text/html",
    ".htm":  "text/html",
}


def _get_config() -> dict[str, Any]:
    """環境変数から S3 設定を取得する。"""
    return {
        "region":          os.getenv("AWS_REGION", "ap-northeast-1"),
        "bucket":          os.getenv("JVA_BUCKET", _DEFAULT_BUCKET_PLACEHOLDER),
        "prefix":          os.getenv("JVA_S3_PREFIX", _DEFAULT_PREFIX).rstrip("/"),
        "expires_seconds": int(os.getenv("JVA_PRESIGNED_URL_EXPIRES_SECONDS",
                                         str(_DEFAULT_EXPIRES_SECONDS))),
    }


def is_s3_configured() -> bool:
    """S3が使用可能な状態かどうかを返す。

    True の条件:
        1. boto3 がインストールされている
        2. JVA_BUCKET 環境変数が設定されており、プレースホルダー以外の値である
    """
    try:
        import boto3  # noqa: F401
    except ImportError:
        return False
    bucket = os.getenv("JVA_BUCKET", "")
    return bool(bucket and bucket != _DEFAULT_BUCKET_PLACEHOLDER)


def get_s3_config() -> dict[str, Any]:
    """現在の S3 設定を返す（認証情報は含まない）。"""
    cfg = _get_config()
    return {
        "configured": is_s3_configured(),
        "region":     cfg["region"],
        "bucket":     cfg["bucket"],
        "prefix":     cfg["prefix"],
        "expires_seconds": cfg["expires_seconds"],
    }


# ── クライアントキャッシュ ────────────────────────────────────────────────────

_client_cache: Any = None


def _get_client() -> Any:
    """boto3 S3 クライアントを返す（遅延初期化・キャッシュ）。

    Raises
    ------
    RuntimeError
        boto3 未インストールまたは S3 未設定の場合
    """
    global _client_cache
    if _client_cache is not None:
        return _client_cache
    try:
        import boto3
    except ImportError as e:
        raise RuntimeError("boto3 がインストールされていません: pip install boto3") from e
    if not is_s3_configured():
        raise RuntimeError("S3 が設定されていません（JVA_BUCKET 環境変数を設定してください）")
    cfg = _get_config()
    _client_cache = boto3.client("s3", region_name=cfg["region"])
    return _client_cache


def _reset_client_cache() -> None:
    """テスト用: クライアントキャッシュをリセットする。"""
    global _client_cache
    _client_cache = None


# ── キー生成 ─────────────────────────────────────────────────────────────────

def build_s3_key_for_job(job_id: str, relative_path: str) -> str:
    """ジョブ成果物の S3 キーを生成する。

    Parameters
    ----------
    job_id : str
        ジョブID（例: 20260508_054525_147f）
    relative_path : str
        ジョブルートからの相対パス（例: reports/report.pdf）

    Returns
    -------
    str
        S3 キー（例: javelin-analysis/jobs/20260508_054525_147f/reports/report.pdf）
    """
    prefix = _get_config()["prefix"]
    rel = relative_path.lstrip("/").replace("\\", "/")
    return f"{prefix}/jobs/{job_id}/{rel}"


def build_s3_key_for_comparison(comparison_id: str, relative_path: str) -> str:
    """比較ジョブ成果物の S3 キーを生成する。

    Parameters
    ----------
    comparison_id : str
        比較ジョブID（例: 20260510_012144_abcd_cmp）
    relative_path : str
        比較ジョブルートからの相対パス（例: comparison_report.pdf）
    """
    prefix = _get_config()["prefix"]
    rel = relative_path.lstrip("/").replace("\\", "/")
    return f"{prefix}/comparisons/{comparison_id}/{rel}"


def infer_content_type(local_path: Path) -> str:
    """ファイル拡張子から Content-Type を推定する。"""
    return _CONTENT_TYPE_MAP.get(local_path.suffix.lower(), "application/octet-stream")


# ── アップロード ──────────────────────────────────────────────────────────────

def upload_file_to_s3(
    local_path: Path,
    s3_key: str,
    content_type: Optional[str] = None,
) -> dict[str, Any]:
    """ファイルを S3 にアップロードする。

    Parameters
    ----------
    local_path : Path
        アップロードするローカルファイルのパス
    s3_key : str
        S3 キー
    content_type : str, optional
        Content-Type（省略時はファイル拡張子から推定）

    Returns
    -------
    dict with keys:
        ok       : bool  成功／失敗
        s3_key   : str   アップロード先キー
        error    : str | None  失敗時のエラーメッセージ
    """
    local_path = Path(local_path)
    if not local_path.exists():
        msg = f"ファイルが見つかりません: {local_path.name}"
        logger.warning("[s3_storage] %s", msg)
        return {"ok": False, "s3_key": s3_key, "error": msg}

    if not local_path.is_file():
        msg = f"ディレクトリです（ファイルを指定してください）: {local_path.name}"
        return {"ok": False, "s3_key": s3_key, "error": msg}

    ct = content_type or infer_content_type(local_path)
    cfg = _get_config()
    bucket = cfg["bucket"]

    try:
        client = _get_client()
        client.upload_file(
            str(local_path),
            bucket,
            s3_key,
            ExtraArgs={"ContentType": ct},
        )
        logger.info("[s3_storage] アップロード完了: %s → s3://%s/%s", local_path.name, bucket, s3_key)
        return {"ok": True, "s3_key": s3_key, "error": None}
    except Exception as e:
        msg = str(e)
        logger.error("[s3_storage] アップロード失敗: %s — %s", local_path.name, msg)
        return {"ok": False, "s3_key": s3_key, "error": msg}


def upload_directory_to_s3(
    local_dir: Path,
    s3_prefix: str,
    extensions: Optional[list[str]] = None,
) -> dict[str, Any]:
    """ディレクトリ以下のファイルをすべて S3 にアップロードする。

    Parameters
    ----------
    local_dir : Path
        アップロードするディレクトリ
    s3_prefix : str
        S3 キープレフィックス（末尾スラッシュは自動除去）
    extensions : list[str], optional
        対象拡張子リスト（例: [".mp4", ".pdf"]）。省略時は全ファイル。

    Returns
    -------
    dict with keys:
        uploaded : list[dict]   成功したファイルのリスト
        failed   : list[dict]   失敗したファイルのリスト
        skipped  : list[str]    スキップしたファイル名リスト
    """
    local_dir = Path(local_dir)
    s3_prefix = s3_prefix.rstrip("/")
    uploaded: list[dict] = []
    failed: list[dict] = []
    skipped: list[str] = []

    if not local_dir.exists():
        logger.warning("[s3_storage] ディレクトリが見つかりません: %s", local_dir)
        return {"uploaded": uploaded, "failed": failed, "skipped": skipped}

    for file_path in sorted(local_dir.rglob("*")):
        if not file_path.is_file():
            continue
        if extensions and file_path.suffix.lower() not in extensions:
            skipped.append(file_path.name)
            continue
        rel = file_path.relative_to(local_dir).as_posix()
        s3_key = f"{s3_prefix}/{rel}"
        result = upload_file_to_s3(file_path, s3_key)
        if result["ok"]:
            uploaded.append(result)
        else:
            failed.append(result)

    return {"uploaded": uploaded, "failed": failed, "skipped": skipped}


# ── presigned URL ─────────────────────────────────────────────────────────────

def generate_presigned_url(
    s3_key: str,
    expires_seconds: Optional[int] = None,
) -> Optional[str]:
    """S3 オブジェクトの presigned GET URL を生成する。

    Parameters
    ----------
    s3_key : str
        S3 キー
    expires_seconds : int, optional
        有効期限秒数。省略時は環境変数 JVA_PRESIGNED_URL_EXPIRES_SECONDS を使用。

    Returns
    -------
    str | None
        presigned URL。失敗時は None を返す。
    """
    cfg = _get_config()
    bucket = cfg["bucket"]
    expires = expires_seconds if expires_seconds is not None else cfg["expires_seconds"]
    try:
        client = _get_client()
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=expires,
        )
        return url
    except Exception as e:
        logger.error("[s3_storage] presigned URL 生成失敗: %s", e)
        return None


def get_presigned_url_expires_at(expires_seconds: Optional[int] = None) -> str:
    """presigned URL の有効期限（ISO 8601 文字列）を返す。"""
    cfg = _get_config()
    expires = expires_seconds if expires_seconds is not None else cfg["expires_seconds"]
    dt = datetime.now(timezone.utc) + timedelta(seconds=expires)
    return dt.isoformat(timespec="seconds")


def generate_presigned_urls_for_job(
    job_id: str,
    artifact_manifest: Optional[list[dict]] = None,
    expires_seconds: Optional[int] = None,
) -> dict[str, Optional[str]]:
    """ジョブのすべての成果物 presigned URL を生成する。

    Parameters
    ----------
    job_id : str
        ジョブID
    artifact_manifest : list[dict], optional
        artifact_manifest.json の artifacts リスト。
        省略時はキー "s3_key" を含む全エントリを対象にする。
    expires_seconds : int, optional
        有効期限秒数

    Returns
    -------
    dict[str, str | None]
        s3_key → presigned URL のマッピング。失敗したキーの値は None。
    """
    if not artifact_manifest:
        return {}
    result: dict[str, Optional[str]] = {}
    for entry in artifact_manifest:
        s3_key = entry.get("s3_key")
        if s3_key:
            result[s3_key] = generate_presigned_url(s3_key, expires_seconds)
    return result


def list_uploaded_artifacts(job_id: str) -> list[dict]:
    """ジョブのアップロード済み S3 オブジェクト一覧を返す。

    Returns
    -------
    list[dict]
        [{"key": str, "size": int, "last_modified": str}, ...]
    """
    cfg = _get_config()
    prefix = f"{cfg['prefix']}/jobs/{job_id}/"
    bucket = cfg["bucket"]
    try:
        client = _get_client()
        paginator = client.get_paginator("list_objects_v2")
        items: list[dict] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                items.append({
                    "key":           obj["Key"],
                    "size":          obj.get("Size", 0),
                    "last_modified": obj.get("LastModified", "").isoformat()
                    if hasattr(obj.get("LastModified", ""), "isoformat") else str(obj.get("LastModified", "")),
                })
        return items
    except Exception as e:
        logger.error("[s3_storage] オブジェクト一覧取得失敗: %s", e)
        return []


# ── アップロードログ ─────────────────────────────────────────────────────────

def append_upload_log(
    log_path: Path,
    job_id: str,
    uploaded: list[dict],
    failed: list[dict],
    expires_at: str,
) -> None:
    """S3 アップロードのログを追記する。

    presigned URL や個人情報はログに出力しない。

    Parameters
    ----------
    log_path : Path
        ログファイルのパス（追記）
    job_id : str
        ジョブID
    uploaded : list[dict]
        アップロード成功リスト（各 dict に "s3_key" を含む）
    failed : list[dict]
        アップロード失敗リスト（各 dict に "s3_key", "error" を含む）
    expires_at : str
        URL 有効期限（ISO 8601 文字列）
    """
    now = datetime.now().isoformat(timespec="seconds")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n[{now}] job_id={job_id}\n")
        f.write(f"  アップロード成功: {len(uploaded)} 件\n")
        for item in uploaded:
            f.write(f"    + {item.get('s3_key', '?')}\n")
        if failed:
            f.write(f"  アップロード失敗: {len(failed)} 件\n")
            for item in failed:
                f.write(f"    x {item.get('s3_key', '?')} — {item.get('error', '')}\n")
        f.write(f"  URL有効期限: {expires_at}\n")
