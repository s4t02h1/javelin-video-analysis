"""Phase 3 ユニットテスト

テスト対象:
- configs/plans.yaml 読み込み
- src/plan_loader: 存在しないプラン→フォールバック
- job_manager: 受付情報の保存・読み込み・デフォルト値
- job_manager: 受付情報フォールバック（ファイルなし / 破損）
- job_manager: 納品前チェックリストの保存・読み込み
- job_manager: 同意事項の初期値が全 False（安全側）
- plan_loader: PyYAML なし環境でフォールバックが動作する
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# ── パス設定 ─────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# `src/types/__init__.py` が stdlib types をシャドーイングするため
# `import src.X` パターンを使う
os.environ.setdefault("JVA_JOBS_DIR", "")  # 後でテスト用 dir をセット


# ─────────────────────────────────────────────────────────────────────────────
# Helper: テンポラリ jobs ディレクトリを使う job_manager を再ロード
# ─────────────────────────────────────────────────────────────────────────────
def _load_job_manager_with_tmpdir(tmp_dir: Path):
    """job_manager モジュールを指定の jobs ディレクトリで動作させる。"""
    import importlib
    import job_manager as jm
    # JOBS_DIR を一時的に差し替える
    original = jm.JOBS_DIR
    jm.JOBS_DIR = tmp_dir
    return jm, original


class TestPlansYaml(unittest.TestCase):
    """configs/plans.yaml の内容確認"""

    def setUp(self):
        self._yaml_path = _REPO_ROOT / "configs" / "plans.yaml"

    def test_plans_yaml_exists(self):
        self.assertTrue(self._yaml_path.exists(), "configs/plans.yaml が存在しません")

    def test_plans_yaml_has_required_keys(self):
        try:
            import yaml
            with open(self._yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except ImportError:
            self.skipTest("PyYAML 未インストールのためスキップ")
        required = {"free_preview", "light", "data_sheet", "full_report", "comparison"}
        self.assertTrue(required.issubset(set(data.keys())), f"必須プランが不足: {required - set(data.keys())}")

    def test_each_plan_has_label(self):
        try:
            import yaml
            with open(self._yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except ImportError:
            self.skipTest("PyYAML 未インストールのためスキップ")
        for plan_key, plan_val in data.items():
            self.assertIn("label", plan_val, f"プラン '{plan_key}' に label がありません")
            self.assertIsInstance(plan_val["label"], str)
            self.assertGreater(len(plan_val["label"]), 0)


class TestPlanLoader(unittest.TestCase):
    """src/plan_loader のテスト"""

    def test_load_plans_returns_dict(self):
        import src.plan_loader as pl
        plans = pl.load_plans()
        self.assertIsInstance(plans, dict)
        self.assertGreater(len(plans), 0)

    def test_known_plan_has_label(self):
        import src.plan_loader as pl
        label = pl.get_plan_label("free_preview")
        self.assertIsInstance(label, str)
        self.assertGreater(len(label), 0)

    def test_unknown_plan_falls_back(self):
        import src.plan_loader as pl
        label = pl.get_plan_label("nonexistent_plan_xyz")
        # フォールバックとして free_preview のラベルか "nonexistent..." かのどちらか
        self.assertIsInstance(label, str)
        self.assertGreater(len(label), 0)

    def test_get_all_plan_keys_includes_required(self):
        import src.plan_loader as pl
        keys = pl.get_all_plan_keys()
        required = {"free_preview", "light", "data_sheet", "full_report", "comparison"}
        self.assertTrue(required.issubset(set(keys)), f"不足キー: {required - set(keys)}")

    def test_get_plan_labels_map_returns_dict(self):
        import src.plan_loader as pl
        m = pl.get_plan_labels_map()
        self.assertIsInstance(m, dict)
        self.assertIn("free_preview", m)
        self.assertIsInstance(m["free_preview"], str)

    def test_fallback_when_yaml_missing(self):
        """plans.yaml が存在しない場合もフォールバックで動作する"""
        import src.plan_loader as pl
        with patch.object(pl, "_PLANS_YAML_PATH", Path("/nonexistent/path/plans.yaml")):
            pl._cache.clear() if hasattr(pl, "_cache") else None
            plans = pl.load_plans()
        self.assertIsInstance(plans, dict)
        self.assertIn("free_preview", plans)


class TestIntakeInfo(unittest.TestCase):
    """job_manager の受付情報 (intake_info.json) テスト"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp)
        import job_manager as jm
        self._jm = jm
        self._original_jobs_dir = jm.JOBS_DIR
        jm.JOBS_DIR = self._tmp_path
        # テスト用ジョブ ID（実ディレクトリを作成する）
        self._job_id = "test_phase3_intake"
        (self._tmp_path / self._job_id).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._jm.JOBS_DIR = self._original_jobs_dir
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_get_intake_info_returns_defaults_when_no_file(self):
        info = self._jm.get_intake_info(self._job_id)
        self.assertIsInstance(info, dict)
        # 同意事項が全て False（安全側）
        for key in [
            "consent_analysis_reference",
            "consent_not_medical",
            "consent_not_coaching",
            "consent_accuracy_varies",
            "consent_delivery_time",
            "consent_sns_separate",
        ]:
            self.assertFalse(info[key], f"{key} のデフォルトが True になっています（安全側 = False が必要）")

    def test_update_intake_info_saves_and_reloads(self):
        self._jm.update_intake_info(
            self._job_id,
            name_or_nickname="テスト選手",
            dominant_arm="right",
            height_m=1.75,
            desired_plan="full_report",
        )
        info = self._jm.get_intake_info(self._job_id)
        self.assertEqual(info["name_or_nickname"], "テスト選手")
        self.assertEqual(info["dominant_arm"], "right")
        self.assertAlmostEqual(float(info["height_m"]), 1.75)
        self.assertEqual(info["desired_plan"], "full_report")

    def test_update_intake_info_preserves_created_at(self):
        self._jm.update_intake_info(self._job_id, name_or_nickname="First")
        info1 = self._jm.get_intake_info(self._job_id)
        created1 = info1["created_at"]
        self._jm.update_intake_info(self._job_id, name_or_nickname="Second")
        info2 = self._jm.get_intake_info(self._job_id)
        self.assertEqual(info2["created_at"], created1, "created_at が更新時に変わってしまっています")

    def test_get_intake_info_fallback_on_corrupted_file(self):
        path = self._tmp_path / self._job_id / "intake_info.json"
        path.write_text("{ invalid json }", encoding="utf-8")
        info = self._jm.get_intake_info(self._job_id)
        self.assertIsInstance(info, dict)
        # 壊れたファイルでもデフォルト値が返る
        self.assertIn("desired_plan", info)
        self.assertFalse(info["consent_analysis_reference"])

    def test_get_intake_info_merges_missing_fields(self):
        """古いジョブに新フィールドが存在しなくてもデフォルト値でマージされる"""
        path = self._tmp_path / self._job_id / "intake_info.json"
        # 古いジョブデータ（フィールドが少ない）
        old_data = {"name_or_nickname": "古いデータ"}
        path.write_text(json.dumps(old_data, ensure_ascii=False), encoding="utf-8")
        info = self._jm.get_intake_info(self._job_id)
        self.assertEqual(info["name_or_nickname"], "古いデータ")
        self.assertIn("consent_analysis_reference", info)
        self.assertFalse(info["consent_analysis_reference"])


