"""
src/comparison_report_pdf.py — Javelin Video Analysis 2動画比較レポート PDF 生成

2本の動画ジョブを比較し、フェーズ別並置画像・差分メトリクス・グラフを
1つの PDF にまとめる。

すべての説明は非断定的な表現を使用する（「〜ように見えます」「〜可能性があります」等）。

出力先: comparisons/<comparison_id>/comparison_report.pdf

Usage:
    from src.comparison_report_pdf import generate_comparison_report_pdf
    from pathlib import Path

    pdf_path = generate_comparison_report_pdf(
        comparison_dir=Path("comparisons/20260510_012144_cmp"),
        job_dir_a=Path("jobs/20260508_054525_147f"),
        job_dir_b=Path("jobs/20260508_054854_fffe"),
    )
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
    BRAND_ORANGE,
    MID_GRAY,
    LIGHT_GRAY,
    CARD_BG,
    TEXT_DARK,
    TEXT_GRAY,
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
    kv_table,
    warn_box,
)

logger = logging.getLogger("javelin.comparison_report_pdf")

_PAGE_W, _PAGE_H = A4
_MARGIN = 2.0 * cm
_CONTENT_W = _PAGE_W - 2 * _MARGIN
_COL_W = (_CONTENT_W - 0.5 * cm) / 2   # 2列の幅
_IMG_MAX_H = 7.5 * cm


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as _e:
        logger.warning("[comparison_report] JSON 読み込み失敗: %s — %s", path, _e)
        return None


def _fmt_val(val) -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        return f"{val:.3f}"
    return str(val)


def _fmt_diff(diff) -> str:
    if diff is None:
        return "—"
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.3f}"


# _PHASE_KEYS_ORDERED / _PHASE_IS_RANGE はモジュールトップには置かない。
# 実行時に src.phase_loader から取得して使う（phases.yaml と一致を保証）。


def _get_phase_img_stems(phase_key: str, is_range: bool) -> list[str]:
    if is_range:
        return [f"{phase_key}_start", f"{phase_key}_end"]
    return [phase_key]


def _phase_compare_section(
    phase_key: str,
    phase_def: dict,
    phase_img_dir_a: Path,
    phase_img_dir_b: Path,
    label_a: str,
    label_b: str,
    styles: dict,
) -> list:
    """フェーズ1件の並置比較セクションを返す。"""
    font_b = get_font(bold=True)
    font_r = get_font(bold=False)
    label = safe_text(phase_def.get("label", phase_key))
    key_points: list[str] = phase_def.get("key_points") or []

    stems = _get_phase_img_stems(phase_key, is_range=bool(phase_def.get("is_range", True)))
    elems: list = []

    elems.append(
        Paragraph(
            f'<font name="{font_b}" size="12" color="{BRAND_BLUE}">{label}</font>',
            styles.get("h2") or styles.get("Normal"),
        )
    )
    elems.append(para_spacer())

    # 各ポイントで A vs B を並置
    for stem in stems:
        img_a = phase_img_dir_a / f"phase_{stem}.jpg"
        img_b = phase_img_dir_b / f"phase_{stem}.jpg"

        # ラベル（開始/終了/単体）
        suffix_label = ""
        if stem.endswith("_start"):
            suffix_label = "（開始フレーム）"
        elif stem.endswith("_end"):
            suffix_label = "（終了フレーム）"

        cells_img: list = []
        cells_lbl: list = []

        for img_path, side_label in [(img_a, label_a), (img_b, label_b)]:
            cap = f'<font name="{font_b}" size="9">{safe_text(side_label)}{suffix_label}</font>'
            cells_lbl.append(Paragraph(cap, styles.get("caption") or styles.get("Normal")))
            if img_path.exists():
                try:
                    iw, ih = scale_image(img_path, _COL_W - 0.3 * cm, _IMG_MAX_H)
                    cells_img.append(Image(str(img_path), width=iw, height=ih))
                except Exception as _e:
                    logger.warning("[comparison_report] 画像読み込み失敗: %s — %s", img_path, _e)
                    cells_img.append(
                        Paragraph("（画像なし）", styles.get("caption") or styles.get("Normal"))
                    )
            else:
                cells_img.append(
                    Paragraph("（画像なし）", styles.get("caption") or styles.get("Normal"))
                )

        tbl = Table(
            [cells_lbl, cells_img],
            colWidths=[_COL_W, _COL_W],
        )
        tbl.setStyle(
            TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("BOX", (0, 0), (-1, -1), 0.5, MID_GRAY),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, MID_GRAY),
                ("BACKGROUND", (0, 0), (-1, 0), CARD_BG),
            ])
        )
        elems.append(KeepTogether([tbl]))
        elems.append(para_spacer())

    # 確認ポイント
    if key_points:
        pts_text = "　".join(f"• {safe_text(pt)}" for pt in key_points)
        elems.append(
            Paragraph(
                f'<font name="{font_r}" size="9" color="#555555">'
                f'確認ポイント: {pts_text}</font>',
                styles.get("caption") or styles.get("Normal"),
            )
        )
        elems.append(para_spacer())

    # 非断定コメント（テンプレート）
    elems.append(
        Paragraph(
            f'<font name="{font_r}" size="9" color="#666666">'
            "上記の画像は参考情報です。動作の違いは角度・タイミング・個人差などにより生じる場合があります。"
            "専門的なコーチングや医療的判断の代替として使用しないでください。"
            "</font>",
            styles.get("caption") or styles.get("Normal"),
        )
    )
    elems.append(section_spacer())
    elems.append(hr())
    elems.append(section_spacer())

    return elems


def _metrics_compare_section(
    comparison_summary: dict,
    label_a: str,
    label_b: str,
    styles: dict,
) -> list:
    """差分メトリクス比較テーブルを返す。"""
    font_b = get_font(bold=True)
    font_r = get_font(bold=False)
    fields: dict = comparison_summary.get("fields", {})
    if not fields:
        return []

    elems: list = []
    elems.append(
        Paragraph(
            f'<font name="{font_b}" size="12" color="{BRAND_BLUE}">数値比較</font>',
            styles.get("h2") or styles.get("Normal"),
        )
    )
    elems.append(para_spacer())
    elems.append(
        Paragraph(
            f'<font name="{font_r}" size="9" color="#555555">'
            "以下の数値は解析から得られた参考値です。動画の撮影条件・解析精度により差異が生じる可能性があります。"
            "</font>",
            styles.get("caption") or styles.get("Normal"),
        )
    )
    elems.append(para_spacer())

    header_row = [
        Paragraph(f'<font name="{font_b}" size="9">指標</font>', styles.get("caption") or styles.get("Normal")),
        Paragraph(f'<font name="{font_b}" size="9">{safe_text(label_a)}</font>', styles.get("caption") or styles.get("Normal")),
        Paragraph(f'<font name="{font_b}" size="9">{safe_text(label_b)}</font>', styles.get("caption") or styles.get("Normal")),
        Paragraph(f'<font name="{font_b}" size="9">差分 (B−A)</font>', styles.get("caption") or styles.get("Normal")),
    ]
    rows = [header_row]

    col_w_label = _CONTENT_W * 0.40
    col_w_val = (_CONTENT_W - col_w_label) / 3

    for field_key, field_info in fields.items():
        label_txt = safe_text(field_info.get("label", field_key))
        val_a = _fmt_val(field_info.get("a"))
        val_b = _fmt_val(field_info.get("b"))
        diff = _fmt_diff(field_info.get("diff"))
        rows.append([
            Paragraph(label_txt, styles.get("caption") or styles.get("Normal")),
            Paragraph(val_a, styles.get("caption") or styles.get("Normal")),
            Paragraph(val_b, styles.get("caption") or styles.get("Normal")),
            Paragraph(diff, styles.get("caption") or styles.get("Normal")),
        ])

    tbl = Table(rows, colWidths=[col_w_label, col_w_val, col_w_val, col_w_val])
    tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
            ("BOX", (0, 0), (-1, -1), 0.5, MID_GRAY),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, MID_GRAY),
        ])
    )
    elems.append(KeepTogether([tbl]))
    elems.append(section_spacer())
    elems.append(hr())
    elems.append(section_spacer())
    return elems


def _graph_compare_section(
    graphs_dir_a: Path,
    graphs_dir_b: Path,
    label_a: str,
    label_b: str,
    styles: dict,
) -> list:
    """グラフ比較セクション（A/B を 2列並置）。"""
    font_b = get_font(bold=True)
    font_r = get_font(bold=False)

    # 同名のグラフを検索
    if not graphs_dir_a.exists() and not graphs_dir_b.exists():
        return []

    graph_stems_a = {p.stem for p in graphs_dir_a.glob("*.png")} if graphs_dir_a.exists() else set()
    graph_stems_b = {p.stem for p in graphs_dir_b.glob("*.png")} if graphs_dir_b.exists() else set()
    common_stems = sorted(graph_stems_a | graph_stems_b)

    if not common_stems:
        return []

    elems: list = []
    elems.append(
        Paragraph(
            f'<font name="{font_b}" size="12" color="{BRAND_BLUE}">グラフ比較</font>',
            styles.get("h2") or styles.get("Normal"),
        )
    )
    elems.append(para_spacer())
    elems.append(
        Paragraph(
            f'<font name="{font_r}" size="9" color="#555555">'
            "グラフは参考値を示したものです。動画の長さやフレームレートが異なる場合、"
            "時間軸の直接比較が難しい場合があります。"
            "</font>",
            styles.get("caption") or styles.get("Normal"),
        )
    )
    elems.append(para_spacer())

    for stem in common_stems:
        img_a = graphs_dir_a / f"{stem}.png"
        img_b = graphs_dir_b / f"{stem}.png"
        cells_img: list = []
        cells_lbl: list = []

        for img_path, side_label in [(img_a, label_a), (img_b, label_b)]:
            cap = f'<font name="{font_b}" size="9">{safe_text(side_label)}</font>'
            cells_lbl.append(Paragraph(cap, styles.get("caption") or styles.get("Normal")))
            if img_path.exists():
                try:
                    iw, ih = scale_image(img_path, _COL_W - 0.3 * cm, 6.0 * cm)
                    cells_img.append(Image(str(img_path), width=iw, height=ih))
                except Exception as _e:
                    logger.warning("[comparison_report] グラフ読み込み失敗: %s — %s", img_path, _e)
                    cells_img.append(
                        Paragraph("（グラフなし）", styles.get("caption") or styles.get("Normal"))
                    )
            else:
                cells_img.append(
                    Paragraph("（グラフなし）", styles.get("caption") or styles.get("Normal"))
                )

        tbl = Table(
            [cells_lbl, cells_img],
            colWidths=[_COL_W, _COL_W],
        )
        tbl.setStyle(
            TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("BOX", (0, 0), (-1, -1), 0.5, MID_GRAY),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, MID_GRAY),
                ("BACKGROUND", (0, 0), (-1, 0), CARD_BG),
            ])
        )
        elems.append(KeepTogether([tbl]))
        elems.append(para_spacer())

    elems.append(section_spacer())
    elems.append(hr())
    elems.append(section_spacer())
    return elems


def generate_comparison_report_pdf(
    comparison_dir: Path,
    job_dir_a: Path,
    job_dir_b: Path,
    label_a: str = "動画A",
    label_b: str = "動画B",
    purpose: str = "",
) -> Path:
    """比較レポート PDF を生成して保存し、Path を返す。

    Parameters
    ----------
    comparison_dir : Path
        比較ジョブのルートディレクトリ（出力先）
    job_dir_a : Path
        比較元ジョブのルートディレクトリ
    job_dir_b : Path
        比較先ジョブのルートディレクトリ
    label_a : str
        動画 A の表示名（例: 改善前）
    label_b : str
        動画 B の表示名（例: 改善後）
    purpose : str
        比較目的（自由記述）

    Returns
    -------
    Path
        生成された PDF のパス（ comparison_dir/comparison_report.pdf ）
    """
    from src.phase_loader import load_phases, get_all_phase_keys

    comparison_dir = Path(comparison_dir)
    job_dir_a = Path(job_dir_a)
    job_dir_b = Path(job_dir_b)

    comparison_dir.mkdir(parents=True, exist_ok=True)
    out_path = comparison_dir / "comparison_report.pdf"

    # 比較サマリー JSON（compare_jobs.py の出力）
    comp_summary = _load_json(comparison_dir / "comparison_summary.json") or {}

    # ジョブ情報
    job_a = _load_json(job_dir_a / "job.json") or {}
    job_b = _load_json(job_dir_b / "job.json") or {}
    job_id_a = job_a.get("job_id", job_dir_a.name)
    job_id_b = job_b.get("job_id", job_dir_b.name)

    # フェーズ画像ディレクトリ
    phase_img_dir_a = job_dir_a / "report" / "phase_frames"
    phase_img_dir_b = job_dir_b / "report" / "phase_frames"

    # グラフディレクトリ
    graphs_dir_a = job_dir_a / "report" / "graphs"
    graphs_dir_b = job_dir_b / "report" / "graphs"

    # フェーズ定義
    phases = load_phases()
    phase_keys = get_all_phase_keys()

    # スタイル設定
    styles = get_styles()
    font_b = get_font(bold=True)
    font_r = get_font(bold=False)

    # ドキュメント構築
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        rightMargin=_MARGIN,
        leftMargin=_MARGIN,
        topMargin=_MARGIN + 1.2 * cm,
        bottomMargin=_MARGIN + 1.0 * cm,
        title=f"2動画比較レポート — {label_a} vs {label_b}",
        author="Javelin Video Analysis",
        subject="2動画比較解析レポート",
    )

    on_page = make_header_footer(f"2動画比較レポート: {safe_text(label_a)} vs {safe_text(label_b)}")

    story: list = []

    # ── 表紙 ───────────────────────────────────────────────────────────────
    story += title_block(
        title_ja="2動画比較レポート",
        subtitle_en="Two-Video Comparison Report",
        info_line=f"生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        styles=styles,
    )
    story.append(section_spacer())

    # 比較概要テーブル
    overview_pairs = [
        ("比較対象A", f"{safe_text(label_a)}（Job: {job_id_a}）"),
        ("比較対象B", f"{safe_text(label_b)}（Job: {job_id_b}）"),
    ]
    if purpose:
        overview_pairs.append(("比較目的", safe_text(purpose)))
    story.append(kv_table(overview_pairs, styles))
    story.append(section_spacer())

    # 免責・注意書き（冒頭）
    story.append(
        warn_box(
            "このレポートは動作の傾向を確認するための参考資料です。"
            "記載された内容は必ずしも正確・完全ではなく、"
            "医療的アドバイス・コーチング指導の代替として使用しないでください。",
            styles,
        )
    )
    story.append(section_spacer())
    story.append(hr())
    story.append(section_spacer())

    # ── フェーズ別比較 ─────────────────────────────────────────────────────
    story.append(
        Paragraph(
            f'<font name="{font_b}" size="14" color="{BRAND_BLUE}">フェーズ別動作比較</font>',
            styles.get("h1") or styles.get("Normal"),
        )
    )
    story.append(para_spacer())
    story.append(
        Paragraph(
            f'<font name="{font_r}" size="9" color="#555555">'
            "各フェーズの代表フレームを左右に並べて表示します。"
            "撮影アングルや照明条件が異なる場合、直接比較には注意が必要です。"
            "</font>",
            styles.get("caption") or styles.get("Normal"),
        )
    )
    story.append(section_spacer())
    story.append(hr())
    story.append(section_spacer())

    for phase_key in phase_keys:
        phase_def = phases.get(phase_key, {})
        if not phase_def:
            continue
        phase_elems = _phase_compare_section(
            phase_key=phase_key,
            phase_def=phase_def,
            phase_img_dir_a=phase_img_dir_a,
            phase_img_dir_b=phase_img_dir_b,
            label_a=label_a,
            label_b=label_b,
            styles=styles,
        )
        story.extend(phase_elems)

    # ── 数値比較 ────────────────────────────────────────────────────────────
    if comp_summary:
        story.extend(
            _metrics_compare_section(comp_summary, label_a, label_b, styles)
        )

    # ── グラフ比較 ──────────────────────────────────────────────────────────
    graph_elems = _graph_compare_section(
        graphs_dir_a, graphs_dir_b, label_a, label_b, styles
    )
    story.extend(graph_elems)

    # ── 免責事項（末尾）────────────────────────────────────────────────────
    story.append(PageBreak())
    story += disclaimer_block(styles)

    # PDF 書き出し
    try:
        doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
        logger.info("[comparison_report] 生成完了: %s", out_path)
    except Exception as _e:
        logger.error("[comparison_report] PDF 生成失敗: %s", _e)
        raise RuntimeError(f"comparison_report_pdf 生成失敗: {_e}") from _e

    return out_path
