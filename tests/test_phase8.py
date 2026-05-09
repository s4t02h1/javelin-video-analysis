"""
tests/test_phase8.py — Phase 8: Docker 化・デプロイ準備・本番運用基盤のテスト

テスト対象:
    - src/config.py  : 環境変数の一元管理
    - src/logging_config.py : ログ設定
    - server/app.py  : /health, /ready エンドポイント
"""
from __future__ import annotations

import importlib
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

# ── パス設定 ──────────────────────────────────────────────────────────────────
# src/types/__init__.py が stdlib types をシャドウするため sys.path.insert(0, 'src') 禁止
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# テスト間で汚染しないよう一元管理するキーリスト
_TRACKED_ENV_KEYS = [
    "JVA_ENV", "JVA_APP_NAME", "JVA_DATA_DIR", "JVA_JOBS_DIR", "JVA_QUEUE_DIR",
    "JVA_LOG_DIR", "JVA_UPLOAD_DIR", "JVA_OUTPUT_DIR", "JVA_COMPARISONS_DIR",
    "JVA_API_KEY", "JVA_BUCKET", "JVA_DEBUG",
    "JVA_ENABLE_INTAKE_API", "JVA_ENABLE_JOBS_API",
    "JVA_WORKER_POLL_INTERVAL_SECONDS", "JVA_WORKER_MAX_RETRIES",
    "JVA_QUEUE_BACKEND", "JVA_ADMIN_PORT", "JVA_ADMIN_PASSWORD",
]


# ─────────────────────────────────────────────────────────────────────────────
class TestConfig(unittest.TestCase):
    """src/config.py のテスト"""

    def setUp(self) -> None:
        """テストごとに config モジュールをリロードして環境変数の影響を隔離する。"""
        # 全追跡キーを退避してから削除（前テストの残留を防ぐ）
        self._saved_env: dict[str, str] = {}
        for key in _TRACKED_ENV_KEYS:
            if key in os.environ:
                self._saved_env[key] = os.environ.pop(key)

        # モジュールをリロードして環境変数の変更を反映させる
        import src.config as _cfg_mod
        importlib.reload(_cfg_mod)
        from src.config import cfg
        self.cfg = cfg

    def tearDown(self) -> None:
        """テスト後に環境変数を完全に元通りにする。"""
        # テスト中に設定された全追跡キーを削除してからオリジナルを復元
        for key in _TRACKED_ENV_KEYS:
            os.environ.pop(key, None)
        for key, val in self._saved_env.items():
            os.environ[key] = val

    # ── デフォルト値 ──────────────────────────────────────────────────────────

    def test_default_env_is_local(self) -> None:
        self.assertEqual(self.cfg.ENV, "local")

    def test_default_debug_is_false(self) -> None:
        self.assertFalse(self.cfg.DEBUG)

    def test_default_app_name(self) -> None:
        self.assertEqual(self.cfg.APP_NAME, "javelin-video-analysis")

    def test_default_data_dir_is_repo_relative(self) -> None:
        """JVA_DATA_DIR 未設定時は REPO_ROOT/data になる。"""
        expected = _REPO_ROOT / "data"
        self.assertEqual(self.cfg.DATA_DIR, expected)

    def test_default_log_dir(self) -> None:
        expected = _REPO_ROOT / "logs"
        self.assertEqual(self.cfg.LOG_DIR, expected)

    def test_default_upload_dir(self) -> None:
        expected = _REPO_ROOT / "uploads"
        self.assertEqual(self.cfg.UPLOAD_DIR, expected)

    def test_default_queue_dir(self) -> None:
        expected = _REPO_ROOT / "data" / "queue"
        self.assertEqual(self.cfg.QUEUE_DIR, expected)

    def test_default_worker_poll_interval(self) -> None:
        self.assertEqual(self.cfg.WORKER_POLL_INTERVAL, 5)

    def test_default_worker_max_retries(self) -> None:
        self.assertEqual(self.cfg.WORKER_MAX_RETRIES, 1)

    def test_default_queue_backend_is_file(self) -> None:
        self.assertEqual(self.cfg.QUEUE_BACKEND, "file")

    def test_default_s3_not_configured(self) -> None:
        """JVA_BUCKET がデフォルト値の場合は S3 未設定扱い。"""
        self.assertFalse(self.cfg.S3_CONFIGURED)

    def test_default_enable_intake_api(self) -> None:
        self.assertTrue(self.cfg.ENABLE_INTAKE_API)

    def test_default_enable_jobs_api(self) -> None:
        self.assertTrue(self.cfg.ENABLE_JOBS_API)

    def test_default_line_webhook_disabled(self) -> None:
        self.assertFalse(self.cfg.LINE_WEBHOOK_ENABLED)

    # ── 環境変数による上書き ──────────────────────────────────────────────────

    def test_env_override_jva_env(self) -> None:
        os.environ["JVA_ENV"] = "production"
        import src.config as _cfg_mod
        importlib.reload(_cfg_mod)
        self.assertEqual(_cfg_mod.cfg.ENV, "production")

    def test_env_override_data_dir_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            os.environ["JVA_DATA_DIR"] = td
            import src.config as _cfg_mod
            importlib.reload(_cfg_mod)
            self.assertEqual(_cfg_mod.cfg.DATA_DIR, Path(td))

    def test_env_override_data_dir_relative(self) -> None:
        os.environ["JVA_DATA_DIR"] = "custom_data"
        import src.config as _cfg_mod
        importlib.reload(_cfg_mod)
        expected = _REPO_ROOT / "custom_data"
        self.assertEqual(_cfg_mod.cfg.DATA_DIR, expected)

    def test_env_override_jobs_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            os.environ["JVA_JOBS_DIR"] = td
            import src.config as _cfg_mod
            importlib.reload(_cfg_mod)
            self.assertEqual(_cfg_mod.cfg.JOBS_DIR, Path(td))

    def test_env_override_queue_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            os.environ["JVA_QUEUE_DIR"] = td
            import src.config as _cfg_mod
            importlib.reload(_cfg_mod)
            self.assertEqual(_cfg_mod.cfg.QUEUE_DIR, Path(td))

    def test_env_override_log_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            os.environ["JVA_LOG_DIR"] = td
            import src.config as _cfg_mod
            importlib.reload(_cfg_mod)
            self.assertEqual(_cfg_mod.cfg.LOG_DIR, Path(td))

    def test_env_override_s3_configured_when_bucket_set(self) -> None:
        os.environ["JVA_BUCKET"] = "my-real-bucket"
        import src.config as _cfg_mod
        importlib.reload(_cfg_mod)
        self.assertTrue(_cfg_mod.cfg.S3_CONFIGURED)

    def test_env_override_s3_not_configured_when_bucket_empty(self) -> None:
        os.environ["JVA_BUCKET"] = ""
        import src.config as _cfg_mod
        importlib.reload(_cfg_mod)
        self.assertFalse(_cfg_mod.cfg.S3_CONFIGURED)

    def test_env_override_worker_poll_interval(self) -> None:
        os.environ["JVA_WORKER_POLL_INTERVAL_SECONDS"] = "10"
        import src.config as _cfg_mod
        importlib.reload(_cfg_mod)
        self.assertEqual(_cfg_mod.cfg.WORKER_POLL_INTERVAL, 10)

    def test_env_override_enable_intake_api_false(self) -> None:
        os.environ["JVA_ENABLE_INTAKE_API"] = "false"
        import src.config as _cfg_mod
        importlib.reload(_cfg_mod)
        self.assertFalse(_cfg_mod.cfg.ENABLE_INTAKE_API)

    def test_env_override_debug_true(self) -> None:
        os.environ["JVA_DEBUG"] = "true"
        import src.config as _cfg_mod
        importlib.reload(_cfg_mod)
        self.assertTrue(_cfg_mod.cfg.DEBUG)

    def test_jobs_dir_falls_back_to_data_subdir(self) -> None:
        """JVA_JOBS_DIR 未設定時は JVA_DATA_DIR/jobs を返す。"""
        with tempfile.TemporaryDirectory() as td:
            os.environ["JVA_DATA_DIR"] = td
            import src.config as _cfg_mod
            importlib.reload(_cfg_mod)
            self.assertEqual(_cfg_mod.cfg.JOBS_DIR, Path(td) / "jobs")


