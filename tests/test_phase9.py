"""
tests/test_phase9.py — Phase 9: 課金・利用規約・正式サービス化準備 テスト
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# ── パス設定 ──────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.append(str(_REPO_ROOT))


class TestPricingPlans(unittest.TestCase):
    """pricing_plans.yaml の読み込みテスト"""

    def test_file_exists(self) -> None:
        """pricing_plans.yaml が存在する"""
        plans_path = _REPO_ROOT / "configs" / "pricing_plans.yaml"
        self.assertTrue(plans_path.exists(), f"pricing_plans.yaml が見つかりません: {plans_path}")

    def test_load_pricing_plans(self) -> None:
        """load_pricing_plans() が dict を返す"""
        from src.order_manager import load_pricing_plans
        plans = load_pricing_plans()
        self.assertIsInstance(plans, dict)
        self.assertGreater(len(plans), 0, "プランが1件以上ある")

    def test_expected_plan_keys(self) -> None:
        """主要プランキーが存在する"""
        from src.order_manager import load_pricing_plans
        plans = load_pricing_plans()
        expected = {"free_preview", "light", "data_sheet", "full_report", "comparison"}
        for key in expected:
            self.assertIn(key, plans, f"プランキー {key!r} が見つかりません")

    def test_free_preview_not_payment_required(self) -> None:
        """free_preview は payment_required=False"""
        from src.order_manager import is_payment_required
        self.assertFalse(is_payment_required("free_preview"))

    def test_paid_plans_require_payment(self) -> None:
        """有料プランは payment_required=True"""
        from src.order_manager import is_payment_required
        for plan in ("light", "data_sheet", "full_report", "comparison"):
            with self.subTest(plan=plan):
                self.assertTrue(is_payment_required(plan), f"{plan} は payment_required=True のはず")

    def test_unknown_plan_returns_none(self) -> None:
        """存在しないプランは get_plan が None を返す（落ちない）"""
        from src.order_manager import get_plan
        result = get_plan("nonexistent_plan_xyz")
        self.assertIsNone(result)

    def test_unknown_plan_price_returns_zero(self) -> None:
        """存在しないプランは get_price_jpy が 0 を返す（落ちない）"""
        from src.order_manager import get_price_jpy
        self.assertEqual(get_price_jpy("nonexistent_plan_xyz"), 0)

    def test_plan_prices_are_non_negative(self) -> None:
        """すべてのプランの価格が 0 以上"""
        from src.order_manager import load_pricing_plans
        for key, plan in load_pricing_plans().items():
            with self.subTest(plan=key):
                self.assertGreaterEqual(plan.get("price_jpy", 0), 0)

    def test_free_preview_price_is_zero(self) -> None:
        """free_preview の価格が 0"""
        from src.order_manager import get_price_jpy
        self.assertEqual(get_price_jpy("free_preview"), 0)


class TestOrderManager(unittest.TestCase):
    """order_manager の CRUD テスト"""

    def setUp(self) -> None:
        """テスト用の一時ディレクトリを orders_dir として使う"""
        self._tmpdir = tempfile.mkdtemp()
        os.environ["JVA_ORDERS_DIR"] = self._tmpdir

    def tearDown(self) -> None:
        """一時ディレクトリを削除し、環境変数をリセット"""
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        os.environ.pop("JVA_ORDERS_DIR", None)

    def test_create_order_basic(self) -> None:
        """基本的な注文作成"""
        from src.order_manager import create_order
        order = create_order("light", customer_label="テスト太郎")
        self.assertIn("order_id", order)
        self.assertTrue(order["order_id"].startswith("ORD_"))
        self.assertEqual(order["selected_plan"], "light")
        self.assertEqual(order["customer_label"], "テスト太郎")

    def test_create_order_persisted(self) -> None:
        """作成した注文が order.json として保存される"""
        from src.order_manager import create_order, load_order
        order = create_order("data_sheet")
        loaded = load_order(order["order_id"])
        self.assertEqual(loaded["order_id"], order["order_id"])
        self.assertEqual(loaded["selected_plan"], "data_sheet")

    def test_create_order_price_auto_filled(self) -> None:
        """プランの価格が自動設定される"""
        from src.order_manager import create_order, get_price_jpy
        plan = "full_report"
        expected_price = get_price_jpy(plan)
        order = create_order(plan)
        self.assertEqual(order["price_jpy"], expected_price)
        self.assertEqual(order["final_price_jpy"], expected_price)

    def test_create_order_discount(self) -> None:
        """割引額が final_price_jpy に反映される"""
        from src.order_manager import create_order, get_price_jpy
        plan = "full_report"
        base_price = get_price_jpy(plan)
        order = create_order(plan, discount_jpy=500)
        self.assertEqual(order["discount_jpy"], 500)
        self.assertEqual(order["final_price_jpy"], max(0, base_price - 500))

    def test_create_order_free_plan_sets_not_required(self) -> None:
        """無料プランは payment_status が not_required"""
        from src.order_manager import create_order
        order = create_order("free_preview")
        self.assertEqual(order["payment_status"], "not_required")

    def test_create_order_paid_plan_sets_unpaid(self) -> None:
        """有料プランは payment_status が unpaid"""
        from src.order_manager import create_order
        order = create_order("light")
        self.assertEqual(order["payment_status"], "unpaid")

    def test_create_order_with_job_id(self) -> None:
        """job_id を紐付けた注文を作成できる"""
        from src.order_manager import create_order, find_orders_for_job
        order = create_order("data_sheet", job_id="test_job_001")
        self.assertEqual(order["job_id"], "test_job_001")
        orders = find_orders_for_job("test_job_001")
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["order_id"], order["order_id"])

    def test_create_order_with_intake_id(self) -> None:
        """intake_id を紐付けた注文を作成できる"""
        from src.order_manager import create_order, find_orders_for_intake
        order = create_order("light", intake_id="intake_test_001")
        self.assertEqual(order["intake_id"], "intake_test_001")
        orders = find_orders_for_intake("intake_test_001")
        self.assertEqual(len(orders), 1)

    def test_create_order_with_comparison_id(self) -> None:
        """comparison_id を紐付けた注文を作成できる"""
        from src.order_manager import create_order, find_orders_for_comparison
        order = create_order("comparison", comparison_id="cmp_test_001")
        self.assertEqual(order["comparison_id"], "cmp_test_001")
        orders = find_orders_for_comparison("cmp_test_001")
        self.assertEqual(len(orders), 1)

    def test_update_payment_status(self) -> None:
        """支払いステータスを更新できる"""
        from src.order_manager import create_order, update_order, load_order
        order = create_order("light")
        updated = update_order(order["order_id"], payment_status="paid")
        self.assertEqual(updated["payment_status"], "paid")
        # 永続化確認
        reloaded = load_order(order["order_id"])
        self.assertEqual(reloaded["payment_status"], "paid")

    def test_update_delivery_status(self) -> None:
        """納品ステータスを更新できる"""
        from src.order_manager import create_order, update_order
        order = create_order("light")
        updated = update_order(order["order_id"], delivery_status="delivered")
        self.assertEqual(updated["delivery_status"], "delivered")

    def test_update_refund_status(self) -> None:
        """返金ステータスを更新できる"""
        from src.order_manager import create_order, update_order
        order = create_order("light")
        updated = update_order(order["order_id"], refund_status="requested")
        self.assertEqual(updated["refund_status"], "requested")

    def test_list_orders(self) -> None:
        """list_orders が全注文を返す"""
        from src.order_manager import create_order, list_orders
        create_order("free_preview", customer_label="A")
        create_order("light", customer_label="B")
        create_order("data_sheet", customer_label="C")
        orders = list_orders()
        self.assertEqual(len(orders), 3)

    def test_list_orders_empty(self) -> None:
        """注文がない場合は空リストを返す"""
        from src.order_manager import list_orders
        orders = list_orders()
        self.assertEqual(orders, [])

    def test_order_id_format(self) -> None:
        """order_id が ORD_YYYYMMDD_HHMMSS_xxxx 形式"""
        from src.order_manager import create_order
        import re
        order = create_order("free_preview")
        self.assertRegex(order["order_id"], r"^ORD_\d{8}_\d{6}_[0-9a-f]{4}$")

    def test_final_price_non_negative(self) -> None:
        """割引額が価格を超えても final_price_jpy は 0 以上"""
        from src.order_manager import create_order, get_price_jpy
        plan = "light"
        base = get_price_jpy(plan)
        order = create_order(plan, discount_jpy=base + 9999)
        self.assertGreaterEqual(order["final_price_jpy"], 0)

    def test_update_recalculates_final_price(self) -> None:
        """update_order で discount_jpy を変更すると final_price_jpy が再計算される"""
        from src.order_manager import create_order, update_order, get_price_jpy
        plan = "data_sheet"
        base = get_price_jpy(plan)
        order = create_order(plan)
        self.assertEqual(order["final_price_jpy"], base)
        updated = update_order(order["order_id"], discount_jpy=500)
        self.assertEqual(updated["final_price_jpy"], max(0, base - 500))


class TestPaymentDeliveryCheck(unittest.TestCase):
    """check_payment_before_delivery テスト"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        os.environ["JVA_ORDERS_DIR"] = self._tmpdir

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        os.environ.pop("JVA_ORDERS_DIR", None)

    def test_free_plan_ok(self) -> None:
        """無料プランは納品 OK"""
        from src.order_manager import create_order, check_payment_before_delivery
        order = create_order("free_preview")
        result = check_payment_before_delivery(order)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "not_required")

    def test_paid_plan_unpaid_warning(self) -> None:
        """有料プランで未払いの場合、ok=False で警告が出る"""
        from src.order_manager import create_order, check_payment_before_delivery
        order = create_order("light")
        result = check_payment_before_delivery(order)
        self.assertFalse(result["ok"])
        self.assertIsNotNone(result["warning"])
        self.assertEqual(result["reason"], "unpaid")

    def test_paid_plan_paid_ok(self) -> None:
        """有料プランで paid の場合は納品 OK"""
        from src.order_manager import create_order, update_order, check_payment_before_delivery
        order = create_order("full_report")
        updated = update_order(order["order_id"], payment_status="paid")
        result = check_payment_before_delivery(updated)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "paid")

    def test_payment_requested_still_warns(self) -> None:
        """payment_requested は paid でないため警告"""
        from src.order_manager import create_order, update_order, check_payment_before_delivery
        order = create_order("data_sheet")
        updated = update_order(order["order_id"], payment_status="payment_requested")
        result = check_payment_before_delivery(updated)
        self.assertFalse(result["ok"])

    def test_not_required_status_ok(self) -> None:
        """payment_status=not_required は直接 OK"""
        from src.order_manager import create_order, update_order, check_payment_before_delivery
        order = create_order("light")
        updated = update_order(order["order_id"], payment_status="not_required")
        result = check_payment_before_delivery(updated)
        self.assertTrue(result["ok"])


