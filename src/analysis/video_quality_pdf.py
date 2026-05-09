"""
src/analysis/video_quality_pdf.py — Javelin Video Analysis 動画品質チェック PDF 生成 (Phase 10)

video_quality_report.json の内容から PDF レポートを生成します。

出力先: job_dir/report/video_quality_report.pdf

Usage:
    from src.analysis.video_quality_pdf import generate_video_quality_pdf
    from pathlib import Path

    pdf_path = generate_video_quality_pdf(Path("jobs/20260508_070156_518a"))
    # -> Path("jobs/20260508_070156_518a/report/video_quality_report.pdf")
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
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
    MID_GRAY,
    get_font,
    get_styles,
    make_header_footer,
    safe_text,
    disclaimer_block,
    hr,
    section_spacer,
    para_spacer,
)

logger = logging.getLogger("jva.video_quality_pdf")

_PAGE_W, _PAGE_H = A4
_MARGIN_LR = 2.0 * cm
_CONTENT_W  = _PAGE_W - 2 * _MARGIN_LR

# 品質ラベル → 背景色
_QUALITY_COLORS = {
    "good":   "#2e7d32",  # 緑
    "medium": "#f57f17",  # 橙
    "low":    "#c62828",  # 赤
    "unknown": "#757575", # グレー
}

_QUALITY_LABELS = {
    "good":    "良好",
    "medium":  "中程度",
    "low":     "低め",
    "unknown": "不明",
}


def _load_quality_report(job_dir: Path) -> Optional[Dict[str, Any]]:
    """video_quality_report.json を読み込んで返す。存在しない場合は None。"""
    path = Path(job_dir) / "report" / "video_quality_report.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[video_quality_pdf] JSON 読み込み失敗: %s", e)
        return None


def _pct(val: Optional[float]) -> str:
    if val is None:
        return "—"
    return f"{val * 100:.1f}%"


def _fmt_float(val: Optional[float], digits: int = 2) -> str:
    if val is None:
        return "—"
    return f"{val:.{digits}f}"


def generate_video_quality_pdf(job_dir: Path) -> Path:
    """
    video_quality_report.json を読み込んで video_quality_report.pdf を生成する。

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ

    Returns
    -------
    Path
        生成した PDF のパス

    Raises
    ------
    FileNotFoundError
        video_quality_report.json が存在しない場合
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "video_quality_report.pdf"

    report = _load_quality_report(job_dir)
    if report is None:
        raise FileNotFoundError(
            f"video_quality_report.json が見つかりません: {report_dir}"
        )

    status = report.get("status", "unknown")
    styles = get_styles()
    font_b = get_font(bold=True)
    font_r = get_font(bold=False)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=_MARGIN_LR,
        rightMargin=_MARGIN_LR,
        topMargin=2.5 * cm,
        bottomMargin=2.0 * cm,
        title="動画品質チェックレポート",
        author="Javelin Video Analysis",
    )

    story: List[Any] = []

    # ── タイトル ──────────────────────────────────────────────────────────────
    story.append(
        Paragraph(
            f'<font name="{font_b}" size="18" color="{BRAND_BLUE}">動画品質チェックレポート</font>',
            styles["h1"],
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            f'<font name="{font_r}" size="9" color="{MID_GRAY}">'
            f'ジョブID: {safe_text(job_dir.name)} ／ 生成日時: {safe_text(report.get("generated_at", "—"))}'
            f'</font>',
            styles["caption"],
        )
    )
    story.append(hr())
    story.append(section_spacer())

    # ── ステータス確認 ────────────────────────────────────────────────────────
    if status in ("skipped", "error", "disabled"):
        reason = report.get("reason", "詳細不明")
        story.append(
            Paragraph(
                f'<font name="{font_b}" size="11">チェック結果: <font color="#888888">{safe_text(status)}</font></font>',
                styles["body"],
            )
        )
        story.append(para_spacer())
        story.append(
            Paragraph(
                f'理由: {safe_text(reason)}',
                styles["body"],
            )
        )
        story.append(section_spacer())
        story.append(disclaimer_block(
            "この品質評価は動画の解析適性を参考情報として示すものです。"
            "品質スコアは絶対評価ではなく、動画条件により変動します。"
        ))
        doc.build(story, onFirstPage=make_header_footer, onLaterPages=make_header_footer)
        logger.info("[video_quality_pdf] 生成完了 (status=%s): %s", status, out_path)
        return out_path

    # ── 総合品質バッジ ────────────────────────────────────────────────────────
    overall_quality = report.get("overall_quality", "unknown")
    overall_label   = report.get("overall_quality_label") or _QUALITY_LABELS.get(overall_quality, "—")
    overall_desc    = report.get("overall_description", "")
    badge_color     = _QUALITY_COLORS.get(overall_quality, _QUALITY_COLORS["unknown"])

    story.append(
        Paragraph(
            f'<font name="{font_b}" size="13" color="{BRAND_BLUE}">総合品質評価</font>',
            styles["h2"],
        )
    )
    story.append(para_spacer())

    # バッジ風テーブル
    badge_table = Table(
        [[Paragraph(
            f'<font name="{font_b}" size="14" color="#ffffff">{safe_text(overall_label)}</font>',
            styles["body"],
        )]],
        colWidths=[_CONTENT_W * 0.25],
        rowHeights=[1.0 * cm],
    )
    badge_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(badge_color)),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(badge_table)
    story.append(para_spacer())

    if overall_desc:
        story.append(Paragraph(safe_text(overall_desc), styles["body"]))
    story.append(section_spacer())

    # ── 計測値サマリー ────────────────────────────────────────────────────────
    story.append(
        Paragraph(
            f'<font name="{font_b}" size="13" color="{BRAND_BLUE}">計測値サマリー</font>',
            styles["h2"],
        )
    )
    story.append(para_spacer())

    metrics = [
        ("FPS（推定値）",     _fmt_float(report.get("fps"), 1)),
        ("動画長",            f'{_fmt_float(report.get("duration_sec"), 2)} 秒'),
        ("総フレーム数",       str(report.get("total_frames", "—"))),
        ("姿勢検出率",         _pct(report.get("pose_detection_rate"))),
        ("ランドマーク欠損率", _pct(report.get("landmark_missing_rate"))),
    ]

    metrics_data = [
        [
            Paragraph(f'<font name="{font_b}" size="9">{safe_text(k)}</font>', styles["caption"]),
            Paragraph(f'<font name="{font_r}" size="9">{safe_text(v)}</font>', styles["caption"]),
        ]
        for k, v in metrics
    ]

    metrics_table = Table(metrics_data, colWidths=[_CONTENT_W * 0.45, _CONTENT_W * 0.45])
    metrics_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f7f7")),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(metrics_table)
    story.append(section_spacer())

    # ── 注意事項 ──────────────────────────────────────────────────────────────
    warnings_list: List[str] = report.get("warnings", [])
    if warnings_list:
        story.append(
            Paragraph(
                f'<font name="{font_b}" size="13" color="{BRAND_BLUE}">注意事項</font>',
                styles["h2"],
            )
        )
        story.append(para_spacer())
        for w in warnings_list:
            story.append(
                Paragraph(
                    f'<font name="{font_r}" size="9" color="#CC4400">⚠ {safe_text(w)}</font>',
                    styles["body"],
                )
            )
            story.append(Spacer(1, 2 * mm))
        story.append(section_spacer())

    # ── ランドマーク別欠損率 ──────────────────────────────────────────────────
    landmark_stats = report.get("landmark_stats", {})
    per_landmark = landmark_stats.get("per_landmark", {})
    if per_landmark:
        story.append(
            Paragraph(
                f'<font name="{font_b}" size="13" color="{BRAND_BLUE}">ランドマーク別の安定性</font>',
                styles["h2"],
            )
        )
        story.append(para_spacer())

        _jp_map = {
            "nose": "鼻",
            "left_shoulder": "左肩", "right_shoulder": "右肩",
            "left_elbow": "左肘", "right_elbow": "右肘",
            "left_wrist": "左手首", "right_wrist": "右手首",
            "left_hip": "左腰", "right_hip": "右腰",
            "left_knee": "左膝", "right_knee": "右膝",
            "left_ankle": "左足首", "right_ankle": "右足首",
        }

        lm_header = [
            Paragraph(f'<font name="{font_b}" size="8">部位</font>', styles["caption"]),
            Paragraph(f'<font name="{font_b}" size="8">欠損率</font>', styles["caption"]),
            Paragraph(f'<font name="{font_b}" size="8">安定性</font>', styles["caption"]),
        ]
        lm_rows = [lm_header]
        for name, rate in per_landmark.items():
            if not isinstance(rate, (int, float)):
                continue
            jp_name = _jp_map.get(name, name)
            rate_pct = _pct(rate)
            if rate < 0.15:
                stability = "安定"
                stab_color = "#2e7d32"
            elif rate < 0.35:
                stability = "やや不安定"
                stab_color = "#f57f17"
            else:
                stability = "不安定"
                stab_color = "#c62828"
            lm_rows.append([
                Paragraph(f'<font name="{font_r}" size="8">{safe_text(jp_name)}</font>', styles["caption"]),
                Paragraph(f'<font name="{font_r}" size="8">{rate_pct}</font>', styles["caption"]),
                Paragraph(f'<font name="{font_r}" size="8" color="{stab_color}">{stability}</font>', styles["caption"]),
            ])

        lm_table = Table(
            lm_rows,
            colWidths=[_CONTENT_W * 0.35, _CONTENT_W * 0.25, _CONTENT_W * 0.30],
        )
        lm_table.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#e8eaf6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID",        (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING",  (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(lm_table)
        story.append(section_spacer())

    # ── 次回撮影アドバイス ────────────────────────────────────────────────────
    advice_list: List[str] = report.get("next_shooting_advice", [])
    if advice_list:
        story.append(
            Paragraph(
                f'<font name="{font_b}" size="13" color="{BRAND_BLUE}">次回撮影のアドバイス</font>',
                styles["h2"],
            )
        )
        story.append(para_spacer())
        for i, advice in enumerate(advice_list, 1):
            story.append(
                Paragraph(
                    f'<font name="{font_r}" size="9">{i}. {safe_text(advice)}</font>',
                    styles["body"],
                )
            )
            story.append(Spacer(1, 1.5 * mm))
        story.append(section_spacer())

    # ── 免責事項 ──────────────────────────────────────────────────────────────
    disclaimer_text = report.get(
        "disclaimer",
        "この品質評価は動画の解析適性を参考情報として示すものです。"
        "品質スコアは絶対評価ではなく、動画条件により変動します。",
    )
    story.append(disclaimer_block(disclaimer_text))

    doc.build(story, onFirstPage=make_header_footer, onLaterPages=make_header_footer)
    logger.info("[video_quality_pdf] 生成完了: %s", out_path)
    return out_path


def generate_video_quality_pdf_for_job(job_dir: Path) -> Optional[Path]:
    """
    ジョブディレクトリに対して動画品質 PDF を生成する。
    video_quality_report.json がなければ None を返す（例外は発生させない）。
    """
    job_dir = Path(job_dir)
    try:
        return generate_video_quality_pdf(job_dir)
    except FileNotFoundError:
        logger.info("[video_quality_pdf] JSON未生成のためスキップ: %s", job_dir.name)
        return None
    except Exception as e:
        logger.warning("[video_quality_pdf] PDF生成失敗: %s — %s", job_dir.name, e)
        return None
