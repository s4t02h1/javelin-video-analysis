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


# ── ステータス定数 ────────────────────────────────────────────────────────────

# job.json の status フィールドに使用するステータス値
JOB_STATUSES = [
    "created",          # 受付済み
    "uploaded",         # 動画アップロード済み
    "running",          # 解析中
    "completed",        # 解析完了
    "reviewing",        # 内容確認中
    "ready_to_deliver", # 納品準備完了
    "delivered",        # 納品済み
    "failed",           # エラー
    "archived",         # 保管済み
]

JOB_STATUS_LABELS = {
    "created":          "受付済み",
    "uploaded":         "動画アップロード済み",
    "running":          "解析中",
    "completed":        "解析完了",
    "reviewing":        "内容確認中",
    "ready_to_deliver": "納品準備完了",
    "delivered":        "納品済み",
    "failed":           "エラー",
    "archived":         "保管済み",
}

# ── 顧客情報 (customer_info.json) ─────────────────────────────────────────────

_CUSTOMER_INFO_DEFAULTS: dict = {
    # ── 基本情報
    "customer_name":              "",
    "nickname":                   "",           # Phase2追加: ニックネーム
    "instagram_id":               "",
    "event":                      "javelin",
    # ── 身体情報
    "dominant_arm":               "unknown",    # right / left / unknown  (正式フィールド)
    "height_m":                   None,
    "athletic_career":            "",           # Phase2追加: 競技歴
    # ── 撮影情報
    "filming_angle":              "unknown",    # side / back / front / diagonal / unknown  (正式フィールド)
    # ── 許諾・プラン
    "permission_for_social_post": "unknown",    # unknown / allowed / anonymous / denied
    "anonymization_note":         "",           # Phase2追加: 匿名化メモ
    "plan":                       "free_preview",  # free_preview / data_sheet / full_report
    "payment_status":             "unpaid",     # unpaid / paid / free
    # ── 日程
    "received_at":                "",           # Phase2追加: 受付日
    "delivery_scheduled_note":    "",           # Phase2追加: 納品予定メモ
    "delivered_at":               "",           # Phase2追加: 納品済み日時
    # ── メモ
    "notes":                      "",
    "admin_memo":                 "",           # Phase2追加: 管理者メモ
    "request_note":               "",           # 後方互換
    "coach_comment":              "",
    # ── 管理
    "delivery_status":            "not_started",
    # ── 後方互換フィールド（旧名称）
    "dominant_hand":              "unknown",
    "camera_angle":               "unknown",
    "paid_status":                "unknown",
    # ── タイムスタンプ
    "created_at":                 "",
    "updated_at":                 "",
}


def _customer_info_path(job_id: str) -> Path:
    """customer_info.json のパスを返す。"""
    return JOBS_DIR / job_id / "customer_info.json"


