"""
src/improvement_log.py — Javelin Video Analysis: 改善ログ管理 (Phase 15)

β版フィードバックを元にした改善項目（バックログ）を管理します。

ディレクトリ構造:
    data/improvement_logs/
        {improvement_id}/
            improvement.json

ステータス遷移:
    backlog → planned → in_progress → done
           ↘ wont_do
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.improvement")

# ── ディレクトリ ──────────────────────────────────────────────────────────────

_MODULE_DIR = Path(__file__).resolve().parent       # src/
_REPO_ROOT  = _MODULE_DIR.parent                    # project root
IMPROVEMENT_DIR = _REPO_ROOT / "data" / "improvement_logs"

# ── 定数 ──────────────────────────────────────────────────────────────────────

IMPROVEMENT_CATEGORIES: List[str] = [
    "ui",
    "analysis_accuracy",
    "report_quality",
    "delivery_flow",
    "performance",
    "bug",
    "legal",
    "pricing",
    "other",
]

IMPROVEMENT_CATEGORY_LABELS: Dict[str, str] = {
    "ui":               "🖥️ UI/UX",
    "analysis_accuracy": "📊 解析精度",
    "report_quality":   "📄 レポート品質",
    "delivery_flow":    "📦 納品フロー",
    "performance":      "⚡ パフォーマンス",
    "bug":              "🐛 バグ修正",
    "legal":            "⚖️ 法務・利用規約",
    "pricing":          "💰 価格・プラン",
    "other":            "その他",
}

IMPROVEMENT_STATUSES: List[str] = [
    "backlog",
    "planned",
    "in_progress",
    "done",
    "wont_do",
]

IMPROVEMENT_STATUS_LABELS: Dict[str, str] = {
    "backlog":     "📋 バックログ",
    "planned":     "📅 計画済み",
    "in_progress": "⏳ 進行中",
    "done":        "✅ 完了",
    "wont_do":     "⏭️ 対応しない",
}

PRIORITY_LEVELS: List[str] = [
    "low",
    "medium",
    "high",
    "critical",
]

PRIORITY_LABELS: Dict[str, str] = {
    "low":      "🟢 低",
    "medium":   "🟡 中",
    "high":     "🔴 高",
    "critical": "🚨 緊急",
}

# ── デフォルト値 ──────────────────────────────────────────────────────────────

_IMPROVEMENT_DEFAULTS: Dict[str, Any] = {
    # 識別・管理
    "improvement_id":      "",
    "created_at":          "",
    "updated_at":          "",
    "status":              "backlog",
    "category":            "other",
    "priority":            "medium",
    # 内容
    "title":               "",
    "description":         "",
    "impact":              "",        # 影響範囲・改善効果
    # ソース
    "source_feedback_id":  "",        # 元フィードバックID
    "source_job_id":       "",        # 元 job_id（参考）
    # 計画
    "planned_phase":       "",        # 例: "Phase 16"
    "done_at":             None,
    # 管理者メモ
    "admin_note":          "",
}

# ── ID 生成 ──────────────────────────────────────────────────────────────────

def generate_improvement_id() -> str:
    """改善ログIDを生成する: imp_YYYYMMDD_HHMMSS_xxxx"""
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = "".join(random.choices("abcdef0123456789", k=4))
    return f"imp_{ts}_{rand}"


# ── パス ─────────────────────────────────────────────────────────────────────

def get_improvement_dir(improvement_id: str) -> Path:
    """改善ログディレクトリを返す。"""
    return IMPROVEMENT_DIR / improvement_id


def get_improvement_json_path(improvement_id: str) -> Path:
    """improvement.json のパスを返す。"""
    return get_improvement_dir(improvement_id) / "improvement.json"


# ── CRUD ─────────────────────────────────────────────────────────────────────

def create_improvement(
    title: str,
    category: str = "other",
    priority: str = "medium",
    description: str = "",
    impact: str = "",
    source_feedback_id: str = "",
    source_job_id: str = "",
    planned_phase: str = "",
    admin_note: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """改善ログを作成して JSON に保存する。

    Returns:
        dict: 作成された改善ログデータ
    """
    improvement_id = generate_improvement_id()
    now = datetime.now().isoformat()

    improvement: Dict[str, Any] = {**_IMPROVEMENT_DEFAULTS}
    improvement.update(kwargs)
    improvement.update({
        "improvement_id":     improvement_id,
        "created_at":         now,
        "updated_at":         now,
        "title":              title,
        "category":           category,
        "priority":           priority,
        "description":        description,
        "impact":             impact,
        "source_feedback_id": source_feedback_id,
        "source_job_id":      source_job_id,
        "planned_phase":      planned_phase,
        "admin_note":         admin_note,
    })

    imp_dir = get_improvement_dir(improvement_id)
    imp_dir.mkdir(parents=True, exist_ok=True)
    _save(improvement_id, improvement)

    logger.info("改善ログを作成しました: %s", improvement_id)
    return improvement


def create_improvement_from_feedback(
    feedback_id: str,
    title: str = "",
    category: str = "other",
    priority: str = "medium",
    planned_phase: str = "",
    admin_note: str = "",
) -> Dict[str, Any]:
    """フィードバックから改善ログを作成する。

    フィードバックの本文・重要度を引き継ぎ、改善ログを作成する。
    作成後、フィードバックの improvement_id を更新する。

    Returns:
        dict: 作成された改善ログデータ
    """
    try:
        from src.feedback_manager import load_feedback, update_feedback
        fb = load_feedback(feedback_id)
    except Exception as e:
        raise RuntimeError(f"フィードバック読み込み失敗: {e}") from e

    if not fb:
        raise FileNotFoundError(f"フィードバックが見つかりません: {feedback_id}")

    # 重要度のマッピング
    sev_to_pri = {"low": "low", "medium": "medium", "high": "high", "critical": "critical"}
    priority_from_fb = sev_to_pri.get(fb.get("severity", "medium"), priority)

    # フィードバックのタイトル/本文を引き継ぐ
    _title = title or fb.get("title") or f"[フィードバックから] {fb.get('feedback_type', 'other')}"
    _desc  = fb.get("body", "")

    # priority 引数が未指定（"medium" デフォルト）のときはフィードバックの重要度を優先する
    _priority = priority_from_fb if priority == "medium" else priority

    improvement = create_improvement(
        title               = _title,
        category            = category,
        priority            = _priority,
        description         = _desc,
        source_feedback_id  = feedback_id,
        source_job_id       = fb.get("job_id", ""),
        planned_phase       = planned_phase,
        admin_note          = admin_note,
    )

    # フィードバックに improvement_id を記録（インポート済みの update_feedback を再利用）
    try:
        update_feedback(feedback_id, improvement_id=improvement["improvement_id"])
    except Exception as e:
        logger.warning("フィードバックへの improvement_id 書き込み失敗: %s", e)

    return improvement


def load_improvement(improvement_id: str) -> Dict[str, Any]:
    """改善ログ JSON を読み込む。存在しない場合は {} を返す。"""
    p = get_improvement_json_path(improvement_id)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return {**_IMPROVEMENT_DEFAULTS, **raw}
    except Exception as e:
        logger.warning("改善ログ JSON 読み込み失敗 %s: %s", improvement_id, e)
        return {}


def update_improvement(improvement_id: str, **kwargs: Any) -> Dict[str, Any]:
    """改善ログデータを更新して JSON に保存する。

    Returns:
        dict: 更新後の改善ログデータ
    """
    imp = load_improvement(improvement_id)
    if not imp:
        raise FileNotFoundError(f"改善ログが見つかりません: {improvement_id}")
    imp.update(kwargs)
    imp["updated_at"] = datetime.now().isoformat()

    if kwargs.get("status") == "done" and not imp.get("done_at"):
        imp["done_at"] = datetime.now().isoformat()

    _save(improvement_id, imp)
    return imp


def list_improvements(
    status_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    priority_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """改善ログ一覧を返す（作成日時の降順）。

    Args:
        status_filter   : status でフィルタリング（None で全件）
        category_filter : category でフィルタリング（None で全件）
        priority_filter : priority でフィルタリング（None で全件）
    """
    if not IMPROVEMENT_DIR.exists():
        return []

    results = []
    for d in sorted(IMPROVEMENT_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        p = d / "improvement.json"
        if not p.exists():
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            imp = {**_IMPROVEMENT_DEFAULTS, **raw}
        except Exception:
            continue

        if status_filter and imp.get("status") != status_filter:
            continue
        if category_filter and imp.get("category") != category_filter:
            continue
        if priority_filter and imp.get("priority") != priority_filter:
            continue

        results.append(imp)

    return results


# ── 内部ヘルパー ─────────────────────────────────────────────────────────────

def _save(improvement_id: str, data: Dict[str, Any]) -> None:
    """改善ログデータを JSON に保存する。"""
    p = get_improvement_json_path(improvement_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