# ─────────────────────────────────────────────────────────────────────────────
class TestLoggingConfig(unittest.TestCase):
    """src/logging_config.py のテスト"""

    def setUp(self) -> None:
        import src.logging_config as _lc
        _lc.reset_for_testing()
        self._lc = _lc

    def tearDown(self) -> None:
        self._lc.reset_for_testing()

    def test_setup_logging_no_file(self) -> None:
        """enable_file=False でも標準出力ハンドラが設定される。"""
        self._lc.setup_logging(component="test", enable_file=False)
        root = logging.getLogger()
        self.assertGreater(len(root.handlers), 0)

    def test_get_logger_returns_logger(self) -> None:
        logger = self._lc.get_logger("test.module")
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "test.module")

    def test_setup_logging_idempotent(self) -> None:
        """setup_logging は2回呼んでも多重ハンドラにならない。"""
        self._lc.setup_logging(component="test", enable_file=False)
        first_count = len(logging.getLogger().handlers)
        self._lc.reset_for_testing()
        self._lc.setup_logging(component="test", enable_file=False)
        second_count = len(logging.getLogger().handlers)
        self.assertEqual(first_count, second_count)

    def test_setup_logging_creates_log_dir(self) -> None:
        """enable_file=True 指定時にログディレクトリが作成される。"""
        with tempfile.TemporaryDirectory() as td:
            log_dir = Path(td) / "test_logs"
            os.environ["JVA_LOG_DIR"] = str(log_dir)
            try:
                self._lc.setup_logging(component="test_phase8", enable_file=True)
                self.assertTrue(log_dir.exists())
            finally:
                os.environ.pop("JVA_LOG_DIR", None)
                self._lc.reset_for_testing()

    def test_reset_clears_handlers(self) -> None:
        self._lc.setup_logging(component="test", enable_file=False)
        self._lc.reset_for_testing()
        # reset 後は handler なし、または最小限
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 0)


