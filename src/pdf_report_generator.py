"""
pdf_report_generator.py — Javelin Motion Analysis PDF Report Generator

Generates a structured PDF report from job data (job.json + report.json +
representative frames + graph images) using ReportLab.

Usage:
    from src.pdf_report_generator import generate_pdf_report_for_job
    pdf_path = generate_pdf_report_for_job(Path("jobs/20260508_181930_c4bd"))
    # -> Path("jobs/20260508_181930_c4bd/report/report.pdf")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.frames import Frame
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# ── 日本語フォント設定 ─────────────────────────────────────────────────────────────────────────────

_WINDOWS_FONT_CANDIDATES: list[tuple[str, str]] = [
    ("Meiryo",   "C:/Windows/Fonts/meiryo.ttc"),
    ("MSGothic", "C:/Windows/Fonts/msgothic.ttc"),
    ("YuGothic", "C:/Windows/Fonts/YuGothM.ttc"),
]


def _setup_japanese_font() -> tuple[str, str, str]:
    """Windows フォントフォルダから日本語 TrueType フォントを探して ReportLab に登録する。

    僕さいフォントまたは登録失敗時は ("" , "", "") を返す。

    Returns
    -------
    tuple[str, str, str]
        (標準フォント名, 太字フォント名, フォントファイルパス)
    """
    for font_name, font_path in _WINDOWS_FONT_CANDIDATES:
        p = Path(font_path)
        if not p.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(font_name, str(p), subfontIndex=0))
            bold_name = font_name + "Bold"
            try:
                pdfmetrics.registerFont(TTFont(bold_name, str(p), subfontIndex=1))
            except Exception:
                bold_name = font_name  # 太字サブフォントがなければ標準を流用
            logger.info(
                "[pdf_report_generator] 日本語フォント登録完了: %s (regular=%s, bold=%s)",
                font_path, font_name, bold_name,
            )
            return font_name, bold_name, font_path
        except Exception as exc:
            logger.warning(
                "[pdf_report_generator] フォント登録失敗 (%s): %s", font_path, exc
            )
    logger.info(
        "[pdf_report_generator] 日本語フォントが見つかりません。Helvetica にフォールバックします。"
    )
    return "", "", ""


_JP_FONT, _JP_FONT_BOLD, _JP_FONT_PATH = _setup_japanese_font()


def _fn(bold: bool = False) -> str:
    """使用するフォント名を返す（日本語フォント優先、なければ Helvetica）。

    Args:
        bold: True の場合は太字フォント名を返す。
    """
    if bold:
        return _JP_FONT_BOLD if _JP_FONT_BOLD else "Helvetica-Bold"
    return _JP_FONT if _JP_FONT else "Helvetica"


# ── 定数 ──────────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4           # 595.27 x 841.89 pt
MARGIN_L = 2.0 * cm
MARGIN_R = 2.0 * cm
MARGIN_T = 2.0 * cm
MARGIN_B = 2.0 * cm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

BRAND_BLUE   = colors.HexColor("#1A4D8F")
BRAND_ORANGE = colors.HexColor("#E86A2E")
LIGHT_GRAY   = colors.HexColor("#F5F5F5")
MID_GRAY     = colors.HexColor("#CCCCCC")
TEXT_DARK    = colors.HexColor("#1A1A1A")

# ── スタイル ──────────────────────────────────────────────────────────────────

def _make_styles() -> dict:
    base = getSampleStyleSheet()

    def s(name, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    return {
        "cover_title": s(
            "CoverTitle",
            fontName=_fn(bold=True),
            fontSize=28,
            textColor=BRAND_BLUE,
            spaceAfter=6,
            alignment=TA_CENTER,
        ),
        "cover_subtitle": s(
            "CoverSubtitle",
            fontName=_fn(),
            fontSize=13,
            textColor=BRAND_ORANGE,
            spaceAfter=2,
            alignment=TA_CENTER,
        ),
        "cover_date": s(
            "CoverDate",
            fontName=_fn(),
            fontSize=10,
            textColor=colors.grey,
            alignment=TA_CENTER,
        ),
        "section_heading": s(
            "SectionHeading",
            fontName=_fn(bold=True),
            fontSize=14,
            textColor=BRAND_BLUE,
            spaceBefore=12,
            spaceAfter=4,
        ),
        "body": s(
            "Body",
            fontName=_fn(),
            fontSize=10,
            textColor=TEXT_DARK,
            spaceAfter=2,
            leading=16,
        ),
        "body_sm": s(
            "BodySm",
            fontName=_fn(),
            fontSize=9,
            textColor=colors.grey,
            spaceAfter=1,
            leading=14,
        ),
        "caption": s(
            "Caption",
            fontName=_fn(),
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "disclaimer": s(
            "Disclaimer",
            fontName=_fn(),
            fontSize=9,
            textColor=TEXT_DARK,
            spaceAfter=6,
            leading=16,
            alignment=TA_LEFT,
        ),
        "label": s(
            "Label",
            fontName=_fn(bold=True),
            fontSize=10,
            textColor=TEXT_DARK,
            spaceAfter=2,
        ),
        "kv_key": s(
            "KVKey",
            fontName=_fn(bold=True),
            fontSize=10,
            textColor=BRAND_BLUE,
        ),
        "kv_val": s(
            "KVVal",
            fontName=_fn(),
            fontSize=10,
            textColor=TEXT_DARK,
        ),
    }


# ── ヘッダー・フッター描画 ─────────────────────────────────────────────────────

def _draw_header_footer(canvas, doc):
    canvas.saveState()
    # ヘッダー
    canvas.setFillColor(BRAND_BLUE)
    canvas.rect(0, PAGE_H - 1.2 * cm, PAGE_W, 1.2 * cm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(MARGIN_L, PAGE_H - 0.8 * cm, "Javelin Motion Analysis Report")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 0.8 * cm, doc.title or "")
    # フッター
    canvas.setFillColor(MID_GRAY)
    canvas.rect(0, 0, PAGE_W, 1.0 * cm, fill=1, stroke=0)
    canvas.setFillColor(colors.grey)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(MARGIN_L, 0.35 * cm,
                      "Generated by Javelin Video Analysis  |  Not for medical use")
    canvas.drawRightString(PAGE_W - MARGIN_R, 0.35 * cm,
                           f"Page {doc.page}")
    canvas.restoreState()


def _draw_cover_footer(canvas, doc):
    """表紙のフッターはシンプル版"""
    canvas.saveState()
    canvas.setFillColor(BRAND_ORANGE)
    canvas.rect(0, 0, PAGE_W, 0.5 * cm, fill=1, stroke=0)
    canvas.restoreState()


# ── ユーティリティ ────────────────────────────────────────────────────────────

def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _format_dt(dt_str: Optional[str]) -> str:
    if not dt_str:
        return "—"
    try:
        return datetime.fromisoformat(dt_str).strftime("%Y-%m-%d  %H:%M:%S")
    except Exception:
        return dt_str


def _scale_image(img_path: Path, max_w: float, max_h: float) -> tuple[float, float]:
    """画像を最大サイズに収まるようにアスペクト比を保ちリサイズ。"""
    try:
        ir = ImageReader(str(img_path))
        iw, ih = ir.getSize()
        scale = min(max_w / iw, max_h / ih, 1.0)
        return iw * scale, ih * scale
    except Exception:
        return max_w, max_w * 0.5


def _kv_table(pairs: list[tuple[str, str]], styles: dict) -> Table:
    """キー・バリューペアの2列テーブルを生成。"""
    data = [[Paragraph(k, styles["kv_key"]), Paragraph(v, styles["kv_val"])]
            for k, v in pairs]
    col_w = [CONTENT_W * 0.38, CONTENT_W * 0.62]
    tbl = Table(data, colWidths=col_w, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [LIGHT_GRAY, colors.white]),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.25, MID_GRAY),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def _hr(styles: dict) -> List:
    return [Spacer(1, 4), HRFlowable(width=CONTENT_W, color=MID_GRAY), Spacer(1, 4)]


def _sanitize_for_helvetica(text: str) -> str:
    """日本語フォントが登録済みならそのまま返す。

    Helvetica のみの場合は Latin-1 で表現できない文字を '?' に置換する。
    """
    if _JP_FONT:
        return text  # 日本語フォント登録済み—サニタイズ不要
    result: list[str] = []
    for ch in text:
        try:
            ch.encode("latin-1")
            result.append(ch)
        except (UnicodeEncodeError, ValueError):
            result.append("?")
    return "".join(result)


# ── ページビルダー関数 ────────────────────────────────────────────────────────

def _build_cover(job: dict, rep: dict, styles: dict,
                 job_dir: Optional[Path] = None) -> List:
    story = []
    story.append(Spacer(1, 4.0 * cm))
    story.append(Paragraph("動作解析レポート", styles["cover_title"]))
    story.append(Paragraph("Javelin Motion Analysis Report", styles["cover_subtitle"]))
    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width=CONTENT_W * 0.5, color=BRAND_ORANGE,
                             hAlign="CENTER", thickness=2))
    story.append(Spacer(1, 0.6 * cm))

    job_id = job.get("job_id", "—")
    story.append(Paragraph(f"Job ID: {job_id}", styles["cover_subtitle"]))
    story.append(Spacer(1, 0.3 * cm))

    created  = _format_dt(job.get("created_at"))
    updated  = _format_dt(job.get("updated_at"))
    story.append(Paragraph(f"Created:  {created}", styles["cover_date"]))
    story.append(Paragraph(f"Updated:  {updated}", styles["cover_date"]))
    story.append(Spacer(1, 2.0 * cm))

    # メタ情報グリッド
    input_file = job.get("input_file", "—")
    input_name = Path(input_file).name if input_file else "—"
    height_m   = job.get("height_m")
    height_str = f"{height_m:.2f} m" if height_m else "—"

    # status が "running" でも output/ に mp4 があれば Completed と表示
    raw_status = str(job.get("status", "—")).lower()
    effective_status = str(job.get("status", "—")).capitalize()
    if raw_status == "running" and job_dir is not None:
        _out_dir = job_dir / "output"
        if _out_dir.exists() and any(_out_dir.glob("*.mp4")):
            effective_status = "Completed"

    pairs = [
        ("Status",      effective_status),
        ("Mode",        str(job.get("mode", "—"))),
        ("Height",      height_str),
        ("Input video", input_name),
    ]
    story.append(_kv_table(pairs, styles))
    story.append(PageBreak())
    return story


def _build_analysis_summary(job: dict, rep: dict, report_dir: Path, styles: dict) -> List:
    story = []
    story.append(Paragraph("解析サマリー  /  Analysis Summary", styles["section_heading"]))
    story.extend(_hr(styles))

    analysis   = rep.get("analysis", {})
    video_info = rep.get("video_info", {})

    # ── analysis_summary.json のロード（存在すれば拡張データとして使用）────
    summary_path = report_dir / "analysis_summary.json"
    summary: dict = (_load_json(summary_path) or {}) if summary_path.exists() else {}
    use_summary = bool(summary) and summary.get("status") != "skipped"

    # ── 動画情報 ─────────────────────────────────────────────────────────────
    story.append(Paragraph("動画情報", styles["label"]))
    if use_summary:
        sv = summary.get("video") or {}
        # フラット形式（video キーなし）にも対応
        duration_val  = sv.get("duration_sec") if sv else summary.get("duration_sec")
        frame_cnt_val = sv.get("frame_count")  if sv else summary.get("total_frames")
        fps_val       = sv.get("fps")           if sv else (summary.get("fps_estimated") or video_info.get("fps"))
        vid_pairs: list[tuple[str, str]] = [
            ("動画時間",       f"{duration_val:.2f} 秒" if isinstance(duration_val, (int, float)) else "—"),
            ("総フレーム数",   str(frame_cnt_val) if frame_cnt_val is not None else "—"),
            ("解像度",         f"{video_info.get('width', '—')} × {video_info.get('height', '—')} px"),
            ("フレームレート", f"{fps_val}" if fps_val is not None else str(video_info.get("fps", "—"))),
        ]
    else:
        vid_pairs = [
            ("解像度",         f"{video_info.get('width', '—')} × {video_info.get('height', '—')} px"),
            ("フレームレート", str(video_info.get("fps", "—"))),
            ("総フレーム数",   str(video_info.get("total_frames", "—"))),
            ("動画時間",       f"{video_info.get('duration_s', '—')} 秒"),
        ]
    story.append(_kv_table(vid_pairs, styles))
    story.append(Spacer(1, 0.4 * cm))

    # ── 姿勢解析メトリクス（report.json より）──────────────────────────────
    if analysis:
        story.append(Paragraph("姿勢解析メトリクス", styles["label"]))
        _rs = analysis.get("release_speed_kmh")
        ana_pairs: list[tuple[str, str]] = [
            ("身長 (m)",             str(analysis.get("height_m", "—"))),
            ("キャリブレーション",   "はい" if analysis.get("calibrated") else "いいえ"),
            ("ポーズ検出フレーム数", str(analysis.get("pose_detected_frames", "—"))),
            ("ポーズ検出率",         f"{analysis.get('pose_detection_rate', 0):.0%}"
                                     if isinstance(analysis.get("pose_detection_rate"), float)
                                     else "—"),
            ("手首 最大速度 (km/h)", str(analysis.get("wrist_max_speed_kmh", "—"))),
            ("手首 平均速度 (km/h)", str(analysis.get("wrist_mean_speed_kmh", "—"))),
            ("リリース速度 (km/h)",  "未計算" if _rs is None else str(_rs)),
        ]
        story.append(_kv_table(ana_pairs, styles))
        story.append(Spacer(1, 0.4 * cm))

    # ── analysis_summary.json の拡張データ ──────────────────────────────────
    if use_summary:
        # Key Metrics（ネスト形式 or フラット形式）
        km = summary.get("key_metrics") or {}
        if not km:
            # フラット形式: wrist_height_* / shoulder_center_x_* が直接ある
            _kf = {k: summary.get(k) for k in (
                "wrist_height_peak_time_sec", "wrist_height_max", "wrist_height_range",
                "shoulder_center_x_start", "shoulder_center_x_end",
                "hip_center_x_start", "hip_center_x_end",
            )}
            if any(v is not None for v in _kf.values()):
                km = _kf
        if km:
            story.append(Paragraph("手首・体幹メトリクス", styles["label"]))
            max_h_time  = km.get("right_wrist_max_height_time_sec") or km.get("wrist_height_peak_time_sec")
            max_h_norm  = km.get("right_wrist_max_height_norm")     or km.get("wrist_height_max")
            h_range     = km.get("wrist_height_range")
            torso_start = km.get("torso_center_x_start") or km.get("shoulder_center_x_start")
            torso_end   = km.get("torso_center_x_end")   or km.get("shoulder_center_x_end")
            _pairs = [
                ("手首 最高点到達時刻 (秒)",    f"{max_h_time:.3f}" if isinstance(max_h_time, (int, float)) else "—"),
                ("手首 最高到達高さ (正規化)",   f"{max_h_norm:.4f}" if isinstance(max_h_norm, (int, float)) else "—"),
            ]
            if h_range is not None:
                _pairs.append(("手首 高さ可動域 (正規化)", f"{h_range:.4f}"))
            _pairs += [
                ("体幹中心X 開始 (正規化)",     f"{torso_start:.4f}" if isinstance(torso_start, (int, float)) else "—"),
                ("体幹中心X 終了 (正規化)",     f"{torso_end:.4f}"   if isinstance(torso_end,   (int, float)) else "—"),
            ]
            story.append(_kv_table(_pairs, styles))
            story.append(Spacer(1, 0.4 * cm))

        # Pose Quality
        pq = summary.get("pose_quality") or {}
        if pq:
            story.append(Paragraph("ポーズ検出品質", styles["label"]))
            missing_ratio = pq.get("right_wrist_missing_ratio")
            missing_str   = f"{missing_ratio * 100:.1f} %" if isinstance(missing_ratio, (int, float)) else "—"
            avg_vis = pq.get("average_visibility") or {}

            def _vis_str(key: str) -> str:
                v = avg_vis.get(key)
                return f"{v:.3f}" if isinstance(v, (int, float)) else "—"

            story.append(_kv_table([
                ("右手首 未検出率",   missing_str),
                ("平均可視度: 右肩",  _vis_str("right_shoulder")),
                ("平均可視度: 右肘",  _vis_str("right_elbow")),
                ("平均可視度: 右手首", _vis_str("right_wrist")),
                ("平均可視度: 左肩",  _vis_str("left_shoulder")),
                ("平均可視度: 左肘",  _vis_str("left_elbow")),
                ("平均可視度: 左手首", _vis_str("left_wrist")),
            ], styles))
            story.append(Spacer(1, 0.4 * cm))

        # Warnings from analysis_summary.json
        warnings_list: list = summary.get("warnings") or []
        if warnings_list:
            story.append(Paragraph("警告", styles["label"]))
            for w in warnings_list:
                story.append(Paragraph(f"  • {w}", styles["body_sm"]))
            story.append(Spacer(1, 0.2 * cm))

    # ── Pose Detection Rate 警告ボックス（< 70% で赤表示）──────────────────
    detection_rate: Optional[float] = None
    if isinstance(analysis.get("pose_detection_rate"), float):
        detection_rate = analysis["pose_detection_rate"]
    elif use_summary:
        _pq_dr = summary.get("pose_quality", {}) or {}
        _missing = _pq_dr.get("right_wrist_missing_ratio")
        if isinstance(_missing, (int, float)):
            detection_rate = 1.0 - _missing

    if detection_rate is not None and detection_rate < 0.70:
        pct_str = f"{detection_rate:.0%}"
        warn_para = Paragraph(
            f"警告 / Warning: ポーズ検出率が低い値です ({pct_str})。"
            " 動画品質・カメラアングル・照明を確認してください。"
            f"  Pose detection rate is low ({pct_str})."
            " Please check video quality, camera angle, and lighting.",
            ParagraphStyle(
                "WarnText",
                fontName=_fn(bold=True),
                fontSize=9,
                textColor=colors.white,
                spaceAfter=0,
                leading=14,
            ),
        )
        warn_tbl = Table([[warn_para]], colWidths=[CONTENT_W], hAlign="LEFT")
        warn_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#C0392B")),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(warn_tbl)
        story.append(Spacer(1, 0.3 * cm))

    # ── 有効解析区間（valid_segment.json）─────────────────────────────────
    vs_path = report_dir / "valid_segment.json"
    vs: dict = (_load_json(vs_path) or {}) if vs_path.exists() else {}
    if vs:
        story.append(Paragraph("有効解析区間  /  Valid Pose Segment", styles["label"]))
        vs_ratio = vs.get("valid_ratio")
        vs_start_f = vs.get("valid_start_frame")
        vs_end_f   = vs.get("valid_end_frame")
        vs_start_t = vs.get("valid_start_time_sec")
        vs_end_t   = vs.get("valid_end_time_sec")
        vs_valid   = vs.get("valid_frame_count")
        vs_total   = vs.get("total_frame_count")

        def _ft(v) -> str:
            return f"{v:.2f} sec" if isinstance(v, (int, float)) else "—"

        vs_pairs: list[tuple[str, str]] = [
            ("Valid frames",       f"{vs_valid} / {vs_total}" if vs_valid is not None and vs_total is not None else "—"),
            ("Valid ratio",        f"{vs_ratio:.1%}" if isinstance(vs_ratio, (int, float)) else "—"),
            ("Start frame",        str(vs_start_f) if vs_start_f is not None else "—"),
            ("End frame",          str(vs_end_f)   if vs_end_f is not None else "—"),
            ("Start time",         _ft(vs_start_t)),
            ("End time",           _ft(vs_end_t)),
        ]
        story.append(_kv_table(vs_pairs, styles))
        story.append(Spacer(1, 0.3 * cm))

        # valid_ratio < 0.7 → 警告ボックス（オレンジ）
        if isinstance(vs_ratio, (int, float)) and vs_ratio < 0.70:
            _warn_color = colors.HexColor("#C0392B") if vs_ratio < 0.30 else BRAND_ORANGE
            _vs_warn_para = Paragraph(
                f"解析精度に注意 / Caution: 有効ポーズ区間が全体の {vs_ratio:.0%} です。"
                " 動画品質・カメラアングル・照明を改善すると精度が向上します。"
                f"  Valid pose coverage is {vs_ratio:.0%}."
                " Consider improving video quality, camera angle, or lighting.",
                ParagraphStyle(
                    "VSWarnText",
                    fontName=_fn(bold=True),
                    fontSize=9,
                    textColor=colors.white,
                    spaceAfter=0,
                    leading=14,
                ),
            )
            _vs_warn_tbl = Table([[_vs_warn_para]], colWidths=[CONTENT_W], hAlign="LEFT")
            _vs_warn_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), _warn_color),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("TOPPADDING",    (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(_vs_warn_tbl)
            story.append(Spacer(1, 0.2 * cm))

        # warnings リスト
        vs_warnings: list = vs.get("warnings") or []
        if vs_warnings:
            for w in vs_warnings:
                story.append(Paragraph(f"  • {w}", styles["body_sm"]))
            story.append(Spacer(1, 0.2 * cm))

    # ── 出力ファイルサマリ ─────────────────────────────────────────────────
    story.append(Paragraph("出力ファイル一覧", styles["label"]))
    frames_dir  = report_dir / "frames"
    graphs_dir  = report_dir / "graphs"
    csv_path    = report_dir / "pose_landmarks.csv"
    frame_count = len(list(frames_dir.glob("*.jpg")) + list(frames_dir.glob("*.png"))) \
                  if frames_dir.exists() else 0
    graph_count = len(list(graphs_dir.glob("*.png"))) if graphs_dir.exists() else 0

    # 実際の output/ ディレクトリをスキャン（job["output_files"] は不正確なため）
    out_dir = report_dir.parent / "output"
    mp4_list = sorted(out_dir.glob("*.mp4")) if out_dir.exists() else []

    summary_pairs: list[tuple[str, str]] = [
        ("Output videos",         f"{len(mp4_list)} file(s)"),
        ("pose_landmarks.csv",    "✓ Present" if csv_path.exists() else "✗ Not found"),
        ("Representative frames", f"{frame_count} image(s)"),
        ("Graph images",          f"{graph_count} image(s)"),
    ]
    story.append(_kv_table(summary_pairs, styles))
    story.append(Spacer(1, 0.4 * cm))

    if mp4_list:
        story.append(Paragraph("出力動画ファイル", styles["label"]))
        for mp4 in mp4_list:
            story.append(Paragraph(f"  • {mp4.name}", styles["body_sm"]))

    story.append(PageBreak())
    return story


def _build_frames_pages(report_dir: Path, styles: dict,
                        images_per_page: int = 4) -> List:
    story = []
    story.append(Paragraph("代表フレーム  /  Representative Frames", styles["section_heading"]))
    story.extend(_hr(styles))

    frames_dir = report_dir / "frames"
    frame_imgs: List[Path] = []
    if frames_dir.exists():
        frame_imgs = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.png"))

    if not frame_imgs:
        story.append(Paragraph("代表フレームが見つかりませんでした。", styles["body"]))
        story.append(PageBreak())
        return story

    # 1ページに images_per_page 枚（2列×2行）
    max_img_h = (PAGE_H - MARGIN_T - MARGIN_B - 3.0 * cm) / 2 - 1.2 * cm
    max_img_w = (CONTENT_W - 0.4 * cm) / 2

    for i in range(0, len(frame_imgs), images_per_page):
        chunk = frame_imgs[i: i + images_per_page]
        # 2列のテーブルで配置
        rows = []
        captions = []
        for j in range(0, len(chunk), 2):
            row_imgs = chunk[j: j + 2]
            row_cells = []
            cap_cells = []
            for img_path in row_imgs:
                w, h = _scale_image(img_path, max_img_w, max_img_h)
                try:
                    img = Image(str(img_path), width=w, height=h)
                    row_cells.append(img)
                    cap_cells.append(Paragraph(img_path.name, styles["caption"]))
                except Exception:
                    row_cells.append(Paragraph("(image load error)", styles["body_sm"]))
                    cap_cells.append(Paragraph("", styles["caption"]))
            # 2列揃え
            while len(row_cells) < 2:
                row_cells.append("")
                cap_cells.append("")
            rows.append(row_cells)
            captions.append(cap_cells)

        tbl_data = []
        for img_row, cap_row in zip(rows, captions):
            tbl_data.append(img_row)
            tbl_data.append(cap_row)

        col_w = [CONTENT_W / 2, CONTENT_W / 2]
        tbl = Table(tbl_data, colWidths=col_w, hAlign="CENTER")
        tbl.setStyle(TableStyle([
            ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",  (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(tbl)

        if i + images_per_page < len(frame_imgs):
            story.append(PageBreak())

    story.append(PageBreak())
    return story


def _build_graphs_pages(report_dir: Path, styles: dict,
                        images_per_page: int = 2) -> List:
    story = []
    story.append(Paragraph("解析グラフ  /  Analysis Graphs", styles["section_heading"]))
    story.extend(_hr(styles))

    graphs_dir = report_dir / "graphs"
    graph_imgs: List[Path] = []
    if graphs_dir.exists():
        graph_imgs = sorted(graphs_dir.glob("*.png"))

    if not graph_imgs:
        story.append(Paragraph("グラフ画像が見つかりませんでした。", styles["body"]))
        story.append(PageBreak())
        return story

    max_img_h = (PAGE_H - MARGIN_T - MARGIN_B - 3.0 * cm) / images_per_page - 1.2 * cm
    max_img_w = CONTENT_W * 0.95

    for i, img_path in enumerate(graph_imgs):
        w, h = _scale_image(img_path, max_img_w, max_img_h)
        try:
            img = Image(str(img_path), width=w, height=h)
            cap = Paragraph(img_path.stem.replace("_", " ").title(), styles["caption"])
            story.append(KeepTogether([img, cap]))
        except Exception:
            story.append(Paragraph(f"(Could not load: {img_path.name})", styles["body_sm"]))

        story.append(Spacer(1, 0.5 * cm))

        # images_per_page ごとにページブレーク
        if (i + 1) % images_per_page == 0 and i + 1 < len(graph_imgs):
            story.append(PageBreak())

    story.append(PageBreak())
    return story


def _build_coach_comment(customer_info: dict, styles: dict) -> List:
    """依頼情報 / コーチコメント（簡易レビュー）セクションを生成する。

    customer_info.json の全フィールドを反映する。
    各フィールドが空または存在しない場合でも安全に動作する（空 dict でも可）。

    Parameters
    ----------
    customer_info : dict
        customer_info.json を読み込んだ dict
    styles : dict
        _make_styles() の返り値
    """
    story: List = []
    story.append(Paragraph(
        "コーチコメント / 簡易レビュー  /  Coach Comment",
        styles["section_heading"],
    ))
    story.extend(_hr(styles))
    story.append(Spacer(1, 0.2 * cm))

    # ── ヘルパー ──────────────────────────────────────────────────────────────
    def _s(key: str, default: str = "\u2014") -> str:
        """フィールドを安全に取り出してサニタイズする。"""
        v = customer_info.get(key) or ""
        return _sanitize_for_helvetica(str(v).strip()) if v else default

    # 身長
    _height_raw = customer_info.get("height_m")
    try:
        height_str = f"{float(_height_raw):.2f} m" if _height_raw is not None else "\u2014"
    except (ValueError, TypeError):
        height_str = "\u2014"

    # 支払・納品ステータスの日本語マッピング
    _paid_map = {
        "paid":    "支払済",
        "unpaid":  "未払い",
        "unknown": "不明",
    }
    _delivery_map = {
        "not_started": "未着手",
        "in_progress": "進行中",
        "delivered":   "納品済",
        "unknown":     "不明",
    }
    paid_raw     = str(customer_info.get("paid_status")     or "unknown")
    delivery_raw = str(customer_info.get("delivery_status") or "not_started")
    paid_str     = _paid_map.get(paid_raw,     paid_raw)
    delivery_str = _delivery_map.get(delivery_raw, delivery_raw)

    # ── アスリート情報テーブル ────────────────────────────────────────────────
    athlete_pairs: list[tuple[str, str]] = [
        ("お名前",          _s("customer_name")),
        ("Instagram",      _s("instagram_id")),
        ("種目",            _s("event")),
        ("利き腕",          _s("dominant_hand")),
        ("身長",            height_str),
        ("撮影方向",        _s("camera_angle")),
        ("支払ステータス",  paid_str),
        ("納品ステータス",  delivery_str),
    ]
    story.append(Paragraph("アスリート情報", styles["label"]))
    story.append(_kv_table(athlete_pairs, styles))
    story.append(Spacer(1, 0.5 * cm))

    # ── ご相談内容 ────────────────────────────────────────────────────────────
    story.append(Paragraph("ご相談内容", styles["label"]))
    request_note: str = (customer_info.get("request_note") or "").strip()
    if request_note:
        story.append(Paragraph(_sanitize_for_helvetica(request_note), styles["body"]))
    else:
        story.append(Paragraph("記載なし", styles["body_sm"]))
    story.append(Spacer(1, 0.5 * cm))

    # ── コーチコメント（簡易レビュー） ────────────────────────────────────────
    story.append(Paragraph("コーチコメント", styles["label"]))
    coach_comment: str = (customer_info.get("coach_comment") or "").strip()
    if coach_comment:
        story.append(Paragraph(_sanitize_for_helvetica(coach_comment), styles["body"]))
    else:
        story.append(Paragraph("コメント未入力", styles["body_sm"]))

    story.append(PageBreak())
    return story


def _build_analysis_summary_json_section(report_dir: Path, styles: dict) -> List:
    """
    report/analysis_summary.json が存在すれば「Analysis Summary」ページを生成する。

    存在しない場合は空リストを返す（PDF 生成全体を止めない）。
    """
    summary_path = report_dir / "analysis_summary.json"
    if not summary_path.exists():
        return []

    summary = _load_json(summary_path)
    if not summary:
        return []

    # status == "skipped" のときも簡易表示する
    story: List = []
    story.append(Paragraph("解析サマリー  /  Analysis Summary", styles["section_heading"]))
    story.extend(_hr(styles))

    status = summary.get("status", "unknown")
    if status == "skipped":
        reason = summary.get("reason", "—")
        story.append(Paragraph(f"スキップ  —  {reason}", styles["body_sm"]))
        story.append(PageBreak())
        return story

    # ── Video Info ───────────────────────────────────────────────────────────
    video = summary.get("video") or {}
    # フラット形式（video キーなし）にも対応
    duration  = video.get("duration_sec") if video else summary.get("duration_sec")
    frame_cnt = video.get("frame_count")  if video else summary.get("total_frames")
    fps_est   = video.get("fps")          if video else summary.get("fps_estimated")
    duration_str  = f"{duration:.2f} 秒" if isinstance(duration, (int, float)) else "—"
    frame_cnt_str = str(frame_cnt) if frame_cnt is not None else "—"
    fps_str       = str(fps_est)   if fps_est   is not None else "—"

    # ── Key Metrics ──────────────────────────────────────────────────────────
    km = summary.get("key_metrics") or {}
    max_h_time  = km.get("right_wrist_max_height_time_sec") or summary.get("wrist_height_peak_time_sec")
    max_h_norm  = km.get("right_wrist_max_height_norm")     or summary.get("wrist_height_max")
    h_range     = summary.get("wrist_height_range")
    torso_start = km.get("torso_center_x_start") or summary.get("shoulder_center_x_start")
    torso_end   = km.get("torso_center_x_end")   or summary.get("shoulder_center_x_end")

    max_h_time_str  = f"{max_h_time:.3f}" if isinstance(max_h_time, (int, float)) else "—"
    max_h_norm_str  = f"{max_h_norm:.4f}" if isinstance(max_h_norm, (int, float)) else "—"
    h_range_str     = f"{h_range:.4f}"    if isinstance(h_range,    (int, float)) else "—"
    torso_start_str = f"{torso_start:.4f}" if isinstance(torso_start, (int, float)) else "—"
    torso_end_str   = f"{torso_end:.4f}"   if isinstance(torso_end,   (int, float)) else "—"

    # ── Pose Quality ─────────────────────────────────────────────────────────
    pq = summary.get("pose_quality") or {}
    missing_ratio = pq.get("right_wrist_missing_ratio")
    missing_str   = (
        f"{missing_ratio * 100:.1f} %"
        if isinstance(missing_ratio, (int, float))
        else "—"
    )

    avg_vis: dict = pq.get("average_visibility") or {}

    def _vis_str(key: str) -> str:
        v = avg_vis.get(key)
        return f"{v:.3f}" if isinstance(v, (int, float)) else "—"

    story.append(Paragraph("動画情報", styles["label"]))
    story.append(_kv_table([
        ("動画時間",       duration_str),
        ("総フレーム数",   frame_cnt_str),
        ("フレームレート", fps_str),
    ], styles))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("手首・体幹メトリクス", styles["label"]))
    story.append(_kv_table([
        ("手首 最高点到達時刻 (秒)",    max_h_time_str),
        ("手首 最高到達高さ (正規化)",   max_h_norm_str),
        ("手首 高さ可動域 (正規化)",    h_range_str),
        ("体幹中心X 開始 (正規化)",     torso_start_str),
        ("体幹中心X 終了 (正規化)",     torso_end_str),
    ], styles))
    story.append(Spacer(1, 0.3 * cm))

    if pq:
        story.append(Paragraph("ポーズ検出品質", styles["label"]))
        story.append(_kv_table([
            ("右手首 未検出率",    missing_str),
            ("平均可視度: 右肩",   _vis_str("right_shoulder")),
            ("平均可視度: 右肘",   _vis_str("right_elbow")),
            ("平均可視度: 右手首", _vis_str("right_wrist")),
            ("平均可視度: 左肩",   _vis_str("left_shoulder")),
            ("平均可視度: 左肘",   _vis_str("left_elbow")),
            ("平均可視度: 左手首", _vis_str("left_wrist")),
        ], styles))
        story.append(Spacer(1, 0.3 * cm))

    # ── Warnings ─────────────────────────────────────────────────────────────
    warnings: list = summary.get("warnings") or []
    if warnings:
        story.append(Paragraph("警告", styles["label"]))
        for w in warnings:
            story.append(Paragraph(f"  • {w}", styles["body_sm"]))
        story.append(Spacer(1, 0.2 * cm))

    # ── Note ─────────────────────────────────────────────────────────────────
    note = (
        "本解析は可視化サポート用です。"
        "コーチング・医療・競技力評価の代替ではありません。"
    )
    story.append(Paragraph(note, styles["body_sm"]))

    story.append(PageBreak())
    return story


def _build_disclaimer(styles: dict) -> List:
    story = []
    story.append(Paragraph("注意事項・免責事項  /  Notes & Disclaimer", styles["section_heading"]))
    story.extend(_hr(styles))
    story.append(Spacer(1, 0.4 * cm))

    disclaimer_lines = [
        "本解析は、動画から身体の動きや軌跡を可視化し、練習の振り返りを補助するための参考資料です。"
        "競技指導・医療判断・怪我の診断を代替するものではありません。",
        "",
        "This report is generated automatically from pose estimation data "
        "obtained through computer vision processing. "
        "It is <b>not</b> a medical diagnosis or professional coaching assessment.",
        "",
        "姿勢推定の精度は、カメラアングル・動画品質・被写体の陰影・照明条件・服装などによって変動します。"
        "速度・角度・軌跡などの推定値には計測誤差が含まれる場合があります。",
        "",
        f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Software: Javelin Video Analysis  |  Engine: MediaPipe Pose",
        f"Font: {_JP_FONT_PATH if _JP_FONT_PATH else 'Helvetica (Latin-1 fallback)'}",
    ]
    for line in disclaimer_lines:
        story.append(Paragraph(line if line else "&nbsp;", styles["disclaimer"]))

    return story


# ── メインエントリポイント ────────────────────────────────────────────────────

def generate_pdf_report_for_job(job_dir: Path) -> Path:
    """
    job_dir 配下のデータを読み込み、A4 PDF レポートを生成して返す。

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ (例: jobs/20260508_181930_c4bd)

    Returns
    -------
    Path
        生成された PDF のパス (job_dir/report/report.pdf)

    Raises
    ------
    RuntimeError
        PDF 生成に失敗した場合
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    # データ読み込み
    job_json_path = job_dir / "job.json"
    job: dict = _load_json(job_json_path) or {}

    # report.json は複数ある場合があるため最新を使用
    rep_json_files = sorted(
        (job_dir / "output").glob("*_report.json")
    ) if (job_dir / "output").exists() else []
    rep_json_path = report_dir / "report.json"

    rep: dict = {}
    if rep_json_path.exists():
        rep = _load_json(rep_json_path) or {}
    elif rep_json_files:
        rep = _load_json(rep_json_files[-1]) or {}

    # customer_info.json の読み込み（存在しない場合は空 dict）
    customer_info: dict = _load_json(job_dir / "customer_info.json") or {}

    styles = _make_styles()

    # ストーリー組み立て
    story: List = []
    story.extend(_build_cover(job, rep, styles, job_dir=job_dir))
    try:
        story.extend(_build_coach_comment(customer_info, styles))   # page 2: 依頼情報
    except Exception as _ce:
        logger.warning("[pdf_report_generator] coach comment section skipped: %s", _ce)
    story.extend(_build_analysis_summary(job, rep, report_dir, styles))
    story.extend(_build_frames_pages(report_dir, styles, images_per_page=4))
    story.extend(_build_graphs_pages(report_dir, styles, images_per_page=2))
    story.extend(_build_disclaimer(styles))

    # PDF 出力
    pdf_path = report_dir / "report.pdf"
    job_id = job.get("job_id", job_dir.name)

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=MARGIN_T + 1.2 * cm,   # ヘッダー分
        bottomMargin=MARGIN_B + 1.0 * cm, # フッター分
        title=job_id,
        author="Javelin Video Analysis",
        subject="Motion Analysis Report",
    )

    try:
        doc.build(story, onFirstPage=_draw_cover_footer,
                  onLaterPages=_draw_header_footer)
    except Exception as e:
        raise RuntimeError(f"PDF build failed: {e}") from e

    logger.info(
        "[pdf_report_generator] PDF saved: %s  (font: %s)",
        pdf_path,
        _JP_FONT_PATH if _JP_FONT_PATH else "Helvetica (fallback)",
    )
    return pdf_path
