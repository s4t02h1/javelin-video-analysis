"""
src/queue_manager.py — Javelin Video Analysis: ファイルベースジョブキュー (Phase 7)

Redis や Celery に依存しない軽量キュー実装。
将来的に Redis / Celery / RQ / Docker / ECS などへ移行できる設計。

ディレクトリ構造:
    data/queue/
        pending/    {queue_id}.json
        running/    {queue_id}.json
        completed/  {queue_id}.json
        failed/     {queue_id}.json
        cancelled/  {queue_id}.json

ステータス遷移:
    pending → running → completed
    pending → cancelled
    running → failed
    running → completed
    failed  → pending (retry)
    cancelled → pending (retry)
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.queue")

# ── ディレクトリ設定 ──────────────────────────────────────────────────────────

_MODULE_DIR = Path(__file__).resolve().parent   # src/
_REPO_ROOT  = _MODULE_DIR.parent                # project root
_DEFAULT_QUEUE_DIR = _REPO_ROOT / "data" / "queue"


def _queue_root() -> Path:
    """環境変数 JVA_QUEUE_DIR が設定されていればそちらを使う。"""
    d = os.getenv("JVA_QUEUE_DIR", "")
    return Path(d) if d else _DEFAULT_QUEUE_DIR


def _status_dir(status: str) -> Path:
    """ステータスに対応するディレクトリを返す。retrying は pending と同じ。"""
    s = "pending" if status == "retrying" else status
    return _queue_root() / s


def _ensure_dirs() -> None:
    """キューディレクトリを作成する。"""
    for s in ("pending", "running", "completed", "failed", "cancelled"):
        (_queue_root() / s).mkdir(parents=True, exist_ok=True)


# ── 定数 ──────────────────────────────────────────────────────────────────────

QUEUE_STATUSES: List[str] = [
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "retrying",
]

QUEUE_STATUS_LABELS: Dict[str, str] = {
    "pending":   "待機中",
    "running":   "処理中",
    "completed": "完了",
    "failed":    "失敗",
    "cancelled": "キャンセル",
    "retrying":  "リトライ待ち",
}

JOB_TYPES: List[str] = [
    "single_analysis",
    "comparison_analysis",
    "report_generation",
    "s3_upload",
    "delivery_page_generation",
    "full_pipeline",
]

PIPELINE_STEPS: List[str] = [
    "validate_inputs",
    "run_analysis",
    "generate_artifacts",
    "generate_reports",
    "generate_packages",
    "upload_to_s3",
    "generate_delivery_page",
    "update_delivery_url",
    "mark_ready",
]

_QUEUE_JOB_DEFAULTS: Dict[str, Any] = {
    "queue_id":         "",
    "job_id":           "",
    "job_type":         "full_pipeline",
    "status":           "pending",
    "priority":         5,
    "created_at":       "",
    "updated_at":       "",
    "started_at":       None,
    "finished_at":      None,
    "retry_count":      0,
    "max_retries":      1,
    "requested_by":     "",
    "source":           "",
    "steps":            [],
    "current_step":     None,
    "last_error":       None,
    "failed_step":      None,
    "cancel_requested": False,
}


# ── ID 生成 ───────────────────────────────────────────────────────────────────

def generate_queue_id() -> str:
    """qjob_YYYYMMDD_HHMMSS_xxxx 形式の ID を生成する。"""
    now = datetime.now()
    suffix = "".join(random.choices("0123456789abcdef", k=4))
    return now.strftime("qjob_%Y%m%d_%H%M%S") + f"_{suffix}"


# ── ファイルパス ──────────────────────────────────────────────────────────────

def _find_queue_file(queue_id: str) -> Optional[Path]:
    """全ステータスディレクトリから queue_id.json を探す。"""
    for s in ("pending", "running", "completed", "failed", "cancelled"):
        p = (_queue_root() / s) / f"{queue_id}.json"
        if p.exists():
            return p
    return None


def _write_queue_job(qjob: Dict[str, Any], target_dir: Path) -> Path:
    """target_dir にキュージョブ JSON を書き込み、パスを返す。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    p = target_dir / f"{qjob['queue_id']}.json"
    p.write_text(json.dumps(qjob, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_queue_job(
    job_id: str,
    job_type: str = "full_pipeline",
    **kwargs: Any,
) -> Dict[str, Any]:
    """新しいキュージョブを作成して pending に積む。

    Parameters
    ----------
    job_id : str
        紐付ける解析ジョブの ID (job_manager の job_id)
    job_type : str
        処理タイプ (JOB_TYPES のいずれか)
    **kwargs : Any
        _QUEUE_JOB_DEFAULTS のキーを上書き可能

    Returns
    -------
    dict : 作成したキュージョブ
    """
    _ensure_dirs()
    now = datetime.now().isoformat(timespec="seconds")
    queue_id = generate_queue_id()
    qjob: Dict[str, Any] = {
        **_QUEUE_JOB_DEFAULTS,
        "queue_id":   queue_id,
        "job_id":     job_id,
        "job_type":   job_type if job_type in JOB_TYPES else "full_pipeline",
        "status":     "pending",
        "created_at": now,
        "updated_at": now,
        "steps":      [],
    }
    for k, v in kwargs.items():
        if k in _QUEUE_JOB_DEFAULTS:
            qjob[k] = v
    _write_queue_job(qjob, _status_dir("pending"))
    logger.info("[queue] キュー投入: queue_id=%s job_id=%s type=%s",
                queue_id, job_id, qjob["job_type"])
    return qjob


def load_queue_job(queue_id: str) -> Dict[str, Any]:
    """queue_id.json を読み込み、デフォルト値とマージして返す。"""
    p = _find_queue_file(queue_id)
    if p is None:
        raise FileNotFoundError(f"キュージョブが見つかりません: {queue_id}")
    data: Dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return {**_QUEUE_JOB_DEFAULTS, **data}


def update_queue_job(queue_id: str, **kwargs: Any) -> Dict[str, Any]:
    """キュージョブのフィールドを更新する。

    ステータスが変わった場合はファイルを新しいディレクトリに書き込み、旧ファイルを削除する。
    queue_id / created_at は外部から変更不可。
    """
    qjob = load_queue_job(queue_id)
    old_status = qjob["status"]

    # 保護フィールドを除外
    for protected in ("queue_id", "created_at"):
        kwargs.pop(protected, None)

    for k, v in kwargs.items():
        qjob[k] = v
    qjob["updated_at"] = datetime.now().isoformat(timespec="seconds")
    new_status = qjob["status"]

    old_p = _find_queue_file(queue_id)
    new_dir = _status_dir(new_status)
    new_p = _write_queue_job(qjob, new_dir)

    if old_p and old_p != new_p and old_p.exists():
        try:
            old_p.unlink()
        except Exception:
            pass

    return qjob


def list_queue_jobs(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """キュージョブ一覧を返す（新しい順）。

    Parameters
    ----------
    status : str, optional
        指定した場合そのステータスのみ返す。
        None の場合は全ステータスを返す。
    """
    _ensure_dirs()
    jobs: List[Dict[str, Any]] = []
    dirs_to_scan: List[str] = (
        [status] if (status and status != "retrying") else
        ["pending"] if status == "retrying" else
        ["pending", "running", "completed", "failed", "cancelled"]
    )

    for s in dirs_to_scan:
        d = _queue_root() / s
        if not d.exists():
            continue
        for p in d.glob("qjob_*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                qjob = {**_QUEUE_JOB_DEFAULTS, **data}
                # retrying フィルタ: pending ディレクトリの retry_count > 0 なもの
                if status == "retrying" and qjob.get("retry_count", 0) == 0:
                    continue
                if status and status not in ("retrying",) and qjob.get("status") != status:
                    continue
                jobs.append(qjob)
            except Exception:
                pass

    jobs.sort(key=lambda q: q.get("created_at", ""), reverse=True)
    return jobs


def get_queue_counts() -> Dict[str, int]:
    """ステータスごとの件数を返す。"""
    counts: Dict[str, int] = {s: 0 for s in QUEUE_STATUSES}
    _ensure_dirs()
    for s in ("pending", "running", "completed", "failed", "cancelled"):
        d = _queue_root() / s
        if d.exists():
            for p in d.glob("qjob_*.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    actual = data.get("status", s)
                    if actual in counts:
                        counts[actual] += 1
                    else:
                        counts[s] += 1
                except Exception:
                    counts[s] += 1
    return counts


def find_queue_job_for_job(job_id: str) -> Optional[Dict[str, Any]]:
    """job_id に紐付いた最新のキュージョブを返す。なければ None。"""
    candidates = [q for q in list_queue_jobs() if q.get("job_id") == job_id]
    if not candidates:
        return None
    return sorted(candidates, key=lambda q: q.get("created_at", ""), reverse=True)[0]


def find_active_queue_job_for_job(job_id: str) -> Optional[Dict[str, Any]]:
    """job_id に紐付いた pending または running のキュージョブを返す。"""
    for s in ("pending", "running"):
        d = _queue_root() / s
        if not d.exists():
            continue
        for p in d.glob("qjob_*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("job_id") == job_id:
                    return {**_QUEUE_JOB_DEFAULTS, **data}
            except Exception:
                pass
    return None


# ── ワーカー向け操作 ──────────────────────────────────────────────────────────

def claim_next_pending() -> Optional[Dict[str, Any]]:
    """pending の中で最も古いジョブをアトミックに running に移動して返す。

    os.rename() を使ってファイルレベルで排他的に取得する。
    取得できなければ None を返す。
    cancel_requested なジョブはスキップして cancelled に移動する。
    """
    _ensure_dirs()
    pending_dir = _queue_root() / "pending"
    running_dir = _queue_root() / "running"

    # ファイル名でソート（qjob_YYYYMMDD_HHMMSS_xxxx.json → 作成順）
    candidates: List[Path] = sorted(pending_dir.glob("qjob_*.json"))

    for pending_p in candidates:
        queue_id = pending_p.stem
        try:
            qjob = {**_QUEUE_JOB_DEFAULTS,
                    **json.loads(pending_p.read_text(encoding="utf-8"))}
        except Exception:
            continue

        if qjob.get("cancel_requested"):
            _cancel_pending(qjob, pending_p)
            continue

        running_p = running_dir / f"{queue_id}.json"

        # アトミックな移動: rename が成功したワーカーが所有権を獲得
        try:
            # Windows では rename は宛先が存在しない場合にアトミック
            pending_p.rename(running_p)
        except OSError:
            continue  # 別ワーカーが先に取得、またはファイルが消えた

        # 取得成功 → ステータスを更新して書き込む
        now = datetime.now().isoformat(timespec="seconds")
        qjob["status"] = "running"
        qjob["started_at"] = now
        qjob["updated_at"] = now
        running_p.write_text(json.dumps(qjob, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("[queue] 処理開始: queue_id=%s job_id=%s",
                    queue_id, qjob.get("job_id"))
        return qjob

    return None


def _cancel_pending(qjob: Dict[str, Any], src_path: Path) -> None:
    """cancel_requested な pending ジョブを cancelled に移動する（内部用）。"""
    now = datetime.now().isoformat(timespec="seconds")
    qjob["status"] = "cancelled"
    qjob["updated_at"] = now
    cancelled_dir = _queue_root() / "cancelled"
    cancelled_dir.mkdir(parents=True, exist_ok=True)
    dest = cancelled_dir / src_path.name
    _write_queue_job(qjob, cancelled_dir)
    try:
        src_path.unlink()
    except Exception:
        pass
    logger.info("[queue] キャンセル済みをスキップ: queue_id=%s", qjob.get("queue_id"))


def complete_queue_job(
    queue_id: str,
    steps: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """キュージョブを completed に更新する。"""
    _ensure_dirs()
    qjob = load_queue_job(queue_id)
    now = datetime.now().isoformat(timespec="seconds")
    qjob["status"] = "completed"
    qjob["finished_at"] = now
    qjob["updated_at"] = now
    if steps is not None:
        qjob["steps"] = steps
    qjob["current_step"] = None

    old_p = _find_queue_file(queue_id)
    new_p = _write_queue_job(qjob, _queue_root() / "completed")
    if old_p and old_p != new_p and old_p.exists():
        try:
            old_p.unlink()
        except Exception:
            pass

    logger.info("[queue] 完了: queue_id=%s job_id=%s",
                queue_id, qjob.get("job_id"))
    return qjob


def fail_queue_job(
    queue_id: str,
    error: str,
    failed_step: Optional[str] = None,
    steps: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """キュージョブを failed に更新する。"""
    _ensure_dirs()
    qjob = load_queue_job(queue_id)
    now = datetime.now().isoformat(timespec="seconds")
    qjob["status"] = "failed"
    qjob["finished_at"] = now
    qjob["updated_at"] = now
    qjob["last_error"] = str(error)[:2000]
    if failed_step is not None:
        qjob["failed_step"] = failed_step
    if steps is not None:
        qjob["steps"] = steps
    qjob["current_step"] = None

    old_p = _find_queue_file(queue_id)
    new_p = _write_queue_job(qjob, _queue_root() / "failed")
    if old_p and old_p != new_p and old_p.exists():
        try:
            old_p.unlink()
        except Exception:
            pass

    logger.warning("[queue] 失敗: queue_id=%s job_id=%s step=%s error=%.200s",
                   queue_id, qjob.get("job_id"), failed_step, error)
    return qjob


def cancel_queue_job(queue_id: str) -> Dict[str, Any]:
    """キュージョブをキャンセルする。

    - pending: 即時 cancelled に移動
    - running: cancel_requested フラグを立てる（ワーカーが次チェック時に中断）
    - その他: ValueError
    """
    qjob = load_queue_job(queue_id)
    status = qjob.get("status", "")

    if status == "pending":
        old_p = _find_queue_file(queue_id)
        now = datetime.now().isoformat(timespec="seconds")
        qjob["status"] = "cancelled"
        qjob["updated_at"] = now
        new_p = _write_queue_job(qjob, _queue_root() / "cancelled")
        if old_p and old_p != new_p and old_p.exists():
            try:
                old_p.unlink()
            except Exception:
                pass
        logger.info("[queue] キャンセル: queue_id=%s job_id=%s",
                    queue_id, qjob.get("job_id"))
        return qjob

    elif status == "running":
        qjob["cancel_requested"] = True
        qjob["updated_at"] = datetime.now().isoformat(timespec="seconds")
        old_p = _find_queue_file(queue_id)
        if old_p:
            old_p.write_text(json.dumps(qjob, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[queue] キャンセル要求: queue_id=%s job_id=%s",
                    queue_id, qjob.get("job_id"))
        return qjob

    else:
        raise ValueError(f"ステータス '{status}' のジョブはキャンセルできません。"
                         "キャンセルできるのは pending または running のみです。")


def retry_queue_job(queue_id: str) -> Dict[str, Any]:
    """failed または cancelled のジョブを pending に戻す。

    retry_count を 1 増やす。max_retries を超えた場合は警告するが処理は続行する。
    """
    qjob = load_queue_job(queue_id)
    status = qjob.get("status", "")
    if status not in ("failed", "cancelled"):
        raise ValueError(
            f"ステータス '{status}' のジョブはリトライできません。"
            "リトライできるのは failed または cancelled のみです。"
        )

    retry_count = qjob.get("retry_count", 0) + 1
    max_retries = qjob.get("max_retries", 1)

    old_p = _find_queue_file(queue_id)
    now = datetime.now().isoformat(timespec="seconds")
    qjob["status"] = "pending"
    qjob["retry_count"] = retry_count
    qjob["updated_at"] = now
    qjob["started_at"] = None
    qjob["finished_at"] = None
    qjob["current_step"] = None
    qjob["cancel_requested"] = False
    qjob["steps"] = []

    new_p = _write_queue_job(qjob, _queue_root() / "pending")
    if old_p and old_p != new_p and old_p.exists():
        try:
            old_p.unlink()
        except Exception:
            pass

    if retry_count > max_retries:
        logger.warning("[queue] リトライ上限超過: queue_id=%s retry_count=%d max_retries=%d",
                       queue_id, retry_count, max_retries)
    else:
        logger.info("[queue] リトライ: queue_id=%s retry_count=%d",
                    queue_id, retry_count)
    return qjob


def append_step(
    queue_id: str,
    step_name: str,
    success: bool,
    error: str = "",
    started_at: Optional[str] = None,
) -> Dict[str, Any]:
    """ステップの記録を追記し、current_step を更新する。"""
    qjob = load_queue_job(queue_id)
    steps: List[Dict[str, Any]] = list(qjob.get("steps") or [])
    finished_at = datetime.now().isoformat(timespec="seconds")
    steps.append({
        "step":        step_name,
        "success":     success,
        "started_at":  started_at or finished_at,
        "finished_at": finished_at,
        "error":       str(error)[:500] if error else "",
    })
    qjob["steps"] = steps
    qjob["current_step"] = step_name
    qjob["updated_at"] = finished_at

    old_p = _find_queue_file(queue_id)
    if old_p:
        old_p.write_text(json.dumps(qjob, ensure_ascii=False, indent=2), encoding="utf-8")
    return qjob


def is_cancel_requested(queue_id: str) -> bool:
    """ワーカーがステップ間でキャンセル要求を確認するためのヘルパー。"""
    try:
        qjob = load_queue_job(queue_id)
        return bool(qjob.get("cancel_requested"))
    except Exception:
        return False