class TestDeliveryChecklist(unittest.TestCase):
    """job_manager の納品前チェックリスト (delivery_checklist.json) テスト"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp)
        import job_manager as jm
        self._jm = jm
        self._original_jobs_dir = jm.JOBS_DIR
        jm.JOBS_DIR = self._tmp_path
        self._job_id = "test_phase3_checklist"
        (self._tmp_path / self._job_id).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._jm.JOBS_DIR = self._original_jobs_dir
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_get_delivery_checklist_returns_defaults_when_no_file(self):
        chk = self._jm.get_delivery_checklist(self._job_id)
        self.assertIsInstance(chk, dict)
        # 全チェック項目が False のデフォルト
        for key in [
            "chk_intake_confirmed",
            "chk_pdf_generated",
            "chk_zip_generated",
            "chk_delivery_message_ready",
        ]:
            self.assertFalse(chk[key], f"{key} のデフォルトが True になっています")

    def test_update_delivery_checklist_saves_and_reloads(self):
        self._jm.update_delivery_checklist(
            self._job_id,
            chk_intake_confirmed=True,
            chk_pdf_generated=True,
        )
        chk = self._jm.get_delivery_checklist(self._job_id)
        self.assertTrue(chk["chk_intake_confirmed"])
        self.assertTrue(chk["chk_pdf_generated"])
        self.assertFalse(chk["chk_zip_generated"])  # 未設定は False のまま

    def test_update_delivery_checklist_has_updated_at(self):
        self._jm.update_delivery_checklist(self._job_id, chk_plan_matches_deliverables=True)
        chk = self._jm.get_delivery_checklist(self._job_id)
        self.assertIn("updated_at", chk)
        self.assertIsNotNone(chk["updated_at"])
        self.assertGreater(len(chk["updated_at"]), 0)

    def test_get_delivery_checklist_fallback_on_corrupted_file(self):
        path = self._tmp_path / self._job_id / "delivery_checklist.json"
        path.write_text("not json", encoding="utf-8")
        chk = self._jm.get_delivery_checklist(self._job_id)
        self.assertIsInstance(chk, dict)
        self.assertIn("chk_intake_confirmed", chk)

    def test_get_delivery_checklist_merges_missing_keys(self):
        """古いチェックリストに新しいキーがなくてもマージされる"""
        path = self._tmp_path / self._job_id / "delivery_checklist.json"
        old_data = {"chk_pdf_generated": True}
        path.write_text(json.dumps(old_data), encoding="utf-8")
        chk = self._jm.get_delivery_checklist(self._job_id)
        self.assertTrue(chk["chk_pdf_generated"])
        self.assertFalse(chk.get("chk_delivery_message_ready", False))


class TestCSVImportHelpers(unittest.TestCase):
    """CSVインポートのヘルパーロジックのテスト"""

    def test_height_cm_to_m_conversion(self):
        """身長 cm → m の変換ロジック確認"""
        raw = "175"
        val = float(str(raw).replace("cm", "").replace("m", "").strip())
        if val > 10:
            val = round(val / 100.0, 2)
        self.assertAlmostEqual(val, 1.75)

    def test_height_already_in_m(self):
        """身長がすでに m 単位の場合は変換しない"""
        raw = "1.75"
        val = float(str(raw).replace("cm", "").replace("m", "").strip())
        if val > 10:
            val = round(val / 100.0, 2)
        self.assertAlmostEqual(val, 1.75)

    def test_video_count_integer_conversion(self):
        """動画本数が文字列の場合も int に変換できる"""
        raw = "3"
        val = int(raw)
        self.assertEqual(val, 3)

    def test_unexpected_column_does_not_crash(self):
        """未知の列名をスキップしてもクラッシュしない"""
        _intake_fields = {
            "name_or_nickname", "contact", "age_group", "dominant_arm",
            "height_m", "focus_main", "desired_plan",
        }
        _skip_label = "(skip)"
        # 未知列のマッピングは skip
        _mapping = {"未知列A": _skip_label, "名前またはニックネーム": "name_or_nickname"}
        result: dict = {}
        for col_name, field_k in _mapping.items():
            if field_k == _skip_label:
                continue
            result[field_k] = f"value_of_{col_name}"
        self.assertNotIn("未知列A", result)
        self.assertIn("name_or_nickname", result)


if __name__ == "__main__":
    unittest.main()
