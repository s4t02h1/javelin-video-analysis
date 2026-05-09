"""
src/config.py — Javelin Video Analysis: 環境変数設定の一元管理 (Phase 8)

使用方法:
    from src.config import cfg

    jobs_dir = cfg.JOBS_DIR
    log_dir  = cfg.LOG_DIR

ローカル実行時は .env を読み込み、Docker実行時はコンテナの環境変数を使う。
環境変数が未設定の場合はリポジトリルート基準のデフォルト値を使う。
"""
from __future__ import annotations

import os
from pathlib import Path


# ── リポジトリルート ──────────────────────────────────────────────────────────
# src/config.py → src/ → repo root
_REPO_ROOT: Path = Path(__file__).resolve().parent.parent


def _resolve(env_key: str, default_rel: str) -> Path:
    """環境変数が設定されていればその値、なければリポジトリルート相対パスを返す。"""
    val = os.getenv(env_key, "").strip()
    if val:
        p = Path(val)
        return p if p.is_absolute() else (_REPO_ROOT / p)
    return _REPO_ROOT / default_rel


class _Config:
    """アプリ全体の設定値を保持するシングルトン的クラス。"""

    # ── 基本 ─────────────────────────────────────────────────────────────────
    @property
    def ENV(self) -> str:
        return os.getenv("JVA_ENV", "local")

    @property
    def APP_NAME(self) -> str:
        return os.getenv("JVA_APP_NAME", "javelin-video-analysis")

    @property
    def DEBUG(self) -> bool:
        return os.getenv("JVA_DEBUG", "false").lower() == "true"

    # ── ディレクトリ ──────────────────────────────────────────────────────────
    @property
    def REPO_ROOT(self) -> Path:
        return _REPO_ROOT

    @property
    def DATA_DIR(self) -> Path:
        return _resolve("JVA_DATA_DIR", "data")

    @property
    def JOBS_DIR(self) -> Path:
        """ジョブディレクトリ。JVA_DATA_DIR/jobs または JVA_JOBS_DIR で上書き可能。"""
        custom = os.getenv("JVA_JOBS_DIR", "").strip()
        if custom:
            p = Path(custom)
            return p if p.is_absolute() else (_REPO_ROOT / p)
        return self.DATA_DIR / "jobs"

    @property
    def QUEUE_DIR(self) -> Path:
        return _resolve("JVA_QUEUE_DIR", "data/queue")

    @property
    def OUTPUT_DIR(self) -> Path:
        return _resolve("JVA_OUTPUT_DIR", "outputs")

    @property
    def LOG_DIR(self) -> Path:
        return _resolve("JVA_LOG_DIR", "logs")

    @property
    def UPLOAD_DIR(self) -> Path:
        return _resolve("JVA_UPLOAD_DIR", "uploads")

    @property
    def COMPARISONS_DIR(self) -> Path:
        custom = os.getenv("JVA_COMPARISONS_DIR", "").strip()
        if custom:
            p = Path(custom)
            return p if p.is_absolute() else (_REPO_ROOT / p)
        return self.DATA_DIR / "comparisons"

    @property
    def ORDERS_DIR(self) -> Path:
        """注文データディレクトリ (Phase 9)。JVA_ORDERS_DIR で上書き可能。"""
        custom = os.getenv("JVA_ORDERS_DIR", "").strip()
        if custom:
            p = Path(custom)
            return p if p.is_absolute() else (_REPO_ROOT / p)
        return self.DATA_DIR / "orders"

    # ── API ───────────────────────────────────────────────────────────────────
    @property
    def API_KEY(self) -> str:
        return os.getenv("JVA_API_KEY", "")

    @property
    def ENABLE_INTAKE_API(self) -> bool:
        return os.getenv("JVA_ENABLE_INTAKE_API", "true").lower() == "true"

    @property
    def ENABLE_JOBS_API(self) -> bool:
        return os.getenv("JVA_ENABLE_JOBS_API", "true").lower() == "true"

    @property
    def ADMIN_PORT(self) -> int:
        return int(os.getenv("JVA_ADMIN_PORT", "8501"))

    @property
    def ADMIN_PASSWORD(self) -> str:
        """管理画面のパスワード（設定なし = 制限なし）。"""
        return os.getenv("JVA_ADMIN_PASSWORD", "")

    # ── ワーカー / キュー ──────────────────────────────────────────────────────
    @property
    def WORKER_POLL_INTERVAL(self) -> int:
        return int(os.getenv("JVA_WORKER_POLL_INTERVAL_SECONDS", "5"))

    @property
    def WORKER_MAX_RETRIES(self) -> int:
        return int(os.getenv("JVA_WORKER_MAX_RETRIES", "1"))

    @property
    def QUEUE_BACKEND(self) -> str:
        return os.getenv("JVA_QUEUE_BACKEND", "file")

    @property
    def ENABLE_BACKGROUND_WORKER(self) -> bool:
        return os.getenv("JVA_ENABLE_BACKGROUND_WORKER", "true").lower() == "true"

    # ── S3 ────────────────────────────────────────────────────────────────────
    @property
    def AWS_REGION(self) -> str:
        return os.getenv("AWS_REGION", "ap-northeast-1")

    @property
    def S3_BUCKET(self) -> str:
        return os.getenv("JVA_BUCKET", "your-bucket-name")

    @property
    def S3_PREFIX(self) -> str:
        return os.getenv("JVA_S3_PREFIX", "javelin-analysis")

    @property
    def S3_PRESIGNED_EXPIRES(self) -> int:
        return int(os.getenv("JVA_PRESIGNED_URL_EXPIRES_SECONDS", "604800"))

    @property
    def S3_CONFIGURED(self) -> bool:
        """S3 が実際に設定されているかを返す。"""
        return self.S3_BUCKET not in ("", "your-bucket-name")

    # ── LINE ──────────────────────────────────────────────────────────────────
    @property
    def LINE_CHANNEL_SECRET(self) -> str:
        return os.getenv("LINE_CHANNEL_SECRET", "")

    @property
    def LINE_CHANNEL_ACCESS_TOKEN(self) -> str:
        return os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

    @property
    def LINE_WEBHOOK_ENABLED(self) -> bool:
        return os.getenv("LINE_WEBHOOK_ENABLED", "false").lower() == "true"


# シングルトンインスタンス
cfg = _Config()
