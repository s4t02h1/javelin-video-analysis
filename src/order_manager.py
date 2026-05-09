"""
src/order_manager.py — Javelin Video Analysis: 注文・支払い管理 (Phase 9)

注文（order）はジョブ・受付とは独立したエンティティとして管理されます。

ディレクトリ構造:
    data/orders/
        {order_id}/
            order.json

ステータス遷移:
    payment_status:
        unpaid → payment_requested → paid → (delivered)
        unpaid → not_required          （無料プラン）
        paid   → refunded              （返金）
        any    → cancelled

    delivery_status:
        not_started → in_progress → ready → delivered → archived

    refund_status:
        none → requested → approved → completed
                        ↘ rejected
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.order")

# ── ディレクトリ設定 ──────────────────────────────────────────────────────────

_MODULE_DIR = Path(__file__).resolve().parent   # src/
_REPO_ROOT  = _MODULE_DIR.parent                # project root


def _orders_root() -> Path:
    """注文データルートを返す。JVA_DATA_DIR / JVA_ORDERS_DIR 両方を尊重するため
    src.config.cfg.ORDERS_DIR に委譲する。"""
    from src.config import cfg  # lazy import — circular を避ける
    return cfg.ORDERS_DIR


# ── 定数 ──────────────────────────────────────────────────────────────────────

PAYMENT_STATUSES: List[str] = [
    "unpaid",             # 未払い
    "payment_requested",  # 支払い依頼済み
    "paid",               # 支払い確認済み
    "failed",             # 支払い失敗
    "refunded",           # 返金済み
    "cancelled",          # キャンセル済み
    "not_required",       # 支払い不要（無料）
]

PAYMENT_STATUS_LABELS: Dict[str, str] = {
    "unpaid":            "💳 未払い",
    "payment_requested": "📩 支払い依頼済み",
    "paid":              "✅ 支払い確認済み",
    "failed":            "❌ 支払い失敗",
    "refunded":          "↩️ 返金済み",
    "cancelled":         "🚫 キャンセル済み",
    "not_required":      "🆓 支払い不要",
}

DELIVERY_STATUSES: List[str] = [
    "not_started",  # 未着手
    "in_progress",  # 解析中
    "ready",        # 納品準備完了
    "delivered",    # 納品済み
    "archived",     # 保管済み
]

DELIVERY_STATUS_LABELS: Dict[str, str] = {
    "not_started": "⏸️ 未着手",
    "in_progress": "⏳ 解析中",
    "ready":       "📦 納品準備完了",
    "delivered":   "📨 納品済み",
    "archived":    "📂 保管済み",
}

REFUND_STATUSES: List[str] = [
    "none",       # 返金なし
    "requested",  # 返金依頼あり
    "approved",   # 返金承認済み
    "rejected",   # 返金不可
    "completed",  # 返金完了
]

REFUND_STATUS_LABELS: Dict[str, str] = {
    "none":      "—",
    "requested": "🔔 返金依頼あり",
    "approved":  "✅ 返金承認済み",
    "rejected":  "❌ 返金不可",
    "completed": "↩️ 返金完了",
}

CANCEL_STATUSES: List[str] = [
    "none",      # キャンセルなし
    "requested", # キャンセル依頼あり
    "approved",  # キャンセル承認済み
    "rejected",  # キャンセル不可（着手後等）
    "completed", # キャンセル完了
]

CANCEL_STATUS_LABELS: Dict[str, str] = {
    "none":      "—",
    "requested": "🔔 キャンセル依頼あり",
    "approved":  "✅ キャンセル承認済み",
    "rejected":  "❌ キャンセル不可",
    "completed": "🚫 キャンセル完了",
}

PAYMENT_METHODS: List[str] = [
    "manual_bank_transfer",  # 銀行振込（手動確認）
    "paypay",                # PayPay
    "stripe",                # Stripe（将来拡張用）
    "cash",                  # 現金手渡し
    "free",                  # 無料
    "other",                 # その他
]

PAYMENT_METHOD_LABELS: Dict[str, str] = {
    "manual_bank_transfer": "🏦 銀行振込（手動確認）",
    "paypay":               "📱 PayPay",
    "stripe":               "💳 Stripe",
    "cash":                 "💴 現金手渡し",
    "free":                 "🆓 無料",
    "other":                "📝 その他",
}


# ── order_id 生成 ─────────────────────────────────────────────────────────────

def generate_order_id() -> str:
    """ORD_YYYYMMDD_HHMMSS_xxxx 形式のユニークな注文IDを生成する。

    サフィックスは secrets モジュールを使い推測困難にする。
    """
    now = datetime.now()
    suffix = secrets.token_hex(2)   # 4文字の hex 文字列
    return now.strftime("ORD_%Y%m%d_%H%M%S") + f"_{suffix}"


# ── 料金プラン読み込み ────────────────────────────────────────────────────────

def load_pricing_plans() -> Dict[str, Any]:
    """configs/pricing_plans.yaml を読み込んで返す。

    PyYAML が未インストールの場合や YAML 読み込み失敗時は空辞書を返す。
    """
    try:
        import yaml  # type: ignore[import-not-found]
        plans_path = _REPO_ROOT / "configs" / "pricing_plans.yaml"
        if not plans_path.exists():
            return {}
        with open(plans_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("[order] pricing_plans.yaml の読み込みに失敗しました: %s", e)
        return {}


def get_plan(plan_key: str) -> Optional[Dict[str, Any]]:
    """指定したプランキーのプラン定義を返す。存在しない場合は None。"""
    return load_pricing_plans().get(plan_key)


def get_price_jpy(plan_key: str) -> int:
    """プランの価格（円）を返す。不明なプランは 0 を返す。"""
    plan = get_plan(plan_key)
    if plan is None:
        return 0
    return int(plan.get("price_jpy", 0))


def is_payment_required(plan_key: str) -> bool:
    """プランに支払いが必要かどうかを返す。不明なプランは False。"""
    plan = get_plan(plan_key)
    if plan is None:
        return False
    return bool(plan.get("payment_required", False))


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_order(
    selected_plan: str,
    *,
    intake_id: Optional[str] = None,
    job_id: Optional[str] = None,
    comparison_id: Optional[str] = None,
    customer_label: str = "",
    discount_jpy: int = 0,
    invoice_note: str = "",
    admin_note: str = "",
    payment_method: str = "manual_bank_transfer",
) -> Dict[str, Any]:
    """新しい注文を作成して order.json を保存し、order dict を返す。

    価格は pricing_plans.yaml から自動取得します。
    割引額を指定した場合は final_price_jpy = price_jpy - discount_jpy になります。
    無料プランの場合は payment_status を not_required に自動設定します。
    """
    order_id = generate_order_id()
    orders_dir = _orders_root()
    order_dir = orders_dir / order_id
    order_dir.mkdir(parents=True, exist_ok=True)

    price_jpy = get_price_jpy(selected_plan)
    payment_required = is_payment_required(selected_plan)
    final_price_jpy = max(0, price_jpy - discount_jpy)

    # 無料プランは支払いステータスを not_required に設定
    initial_payment_status = "not_required" if not payment_required else "unpaid"
    # 無料プランの支払い方法は free に自動設定
    if not payment_required:
        payment_method = "free"

    now = datetime.now().isoformat(timespec="seconds")
    order: Dict[str, Any] = {
        "order_id":           order_id,
        "created_at":         now,
        "updated_at":         now,
        # 関連エンティティ
        "intake_id":          intake_id,
        "job_id":             job_id,
        "comparison_id":      comparison_id,
        # 顧客・プラン
        "customer_label":     customer_label,
        "selected_plan":      selected_plan,
        "price_jpy":          price_jpy,
        "discount_jpy":       discount_jpy,
        "final_price_jpy":    final_price_jpy,
        # 支払い
        "payment_status":     initial_payment_status,
        "payment_method":     payment_method,
        "payment_reference":  "",   # 振込番号・PayPay取引IDなど
        # メモ
        "invoice_note":       invoice_note,
        "receipt_note":       "",
        # 納品・返金・キャンセル
        "delivery_status":    "not_started",
        "refund_status":      "none",
        "cancel_status":      "none",
        # 管理者メモ
        "admin_note":         admin_note,
    }

    _save_order(order)
    logger.info("[order] 注文作成: %s プラン=%s 金額=%d円", order_id, selected_plan, final_price_jpy)
    return order


def _save_order(order: Dict[str, Any]) -> None:
    """order dict を order.json に書き込む（内部用）。"""
    order_dir = _orders_root() / order["order_id"]
    order_dir.mkdir(parents=True, exist_ok=True)
    order_path = order_dir / "order.json"
    with open(order_path, "w", encoding="utf-8") as f:
        json.dump(order, f, ensure_ascii=False, indent=2)


def update_order(order_id: str, **kwargs: Any) -> Dict[str, Any]:
    """既存の注文フィールドを更新し、updated_at を自動更新して返す。

    Examples:
        update_order(order_id, payment_status="paid")
        update_order(order_id, delivery_status="delivered", receipt_note="...")
    """
    order = load_order(order_id)
    order.update(kwargs)
    order["updated_at"] = datetime.now().isoformat(timespec="seconds")
    # final_price_jpy を再計算（price_jpy や discount_jpy が変わった場合）
    price = int(order.get("price_jpy", 0))
    discount = int(order.get("discount_jpy", 0))
    order["final_price_jpy"] = max(0, price - discount)
    _save_order(order)
    return order


def load_order(order_id: str) -> Dict[str, Any]:
    """order.json を読み込んで dict として返す。"""
    order_path = _orders_root() / order_id / "order.json"
    with open(order_path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_orders() -> List[Dict[str, Any]]:
    """すべての注文を新しい順に返す。"""
    root = _orders_root()
    if not root.exists():
        return []
    orders = []
    for order_dir in root.iterdir():
        if not order_dir.is_dir():
            continue
        order_json = order_dir / "order.json"
        if not order_json.exists():
            continue
        try:
            orders.append(load_order(order_dir.name))
        except Exception:
            pass
    orders.sort(key=lambda o: o.get("order_id", ""), reverse=True)
    return orders


def find_orders_for_job(job_id: str) -> List[Dict[str, Any]]:
    """指定した job_id に紐付いた注文一覧を返す。"""
    return [o for o in list_orders() if o.get("job_id") == job_id]


def find_orders_for_intake(intake_id: str) -> List[Dict[str, Any]]:
    """指定した intake_id に紐付いた注文一覧を返す。"""
    return [o for o in list_orders() if o.get("intake_id") == intake_id]


def find_orders_for_comparison(comparison_id: str) -> List[Dict[str, Any]]:
    """指定した comparison_id に紐付いた注文一覧を返す。"""
    return [o for o in list_orders() if o.get("comparison_id") == comparison_id]


# ── 納品前チェック ────────────────────────────────────────────────────────────

def check_payment_before_delivery(
    order: Dict[str, Any],
) -> Dict[str, Any]:
    """納品前の支払い状態を確認する。

    Returns:
        {
            "ok": bool,              # True なら納品可能
            "warning": str | None,   # 警告メッセージ（ok=False の場合）
            "reason": str,           # "paid" / "not_required" / "unpaid" / "override_allowed"
        }
    """
    payment_status = order.get("payment_status", "unpaid")
    plan_key       = order.get("selected_plan", "")
    plan_info      = get_plan(plan_key)
    payment_req    = plan_info.get("payment_required", True) if plan_info else True

    if not payment_req or payment_status == "not_required":
        return {"ok": True, "warning": None, "reason": "not_required"}

    if payment_status == "paid":
        return {"ok": True, "warning": None, "reason": "paid"}

    label = PAYMENT_STATUS_LABELS.get(payment_status, payment_status)
    return {
        "ok": False,
        "warning": (
            f"⚠️ 支払いが未完了です（現在: {label}）。\n"
            "有料プランの場合は支払い確認後に納品することを推奨します。\n"
            "管理者判断で納品を進めることもできます。"
        ),
        "reason": "unpaid",
    }
