"""
src/message_templates.py — Javelin Video Analysis: メッセージテンプレート (Phase 9)

支払い依頼・支払い確認・キャンセル・返金などのメッセージ文面を生成します。

⚠️ 本物の口座情報・決済URLはこのファイルに書かないでください。
   管理者が管理画面から入力した情報を差し込む方式にしてください。
"""
from __future__ import annotations

from typing import Optional


# ── 免責事項フッター ──────────────────────────────────────────────────────────

_DISCLAIMER_FOOTER = """\

──────────────────────────────────
【ご注意】
本解析は、動画から取得した姿勢推定データをもとにした参考資料です。
競技指導・医療診断・怪我の診断を代替するものではありません。
解析結果は絶対評価ではなく、動画の画質・撮影角度・服装・背景によって精度が異なります。
練習内容や技術判断については、指導者・専門家とご相談ください。
未成年の方がご利用の場合は、保護者または指導者の確認を推奨します。
──────────────────────────────────"""


# ── 支払い依頼テンプレート ────────────────────────────────────────────────────

def generate_payment_request(
    plan_label: str,
    final_price_jpy: int,
    customer_label: str = "",
    order_id: str = "",
    payment_method: str = "manual_bank_transfer",
    payment_info: str = "",   # 口座情報・PayPay IDなど（管理者が入力）
    extra_note: str = "",
) -> str:
    """支払い依頼メッセージを生成して返す。

    Args:
        plan_label       : プラン表示名（例: "フルレポート版"）
        final_price_jpy  : 最終請求金額（円）
        customer_label   : 顧客ラベル（省略可）
        order_id         : 注文ID（省略可）
        payment_method   : 支払い方法キー
        payment_info     : 支払い先情報（管理者が入力する任意文字列）
        extra_note       : 追加メモ（省略可）
    """
    lines = []

    if customer_label:
        lines.append(f"{customer_label} 様")
        lines.append("")

    lines.append("このたびは動画解析サービスへのお申し込みありがとうございます。")
    lines.append("")
    lines.append("━━ ご請求内容 ━━━━━━━━━━━━━━━━━━")
    lines.append(f"ご希望プラン：{plan_label}")
    lines.append(f"料　　　　金：{final_price_jpy:,} 円")
    if order_id:
        lines.append(f"注文番号　　：{order_id}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    # 支払い方法別の案内
    method_labels = {
        "manual_bank_transfer": "銀行振込",
        "paypay":               "PayPay",
        "stripe":               "クレジットカード（Stripe）",
        "cash":                 "現金手渡し",
        "free":                 "無料",
        "other":                "その他",
    }
    method_label = method_labels.get(payment_method, payment_method)

    lines.append(f"【お支払い方法：{method_label}】")
    if payment_info:
        lines.append(payment_info)
    else:
        lines.append("（お支払い先の詳細は別途ご連絡します。）")
    lines.append("")
    lines.append("内容をご確認のうえ、お支払いをお願いいたします。")
    lines.append("お支払い確認後、順番に解析作業へ進みます。")
    lines.append("")

    if extra_note:
        lines.append(extra_note)
        lines.append("")

    lines.append("解析着手後のキャンセル・返金については、原則として対応できない場合があります。")
    lines.append("あらかじめご了承ください。")
    lines.append(_DISCLAIMER_FOOTER)

    return "\n".join(lines)


# ── 支払い確認（領収）テンプレート ────────────────────────────────────────────

def generate_payment_receipt(
    plan_label: str,
    final_price_jpy: int,
    customer_label: str = "",
    order_id: str = "",
    receipt_note: str = "",
    extra_note: str = "",
) -> str:
    """支払い確認メッセージを生成して返す。"""
    lines = []

    if customer_label:
        lines.append(f"{customer_label} 様")
        lines.append("")

    lines.append("お支払いを確認いたしました。")
    lines.append("ありがとうございます。")
    lines.append("")
    lines.append("━━ 支払い確認内容 ━━━━━━━━━━━━━━━━")
    lines.append(f"プ　ラ　ン：{plan_label}")
    lines.append(f"確認金額：{final_price_jpy:,} 円")
    if order_id:
        lines.append(f"注文番号：{order_id}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("これより解析作業に進めます。")
    lines.append("動画の画質や撮影角度によっては、追加確認をお願いする場合があります。")
    lines.append("")
    lines.append("解析が完了しましたら、納品URLをお送りします。")
    lines.append("しばらくお待ちください。")

    if receipt_note:
        lines.append("")
        lines.append(receipt_note)

    if extra_note:
        lines.append("")
        lines.append(extra_note)

    lines.append(_DISCLAIMER_FOOTER)
    return "\n".join(lines)


# ── 納品メッセージ（支払い情報付き版） ───────────────────────────────────────

def generate_delivery_with_payment_info(
    plan_label: str,
    delivery_url: str,
    customer_label: str = "",
    order_id: str = "",
    extra_note: str = "",
) -> str:
    """納品URLと合わせた納品メッセージを生成して返す。"""
    lines = []

    if customer_label:
        lines.append(f"{customer_label} 様")
        lines.append("")

    lines.append("お待たせいたしました。解析が完了しましたのでご連絡します。")
    lines.append("")
    lines.append("━━ 納品内容 ━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"プラン：{plan_label}")
    if order_id:
        lines.append(f"注文番号：{order_id}")
    lines.append(f"納品URL：{delivery_url}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("URLには有効期限がございます。期限内にダウンロードをお願いします。")
    lines.append("ご不明な点がございましたら、お気軽にご連絡ください。")

    if extra_note:
        lines.append("")
        lines.append(extra_note)

    lines.append(_DISCLAIMER_FOOTER)
    return "\n".join(lines)


# ── キャンセル・返金テンプレート ──────────────────────────────────────────────

def generate_cancel_before_analysis(
    plan_label: str,
    customer_label: str = "",
    order_id: str = "",
    extra_note: str = "",
) -> str:
    """解析着手前のキャンセル対応メッセージを生成して返す。"""
    lines = []

    if customer_label:
        lines.append(f"{customer_label} 様")
        lines.append("")

    lines.append("キャンセルのご連絡をありがとうございます。")
    lines.append("")
    if order_id:
        lines.append(f"注文番号：{order_id}（プラン：{plan_label}）")
        lines.append("")
    lines.append("解析着手前のキャンセルを承りました。")
    lines.append("お支払いをいただいていた場合は、返金手続きについて別途ご連絡いたします。")
    lines.append("返金の方法・タイミングについては、お支払い方法により異なります。")
    lines.append("")
    lines.append("またのご利用をお待ちしております。")

    if extra_note:
        lines.append("")
        lines.append(extra_note)

    return "\n".join(lines)


def generate_cancel_after_analysis(
    plan_label: str,
    customer_label: str = "",
    order_id: str = "",
    extra_note: str = "",
) -> str:
    """解析着手後のキャンセル対応メッセージを生成して返す。"""
    lines = []

    if customer_label:
        lines.append(f"{customer_label} 様")
        lines.append("")

    lines.append("ご連絡いただきありがとうございます。")
    lines.append("")
    if order_id:
        lines.append(f"注文番号：{order_id}（プラン：{plan_label}）")
        lines.append("")
    lines.append("恐れ入りますが、解析作業にすでに着手しているため、")
    lines.append("原則としてキャンセル・返金には対応できない場合があります。")
    lines.append("")
    lines.append("ただし、動画の不備・システムエラーなど当方に起因する問題の場合は、")
    lines.append("個別に対応を検討いたします。お気軽にご相談ください。")

    if extra_note:
        lines.append("")
        lines.append(extra_note)

    return "\n".join(lines)


def generate_video_issue_response(
    customer_label: str = "",
    order_id: str = "",
    issue_description: str = "",
    extra_note: str = "",
) -> str:
    """動画不備による対応メッセージを生成して返す。"""
    lines = []

    if customer_label:
        lines.append(f"{customer_label} 様")
        lines.append("")

    lines.append("動画を確認させていただきました。")
    lines.append("")
    if order_id:
        lines.append(f"注文番号：{order_id}")
        lines.append("")
    if issue_description:
        lines.append(f"【確認事項】")
        lines.append(issue_description)
        lines.append("")
    lines.append("上記の点について確認・対応をお願いできますでしょうか。")
    lines.append("")
    lines.append("なお、動画の画質・撮影角度・背景・服装によっては解析精度に影響が出る場合があります。")
    lines.append("状況により解析が難しい場合は、代替案（プラン変更・部分解析など）をご提案する場合があります。")

    if extra_note:
        lines.append("")
        lines.append(extra_note)

    return "\n".join(lines)


def generate_refund_response(
    customer_label: str = "",
    order_id: str = "",
    refund_approved: bool = False,
    refund_amount_jpy: Optional[int] = None,
    extra_note: str = "",
) -> str:
    """返金対応メッセージを生成して返す。"""
    lines = []

    if customer_label:
        lines.append(f"{customer_label} 様")
        lines.append("")

    lines.append("返金に関するご連絡です。")
    lines.append("")
    if order_id:
        lines.append(f"注文番号：{order_id}")
        lines.append("")

    if refund_approved:
        lines.append("ご要望を確認の上、返金対応いたします。")
        if refund_amount_jpy is not None:
            lines.append(f"返金金額：{refund_amount_jpy:,} 円")
        lines.append("返金先・手続きについては、別途ご連絡いたします。")
        lines.append("お時間をいただく場合がございますが、ご了承ください。")
    else:
        lines.append("恐れ入りますが、今回は返金対応が難しい状況です。")
        lines.append("詳細については個別にご説明させていただきます。")
        lines.append("ご不明な点があればお気軽にご連絡ください。")

    if extra_note:
        lines.append("")
        lines.append(extra_note)

    return "\n".join(lines)
