"""
deliverable_packager.py — Javelin Video Analysis 納品用ZIPパッケージ生成

3種類の ZIP を jobs/<job_id>/deliverables/ に生成する。

Usage:
    from src.deliverable_packager import create_deliverable_packages_for_job
    zips = create_deliverable_packages_for_job(Path("jobs/20260508_181930_c4bd"))
    # -> {
    #      "free_preview":          Path(".../deliverables/free_preview.zip"),
    #      "data_sheet_package":    Path(".../deliverables/data_sheet_package.zip"),
    #      "full_report_package":   Path(".../deliverables/full_report_package.zip"),
    #    }
"""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 無料プレビュー動画と判定するファイル名キーワード
_PREVIEW_KEYWORDS = {
    "skeleton", "trail", "heatmap", "hud", "stickman", "vectors", "gaming",
}


# ── ファイル収集ヘルパー ────────────────────────────────────────────────────────

def _collect_preview_mp4s(job_dir: Path) -> List[Path]:
    """output/ 配下からプレビュー用 MP4 を収集する。"""
    output_dir = job_dir / "output"
    if not output_dir.exists():
        return []
    return sorted(
        p for p in output_dir.glob("*.mp4")
        if any(kw in p.name.lower() for kw in _PREVIEW_KEYWORDS)
    )


def _collect_frame_images(job_dir: Path) -> List[Path]:
    """report/frames/ 配下の代表フレーム画像を収集する。"""
    frames_dir = job_dir / "report" / "frames"
    if not frames_dir.exists():
        return []
    return sorted(
        list(frames_dir.glob("*.jpg"))
        + list(frames_dir.glob("*.jpeg"))
        + list(frames_dir.glob("*.png"))
    )


def _collect_graph_images(job_dir: Path) -> List[Path]:
    """report/graphs/ 配下のグラフ画像を収集する。"""
    graphs_dir = job_dir / "report" / "graphs"
    if not graphs_dir.exists():
        return []
    return sorted(graphs_dir.glob("*.png"))


def _collect_csv(job_dir: Path) -> Optional[Path]:
    """report/pose_landmarks.csv を返す（なければ None）。"""
    p = job_dir / "report" / "pose_landmarks.csv"
    return p if p.exists() else None


def _collect_pdf(job_dir: Path) -> Optional[Path]:
    """report/report.pdf を返す（なければ None）。"""
    p = job_dir / "report" / "report.pdf"
    return p if p.exists() else None


def _collect_all_mp4s(job_dir: Path) -> List[Path]:
    """output/ 配下の全 MP4 を収集する。"""
    output_dir = job_dir / "output"
    if not output_dir.exists():
        return []
    return sorted(output_dir.glob("*.mp4"))


# ── ZIP 書き込み ────────────────────────────────────────────────────────────────

def _write_zip(zip_path: Path, entries: List[Tuple[Path, str]]) -> Path:
    """
    ZIP ファイルを書き込む。

    Parameters
    ----------
    zip_path : Path
        出力先 ZIP ファイルパス
    entries : list of (src_path, arcname)
        存在しない src_path はスキップされる

    Returns
    -------
    Path
        zip_path をそのまま返す
    """
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, arcname in entries:
            if not src.exists():
                logger.warning(f"[packager] Skip (not found): {src}")
                continue
            zf.write(src, arcname)
            count += 1
    logger.info(f"[packager] ZIP created ({count} files): {zip_path}")
    return zip_path


# ── report.json 更新 ─────────────────────────────────────────────────────────────

def _update_report_json(job_dir: Path, deliverables_rel: Dict[str, str]) -> None:
    """
    output/ 配下の最新 *_report.json に deliverables フィールドを追記する。
    失敗しても例外を外に投げない（警告のみ）。
    """
    output_dir = job_dir / "output"
    if not output_dir.exists():
        return
    rep_jsons = sorted(output_dir.glob("*_report.json"))
    if not rep_jsons:
        return
    rep_path = rep_jsons[-1]
    try:
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        rep["deliverables"] = deliverables_rel
        rep_path.write_text(
            json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"[packager] deliverables written to {rep_path.name}")
    except Exception as e:
        logger.warning(f"[packager] Failed to update report.json: {e}")


