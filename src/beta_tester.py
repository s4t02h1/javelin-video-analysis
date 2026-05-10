"""
src/beta_tester.py — Javelin Video Analysis: βテスター管理 (Phase 15)

βテスター（β版利用者）のデータを管理します。

ディレクトリ構造:
    data/beta_testers/
        {tester_id}/
            beta_tester.json

ステータス遷移:
    tester_status:
        candidate → invited → accepted → active → completed
                ↘ declined
        any → archived

    consent_status:
        not_sent → sent → agreed
                       ↘ declined
        any → needs_confirmation

    feedback_status:
        not_requested → requested → submitted → reviewed
                                 ↘ missing
"""

from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.beta_tester")

# ── ディレクトリ ──────────────────────────────────────────────────────────────

_MODULE_DIR = Path(__file__).resolve().parent       # src/
_REPO_ROOT  = _MODULE_DIR.parent                    # project root
BETA_TESTERS_DIR = _REPO_ROOT / "data" / "beta_testers"

# ── 定数 ──────────────────────────────────────────────────────────────────────

TESTER_STATUSES: List[str] = [
    "candidate",   # 候補者
    "invited",     # 招待済み
    "accepted",    # 参加承認済み
    "active",      # 解析中
    "completed",   # 完了
    "declined",    # 辞退
    "archived",    # アーカイブ
]

TESTER_STATUS_LABELS: Dict[str, str] = {
    "candidate":  "候補者",
    "invited":    "招待済み",
    "accepted":   "参加承認",
    "active":     "解析中",
    "completed":  "完了",
    "declined":   "辞退",
    "archived":   "アーカイブ",
}

CONSENT_STATUSES: List[str] = [
    "not_sent",           # 未送付
    "sent",               # 送付済み
    "agreed",             # 同意済み
    "declined",           # 同意不可
    "needs_confirmation", # 確認が必要
]

CONSENT_STATUS_LABELS: Dict[str, str] = {
    "not_sent":           "未送付",
    "sent":               "送付済み",
    "agreed":             "✅ 同意済み",
    "declined":           "🚫 同意不可",
    "needs_confirmation": "⚠️ 確認が必要",
}

FEEDBACK_STATUSES: List[str] = [
    "not_requested",  # 未依頼
    "requested",      # 依頼済み
    "submitted",      # 提出済み
    "reviewed",       # 確認済み
    "missing",        # 未提出（期限超過）
]

FEEDBACK_STATUS_LABELS: Dict[str, str] = {
    "not_requested": "未依頼",
    "requested":     "依頼済み",
    "submitted":     "✅ 提出済み",
    "reviewed":      "確認済み",
    "missing":       "⚠️ 未提出",
}

BETA_PLANS: List[str] = [
    "beta_preview",
    "beta_full_report",
    "beta_comparison",
]

BETA_PLAN_LABELS: Dict[str, str] = {
    "beta_preview":     "β版プレビュー",
    "beta_full_report": "β版フル解析",
    "beta_comparison":  "β版2動画比較",
}

# ── デフォルト値 ──────────────────────────────────────────────────────────────

_TESTER_DEFAULTS: Dict[str, Any] = {
    # 識別・管理
    "beta_tester_id":       "",
    "created_at":           "",
    "updated_at":           "",
    "tester_status":        "candidate",
    "is_beta":              True,
    # 基本情報（個人情報 → ログに出力しない）
    "name_or_nickname":     "",
    "contact":              "",          # LINE / DM / メール等
    "instagram_account":    "",
    "line_user_id":         "",
    "email":                "",
    # 競技情報
    "athlete_category":     "",          # 高校生 / 大学生 / マスターズ / 指導者 / 一般
    "event_type":           "javelin",
    "dominant_arm":         "unknown",   # right / left / unknown
    "experience_years":     None,
    "personal_best":        "",
    # プラン・ステータス
    "assigned_plan":        "beta_full_report",
    "invitation_status":    "not_invited",
    "consent_status":       "not_sent",
    "feedback_status":      "not_requested",
    # 関連ID
    "related_intake_ids":   [],
    "related_job_ids":      [],
    "related_order_ids":    [],
    # メモ
    "admin_note":           "",
    # SNS関連（掲載許可と教師データ利用許可は分けて管理）
    "sns_permission_status":           "unknown",   # unknown / allowed / anonymous / denied
    "training_data_consent":           False,       # 教師データへの利用同意
    "sns_and_training_data_same":      False,       # 掲載許可 = 教師データ利用許可ではない
}

# ── ID 生成 ──────────────────────────────────────────────────────────────────

def generate_tester_id() -> str:
    """βテスターIDを生成する: bt_YYYYMMDD_HHMMSS_xxxx"""
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = "".join(random.choices("abcdef0123456789", k=4))
    return f"bt_{ts}_{rand}"


# ── パス ─────────────────────────────────────────────────────────────────────

