"""
tests/test_phase11.py — Phase 11 アノテーション管理のテスト

テスト方針:
- make_annotation / save_annotation / load_annotation の基本動作
- generate_annotation_from_job でのPhase 10データ読み込み
- 手動フレーム（phase_frames.json）が自動推定より優先されること
- エクスポートフィルタ（denied は常に除外、unknown はデフォルト除外）
- エクスポートに個人情報が含まれないこと
- JSONL / CSV エクスポートの動作
- compute_dataset_stats の計算
- 既存ジョブデータを壊さないこと
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# ── sys.path: src/types/__init__.py がstdlib types を隠さないよう project root を追加 ─
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ── ヘルパー: 一時ディレクトリ内のアノテーションルートを差し替える ─────────────────

@pytest.fixture()
def tmp_ann_root(tmp_path, monkeypatch):
    """JVA_ANNOTATIONS_DIR を一時ディレクトリに向ける。"""
    ann_root = tmp_path / "annotations"
    ann_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("JVA_ANNOTATIONS_DIR", str(ann_root))
    return ann_root


@pytest.fixture()
def tmp_job_dir(tmp_path):
    """最低限のジョブディレクトリを作る。"""
    job_dir = tmp_path / "test_job_phase11"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "report").mkdir(exist_ok=True)

    # job.json
    (job_dir / "job.json").write_text(
        json.dumps({
            "job_id": "test_job_phase11",
            "input_file": str(job_dir / "sample.mp4"),
            "status": "completed",
        }),
        encoding="utf-8",
    )
    return job_dir


# ══════════════════════════════════════════════════════════════════════════════
# テスト 1: make_annotation + save_annotation + load_annotation
# ══════════════════════════════════════════════════════════════════════════════

def test_create_and_save_load_annotation(tmp_ann_root):
    """make_annotation → save_annotation → load_annotation のラウンドトリップ。"""
    from src.annotation.manager import make_annotation, save_annotation, load_annotation

    ann = make_annotation(
        job_id="test_job_001",
        dominant_arm="right",
        fps=30.0,
        total_frames=90,
        duration_sec=3.0,
    )
    assert ann["annotation_status"] == "draft"
    assert ann["annotation_id"].startswith("ann_")
    assert ann["consent_for_training_data"] == "unknown"
    assert ann["sns_permission"] == "unknown"
    assert "phase_labels" in ann
    assert "event_labels" in ann

    path = save_annotation(ann)
    assert path.exists()

    loaded = load_annotation(ann["annotation_id"])
    assert loaded is not None
    assert loaded["job_id"] == "test_job_001"
    assert loaded["dominant_arm"] == "right"


# ══════════════════════════════════════════════════════════════════════════════
# テスト 2: generate_annotation_from_job で Phase 10 データを読み込む
# ══════════════════════════════════════════════════════════════════════════════

def test_generate_annotation_from_phase10_result(tmp_ann_root, tmp_job_dir):
    """phase_detection_result.json があればフェーズ情報が読み込まれる。"""
    from src.annotation.manager import generate_annotation_from_job

    # Phase 10 推定結果を模擬
    detection_result = {
        "status": "ok",
        "dominant_arm": "right",
        "generated_at": "2026-05-11T10:00:00",
        "phases": {
            "release": {
                "frame": 45,
                "time_sec": 1.5,
                "confidence": 0.85,
                "method": "pose_peak",
            },
            "block": {
                "frame": 30,
                "time_sec": 1.0,
                "confidence": 0.78,
                "method": "pose_peak",
            },
        },
    }
    (tmp_job_dir / "report" / "phase_detection_result.json").write_text(
        json.dumps(detection_result), encoding="utf-8"
    )

    ann = generate_annotation_from_job(tmp_job_dir)

    assert ann["job_id"] == "test_job_phase11"
    assert ann["dominant_arm"] == "right"
    assert ann["annotation_status"] == "draft"

    # release フェーズが読み込まれる
    release_pl = ann["phase_labels"]["release"]
    assert release_pl["frame"] == 45
    assert release_pl["source"] == "auto"
    assert release_pl["confidence"] == 0.85

    # event_labels にも反映
    release_ev = ann["event_labels"]["release"]
    assert release_ev["frame"] == 45


# ══════════════════════════════════════════════════════════════════════════════
# テスト 3: phase_frames.json の手動フレームが自動推定より優先される
# ══════════════════════════════════════════════════════════════════════════════

def test_manual_frame_takes_priority(tmp_ann_root, tmp_job_dir):
    """phase_frames.json の値は phase_detection_result.json の自動推定を上書きする。"""
    from src.annotation.manager import generate_annotation_from_job

    # 自動推定: release frame = 45
    detection_result = {
        "status": "ok",
        "dominant_arm": "right",
        "generated_at": "2026-05-11T10:00:00",
        "phases": {
            "release": {"frame": 45, "time_sec": 1.5, "confidence": 0.8, "method": "pose_peak"},
        },
    }
    (tmp_job_dir / "report" / "phase_detection_result.json").write_text(
        json.dumps(detection_result), encoding="utf-8"
    )

    # 手動フレーム指定: release frame = 50 (意図的に違う値)
    phase_frames = {
        "fps": 30.0,
        "total_frames": 90,
        "release_frame": 50,
    }
    (tmp_job_dir / "phase_frames.json").write_text(
        json.dumps(phase_frames), encoding="utf-8"
    )

    ann = generate_annotation_from_job(tmp_job_dir)

    # phase_frames.json が優先される
    release_pl = ann["phase_labels"]["release"]
    assert release_pl["frame"] == 50, f"Expected 50, got {release_pl['frame']}"
    assert release_pl["reviewed"] is True  # 手動指定なので reviewed=True


# ══════════════════════════════════════════════════════════════════════════════
# テスト 4: consent=unknown はデフォルトでエクスポート除外
# ══════════════════════════════════════════════════════════════════════════════

def test_unknown_consent_excluded_by_default(tmp_ann_root, tmp_path):
    """consent_for_training_data=unknown はデフォルトでエクスポートから除外される。"""
    from src.annotation.manager import make_annotation, save_annotation, set_annotation_status
    from src.annotation.exporter import export_annotations

    ann = make_annotation(job_id="unknown_consent_job", consent_for_training_data="unknown")
    save_annotation(ann)
    set_annotation_status(ann["annotation_id"], "confirmed")

    out_dir = tmp_path / "exports"
    result = export_annotations(output_dir=out_dir, include_unknown_consent=False, dry_run=True)

    assert result["exported"] == 0
    assert result["excluded"] >= 1
    reasons = result["excluded_reasons"]
    assert any("unknown" in r for r in reasons)


# ══════════════════════════════════════════════════════════════════════════════
# テスト 5: consent=denied は常にエクスポート除外
# ══════════════════════════════════════════════════════════════════════════════

def test_denied_consent_always_excluded(tmp_ann_root, tmp_path):
    """consent_for_training_data=denied は include_unknown_consent=True でも除外される。"""
    from src.annotation.manager import make_annotation, save_annotation, set_annotation_status
    from src.annotation.exporter import export_annotations

    ann = make_annotation(job_id="denied_consent_job", consent_for_training_data="denied")
    save_annotation(ann)
    set_annotation_status(ann["annotation_id"], "confirmed")

    out_dir = tmp_path / "exports_denied"
    result = export_annotations(output_dir=out_dir, include_unknown_consent=True, dry_run=True)

    assert result["exported"] == 0
    reasons = result["excluded_reasons"]
    assert any("denied" in r for r in reasons)


# ══════════════════════════════════════════════════════════════════════════════
# テスト 6: エクスポートレコードに source_video_path が含まれない
# ══════════════════════════════════════════════════════════════════════════════

def test_no_source_video_path_in_export(tmp_ann_root, tmp_path):
    """source_video_path はエクスポートレコードに含まれてはならない。"""
    from src.annotation.manager import make_annotation, save_annotation, set_annotation_status
    from src.annotation.exporter import _build_export_record, _load_config

    ann = make_annotation(
        job_id="video_path_test_job",
        consent_for_training_data="allowed",
        source_video_path="/secret/path/to/video.mp4",
    )
    save_annotation(ann)
    set_annotation_status(ann["annotation_id"], "confirmed")

    cfg = _load_config()
    record = _build_export_record(ann, cfg)

    assert "source_video_path" not in record, "source_video_path がエクスポートに含まれています"
    assert "/secret/path" not in json.dumps(record), "動画パスがエクスポートに漏れています"


# ══════════════════════════════════════════════════════════════════════════════
# テスト 7: JSONL エクスポートの動作確認
# ══════════════════════════════════════════════════════════════════════════════

def test_jsonl_export(tmp_ann_root, tmp_path):
    """JSONL エクスポートが正しく生成される。"""
    from src.annotation.manager import make_annotation, save_annotation, set_annotation_status, update_annotation
    from src.annotation.exporter import export_annotations

    ann = make_annotation(
        job_id="jsonl_test_job",
        consent_for_training_data="allowed",
        dominant_arm="right",
        fps=30.0,
        total_frames=90,
    )
    # イベントラベルを設定
    ann["event_labels"]["release"]["frame"] = 45
    ann["event_labels"]["release"]["source"] = "manual"
    ann["event_labels"]["release"]["reviewed"] = True
    save_annotation(ann)
    set_annotation_status(ann["annotation_id"], "confirmed")

    out_dir = tmp_path / "jsonl_exports"
    result = export_annotations(output_dir=out_dir, include_unknown_consent=False, dry_run=False)

    assert result["exported"] == 1
    jsonl_path = Path(result["jsonl_path"])
    assert jsonl_path.exists()

    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["job_id"] == "jsonl_test_job"
    assert "source_video_path" not in record
    assert record.get("dominant_arm") == "right"


# ══════════════════════════════════════════════════════════════════════════════
# テスト 8: CSV エクスポートの動作確認
# ══════════════════════════════════════════════════════════════════════════════

def test_csv_export(tmp_ann_root, tmp_path):
    """CSV エクスポートが正しく生成される。"""
    import csv as _csv
    from src.annotation.manager import make_annotation, save_annotation, set_annotation_status
    from src.annotation.exporter import export_annotations

    ann = make_annotation(
        job_id="csv_test_job",
        consent_for_training_data="allowed",
        dominant_arm="left",
    )
    save_annotation(ann)
    set_annotation_status(ann["annotation_id"], "confirmed")

    out_dir = tmp_path / "csv_exports"
    result = export_annotations(output_dir=out_dir, dry_run=False)

    assert result["exported"] == 1
    csv_path = Path(result["csv_path"])
    assert csv_path.exists()

    with csv_path.open("r", encoding="utf-8-sig") as f:
        reader = _csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["job_id"] == "csv_test_job"
    assert "source_video_path" not in rows[0]
    assert rows[0].get("dominant_arm") == "left"


# ══════════════════════════════════════════════════════════════════════════════
# テスト 9: compute_dataset_stats の計算
# ══════════════════════════════════════════════════════════════════════════════

def test_dataset_stats(tmp_ann_root):
    """compute_dataset_stats が正しく集計する。"""
    from src.annotation.manager import (
        make_annotation, save_annotation, set_annotation_status,
        update_annotation, compute_dataset_stats,
    )

    # confirmed + allowed
    ann1 = make_annotation(job_id="stats_job_1", consent_for_training_data="allowed")
    ann1["event_labels"]["release"]["frame"] = 45
    save_annotation(ann1)
    set_annotation_status(ann1["annotation_id"], "confirmed")

    # draft + unknown
    ann2 = make_annotation(job_id="stats_job_2", consent_for_training_data="unknown")
    save_annotation(ann2)

    # confirmed + denied → export_allowed = 0
    ann3 = make_annotation(job_id="stats_job_3", consent_for_training_data="denied")
    save_annotation(ann3)
    set_annotation_status(ann3["annotation_id"], "confirmed")

    stats = compute_dataset_stats()

    assert stats["total"] == 3
    assert stats["confirmed"] == 2  # ann1, ann3
    assert stats["draft"] == 1       # ann2
    assert stats["training_data_allowed"] == 1  # ann1 only (allowed)
    assert stats["has_release_label"] == 1       # ann1 only
    assert stats["export_allowed"] == 1          # ann1: confirmed + allowed


# ══════════════════════════════════════════════════════════════════════════════
# テスト 10: 既存ジョブデータが壊れないこと
# ══════════════════════════════════════════════════════════════════════════════

def test_existing_job_data_not_broken(tmp_ann_root, tmp_job_dir):
    """アノテーション機能の追加後も既存ジョブの job.json が正常に読めること。"""
    # job.json が存在することを確認
    job_json = tmp_job_dir / "job.json"
    assert job_json.exists()

    job_data = json.loads(job_json.read_text(encoding="utf-8"))
    assert job_data["job_id"] == "test_job_phase11"
    assert "input_file" in job_data

    # generate_annotation_from_job は job.json を壊さない
    from src.annotation.manager import generate_annotation_from_job

    ann = generate_annotation_from_job(tmp_job_dir)
    assert ann is not None
    assert ann["job_id"] == "test_job_phase11"

    # job.json が変更されていないこと
    job_data_after = json.loads(job_json.read_text(encoding="utf-8"))
    assert job_data_after == job_data


# ══════════════════════════════════════════════════════════════════════════════
# テスト 11: create_annotation_draft_for_job は重複作成しない
# ══════════════════════════════════════════════════════════════════════════════

def test_no_duplicate_annotation_draft(tmp_ann_root, tmp_job_dir):
    """create_annotation_draft_for_job を2回呼んでも重複しない。"""
    from src.annotation.manager import create_annotation_draft_for_job, list_annotations

    path1 = create_annotation_draft_for_job(tmp_job_dir)
    path2 = create_annotation_draft_for_job(tmp_job_dir)  # 2回目はスキップ

    anns = list_annotations(job_id_filter="test_job_phase11")
    assert len(anns) == 1, f"重複アノテーションが作成されました: {len(anns)} 件"


# ══════════════════════════════════════════════════════════════════════════════
# テスト 12: SNS許可と教師データ許可は独立したフィールド
# ══════════════════════════════════════════════════════════════════════════════

def test_sns_and_training_consent_are_independent(tmp_ann_root):
    """sns_permission と consent_for_training_data は別フィールド。"""
    from src.annotation.manager import make_annotation, save_annotation, load_annotation

    ann = make_annotation(
        job_id="consent_independence_job",
        consent_for_training_data="denied",
        sns_permission="allowed",
    )
    save_annotation(ann)

    loaded = load_annotation(ann["annotation_id"])
    assert loaded["consent_for_training_data"] == "denied"
    assert loaded["sns_permission"] == "allowed"

    # denied consent + sns_permission=allowed はエクスポートから除外される
    from src.annotation.exporter import _should_export, _load_config
    from src.annotation.manager import set_annotation_status
    set_annotation_status(ann["annotation_id"], "confirmed")

    loaded_confirmed = load_annotation(ann["annotation_id"])
    cfg = _load_config()
    ok, reason = _should_export(loaded_confirmed, cfg)
    assert ok is False
    assert "denied" in reason
