"""
tests/test_video_instruction_pdf_generator.py

解析動画 説明書 PDF 生成のユニットテスト。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from src.video_instruction_pdf_generator import generate_video_instruction_pdf_for_job


# ── フィクスチャ ─────────────────────────────────────────────────────────────

def _make_job_dir(tmp_path: Path, *, mp4_stems: list[str] | None = None) -> Path:
    """テスト用のダミー job ディレクトリを作成して返す。"""
    job_dir = tmp_path / "test_job"
    output_dir = job_dir / "output"
    report_dir = job_dir / "report"
    output_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)

    # job.json
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "job_id": "test_job",
                "status": "completed",
                "created_at": "2026-05-10T00:00:00",
                "updated_at": "2026-05-10T00:01:00",
                "height_m": 1.75,
                "mode": "all_variants",
                "input_file": str(job_dir / "input" / "original.mp4"),
                "output_files": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # analysis_summary.json（旧形式）
    (report_dir / "analysis_summary.json").write_text(
        json.dumps(
            {
                "status": "ok",
                "generated_at": "2026-05-10T00:01:00",
                "total_frames": 249,
                "duration_sec": 8.27,
                "fps_estimated": 29.99,
                "dominant_hand": "right",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # *_report.json（最初の1本分）
    rep_data = {
        "generated_at": "2026-05-10T00:01:00",
        "video_info": {
            "width": 1280,
            "height": 720,
            "fps": 29.988,
            "total_frames": 249,
            "duration_s": 8.3,
        },
        "analysis": {
            "height_m": 1.75,
            "pose_detected_frames": 200,
            "pose_detection_rate": 0.80,
            "wrist_max_speed_kmh": 72.3,
        },
    }
    (output_dir / "analysis_original_skeleton_report.json").write_text(
        json.dumps(rep_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # MP4 ダミーファイルを作成
    _all_stems = [
        "analysis_original_skeleton",
        "analysis_original_vectors",
        "analysis_original_stickman",
        "analysis_original_hud",
        "analysis_original_analysis",
    ]
    stems_to_create = mp4_stems if mp4_stems is not None else _all_stems
    for stem in stems_to_create:
        (output_dir / f"{stem}.mp4").write_bytes(b"\x00" * 16)  # ダミーバイト

    return job_dir


# ── テスト ────────────────────────────────────────────────────────────────────

def test_pdf_generated(tmp_path: Path) -> None:
    """video_instruction.pdf が生成されることを確認する。"""
    job_dir = _make_job_dir(tmp_path)
    pdf_path = generate_video_instruction_pdf_for_job(job_dir)

    assert pdf_path.exists(), "PDFファイルが存在すること"
    assert pdf_path.stat().st_size > 0, "PDFファイルのサイズが0より大きいこと"
    assert pdf_path == job_dir / "report" / "video_instruction.pdf"


def test_pdf_output_path(tmp_path: Path) -> None:
    """出力先が report/video_instruction.pdf であることを確認する。"""
    job_dir = _make_job_dir(tmp_path)
    pdf_path = generate_video_instruction_pdf_for_job(job_dir)
    assert pdf_path.parent.name == "report"
    assert pdf_path.name == "video_instruction.pdf"


def test_five_videos_label(tmp_path: Path, capsys) -> None:
    """5本の動画が存在するとき、PDF生成が成功することを確認する。

    ※ PDF本文の「以下の5本」テキスト検証は、バイナリ埋め込みのため
       ここでは生成成功（例外なし）のみを確認する。
    """
    job_dir = _make_job_dir(tmp_path)  # デフォルトで5本作成
    pdf_path = generate_video_instruction_pdf_for_job(job_dir)
    assert pdf_path.exists()


def test_partial_videos_no_error(tmp_path: Path) -> None:
    """動画が一部欠けていてもPDF生成が失敗しないことを確認する。"""
    job_dir = _make_job_dir(
        tmp_path,
        mp4_stems=["analysis_original_skeleton", "analysis_original_hud"],  # 2本だけ
    )
    # 例外が起きないこと
    pdf_path = generate_video_instruction_pdf_for_job(job_dir)
    assert pdf_path.exists()


def test_no_videos_no_error(tmp_path: Path) -> None:
    """動画が1本もなくてもPDF生成が失敗しないことを確認する。"""
    job_dir = _make_job_dir(tmp_path, mp4_stems=[])
    pdf_path = generate_video_instruction_pdf_for_job(job_dir)
    assert pdf_path.exists()


def test_missing_job_json_no_error(tmp_path: Path) -> None:
    """job.json が存在しなくてもPDF生成が失敗しないことを確認する。"""
    job_dir = _make_job_dir(tmp_path)
    (job_dir / "job.json").unlink()
    pdf_path = generate_video_instruction_pdf_for_job(job_dir)
    assert pdf_path.exists()


def test_missing_summary_no_error(tmp_path: Path) -> None:
    """analysis_summary.json が存在しなくてもPDF生成が失敗しないことを確認する。"""
    job_dir = _make_job_dir(tmp_path)
    (job_dir / "report" / "analysis_summary.json").unlink()
    pdf_path = generate_video_instruction_pdf_for_job(job_dir)
    assert pdf_path.exists()


def test_regenerate_overwrites(tmp_path: Path) -> None:
    """2回生成した場合も上書きで成功することを確認する。"""
    job_dir = _make_job_dir(tmp_path)
    pdf1 = generate_video_instruction_pdf_for_job(job_dir)
    mtime1 = pdf1.stat().st_mtime

    import time
    time.sleep(0.05)

    pdf2 = generate_video_instruction_pdf_for_job(job_dir)
    mtime2 = pdf2.stat().st_mtime

    assert pdf1 == pdf2
    assert mtime2 >= mtime1


# ── ZIP 同梱テスト ────────────────────────────────────────────────────────────

def test_all_zips_contain_instruction_pdf(tmp_path: Path) -> None:
    """3種類すべてのZIPに video_instruction.pdf が含まれることを確認する。"""
    from src.deliverable_packager import create_deliverable_packages_for_job

    job_dir = _make_job_dir(tmp_path)

    # report.pdf ダミーを作成（full_report 用）
    (job_dir / "report" / "report.pdf").write_bytes(b"%PDF-1.4 dummy")

    # CSV ダミー
    (job_dir / "report" / "pose_landmarks.csv").write_text(
        "frame,x,y\n0,0.5,0.5\n", encoding="utf-8"
    )

    zips = create_deliverable_packages_for_job(job_dir)

    instr_arc_name = "docs/video_instruction.pdf"

    for zip_key in ("free_preview", "data_sheet_package", "full_report_package"):
        assert zip_key in zips, f"{zip_key} が生成されていること"
        zip_path = zips[zip_key]
        assert zip_path.exists(), f"{zip_key}.zip が存在すること"
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert instr_arc_name in names, (
                f"{zip_key}.zip に {instr_arc_name} が含まれていること。"
                f"実際の内容: {names}"
            )