class TestMessageTemplates(unittest.TestCase):
    """message_templates のテスト"""

    def test_payment_request_contains_plan_label(self) -> None:
        """支払い依頼メッセージにプランラベルが含まれる"""
        from src.message_templates import generate_payment_request
        msg = generate_payment_request("フルレポート版", 5000, customer_label="山田太郎")
        self.assertIn("フルレポート版", msg)
        self.assertIn("5,000", msg)
        self.assertIn("山田太郎", msg)

    def test_payment_request_disclaimer(self) -> None:
        """支払い依頼メッセージに免責事項が含まれる"""
        from src.message_templates import generate_payment_request
        msg = generate_payment_request("ライト版", 1000)
        self.assertIn("競技指導", msg)
        self.assertIn("医療診断", msg)
        self.assertIn("参考資料", msg)

    def test_payment_receipt_contains_amount(self) -> None:
        """領収メッセージに金額が含まれる"""
        from src.message_templates import generate_payment_receipt
        msg = generate_payment_receipt("データシート版", 3000, customer_label="鈴木花子")
        self.assertIn("3,000", msg)
        self.assertIn("鈴木花子", msg)
        self.assertIn("お支払いを確認", msg)

    def test_delivery_message_with_url(self) -> None:
        """納品メッセージに URL が含まれる"""
        from src.message_templates import generate_delivery_with_payment_info
        url = "https://example.com/delivery/test"
        msg = generate_delivery_with_payment_info("ライト版", url)
        self.assertIn(url, msg)
        self.assertIn("納品URL", msg)

    def test_cancel_before_analysis(self) -> None:
        """解析着手前キャンセルメッセージに適切な文面が含まれる"""
        from src.message_templates import generate_cancel_before_analysis
        msg = generate_cancel_before_analysis("light", customer_label="テスト様")
        self.assertIn("テスト様", msg)
        self.assertIn("キャンセル", msg)
        # 返金への言及
        self.assertIn("返金", msg)

    def test_cancel_after_analysis(self) -> None:
        """解析着手後キャンセルメッセージに原則返金不可の文面が含まれる"""
        from src.message_templates import generate_cancel_after_analysis
        msg = generate_cancel_after_analysis("full_report")
        self.assertIn("原則", msg)

    def test_refund_approved_message(self) -> None:
        """返金承認メッセージに金額が含まれる"""
        from src.message_templates import generate_refund_response
        msg = generate_refund_response(
            customer_label="テスト様",
            refund_approved=True,
            refund_amount_jpy=3000,
        )
        self.assertIn("3,000", msg)
        self.assertIn("返金", msg)

    def test_refund_rejected_message(self) -> None:
        """返金不可メッセージ"""
        from src.message_templates import generate_refund_response
        msg = generate_refund_response(refund_approved=False)
        self.assertIn("難しい", msg)

    def test_no_real_account_info_in_templates(self) -> None:
        """テンプレートに本物の口座情報が含まれていないこと"""
        from src.message_templates import generate_payment_request
        msg = generate_payment_request("ライト版", 1000, payment_info="")
        # 本物の口座番号形式（数字7桁）がないこと
        import re
        account_pattern = re.compile(r"\b\d{7}\b")
        self.assertIsNone(account_pattern.search(msg), "テンプレートに口座番号らしき数字が含まれています")

    def test_video_issue_response(self) -> None:
        """動画不備対応メッセージ"""
        from src.message_templates import generate_video_issue_response
        msg = generate_video_issue_response(issue_description="画質が低すぎます")
        self.assertIn("画質が低すぎます", msg)


