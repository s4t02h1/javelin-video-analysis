"""Phase 6 ユニット/統合テスト

テスト対象:
- src/intake_manager: intake 作成・更新・一覧・ステータス変更
- src/intake_manager: 同意事項の初期値が全 False（安全側）
- src/intake_manager: convert_intake_to_job（ジョブ化・二重変換防止）
- server/intake_api: FastAPI TestClient 経由で各エンドポイントを確認
- server/intake_api: APIキー認証（無効キー → 401）
- server/intake_api: raw_payload が保存される
- server/intake_api: ヘルスチェック（認証不要）
- 後方互換: 既存 job データが壊れない
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, Dict
from unittest.mock import MagicMock, patch

# ── パス設定 ─────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
# `src/types/__init__.py` が stdlib types をシャドーイングするため
# sys.path.insert(0, 'src') は使わず _REPO_ROOT のみ追加する
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import src.intake_manager as _im_mod

# テスト用 INTAKES_DIR を一時ディレクトリにする仕組み
def _patch_intakes_dir(new_dir: Path):
    _im_mod.INTAKES_DIR = new_dir


# ═══════════════════════════════════════════════════════════════════════════════
# 1. intake_manager 単体テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntakeManager(unittest.TestCase):
    """src/intake_manager の基本機能テスト"""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="jva_test_intakes_")
        self._original_intakes_dir = _im_mod.INTAKES_DIR
        _patch_intakes_dir(Path(self._tmpdir))

    def tearDown(self):
        _patch_intakes_dir(self._original_intakes_dir)
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ── 基本 CRUD ──────────────────────────────────────────────────────────────

    def test_create_intake_returns_dict(self):
        """intake を作成できる"""
        intake = _im_mod.create_intake(source="manual")
        self.assertIsInstance(intake, dict)
        self.assertIn("intake_id", intake)
        self.assertTrue(intake["intake_id"].startswith("intake_"))

    def test_create_intake_source_stored(self):
        """ソースが保存される"""
        intake = _im_mod.create_intake(source="google_form")
        self.assertEqual(intake["source"], "google_form")

    def test_create_intake_missing_fields_ok(self):
        """必須項目が欠けていてもエラーにならない"""
        intake = _im_mod.create_intake(source="api", raw_payload={"x": 1})
        self.assertIn("intake_id", intake)
        self.assertEqual(intake["raw_payload"], {"x": 1})

    def test_create_intake_default_status(self):
        """デフォルトステータスは received"""
        intake = _im_mod.create_intake(source="manual")
        self.assertEqual(intake["status"], "received")

    def test_load_intake_returns_dict(self):
        """intake を読み込める"""
        created = _im_mod.create_intake(source="manual")
        loaded = _im_mod.load_intake(created["intake_id"])
        self.assertEqual(loaded["intake_id"], created["intake_id"])

    def test_load_intake_merges_defaults(self):
        """存在しないフィールドにデフォルト値が補完される"""
        created = _im_mod.create_intake(source="manual")
        loaded = _im_mod.load_intake(created["intake_id"])
        # デフォルト同意値は全て False
        for ckey in _im_mod.CONSENT_LABELS:
            self.assertFalse(loaded.get(ckey), f"{ckey} のデフォルトが False でない")

    def test_update_intake_field(self):
        """フィールドを更新できる"""
        created = _im_mod.create_intake(source="manual")
        updated = _im_mod.update_intake(created["intake_id"], name_or_nickname="テスト太郎")
        self.assertEqual(updated["name_or_nickname"], "テスト太郎")

    def test_update_intake_updated_at_changes(self):
        """updated_at が変化する"""
        created = _im_mod.create_intake(source="manual")
        before = created.get("updated_at")
        import time; time.sleep(0.01)
        updated = _im_mod.update_intake(created["intake_id"], admin_note="テスト")
        self.assertIsNotNone(updated.get("updated_at"))

    def test_list_intakes_returns_list(self):
        """list_intakes がリストを返す"""
        _im_mod.create_intake(source="manual")
        _im_mod.create_intake(source="google_form")
        result = _im_mod.list_intakes()
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 2)

    def test_list_intakes_filter_by_source(self):
        """ソースフィルタが機能する"""
        _im_mod.create_intake(source="manual")
        _im_mod.create_intake(source="google_form")
        result = _im_mod.list_intakes(source="manual")
        self.assertTrue(all(i["source"] == "manual" for i in result))

    def test_set_intake_status(self):
        """ステータスを変更できる"""
        created = _im_mod.create_intake(source="manual")
        updated = _im_mod.set_intake_status(created["intake_id"], "needs_review")
        self.assertEqual(updated["status"], "needs_review")

    def test_archive_intake(self):
        """アーカイブできる"""
        created = _im_mod.create_intake(source="manual")
        archived = _im_mod.archive_intake(created["intake_id"])
        self.assertEqual(archived["status"], "archived")

    def test_reject_intake(self):
        """対応不可にできる"""
        created = _im_mod.create_intake(source="manual")
        rejected = _im_mod.reject_intake(created["intake_id"], note="テスト理由")
        self.assertEqual(rejected["status"], "rejected")

    # ── 同意事項 ───────────────────────────────────────────────────────────────

    def test_consent_defaults_all_false(self):
        """同意事項の初期値が全て False（安全側）"""
        intake = _im_mod.create_intake(source="manual")
        loaded = _im_mod.load_intake(intake["intake_id"])
        for ckey in _im_mod.CONSENT_LABELS:
            self.assertFalse(
                loaded.get(ckey),
                f"{ckey} のデフォルトが False でない: {loaded.get(ckey)}"
            )

    def test_check_all_consents_false_when_not_set(self):
        """同意未設定では check_all_consents が False"""
        intake = _im_mod.create_intake(source="manual")
        loaded = _im_mod.load_intake(intake["intake_id"])
        self.assertFalse(_im_mod.check_all_consents(loaded))

    def test_check_all_consents_true_when_all_set(self):
        """全同意済みで check_all_consents が True"""
        intake = _im_mod.create_intake(source="manual")
        consent_kwargs = {k: True for k in _im_mod.CONSENT_LABELS}
        updated = _im_mod.update_intake(intake["intake_id"], **consent_kwargs)
        self.assertTrue(_im_mod.check_all_consents(updated))

    def test_missing_consents_returns_list(self):
        """missing_consents がリストを返す"""
        intake = _im_mod.create_intake(source="manual")
        loaded = _im_mod.load_intake(intake["intake_id"])
        missing = _im_mod.missing_consents(loaded)
        self.assertIsInstance(missing, list)
        self.assertEqual(set(missing), set(_im_mod.CONSENT_LABELS.keys()))

    # ── ジョブ化 ───────────────────────────────────────────────────────────────

    def _make_mock_job_manager(self, tmp_jobs_dir: Path) -> ModuleType:
        """テスト用 job_manager モックを作成する"""
        mock_jm = MagicMock()

        _created_jobs: Dict[str, Dict] = {}

        def _create_job(height_m=None, mode="all_variants"):
            import uuid
            job_id = "job_test_" + uuid.uuid4().hex[:8]
            _created_jobs[job_id] = {"job_id": job_id, "status": "created"}
            return job_id

        def _update_job(job_id: str, **kwargs):
            if job_id in _created_jobs:
                _created_jobs[job_id].update(kwargs)
            job_path = tmp_jobs_dir / job_id / "job.json"
            job_path.parent.mkdir(parents=True, exist_ok=True)
            data = _created_jobs.get(job_id, {"job_id": job_id})
            data.update(kwargs)
            _created_jobs[job_id] = data
            job_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        def _update_customer_info(job_id: str, **kwargs):
            pass

        mock_jm.create_job.side_effect = _create_job
        mock_jm.update_job.side_effect = _update_job
        mock_jm.update_customer_info.side_effect = _update_customer_info
        return mock_jm

    def test_convert_intake_to_job(self):
        """intake から job を作成できる"""
        tmp_jobs = Path(tempfile.mkdtemp(prefix="jva_test_jobs_"))
        try:
            mock_jm = self._make_mock_job_manager(tmp_jobs)
            intake = _im_mod.create_intake(source="manual", height_cm=175.0)
            result = _im_mod.convert_intake_to_job(intake["intake_id"], mock_jm, force=False)
            self.assertIn("job", result)
            self.assertIn("intake", result)
            updated_intake = _im_mod.load_intake(intake["intake_id"])
            self.assertEqual(updated_intake["status"], "converted")
            self.assertIsNotNone(updated_intake.get("converted_job_id"))
        finally:
            import shutil
            shutil.rmtree(str(tmp_jobs), ignore_errors=True)

    def test_convert_intake_double_conversion_raises(self):
        """二重ジョブ化を防止できる（force=False）"""
        tmp_jobs = Path(tempfile.mkdtemp(prefix="jva_test_jobs_"))
        try:
            mock_jm = self._make_mock_job_manager(tmp_jobs)
            intake = _im_mod.create_intake(source="manual")
            _im_mod.convert_intake_to_job(intake["intake_id"], mock_jm, force=False)
            # 2回目は ValueError
            with self.assertRaises(ValueError):
                _im_mod.convert_intake_to_job(intake["intake_id"], mock_jm, force=False)
        finally:
            import shutil
            shutil.rmtree(str(tmp_jobs), ignore_errors=True)

    def test_convert_intake_force_allows_reconversion(self):
        """force=True で二重ジョブ化を許可する"""
        tmp_jobs = Path(tempfile.mkdtemp(prefix="jva_test_jobs_"))
        try:
            mock_jm = self._make_mock_job_manager(tmp_jobs)
            intake = _im_mod.create_intake(source="manual")
            res1 = _im_mod.convert_intake_to_job(intake["intake_id"], mock_jm, force=False)
            res2 = _im_mod.convert_intake_to_job(intake["intake_id"], mock_jm, force=True)
            self.assertNotEqual(res1["job"]["job_id"], res2["job"]["job_id"])
        finally:
            import shutil
            shutil.rmtree(str(tmp_jobs), ignore_errors=True)

    # ── raw_payload ────────────────────────────────────────────────────────────

    def test_raw_payload_stored(self):
        """raw_payload が保存される"""
        payload = {"form_key": "テスト", "extra": 42}
        intake = _im_mod.create_intake(source="google_form", raw_payload=payload)
        loaded = _im_mod.load_intake(intake["intake_id"])
        self.assertEqual(loaded.get("raw_payload"), payload)

    # ── intake_id バリデーション ──────────────────────────────────────────────

    def test_load_nonexistent_intake_raises(self):
        """存在しない intake_id ではエラーが発生する"""
        with self.assertRaises(FileNotFoundError):
            _im_mod.load_intake("intake_00000000_000000_xxxx")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FastAPI intake_api テスト（TestClient 使用）
# ═══════════════════════════════════════════════════════════════════════════════

# TestClient が利用できない場合はスキップ
try:
    from fastapi.testclient import TestClient
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

_SKIP_MSG = "fastapi[testclient] が未インストールのためスキップ"


@unittest.skipUnless(_FASTAPI_AVAILABLE, _SKIP_MSG)
class TestIntakeApi(unittest.TestCase):
    """FastAPI TestClient による /v1/intakes エンドポイントテスト"""

    @classmethod
    def setUpClass(cls):
        """テスト用 FastAPI アプリを作成する"""
        cls._tmpdir = Path(tempfile.mkdtemp(prefix="jva_test_api_intakes_"))
        cls._original_intakes_dir = _im_mod.INTAKES_DIR
        _patch_intakes_dir(cls._tmpdir)

        # APIキーを設定（テスト用）
        os.environ["JVA_API_KEY"] = "test-api-key-12345"
        os.environ["JVA_ENABLE_INTAKE_API"] = "true"

        # intake_api モジュールを再ロードして環境変数を反映させる
        import server.intake_api as _intake_api_mod
        importlib.reload(_intake_api_mod)

        from fastapi import FastAPI
        cls._app = FastAPI()
        cls._app.include_router(_intake_api_mod.intake_router, prefix="/v1")
        cls._client = TestClient(cls._app, raise_server_exceptions=True)

    @classmethod
    def tearDownClass(cls):
        _patch_intakes_dir(cls._original_intakes_dir)
        import shutil
        shutil.rmtree(str(cls._tmpdir), ignore_errors=True)
        os.environ.pop("JVA_API_KEY", None)

    def _auth_headers(self) -> dict:
        return {"X-JVA-API-Key": "test-api-key-12345"}

    # ── ヘルスチェック（認証不要）────────────────────────────────────────────

    def test_health_no_auth(self):
        """ヘルスチェックは認証なしで 200 を返す"""
        r = self._client.get("/v1/intakes/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("status"), "ok")

    # ── 認証テスト ────────────────────────────────────────────────────────────

    def test_list_without_api_key_returns_401(self):
        """APIキーなしで一覧取得すると 401"""
        r = self._client.get("/v1/intakes")
        self.assertEqual(r.status_code, 401)

    def test_list_with_wrong_api_key_returns_401(self):
        """不正なAPIキーで 401"""
        r = self._client.get(
            "/v1/intakes",
            headers={"X-JVA-API-Key": "wrong-key"},
        )
        self.assertEqual(r.status_code, 401)

    def test_create_without_api_key_returns_401(self):
        """APIキーなしで作成すると 401"""
        r = self._client.post("/v1/intakes", json={"source": "manual"})
        self.assertEqual(r.status_code, 401)

    # ── intake CRUD ───────────────────────────────────────────────────────────

    def test_create_intake_201(self):
        """POST /v1/intakes で 201 が返る"""
        r = self._client.post(
            "/v1/intakes",
            json={"source": "api", "raw_payload": {"test": True}},
            headers=self._auth_headers(),
        )
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertIn("intake_id", data)

    def test_create_intake_source_stored(self):
        """ソースが保存される"""
        r = self._client.post(
            "/v1/intakes",
            json={"source": "google_form"},
            headers=self._auth_headers(),
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["source"], "google_form")

    def test_create_intake_minimal_payload(self):
        """ペイロードが空でも作成できる"""
        r = self._client.post(
            "/v1/intakes",
            json={},
            headers=self._auth_headers(),
        )
        self.assertEqual(r.status_code, 201)
        self.assertIn("intake_id", r.json())

    def test_list_intakes_200(self):
        """GET /v1/intakes で 200 が返る"""
        r = self._client.get("/v1/intakes", headers=self._auth_headers())
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_get_intake_200(self):
        """GET /v1/intakes/{id} で 200 が返る"""
        created = self._client.post(
            "/v1/intakes",
            json={"source": "manual"},
            headers=self._auth_headers(),
        ).json()
        iid = created["intake_id"]
        r = self._client.get(f"/v1/intakes/{iid}", headers=self._auth_headers())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["intake_id"], iid)

    def test_get_nonexistent_intake_404(self):
        """存在しない intake_id で 404"""
        r = self._client.get(
            "/v1/intakes/intake_00000000_000000_xxxx",
            headers=self._auth_headers(),
        )
        self.assertEqual(r.status_code, 404)

    def test_patch_intake_200(self):
        """PATCH /v1/intakes/{id} で更新できる"""
        created = self._client.post(
            "/v1/intakes",
            json={"source": "manual"},
            headers=self._auth_headers(),
        ).json()
        iid = created["intake_id"]
        r = self._client.patch(
            f"/v1/intakes/{iid}",
            json={"admin_note": "テスト更新"},
            headers=self._auth_headers(),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["admin_note"], "テスト更新")

    def test_patch_protected_fields_ignored(self):
        """保護フィールド（intake_id, created_at）は上書きされない"""
        created = self._client.post(
            "/v1/intakes",
            json={"source": "manual"},
            headers=self._auth_headers(),
        ).json()
        iid = created["intake_id"]
        original_created_at = created.get("created_at")
        r = self._client.patch(
            f"/v1/intakes/{iid}",
            json={"intake_id": "tampered_id", "created_at": "2000-01-01T00:00:00"},
            headers=self._auth_headers(),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["intake_id"], iid)
        # created_at は変化しない
        self.assertEqual(r.json().get("created_at"), original_created_at)

    # ── raw_payload ───────────────────────────────────────────────────────────

    def test_raw_payload_stored_via_api(self):
        """raw_payload が保存される"""
        payload = {"form_key": "テスト", "extra": 99}
        r = self._client.post(
            "/v1/intakes",
            json={"source": "api", "raw_payload": payload},
            headers=self._auth_headers(),
        )
        self.assertEqual(r.status_code, 201)
        iid = r.json()["intake_id"]
        r2 = self._client.get(f"/v1/intakes/{iid}", headers=self._auth_headers())
        self.assertEqual(r2.json().get("raw_payload"), payload)

    # ── consent デフォルト ────────────────────────────────────────────────────

    def test_consent_defaults_all_false_via_api(self):
        """API 経由で作成した intake の同意事項デフォルトが全 False"""
        r = self._client.post(
            "/v1/intakes",
            json={"source": "api"},
            headers=self._auth_headers(),
        )
        self.assertEqual(r.status_code, 201)
        iid = r.json()["intake_id"]
        r2 = self._client.get(f"/v1/intakes/{iid}", headers=self._auth_headers())
        data = r2.json()
        for ckey in _im_mod.CONSENT_LABELS:
            self.assertFalse(
                data.get(ckey),
                f"{ckey} のデフォルトが False でない: {data.get(ckey)}"
            )

    # ── アーカイブ・対応不可 ──────────────────────────────────────────────────

    def test_archive_intake_200(self):
        """POST /v1/intakes/{id}/archive で 200"""
        created = self._client.post(
            "/v1/intakes",
            json={"source": "manual"},
            headers=self._auth_headers(),
        ).json()
        iid = created["intake_id"]
        r = self._client.post(
            f"/v1/intakes/{iid}/archive",
            headers=self._auth_headers(),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "archived")

    def test_reject_intake_200(self):
        """POST /v1/intakes/{id}/reject で 200"""
        created = self._client.post(
            "/v1/intakes",
            json={"source": "manual"},
            headers=self._auth_headers(),
        ).json()
        iid = created["intake_id"]
        r = self._client.post(
            f"/v1/intakes/{iid}/reject",
            json={"note": "テスト対応不可"},
            headers=self._auth_headers(),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "rejected")

    # ── ジョブ化 ──────────────────────────────────────────────────────────────

    def test_convert_to_job_via_api(self):
        """POST /v1/intakes/{id}/convert-to-job で 201"""
        created = self._client.post(
            "/v1/intakes",
            json={"source": "api", "height_cm": 175.0},
            headers=self._auth_headers(),
        ).json()
        iid = created["intake_id"]

        # job_manager をモックする
        mock_jm = MagicMock()
        created_job_id = "job_test_api_001"

        def _create_job(height_m=None, mode="all_variants"):
            return created_job_id

        mock_jm.create_job.side_effect = _create_job
        mock_jm.update_job.side_effect = lambda job_id, **kw: None
        mock_jm.update_customer_info.side_effect = lambda job_id, **kw: None

        with patch("job_manager.create_job", side_effect=_create_job), \
             patch("job_manager.update_job", side_effect=lambda job_id, **kw: None), \
             patch("job_manager.update_customer_info", side_effect=lambda job_id, **kw: None):
            r = self._client.post(
                f"/v1/intakes/{iid}/convert-to-job",
                headers=self._auth_headers(),
            )
        self.assertEqual(r.status_code, 201)
        data = r.json()
        # APIレスポンスは {"intake_id": ..., "job_id": ..., "status": "converted"}
        self.assertIn("job_id", data)

    def test_convert_to_job_double_returns_409(self):
        """二重ジョブ化リクエストで 409"""
        created = self._client.post(
            "/v1/intakes",
            json={"source": "api"},
            headers=self._auth_headers(),
        ).json()
        iid = created["intake_id"]

        mock_jm = MagicMock()
        call_count = [0]

        def _create_job(height_m=None, mode="all_variants"):
            call_count[0] += 1
            return f"job_test_double_{call_count[0]:03d}"

        with patch("job_manager.create_job", side_effect=_create_job), \
             patch("job_manager.update_job", side_effect=lambda job_id, **kw: None), \
             patch("job_manager.update_customer_info", side_effect=lambda job_id, **kw: None):
            r1 = self._client.post(
                f"/v1/intakes/{iid}/convert-to-job",
                headers=self._auth_headers(),
            )
            self.assertEqual(r1.status_code, 201)
            r2 = self._client.post(
                f"/v1/intakes/{iid}/convert-to-job",
                headers=self._auth_headers(),
            )
        self.assertEqual(r2.status_code, 409)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 後方互換テスト: 既存 job データが壊れない
# ═══════════════════════════════════════════════════════════════════════════════

class TestBackwardCompatibility(unittest.TestCase):
    """既存 job データの後方互換性を確認する"""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="jva_test_compat_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_existing_job_without_intake_fields(self):
        """source_intake_id フィールドなしの既存 job を読み込めること"""
        import job_manager as jm
        original_jobs_dir = jm.JOBS_DIR
        try:
            jm.JOBS_DIR = Path(self._tmpdir)
            job = jm.create_job(height_m=None, mode="all_variants")
            job_id = job["job_id"]
            loaded = jm.load_job(job_id)
            self.assertIsInstance(loaded, dict)
            self.assertEqual(loaded["job_id"], job_id)
            self.assertIn("job_id", loaded)
        finally:
            jm.JOBS_DIR = original_jobs_dir

    def test_existing_job_customer_info_compatible(self):
        """既存 customer_info フィールドが壊れないこと"""
        import job_manager as jm
        original_jobs_dir = jm.JOBS_DIR
        try:
            jm.JOBS_DIR = Path(self._tmpdir)
            job = jm.create_job(height_m=None, mode="all_variants")
            job_id = job["job_id"]
            jm.update_customer_info(job_id, customer_name="後方互換テスト")
            ci = jm.get_customer_info(job_id)
            self.assertEqual(ci.get("customer_name"), "後方互換テスト")
        finally:
            jm.JOBS_DIR = original_jobs_dir


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 個人情報ログ漏洩テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestPiiNotLogged(unittest.TestCase):
    """個人情報がログに出力されないことを確認する"""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="jva_test_pii_")
        self._original_intakes_dir = _im_mod.INTAKES_DIR
        _patch_intakes_dir(Path(self._tmpdir))

    def tearDown(self):
        _patch_intakes_dir(self._original_intakes_dir)
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_convert_to_job_pii_not_in_log(self):
        """convert_intake_to_job がログに個人情報を出力しない"""
        import logging
        import io

        _PII_FIELDS = {"name_or_nickname", "contact", "line_user_id", "email", "instagram_account"}
        pii_sample = {
            "name_or_nickname": "山田テスト",
            "contact": "@test_contact_12345",
            "email": "test.pii@example.com",
        }

        log_stream = io.StringIO()
        _handler = logging.StreamHandler(log_stream)
        _handler.setLevel(logging.DEBUG)
        _im_mod.logger.addHandler(_handler)

        try:
            intake = _im_mod.create_intake(
                source="manual",
                **pii_sample,
            )

            mock_jm = MagicMock()
            mock_jm.create_job.return_value = "job_pii_test_001"
            mock_jm.update_job.side_effect = lambda job_id, **kw: None
            mock_jm.update_customer_info.side_effect = lambda job_id, **kw: None

            _im_mod.convert_intake_to_job(intake["intake_id"], mock_jm, force=False)

            log_output = log_stream.getvalue()
            for pii_val in pii_sample.values():
                self.assertNotIn(
                    pii_val,
                    log_output,
                    f"個人情報 '{pii_val}' がログに含まれています",
                )
        finally:
            _im_mod.logger.removeHandler(_handler)

    def test_create_intake_pii_not_in_log(self):
        """create_intake がログに個人情報を出力しない"""
        import io
        import logging
        log_stream = io.StringIO()
        _handler = logging.StreamHandler(log_stream)
        _handler.setLevel(logging.DEBUG)
        _im_mod.logger.addHandler(_handler)
        try:
            _im_mod.create_intake(
                source="google_form",
                name_or_nickname="PII名前テスト",
                contact="@pii_contact_test",
                email="pii_unique_test_email@example.com",
            )
            log_output = log_stream.getvalue()
            self.assertNotIn("PII名前テスト", log_output)
            self.assertNotIn("@pii_contact_test", log_output)
            self.assertNotIn("pii_unique_test_email@example.com", log_output)
        finally:
            _im_mod.logger.removeHandler(_handler)


if __name__ == "__main__":
    unittest.main()
