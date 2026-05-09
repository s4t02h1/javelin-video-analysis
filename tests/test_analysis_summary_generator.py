"""
tests/test_analysis_summary_generator.py — analysis_summary_generator モジュールのテスト
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

# プロジェクトルートを sys.path に追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analysis_summary_generator import (
    _build_summary,
    _compute_key_metrics_section,
    _compute_pose_quality_section,
    _compute_video_section,
    generate_analysis_summary_for_job,
)


# ── テスト用 DataFrame ファクトリ ─────────────────────────────────────────────

def _make_df(n: int = 30, fps: float = 30.0) -> pd.DataFrame:
    """最小限の列を持つ DataFrame を生成する。"""
    import numpy as np

    frames = list(range(1, n + 1))
    time_sec = [i / fps for i in range(n)]
    # 右手首: フレーム中央付近で最高点（y 最小 = 高さ最大）
    half = n // 2 if n > 1 else 1
    wrist_y = [0.6 - 0.3 * ((i - half) / half) ** 2 for i in range(n)]
    wrist_x = [0.5 + 0.01 * i for i in range(n)]

    data = {
        "frame": frames,
        "time_sec": time_sec,
        "right_wrist_x": wrist_x,
        "right_wrist_y": wrist_y,
        "left_shoulder_x": [0.3] * n,
        "left_shoulder_y": [0.3] * n,
        "right_shoulder_x": [0.7] * n,
        "right_shoulder_y": [0.3] * n,
        "left_hip_x": [0.35] * n,
        "left_hip_y": [0.6] * n,
        "right_hip_x": [0.65] * n,
        "right_hip_y": [0.6] * n,
    }

    # visibility 列
    for lm in [
        "right_shoulder", "right_elbow", "right_wrist",
        "left_shoulder", "left_elbow", "left_wrist",
    ]:
        data[f"{lm}_visibility"] = [0.9] * n

    return pd.DataFrame(data)


def _make_df_with_missing(n: int = 20, missing_every: int = 4) -> pd.DataFrame:
    """right_wrist_x に一定間隔で NaN を含む DataFrame。"""
    df = _make_df(n=n)
    for i in range(0, n, missing_every):
        df.at[i, "right_wrist_x"] = float("nan")
    return df


# ── _compute_video_section ────────────────────────────────────────────────────

class TestComputeVideoSection:
    def test_frame_count(self):
        df = _make_df(n=30)
        w: list[str] = []
        result = _compute_video_section(df, w)
        assert result["frame_count"] == 30

    def test_duration_sec(self):
        df = _make_df(n=30, fps=30.0)
        w: list[str] = []
        result = _compute_video_section(df, w)
        # 0〜29 フレーム: duration = 29/30 ≒ 0.967
        assert result["duration_sec"] is not None
        assert result["duration_sec"] > 0

    def test_no_time_sec_column(self):
        df = _make_df().drop(columns=["time_sec"])
        w: list[str] = []
        result = _compute_video_section(df, w)
        assert result["duration_sec"] is None
        assert len(w) == 1
        assert "time_sec" in w[0]

    def test_single_row_gives_no_duration(self):
        df = _make_df(n=1)
        w: list[str] = []
        result = _compute_video_section(df, w)
        assert result["duration_sec"] is None
        assert len(w) == 1


# ── _compute_pose_quality_section ────────────────────────────────────────────

class TestComputePoseQualitySection:
    def test_no_missing(self):
        df = _make_df(n=20)
        w: list[str] = []
        result = _compute_pose_quality_section(df, w)
        assert result["right_wrist_missing_ratio"] == 0.0

    def test_missing_ratio(self):
        df = _make_df_with_missing(n=20, missing_every=4)
        w: list[str] = []
        result = _compute_pose_quality_section(df, w)
        # 20 行中 0,4,8,12,16 の 5 行が NaN → ratio = 0.25
        assert result["right_wrist_missing_ratio"] == pytest.approx(0.25, abs=1e-4)

    def test_average_visibility_keys(self):
        df = _make_df(n=10)
        w: list[str] = []
        result = _compute_pose_quality_section(df, w)
        for lm in ["right_shoulder", "right_elbow", "right_wrist",
                   "left_shoulder", "left_elbow", "left_wrist"]:
            assert lm in result["average_visibility"]

    def test_average_visibility_value(self):
        df = _make_df(n=10)
        w: list[str] = []
        result = _compute_pose_quality_section(df, w)
        assert result["average_visibility"]["right_wrist"] == pytest.approx(0.9, abs=1e-4)

    def test_missing_wrist_x_column_adds_warning(self):
        df = _make_df().drop(columns=["right_wrist_x"])
        w: list[str] = []
        result = _compute_pose_quality_section(df, w)
        assert result["right_wrist_missing_ratio"] is None
        assert any("right_wrist_x" in msg for msg in w)

    def test_missing_visibility_column_adds_warning(self):
        df = _make_df().drop(columns=["right_elbow_visibility"])
        w: list[str] = []
        result = _compute_pose_quality_section(df, w)
        assert result["average_visibility"]["right_elbow"] is None
        assert any("right_elbow_visibility" in msg for msg in w)


# ── _compute_key_metrics_section ─────────────────────────────────────────────

class TestComputeKeyMetricsSection:
    def test_wrist_max_height_is_computed(self):
        df = _make_df(n=30, fps=30.0)
        w: list[str] = []
        result = _compute_key_metrics_section(df, w)
        assert result["right_wrist_max_height_time_sec"] is not None
        assert result["right_wrist_max_height_norm"] is not None

    def test_height_is_1_minus_y(self):
        """最高点の height_norm = 1 - min(right_wrist_y)"""
        df = _make_df(n=30, fps=30.0)
        min_y = df["right_wrist_y"].min()
        expected_norm = round(1.0 - float(min_y), 4)
        w: list[str] = []
        result = _compute_key_metrics_section(df, w)
        assert result["right_wrist_max_height_norm"] == pytest.approx(expected_norm, abs=1e-3)

    def test_missing_wrist_y_adds_warning(self):
        df = _make_df().drop(columns=["right_wrist_y"])
        w: list[str] = []
        result = _compute_key_metrics_section(df, w)
        assert result["right_wrist_max_height_time_sec"] is None
        assert result["right_wrist_max_height_norm"] is None
        assert len(w) >= 1

    def test_torso_center_computed(self):
        df = _make_df(n=10)
        w: list[str] = []
        result = _compute_key_metrics_section(df, w)
        # 肩中心 X = (0.3 + 0.7)/2 = 0.5, 腰中心 X = (0.35 + 0.65)/2 = 0.5
        # torso center = (0.5 + 0.5)/2 = 0.5
        assert result["torso_center_x_start"] == pytest.approx(0.5, abs=1e-4)
        assert result["torso_center_x_end"]   == pytest.approx(0.5, abs=1e-4)

    def test_torso_center_missing_column_adds_warning(self):
        df = _make_df().drop(columns=["left_hip_x"])
        w: list[str] = []
        result = _compute_key_metrics_section(df, w)
        assert result["torso_center_x_start"] is None
        assert any("left_hip_x" in msg for msg in w)


# ── _build_summary ────────────────────────────────────────────────────────────

class TestBuildSummary:
    def test_structure(self):
        df = _make_df(n=20)
        result = _build_summary("test_job_001", df)
        assert result["job_id"] == "test_job_001"
        assert result["status"] == "ok"
        assert "video" in result
        assert "pose_quality" in result
        assert "key_metrics" in result
        assert isinstance(result["warnings"], list)

    def test_generated_at_is_str(self):
        df = _make_df(n=10)
        result = _build_summary("abc", df)
        assert isinstance(result["generated_at"], str)


# ── generate_analysis_summary_for_job（統合テスト） ──────────────────────────

class TestGenerateAnalysisSummaryForJob:
    def test_ok_case(self, tmp_path: Path):
        """CSV が存在するジョブ: status=ok で JSON が生成される。"""
        job_dir = tmp_path / "20260510_120000_test"
        report_dir = job_dir / "report"
        report_dir.mkdir(parents=True)

        csv_path = report_dir / "pose_landmarks.csv"
        _make_df(n=30).to_csv(csv_path, index=False)

        out = generate_analysis_summary_for_job(job_dir)
        assert out.exists()

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "ok"
        assert data["video"]["frame_count"] == 30
        assert data["pose_quality"]["right_wrist_missing_ratio"] == 0.0
        assert data["key_metrics"]["right_wrist_max_height_norm"] is not None

    def test_no_csv_gives_skipped(self, tmp_path: Path):
        """CSV が存在しないジョブ: status=skipped。"""
        job_dir = tmp_path / "no_csv_job"
        job_dir.mkdir()

        out = generate_analysis_summary_for_job(job_dir)
        assert out.exists()

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "skipped"
        assert len(data["warnings"]) >= 1

    def test_empty_csv_gives_skipped(self, tmp_path: Path):
        """CSV が空のジョブ: status=skipped。"""
        job_dir = tmp_path / "empty_csv_job"
        report_dir = job_dir / "report"
        report_dir.mkdir(parents=True)

        csv_path = report_dir / "pose_landmarks.csv"
        csv_path.write_text("frame,time_sec\n", encoding="utf-8")

        out = generate_analysis_summary_for_job(job_dir)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "skipped"

    def test_job_id_from_job_json(self, tmp_path: Path):
        """job.json が存在する場合は job_id を読む。"""
        job_dir = tmp_path / "job_with_meta"
        report_dir = job_dir / "report"
        report_dir.mkdir(parents=True)

        (job_dir / "job.json").write_text(
            json.dumps({"job_id": "custom_id_999"}), encoding="utf-8"
        )
        csv_path = report_dir / "pose_landmarks.csv"
        _make_df(n=10).to_csv(csv_path, index=False)

        out = generate_analysis_summary_for_job(job_dir)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["job_id"] == "custom_id_999"

    def test_job_id_fallback_to_dirname(self, tmp_path: Path):
        """job.json が存在しない場合はディレクトリ名を job_id にする。"""
        job_dir = tmp_path / "fallback_dir_name"
        report_dir = job_dir / "report"
        report_dir.mkdir(parents=True)

        csv_path = report_dir / "pose_landmarks.csv"
        _make_df(n=10).to_csv(csv_path, index=False)

        out = generate_analysis_summary_for_job(job_dir)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["job_id"] == "fallback_dir_name"

    def test_report_json_updated(self, tmp_path: Path):
        """report.json が存在する場合は analysis_summary_json パスが追記される。"""
        job_dir = tmp_path / "with_report_json"
        report_dir = job_dir / "report"
        report_dir.mkdir(parents=True)

        report_json = job_dir / "report.json"
        report_json.write_text(json.dumps({"report_files": {}}), encoding="utf-8")

        csv_path = report_dir / "pose_landmarks.csv"
        _make_df(n=10).to_csv(csv_path, index=False)

        generate_analysis_summary_for_job(job_dir)

        meta = json.loads(report_json.read_text(encoding="utf-8"))
        assert "analysis_summary_json" in meta["report_files"]
        assert meta["report_files"]["analysis_summary_json"] == "report/analysis_summary.json"

    def test_job_json_updated(self, tmp_path: Path):
        """job.json が存在する場合は analysis_summary_json パスが追記される。"""
        job_dir = tmp_path / "with_job_json"
        report_dir = job_dir / "report"
        report_dir.mkdir(parents=True)

        job_json = job_dir / "job.json"
        job_json.write_text(json.dumps({"job_id": "with_job_json"}), encoding="utf-8")

        csv_path = report_dir / "pose_landmarks.csv"
        _make_df(n=10).to_csv(csv_path, index=False)

        generate_analysis_summary_for_job(job_dir)

        meta = json.loads(job_json.read_text(encoding="utf-8"))
        assert meta.get("analysis_summary_json") == "report/analysis_summary.json"

    def test_csv_source_stored(self, tmp_path: Path):
        """出力 JSON に csv_source が記録される。"""
        job_dir = tmp_path / "csv_source_check"
        report_dir = job_dir / "report"
        report_dir.mkdir(parents=True)

        csv_path = report_dir / "pose_landmarks.csv"
        _make_df(n=10).to_csv(csv_path, index=False)

        out = generate_analysis_summary_for_job(job_dir)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "csv_source" in data
        assert "pose_landmarks.csv" in data["csv_source"]

    def test_with_partial_missing_columns(self, tmp_path: Path):
        """一部列が欠損してもクラッシュせず warnings に記録される。"""
        job_dir = tmp_path / "partial_cols"
        report_dir = job_dir / "report"
        report_dir.mkdir(parents=True)

        df = _make_df(n=15)
        df = df.drop(columns=["right_wrist_y", "left_hip_x"])
        csv_path = report_dir / "pose_landmarks.csv"
        df.to_csv(csv_path, index=False)

        out = generate_analysis_summary_for_job(job_dir)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "ok"
        assert len(data["warnings"]) >= 1
        assert data["key_metrics"]["right_wrist_max_height_norm"] is None