class TestConfigOrdersDir(unittest.TestCase):
    """src/config.py の ORDERS_DIR テスト"""

    def setUp(self) -> None:
        self._saved = {k: os.environ[k] for k in ("JVA_DATA_DIR", "JVA_ORDERS_DIR") if k in os.environ}
        os.environ.pop("JVA_DATA_DIR", None)
        os.environ.pop("JVA_ORDERS_DIR", None)
        # Windows / Unix 共通の一時ディレクトリ
        import tempfile
        self._tmp_orders = tempfile.mkdtemp()
        self._tmp_data   = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil
        os.environ.pop("JVA_DATA_DIR", None)
        os.environ.pop("JVA_ORDERS_DIR", None)
        for k, v in self._saved.items():
            os.environ[k] = v
        shutil.rmtree(self._tmp_orders, ignore_errors=True)
        shutil.rmtree(self._tmp_data,   ignore_errors=True)

    def test_default_orders_dir(self) -> None:
        """デフォルトの ORDERS_DIR は data/orders"""
        from src.config import _Config
        cfg = _Config()
        self.assertTrue(str(cfg.ORDERS_DIR).endswith(str(Path("data") / "orders")))

    def test_custom_orders_dir_via_env(self) -> None:
        """JVA_ORDERS_DIR 環境変数で上書きできる"""
        from src.config import _Config
        os.environ["JVA_ORDERS_DIR"] = self._tmp_orders
        cfg = _Config()
        self.assertEqual(Path(cfg.ORDERS_DIR), Path(self._tmp_orders))

    def test_orders_dir_follows_data_dir(self) -> None:
        """JVA_DATA_DIR を変えると ORDERS_DIR も変わる"""
        from src.config import _Config
        os.environ["JVA_DATA_DIR"] = self._tmp_data
        cfg = _Config()
        expected = Path(self._tmp_data) / "orders"
        self.assertEqual(Path(cfg.ORDERS_DIR), expected)


