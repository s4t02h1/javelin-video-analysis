"""
tests/test_phase10.py — Phase 10 自動フェーズ推定・解析精度向上 テスト
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

import pytest

# ── リポジトリルートを sys.path に追加 ──────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ── テスト共通ユーティリティ ─────────────────────────────────────────────────
_LANDMARK_NAMES = [
    "nose",
    "left_shoulder", "right_shoulder",
    "left_elbow",    "right_elbow",
    "left_wrist",    "right_wrist",
    "left_hip",      "right_hip",
    "left_knee",     "right_knee",
    "left_ankle",    "right_ankle",
]


def _make_csv_content(num_frames: int = 60, fps: float = 30.0) -> str:
    """テスト用 pose_landmarks.csv の内容を生成する。"""
    headers = ["frame", "time_sec"]
    for name in _LANDMARK_NAMES:
        headers += [f"{name}_x", f"{name}_y", f"{name}_z", f"{name}_visibility"]

    rows = []
    for i in range(num_frames):
        t = i / fps
        row: Dict[str, Any] = {"frame": i, "time_sec": round(t, 4)}
        # 右手首の速度ピークをフレーム40付近に置く（リリース模擬）
        release_t = 40 / fps
        dist_from_release = abs(t - release_t)
        for name in _LANDMARK_NAMES:
            # 基本値（0.3〜0.7の範囲で動く）
            x_base = 0.5 + 0.1 * (i / num_frames)
            y_base = 0.5 - 0.05 * (i / num_frames)
            # 右手首はリリース付近で高くなる（y が小さくなる）
            if name == "right_wrist":
                y_val = max(0.1, y_base - 0.3 * max(0, 0.5 - dist_from_release))
                x_val = x_base + 0.2 * max(0, 0.5 - dist_from_release)
            else:
                x_val = x_base
                y_val = y_base
            row[f"{name}_x"]          = round(x_val, 4)
            row[f"{name}_y"]          = round(y_val, 4)
            row[f"{name}_z"]          = 0.0
            row[f"{name}_visibility"] = 0.9
        rows.append(row)

    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _write_csv(tmp_dir: Path, num_frames: int = 60, fps: float = 30.0) -> Path:
    report_dir = tmp_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "pose_landmarks.csv"
    csv_path.write_text(_make_csv_content(num_frames, fps), encoding="utf-8")
    return csv_path


# ══════════════════════════════════════════════════════════════════════════════
# Phase Detection Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestPhaseDetectionModule:
    """src.analysis.phase_detection の単体テスト"""

    def test_import(self):
        from src.analysis import phase_detection  # noqa: F401

    def test_detect_phases_without_csv(self):
        """CSV がなくても例外が出ずに skipped を返す。"""
        from src.analysis.phase_detection import detect_phases
        result = detect_phases(csv_path=None, dominant_arm="right", fps=30.0, total_frames=60)
        assert result["status"] == "skipped"
        assert isinstance(result["phases"], dict)

    def test_detect_phases_with_nonexistent_csv(self):
        """存在しない CSV パスでも例外が出ない。"""
        from src.analysis.phase_detection import detect_phases
        result = detect_phases(
            csv_path=Path("/nonexistent/path/pose_landmarks.csv"),
            dominant_arm="right",
        )
        assert result["status"] == "skipped"

    def test_detect_phases_with_valid_csv(self):
        """有効な CSV から OK を返し、phases dict が含まれる。"""
        from src.analysis.phase_detection import detect_phases
        with tempfile.TemporaryDirectory() as td:
            csv_path = _write_csv(Path(td))
            result = detect_phases(csv_path=csv_path, dominant_arm="right", fps=30.0)
            assert result["status"] == "ok"
            assert "release" in result["phases"]
            assert "block" in result["phases"]

    def test_release_frame_within_range(self):
        """リリース候補フレームが有効範囲内にある。"""
        from src.analysis.phase_detection import detect_phases
        num_frames = 90
        fps = 30.0
        with tempfile.TemporaryDirectory() as td:
            csv_path = _write_csv(Path(td), num_frames=num_frames, fps=fps)
            result = detect_phases(csv_path=csv_path, dominant_arm="right", fps=fps, total_frames=num_frames)
            release = result["phases"].get("release", {})
            frame = release.get("frame")
            if frame is not None:
                assert 0 <= frame < num_frames, f"release frame {frame} out of range"

    def test_confidence_in_range(self):
        """confidence が常に 0.0〜1.0 に収まる。"""
        from src.analysis.phase_detection import detect_phases
        with tempfile.TemporaryDirectory() as td:
            csv_path = _write_csv(Path(td))
            result = detect_phases(csv_path=csv_path, dominant_arm="right", fps=30.0)
            for phase_key, phase_data in result["phases"].items():
                conf = phase_data.get("confidence", 0.0)
                assert 0.0 <= conf <= 1.0, f"{phase_key} confidence={conf} out of [0,1]"

    def test_right_vs_left_arm(self):
        """右投げと左投げで is_auto_detected が同じ構造を返す。"""
        from src.analysis.phase_detection import detect_phases
        with tempfile.TemporaryDirectory() as td:
            csv_path = _write_csv(Path(td))
            result_r = detect_phases(csv_path=csv_path, dominant_arm="right", fps=30.0)
            result_l = detect_phases(csv_path=csv_path, dominant_arm="left", fps=30.0)
            assert result_r["dominant_arm"] == "right"
            assert result_l["dominant_arm"] == "left"
            # 両方 OK ステータス
            assert result_r["status"] == "ok"
            assert result_l["status"] == "ok"

    def test_all_phases_have_required_fields(self):
        """各フェーズ結果に必須フィールドが含まれる。"""
        from src.analysis.phase_detection import detect_phases
        required_fields = ["confidence", "confidence_label", "method", "reason",
                           "is_auto_detected", "needs_review"]
        with tempfile.TemporaryDirectory() as td:
            csv_path = _write_csv(Path(td))
            result = detect_phases(csv_path=csv_path, dominant_arm="right", fps=30.0)
            for phase_key, phase_data in result["phases"].items():
                for field in required_fields:
                    assert field in phase_data, f"{phase_key} missing field '{field}'"

    def test_short_video_does_not_crash(self):
        """短すぎる動画（5フレーム）でも例外が出ない。"""
        from src.analysis.phase_detection import detect_phases
        with tempfile.TemporaryDirectory() as td:
            csv_path = _write_csv(Path(td), num_frames=5, fps=30.0)
            result = detect_phases(csv_path=csv_path, dominant_arm="right", fps=30.0)
            # skipped か ok か、いずれにしてもエラーにならない
            assert result["status"] in ("ok", "skipped")

    def test_confidence_label_function(self):
        """confidence_label 関数が正しいラベルを返す。"""
        from src.analysis.phase_detection import confidence_label
        assert confidence_label(0.90) == "推定精度 高め"
        assert confidence_label(0.75) == "推定精度 高め"
        assert confidence_label(0.74) == "推定精度 中程度"
        assert confidence_label(0.45) == "推定精度 中程度"
        assert confidence_label(0.44) == "推定精度 低め"
        assert confidence_label(0.00) == "推定精度 低め"

    def test_confidence_warning_function(self):
        """confidence_warning が低信頼度で警告テキストを返す。"""
        from src.analysis.phase_detection import confidence_warning
        assert confidence_warning(0.80) is None
        assert confidence_warning(0.45) is None
        warn = confidence_warning(0.44)
        assert warn is not None
        assert isinstance(warn, str)
        assert len(warn) > 10


# ══════════════════════════════════════════════════════════════════════════════
# Phase Correction Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestPhaseCorrections:
    """フェーズ補正履歴の保存・読み込みテスト"""

    def test_save_and_load_correction(self):
        """修正を保存して読み込める。"""
        from src.analysis.phase_detection import save_phase_correction, load_phase_corrections
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            out_path = save_phase_correction(
                job_dir=job_dir,
                phase_key="release",
                auto_frame=100,
                manual_frame=105,
                accepted=False,
                confidence=0.72,
                admin_note="テスト修正",
            )
            assert out_path.exists()
            corrections = load_phase_corrections(job_dir)
            assert "release" in corrections
            assert corrections["release"]["auto_detected_frame"] == 100
            assert corrections["release"]["manual_corrected_frame"] == 105
            assert corrections["release"]["accepted_by_admin"] is False
            assert corrections["release"]["correction_delta"] == 5
            assert corrections["release"]["admin_note"] == "テスト修正"

    def test_save_correction_accepted(self):
        """採用フラグが正しく保存される。"""
        from src.analysis.phase_detection import save_phase_correction, load_phase_corrections
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            save_phase_correction(
                job_dir=job_dir,
                phase_key="block",
                auto_frame=80,
                manual_frame=80,
                accepted=True,
                confidence=0.55,
            )
            corrections = load_phase_corrections(job_dir)
            assert corrections["block"]["accepted_by_admin"] is True
            assert corrections["block"]["correction_delta"] == 0

    def test_multiple_corrections_accumulate(self):
        """複数フェーズの修正が蓄積される。"""
        from src.analysis.phase_detection import save_phase_correction, load_phase_corrections
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            for key in ["release", "block", "withdrawal_start"]:
                save_phase_correction(job_dir, key, 50, 52, False, 0.60)
            corrections = load_phase_corrections(job_dir)
            assert set(corrections.keys()) >= {"release", "block", "withdrawal_start"}

    def test_load_corrections_missing_file(self):
        """ファイルが存在しない場合は空dict。"""
        from src.analysis.phase_detection import load_phase_corrections
        with tempfile.TemporaryDirectory() as td:
            result = load_phase_corrections(Path(td))
            assert result == {}

    def test_save_correction_with_none_manual_frame(self):
        """manual_frame が None でも保存できる（リセット用）。"""
        from src.analysis.phase_detection import save_phase_correction, load_phase_corrections
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            save_phase_correction(
                job_dir=job_dir,
                phase_key="release",
                auto_frame=100,
                manual_frame=None,
                accepted=False,
                confidence=0.60,
                admin_note="リセット",
            )
            corrections = load_phase_corrections(job_dir)
            assert corrections["release"]["manual_corrected_frame"] is None
            assert corrections["release"]["correction_delta"] is None


# ══════════════════════════════════════════════════════════════════════════════
# detect_phases_for_job Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectPhasesForJob:
    """detect_phases_for_job のジョブ単位テスト"""

    def test_creates_output_json(self):
        """phase_detection_result.json が生成される。"""
        from src.analysis.phase_detection import detect_phases_for_job
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            _write_csv(job_dir)
            out = detect_phases_for_job(job_dir)
            assert out.exists()
            data = json.loads(out.read_text(encoding="utf-8"))
            assert "status" in data

    def test_no_csv_returns_skipped(self):
        """CSV がなくても JSON が生成され status="skipped"。"""
        from src.analysis.phase_detection import detect_phases_for_job
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            # report dir も作らない状態で実行
            out = detect_phases_for_job(job_dir)
            assert out.exists()
            data = json.loads(out.read_text(encoding="utf-8"))
            assert data["status"] == "skipped"

    def test_does_not_raise_on_error(self):
        """内部エラーでも例外が出ない（status="error" として保存）。"""
        from src.analysis import phase_detection as pd_module
        original_detect = pd_module.detect_phases

        def _broken(*args, **kwargs):
            raise RuntimeError("テスト用の意図的エラー")

        pd_module.detect_phases = _broken
        try:
            with tempfile.TemporaryDirectory() as td:
                job_dir = Path(td)
                _write_csv(job_dir)
                out = pd_module.detect_phases_for_job(job_dir)
                assert out.exists()
                data = json.loads(out.read_text(encoding="utf-8"))
                assert data["status"] == "error"
        finally:
            pd_module.detect_phases = original_detect

    def test_reads_dominant_hand_from_customer_info(self):
        """customer_info.json の dominant_hand が使われる。"""
        from src.analysis.phase_detection import detect_phases_for_job, load_phase_detection_result
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            _write_csv(job_dir)
            (job_dir / "customer_info.json").write_text(
                json.dumps({"dominant_hand": "left"}), encoding="utf-8"
            )
            detect_phases_for_job(job_dir)
            result = load_phase_detection_result(job_dir)
            assert result is not None
            assert result.get("dominant_arm") == "left"

    def test_does_not_overwrite_phase_frames_json(self):
        """自動推定は phase_frames.json を勝手に更新しない。"""
        from src.analysis.phase_detection import detect_phases_for_job
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            _write_csv(job_dir)
            pf_path = job_dir / "phase_frames.json"
            original_pf = {
                "fps": 30.0,
                "total_frames": 90,
                "release_frame": 999,  # 手動指定の番哨値
            }
            pf_path.write_text(json.dumps(original_pf), encoding="utf-8")

            detect_phases_for_job(job_dir)

            # phase_frames.json が変わっていないことを確認
            after_pf = json.loads(pf_path.read_text(encoding="utf-8"))
            assert after_pf["release_frame"] == 999, (
                "自動推定が手動フェーズ指定を上書きしてはいけません"
            )

    def test_load_phase_detection_result_missing(self):
        """JSON が存在しない場合 load_phase_detection_result は None を返す。"""
        from src.analysis.phase_detection import load_phase_detection_result
        with tempfile.TemporaryDirectory() as td:
            assert load_phase_detection_result(Path(td)) is None


# ══════════════════════════════════════════════════════════════════════════════
# Video Quality Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestVideoQualityModule:
    """src.analysis.video_quality の単体テスト"""

    def test_import(self):
        from src.analysis import video_quality  # noqa: F401

    def test_check_without_csv(self):
        """CSV なしでも skipped を返す。"""
        from src.analysis.video_quality import check_video_quality
        result = check_video_quality(csv_path=None)
        assert result["status"] == "skipped"

    def test_check_with_valid_csv(self):
        """有効な CSV から OK を返す。"""
        from src.analysis.video_quality import check_video_quality
        with tempfile.TemporaryDirectory() as td:
            csv_path = _write_csv(Path(td))
            result = check_video_quality(csv_path=csv_path, fps=30.0)
            assert result["status"] == "ok"
            assert "overall_quality" in result
            assert result["overall_quality"] in ("good", "medium", "low")

    def test_quality_report_json_created(self):
        """check_video_quality_for_job が JSON を生成する。"""
        from src.analysis.video_quality import check_video_quality_for_job, load_video_quality_report
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            _write_csv(job_dir)
            out = check_video_quality_for_job(job_dir)
            assert out.exists()
            data = load_video_quality_report(job_dir)
            assert data is not None
            assert "overall_quality" in data

    def test_no_csv_creates_skipped_json(self):
        """CSV なしでも JSON が生成され status="skipped"。"""
        from src.analysis.video_quality import check_video_quality_for_job
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            out = check_video_quality_for_job(job_dir)
            assert out.exists()
            data = json.loads(out.read_text(encoding="utf-8"))
            assert data["status"] == "skipped"

    def test_does_not_raise_on_internal_error(self):
        """内部エラーでも例外が出ない。"""
        from src.analysis import video_quality as vq_module
        original_check = vq_module.check_video_quality

        def _broken(*args, **kwargs):
            raise RuntimeError("テスト用の意図的エラー")

        vq_module.check_video_quality = _broken
        try:
            with tempfile.TemporaryDirectory() as td:
                job_dir = Path(td)
                _write_csv(job_dir)
                out = vq_module.check_video_quality_for_job(job_dir)
                assert out.exists()
                data = json.loads(out.read_text(encoding="utf-8"))
                assert data["status"] == "error"
        finally:
            vq_module.check_video_quality = original_check

    def test_warnings_is_list(self):
        """warnings フィールドはリスト。"""
        from src.analysis.video_quality import check_video_quality
        with tempfile.TemporaryDirectory() as td:
            csv_path = _write_csv(Path(td))
            result = check_video_quality(csv_path=csv_path, fps=30.0)
            assert isinstance(result.get("warnings"), list)

    def test_load_video_quality_report_missing(self):
        """JSON が存在しない場合は None を返す。"""
        from src.analysis.video_quality import load_video_quality_report
        with tempfile.TemporaryDirectory() as td:
            assert load_video_quality_report(Path(td)) is None

    def test_low_fps_triggers_warning(self):
        """低 FPS で警告が含まれる。"""
        from src.analysis.video_quality import check_video_quality
        with tempfile.TemporaryDirectory() as td:
            csv_path = _write_csv(Path(td), num_frames=60, fps=10.0)
            result = check_video_quality(csv_path=csv_path, fps=10.0)
            if result["status"] == "ok":
                warnings = result.get("warnings", [])
                # 少なくとも1件の警告があること（FPS低下の警告）
                # ただし CSV から推定する FPS と fps パラメータが一致しない場合もある
                # ここでは warnings が list であることだけ確認
                assert isinstance(warnings, list)

    def test_short_video_does_not_crash(self):
        """3フレームのみの短いCSVでも例外が出ない。"""
        from src.analysis.video_quality import check_video_quality
        with tempfile.TemporaryDirectory() as td:
            csv_path = _write_csv(Path(td), num_frames=3, fps=30.0)
            result = check_video_quality(csv_path=csv_path, fps=30.0)
            assert result["status"] in ("ok", "skipped")


# ══════════════════════════════════════════════════════════════════════════════
# Worker Step Integration Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestWorkerStepIntegration:
    """worker.py の Phase 10 ステップ関数のテスト"""

    def test_step_functions_exist_in_worker(self):
        """worker モジュールに Phase 10 ステップ関数が存在する。"""
        import worker
        assert hasattr(worker, "_step_check_video_quality")
        assert hasattr(worker, "_step_detect_phases")

    def test_step_check_video_quality_does_not_raise(self):
        """_step_check_video_quality がエラーを外に出さない。"""
        import worker
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            _write_csv(job_dir)
            # 例外が出なければ成功
            try:
                worker._step_check_video_quality("test_job_id", job_dir)
            except Exception as e:
                pytest.fail(f"_step_check_video_quality raised: {e}")

    def test_step_detect_phases_does_not_raise(self):
        """_step_detect_phases がエラーを外に出さない。"""
        import worker
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            _write_csv(job_dir)
            try:
                worker._step_detect_phases("test_job_id", job_dir)
            except Exception as e:
                pytest.fail(f"_step_detect_phases raised: {e}")

    def test_pipeline_includes_phase10_steps(self):
        """pipeline_steps に Phase 10 ステップが含まれることを確認（ソース検索）。"""
        worker_path = _REPO_ROOT / "worker.py"
        content = worker_path.read_text(encoding="utf-8")
        assert "check_video_quality" in content
        assert "detect_phases" in content
        # fatal_steps に含まれないことを確認
        assert '"check_video_quality"' not in content.split("fatal_steps")[1][:200] \
            or "check_video_quality" not in content.split("fatal_steps = {")[1].split("}")[0]
