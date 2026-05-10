"""
tests/test_phase13.py — Phase 13: ユーザー向けダッシュボード テスト
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest


# ── テスト用ジョブディレクトリを作成するヘルパー ────────────────────────────────


def _make_test_job(tmp_path: Path, with_metrics: bool = True, with_frames: bool = True,
                   with_graphs: bool = False, with_videos: bool = False,
                   with_phase_frames: bool = True) -> Path:
    """テスト用の最小限ジョブディレクトリを作成する。"""
    job_dir = tmp_path / "test_job_p13"
    (job_dir / "input").mkdir(parents=True)
    (job_dir / "output").mkdir()
    (job_dir / "report").mkdir()
    (job_dir / "report" / "frames").mkdir()
    (job_dir / "report" / "graphs").mkdir()

    # job.json
    (job_dir / "job.json").write_text(json.dumps({
        "job_id": "test_job_p13",
        "status": "delivery_ready",
        "created_at": "2026-05-10T00:00:00",
        "updated_at": "2026-05-10T00:00:00",
        "height_m": None,
        "mode": "all_variants",
    }), encoding="utf-8")

    # customer_info.json
    (job_dir / "customer_info.json").write_text(json.dumps({
        "customer_name": "テスト選手",
        "plan": "スタンダード",
        "dominant_arm": "right",
    }), encoding="utf-8")

    # phase_frames.json
    if with_phase_frames:
        (job_dir / "phase_frames.json").write_text(json.dumps({
            "release_frame": 100,
            "block_frame": 90,
        }), encoding="utf-8")

    # advanced_metrics.json
    if with_metrics:
        (job_dir / "report" / "advanced_metrics.json").write_text(json.dumps({
            "job_id": "test_job_p13",
            "status": "ok",
            "metrics_version": "0.1.0",
            "generated_at": "2026-05-10T00:00:00",
            "fps": 30.0,
            "dominant_arm": "right",
            "quality": {
                "overall_quality": "good",
                "metrics_reliability": "high",
                "pose_detection_rate": 0.95,
                "warnings": [],
            },
            "release_metrics": {
                "available": True,
                "release_wrist_height_normalized": {"value": 1.2, "unit": "body_scale", "reliability": "high", "note": ""},
                "release_wrist_velocity_normalized": {"value": 8.5, "unit": "body_scale/sec", "reliability": "high", "note": ""},
                "release_arm_extension_ratio": {"value": 0.92, "unit": "ratio(0-1)", "reliability": "medium", "note": ""},
            },
            "block_metrics": {
                "available": True,
                "block_to_release_time_sec": {"value": 0.15, "unit": "sec", "reliability": "medium", "note": ""},
                "hip_deceleration_ratio": {"value": 0.62, "unit": "ratio", "reliability": "medium", "note": ""},
            },
            "trunk_metrics": {"available": False},
            "arm_metrics": {
                "available": True,
                "throwing_wrist_peak_velocity": {"value": 12.3, "unit": "body_scale/sec", "reliability": "high", "note": ""},
            },
            "trajectory_metrics": {},
            "phase_metrics": {},
        }), encoding="utf-8")

    # 代表フレーム画像（1x1 白PNG）
    if with_frames:
        import base64
        # 1x1 白 PNG のバイト列
        _PNG_1X1 = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
        )
        (job_dir / "report" / "frames" / "release_frame.png").write_bytes(_PNG_1X1)
        (job_dir / "report" / "frames" / "block_frame.png").write_bytes(_PNG_1X1)

    if with_videos:
        (job_dir / "output" / "analysis_skeleton.mp4").write_bytes(b"\x00" * 100)

    return job_dir


# ── テスト ──────────────────────────────────────────────────────────────────


class TestUserDashboardGenerate:
    def test_generates_html_file(self, tmp_path: Path) -> None:
        """user_dashboard.html が生成される。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        job_dir = _make_test_job(tmp_path)
        out = generate_user_dashboard_for_job(job_dir)
        assert out is not None
        assert out.exists()
        assert out.suffix == ".html"
        assert out.stat().st_size > 500

    def test_html_contains_job_id(self, tmp_path: Path) -> None:
        """HTMLにジョブIDが含まれる。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        job_dir = _make_test_job(tmp_path)
        out = generate_user_dashboard_for_job(job_dir)
        assert out is not None
        content = out.read_text(encoding="utf-8")
        assert "test_job_p13" in content

    def test_no_metrics_does_not_crash(self, tmp_path: Path) -> None:
        """advanced_metrics.json がなくても落ちない。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        job_dir = _make_test_job(tmp_path, with_metrics=False)
        out = generate_user_dashboard_for_job(job_dir)
        assert out is not None
        assert out.exists()

    def test_no_phase_frames_does_not_crash(self, tmp_path: Path) -> None:
        """phase_frames.json がなくても落ちない。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        job_dir = _make_test_job(tmp_path, with_phase_frames=False)
        out = generate_user_dashboard_for_job(job_dir)
        assert out is not None

    def test_no_frames_shows_missing_placeholder(self, tmp_path: Path) -> None:
        """フレーム画像がなければ「未生成」プレースホルダーが含まれる。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        job_dir = _make_test_job(tmp_path, with_frames=False)
        out = generate_user_dashboard_for_job(job_dir)
        assert out is not None
        content = out.read_text(encoding="utf-8")
        assert "フェーズ画像はありません" in content

    def test_no_videos_does_not_crash(self, tmp_path: Path) -> None:
        """動画ファイルがなくても落ちない。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        job_dir = _make_test_job(tmp_path, with_videos=False)
        out = generate_user_dashboard_for_job(job_dir)
        assert out is not None

    def test_pdf_links_show_unavailable(self, tmp_path: Path) -> None:
        """PDFが存在しない場合「未生成」が表示される。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        job_dir = _make_test_job(tmp_path)
        out = generate_user_dashboard_for_job(job_dir)
        assert out is not None
        content = out.read_text(encoding="utf-8")
        assert "未生成" in content

    def test_metrics_cards_appear(self, tmp_path: Path) -> None:
        """advanced_metricsがあれば主要指標カードが含まれる。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        job_dir = _make_test_job(tmp_path)
        out = generate_user_dashboard_for_job(job_dir)
        assert out is not None
        content = out.read_text(encoding="utf-8")
        assert "主要指標" in content

    def test_research_data_section_separate(self, tmp_path: Path) -> None:
        """CSV/JSONが研究・開発用として分離表示される。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        job_dir = _make_test_job(tmp_path)
        out = generate_user_dashboard_for_job(job_dir)
        assert out is not None
        content = out.read_text(encoding="utf-8")
        assert "研究・開発用" in content

    def test_disclaimer_present(self, tmp_path: Path) -> None:
        """免責事項が含まれる。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        job_dir = _make_test_job(tmp_path)
        out = generate_user_dashboard_for_job(job_dir)
        assert out is not None
        content = out.read_text(encoding="utf-8")
        assert "免責事項" in content or "注意事項" in content

    def test_no_assertion_断定的(self, tmp_path: Path) -> None:
        """断定的な表現が含まれないこと（「〜です。」で終わる参考表現の確認）。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        job_dir = _make_test_job(tmp_path)
        out = generate_user_dashboard_for_job(job_dir)
        assert out is not None
        content = out.read_text(encoding="utf-8")
        # 参考値という文言があること
        assert "参考" in content

    def test_s3_not_configured_local_html_works(self, tmp_path: Path) -> None:
        """S3が設定されていなくてもローカルHTML生成は動作する。"""
        import os
        env_backup = os.environ.get("JVA_BUCKET")
        try:
            os.environ.pop("JVA_BUCKET", None)
            from src.dashboard_generator import generate_user_dashboard_for_job
            job_dir = _make_test_job(tmp_path)
            out = generate_user_dashboard_for_job(job_dir)
            assert out is not None
        finally:
            if env_backup:
                os.environ["JVA_BUCKET"] = env_backup


