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


def _ensure_video_instruction_pdf(job_dir: Path) -> Optional[Path]:
    """report/video_instruction.pdf を返す。存在しなければ自動生成する。"""
    p = job_dir / "report" / "video_instruction.pdf"
    if p.exists():
        return p
    try:
        from src.video_instruction_pdf_generator import generate_video_instruction_pdf_for_job
        return generate_video_instruction_pdf_for_job(job_dir)
    except Exception as e:
        logger.warning(f"[packager] video_instruction.pdf 生成失敗: {e}")
        return None


def _ensure_athlete_data_sheet_pdf(job_dir: Path) -> Optional[Path]:
    """report/athlete_data_sheet.pdf を返す。存在しなければ自動生成する。"""
    p = job_dir / "report" / "athlete_data_sheet.pdf"
    if p.exists():
        return p
    try:
        from src.athlete_data_sheet_generator import generate_athlete_data_sheet_for_job
        return generate_athlete_data_sheet_for_job(job_dir)
    except Exception as e:
        logger.warning(f"[packager] athlete_data_sheet.pdf 生成失敗: {e}")
        return None


def _ensure_key_frame_sheet_pdf(job_dir: Path) -> Optional[Path]:
    """report/key_frame_sheet.pdf を返す。存在しなければ自動生成する。"""
    p = job_dir / "report" / "key_frame_sheet.pdf"
    if p.exists():
        return p
    try:
        from src.key_frame_sheet_generator import generate_key_frame_sheet_for_job
        return generate_key_frame_sheet_for_job(job_dir)
    except Exception as e:
        logger.warning(f"[packager] key_frame_sheet.pdf 生成失敗: {e}")
        return None


def _ensure_graph_pack_pdf(job_dir: Path) -> Optional[Path]:
    """report/graph_pack.pdf を返す。存在しなければ自動生成する。"""
    p = job_dir / "report" / "graph_pack.pdf"
    if p.exists():
        return p
    try:
        from src.graph_pack_generator import generate_graph_pack_for_job
        return generate_graph_pack_for_job(job_dir)
    except Exception as e:
        logger.warning(f"[packager] graph_pack.pdf 生成失敗: {e}")
        return None


def _ensure_coach_review_sheet_pdf(job_dir: Path) -> Optional[Path]:
    """report/coach_review_sheet.pdf を返す。存在しなければ自動生成する。"""
    p = job_dir / "report" / "coach_review_sheet.pdf"
    if p.exists():
        return p
    try:
        from src.coach_review_sheet_generator import generate_coach_review_sheet_for_job
        return generate_coach_review_sheet_for_job(job_dir)
    except Exception as e:
        logger.warning(f"[packager] coach_review_sheet.pdf 生成失敗: {e}")
        return None


