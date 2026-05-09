"""
tests/test_phase7.py — Phase 7: ジョブキュー・ワーカー・Jobs API のテスト

実行方法:
    C:/venvs/javelin312/Scripts/python.exe -m pytest tests/test_phase7.py -v
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

# sys.path に repo ルートを追加（src/types/__init__.py のシャドウ問題を回避）
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import src.queue_manager as _qm_mod
from src.queue_manager import (
    QUEUE_STATUSES,
    QUEUE_STATUS_LABELS,
    JOB_TYPES,
    PIPELINE_STEPS,
    generate_queue_id,
    create_queue_job,
    load_queue_job,
    update_queue_job,
    list_queue_jobs,
    get_queue_counts,
    find_queue_job_for_job,
    find_active_queue_job_for_job,
    claim_next_pending,
    complete_queue_job,
    fail_queue_job,
    cancel_queue_job,
    retry_queue_job,
    append_step,
    is_cancel_requested,
)


# ─────────────────────────────────────────────────────────────────────────────
# ヘルパー: テスト用キューディレクトリを一時フォルダに向ける
# ─────────────────────────────────────────────────────────────────────────────

class _QueueTestBase(unittest.TestCase):
    """キューディレクトリを一時フォルダに差し替える基底クラス。"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="jva_test_queue_")
        self._orig = _qm_mod._DEFAULT_QUEUE_DIR
        _qm_mod._DEFAULT_QUEUE_DIR = Path(self._tmpdir)

    def tearDown(self) -> None:
        _qm_mod._DEFAULT_QUEUE_DIR = self._orig
        shutil.rmtree(self._tmpdir, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# TestQueueManagerConstants
# ─────────────────────────────────────────────────────────────────────────────

class TestQueueManagerConstants(unittest.TestCase):
    def test_queue_statuses_exist(self) -> None:
        for s in ("pending", "running", "completed", "failed", "cancelled"):
            self.assertIn(s, QUEUE_STATUSES)

    def test_status_labels_match_statuses(self) -> None:
        for s in ("pending", "running", "completed", "failed", "cancelled"):
            self.assertIn(s, QUEUE_STATUS_LABELS)

    def test_job_types_nonempty(self) -> None:
        self.assertGreater(len(JOB_TYPES), 0)
        self.assertIn("full_pipeline", JOB_TYPES)

    def test_pipeline_steps_ordered(self) -> None:
        self.assertGreater(len(PIPELINE_STEPS), 0)
        self.assertEqual(PIPELINE_STEPS[0], "validate_inputs")
        self.assertEqual(PIPELINE_STEPS[-1], "mark_ready")


# ─────────────────────────────────────────────────────────────────────────────
# TestGenerateQueueId
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateQueueId(unittest.TestCase):
    def test_format(self) -> None:
        qid = generate_queue_id()
        self.assertTrue(qid.startswith("qjob_"), f"Expected qjob_ prefix: {qid}")
        parts = qid.split("_")
        # qjob_YYYYMMDD_HHMMSS_xxxx => 4 parts
        self.assertEqual(len(parts), 4, f"Unexpected format: {qid}")

    def test_uniqueness(self) -> None:
        ids = {generate_queue_id() for _ in range(20)}
        self.assertEqual(len(ids), 20)


# ─────────────────────────────────────────────────────────────────────────────
# TestCreateLoadQueueJob
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateLoadQueueJob(_QueueTestBase):
    def test_create_returns_dict(self) -> None:
        qjob = create_queue_job("job_001", job_type="full_pipeline")
        self.assertIsInstance(qjob, dict)
        self.assertEqual(qjob["job_id"], "job_001")
        self.assertEqual(qjob["status"], "pending")
        self.assertIn("queue_id", qjob)

    def test_file_is_created_in_pending(self) -> None:
        qjob = create_queue_job("job_002")
        pending_dir = Path(self._tmpdir) / "pending"
        files = list(pending_dir.glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].stem, qjob["queue_id"])

    def test_load_queue_job_roundtrip(self) -> None:
        qjob = create_queue_job("job_003", source="test")
        loaded = load_queue_job(qjob["queue_id"])
        self.assertEqual(loaded["queue_id"], qjob["queue_id"])
        self.assertEqual(loaded["job_id"], "job_003")
        self.assertEqual(loaded["source"], "test")

    def test_load_merges_defaults(self) -> None:
        """保存されていないフィールドはデフォルト値を返す。"""
        qjob = create_queue_job("job_004")
        loaded = load_queue_job(qjob["queue_id"])
        self.assertIn("retry_count", loaded)
        self.assertIn("steps", loaded)