class TestLogPrivacy(unittest.TestCase):
    """個人情報のログ出力テスト"""

    def test_payment_reference_not_logged_automatically(self) -> None:
        """order_manager は payment_reference をデフォルトでログに出力しない"""
        import logging
        import tempfile
        import shutil
        tmpdir = tempfile.mkdtemp()
        os.environ["JVA_ORDERS_DIR"] = tmpdir
        try:
            # ログキャプチャ
            log_records = []

            class CaptureHandler(logging.Handler):
                def emit(self, record: logging.LogRecord) -> None:
                    log_records.append(record.getMessage())

            capture = CaptureHandler()
            logger = logging.getLogger("jva.order")
            logger.addHandler(capture)
            old_level = logger.level
            logger.setLevel(logging.DEBUG)
            try:
                from src.order_manager import create_order
                create_order("light", customer_label="テスト")
            finally:
                logger.removeHandler(capture)
                logger.setLevel(old_level)

            # ログメッセージに customer_label そのものは含まれない（order_idとplan名のみ）
            for msg in log_records:
                self.assertNotIn("テスト", msg, f"顧客ラベルがログに出力されています: {msg!r}")
        finally:
            os.environ.pop("JVA_ORDERS_DIR", None)
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestLegalDocs(unittest.TestCase):
    """法務ドラフトファイルの存在確認テスト"""

    _LEGAL_DIR = _REPO_ROOT / "docs" / "legal"

    def _check_file(self, filename: str) -> None:
        path = self._LEGAL_DIR / filename
        self.assertTrue(path.exists(), f"法務ドラフトが見つかりません: {path}")

    def test_terms_of_service_draft_exists(self) -> None:
        self._check_file("terms_of_service_draft.md")

    def test_privacy_policy_draft_exists(self) -> None:
        self._check_file("privacy_policy_draft.md")

    def test_specified_commercial_transactions_draft_exists(self) -> None:
        self._check_file("specified_commercial_transactions_draft.md")

    def test_refund_cancel_policy_draft_exists(self) -> None:
        self._check_file("refund_cancel_policy_draft.md")

    def test_minor_user_policy_draft_exists(self) -> None:
        self._check_file("minor_user_policy_draft.md")

    def test_disclaimer_draft_exists(self) -> None:
        self._check_file("disclaimer_draft.md")

    def test_all_drafts_marked_as_draft(self) -> None:
        """すべての法務ドラフトに「ドラフト」または「draft」の表記がある"""
        for fname in [
            "terms_of_service_draft.md",
            "privacy_policy_draft.md",
            "specified_commercial_transactions_draft.md",
            "refund_cancel_policy_draft.md",
            "minor_user_policy_draft.md",
            "disclaimer_draft.md",
        ]:
            path = self._LEGAL_DIR / fname
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8").lower()
            self.assertTrue(
                "ドラフト" in content or "draft" in content,
                f"{fname} に「ドラフト」または「draft」の表記がありません"
            )


if __name__ == "__main__":
    unittest.main()
