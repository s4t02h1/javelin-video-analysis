"""tests/test_phase12.py — Phase 12 高度解析指標のユニットテスト

テスト実行:
    python -m pytest tests/test_phase12.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ── パス設定 ─────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# テスト用ジョブ作成ヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def _make_test_job(
    tmp_path: Path,
    dominant_arm: str = "right",
    release_frame: int | None = 50,
    block_frame: int | None = 45,
    n_frames: int = 100,
    fps: float = 30.0,
    include_csv: bool = True,
) -> Path:
    """最小限の構成を持つテスト用ジョブディレクトリを作成する。"""
    job_dir = tmp_path / "test_job"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "report").mkdir(exist_ok=True)

    # job.json
    (job_dir / "job.json").write_text(
        json.dumps({"job_id": "test_job", "status": "completed"}),
        encoding="utf-8",
    )

    # customer_info.json
    (job_dir / "customer_info.json").write_text(
        json.dumps({"dominant_arm": dominant_arm}),
        encoding="utf-8",
    )

    # phase_frames.json
    pf: dict = {}
    if release_frame is not None:
        pf["release_frame"] = release_frame
    if block_frame is not None:
        pf["block_frame"] = block_frame
    (job_dir / "phase_frames.json").write_text(json.dumps(pf), encoding="utf-8")

    # video_quality_report.json（FPS 情報）— 実際のファイル名に合わせる
    (job_dir / "report" / "video_quality_report.json").write_text(
        json.dumps({"fps": fps, "overall_quality": "medium", "pose_detection_rate": 0.95}),
        encoding="utf-8",
    )

    if include_csv:
        # pose_landmarks.csv — 全ランドマークをゆるやかに動かす
        data: dict = {}
        rng = np.random.default_rng(seed=42)
        for side in ("left", "right"):
            for lm in ("wrist", "elbow", "shoulder", "hip", "knee", "ankle"):
                data[f"{side}_{lm}_x"] = np.linspace(0.3, 0.7, n_frames) + rng.normal(0, 0.01, n_frames)
                data[f"{side}_{lm}_y"] = np.linspace(0.4, 0.6, n_frames) + rng.normal(0, 0.01, n_frames)
        data["time_sec"] = np.linspace(0.0, n_frames / fps, n_frames)
        data["frame"] = list(range(n_frames))

        csv_path = job_dir / "report" / "pose_landmarks.csv"
        pd.DataFrame(data).to_csv(csv_path, index=False)

    return job_dir


# ─────────────────────────────────────────────────────────────────────────────
# 1. compute_advanced_metrics_for_job が JSON を生成する
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_advanced_metrics_creates_json(tmp_path: Path) -> None:
    job_dir = _make_test_job(tmp_path)

    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job

    out = compute_advanced_metrics_for_job(job_dir)
    assert out is not None, "戻り値が None"
    assert out.exists(), f"出力ファイルが存在しません: {out}"
    assert out.suffix == ".json"

    with open(out, encoding="utf-8") as f:
        data = json.load(f)

    assert "job_id" in data
    assert "status" in data
    assert "metrics_version" in data


# ─────────────────────────────────────────────────────────────────────────────
# 2. release_frame=None でもクラッシュしない
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_no_release_frame(tmp_path: Path) -> None:
    job_dir = _make_test_job(tmp_path, release_frame=None, block_frame=None)

    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job

    out = compute_advanced_metrics_for_job(job_dir)
    assert out is not None

    with open(out, encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("status") in ("ok", "no_data", "partial")
    # release_metrics が available=False になるはず
    release = data.get("release_metrics", {})
    assert release.get("available") is False or "release_frame" not in data.get("release_metrics", {})


# ─────────────────────────────────────────────────────────────────────────────
# 3. block_frame=None でもクラッシュしない
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_no_block_frame(tmp_path: Path) -> None:
    job_dir = _make_test_job(tmp_path, block_frame=None)

    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job

    out = compute_advanced_metrics_for_job(job_dir)
    assert out is not None

    with open(out, encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("status") in ("ok", "no_data", "partial")


# ─────────────────────────────────────────────────────────────────────────────
# 4. pose_landmarks.csv がなくてもクラッシュしない
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_missing_csv(tmp_path: Path) -> None:
    job_dir = _make_test_job(tmp_path, include_csv=False)

    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job

    # 例外を投げずに戻り値を返すか None を返す
    try:
        out = compute_advanced_metrics_for_job(job_dir)
    except Exception as e:
        pytest.fail(f"CSV なしで例外が発生: {e}")

    # out が None の場合は OK（CSV なしで生成スキップ）
    if out is not None and out.exists():
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        # status は ok 以外（no_data / failed / no_pose_data）
        assert data.get("status") != "ok" or data.get("quality", {}).get("pose_detection_rate", 0) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. 右利き / 左利きで dominant_arm が正しく記録される
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("arm", ["right", "left"])
def test_dominant_arm_recorded(tmp_path: Path, arm: str) -> None:
    job_dir = _make_test_job(tmp_path / arm, dominant_arm=arm)

    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job

    out = compute_advanced_metrics_for_job(job_dir)
    assert out is not None

    with open(out, encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("dominant_arm") == arm


# ─────────────────────────────────────────────────────────────────────────────
# 6. reliability が JSON に保存される
# ─────────────────────────────────────────────────────────────────────────────

def test_reliability_saved(tmp_path: Path) -> None:
    job_dir = _make_test_job(tmp_path)

    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job

    out = compute_advanced_metrics_for_job(job_dir)
    assert out is not None

    with open(out, encoding="utf-8") as f:
        data = json.load(f)

    quality = data.get("quality", {})
    assert "metrics_reliability" in quality
    assert quality["metrics_reliability"] in ("high", "medium", "low", "unknown")


# ─────────────────────────────────────────────────────────────────────────────
# 7. metric_labels.yaml が読み込める
# ─────────────────────────────────────────────────────────────────────────────

def test_metric_labels_yaml_loads() -> None:
    import yaml  # type: ignore[import-not-found]

    labels_path = _REPO_ROOT / "configs" / "metric_labels.yaml"
    assert labels_path.exists(), f"metric_labels.yaml が見つかりません: {labels_path}"

    with open(labels_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert isinstance(data, dict)
    assert len(data) > 0

    # 必須エントリを確認
    for key in ("release_wrist_height_normalized", "release_wrist_velocity_normalized"):
        assert key in data, f"必須キー `{key}` が metric_labels.yaml にありません"
        entry = data[key]
        assert "label" in entry
        assert "description" in entry


# ─────────────────────────────────────────────────────────────────────────────
# 8. PDF が生成される
# ─────────────────────────────────────────────────────────────────────────────

def test_pdf_generates(tmp_path: Path) -> None:
    job_dir = _make_test_job(tmp_path)

    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job
    from src.analysis.advanced_metrics_report import generate_advanced_metrics_report_for_job

    compute_advanced_metrics_for_job(job_dir)
    pdf_path = generate_advanced_metrics_report_for_job(job_dir)

    assert pdf_path is not None, "PDF パスが None"
    assert pdf_path.exists(), f"PDF ファイルが存在しません: {pdf_path}"
    assert pdf_path.stat().st_size > 100, "PDF が空ファイル（100 bytes 以下）"


# ─────────────────────────────────────────────────────────────────────────────
# 9. 比較指標が生成される
# ─────────────────────────────────────────────────────────────────────────────

def test_comparison_metrics_generate(tmp_path: Path) -> None:
    job_a = _make_test_job(tmp_path / "job_a")
    job_b = _make_test_job(tmp_path / "job_b")

    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job
    from src.analysis.comparison_advanced_metrics import (
        compute_comparison_advanced_metrics,
    )

    compute_advanced_metrics_for_job(job_a)
    compute_advanced_metrics_for_job(job_b)

    result = compute_comparison_advanced_metrics(job_a, job_b, "動画A", "動画B")

    assert isinstance(result, dict), "比較結果が dict でない"
    assert "comparisons" in result
    assert isinstance(result["comparisons"], list)
    assert len(result["comparisons"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 10. 比較 PDF が生成される
# ─────────────────────────────────────────────────────────────────────────────

def test_comparison_pdf_generates(tmp_path: Path) -> None:
    job_a = _make_test_job(tmp_path / "job_a")
    job_b = _make_test_job(tmp_path / "job_b")

    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job
    from src.analysis.comparison_advanced_report import (
        generate_comparison_advanced_report_for_jobs,
    )

    compute_advanced_metrics_for_job(job_a)
    compute_advanced_metrics_for_job(job_b)

    out_path = tmp_path / "comparison.pdf"
    pdf_path = generate_comparison_advanced_report_for_jobs(
        job_a, job_b, "動画A", "動画B", output_path=out_path
    )

    assert pdf_path is not None, "比較 PDF パスが None"
    assert pdf_path.exists(), f"比較 PDF が存在しません: {pdf_path}"
    assert pdf_path.stat().st_size > 100, "比較 PDF が空"


# ─────────────────────────────────────────────────────────────────────────────
# 11. advanced_metrics 計算エラーでも通常処理が止まらない
#     (compute_advanced_metrics_for_job が例外を発生させず None を返す)
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_error_does_not_raise(tmp_path: Path) -> None:
    """compute_advanced_metrics_for_job は内部エラーで例外を発生させない。"""
    # 壊れた CSV（数値以外のデータ）を用意
    job_dir = _make_test_job(tmp_path, include_csv=False)
    bad_csv = job_dir / "report" / "pose_landmarks.csv"
    bad_csv.write_text("not,valid,csv\nxxx,yyy,zzz\n", encoding="utf-8")

    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job

    # 例外が発生しないことを確認
    try:
        out = compute_advanced_metrics_for_job(job_dir)
    except Exception as e:
        pytest.fail(f"壊れた CSV で例外が発生: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 12. エクスポートファイルに個人情報が含まれない
# ─────────────────────────────────────────────────────────────────────────────

def test_no_personal_info_in_export(tmp_path: Path) -> None:
    # 個人情報をセット
    job_dir = _make_test_job(tmp_path)
    customer_data = {
        "dominant_arm": "right",
        "name": "テスト太郎",
        "email": "test@example.com",
        "phone": "090-0000-0000",
        "address": "東京都テスト区",
    }
    (job_dir / "customer_info.json").write_text(
        json.dumps(customer_data, ensure_ascii=False),
        encoding="utf-8",
    )

    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job

    out = compute_advanced_metrics_for_job(job_dir)
    assert out is not None

    content = out.read_text(encoding="utf-8")
    for pii in ("テスト太郎", "test@example.com", "090-0000-0000", "東京都テスト区"):
        assert pii not in content, f"個人情報 '{pii}' がエクスポートファイルに含まれています"