# ── メインエントリポイント ────────────────────────────────────────────────────────

def create_deliverable_packages_for_job(job_dir: Path) -> Dict[str, Path]:
    """
    3 種類の納品用 ZIP を生成して返す。

    【free_preview.zip】
        プレビュー用 MP4 + 代表フレーム先頭3枚

    【data_sheet_package.zip】
        pose_landmarks.csv + グラフ画像 + 全代表フレーム

    【full_report_package.zip】
        report.pdf + pose_landmarks.csv + グラフ画像 + 全代表フレーム + 全出力 MP4

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ（例: jobs/20260508_181930_c4bd）

    Returns
    -------
    dict[str, Path]
        生成された ZIP の辞書。生成されなかったキーは含まれない。
        キー: "free_preview" / "data_sheet_package" / "full_report_package"
    """
    job_dir = Path(job_dir)
    deliv_dir = job_dir / "deliverables"

    # ── 素材収集 ────────────────────────────────────────────────────────────
    preview_mp4s = _collect_preview_mp4s(job_dir)
    frame_images = _collect_frame_images(job_dir)
    graph_images = _collect_graph_images(job_dir)
    csv_path     = _collect_csv(job_dir)
    pdf_path     = _collect_pdf(job_dir)
    all_mp4s     = _collect_all_mp4s(job_dir)

    result: Dict[str, Path] = {}
    deliverables_rel: Dict[str, str] = {}

    # ── free_preview.zip ──────────────────────────────────────────────────────
    try:
        entries: List[Tuple[Path, str]] = []
        for p in preview_mp4s:
            entries.append((p, f"videos/{p.name}"))
        for p in frame_images[:3]:            # 代表フレーム先頭3枚
            entries.append((p, f"frames/{p.name}"))

        if entries:
            zp = _write_zip(deliv_dir / "free_preview.zip", entries)
            result["free_preview"] = zp
            deliverables_rel["free_preview_zip"] = "deliverables/free_preview.zip"
        else:
            logger.info("[packager] free_preview.zip: no files to include, skipped")
    except Exception as e:
        logger.warning(f"[packager] free_preview.zip failed: {e}")

    # ── data_sheet_package.zip ───────────────────────────────────────────────
    try:
        entries = []
        if csv_path:
            entries.append((csv_path, "pose_landmarks.csv"))
        for p in graph_images:
            entries.append((p, f"graphs/{p.name}"))
        for p in frame_images:
            entries.append((p, f"frames/{p.name}"))

        if entries:
            zp = _write_zip(deliv_dir / "data_sheet_package.zip", entries)
            result["data_sheet_package"] = zp
            deliverables_rel["data_sheet_package_zip"] = "deliverables/data_sheet_package.zip"
        else:
            logger.info("[packager] data_sheet_package.zip: no files to include, skipped")
    except Exception as e:
        logger.warning(f"[packager] data_sheet_package.zip failed: {e}")

    # ── full_report_package.zip ───────────────────────────────────────────────
    try:
        entries = []
        if pdf_path:
            entries.append((pdf_path, "report.pdf"))
        if csv_path:
            entries.append((csv_path, "pose_landmarks.csv"))
        for p in graph_images:
            entries.append((p, f"graphs/{p.name}"))
        for p in frame_images:
            entries.append((p, f"frames/{p.name}"))
        for p in all_mp4s:
            entries.append((p, f"videos/{p.name}"))

        if entries:
            zp = _write_zip(deliv_dir / "full_report_package.zip", entries)
            result["full_report_package"] = zp
            deliverables_rel["full_report_package_zip"] = "deliverables/full_report_package.zip"
        else:
            logger.info("[packager] full_report_package.zip: no files to include, skipped")
    except Exception as e:
        logger.warning(f"[packager] full_report_package.zip failed: {e}")

    # ── report.json に deliverables 追記 ────────────────────────────────────
    if deliverables_rel:
        _update_report_json(job_dir, deliverables_rel)

    return result