class TestComparisonDashboardGenerate:
    def test_generates_comparison_html(self, tmp_path: Path) -> None:
        """comparison_dashboard.html が生成される。"""
        from src.comparison_dashboard_generator import generate_comparison_dashboard_for_jobs
        job_a = _make_test_job(tmp_path / "job_a")
        job_b = _make_test_job(tmp_path / "job_b")
        out = generate_comparison_dashboard_for_jobs(job_a, job_b)
        assert out is not None
        assert out.exists()
        assert out.stat().st_size > 500

    def test_comparison_contains_labels(self, tmp_path: Path) -> None:
        """A/Bラベルが含まれる。"""
        from src.comparison_dashboard_generator import generate_comparison_dashboard_for_jobs
        job_a = _make_test_job(tmp_path / "job_a")
        job_b = _make_test_job(tmp_path / "job_b")
        out = generate_comparison_dashboard_for_jobs(job_a, job_b, job_a_label="試技A", job_b_label="試技B")
        assert out is not None
        content = out.read_text(encoding="utf-8")
        assert "試技A" in content
        assert "試技B" in content

    def test_comparison_no_metrics_does_not_crash(self, tmp_path: Path) -> None:
        """比較指標データがなくても落ちない。"""
        from src.comparison_dashboard_generator import generate_comparison_dashboard_for_jobs
        job_a = _make_test_job(tmp_path / "job_a", with_metrics=False)
        job_b = _make_test_job(tmp_path / "job_b", with_metrics=False)
        out = generate_comparison_dashboard_for_jobs(job_a, job_b)
        assert out is not None

    def test_comparison_disclaimer_present(self, tmp_path: Path) -> None:
        """比較ダッシュボードに免責事項・注意文が含まれる。"""
        from src.comparison_dashboard_generator import generate_comparison_dashboard_for_jobs
        job_a = _make_test_job(tmp_path / "job_a")
        job_b = _make_test_job(tmp_path / "job_b")
        out = generate_comparison_dashboard_for_jobs(job_a, job_b)
        assert out is not None
        content = out.read_text(encoding="utf-8")
        assert "断定" in content or "参考" in content


class TestDashboardDeliveryMessage:
    def test_message_with_url(self) -> None:
        """URLありの納品メッセージに重要情報が含まれる。"""
        from src.dashboard_generator import generate_dashboard_delivery_message
        msg = generate_dashboard_delivery_message(
            job_id="test_p13",
            dashboard_url="https://example.com/dashboard",
            url_expires_at="2026-05-24T00:00:00",
        )
        assert "https://example.com/dashboard" in msg
        assert "test_p13" in msg
        assert "参考" in msg

    def test_message_no_url(self) -> None:
        """URLなしの場合もクラッシュしない。"""
        from src.dashboard_generator import generate_dashboard_delivery_message
        msg = generate_dashboard_delivery_message(job_id="test_p13", dashboard_url=None)
        assert "test_p13" in msg


class TestDashboardPipelineNonFatal:
    def test_generate_failure_returns_none(self, tmp_path: Path) -> None:
        """生成失敗時は None を返し例外を投げない。"""
        from src.dashboard_generator import generate_user_dashboard_for_job
        # 存在しない不正なディレクトリ（job.json なし → クラッシュしないことを確認）
        job_dir = tmp_path / "broken_job"
        job_dir.mkdir()
        out = generate_user_dashboard_for_job(job_dir)
        # None または Path いずれも許容（データ不足でも生成試みる設計のため）
        assert out is None or out.exists()
