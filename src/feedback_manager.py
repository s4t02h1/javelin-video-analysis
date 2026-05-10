"""
src/feedback_manager.py — Javelin Video Analysis: βフィードバック管理 (Phase 15)

β版利用者からのフィードバックを管理します。

ディレクトリ構造:
    data/feedback/
        {feedback_id}/
            feedback.json

⚠️ セキュリティ方針
    - フィードバック API は dashboard_token を受け取る
    - job_id は API レスポンスに含めない（内部解決のみ）
    - 個人情報（名前・連絡先）をログに出力しない

ステータス遷移:
    new → triaged → in_progress → resolved
                              ↘ wont_fix
    any → archived
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.feedback")

# ── ディレクトリ ──────────────────────────────────────────────────────────────

_MODULE_DIR = Path(__file__).resolve().parent       # src/
_REPO_ROOT  = _MODULE_DIR.parent                    # project root
FEEDBACK_DIR = _REPO_ROOT / "data" / "feedback"

# ── 定数 ──────────────────────────────────────────────────────────────────────

FEEDBACK_TYPES: List[str] = [
    "bug",
    "confusing_ui",
    "report_quality",
    "analysis_quality",
    "delivery_issue",
    "payment_issue",
    "positive",
    "other",
]

FEEDBACK_TYPE_LABELS: Dict[str, str] = {
    "bug":              "🐛 バグ・エラー",
    "confusing_ui":     "😕 UIがわかりにくい",
    "report_quality":   "📄 レポート品質",
    "analysis_quality": "📊 解析精度・品質",
    "delivery_issue":   "📦 納品に関する問題",
    "payment_issue":    "💰 支払いに関する問題",
    "positive":         "👍 良かった点",
    "other":            "その他",
}

SEVERITY_LEVELS: List[str] = [
    "low",
    "medium",
    "high",
    "critical",
]

SEVERITY_LABELS: Dict[str, str] = {
    "low":      "🟢 低",
    "medium":   "🟡 中",
    "high":     "🔴 高",
    "critical": "🚨 緊急",
}

FEEDBACK_STATUSES: List[str] = [
    "new",
    "triaged",
    "in_progress",
    "resolved",
    "wont_fix",
    "archived",
]

FEEDBACK_STATUS_LABELS: Dict[str, str] = {
    "new":         "🆕 新規",
    "triaged":     "🔍 確認済み",
    "in_progress": "⏳ 対応中",
    "resolved":    "✅ 解決済み",
    "wont_fix":    "⏭️ 対応しない",
    "archived":    "📂 アーカイブ",
}

# ── デフォルト値 ──────────────────────────────────────────────────────────────

_FEEDBACK_DEFAULTS: Dict[str, Any] = {
    # 識別・管理
    "feedback_id":       "",
    "created_at":        "",
    "updated_at":        "",
    "status":            "new",
    # 送信者
    "beta_tester_id":    "",    # βテスターID（任意）
    # 内部解決（APIレスポンスには含めない）
    "job_id":            "",    # dashboard_token から解決
    "dashboard_token":   "",    # 入力で受け取る
    # フィードバック内容
    "feedback_type":     "other",
    "severity":          "low",
    "title":             "",
    "body":              "",
    # 端末情報
    "device":            "",    # スマホ / PC / タブレット 等
    "os":                "",    # iOS / Android / Windows 等
    "browser":           "",    # Chrome / Safari 等
    "screenshot_note":   "",    # スクリーンショット説明
    # 管理者
    "admin_note":        "",
    "resolved_at":       None,
    # 改善ログへのリンク
    "improvement_id":    "",
}

# ── ID 生成 ──────────────────────────────────────────────────────────────────

def generate_feedback_id() -> str:
    """フィードバックIDを生成する: fb_YYYYMMDD_HHMMSS_xxxx"""
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = "".join(random.choices("abcdef0123456789", k=4))
    return f"fb_{ts}_{rand}"


# ── パス ─────────────────────────────────────────────────────────────────────

def get_feedback_dir(feedback_id: str) -> Path:
    """フィードバックデータディレクトリを返す。"""
    return FEEDBACK_DIR / feedback_id


def get_feedback_json_path(feedback_id: str) -> Path:
    """feedback.json のパスを返す。"""
    return get_feedback_dir(feedback_id) / "feedback.json"


# ── CRUD ─────────────────────────────────────────────────────────────────────

def create_feedback(
    feedback_type: str = "other",
    severity: str = "low",
    title: str = "",
    body: str = "",
    dashboard_token: str = "",
    beta_tester_id: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """フィードバックを作成して JSON に保存する。

    dashboard_token から job_id を内部解決する。
    job_id は API レスポンスに含めない（セキュリティ上の方針）。

    Args:
        feedback_type   : フィードバック種別
        severity        : 重要度
        title           : タイトル
        body            : 本文
        dashboard_token : ダッシュボードトークン（job_id 解決用）
        beta_tester_id  : βテスターID（任意）
        **kwargs        : その他フィールド

    Returns:
        dict: 作成されたフィードバックデータ（job_id は含む — 内部使用のみ）
    """
    feedback_id = generate_feedback_id()
    now = datetime.now().isoformat()

    # dashboard_token から job_id を解決（失敗しても続行）
    job_id = _resolve_job_id_from_token(dashboard_token)

    feedback: Dict[str, Any] = {**_FEEDBACK_DEFAULTS}
    feedback.update(kwargs)
    feedback.update({
        "feedback_id":     feedback_id,
        "created_at":      now,
        "updated_at":      now,
        "feedback_type":   feedback_type,
        "severity":        severity,
        "title":           title,
        "body":            body,
        "dashboard_token": dashboard_token,
        "job_id":          job_id,
        "beta_tester_id":  beta_tester_id,
    })

    fb_dir = get_feedback_dir(feedback_id)
    fb_dir.mkdir(parents=True, exist_ok=True)
    _save(feedback_id, feedback)

    logger.info("フィードバックを作成しました: %s (type=%s, severity=%s)", feedback_id, feedback_type, severity)
    return feedback


def load_feedback(feedback_id: str) -> Dict[str, Any]:
    """フィードバック JSON を読み込む。存在しない場合は {} を返す。"""
    p = get_feedback_json_path(feedback_id)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return {**_FEEDBACK_DEFAULTS, **raw}
    except Exception as e:
        logger.warning("フィードバック JSON 読み込み失敗 %s: %s", feedback_id, e)
        return {}


def update_feedback(feedback_id: str, **kwargs: Any) -> Dict[str, Any]:
    """フィードバックデータを更新して JSON に保存する。

    Returns:
        dict: 更新後のフィードバックデータ
    """
    fb = load_feedback(feedback_id)
    if not fb:
        raise FileNotFoundError(f"フィードバックが見つかりません: {feedback_id}")
    fb.update(kwargs)
    fb["updated_at"] = datetime.now().isoformat()

    if kwargs.get("status") == "resolved" and not fb.get("resolved_at"):
        fb["resolved_at"] = datetime.now().isoformat()

    _save(feedback_id, fb)
    return fb


def list_feedback(
    status_filter: Optional[str] = None,
    severity_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """フィードバック一覧を返す（作成日時の降順）。

    Args:
        status_filter   : status でフィルタリング（None で全件）
        severity_filter : severity でフィルタリング（None で全件）
        type_filter     : feedback_type でフィルタリング（None で全件）
    """
    if not FEEDBACK_DIR.exists():
        return []

    results = []
    for d in sorted(FEEDBACK_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        p = d / "feedback.json"
        if not p.exists():
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            fb = {**_FEEDBACK_DEFAULTS, **raw}
        except Exception:
            continue

        if status_filter and fb.get("status") != status_filter:
            continue
        if severity_filter and fb.get("severity") != severity_filter:
            continue
        if type_filter and fb.get("feedback_type") != type_filter:
            continue

        results.append(fb)

    return results


# ── 内部ヘルパー ─────────────────────────────────────────────────────────────

def _resolve_job_id_from_token(token: str) -> str:
    """dashboard_token から job_id を解決する。失敗時は空文字を返す。"""
    if not token:
        return ""
    try:
        from src.dashboard_manifest import find_job_id_by_token
        result = find_job_id_by_token(token)
        if result:
            job_id, _ = result
            return job_id
    except Exception as e:
        logger.debug("token から job_id 解決失敗: %s", e)
    return ""


def _save(feedback_id: str, data: Dict[str, Any]) -> None:
    """フィードバックデータを JSON に保存する。"""
    p = get_feedback_json_path(feedback_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