# ─────────────────────────────────────────────────────────────────────────────
class TestHealthEndpoints(unittest.TestCase):
    """server/app.py の /health, /ready エンドポイントのテスト"""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from fastapi.testclient import TestClient
            from server.app import app
            cls.client = TestClient(app)
            cls._available = True
        except ImportError:
            cls._available = False

    def _skip_if_unavailable(self) -> None:
        if not self._available:
            self.skipTest("fastapi または server.app が利用不可")

    def test_health_returns_200(self) -> None:
        self._skip_if_unavailable()
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)

    def test_health_returns_status_ok(self) -> None:
        self._skip_if_unavailable()
        r = self.client.get("/health")
        data = r.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["app"], "javelin-video-analysis")

    def test_ready_returns_json(self) -> None:
        self._skip_if_unavailable()
        r = self.client.get("/ready")
        # 200 または 503
        self.assertIn(r.status_code, (200, 503))
        data = r.json()
        self.assertIn("status", data)
        self.assertIn("checks", data)

    def test_ready_includes_expected_checks(self) -> None:
        self._skip_if_unavailable()
        r = self.client.get("/ready")
        data = r.json()
        checks = data.get("checks", {})
        self.assertIn("data_dir", checks)
        self.assertIn("queue_dir", checks)
        self.assertIn("s3_configured", checks)

    def test_ready_s3_configured_false_without_bucket(self) -> None:
        """S3 未設定でも /ready が例外なく返ることを確認。"""
        self._skip_if_unavailable()
        saved = os.environ.get("JVA_BUCKET")
        os.environ["JVA_BUCKET"] = "your-bucket-name"
        try:
            r = self.client.get("/ready")
            self.assertIn(r.status_code, (200, 503))
            data = r.json()
            self.assertFalse(data["checks"]["s3_configured"])
        finally:
            if saved is not None:
                os.environ["JVA_BUCKET"] = saved
            else:
                os.environ.pop("JVA_BUCKET", None)

    def test_ready_includes_env_field(self) -> None:
        self._skip_if_unavailable()
        r = self.client.get("/ready")
        data = r.json()
        self.assertIn("env", data)


# ─────────────────────────────────────────────────────────────────────────────
class TestDockerArtifacts(unittest.TestCase):
    """Dockerfile / docker-compose.yml / .dockerignore の存在確認。"""

    def test_dockerfile_exists(self) -> None:
        self.assertTrue((_REPO_ROOT / "Dockerfile").exists(), "Dockerfile が見つかりません")

    def test_dockerignore_exists(self) -> None:
        self.assertTrue((_REPO_ROOT / ".dockerignore").exists(), ".dockerignore が見つかりません")

    def test_docker_compose_exists(self) -> None:
        self.assertTrue((_REPO_ROOT / "docker-compose.yml").exists(), "docker-compose.yml が見つかりません")

    def test_env_example_exists(self) -> None:
        self.assertTrue((_REPO_ROOT / ".env.example").exists(), ".env.example が見つかりません")

    def test_dockerfile_has_jva_user(self) -> None:
        dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("USER jva", dockerfile, "Dockerfile に非 root ユーザー設定がありません")

    def test_dockerfile_has_env_vars(self) -> None:
        dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("JVA_DATA_DIR", dockerfile)
        self.assertIn("JVA_LOG_DIR", dockerfile)

    def test_dockerignore_excludes_env(self) -> None:
        ignore = (_REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn(".env", ignore, ".dockerignore に .env が含まれていません")

    def test_env_example_has_required_keys(self) -> None:
        content = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        for key in ["JVA_ENV", "JVA_API_KEY", "JVA_DATA_DIR", "JVA_QUEUE_DIR", "JVA_LOG_DIR"]:
            self.assertIn(key, content, f".env.example に {key} が含まれていません")

    def test_requirements_has_streamlit(self) -> None:
        content = (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("streamlit", content, "requirements.txt に streamlit が含まれていません")


# ─────────────────────────────────────────────────────────────────────────────
class TestDeploymentDocs(unittest.TestCase):
    """ドキュメントファイルの存在確認。"""

    def test_deployment_guide_exists(self) -> None:
        self.assertTrue((_REPO_ROOT / "docs" / "deployment_guide.md").exists())

    def test_security_checklist_exists(self) -> None:
        self.assertTrue((_REPO_ROOT / "docs" / "security_checklist.md").exists())

    def test_readme_has_phase8(self) -> None:
        readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Phase 8", readme)

    def test_scripts_exist(self) -> None:
        for s in ["dev_api.ps1", "dev_admin.ps1", "dev_worker.ps1", "docker_up.ps1", "docker_down.ps1"]:
            self.assertTrue((_REPO_ROOT / "scripts" / s).exists(), f"scripts/{s} が見つかりません")


if __name__ == "__main__":
    unittest.main()
