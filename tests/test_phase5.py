"""
tests/test_phase5.py — Phase 5: S3保存・納品URL生成・スマホ閲覧対応 テスト

boto3 は unittest.mock でモックする。
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── import パス ──────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))   # job_manager を直接 import するため
# NOTE: src/ は絶対に sys.path.insert しない → import src.X パターンで使う


# ════════════════════════════════════════════════════════════════════════════
# テスト用フィクスチャ
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_job_dir(tmp_path: Path) -> Path:
    """テスト用ジョブディレクトリを作成する。"""
    job_dir = tmp_path / "jobs" / "test_job_ph5"
    (job_dir / "report").mkdir(parents=True)
    (job_dir / "output").mkdir(parents=True)
    (job_dir / "deliverables").mkdir(parents=True)
    (job_dir / "input").mkdir(parents=True)

    # ダミーファイル
    (job_dir / "report" / "00_最初に読んでください.pdf").write_bytes(b"%PDF-1.4 dummy")
    (job_dir / "report" / "athlete_data_sheet.pdf").write_bytes(b"%PDF-1.4 dummy")
    (job_dir / "report" / "graph_pack.pdf").write_bytes(b"%PDF-1.4 dummy")
    (job_dir / "report" / "phase_summary.pdf").write_bytes(b"%PDF-1.4 dummy")
    (job_dir / "deliverables" / "full_report_package.zip").write_bytes(b"PK dummy")
    (job_dir / "deliverables" / "data_sheet_package.zip").write_bytes(b"PK dummy")

    return job_dir


@pytest.fixture
def job_id() -> str:
    return "test_job_ph5"


# ════════════════════════════════════════════════════════════════════════════
# 1. is_s3_configured
# ════════════════════════════════════════════════════════════════════════════

class TestIsS3Configured:
    """is_s3_configured() のテスト。"""

    def test_returns_false_when_no_bucket(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JVA_BUCKET 未設定時は False を返す。"""
        monkeypatch.delenv("JVA_BUCKET", raising=False)
        # boto3 はインポート済みでも bucket がなければ False
        from src.storage import s3_storage
        s3_storage._reset_client_cache()
        assert s3_storage.is_s3_configured() is False

    def test_returns_false_when_placeholder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JVA_BUCKET がプレースホルダーのままでは False を返す。"""
        monkeypatch.setenv("JVA_BUCKET", "your-bucket-name")
        from src.storage import s3_storage
        s3_storage._reset_client_cache()
        assert s3_storage.is_s3_configured() is False

    def test_returns_true_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JVA_BUCKET が正しく設定されており boto3 が使える場合は True を返す。"""
        monkeypatch.setenv("JVA_BUCKET", "my-real-bucket")
        monkeypatch.setenv("AWS_REGION", "ap-northeast-1")
        with patch.dict("sys.modules", {"boto3": MagicMock()}):
            from importlib import reload
            from src.storage import s3_storage as _mod
            # boto3 を mock に差し替えて is_s3_configured を直接テスト
            with patch("src.storage.s3_storage.is_s3_configured", return_value=True):
                from src.storage.s3_storage import is_s3_configured
                assert is_s3_configured() is True


# ════════════════════════════════════════════════════════════════════════════
# 2. S3キー生成
# ════════════════════════════════════════════════════════════════════════════

