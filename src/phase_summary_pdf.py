"""
src/phase_summary_pdf.py — Javelin Video Analysis フェーズ別サマリー PDF 生成

指定ジョブのフェーズ別フレーム画像・アノテーション情報を元に
フェーズ別サマリー PDF を生成する。

出力先: job_dir/report/phase_summary.pdf

Usage:
    from src.phase_summary_pdf import generate_phase_summary_pdf
    from pathlib import Path

    pdf_path = generate_phase_summary_pdf(Path("jobs/20260508_070156_518a"))
    # -> Path("jobs/20260508_070156_518a/report/phase_summary.pdf")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.pdf_styles import (
    BRAND_BLUE,
    MID_GRAY,
    get_font,
    get_styles,
    make_header_footer,
    safe_text,
    scale_image,
    disclaimer_block,
    hr,
    section_spacer,
    para_spacer,
    title_block,
)

logger = logging.getLogger("javelin.phase_summary_pdf")

_PAGE_W, _PAGE_H = A4
_MARGIN = 2.0 * cm
_CONTENT_W = _PAGE_W - 2 * _MARGIN
_IMG_MAX_W = _CONTENT_W * 0.85
_IMG_MAX_H = 8 * cm


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as _e:
        logger.warning("[phase_summary_pdf] JSON 読み込み失敗: %s — %s", path, _e)
        return None


def _fmt_sec(sec) -> str:
    """秒数を「X.XX 秒」形式に変換。"""
    if sec is None:
        return "—"
    try:
        return f"{float(sec):.2f} 秒"
    except (TypeError, ValueError):
        return "—"


def _fmt_frame(frame) -> str:
    if frame is None:
        return "—"
    return str(int(frame))


def _build_phase_entry(
    phase_key: str,
    phase_def: dict,
    phase_frames: dict,
    phase_img_dir: Path,
    styles: dict,
    is_range: bool,
    detection_phase: dict | None = None,
) -> list:
    """フェーズ1件分の Flowable リストを返す。"""
    font_b = get_font(bold=True)
    font_r = get_font(bold=False)
    label = safe_text(phase_def.get("label", phase_key))
    desc = safe_text(phase_def.get("description", ""))
    key_points: list[str] = phase_def.get("key_points") or []

    # --- フレーム番号 / 秒数 ------------------------------------------------
    if is_range:
        start_frame = phase_frames.get(f"{phase_key}_start_frame")
        end_frame = phase_frames.get(f"{phase_key}_end_frame")
        fps = phase_frames.get("fps")
        start_sec = phase_frames.get(f"{phase_key}_start_sec")
        end_sec = phase_frames.get(f"{phase_key}_end_sec")
        frame_info = (
            f"開始: {_fmt_frame(start_frame)} フレーム ({_fmt_sec(start_sec)})　"
            f"終了: {_fmt_frame(end_frame)} フレーム ({_fmt_sec(end_sec)})"
        )
        img_stems = [f"{phase_key}_start", f"{phase_key}_end"]
    else:
        frame_no = phase_frames.get(f"{phase_key}_frame")
        sec = phase_frames.get(f"{phase_key}_sec")
        frame_info = f"{_fmt_frame(frame_no)} フレーム ({_fmt_sec(sec)})"
        img_stems = [phase_key]

    # --- 代表フレーム画像の収集 ----------------------------------------------
    img_paths: list[Path] = []
    for stem in img_stems:
        p = phase_img_dir / f"phase_{stem}.jpg"
        if p.exists():
            img_paths.append(p)

    # --- Flowable 構築 -------------------------------------------------------
    elems: list = []

    # セクション見出し
    elems.append(
        Paragraph(
            f'<font name="{font_b}" size="13" color="{BRAND_BLUE}">{label}</font>',
            styles.get("h2") or styles.get("Normal"),  # type: ignore[arg-type]
        )
    )
    elems.append(Paragraph(frame_info, styles.get("caption") or styles.get("Normal")))  # type: ignore[arg-type]

    # Phase 10: 自動推定候補の情報（存在する場合）
    if detection_phase and detection_phase.get("frame") is not None:
        _det_clbl   = safe_text(detection_phase.get("confidence_label", "—"))
        _det_method = safe_text(detection_phase.get("method", "—"))
        _det_reason = safe_text(detection_phase.get("reason", ""))
        _det_warn   = detection_phase.get("warning")
        _det_frame  = detection_phase.get("frame")
        _auto_text = (
            f'<font name="{get_font(bold=False)}" size="8" color="#888888">'
            f'【自動推定候補】フレーム {_det_frame} / {_det_clbl} / 手法: {_det_method}<br/>'
            f'候補として自動抽出されました。参考値のため、管理者が確認してください。<br/>'
            f'{_det_reason[:120]}'
            f'</font>'
        )
        elems.append(Paragraph(_auto_text, styles.get("caption") or styles.get("Normal")))
        if _det_warn:
            _warn_text = (
                f'<font name="{get_font(bold=False)}" size="7.5" color="#CC4400">'
                f'⚠️ {safe_text(_det_warn[:150])}'
                f'</font>'
            )
            elems.append(Paragraph(_warn_text, styles.get("caption") or styles.get("Normal")))

    elems.append(para_spacer())
    elems.append(Paragraph(desc, styles.get("body") or styles.get("Normal")))  # type: ignore[arg-type]

    # 確認ポイント
    if key_points:
        elems.append(para_spacer())
        elems.append(
            Paragraph(
                f'<font name="{font_b}">確認ポイント</font>',
                styles.get("body") or styles.get("Normal"),
            )
        )
        for pt in key_points:
            elems.append(
                Paragraph(
                    f'　• {safe_text(pt)}',
                    styles.get("body") or styles.get("Normal"),
                )
            )

    # 代表フレーム画像
    if img_paths:
        elems.append(para_spacer())
        img_row: list = []
        for img_path in img_paths:
            try:
                iw, ih = scale_image(img_path, _IMG_MAX_W / max(1, len(img_paths)), _IMG_MAX_H)
                img_row.append(Image(str(img_path), width=iw, height=ih))
            except Exception as _e:
                logger.warning("[phase_summary_pdf] 画像読み込み失敗: %s — %s", img_path, _e)

        if len(img_row) == 1:
            elems.append(img_row[0])
        elif len(img_row) >= 2:
            # 2 枚並べる
            col_w = _CONTENT_W / len(img_row)
            tdata = [img_row]
            t = Table(tdata, colWidths=[col_w] * len(img_row))
            t.setStyle(
                TableStyle([
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ])
            )
            elems.append(t)
    elif not img_paths:
        elems.append(para_spacer())
        elems.append(
            Paragraph(
                "（代表フレーム画像は未生成です）",
                styles.get("caption") or styles.get("Normal"),
            )
        )

    elems.append(section_spacer())
    elems.append(hr())
    elems.append(section_spacer())

    return elems


def generate_phase_summary_pdf(job_dir: Path) -> Path:
    """フェーズ別サマリー PDF を生成して保存し、Path を返す。

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ

    Returns
    -------
    Path
        生成された PDF のパス（ job_dir/report/phase_summary.pdf ）

    Raises
    ------
    RuntimeError
        PDF 生成に失敗した場合
    """
    from src.phase_loader import load_phases, get_all_phase_keys

    job_dir = Path(job_dir)

    # ジョブ情報読み込み
    job_json = _load_json(job_dir / "job.json") or {}
    job_id = job_json.get("job_id", job_dir.name)

    # フェーズフレーム情報読み込み
    phase_frames = _load_json(job_dir / "phase_frames.json") or {}

    # フェーズ定義
    phases = load_phases()
    phase_keys = get_all_phase_keys()

    # 代表フレーム画像ディレクトリ
    phase_img_dir = job_dir / "report" / "phase_frames"

    # Phase 10: 自動フェーズ推定結果（存在する場合に PDF に反映）
    detection_result = _load_json(job_dir / "report" / "phase_detection_result.json") or {}
    detection_phases = detection_result.get("phases", {}) if detection_result.get("status") == "ok" else {}

    # 出力先
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "phase_summary.pdf"

    # スタイル設定
    styles = get_styles()

    # --- ドキュメント構築 ---------------------------------------------------
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        rightMargin=_MARGIN,
        leftMargin=_MARGIN,
        topMargin=_MARGIN + 1.2 * cm,
        bottomMargin=_MARGIN + 1.0 * cm,
        title=f"フェーズ別解析サマリー — {job_id}",
        author="Javelin Video Analysis",
        subject="フェーズ別動作解析サマリー",
    )

    on_page = make_header_footer("フェーズ別解析サマリー")

    story: list = []

    # タイトルブロック
    story += title_block(
        title_ja="フェーズ別解析サマリー",
        subtitle_en="Phase-by-Phase Analysis Summary",
        info_line=f"Job ID: {job_id}　生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        styles=styles,
    )
    story.append(section_spacer())

    # 注意書き
    font_r = get_font(bold=False)
    story.append(
        Paragraph(
            f'<font name="{font_r}" size="9" color="#555555">'
            "このサマリーは投てき動作の各フェーズを動画フレームで確認するための参考資料です。"
            "フェーズ境界は管理者が手動で設定した概算値であり、"
            "実際の動作と一致しない場合があります。"
            "</font>",
            styles.get("caption") or styles.get("Normal"),
        )
    )
    story.append(section_spacer())
    story.append(hr())
    story.append(section_spacer())

    # フェーズごとに出力（phase_def は取得済みなので is_range_phase() を再呼び出しせず直接参照）
    for phase_key in phase_keys:
        phase_def = phases.get(phase_key, {})
        if not phase_def:
            continue
        entry = _build_phase_entry(
            phase_key=phase_key,
            phase_def=phase_def,
            phase_frames=phase_frames,
            phase_img_dir=phase_img_dir,
            styles=styles,
            is_range=bool(phase_def.get("is_range", True)),
            detection_phase=detection_phases.get(phase_key),
        )
        story.extend(entry)

    # 免責事項
    story.append(PageBreak())
    story += disclaimer_block(styles)

    # PDF 書き出し
    try:
        doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
        logger.info("[phase_summary_pdf] 生成完了: %s", out_path)
    except Exception as _e:
        logger.error("[phase_summary_pdf] PDF 生成失敗: %s", _e)
        raise RuntimeError(f"phase_summary_pdf 生成失敗: {_e}") from _e

    return out_path