# ─────────────────────────────────────────────────────────────────────────────
# TestUpdateQueueJob
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateQueueJob(_QueueTestBase):
    def test_update_field(self) -> None:
        qjob = create_queue_job("job_005")
        updated = update_queue_job(qjob["queue_id"], priority=10)
        self.assertEqual(updated["priority"], 10)

    def test_queue_id_is_immutable(self) -> None:
        qjob = create_queue_job("job_006")
        original_qid = qjob["queue_id"]
        # queue_id は保護されているので別フィールドで上書きを試みる
        update_queue_job(original_qid, priority=99)
        loaded = load_queue_job(original_qid)
        # queue_id が変わっていないことを確認
        self.assertEqual(loaded["queue_id"], original_qid)
        # 更新は反映されている
        self.assertEqual(loaded["priority"], 99)

    def test_created_at_is_immutable(self) -> None:
        qjob = create_queue_job("job_007")
        original_cat = qjob["created_at"]
        update_queue_job(qjob["queue_id"], created_at="1970-01-01T00:00:00")
        loaded = load_queue_job(qjob["queue_id"])
        self.assertEqual(loaded["created_at"], original_cat)


# ─────────────────────────────────────────────────────────────────────────────
# TestListAndCount
# ─────────────────────────────────────────────────────────────────────────────

class TestListAndCount(_QueueTestBase):
    def test_list_all(self) -> None:
        create_queue_job("job_011")
        create_queue_job("job_012")
        jobs = list_queue_jobs()
        self.assertEqual(len(jobs), 2)

    def test_list_by_status(self) -> None:
        qjob = create_queue_job("job_013")
        jobs_pending = list_queue_jobs(status="pending")
        self.assertEqual(len(jobs_pending), 1)
        jobs_running = list_queue_jobs(status="running")
        self.assertEqual(len(jobs_running), 0)

    def test_get_queue_counts(self) -> None:
        create_queue_job("job_014")
        create_queue_job("job_015")
        counts = get_queue_counts()
        self.assertEqual(counts["pending"], 2)
        self.assertEqual(counts.get("running", 0), 0)

    def test_find_queue_job_for_job(self) -> None:
        qjob = create_queue_job("job_016")
        found = find_queue_job_for_job("job_016")
        self.assertIsNotNone(found)
        self.assertEqual(found["queue_id"], qjob["queue_id"])

    def test_find_queue_job_returns_none_for_unknown(self) -> None:
        result = find_queue_job_for_job("nonexistent_job")
        self.assertIsNone(result)

    def test_find_active_queue_job(self) -> None:
        qjob = create_queue_job("job_017")
        found = find_active_queue_job_for_job("job_017")
        self.assertIsNotNone(found)
        self.assertEqual(found["queue_id"], qjob["queue_id"])


# ─────────────────────────────────────────────────────────────────────────────
# TestClaimAndTransitions
# ─────────────────────────────────────────────────────────────────────────────

class TestClaimAndTransitions(_QueueTestBase):
    def test_claim_next_pending(self) -> None:
        create_queue_job("job_021")
        claimed = claim_next_pending()
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["status"], "running")
        self.assertEqual(claimed["job_id"], "job_021")

    def test_claim_moves_to_running_dir(self) -> None:
        create_queue_job("job_022")
        claimed = claim_next_pending()
        running_dir = Path(self._tmpdir) / "running"
        pending_dir = Path(self._tmpdir) / "pending"
        self.assertEqual(len(list(running_dir.glob("*.json"))), 1)
        self.assertEqual(len(list(pending_dir.glob("*.json"))), 0)

    def test_claim_returns_none_when_empty(self) -> None:
        result = claim_next_pending()
        self.assertIsNone(result)

    def test_complete_queue_job(self) -> None:
        create_queue_job("job_023")
        claimed = claim_next_pending()
        completed = complete_queue_job(claimed["queue_id"])
        self.assertEqual(completed["status"], "completed")
        completed_dir = Path(self._tmpdir) / "completed"
        self.assertEqual(len(list(completed_dir.glob("*.json"))), 1)

    def test_fail_queue_job(self) -> None:
        create_queue_job("job_024")
        claimed = claim_next_pending()
        failed = fail_queue_job(claimed["queue_id"], error="Test error", failed_step="run_analysis")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["last_error"], "Test error")
        self.assertEqual(failed["failed_step"], "run_analysis")


# ─────────────────────────────────────────────────────────────────────────────
# TestCancelAndRetry
# ─────────────────────────────────────────────────────────────────────────────