def get_tester_dir(tester_id: str) -> Path:
    """テスターデータディレクトリを返す（存在保証なし）。"""
    return BETA_TESTERS_DIR / tester_id


def get_tester_json_path(tester_id: str) -> Path:
    """beta_tester.json のパスを返す。"""
    return get_tester_dir(tester_id) / "beta_tester.json"


# ── CRUD ─────────────────────────────────────────────────────────────────────

def create_beta_tester(
    name_or_nickname: str = "",
    contact: str = "",
    assigned_plan: str = "beta_full_report",
    admin_note: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """新しいβテスターを作成して JSON に保存する。

    Args:
        name_or_nickname : 氏名またはニックネーム
        contact          : 連絡先（LINE / DM / メール等）
        assigned_plan    : 割り当てβプラン
        admin_note       : 管理者メモ
        **kwargs         : その他フィールド（_TESTER_DEFAULTS のキーと一致するもの）

    Returns:
        dict: 作成されたβテスターデータ
    """
    tester_id = generate_tester_id()
    now = datetime.now().isoformat()

    tester: Dict[str, Any] = {**_TESTER_DEFAULTS}
    tester.update(kwargs)
    tester.update({
        "beta_tester_id":    tester_id,
        "created_at":        now,
        "updated_at":        now,
        "name_or_nickname":  name_or_nickname,
        "contact":           contact,
        "assigned_plan":     assigned_plan,
        "admin_note":        admin_note,
    })

    tester_dir = get_tester_dir(tester_id)
    tester_dir.mkdir(parents=True, exist_ok=True)
    _save(tester_id, tester)

    logger.info("βテスターを作成しました: %s", tester_id)
    return tester


def load_beta_tester(tester_id: str) -> Dict[str, Any]:
    """βテスター JSON を読み込む。存在しない場合は {} を返す。"""
    p = get_tester_json_path(tester_id)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return {**_TESTER_DEFAULTS, **raw}
    except Exception as e:
        logger.warning("βテスター JSON 読み込み失敗 %s: %s", tester_id, e)
        return {}


def update_beta_tester(tester_id: str, **kwargs: Any) -> Dict[str, Any]:
    """βテスターデータを更新して JSON に保存する。

    Returns:
        dict: 更新後のβテスターデータ
    """
    tester = load_beta_tester(tester_id)
    if not tester:
        raise FileNotFoundError(f"βテスターが見つかりません: {tester_id}")
    tester.update(kwargs)
    tester["updated_at"] = datetime.now().isoformat()
    _save(tester_id, tester)
    return tester


def list_beta_testers(
    status_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """βテスター一覧を返す（作成日時の降順）。

    Args:
        status_filter: tester_status でフィルタリング（None で全件）
    """
    if not BETA_TESTERS_DIR.exists():
        return []

    results = []
    for d in sorted(BETA_TESTERS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        p = d / "beta_tester.json"
        if not p.exists():
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            tester = {**_TESTER_DEFAULTS, **raw}
        except Exception:
            continue

        if status_filter and tester.get("tester_status") != status_filter:
            continue
        results.append(tester)

    return results


def archive_tester(tester_id: str) -> Dict[str, Any]:
    """βテスターをアーカイブ状態にする。"""
    return update_beta_tester(tester_id, tester_status="archived")


def tester_from_intake(intake_id: str) -> Dict[str, Any]:
    """既存 intake データからβテスターを作成する。

    Returns:
        dict: 作成されたβテスターデータ
    """
    try:
        from src.intake_manager import load_intake
        intake = load_intake(intake_id)
    except Exception as e:
        raise RuntimeError(f"intake 読み込み失敗: {e}") from e

    if not intake:
        raise FileNotFoundError(f"intake が見つかりません: {intake_id}")

    tester = create_beta_tester(
        name_or_nickname  = intake.get("name_or_nickname", ""),
        contact           = intake.get("contact", ""),
        admin_note        = f"intake から作成: {intake_id}",
        instagram_account = intake.get("instagram_account", ""),
        line_user_id      = intake.get("line_user_id", ""),
        email             = intake.get("email", ""),
        athlete_category  = intake.get("age_group", ""),
        event_type        = intake.get("event_type", "javelin"),
        dominant_arm      = intake.get("dominant_arm", "unknown"),
        experience_years  = intake.get("experience_years"),
        personal_best     = intake.get("personal_best", ""),
        related_intake_ids = [intake_id],
        sns_permission_status = intake.get("sns_permission_status", "unknown"),
    )

    # intake に beta_tester_id を記録
    try:
        from src.intake_manager import update_intake
        update_intake(intake_id, beta_tester_id=tester["beta_tester_id"])
    except Exception as e:
        logger.warning("intake への beta_tester_id 書き込み失敗: %s", e)

    return tester


# ── 内部ヘルパー ─────────────────────────────────────────────────────────────

def _save(tester_id: str, data: Dict[str, Any]) -> None:
    """βテスターデータを JSON に保存する。"""
    p = get_tester_json_path(tester_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
