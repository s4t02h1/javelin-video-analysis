"""
src/job_logger.py — Javelin Video Analysis ジョブ別ロガー

各ジョブの操作ログを jobs/<job_id>/logs/job_log.txt に追記する。
ログ項目: 日時 / ジョブID / 処理名 / 成功or失敗 / エラー内容 / 生成ファイル名
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── プロセスレベルのモジュールロガー ─────────────────────────────────────────

_module_logger = logging.getLogger("javelin.job_logger")


def _jobs_dir() -> Path:
    """JOBS_DIR を動的に解決する（循環 import 回避）。"""
    try:
        from job_manager import JOBS_DIR
        return JOBS_DIR
    except ImportError:
        return Path(__file__).resolve().parent.parent / "jobs"


# ── 主要 API ──────────────────────────────────────────────────────────────────

def log_event(
    job_id: str,
    action: str,
    success: bool,
    *,
    file_name: Optional[str] = None,
    error: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """ジョブ別ログファイルに1行追記する。

    Parameters
    ----------
    job_id   : ジョブID
    action   : 処理名（例: 'pdf_generated', 'status_changed'）
    success  : 成功 True / 失敗 False
    file_name: 生成・操作したファイル名（任意）
    error    : エラー内容の文字列（任意）
    extra    : 追加情報 dict（任意）
    """
    now = datetime.now().isoformat(timespec="seconds")
    record: dict = {
        "ts":       now,
        "job_id":   job_id,
        "action":   action,
        "success":  success,
    }
    if file_name:
        record["file_name"] = file_name
    if error:
        record["error"] = error[:1000]   # 長すぎるスタックは切り捨て
    if extra:
        record["extra"] = extra

    line = json.dumps(record, ensure_ascii=False)

    # ── jobs/<job_id>/logs/job_log.txt に追記 ───────────────────────────────
    try:
        log_path = _jobs_dir() / job_id / "logs" / "job_log.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as _e:
        _module_logger.warning("[job_logger] ログ書き込み失敗 (%s): %s", job_id, _e)

    # ── コンソールにも出力 ────────────────────────────────────────────────────
    level = logging.INFO if success else logging.WARNING
    _module_logger.log(level, "[%s] %s  success=%s  file=%s  error=%s",
                       job_id, action, success, file_name, error)


def read_job_log(job_id: str) -> list[dict]:
    """jobs/<job_id>/logs/job_log.txt を読み込んで dict のリストで返す。

    ファイルが存在しない / 読み込み失敗時は空リストを返す。
    """
    log_path = _jobs_dir() / job_id / "logs" / "job_log.txt"
    if not log_path.exists():
        return []
    records: list[dict] = []
    try:
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({"raw": line})
    except Exception as _e:
        _module_logger.warning("[job_logger] ログ読み込み失敗 (%s): %s", job_id, _e)
    return records


# ── 便利ラッパー ──────────────────────────────────────────────────────────────

def log_status_change(job_id: str, old_status: str, new_status: str) -> None:
    log_event(job_id, "status_changed", True,
              extra={"from": old_status, "to": new_status})


def log_pdf_generated(job_id: str, file_name: str) -> None:
    log_event(job_id, "pdf_generated", True, file_name=file_name)


def log_zip_generated(job_id: str, file_name: str) -> None:
    log_event(job_id, "zip_generated", True, file_name=file_name)


def log_analysis_start(job_id: str) -> None:
    log_event(job_id, "analysis_start", True)


def log_analysis_complete(job_id: str, output_count: int) -> None:
    log_event(job_id, "analysis_complete", True, extra={"output_count": output_count})


def log_error(job_id: str, action: str, error: str) -> None:
    log_event(job_id, action, False, error=error)
