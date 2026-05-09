"""
tests/test_phase4.py — Phase 4 ユニットテスト

Phase 4 で追加された機能（フェーズ定義・フェーズフレーム・比較ジョブ管理・
フレーム抽出・PDF/ZIP 生成の軽量テスト）を検証する。

実行:
    python -m pytest tests/test_phase4.py -v
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 1. configs/phases.yaml / src/phase_loader.py
# ─────────────────────────────────────────────────────────────────────────────

class TestPhaseLoader:
    def test_load_phases_returns_dict(self):
        from src.phase_loader import load_phases
        phases = load_phases()
        assert isinstance(phases, dict)
        assert len(phases) > 0

    def test_all_expected_phase_keys_present(self):
        from src.phase_loader import get_all_phase_keys
        keys = get_all_phase_keys()
        for expected in ["approach", "cross_step", "withdrawal", "block", "release", "follow_through", "recovery"]:
            assert expected in keys, f"フェーズキー '{expected}' が見つかりません"

    def test_get_phase_label(self):
        from src.phase_loader import get_phase_label
        label = get_phase_label("block")
        assert isinstance(label, str)
        assert len(label) > 0

    def test_unknown_phase_key_returns_key_itself(self):
        from src.phase_loader import get_phase_label
        label = get_phase_label("nonexistent_phase_xyz")
        assert label == "nonexistent_phase_xyz"

    def test_get_phase_key_points_returns_list(self):
        from src.phase_loader import get_phase_key_points
        pts = get_phase_key_points("release")
        assert isinstance(pts, list)

    def test_is_range_phase_block_false(self):
        from src.phase_loader import is_range_phase
        assert is_range_phase("block") is False

    def test_is_range_phase_approach_true(self):
        from src.phase_loader import is_range_phase
        assert is_range_phase("approach") is True

    def test_get_phase_labels_map(self):
        from src.phase_loader import get_phase_labels_map
        m = get_phase_labels_map()
        assert isinstance(m, dict)
        assert "block" in m
        assert "release" in m

    def test_phases_yaml_exists(self):
        yaml_path = Path(__file__).resolve().parent.parent / "configs" / "phases.yaml"
        assert yaml_path.exists(), "configs/phases.yaml が存在しません"


# ─────────────────────────────────────────────────────────────────────────────
# 2. job_manager.py — フェーズフレーム
# ─────────────────────────────────────────────────────────────────────────────

class TestPhaseFramesJobManager:
    def test_get_phase_frames_default_for_nonexistent_job(self):
        import job_manager
        pf = job_manager.get_phase_frames("__nonexistent_job_xyz__")
        assert isinstance(pf, dict)
        assert "block_frame" in pf
        assert pf["block_frame"] is None

    def test_update_phase_frames_creates_file(self):
        import job_manager
        with tempfile.TemporaryDirectory() as tmpdir:
            # jobs/ ディレクトリ構造を模倣
            orig_dir = job_manager.JOBS_DIR
            job_manager.JOBS_DIR = Path(tmpdir)
            try:
                jid = "test_pf_job_abc"
                (Path(tmpdir) / jid).mkdir()
                pf = job_manager.update_phase_frames(jid, block_frame=120, fps=30.0)
                assert pf["block_frame"] == 120
                assert pf["fps"] == 30.0
                assert pf["updated_at"] != ""
                # ファイルが書き込まれているか
                pf_path = Path(tmpdir) / jid / "phase_frames.json"
                assert pf_path.exists()
            finally:
                job_manager.JOBS_DIR = orig_dir

    def test_update_phase_frames_sec_calculated(self):
        import job_manager
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = job_manager.JOBS_DIR
            job_manager.JOBS_DIR = Path(tmpdir)
            try:
                jid = "test_pf_sec_job"
                (Path(tmpdir) / jid).mkdir()
                pf = job_manager.update_phase_frames(jid, block_frame=60, fps=30.0)
                # block_sec = 60 / 30 = 2.0
                assert pf.get("block_sec") == pytest.approx(2.0, abs=0.01)
            finally:
                job_manager.JOBS_DIR = orig_dir

    def test_get_phase_frames_roundtrip(self):
        import job_manager
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = job_manager.JOBS_DIR
            job_manager.JOBS_DIR = Path(tmpdir)
            try:
                jid = "test_pf_roundtrip"
                (Path(tmpdir) / jid).mkdir()
                job_manager.update_phase_frames(jid, release_frame=200, fps=25.0)
                pf2 = job_manager.get_phase_frames(jid)
                assert pf2["release_frame"] == 200
                assert pf2["fps"] == 25.0
            finally:
                job_manager.JOBS_DIR = orig_dir


# ─────────────────────────────────────────────────────────────────────────────
# 3. job_manager.py — 比較ジョブ
# ─────────────────────────────────────────────────────────────────────────────

class TestComparisonJobManager:
    def test_create_comparison_returns_dict(self):
        import job_manager
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = job_manager.COMPARISONS_DIR
            job_manager.COMPARISONS_DIR = Path(tmpdir) / "comparisons"
            try:
                comp = job_manager.create_comparison(
                    job_a_id="job_a_test",
                    job_b_id="job_b_test",
                    label_a="改善前",
                    label_b="改善後",
                )
                assert comp["job_a_id"] == "job_a_test"
                assert comp["job_b_id"] == "job_b_test"
                assert comp["label_a"] == "改善前"
                assert comp["comparison_id"] != ""
                assert comp["status"] == "created"
            finally:
                job_manager.COMPARISONS_DIR = orig_dir

    def test_load_comparison_roundtrip(self):
        import job_manager
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = job_manager.COMPARISONS_DIR
            job_manager.COMPARISONS_DIR = Path(tmpdir) / "comparisons"
            try:
                comp = job_manager.create_comparison("job_x", "job_y", purpose="テスト")
                cid = comp["comparison_id"]
                loaded = job_manager.load_comparison(cid)
                assert loaded["job_a_id"] == "job_x"
                assert loaded["purpose"] == "テスト"
            finally:
                job_manager.COMPARISONS_DIR = orig_dir

    def test_update_comparison_status(self):
        import job_manager
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = job_manager.COMPARISONS_DIR
            job_manager.COMPARISONS_DIR = Path(tmpdir) / "comparisons"
            try:
                comp = job_manager.create_comparison("j1", "j2")
                cid = comp["comparison_id"]
                updated = job_manager.update_comparison(cid, status="report_generated")
                assert updated["status"] == "report_generated"
            finally:
                job_manager.COMPARISONS_DIR = orig_dir

    def test_list_comparisons_empty(self):
        import job_manager
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = job_manager.COMPARISONS_DIR
            job_manager.COMPARISONS_DIR = Path(tmpdir) / "comparisons_empty"
            try:
                result = job_manager.list_comparisons()
                assert result == []
            finally:
                job_manager.COMPARISONS_DIR = orig_dir

    def test_list_comparisons_finds_created(self):
        import job_manager
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = job_manager.COMPARISONS_DIR
            job_manager.COMPARISONS_DIR = Path(tmpdir) / "comparisons"
            try:
                job_manager.create_comparison("j1", "j2", label_a="A", label_b="B")
                job_manager.create_comparison("j3", "j4", label_a="C", label_b="D")
                listing = job_manager.list_comparisons()
                assert len(listing) == 2
            finally:
                job_manager.COMPARISONS_DIR = orig_dir

    def test_load_comparison_nonexistent_raises(self):
        import job_manager
        with pytest.raises(FileNotFoundError):
            job_manager.load_comparison("__nonexistent_comparison_xyz__")


# ─────────────────────────────────────────────────────────────────────────────
# 4. src/phase_frames.py — フレーム抽出
# ─────────────────────────────────────────────────────────────────────────────

class TestPhaseFrames:
    def test_extract_phase_frames_no_video(self, tmp_path):
        """動画ファイルなし → 空 dict を返す（クラッシュしない）"""
        from src.phase_frames import extract_phase_frames
        result = extract_phase_frames(
            video_path=tmp_path / "nonexistent.mp4",
            output_dir=tmp_path / "out",
            phase_frames_dict={"block_frame": 5},
        )
        assert isinstance(result, dict)

    def test_extract_phase_frames_all_none(self, tmp_path):
        """フレーム番号が全て None → 空 dict を返す（クラッシュしない）"""
        from src.phase_frames import extract_phase_frames
        result = extract_phase_frames(
            video_path=tmp_path / "video.mp4",
            output_dir=tmp_path / "out",
            phase_frames_dict={
                "block_frame": None,
                "release_frame": None,
            },
        )
        assert result == {}

    def test_parse_frame_keys_correct(self):
        """_parse_frame_keys のキー変換が正しい"""
        from src.phase_frames import _parse_frame_keys
        result = _parse_frame_keys({
            "approach_start_frame": 10,
            "approach_end_frame": 80,
            "block_frame": 120,
            "fps": 30.0,
        })
        assert result.get("approach_start") == 10
        assert result.get("approach_end") == 80
        assert result.get("block") == 120
        assert "fps" not in result  # fps はフレームキーではない

    def test_extract_phase_frames_for_job_no_files(self, tmp_path):
        """phase_frames.json なし → 空 dict を返す（クラッシュしない）"""
        from src.phase_frames import extract_phase_frames_for_job
        result = extract_phase_frames_for_job(tmp_path)
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# 5. src/comparison_zip.py — ZIP 生成
# ─────────────────────────────────────────────────────────────────────────────

class TestComparisonZip:
    def test_create_comparison_zip_creates_file(self, tmp_path):
        """最低限のディレクトリ構成で ZIP が生成される"""
        from src.comparison_zip import create_comparison_zip
        comp_dir = tmp_path / "comp_001"
        job_a_dir = tmp_path / "job_a"
        job_b_dir = tmp_path / "job_b"
        comp_dir.mkdir()
        job_a_dir.mkdir()
        job_b_dir.mkdir()

        zip_path = create_comparison_zip(
            comparison_dir=comp_dir,
            job_dir_a=job_a_dir,
            job_dir_b=job_b_dir,
            label_a="改善前",
            label_b="改善後",
        )
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"

    def test_create_comparison_zip_contains_readme(self, tmp_path):
        """ZIP 内に readme.txt が含まれている"""
        import zipfile
        from src.comparison_zip import create_comparison_zip
        comp_dir = tmp_path / "comp_002"
        job_a_dir = tmp_path / "job_a2"
        job_b_dir = tmp_path / "job_b2"
        comp_dir.mkdir(); job_a_dir.mkdir(); job_b_dir.mkdir()

        zip_path = create_comparison_zip(comp_dir, job_a_dir, job_b_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        assert any("readme.txt" in n for n in names)

    def test_create_comparison_zip_contains_disclaimer(self, tmp_path):
        """ZIP 内に disclaimer.txt が含まれている"""
        import zipfile
        from src.comparison_zip import create_comparison_zip
        comp_dir = tmp_path / "comp_003"
        job_a_dir = tmp_path / "job_a3"
        job_b_dir = tmp_path / "job_b3"
        comp_dir.mkdir(); job_a_dir.mkdir(); job_b_dir.mkdir()

        zip_path = create_comparison_zip(comp_dir, job_a_dir, job_b_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        assert any("disclaimer.txt" in n for n in names)

    def test_create_comparison_zip_includes_report_if_exists(self, tmp_path):
        """比較レポート PDF が存在する場合 ZIP に含まれる"""
        import zipfile
        from src.comparison_zip import create_comparison_zip
        comp_dir = tmp_path / "comp_004"
        job_a_dir = tmp_path / "job_a4"
        job_b_dir = tmp_path / "job_b4"
        comp_dir.mkdir(); job_a_dir.mkdir(); job_b_dir.mkdir()
        # ダミーの比較レポートを作成
        (comp_dir / "comparison_report.pdf").write_bytes(b"dummy pdf content")

        zip_path = create_comparison_zip(comp_dir, job_a_dir, job_b_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        assert any("comparison_report.pdf" in n for n in names)


# ─────────────────────────────────────────────────────────────────────────────
# 6. configs/plans.yaml — comparison プランの更新確認
# ─────────────────────────────────────────────────────────────────────────────

class TestPlansYamlComparison:
    def test_comparison_plan_includes_phase_summary_pdf(self):
        from src.plan_loader import get_plan_includes
        includes = get_plan_includes("comparison")
        assert "phase_summary_pdf" in includes, \
            "comparison プランに phase_summary_pdf が含まれていません"

    def test_comparison_plan_includes_comparison_phase_images(self):
        from src.plan_loader import get_plan_includes
        includes = get_plan_includes("comparison")
        assert "comparison_phase_images" in includes, \
            "comparison プランに comparison_phase_images が含まれていません"