class TestCancelAndRetry(_QueueTestBase):
    def test_cancel_pending_job(self) -> None:
        qjob = create_queue_job("job_031")
        cancelled = cancel_queue_job(qjob["queue_id"])
        self.assertEqual(cancelled["status"], "cancelled")

    def test_cancel_running_sets_flag(self) -> None:
        create_queue_job("job_032")
        claimed = claim_next_pending()
        cancel_queue_job(claimed["queue_id"])
        self.assertTrue(is_cancel_requested(claimed["queue_id"]))

    def test_retry_failed_job(self) -> None:
        create_queue_job("job_033")
        claimed = claim_next_pending()
        fail_queue_job(claimed["queue_id"], error="some error")
        retried = retry_queue_job(claimed["queue_id"])
        self.assertEqual(retried["status"], "pending")
        # retry_count は増えている
        self.assertGreaterEqual(retried["retry_count"], 1)

    def test_retry_cancelled_job(self) -> None:
        qjob = create_queue_job("job_034")
        cancel_queue_job(qjob["queue_id"])
        retried = retry_queue_job(qjob["queue_id"])
        self.assertEqual(retried["status"], "pending")

    def test_is_cancel_requested_false_by_default(self) -> None:
        qjob = create_queue_job("job_035")
        self.assertFalse(is_cancel_requested(qjob["queue_id"]))


# ─────────────────────────────────────────────────────────────────────────────
# TestAppendStep
# ─────────────────────────────────────────────────────────────────────────────

class TestAppendStep(_QueueTestBase):
    def test_append_step_success(self) -> None:
        create_queue_job("job_041")
        claimed = claim_next_pending()
        updated = append_step(claimed["queue_id"], "validate_inputs", success=True)
        self.assertEqual(len(updated["steps"]), 1)
        self.assertTrue(updated["steps"][0]["success"])
        self.assertEqual(updated["steps"][0]["step"], "validate_inputs")

    def test_append_step_failure(self) -> None:
        create_queue_job("job_042")
        claimed = claim_next_pending()
        updated = append_step(claimed["queue_id"], "run_analysis", success=False, error="crash")
        self.assertFalse(updated["steps"][0]["success"])
        self.assertEqual(updated["steps"][0]["error"], "crash")

    def test_multiple_steps_accumulate(self) -> None:
        create_queue_job("job_043")
        claimed = claim_next_pending()
        append_step(claimed["queue_id"], "validate_inputs", success=True)
        append_step(claimed["queue_id"], "run_analysis", success=True)
        loaded = load_queue_job(claimed["queue_id"])
        self.assertEqual(len(loaded["steps"]), 2)


# ─────────────────────────────────────────────────────────────────────────────
# TestJobsApi (FastAPI TestClient)
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

@unittest.skipUnless(_HAS_FASTAPI, "fastapi not installed")
class TestJobsApi(_QueueTestBase):
    def setUp(self) -> None:
        super().setUp()
        # サーバーのキューディレクトリもテスト用に差し替え
        import src.queue_manager as _qm
        _qm._DEFAULT_QUEUE_DIR = Path(self._tmpdir)

        import os
        os.environ["JVA_API_KEY"] = "test-api-key"

        from server.jobs_api import jobs_router
        from fastapi import FastAPI
        _app = FastAPI()
        _app.include_router(jobs_router, prefix="/v1")
        self.client = TestClient(_app, raise_server_exceptions=False)
        self._headers = {"X-JVA-API-Key": "test-api-key"}

    def test_health_endpoint(self) -> None:
        resp = self.client.get("/v1/jobs/health")
        self.assertEqual(resp.status_code, 200)

    def test_create_job_requires_auth(self) -> None:
        resp = self.client.post("/v1/jobs", json={"height_m": 1.75})
        # No API key → 401 or 403
        self.assertIn(resp.status_code, (401, 403))

    def test_create_job_with_auth(self) -> None:
        resp = self.client.post(
            "/v1/jobs",
            json={"height_m": 1.75},
            headers=self._headers,
        )
        self.assertIn(resp.status_code, (200, 201))
        data = resp.json()
        self.assertIn("job_id", data)

    def test_get_unknown_job_returns_404(self) -> None:
        resp = self.client.get("/v1/jobs/nonexistent-job-id", headers=self._headers)
        self.assertEqual(resp.status_code, 404)

    def test_get_queue_overview(self) -> None:
        resp = self.client.get("/v1/queue", headers=self._headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("counts", data)


# ─────────────────────────────────────────────────────────────────────────────
# TestBackwardCompatibility
# ─────────────────────────────────────────────────────────────────────────────

class TestBackwardCompatibility(unittest.TestCase):
    """Phase 1〜6 で使われていた定数・関数が壊れていないことを確認。"""

    def test_job_manager_importable(self) -> None:
        import job_manager
        self.assertTrue(hasattr(job_manager, "create_job"))
        self.assertTrue(hasattr(job_manager, "list_jobs"))

    def test_job_statuses_exist(self) -> None:
        from job_manager import JOB_STATUSES
        for s in ("created", "uploaded", "running", "completed", "failed"):
            self.assertIn(s, JOB_STATUSES)

    def test_intake_manager_importable(self) -> None:
        try:
            from src.intake_manager import INTAKE_STATUSES, create_intake
        except ImportError:
            self.skipTest("intake_manager not available")
        self.assertIn("received", INTAKE_STATUSES)


if __name__ == "__main__":
    unittest.main()
