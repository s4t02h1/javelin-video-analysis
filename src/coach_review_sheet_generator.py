"""
coach_review_sheet_generator.py — コーチレビューシート PDF 生成

コーチや指導者が記入しやすい A4 PDF を生成する。
自動解析で得られた主要指標を小さく表示しつつ、
各フェーズの評価欄・メモ欄を設ける。

Usage:
    from src.coach_review_sheet_generator import generate_coach_review_sheet_for_job
    pdf_path = generate_coach_review_sheet_for_job(Path("jobs/20260510_012144_0513"))
    # -> Path("jobs/20260510_012144_0513/report/coach_review_sheet.pdf")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.pdf_styles import (
    get_font as _get_font,
    make_header_footer as _make_hf,
    safe_text as _safe,
    BODY_BOT_MARGIN,
    BODY_TOP_MARGIN,
    MARGIN_H,
)

logger = logging.getLogger(__name__)


def _fn(bold: bool = False) -> str:
    return _get_font(bold=bold)



# ── 定数 ──────────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN    = MARGIN_H
CONTENT_W = PAGE_W - 2 * MARGIN

BRAND_BLUE   = colors.HexColor("#1A4D8F")
BRAND_ORANGE = colors.HexColor("#E86A2E")
LIGHT_GRAY   = colors.HexColor("#F5F5F5")
MID_GRAY     = colors.HexColor("#CCCCCC")
WRITE_LINE   = colors.HexColor("#E8E8E8")
TEXT_DARK    = colors.HexColor("#1A1A1A")
TEXT_GRAY    = colors.HexColor("#888888")

_DISCLAIMER = (
    "本資料は参考資料です。医療診断・怪我の診断を代替するものではありません。"
    "速度等の数値は撮影条件の影響を受ける参考推定値です。"
)

# 記入欄の行の高さ（0.55 cm × n行）
_LINE_H = 0.55 * cm


# ── スタイル ──────────────────────────────────────────────────────────────────

def _make_styles() -> dict:
    def s(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    return {
        "title": s("CRSTitle", fontName=_fn(True), fontSize=20,
                   textColor=BRAND_BLUE, spaceAfter=3, alignment=TA_CENTER),
        "subtitle": s("CRSSubtitle", fontName=_fn(), fontSize=10,
                      textColor=BRAND_ORANGE, spaceAfter=2, alignment=TA_CENTER),
        "date_line": s("CRSDate", fontName=_fn(), fontSize=8,
                       textColor=colors.grey, alignment=TA_CENTER),
        "section": s("CRSSection", fontName=_fn(True), fontSize=11,
                     textColor=BRAND_BLUE, spaceBefore=8, spaceAfter=3),
        "subsection": s("CRSSubSection", fontName=_fn(True), fontSize=9,
                        textColor=TEXT_DARK, spaceBefore=4, spaceAfter=2),
        "body_sm": s("CRSBodySm", fontName=_fn(), fontSize=8,
                     textColor=TEXT_GRAY, leading=13),
        "metric_key": s("CRSMetricKey", fontName=_fn(True), fontSize=8,
                        textColor=BRAND_BLUE),
        "metric_val": s("CRSMetricVal", fontName=_fn(), fontSize=8,
                        textColor=TEXT_DARK),
        "write_label": s("CRSWriteLabel", fontName=_fn(True), fontSize=9,
                         textColor=TEXT_DARK, spaceBefore=2, spaceAfter=1),
        "disclaimer": s("CRSDisclaimer", fontName=_fn(), fontSize=7,
                        textColor=TEXT_GRAY, leading=11, alignment=TA_LEFT),
    }


# ── ヘッダー・フッター ────────────────────────────────────────────────────────

_draw_header_footer = _make_hf("コーチレビューシート")


# ── JSON ヘルパー ───────────────────────────────────────────────────────────

def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _fmt(val, suffix: str = "", digits: int = 2, fallback: str = "—") -> str:
    if val is None:
        return fallback
    try:
        return f"{float(val):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(val) or fallback


def _pct(val, fallback: str = "—") -> str:
    if val is None:
        return fallback
    try:
        return f"{float(val) * 100:.1f} %"
    except (TypeError, ValueError):
        return fallback


# ── 記入欄テーブル生成 ─────────────────────────────────────────────────────────

def _write_box(label: str, lines: int, styles: dict) -> list:
    """ラベル付き手書き記入欄を生成する。"""
    box_h = _LINE_H * lines
    # 罫線を模倣するセルを縦に並べる
    row_data = [[Paragraph("", styles["body_sm"])] for _ in range(lines)]
    box_tbl = Table(row_data, colWidths=[CONTENT_W - 0.4 * cm],
                    rowHeights=[_LINE_H] * lines)
    box_tbl.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.25, WRITE_LINE),
        ("BACKGROUND",    (0, 0), (-1, -1), colors.white),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return [
        Paragraph(_safe(label), styles["write_label"]),
        box_tbl,
    ]


def _phase_section(phase_name: str, phase_en: str,
                   check_points: list[str], styles: dict) -> list:
    """フェーズ単位のチェックポイント＋記入欄を生成する。"""
    elems: list = []
    elems.append(Paragraph(_safe(f"{phase_name}  /  {phase_en}"),
                            styles["subsection"]))
    # チェックポイント
    chk_data = [
        [Paragraph("☐", styles["body_sm"]), Paragraph(_safe(cp), styles["body_sm"])]
        for cp in check_points
    ]
    chk_tbl = Table(chk_data, colWidths=[0.5 * cm, CONTENT_W - 0.7 * cm], hAlign="LEFT")
    chk_tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING",   (0, 0), (-1, -1), 2),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elems.append(chk_tbl)
    elems.extend(_write_box(f"コメント（{phase_name}）:", 3, styles))
    return elems


# ── PDF ストーリー構築 ────────────────────────────────────────────────────────

def _build_story(job_dir: Path, styles: dict) -> list:
    story: list = []

    job = _load_json(job_dir / "job.json") or {}
    ci  = _load_json(job_dir / "customer_info.json") or {}
    summary = _load_json(job_dir / "report" / "analysis_summary.json") or {}

    job_id   = job.get("job_id", "—")
    name     = ci.get("customer_name") or "—"
    event    = ci.get("event") or "—"
    arm      = ci.get("dominant_arm") or ci.get("dominant_hand") or ""
    arm_str  = {"right": "右 (Right)", "left": "左 (Left)"}.get(arm, arm or "—")
    h        = job.get("height_m")
    height_str = f"{h:.2f} m" if isinstance(h, (int, float)) else "—"
    gen_at   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── タイトルブロック ────────────────────────────────────────────────────
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(_safe("コーチレビューシート"), styles["title"]))
    story.append(Paragraph("Coach Review Sheet  —  Javelin Video Analysis", styles["subtitle"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(HRFlowable(width=CONTENT_W * 0.5, color=BRAND_ORANGE,
                             hAlign="CENTER", thickness=2))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph(
        _safe(f"Job ID: {job_id}  |  選手: {name}  |  種目: {event}  |  出力日: {gen_at}"),
        styles["date_line"],
    ))
    story.append(Spacer(1, 0.3 * cm))

    # ── 選手基本情報 ────────────────────────────────────────────────────────
    info_data = [
        [Paragraph(_safe("選手名"), styles["metric_key"]),
         Paragraph(_safe(name), styles["metric_val"]),
         Paragraph(_safe("利き腕"), styles["metric_key"]),
         Paragraph(_safe(arm_str), styles["metric_val"])],
        [Paragraph(_safe("種目"), styles["metric_key"]),
         Paragraph(_safe(event), styles["metric_val"]),
         Paragraph(_safe("身長"), styles["metric_key"]),
         Paragraph(_safe(height_str), styles["metric_val"])],
    ]
    info_tbl = Table(info_data,
                     colWidths=[CONTENT_W * 0.20, CONTENT_W * 0.30,
                                CONTENT_W * 0.20, CONTENT_W * 0.30])
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.25, MID_GRAY),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 0.3 * cm))

    # ── 自動解析メトリクス（小サイズ参考）──────────────────────────────────
    story.append(Paragraph(_safe("▶ 自動解析メトリクス（参考推定値）"), styles["section"]))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY, thickness=0.5))
    story.append(Spacer(1, 0.15 * cm))

    # 値の収集
    output_dir = job_dir / "output"
    rep_jsons  = sorted(output_dir.glob("*_report.json")) if output_dir.exists() else []
    rep = (_load_json(rep_jsons[0]) or {}) if rep_jsons else {}
    ana = rep.get("analysis") or {}
    vi  = rep.get("video_info") or {}

    def _sv(d: dict, key: str, suffix: str = "", digits: int = 2) -> str:
        return _fmt(d.get(key), suffix, digits)

    # 旧・新両形式から取得
    dur_val  = None
    fps_val  = None
    dr_val   = None
    if "video" in summary:
        v_ = summary.get("video") or {}
        dur_val = v_.get("duration_sec")
    elif summary.get("duration_sec") is not None:
        dur_val = summary["duration_sec"]
    if not dur_val:
        dur_val = vi.get("duration_s")
    fps_val = vi.get("fps")
    dr_val  = ana.get("pose_detection_rate")

    peak_t = summary.get("wrist_height_peak_time_sec")
    km = summary.get("key_metrics") or {}
    if km.get("right_wrist_max_height_time_sec") is not None:
        peak_t = km["right_wrist_max_height_time_sec"]

    metrics_data = [
        [
            Paragraph(_safe("動画尺"), styles["metric_key"]),
            Paragraph(_safe(_fmt(dur_val, " 秒")), styles["metric_val"]),
            Paragraph(_safe("FPS"), styles["metric_key"]),
            Paragraph(_safe(_fmt(fps_val, "", digits=3)), styles["metric_val"]),
        ],
        [
            Paragraph(_safe("ポーズ検出率"), styles["metric_key"]),
            Paragraph(_safe(_pct(dr_val)), styles["metric_val"]),
            Paragraph(_safe("手首最大速度"), styles["metric_key"]),
            Paragraph(_safe(_fmt(ana.get("wrist_max_speed_kmh"), " km/h ※推定")),
                      styles["metric_val"]),
        ],
        [
            Paragraph(_safe("手首平均速度"), styles["metric_key"]),
            Paragraph(_safe(_fmt(ana.get("wrist_mean_speed_kmh"), " km/h ※推定")),
                      styles["metric_val"]),
            Paragraph(_safe("手首速度ピーク時刻"), styles["metric_key"]),
            Paragraph(_safe(_fmt(peak_t, " 秒")), styles["metric_val"]),
        ],
    ]
    m_tbl = Table(metrics_data,
                  colWidths=[CONTENT_W * 0.22, CONTENT_W * 0.28,
                             CONTENT_W * 0.22, CONTENT_W * 0.28])
    m_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [LIGHT_GRAY, colors.white, LIGHT_GRAY]),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("GRID",          (0, 0), (-1, -1), 0.25, MID_GRAY),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(m_tbl)
    story.append(Spacer(1, 0.35 * cm))

    # ── 良かった点 ────────────────────────────────────────────────────────
    story.append(Paragraph(_safe("▶ 総合評価"), styles["section"]))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY, thickness=0.5))
    story.append(Spacer(1, 0.1 * cm))
    story.extend(_write_box("✅  良かった点:", 4, styles))
    story.append(Spacer(1, 0.2 * cm))
    story.extend(_write_box("📌  次回の課題:", 4, styles))
    story.append(Spacer(1, 0.3 * cm))

    # ── フェーズ別評価 ────────────────────────────────────────────────────
    story.append(Paragraph(_safe("▶ フェーズ別評価"), styles["section"]))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY, thickness=0.5))
    story.append(Spacer(1, 0.1 * cm))

    phases = [
        (
            "助走", "Approach",
            ["助走スピードは適切か", "ボールを後方に引くタイミング", "体の向きと重心位置"],
        ),
        (
            "クロスステップ", "Cross Step",
            ["クロスステップのリズム", "肩・腰の回転準備", "左腕の引きつけ"],
        ),
        (
            "ブロック", "Block",
            ["左脚のブロックが有効か", "上体の前傾角度", "腰から肩への回転順序"],
        ),
        (
            "リリース", "Release",
            ["リリース角度・タイミング", "手首のスナップ", "手首速度ピークの位置"],
        ),
        (
            "フォロースルー", "Follow Through",
            ["体の回転が最後まで続いているか", "安全に止まれているか", "バランスの維持"],
        ),
    ]

    for ph_jp, ph_en, chk_pts in phases:
        story.extend(_phase_section(ph_jp, ph_en, chk_pts, styles))
        story.append(Spacer(1, 0.2 * cm))

    # ── 自由メモ欄 ───────────────────────────────────────────────────────
    story.append(Paragraph(_safe("▶ メモ / その他"), styles["section"]))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY, thickness=0.5))
    story.append(Spacer(1, 0.1 * cm))
    story.extend(_write_box("メモ:", 6, styles))
    story.append(Spacer(1, 0.3 * cm))

    # ── 免責文 ────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Paragraph(_safe(_DISCLAIMER), styles["disclaimer"]))

    return story


# ── エントリポイント ──────────────────────────────────────────────────────────

def generate_coach_review_sheet_for_job(job_dir: Path) -> Path:
    """コーチレビューシート PDF を生成して返す。

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ

    Returns
    -------
    Path
        生成された PDF のパス: ``<job_dir>/report/coach_review_sheet.pdf``
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "coach_review_sheet.pdf"

    styles = _make_styles()
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN_H,
        rightMargin=MARGIN_H,
        topMargin=BODY_TOP_MARGIN,
        bottomMargin=BODY_BOT_MARGIN,
        title="コーチレビューシート — やり投げ動作解析",
        author="やり投げ動作解析システム",
    )
    doc.build(
        _build_story(job_dir, styles),
        onFirstPage=_draw_header_footer,
        onLaterPages=_draw_header_footer,
    )
    logger.info("[coach_review_sheet] PDF 生成完了: %s", out_path)
    return out_path
