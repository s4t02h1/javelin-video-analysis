"""
src/job_manager.py — Javelin Video Analysis ジョブ管理モジュール

各解析ジョブを jobs/<job_id>/ 以下のディレクトリで管理する。

ディレクトリ構造:
    jobs/
        YYYYMMDD_HHMMSS_xxxx/
            input/
                original.mp4
            output/
                analysis_original.mp4
                ...
            report/
            job.json
"""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# job_manager.py はプロジェクトルート（run.py と同階層）に置く
_MODULE_DIR = Path(__file__).resolve().parent   # .../javelin-video-analysis/
_REPO_ROOT = _MODULE_DIR                         # そのままプロジェクトルート
JOBS_DIR = _REPO_ROOT / "jobs"


# ── ジョブID ──────────────────────────────────────────────────────────────────

def generate_job_id() -> str:
    """YYYYMMDD_HHMMSS_xxxx 形式のユニークなジョブIDを生成する。"""
    now = datetime.now()
    suffix = "".join(random.choices("0123456789abcdef", k=4))
    return now.strftime("%Y%m%d_%H%M%S") + f"_{suffix}"


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_job(height_m: Optional[float], mode: str) -> dict:
    """新しいジョブディレクトリを作成し、job.json を初期化して返す。

    Args:
        height_m: 被写体の身長（メートル）。None の場合はピクセル単位。
        mode: 解析モード ('basic' | 'heatmap' | 'vectors' | 'hud' | 'all_variants')

    Returns:
        初期化された job dict。
    """
    job_id = generate_job_id()
    job_dir = JOBS_DIR / job_id

    for sub in ("input", "output", "report"):
        (job_dir / sub).mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat(timespec="seconds")
    job: dict = {
        "job_id": job_id,
        "status": "created",
        "created_at": now,
        "updated_at": now,
        "height_m": height_m,
        "mode": mode,
        "input_file": str(job_dir / "input" / "original.mp4"),
        "output_files": [],
        "error": None,
    }
    _save_job(job)
    return job


def _save_job(job: dict) -> None:
    """job dict を job.json に書き込む（内部用）。"""
    job_dir = JOBS_DIR / job["job_id"]
    with open(job_dir / "job.json", "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)


def update_job(job_id: str, **kwargs) -> dict:
    """既存ジョブのフィールドを更新し、updated_at を自動更新して返す。

    使用例:
        update_job(job_id, status="running")
        update_job(job_id, status="completed", output_files=[...])
        update_job(job_id, status="failed", error="...")
    """
    job = load_job(job_id)
    job.update(kwargs)
    job["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _save_job(job)
    return job


def load_job(job_id: str) -> dict:
    """job.json を読み込んで dict として返す。"""
    job_path = JOBS_DIR / job_id / "job.json"
    with open(job_path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_jobs() -> List[dict]:
    """すべてのジョブを新しい順に返す。job.json がないフォルダは最小限の情報で補完。"""
    if not JOBS_DIR.exists():
        return []
    jobs = []
    for job_dir in JOBS_DIR.iterdir():
        if not job_dir.is_dir():
            continue
        job_json = job_dir / "job.json"
        if job_json.exists():
            try:
                jobs.append(load_job(job_dir.name))
            except Exception:
                pass
        else:
            # job.json がない（CLI 実行など）場合はフォルダ情報から最小限を生成
            stub: dict = {
                "job_id":       job_dir.name,
                "status":       "completed",
                "created_at":   "",
                "updated_at":   "",
                "height_m":     None,
                "mode":         "unknown",
                "input_file":   str(job_dir / "input" / "original.mp4"),
                "output_files": [],
                "error":        None,
            }
            jobs.append(stub)

    # job_id が YYYYMMDD_HHMMSS_xxxx 形式のジョブを新しい順に先頭へ、その他は末尾へ
    import re
    _ts_pat = re.compile(r"^\d{8}_\d{6}_")
    ts_jobs    = [j for j in jobs if _ts_pat.match(j.get("job_id", ""))]
    other_jobs = [j for j in jobs if not _ts_pat.match(j.get("job_id", ""))]
    ts_jobs.sort(key=lambda j: j.get("job_id", ""), reverse=True)
    other_jobs.sort(key=lambda j: j.get("job_id", ""))
    return ts_jobs + other_jobs


def get_job_dir(job_id: str) -> Path:
    """ジョブディレクトリの Path を返す。"""
    return JOBS_DIR / job_id


# ── ユーティリティ ────────────────────────────────────────────────────────────

def collect_output_files(job_id: str) -> List[str]:
    """ジョブの output/ と report/ ディレクトリにあるファイルのパス文字列リストを返す。"""
    job_dir = JOBS_DIR / job_id
    files: List[str] = []
    for sub in ("output", "report"):
        sub_dir = job_dir / sub
        if sub_dir.exists():
            files.extend(str(f) for f in sub_dir.iterdir() if f.is_file())
    return sorted(files)


# ── 顧客情報 (customer_info.json) ─────────────────────────────────────────────

_CUSTOMER_INFO_DEFAULTS: dict = {
    "customer_name":   "",
    "instagram_id":    "",
    "event":           "javelin",
    "dominant_hand":   "unknown",
    "height_m":        None,
    "camera_angle":    "unknown",
    "request_note":    "",
    "coach_comment":   "",
    "delivery_status": "not_started",
    "paid_status":     "unknown",
    "created_at":      "",
    "updated_at":      "",
}


def _customer_info_path(job_id: str) -> Path:
    """customer_info.json のパスを返す。"""
    return JOBS_DIR / job_id / "customer_info.json"


def get_customer_info(job_id: str) -> dict:
    """customer_info.json を読み込んで返す。

    ファイルが存在しない場合はデフォルト値を返す。
    フィールドが追加された場合はデフォルト値でマージして返す（前方互換）。
    """
    path = _customer_info_path(job_id)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data: dict = json.load(f)
        # 新フィールドが追加された場合のマイグレーション（既存値を優先）
        return {**_CUSTOMER_INFO_DEFAULTS, **data}
    # ファイルがない場合はデフォルト（created_at は現在時刻）
    now = datetime.now().isoformat(timespec="seconds")
    return {**_CUSTOMER_INFO_DEFAULTS, "created_at": now, "updated_at": now}


def update_customer_info(job_id: str, **kwargs) -> dict:
    """customer_info.json の指定フィールドを更新して保存し、更新後の dict を返す。

    使用例:
        update_customer_info(job_id, customer_name="山田 太郎", paid_status="data_sheet")
        update_customer_info(job_id, delivery_status="preview_delivered")
    """
    info = get_customer_info(job_id)
    # created_at は初回設定後は上書きしない
    existing_created = info.get("created_at") or ""
    info.update(kwargs)
    if existing_created:
        info["created_at"] = existing_created
    elif not info.get("created_at"):
        info["created_at"] = datetime.now().isoformat(timespec="seconds")
    info["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path = _customer_info_path(job_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return info