def get_customer_info(job_id: str) -> dict:
    """customer_info.json を読み込んで返す。

    ファイルが存在しない場合はデフォルト値を返す。
    フィールドが追加された場合はデフォルト値でマージして返す（前方互換）。
    旧フィールド名（dominant_hand / camera_angle）は新フィールド名へ自動移行する。
    JSONが壊れている場合は警告ログを出しデフォルト値を返す（管理画面を落とさない）。
    """
    import logging as _logging
    path = _customer_info_path(job_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data: dict = json.load(f)
        except (json.JSONDecodeError, OSError) as _e:
            _logging.warning(
                "[job_manager] customer_info.json の読み込みに失敗しました (%s): %s", job_id, _e
            )
            now = datetime.now().isoformat(timespec="seconds")
            return {**_CUSTOMER_INFO_DEFAULTS, "created_at": now, "updated_at": now}
        # 新フィールドが追加された場合のマイグレーション（既存値を優先）
        merged = {**_CUSTOMER_INFO_DEFAULTS, **data}
        # 旧フィールド → 新フィールドの自動移行（新フィールドが未設定の場合のみ）
        if (not merged.get("dominant_arm") or merged["dominant_arm"] == "unknown") \
                and data.get("dominant_hand") and data["dominant_hand"] != "unknown":
            merged["dominant_arm"] = data["dominant_hand"]
        if (not merged.get("filming_angle") or merged["filming_angle"] == "unknown") \
                and data.get("camera_angle") and data["camera_angle"] != "unknown":
            merged["filming_angle"] = data["camera_angle"]
        return merged
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return info


# ── 受付情報 (intake_info.json) ───────────────────────────────────────────────

_INTAKE_INFO_DEFAULTS: dict = {
    # ── 基本情報
    "name_or_nickname":     "",   # 名前またはニックネーム
    "contact":              "",   # 連絡先
    "age_group":            "",   # 年齢区分: 中学生 / 高校生 / 大学生 / 社会人 / マスターズ / その他
    "gender":               "",   # 性別（任意）
    "athletic_career":      "",   # 競技歴
    "personal_best":        "",   # 自己ベスト
    "dominant_arm":         "unknown",  # right / left / unknown
    "height_m":             None,
    "affiliation_type":     "",   # 中学 / 高校 / 大学 / 社会人 / マスターズ / その他
    # ── 動画情報
    "filming_date":         "",   # 撮影日
    "filming_context":      "",   # 大会 / 練習 / その他
    "filming_angle":        "unknown",  # side / diagonal_back / front / other
    "video_type":           "",   # 全助走 / 投げのみ / 部分練習 / その他
    "is_slow_motion":       False,
    "video_count":          1,
    "video_priority_note":  "",   # 解析したい優先順位メモ
    "video_memo":           "",
    # ── 相談内容
    "focus_main":           "",   # 一番見てほしい点（自由記述）
    "focus_approach":       False,  # 助走
    "focus_crossstep":      False,  # クロスステップ
    "focus_block":          False,  # ブロック
    "focus_release":        False,  # リリース
    "focus_upper_body":     False,  # 上半身
    "focus_lower_body":     False,  # 下半身
    "focus_other":          "",   # その他自由記述
    # ── 希望プラン
    "desired_plan":         "free_preview",  # free_preview / light / data_sheet / full_report / comparison / undecided
    # ── 同意事項（False = 未同意 が安全側デフォルト）
    "consent_analysis_reference":  False,  # 解析は参考資料であることに同意
    "consent_not_medical":         False,  # 医療診断・怪我の診断ではないことに同意
    "consent_not_coaching":        False,  # 専門的な競技指導の代替ではないことに同意
    "consent_accuracy_varies":     False,  # 動画の画質・角度により精度が変わることに同意
    "consent_delivery_time":       False,  # 納品まで時間がかかる場合があることに同意
    "consent_sns_separate":        False,  # SNS掲載は別途許可制であることに同意
    # ── タイムスタンプ
    "created_at":           "",
    "updated_at":           "",
}


def _intake_info_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / "intake_info.json"


def get_intake_info(job_id: str) -> dict:
    """intake_info.json を読み込んで返す。

    ファイルが存在しない・壊れている場合はデフォルト値を返す（管理画面を落とさない）。
    既存ジョブに未追加フィールドがある場合はデフォルト値でマージ（前方互換）。
    """
    import logging as _log
    path = _intake_info_path(job_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data: dict = json.load(f)
        except (json.JSONDecodeError, OSError) as _e:
            _log.warning("[job_manager] intake_info.json 読み込み失敗 (%s): %s", job_id, _e)
            now = datetime.now().isoformat(timespec="seconds")
            return {**_INTAKE_INFO_DEFAULTS, "created_at": now, "updated_at": now}
        return {**_INTAKE_INFO_DEFAULTS, **data}
    now = datetime.now().isoformat(timespec="seconds")
    return {**_INTAKE_INFO_DEFAULTS, "created_at": now, "updated_at": now}


def update_intake_info(job_id: str, **kwargs) -> dict:
    """intake_info.json の指定フィールドを更新して保存する。"""
    info = get_intake_info(job_id)
    existing_created = info.get("created_at") or ""
    info.update(kwargs)
    if existing_created:
        info["created_at"] = existing_created
    elif not info.get("created_at"):
        info["created_at"] = datetime.now().isoformat(timespec="seconds")
    info["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path = _intake_info_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return info


# ── 納品前チェックリスト (delivery_checklist.json) ────────────────────────────

_DELIVERY_CHECKLIST_DEFAULTS: dict = {
    "chk_intake_confirmed":       False,  # 受付情報を確認した
    "chk_dominant_arm":           False,  # 利き腕を確認した
    "chk_height":                 False,  # 身長を確認した
    "chk_filming_angle":          False,  # 動画の撮影角度を確認した
    "chk_pdf_generated":          False,  # PDFが生成されている
    "chk_analysis_video":         False,  # 解析動画が生成されている
    "chk_zip_generated":          False,  # ZIPが生成されている
    "chk_readme_in_zip":          False,  # 00_最初に読んでください.pdf が含まれている
    "chk_instruction_pdf":        False,  # 解析動画の見方PDFが含まれている
    "chk_disclaimer_in_zip":      False,  # 免責事項が含まれている
    "chk_plan_matches_deliverables": False,  # 希望プランと納品物が一致している
    "chk_sns_permission":         False,  # SNS掲載許可ステータスを確認した
    "chk_delivery_message_ready": False,  # 納品メッセージを生成した
    "updated_at":                 "",
}


def _delivery_checklist_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / "delivery_checklist.json"


def get_delivery_checklist(job_id: str) -> dict:
    """delivery_checklist.json を読み込んで返す。存在しない場合はデフォルトを返す。"""
    import logging as _log
    path = _delivery_checklist_path(job_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data: dict = json.load(f)
            return {**_DELIVERY_CHECKLIST_DEFAULTS, **data}
        except (json.JSONDecodeError, OSError) as _e:
            _log.warning("[job_manager] delivery_checklist.json 読み込み失敗 (%s): %s", job_id, _e)
    return dict(_DELIVERY_CHECKLIST_DEFAULTS)


def update_delivery_checklist(job_id: str, **kwargs) -> dict:
    """delivery_checklist.json を更新して保存する。"""
    chk = get_delivery_checklist(job_id)
    chk.update(kwargs)
    chk["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path = _delivery_checklist_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(chk, f, ensure_ascii=False, indent=2)
    return chk

