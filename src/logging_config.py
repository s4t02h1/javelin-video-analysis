"""
src/logging_config.py — Javelin Video Analysis: ログ設定の一元管理 (Phase 8)

使用方法:
    from src.logging_config import setup_logging, get_logger

    # アプリ起動時に1回だけ呼ぶ
    setup_logging(component="api")

    # モジュール内でロガーを取得
    logger = get_logger(__name__)
    logger.info("処理開始")

コンポーネント別ログファイル:
    logs/api.log         — FastAPI
    logs/worker.log      — バックグラウンドワーカー
    logs/admin.log       — Streamlit 管理画面
    logs/errors.log      — ERROR 以上（全コンポーネント共通）

⚠️  presigned URL・APIキー・個人情報をログに出力しないこと。
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path


_SETUP_DONE: bool = False


def _log_dir() -> Path:
    """ログディレクトリを返す。環境変数 JVA_LOG_DIR が優先される。"""
    val = os.getenv("JVA_LOG_DIR", "").strip()
    if val:
        p = Path(val)
        if not p.is_absolute():
            # リポジトリルート基準に変換
            repo = Path(__file__).resolve().parent.parent
            p = repo / p
        return p
    # デフォルト: リポジトリルート/logs
    return Path(__file__).resolve().parent.parent / "logs"


def setup_logging(
    component: str = "app",
    level: int | str | None = None,
    enable_file: bool = True,
) -> None:
    """ログ設定を初期化する。

    Parameters
    ----------
    component : str
        コンポーネント名 ("api" | "worker" | "admin" | "app")。
        ログファイル名に使用される: logs/<component>.log
    level : int | str | None
        ルートロガーのログレベル。None の場合は JVA_DEBUG 環境変数を参照。
    enable_file : bool
        True の場合はファイルハンドラも追加する（デフォルト: True）。
        False の場合は標準出力のみ（テスト向け）。
    """
    global _SETUP_DONE
    if _SETUP_DONE:
        return
    _SETUP_DONE = True

    # ─ ログレベル決定 ─────────────────────────────────────────────────────────
    if level is None:
        debug = os.getenv("JVA_DEBUG", "false").lower() == "true"
        level = logging.DEBUG if debug else logging.INFO

    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # ─ フォーマッター ─────────────────────────────────────────────────────────
    fmt_detailed = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt_simple = logging.Formatter(
        "[%(levelname)s] %(name)s — %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(level)

    # 既存のハンドラをクリア（多重設定防止）
    root.handlers.clear()

    # ─ 標準出力ハンドラ ───────────────────────────────────────────────────────
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    stdout_handler.setFormatter(fmt_simple)
    root.addHandler(stdout_handler)

    if not enable_file:
        return

    # ─ ファイルハンドラ ───────────────────────────────────────────────────────
    log_dir = _log_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logging.warning("ログディレクトリの作成に失敗しました: %s — ファイルログを無効化します", e)
        return

    # コンポーネント別ログ (logs/<component>.log)
    comp_log = log_dir / f"{component}.log"
    comp_handler = logging.handlers.RotatingFileHandler(
        comp_log,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    comp_handler.setLevel(level)
    comp_handler.setFormatter(fmt_detailed)
    root.addHandler(comp_handler)

    # エラーログ (logs/errors.log)
    err_log = log_dir / "errors.log"
    err_handler = logging.handlers.RotatingFileHandler(
        err_log,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(fmt_detailed)
    root.addHandler(err_handler)

    # サードパーティライブラリのノイズを抑制
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """モジュール名でロガーを取得する。

    使用例:
        logger = get_logger(__name__)
        logger.info("処理完了")
    """
    return logging.getLogger(name)


def reset_for_testing() -> None:
    """テスト用: ログ設定をリセットする。"""
    global _SETUP_DONE
    _SETUP_DONE = False
    root = logging.getLogger()
    root.handlers.clear()