def _generate_readme_txt(job_dir: Path) -> Optional[Path]:
    """deliverables/README.txt を生成して返す（日本語版）。"""
    import json as _json
    from datetime import datetime
    deliv_dir = job_dir / "deliverables"
    deliv_dir.mkdir(parents=True, exist_ok=True)
    out = deliv_dir / "README.txt"
    try:
        job = {}
        ci  = {}
        try:
            job = _json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        try:
            ci = _json.loads((job_dir / "customer_info.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        job_id    = job.get("job_id", job_dir.name)
        name      = ci.get("customer_name") or "—"
        event_str = ci.get("event") or "—"
        now_str   = datetime.now().strftime("%Y/%m/%d %H:%M")
        lines = [
            "ヤリ投げ動画解析 — 成果物パッケージ",
            "Javelin Video Analysis — Delivery Package",
            "=" * 50,
            f"解析ID  : {job_id}",
            f"選手氏名: {name}",
            f"種目    : {event_str}",
            f"出力日時: {now_str}",
            "",
            "【ファイル構成】",
            "",
            "  videos/",
            "    骨格・軌跡・HUD などの解析動画（MP4形式）",
            "    各動画の見方は docs/video_instruction.pdf をご覧ください。",
            "",
            "  frames/",
            "    動作フェーズごとの代表フレーム画像（JPG形式）",
            "",
            "  docs/",
            "    video_instruction.pdf  — 解析動画の見方・各種指標の説明書",
            "",
            "  athlete_data_sheet.pdf",
            "    主要指標をまとめた選手向けサマリーシート。",
            "    手首高さ・速度・重心移動などのハイライトを記載しています。",
            "",
            "  key_frame_sheet.pdf",
            "    動作フェーズ別の重要フレームを一覧表示したシートです。",
            "    フォームの確認・振り返りにお使いください。",
            "",
            "  graph_pack.pdf",
            "    解析グラフを解説付きでまとめた PDF です。",
            "    手首の高さ変化・速度変化・運動連鎖などを収録しています。",
            "",
            "  coach_review_sheet.pdf (フルレポートパッケージのみ)",
            "    コーチ記入用のフェーズ別チェックリスト＆フリーメモ欄です。",
            "",
            "  report.pdf (フルレポートパッケージのみ)",
            "    システムが生成する詳細解析レポートです（A4縦向き）。",
            "",
            "  raw_data/",
            "    pose_landmarks.csv — 全フレームの関節座標データ（生データ）",
            "    analysis_summary.json / valid_segment.json — 解析内部データ",
            "",
            "【ご注意事項】",
            "  ・ 本解析結果は2D動画からの姿勢推定をもとにした参考可視化です。",
            "  ・ 速度・高さ等の数値は撮影条件・推定精度の影響を受ける参考値です。",
            "  ・ 医療判断・怪我の診断・競技選考の代替としてご利用いただけません。",
            "  ・ データの第三者への再配布はご遠慮ください。",
            "",
            "Generated by Javelin Video Analysis System",
            "https://github.com/javelin-video-analysis",
        ]
        out.write_text("\n".join(lines), encoding="utf-8")
        return out
    except Exception as e:
        logger.warning(f"[packager] README.txt 生成失敗: {e}")
        return None


def _ensure_intro_pdf(job_dir: Path) -> Optional[Path]:
    """report/00_最初に読んでください.pdf を返す。存在しなければ自動生成する。"""
    p = job_dir / "report" / "00_最初に読んでください.pdf"
    if p.exists():
        return p
    try:
        from src.intro_pdf_generator import generate_intro_pdf_for_job
        return generate_intro_pdf_for_job(job_dir)
    except Exception as e:
        logger.warning(f"[packager] 00_最初に読んでください.pdf 生成失敗: {e}")
        return None


def _generate_disclaimer_txt(job_dir: Path) -> Optional[Path]:
    """deliverables/disclaimer.txt を生成して返す。"""
    from datetime import datetime
    deliv_dir = job_dir / "deliverables"
    deliv_dir.mkdir(parents=True, exist_ok=True)
    out = deliv_dir / "disclaimer.txt"
    try:
        now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
        lines = [
            "【ご注意事項・免責事項】",
            "=" * 50,
            "",
            "本解析は、動画から取得した姿勢推定データをもとにした参考資料です。",
            "競技指導、医療判断、怪我の診断を代替するものではありません。",
            "最終的な練習内容や技術判断は、指導者・専門家と相談しながら行ってください。",
            "",
            "・ 解析に使用するAI姿勢推定は、撮影条件の影響を受けます。",
            "  数値や骨格ラインは参考値としてご理解ください。",
            "・ 本解析データおよびPDFの第三者への再配布・商用利用はご遠慮ください。",
            "・ 解析結果に基づく判断による損害について、当サービスは責任を負いかねます。",
            "",
            f"発行日時: {now_str}",
            "Generated by Javelin Video Analysis System",
        ]
        out.write_text("\n".join(lines), encoding="utf-8")
        return out
    except Exception as e:
        logger.warning(f"[packager] disclaimer.txt 生成失敗: {e}")
        return None


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
        00_最初に読んでください.pdf
        01_解析動画/ (プレビュー用 MP4)
        解析動画の見方.pdf
        02_代表フレーム画像/ (先頭3枚)
        99_注意事項/disclaimer.txt

    【data_sheet_package.zip】
        00_最初に読んでください.pdf
        01_解析動画/ (全 MP4)
        解析動画の見方.pdf
        02_選手向けサマリー/ (athlete_data_sheet・key_frame_sheet・graph_pack)
        03_代表フレーム画像/ (全フレーム)
        04_研究・開発用データ/ (pose_landmarks.csv)
        99_注意事項/disclaimer.txt

    【full_report_package.zip】
        00_最初に読んでください.pdf
        report.pdf
        01_解析動画/ (全 MP4)
        解析動画の見方.pdf
        02_選手向けサマリー/ (athlete_data_sheet・key_frame_sheet・graph_pack)
        03_コーチ向け/ (coach_review_sheet)
        04_代表フレーム画像/ (全フレーム)
        05_研究・開発用データ/ (CSV・JSON)
        99_注意事項/disclaimer.txt

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ（例: jobs/20260508_181930_c4bd）

    Returns
    -------
    dict[str, Path]
        生成された ZIP の辞書。
        キー: "free_preview" / "data_sheet_package" / "full_report_package"
    """
    job_dir = Path(job_dir)
    deliv_dir = job_dir / "deliverables"

    # ── 素材収集 ────────────────────────────────────────────────────────────
    preview_mp4s      = _collect_preview_mp4s(job_dir)
    frame_images      = _collect_frame_images(job_dir)
    graph_images      = _collect_graph_images(job_dir)
    csv_path          = _collect_csv(job_dir)
    pdf_path          = _collect_pdf(job_dir)
    all_mp4s          = _collect_all_mp4s(job_dir)
    intro_pdf         = _ensure_intro_pdf(job_dir)
    instr_pdf_path    = _ensure_video_instruction_pdf(job_dir)
    athlete_pdf       = _ensure_athlete_data_sheet_pdf(job_dir)
    key_frame_pdf     = _ensure_key_frame_sheet_pdf(job_dir)
    graph_pack_pdf    = _ensure_graph_pack_pdf(job_dir)
    coach_review_pdf  = _ensure_coach_review_sheet_pdf(job_dir)
    disclaimer_txt    = _generate_disclaimer_txt(job_dir)
    # 後方互換: README.txt も生成しておく
    _generate_readme_txt(job_dir)

    result: Dict[str, Path] = {}
    deliverables_rel: Dict[str, str] = {}

    # ── free_preview.zip ──────────────────────────────────────────────────────
    try:
        entries: List[Tuple[Path, str]] = []
        if intro_pdf:
            entries.append((intro_pdf,     "00_最初に読んでください.pdf"))
        if instr_pdf_path:
            entries.append((instr_pdf_path, "解析動画の見方.pdf"))
        for p in preview_mp4s:
            entries.append((p, f"01_解析動画/{p.name}"))
        for p in frame_images[:3]:
            entries.append((p, f"02_代表フレーム画像/{p.name}"))
        if disclaimer_txt:
            entries.append((disclaimer_txt, "99_注意事項/注意事項.txt"))

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
        if intro_pdf:
            entries.append((intro_pdf,     "00_最初に読んでください.pdf"))
        if instr_pdf_path:
            entries.append((instr_pdf_path, "解析動画の見方.pdf"))
        for p in all_mp4s:
            entries.append((p, f"01_解析動画/{p.name}"))
        if athlete_pdf:
            entries.append((athlete_pdf,   "02_選手向けサマリー/選手向けサマリー.pdf"))
        if key_frame_pdf:
            entries.append((key_frame_pdf, "02_選手向けサマリー/代表フレームシート.pdf"))
        if graph_pack_pdf:
            entries.append((graph_pack_pdf,"02_選手向けサマリー/グラフ解説.pdf"))
        for p in frame_images:
            entries.append((p, f"03_代表フレーム画像/{p.name}"))
        if csv_path:
            entries.append((csv_path, "04_研究・開発用データ/pose_landmarks.csv"))
        if disclaimer_txt:
            entries.append((disclaimer_txt, "99_注意事項/注意事項.txt"))

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
        if intro_pdf:
            entries.append((intro_pdf,     "00_最初に読んでください.pdf"))
        if pdf_path:
            entries.append((pdf_path,      "report.pdf"))
        if instr_pdf_path:
            entries.append((instr_pdf_path, "解析動画の見方.pdf"))
        for p in all_mp4s:
            entries.append((p, f"01_解析動画/{p.name}"))
        if athlete_pdf:
            entries.append((athlete_pdf,   "02_選手向けサマリー/選手向けサマリー.pdf"))
        if key_frame_pdf:
            entries.append((key_frame_pdf, "02_選手向けサマリー/代表フレームシート.pdf"))
        if graph_pack_pdf:
            entries.append((graph_pack_pdf,"02_選手向けサマリー/グラフ解説.pdf"))
        if coach_review_pdf:
            entries.append((coach_review_pdf, "03_コーチ向け/コーチ向けレビューシート.pdf"))
        for p in frame_images:
            entries.append((p, f"04_代表フレーム画像/{p.name}"))
        if csv_path:
            entries.append((csv_path, "05_研究・開発用データ/pose_landmarks.csv"))
        summary_json = job_dir / "report" / "analysis_summary.json"
        if summary_json.exists():
            entries.append((summary_json,  "05_研究・開発用データ/analysis_summary.json"))
        vs_json = job_dir / "report" / "valid_segment.json"
        if vs_json.exists():
            entries.append((vs_json,       "05_研究・開発用データ/valid_segment.json"))
        for p in graph_images:
            entries.append((p, f"05_研究・開発用データ/グラフ画像/{p.name}"))
        if disclaimer_txt:
            entries.append((disclaimer_txt, "99_注意事項/注意事項.txt"))

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