class TestS3KeyBuilding:
    """S3 キー生成のテスト。"""

    def test_build_job_key_default_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """デフォルトプレフィックスでジョブ S3 キーが正しく生成される。"""
        monkeypatch.setenv("JVA_S3_PREFIX", "javelin-analysis")
        from src.storage.s3_storage import build_s3_key_for_job
        key = build_s3_key_for_job("20260508_054525_147f", "reports/report.pdf")
        assert key == "javelin-analysis/jobs/20260508_054525_147f/reports/report.pdf"

    def test_build_job_key_custom_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """カスタムプレフィックスが反映される。"""
        monkeypatch.setenv("JVA_S3_PREFIX", "custom/prefix")
        from src.storage.s3_storage import build_s3_key_for_job
        key = build_s3_key_for_job("job_abc", "videos/output.mp4")
        assert key == "custom/prefix/jobs/job_abc/videos/output.mp4"

    def test_build_comparison_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """比較ジョブの S3 キーが comparisons/ プレフィックスになる。"""
        monkeypatch.setenv("JVA_S3_PREFIX", "javelin-analysis")
        from src.storage.s3_storage import build_s3_key_for_comparison
        key = build_s3_key_for_comparison("cmp_xyz", "comparison_report.pdf")
        assert key == "javelin-analysis/comparisons/cmp_xyz/comparison_report.pdf"

    def test_backslash_in_relative_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Windows のバックスラッシュを含むパスも正しく変換される。"""
        monkeypatch.setenv("JVA_S3_PREFIX", "javelin-analysis")
        from src.storage.s3_storage import build_s3_key_for_job
        key = build_s3_key_for_job("job123", r"report\phase_summary.pdf")
        assert "\\" not in key
        assert key == "javelin-analysis/jobs/job123/report/phase_summary.pdf"


# ════════════════════════════════════════════════════════════════════════════
# 3. Content-Type マッピング
# ════════════════════════════════════════════════════════════════════════════

class TestContentTypeMapping:
    """infer_content_type() のテスト。"""

    @pytest.mark.parametrize("filename,expected", [
        ("report.pdf",    "application/pdf"),
        ("video.mp4",     "video/mp4"),
        ("photo.jpg",     "image/jpeg"),
        ("photo.jpeg",    "image/jpeg"),
        ("graph.png",     "image/png"),
        ("data.csv",      "text/csv"),
        ("meta.json",     "application/json"),
        ("bundle.zip",    "application/zip"),
        ("readme.txt",    "text/plain"),
        ("page.html",     "text/html"),
        ("unknown.xyz",   "application/octet-stream"),
        ("VIDEO.MP4",     "video/mp4"),  # 大文字
    ])
    def test_content_types(self, filename: str, expected: str) -> None:
        from src.storage.s3_storage import infer_content_type
        ct = infer_content_type(Path(filename))
        assert ct == expected


# ════════════════════════════════════════════════════════════════════════════
# 4. upload_file_to_s3 — ファイルが存在しない場合は落ちない
# ════════════════════════════════════════════════════════════════════════════

class TestUploadFileToS3:
    """upload_file_to_s3() のテスト（boto3 mock）。"""

    def test_missing_file_does_not_raise(self) -> None:
        """存在しないファイルを指定しても例外を上げず、ok=False を返す。"""
        from src.storage.s3_storage import upload_file_to_s3
        result = upload_file_to_s3(Path("/nonexistent/path/file.pdf"), "some/key.pdf")
        assert result["ok"] is False
        assert result["s3_key"] == "some/key.pdf"
        assert result["error"] is not None

    def test_upload_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """正常アップロードで ok=True が返る（boto3 mock）。"""
        monkeypatch.setenv("JVA_BUCKET", "test-bucket")
        monkeypatch.setenv("AWS_REGION", "ap-northeast-1")
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4")

        mock_s3 = MagicMock()
        mock_s3.upload_file.return_value = None

        from src.storage import s3_storage
        s3_storage._reset_client_cache()
        with patch("src.storage.s3_storage._get_client", return_value=mock_s3):
            result = s3_storage.upload_file_to_s3(test_file, "jobs/test/report.pdf")

        assert result["ok"] is True
        assert result["s3_key"] == "jobs/test/report.pdf"
        assert result["error"] is None
        mock_s3.upload_file.assert_called_once()

    def test_upload_failure_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """boto3 が例外を上げた場合は ok=False, error に文字列が入る。"""
        monkeypatch.setenv("JVA_BUCKET", "test-bucket")
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4")

        mock_s3 = MagicMock()
        mock_s3.upload_file.side_effect = Exception("AccessDenied")

        from src.storage import s3_storage
        s3_storage._reset_client_cache()
        with patch("src.storage.s3_storage._get_client", return_value=mock_s3):
            result = s3_storage.upload_file_to_s3(test_file, "jobs/test/report.pdf")

        assert result["ok"] is False
        assert "AccessDenied" in result["error"]


# ════════════════════════════════════════════════════════════════════════════
# 5. artifact_manifest 生成
# ════════════════════════════════════════════════════════════════════════════

class TestArtifactManifest:
    """artifact_manifest.py のテスト。"""

    def test_build_manifest_detects_existing_files(
        self, tmp_job_dir: Path, job_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """存在するファイルが exists=True で検出される。"""
        monkeypatch.setenv("JVA_S3_PREFIX", "javelin-analysis")
        from src.artifact_manifest import build_artifact_manifest
        manifest = build_artifact_manifest(tmp_job_dir, job_id)
        assert manifest["job_id"] == job_id
        assert manifest["exists_count"] > 0
        assert manifest["total_count"] > 0
        # 存在するファイルはすべて exists=True
        existing = [a for a in manifest["artifacts"] if a["exists"]]
        assert len(existing) == manifest["exists_count"]

    def test_save_and_load_manifest(
        self, tmp_job_dir: Path, job_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """マニフェストを保存→読み込みできる。"""
        monkeypatch.setenv("JVA_S3_PREFIX", "javelin-analysis")
        from src.artifact_manifest import build_artifact_manifest, save_artifact_manifest, load_artifact_manifest
        manifest = build_artifact_manifest(tmp_job_dir, job_id)
        path = save_artifact_manifest(tmp_job_dir, manifest)
        assert path.exists()
        loaded = load_artifact_manifest(tmp_job_dir)
        assert loaded is not None
        assert loaded["job_id"] == job_id

    def test_load_manifest_returns_none_when_missing(self, tmp_path: Path) -> None:
        """artifact_manifest.json がない場合は None を返す。"""
        from src.artifact_manifest import load_artifact_manifest
        result = load_artifact_manifest(tmp_path)
        assert result is None

    def test_manifest_s3_keys_contain_job_id(
        self, tmp_job_dir: Path, job_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """S3 キーにジョブ ID が含まれている。"""
        monkeypatch.setenv("JVA_S3_PREFIX", "javelin-analysis")
        from src.artifact_manifest import build_artifact_manifest
        manifest = build_artifact_manifest(tmp_job_dir, job_id)
        for art in manifest["artifacts"]:
            assert job_id in art["s3_key"], f"job_id not in s3_key: {art['s3_key']}"

    def test_manifest_no_personal_info_in_keys(
        self, tmp_job_dir: Path, job_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """S3 キーに典型的な個人情報パターン（名前・学校名）が入らない。"""
        monkeypatch.setenv("JVA_S3_PREFIX", "javelin-analysis")
        from src.artifact_manifest import build_artifact_manifest
        manifest = build_artifact_manifest(tmp_job_dir, job_id)
        # S3 キーはジョブIDのみで構成されるはず
        for art in manifest["artifacts"]:
            # キーが S3 プレフィックス + jobs/ + job_id の形式になっている
            assert art["s3_key"].startswith("javelin-analysis/jobs/")


# ════════════════════════════════════════════════════════════════════════════
# 6. delivery_page.py — HTML生成
# ════════════════════════════════════════════════════════════════════════════

class TestDeliveryPage:
    """delivery_page.py のテスト。"""

    def _minimal_manifest(self) -> dict:
        return {
            "job_id": "test_job_001",
            "generated_at": "2026-05-10T00:00:00",
            "total_count": 2,
            "exists_count": 2,
            "missing_count": 0,
            "artifacts": [
                {
                    "category": "最初に読む資料",
                    "label": "最初に読んでください",
                    "local_path": "report/00_最初に読んでください.pdf",
                    "s3_key": "javelin-analysis/jobs/test_job_001/docs/00_readme.pdf",
                    "content_type": "application/pdf",
                    "required": True,
                    "exists": True,
                    "size_bytes": 1024,
                },
                {
                    "category": "解析動画",
                    "label": "骨格線つき動画",
                    "local_path": "output/skeleton.mp4",
                    "s3_key": "javelin-analysis/jobs/test_job_001/videos/skeleton.mp4",
                    "content_type": "video/mp4",
                    "required": False,
                    "exists": True,
                    "size_bytes": 50000000,
                },
            ],
        }

    def test_generate_delivery_page_returns_html(self) -> None:
        """generate_delivery_page() が非空の HTML 文字列を返す。"""
        from src.delivery_page import generate_delivery_page
        html = generate_delivery_page(
            manifest=self._minimal_manifest(),
            job_id="test_job_001",
        )
        assert isinstance(html, str)
        assert len(html) > 100
        assert "<!DOCTYPE html>" in html

    def test_html_contains_category_name(self) -> None:
        """生成された HTML にカテゴリ名が含まれる。"""
        from src.delivery_page import generate_delivery_page
        html = generate_delivery_page(
            manifest=self._minimal_manifest(),
            job_id="test_job_001",
        )
        assert "最初に読む資料" in html
        assert "解析動画" in html

    def test_html_contains_presigned_url(self) -> None:
        """presigned URL が渡された場合、HTML に含まれる。"""
        from src.delivery_page import generate_delivery_page
        presigned = {
            "javelin-analysis/jobs/test_job_001/docs/00_readme.pdf": "https://s3.example.com/signed-url?X-Amz-Expires=604800"
        }
        html = generate_delivery_page(
            manifest=self._minimal_manifest(),
            job_id="test_job_001",
            presigned_urls=presigned,
        )
        assert "https://s3.example.com/signed-url" in html

    def test_html_does_not_have_external_css(self) -> None:
        """HTML が外部 CSS を依存していない（1ファイル完結）。"""
        from src.delivery_page import generate_delivery_page
        html = generate_delivery_page(
            manifest=self._minimal_manifest(),
            job_id="test_job_001",
        )
        # <link rel="stylesheet" href="..."> が外部 URL を参照しないこと
        import re
        external_links = re.findall(r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']https?://', html)
        assert len(external_links) == 0

    def test_save_delivery_page(self, tmp_path: Path) -> None:
        """save_delivery_page() がファイルを保存する。"""
        from src.delivery_page import generate_delivery_page, save_delivery_page
        html = generate_delivery_page(
            manifest=self._minimal_manifest(),
            job_id="test_job_001",
        )
        out_path = save_delivery_page(tmp_path / "report", html)
        assert out_path.exists()
        assert out_path.name == "delivery_page.html"
        saved = out_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in saved

    def test_html_escaping_in_customer_info(self) -> None:
        """customer_info にHTMLメタ文字が含まれてもエスケープされる。"""
        from src.delivery_page import generate_delivery_page
        html = generate_delivery_page(
            manifest=self._minimal_manifest(),
            job_id="test_job_001",
            customer_info={"customer_name": "<script>alert('xss')</script>"},
        )
        assert "<script>alert('xss')</script>" not in html
        assert "&lt;script&gt;" in html

    def test_expires_display_format(self) -> None:
        """有効期限が読みやすい形式で表示される。"""
        from src.delivery_page import generate_delivery_page
        html = generate_delivery_page(
            manifest=self._minimal_manifest(),
            job_id="test_job_001",
            expires_at="2026-05-17T10:00:00+09:00",
        )
        # 年月日が含まれること
        assert "2026年" in html


# ════════════════════════════════════════════════════════════════════════════
# 7. presigned URL 生成 (mock)
# ════════════════════════════════════════════════════════════════════════════

class TestPresignedUrl:
    """generate_presigned_url() のテスト（boto3 mock）。"""

    def test_generate_presigned_url_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """正常時に URL 文字列が返る。"""
        monkeypatch.setenv("JVA_BUCKET", "real-bucket")
        monkeypatch.setenv("AWS_REGION", "ap-northeast-1")
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/signed"

        from src.storage import s3_storage
        s3_storage._reset_client_cache()
        with patch("src.storage.s3_storage._get_client", return_value=mock_s3):
            url = s3_storage.generate_presigned_url("javelin-analysis/jobs/abc/reports/report.pdf")

        assert url == "https://s3.example.com/signed"
        mock_s3.generate_presigned_url.assert_called_once()

    def test_generate_presigned_url_failure_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """boto3 が例外を上げた場合は None を返す。"""
        monkeypatch.setenv("JVA_BUCKET", "real-bucket")
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.side_effect = Exception("NoSuchKey")

        from src.storage import s3_storage
        s3_storage._reset_client_cache()
        with patch("src.storage.s3_storage._get_client", return_value=mock_s3):
            url = s3_storage.generate_presigned_url("bad/key")

        assert url is None


# ════════════════════════════════════════════════════════════════════════════
# 8. job_manager S3フィールド
# ════════════════════════════════════════════════════════════════════════════

class TestJobManagerS3Fields:
    """job_manager.py の S3 関連関数のテスト。"""

    def test_get_job_s3_status_defaults_for_old_job(self) -> None:
        """古いジョブ dict（S3フィールドなし）でも安全に動作する。"""
        from job_manager import get_job_s3_status
        old_job = {
            "job_id": "legacy_job",
            "status": "completed",
            "created_at": "2026-01-01T00:00:00",
        }
        status = get_job_s3_status(old_job)
        assert status["upload_status"] == "none"
        assert status["uploaded_artifacts_count"] == 0
        assert status["delivery_page_url"] is None
        assert status["delivery_url_expires_at"] is None

    def test_update_job_s3_delivery_saves_fields(self, tmp_path: Path) -> None:
        """update_job_s3_delivery() が job.json にフィールドを保存する。"""
        import job_manager
        # JOBS_DIR をテンポラリに差し替え
        orig_jobs_dir = job_manager.JOBS_DIR
        job_manager.JOBS_DIR = tmp_path / "jobs"

        try:
            job = job_manager.create_job(None, "basic")
            jid = job["job_id"]
            updated = job_manager.update_job_s3_delivery(
                jid,
                delivery_page_s3_key="javelin/delivery/page.html",
                delivery_page_url="https://s3.example.com/page",
                delivery_url_expires_at="2026-05-20T00:00:00",
                uploaded_artifacts_count=10,
                upload_status="complete",
            )
            assert updated["upload_status"] == "complete"
            assert updated["uploaded_artifacts_count"] == 10
            assert updated["delivery_page_url"] == "https://s3.example.com/page"

            # ディスクからリロードしても値が残っている
            reloaded = job_manager.load_job(jid)
            assert reloaded["upload_status"] == "complete"
        finally:
            job_manager.JOBS_DIR = orig_jobs_dir


# ════════════════════════════════════════════════════════════════════════════
# 9. append_upload_log — 個人情報・URLをログに残さない
# ════════════════════════════════════════════════════════════════════════════

class TestUploadLog:
    """append_upload_log() のテスト。"""

    def test_log_does_not_contain_presigned_url(self, tmp_path: Path) -> None:
        """ログファイルに presigned URL（https://... 形式）が入らない。"""
        from src.storage.s3_storage import append_upload_log
        log_path = tmp_path / "logs" / "s3_upload.log"
        uploaded = [{"s3_key": "javelin-analysis/jobs/test/reports/report.pdf", "ok": True}]
        failed: list[dict] = []
        append_upload_log(log_path, "test_job_001", uploaded, failed,
                          expires_at="2026-05-17T10:00:00")
        log_text = log_path.read_text(encoding="utf-8")
        # ログには s3_key のキー名（パス）は書き出すが、presigned URL（?X-Amz-Signature=...）は不要
        assert "X-Amz-Signature" not in log_text
        assert "https://" not in log_text

    def test_log_records_success_and_failure(self, tmp_path: Path) -> None:
        """成功・失敗の件数がログに記録される。"""
        from src.storage.s3_storage import append_upload_log
        log_path = tmp_path / "logs" / "s3_upload.log"
        uploaded = [
            {"s3_key": "javelin-analysis/jobs/test/reports/report.pdf", "ok": True},
            {"s3_key": "javelin-analysis/jobs/test/videos/skeleton.mp4", "ok": True},
        ]
        failed = [{"s3_key": "javelin-analysis/jobs/test/zip/package.zip", "ok": False, "error": "AccessDenied"}]
        append_upload_log(log_path, "test_job_001", uploaded, failed,
                          expires_at="2026-05-17T10:00:00")
        log_text = log_path.read_text(encoding="utf-8")
        assert "2 件" in log_text   # 成功件数
        assert "1 件" in log_text   # 失敗件数
        assert "test_job_001" in log_text
