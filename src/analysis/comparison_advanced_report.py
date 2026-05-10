"""
src/analysis/comparison_advanced_report.py — Phase 12 比較指標 PDF レポート生成

comparison_advanced_metrics.json をもとに、比較レポート PDF を生成します。

対象読者: 高校生アスリート、保護者、コーチ
位置づけ: 参考資料（医療診断・競技指導の代替ではありません）

出力先: save_dir/comparison_advanced_report.pdf

Usage:
    from src.analysis.comparison_advanced_report import (
        generate_comparison_advanced_report_for_jobs
    )
    from pathlib import Path

    out = generate_comparison_advanced_report_for_jobs(
        job_a_dir=Path("jobs/20260508_070156_518a"),
        job_b_dir=Path("jobs/20260508_081953_329a"),
    )
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
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
    WARN_BG,
    WARN_BORDER,
    TEXT_GRAY,
    TEXT_DARK,
    CONTENT_W,
    get_font,
    get_styles,
    make_header_footer,
    safe_text,
    disclaimer_block,
    hr,
    section_spacer,
    para_spacer,
)

logger = logging.getLogger("jva.comparison_advanced_report")

_PAGE_W, _PAGE_H = A4
_MARGIN_LR = 1.8 * cm
_CONTENT_W = _PAGE_W - 2 * _MARGIN_LR


# ── 共通ヘルパー ─────────────────────────────────────────────────────────────

def _fmt(val: Any, digits: int = 3, suffix: str = "") -> str:
    if val is None:
        return "—"
    try:
        return f"{round(float(val), digits)}{suffix}"
    except (TypeError, ValueError):
        return str(val)


def _reliability_icon(rel: str) -> str:
    icons = {"high": "🟢 高", "medium": "🟡 中", "low": "🔴 低", "unknown": "⚪ 不明"}
    return icons.get(rel, rel)


def _delta_direction(delta: Any, pct: Any) -> tuple[str, Any]:
    """差分方向と色を返す。"""
    if delta is None:
        return "—", MID_GRAY
    d = float(delta)
    if abs(d) < 1e-8:
        return "≈ 0", colors.HexColor("#95A5A6")
    arrow = "▲" if d > 0 else "▽"
    pct_str = f"{abs(float(pct)):.1f}%" if pct is not None else ""
    col = colors.HexColor("#27AE60") if d > 0 else colors.HexColor("#E74C3C")
    return f"{arrow} {_fmt(abs(d))}  {pct_str}", col


# ── 比較テーブル生成 ─────────────────────────────────────────────────────────

def _comparison_table(
    comparisons: List[Dict[str, Any]],
    label_a: str,
    label_b: str,
    styles: dict,
    font_b: str,
    font_r: str,
) -> List[Any]:
    """比較テーブル (story リスト) を生成する。"""
    story: List[Any] = []

    header = [
        Paragraph(f'<font name="{font_b}" size="8">指標</font>', styles["kv_key"]),
        Paragraph(f'<font name="{font_b}" size="8">{safe_text(label_a)}</font>', styles["kv_key"]),
        Paragraph(f'<font name="{font_b}" size="8">{safe_text(label_b)}</font>', styles["kv_key"]),
        Paragraph(f'<font name="{font_b}" size="8">差分 (B-A)</font>', styles["kv_key"]),
        Paragraph(f'<font name="{font_b}" size="8">信頼度</font>', styles["kv_key"]),
    ]
    rows = [header]

    for item in comparisons:
        lbl   = item.get("label", item.get("metric", "—"))
        rel   = item.get("reliability", "unknown")
        rel_icon = _reliability_icon(rel)
        val_a_raw = item.get(f"{label_a}_value")
        val_b_raw = item.get(f"{label_b}_value")
        delta     = item.get("delta")
        delta_pct = item.get("delta_percent")
        direction, _col = _delta_direction(delta, delta_pct)

        row = [
            Paragraph(f'<font name="{font_r}" size="8">{safe_text(str(lbl))}</font>', styles["kv_val"]),
            Paragraph(f'<font name="{font_r}" size="8">{_fmt(val_a_raw)}</font>', styles["kv_val"]),
            Paragraph(f'<font name="{font_r}" size="8">{_fmt(val_b_raw)}</font>', styles["kv_val"]),
            Paragraph(f'<font name="{font_r}" size="8">{safe_text(direction)}</font>', styles["kv_val"]),
            Paragraph(f'<font name="{font_r}" size="8">{safe_text(rel_icon)}</font>', styles["kv_val"]),
        ]
        rows.append(row)

    col_widths = [
        _CONTENT_W * 0.32,
        _CONTENT_W * 0.14,
        _CONTENT_W * 0.14,
        _CONTENT_W * 0.22,
        _CONTENT_W * 0.14,
    ]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8ff")]),
        ("GRID",          (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)
    return story


# ── 解釈文セクション ─────────────────────────────────────────────────────────

def _interpretation_section(
    comparisons: List[Dict[str, Any]],
    notable_keys: List[str],
    styles: dict,
    font_b: str,
    font_r: str,
) -> List[Any]:
    """注目指標の解釈文セクションを生成する。"""
    story: List[Any] = []

    if not notable_keys:
        story.append(Paragraph(
            f'<font name="{font_r}" size="9">'
            "2つの動画で大きな差が見られた指標はありませんでした。"
            "</font>",
            styles["body"],
        ))
        return story

    for c in comparisons:
        if c.get("metric") not in notable_keys:
            continue
        lbl   = c.get("label", c.get("metric", "—"))
        interp = c.get("interpretation", "")
        rel   = c.get("reliability", "unknown")
        delta = c.get("delta")
        dpct  = c.get("delta_percent")

        story.append(Paragraph(
            f'<font name="{font_b}" size="9" color="{BRAND_BLUE.hexval()}">{safe_text(str(lbl))}</font>',
            styles["body_bold"],
        ))
        direction, _ = _delta_direction(delta, dpct)
        story.append(Paragraph(
            f'<font name="{font_r}" size="8.5">{safe_text(str(interp))}</font>',
            styles["body"],
        ))
        story.append(Paragraph(
            f'<font name="{font_r}" size="8" color="{TEXT_GRAY.hexval()}">'
            f"差分: {_fmt(delta)}　{safe_text(direction)}　信頼度: {_reliability_icon(rel)}"
            f"</font>",
            styles["note"],
        ))
        story.append(Spacer(1, 2 * mm))

    return story


# ── メイン生成関数 ────────────────────────────────────────────────────────────

def generate_comparison_advanced_report(
    comparison_data: Dict[str, Any],
    output_path: Path,
) -> Path:
    """
    comparison_advanced_metrics dict から PDF を生成する。

    Parameters
    ----------
    comparison_data : dict
        compute_comparison_advanced_metrics() の戻り値
    output_path : Path
        出力 PDF パス
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = get_styles("car_")
    font_b = get_font(bold=True)
    font_r = get_font(bold=False)

    label_a = comparison_data.get("job_a_label", "動画A")
    label_b = comparison_data.get("job_b_label", "動画B")
    job_a_id = comparison_data.get("job_a_id", "—")
    job_b_id = comparison_data.get("job_b_id", "—")
    gen_at   = comparison_data.get("generated_at", "—")
    summary  = comparison_data.get("summary", {})
    combined_rel = comparison_data.get("combined_reliability", "unknown")
    comparisons  = comparison_data.get("comparisons", [])
    notable_keys = summary.get("notable_change_keys", [])

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=_MARGIN_LR, rightMargin=_MARGIN_LR,
        topMargin=2.5 * cm, bottomMargin=2.0 * cm,
        title="解析指標 比較レポート（参考資料）",
        author="Javelin Video Analysis",
    )

    story: List[Any] = []

    # ── タイトル ──────────────────────────────────────────────────────────────
    story.append(Paragraph(
        f'<font name="{font_b}" size="18" color="{BRAND_BLUE.hexval()}">解析指標 比較レポート</font>',
        styles["doc_title"],
    ))
    story.append(Paragraph(
        f'<font name="{font_r}" size="9" color="#CC4400">'
        "⚠️ このレポートは参考資料です。医療診断・競技指導の代替ではありません。"
        "</font>",
        styles["caption"],
    ))
    story.append(Spacer(1, 1 * mm))
    story.append(Paragraph(
        f'<font name="{font_r}" size="8.5" color="{TEXT_GRAY.hexval()}">'
        f"{safe_text(label_a)}: {safe_text(job_a_id)}　"
        f"{safe_text(label_b)}: {safe_text(job_b_id)}　"
        f"生成日時: {safe_text(gen_at)}"
        f"</font>",
        styles["caption"],
    ))
    story.append(hr())
    story.append(section_spacer())

    # ── 注意事項 ──────────────────────────────────────────────────────────────
    story.append(Paragraph(
        f'<font name="{font_r}" size="9">'
        "このレポートは、2つの動画の解析指標を参考として比較したものです。"
        "すべての数値は動画上の座標から算出した相対指標であり、"
        "実際の距離・速度・角度と完全に一致するわけではありません。"
        "差分が大きくても、撮影条件や姿勢推定の違いによるものである場合があります。"
        "数値だけで動作の優劣を判断しないでください。"
        "</font>",
        styles["body"],
    ))
    story.append(section_spacer())

    # ── 概要 ──────────────────────────────────────────────────────────────────
    story.append(Paragraph(
        f'<font name="{font_b}" size="13" color="{BRAND_BLUE.hexval()}">比較概要</font>',
        styles["section"],
    ))
    story.append(para_spacer())

    summary_rows = [
        ("比較対象A",         f"{safe_text(label_a)}（{safe_text(job_a_id)}）"),
        ("比較対象B",         f"{safe_text(label_b)}（{safe_text(job_b_id)}）"),
        ("総合信頼度",        _reliability_icon(combined_rel)),
        ("比較できた指標数",  f"{summary.get('computable_metrics', '—')} / {summary.get('compared_metrics', '—')} 指標"),
        ("差異が大きい指標数", f"{summary.get('notable_changes_count', '—')} 指標"
                              f"（基準: ±{summary.get('notable_threshold_percent', '—')}%以上）"),
    ]
    sq_data = [
        [
            Paragraph(f'<font name="{font_b}" size="8.5">{k}</font>', styles["kv_key"]),
            Paragraph(f'<font name="{font_r}" size="8.5">{safe_text(str(v))}</font>', styles["kv_val"]),
        ]
        for k, v in summary_rows
    ]
    sq_table = Table(sq_data, colWidths=[_CONTENT_W * 0.38, _CONTENT_W * 0.56])
    sq_table.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f5f8ff")]),
        ("GRID",           (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
        ("TOPPADDING",     (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(sq_table)
    story.append(section_spacer())

    # ── 全指標比較テーブル ────────────────────────────────────────────────────
    story.append(Paragraph(
        f'<font name="{font_b}" size="13" color="{BRAND_BLUE.hexval()}">指標一覧（比較）</font>',
        styles["section"],
    ))
    story.append(para_spacer())
    story.append(Paragraph(
        f'<font name="{font_r}" size="9">'
        "▲ は B の方が大きい傾向、▽ は A の方が大きい傾向を示します。"
        "差分は相対値であり、数値の意味はそれぞれの指標の説明をご確認ください。"
        "</font>",
        styles["body_sm"],
    ))
    story.append(Spacer(1, 2 * mm))

    if comparisons:
        story += _comparison_table(comparisons, label_a, label_b, styles, font_b, font_r)
    else:
        story.append(Paragraph("比較データがありません。", styles["body"]))
    story.append(section_spacer())

    # ── 差異が大きい指標の解釈 ────────────────────────────────────────────────
    story.append(Paragraph(
        f'<font name="{font_b}" size="13" color="{BRAND_BLUE.hexval()}">'
        "差異が大きかった指標の解釈（参考）"
        "</font>",
        styles["section"],
    ))
    story.append(para_spacer())
    story.append(Paragraph(
        f'<font name="{font_r}" size="9">'
        "以下は差異が大きかった指標に対する参考解釈です。"
        "「傾向がある」「可能性がある」等の表現は断定ではなく、参考指標としてお読みください。"
        "</font>",
        styles["body"],
    ))
    story.append(Spacer(1, 2 * mm))

    story += _interpretation_section(comparisons, notable_keys, styles, font_b, font_r)
    story.append(section_spacer())

    # ── 指標説明 ──────────────────────────────────────────────────────────────
    story.append(Paragraph(
        f'<font name="{font_b}" size="13" color="{BRAND_BLUE.hexval()}">指標の説明（参考）</font>',
        styles["section"],
    ))
    story.append(para_spacer())
    for c in comparisons:
        lbl  = c.get("label", c.get("metric", "—"))
        desc = c.get("description", "")
        caut = c.get("caution", "")
        if desc:
            story.append(Paragraph(
                f'<font name="{font_b}" size="8.5">{safe_text(str(lbl))}</font>',
                styles["body_bold"],
            ))
            story.append(Paragraph(
                f'<font name="{font_r}" size="8">{safe_text(str(desc))}</font>',
                styles["body_sm"],
            ))
            if caut:
                story.append(Paragraph(
                    f'<font name="{font_r}" size="7.5" color="{TEXT_GRAY.hexval()}">'
                    f"注意: {safe_text(str(caut))}</font>",
                    styles["note"],
                ))
            story.append(Spacer(1, 1.5 * mm))
    story.append(section_spacer())

    # ── 注意事項 ──────────────────────────────────────────────────────────────
    story.append(Paragraph(
        f'<font name="{font_b}" size="13" color="{BRAND_BLUE.hexval()}">注意事項</font>',
        styles["section"],
    ))
    story.append(para_spacer())
    cautions = [
        "すべての数値は参考値です。動画上の座標から算出した相対指標であり、実際の値とは異なります。",
        "2D動画上の見かけの角度推定は3Dの正確な角度ではありません。",
        "撮影角度・動画品質が異なる動画を比較する場合、差分の解釈には特に注意が必要です。",
        "「信頼度 低」の指標は誤差が大きく、数値の比較は参考程度に留めてください。",
        "このレポートは医療診断・怪我の診断・専門的競技指導の代替ではありません。",
        "数値の差だけでフォームの優劣や記録の優劣を判断しないでください。",
    ]
    for c in cautions:
        story.append(Paragraph(
            f'<font name="{font_r}" size="9">• {safe_text(c)}</font>',
            styles["body"],
        ))
    story.append(section_spacer())
    story.extend(disclaimer_block(styles))

    doc.build(
        story,
        onFirstPage=make_header_footer("解析指標 比較レポート（参考資料）"),
        onLaterPages=make_header_footer("解析指標 比較レポート（参考資料）"),
    )

    logger.info("[comparison_advanced_report] PDF 生成完了: %s", output_path)
    return output_path


def generate_comparison_advanced_report_for_jobs(
    job_a_dir: Path,
    job_b_dir: Path,
    comparison_id: Optional[str] = None,
    job_a_label: str = "動画A",
    job_b_label: str = "動画B",
    output_path: Optional[Path] = None,
) -> Optional[Path]:
    """
    2つのジョブの高度比較 PDF を生成する。
    失敗しても例外を送出しない（worker 安全設計）。
    """
    try:
        from src.analysis.comparison_advanced_metrics import (
            compute_comparison_advanced_metrics,
        )

        comparison_data = compute_comparison_advanced_metrics(
            job_a_dir=job_a_dir,
            job_b_dir=job_b_dir,
            job_a_label=job_a_label,
            job_b_label=job_b_label,
        )

        if output_path is None:
            if comparison_id:
                _REPO_ROOT = Path(__file__).resolve().parent.parent.parent
                save_dir = _REPO_ROOT / "jobs" / "comparisons" / comparison_id
            else:
                save_dir = Path(job_a_dir) / "report"
            save_dir.mkdir(parents=True, exist_ok=True)
            output_path = save_dir / "comparison_advanced_report.pdf"

        return generate_comparison_advanced_report(comparison_data, output_path)

    except Exception as e:
        logger.error("[comparison_advanced_report] PDF 生成エラー: %s", e)
        return None
