"""
src/intake_manager.py — Javelin Video Analysis: 受付 (intake) データ管理

受付ジョブ (intake) は解析ジョブ (job) とは別に管理される。

ディレクトリ構造:
    intakes/
        intake_YYYYMMDD_HHMMSS_xxxx/
            intake.json

intake と job の関係:
    intake.json: converted_job_id  → 変換先 job_id
    job.json:    source_intake_id  → 元 intake_id

ステータス遷移:
    received → needs_review → ready_for_job → converted
                           ↘ rejected
    any → archived
"""

from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.intake")

# ── ディレクトリ ──────────────────────────────────────────────────────────────

_MODULE_DIR = Path(__file__).resolve().parent          # src/
_REPO_ROOT  = _MODULE_DIR.parent                       # project root
INTAKES_DIR = _REPO_ROOT / "intakes"

# ── 定数 ──────────────────────────────────────────────────────────────────────

INTAKE_STATUSES: List[str] = [
    "received",       # 受付済み
    "needs_review",   # 確認が必要
    "ready_for_job",  # ジョブ化可能
    "converted",      # ジョブ化済み
    "rejected",       # 対応不可
    "archived",       # 保管済み
]

INTAKE_STATUS_LABELS: Dict[str, str] = {
    "received":      "受付済み",
    "needs_review":  "確認が必要",
    "ready_for_job": "ジョブ化可能",
    "converted":     "ジョブ化済み",
    "rejected":      "対応不可",
    "archived":      "保管済み",
}

INTAKE_SOURCES: List[str] = [
    "manual",
    "google_form",
    "line",
    "api",
    "csv_import",
    "unknown",
]

# ── デフォルト値 ──────────────────────────────────────────────────────────────

_INTAKE_DEFAULTS: Dict[str, Any] = {
    # ── 識別・管理
    "intake_id":                          "",
    "created_at":                         "",
    "updated_at":                         "",
    "status":                             "received",
    "source":                             "unknown",
    # ── 基本情報（個人情報 → ログに出力しない）
    "name_or_nickname":                   "",
    "contact":                            "",
    "line_user_id":                       "",
    "email":                              "",
    "instagram_account":                  "",
    # ── 競技情報
    "age_group":                          "",
    "gender_optional":                    "",
    "event_type":                         "javelin",
    "dominant_arm":                       "unknown",
    "height_cm":                          None,
    "experience_years":                   None,
    "personal_best":                      "",
    "affiliation_type":                   "",
    # ── 動画情報
    "video_count":                        1,
    "video_submission_method":            "",
    "shooting_angle":                     "unknown",
    "video_type":                         "",
    "is_slow_motion":                     False,
    # ── 相談内容
    "main_request":                       "",
    "focus_points":                       [],
    # ── 希望プラン
    "desired_plan":                       "free_preview",
    # ── 同意事項（False = 未同意 が安全側デフォルト）
    "consent_reference_analysis":         False,
    "consent_not_medical":                False,
    "consent_not_coaching_replacement":   False,
    "consent_accuracy_depends_on_video":  False,
    "consent_delivery_may_take_time":     False,
    "consent_sns_requires_permission":    False,
    # ── SNS掲載許可
    "sns_permission_status":              "unknown",  # unknown / allowed / anonymous / denied
    # ── 管理者メモ・生データ
    "admin_note":                         "",
    "raw_payload":                        {},
    # ── ジョブ連携
    "converted_job_id":                   None,
}

# ── ID 生成 ──────────────────────────────────────────────────────────────────

def generate_intake_id() -> str:
    """intake_YYYYMMDD_HHMMSS_xxxx 形式のユニーク ID を生成する。"""
    now    = datetime.now()
    suffix = "".join(random.choices("0123456789abcdef", k=4))
    return now.strftime("intake_%Y%m%d_%H%M%S") + f"_{suffix}"

# ── ファイルパス ──────────────────────────────────────────────────────────────

def _intake_path(intake_id: str) -> Path:
    return INTAKES_DIR / intake_id / "intake.json"

def get_intake_dir(intake_id: str) -> Path:
    """受付ディレクトリの Path を返す。"""
    return INTAKES_DIR / intake_id

# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_intake(
    source: str = "unknown",
    raw_payload: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """新しい intake を作成して保存し、intake dict を返す。

    Parameters
    ----------
    source      : INTAKE_SOURCES のいずれか
    raw_payload : フォームから受け取った元データ（丸ごと保存）
    **kwargs    : intake フィールドの上書き値（不足項目があっても落ちない）

    Returns
    -------
    intake dict
    """
    intake_id = generate_intake_id()
    now       = datetime.now().isoformat(timespec="seconds")

    intake: Dict[str, Any] = {
        **_INTAKE_DEFAULTS,
        "intake_id":    intake_id,
        "created_at":   now,
        "updated_at":   now,
        "source":       source if source in INTAKE_SOURCES else "unknown",
        "raw_payload":  raw_payload or {},
    }
    # 不明なフィールドも raw_payload 以外は安全に上書き
    for k, v in kwargs.items():
        intake[k] = v

    path = _intake_path(intake_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(intake, f, ensure_ascii=False, indent=2)

    logger.info(
        "[intake] 作成 intake_id=%s source=%s",
        intake_id, intake["source"],
    )
    return intake


def load_intake(intake_id: str) -> Dict[str, Any]:
    """intake.json を読み込んで dict を返す。"""
    path = _intake_path(intake_id)
    if not path.exists():
        raise FileNotFoundError(f"intake が見つかりません: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {**_INTAKE_DEFAULTS, **data}


def _save_intake(intake: Dict[str, Any]) -> None:
    """intake dict を intake.json に書き込む（内部用）。"""
    path = _intake_path(intake["intake_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(intake, f, ensure_ascii=False, indent=2)


def update_intake(intake_id: str, **kwargs: Any) -> Dict[str, Any]:
    """既存 intake を更新して保存し、更新後の dict を返す。

    不明なフィールドを渡しても落ちない（後方互換）。
    updated_at は自動更新される。
    """
    intake = load_intake(intake_id)
    old_status = intake.get("status", "")
    for k, v in kwargs.items():
        intake[k] = v
    intake["updated_at"] = datetime.now().isoformat(timespec="seconds")

    new_status = intake.get("status", "")
    if old_status != new_status:
        logger.info(
            "[intake] ステータス変更 intake_id=%s %s → %s",
            intake_id, old_status, new_status,
        )
    else:
        logger.info("[intake] 更新 intake_id=%s", intake_id)

    _save_intake(intake)
    return intake


def list_intakes(
    status: Optional[str] = None,
    source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """全 intake を新しい順に返す。

    Parameters
    ----------
    status : フィルタするステータス（None = 全件）
    source : フィルタするソース（None = 全件）
    """
    if not INTAKES_DIR.exists():
        return []
    result: List[Dict[str, Any]] = []
    for idir in INTAKES_DIR.iterdir():
        if not idir.is_dir():
            continue
        ipath = idir / "intake.json"
        if not ipath.exists():
            continue
        try:
            with open(ipath, "r", encoding="utf-8") as f:
                data = json.load(f)
            intake = {**_INTAKE_DEFAULTS, **data}
        except Exception:
            continue
        if status is not None and intake.get("status") != status:
            continue
        if source is not None and intake.get("source") != source:
            continue
        result.append(intake)
    result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return result


# ── ステータス遷移ヘルパー ─────────────────────────────────────────────────────

def set_intake_status(intake_id: str, new_status: str) -> Dict[str, Any]:
    """ステータスを変更して保存する。"""
    if new_status not in INTAKE_STATUSES:
        raise ValueError(f"不正なステータス: {new_status}")
    return update_intake(intake_id, status=new_status)


def archive_intake(intake_id: str) -> Dict[str, Any]:
    """intake を archived に変更する。"""
    return set_intake_status(intake_id, "archived")


def reject_intake(intake_id: str, note: str = "") -> Dict[str, Any]:
    """intake を rejected に変更する。"""
    kwargs: Dict[str, Any] = {"status": "rejected"}
    if note:
        current = load_intake(intake_id)
        existing = current.get("admin_note", "")
        kwargs["admin_note"] = (existing + "\n" + note).strip()
    return update_intake(intake_id, **kwargs)


# ── intake → job 変換 ─────────────────────────────────────────────────────────

def check_all_consents(intake: Dict[str, Any]) -> bool:
    """同意事項が全て True かどうかを返す。"""
    consent_keys = [
        "consent_reference_analysis",
        "consent_not_medical",
        "consent_not_coaching_replacement",
        "consent_accuracy_depends_on_video",
        "consent_delivery_may_take_time",
        "consent_sns_requires_permission",
    ]
    return all(intake.get(k, False) for k in consent_keys)


def missing_consents(intake: Dict[str, Any]) -> List[str]:
    """未同意の同意事項キーリストを返す。"""
    consent_keys = [
        "consent_reference_analysis",
        "consent_not_medical",
        "consent_not_coaching_replacement",
        "consent_accuracy_depends_on_video",
        "consent_delivery_may_take_time",
        "consent_sns_requires_permission",
    ]
    return [k for k in consent_keys if not intake.get(k, False)]


CONSENT_LABELS: Dict[str, str] = {
    "consent_reference_analysis":        "解析は参考資料であることへの同意",
    "consent_not_medical":               "医療診断・怪我の診断でないことへの同意",
    "consent_not_coaching_replacement":  "専門的競技指導の代替でないことへの同意",
    "consent_accuracy_depends_on_video": "動画品質により精度が変わることへの同意",
    "consent_delivery_may_take_time":    "納品まで時間がかかる場合への同意",
    "consent_sns_requires_permission":   "SNS掲載は別途許可制であることへの同意",
}


def convert_intake_to_job(
    intake_id: str,
    job_manager_module: Any,
    force: bool = False,
) -> Dict[str, Any]:
    """intake から新規 job を作成して相互IDを保存する。

    Parameters
    ----------
    intake_id       : 変換する intake の ID
    job_manager_module : job_manager モジュール（循環インポート回避のため注入）
    force           : True の場合、converted_job_id が既存でも再変換を許可

    Returns
    -------
    {"intake": updated_intake, "job": new_job}

    Raises
    ------
    ValueError
        すでに converted_job_id が設定されており force=False の場合
    """
    intake = load_intake(intake_id)

    if intake.get("converted_job_id") and not force:
        raise ValueError(
            f"この intake はすでにジョブ化済みです: converted_job_id={intake['converted_job_id']}"
        )

    # job を作成
    height_m: Optional[float] = None
    if intake.get("height_cm") is not None:
        try:
            height_m = float(intake["height_cm"]) / 100.0
        except (TypeError, ValueError):
            pass

    new_job_result = job_manager_module.create_job(height_m=height_m, mode="all_variants")
    # create_job は job_id 文字列を返す場合と dict を返す場合がある
    if isinstance(new_job_result, str):
        job_id = new_job_result
    else:
        job_id = new_job_result["job_id"]

    # job.json に受付情報をコピー
    job_manager_module.update_job(
        job_id,
        source_intake_id=intake_id,
        customer_name_hint=intake.get("name_or_nickname", ""),
    )

    # customer_info.json も初期セット
    job_manager_module.update_customer_info(
        job_id,
        customer_name=intake.get("name_or_nickname", ""),
        dominant_arm=intake.get("dominant_arm", "unknown"),
        plan=intake.get("desired_plan", "free_preview"),
        height_m=height_m,
        notes=intake.get("main_request", ""),
        admin_memo=intake.get("admin_note", ""),
    )

    # intake を更新
    updated_intake = update_intake(
        intake_id,
        status="converted",
        converted_job_id=job_id,
    )

    logger.info(
        "[intake] ジョブ変換 intake_id=%s → job_id=%s",
        intake_id, job_id,
    )
    return {"intake": updated_intake, "job": {"job_id": job_id}}


# ── ログユーティリティ ────────────────────────────────────────────────────────

def append_intake_audit_log(
    log_path: Path,
    intake_id: str,
    source: str,
    action: str,
    success: bool,
    error: str = "",
) -> None:
    """監査ログを追記する。個人情報は含まない。

    Parameters
    ----------
    log_path  : ログファイルパス（親ディレクトリは自動作成）
    intake_id : 対象 intake_id
    source    : 受付ソース
    action    : 処理名 (create / update / status_change / convert_to_job / ...)
    success   : 成功/失敗
    error     : エラー内容（失敗時）
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    record = {
        "timestamp":  now,
        "intake_id":  intake_id,
        "source":     source,
        "action":     action,
        "success":    success,
        "error":      error,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
