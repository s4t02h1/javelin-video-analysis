"""
key_frame_sheet_generator.py — キーフレームシート PDF 生成

代表フレーム画像をフェーズ別に並べた PDF を生成する。

Usage:
    from src.key_frame_sheet_generator import generate_key_frame_sheet_for_job
    pdf_path = generate_key_frame_sheet_for_job(Path("jobs/20260510_012144_0513"))
    # -> Path("jobs/20260510_012144_0513/report/key_frame_sheet.pdf")
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ── 日本語フォント設定 ──────────────────────────────────────────────────────────

_WINDOWS_FONT_CANDIDATES: list[tuple[str, str]] = [
    ("Meiryo",   "C:/Windows/Fonts/meiryo.ttc"),
    ("MSGothic", "C:/Windows/Fonts/msgothic.ttc"),
    ("YuGothic", "C:/Windows/Fonts/YuGothM.ttc"),
]


def _setup_japanese_font() -> tuple[str, str]:
    for font_name, font_path in _WINDOWS_FONT_CANDIDATES:
        p = Path(font_path)
        if not p.exists():
            continue
        try:
            try:
                pdfmetrics.getFont(font_name)
                bold_name = font_name + "Bold"
                try:
                    pdfmetrics.getFont(bold_name)
                except KeyError:
                    bold_name = font_name
                return font_name, bold_name
            except KeyError:
                pass
            pdfmetrics.registerFont(TTFont(font_name, str(p), subfontIndex=0))
            bold_name = font_name + "Bold"
            try:
                pdfmetrics.registerFont(TTFont(bold_name, str(p), subfontIndex=1))
            except Exception:
                bold_name = font_name
            logger.info("[key_frame_sheet] 日本語フォント登録: %s", font_path)
            return font_name, bold_name
        except Exception as exc:
            logger.warning("[key_frame_sheet] フォント登録失敗 (%s): %s", font_path, exc)
    return "", ""


_JP_FONT, _JP_FONT_BOLD = _setup_japanese_font()


def _fn(bold: bool = False) -> str:
    if bold:
        return _JP_FONT_BOLD if _JP_FONT_BOLD else "Helvetica-Bold"
    return _JP_FONT if _JP_FONT else "Helvetica"


def _safe(text: str) -> str:
    if _JP_FONT:
        return text
    return "".join(c if c.encode("latin-1", errors="ignore") else "?" for c in text)


# ── 定数 ──────────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN  = 1.5 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

BRAND_BLUE   = colors.HexColor("#1A4D8F")
BRAND_ORANGE = colors.HexColor("#E86A2E")
LIGHT_GRAY   = colors.HexColor("#F5F5F5")
MID_GRAY     = colors.HexColor("#CCCCCC")
TEXT_DARK    = colors.HexColor("#1A1A1A")
TEXT_GRAY    = colors.HexColor("#666666")

# フレームファイル名キーワード → フェーズ情報 (日本語名, 英語名, コメント)
_PHASE_MAP: dict[str, tuple[str, str, str]] = {
    "start":  ("開始", "Start",           "助走開始時のポジション"),
    "25pct":  ("25% — 助走期", "25% — Approach",    "助走〜体重移動"),
    "50pct":  ("50% — クロスステップ", "50% — Cross Step", "クロスステップ〜体の向き"),
    "75pct":  ("75% — デリバリー期", "75% — Delivery",    "体を前に倒し投げに入る局面"),
    "90pct":  ("90% — リリース付近", "90% — Release",     "リリース推定付近"),
}

_DISCLAIMER = (
    "本資料は参考資料です。競技指導・医療判断・怪我の診断を代替するものではありません。"
)


# ── スタイル ──────────────────────────────────────────────────────────────────

def _make_styles() -> dict:
    def s(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    return {
        "title": s("KFSTitle", fontName=_fn(True), fontSize=20,
                   textColor=BRAND_BLUE, spaceAfter=4, alignment=TA_CENTER),
        "subtitle": s("KFSSubtitle", fontName=_fn(), fontSize=11,
                      textColor=BRAND_ORANGE, spaceAfter=2, alignment=TA_CENTER),
        "date_line": s("KFSDate", fontName=_fn(), fontSize=8,
                       textColor=colors.grey, alignment=TA_CENTER),
        "phase_title": s("KFSPhaseTitle", fontName=_fn(True), fontSize=12,
                         textColor=BRAND_BLUE, spaceBefore=4, spaceAfter=2),
        "phase_subtitle": s("KFSPhaseSub", fontName=_fn(), fontSize=9,
                            textColor=BRAND_ORANGE, spaceAfter=2),
        "meta_key": s("KFSMetaKey", fontName=_fn(True), fontSize=8,
                      textColor=BRAND_BLUE),
        "meta_val": s("KFSMetaVal", fontName=_fn(), fontSize=8,
                      textColor=TEXT_DARK),
        "comment_label": s("KFSCommentLabel", fontName=_fn(True), fontSize=8,
                           textColor=TEXT_GRAY),
        "comment_space": s("KFSCommentSpace", fontName=_fn(), fontSize=8,
                           textColor=colors.HexColor("#AAAAAA")),
        "missing": s("KFSMissing", fontName=_fn(), fontSize=9,
                     textColor=colors.grey, alignment=TA_CENTER),
        "disclaimer": s("KFSDisclaimer", fontName=_fn(), fontSize=7,
                        textColor=TEXT_GRAY, leading=12, alignment=TA_LEFT),
        "intro": s("KFSIntro", fontName=_fn(), fontSize=9,
                   textColor=TEXT_DARK, leading=14, spaceAfter=4),
    }


# ── ヘッダー・フッター ────────────────────────────────────────────────────────

def _draw_header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(BRAND_BLUE)
    canvas.rect(0, PAGE_H - 1.0 * cm, PAGE_W, 1.0 * cm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(MARGIN, PAGE_H - 0.65 * cm, "Javelin Video Analysis")
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 0.65 * cm, "Key Frame Sheet")
    canvas.setFillColor(MID_GRAY)
    canvas.rect(0, 0, PAGE_W, 0.8 * cm, fill=1, stroke=0)
    canvas.setFillColor(TEXT_GRAY)
    canvas.setFont("Helvetica", 6)
    canvas.drawString(MARGIN, 0.28 * cm, "Not for medical use  |  Reference estimates only")
    canvas.drawRightString(PAGE_W - MARGIN, 0.28 * cm, f"Page {doc.page}")
    canvas.restoreState()


# ── JSON / CSV ヘルパー ──────────────────────────────────────────────────────

def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_csv_lookup(csv_path: Path) -> dict[int, dict]:
    """pose_landmarks.csv を frame 番号をキーにした dict に変換する。
    読み込み失敗時は空 dict を返す。"""
    try:
        import csv
        result: dict[int, dict] = {}
        with csv_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    frame_num = int(row["frame"])
                    result[frame_num] = row
                except (KeyError, ValueError):
                    pass
        return result
    except Exception:
        return {}


def _scale_image(img_path: Path, max_w: float, max_h: float) -> tuple[float, float]:
    try:
        ir = ImageReader(str(img_path))
        iw, ih = ir.getSize()
        scale = min(max_w / iw, max_h / ih, 1.0)
        return iw * scale, ih * scale
    except Exception:
        return max_w, max_w * 0.5


# ── フレーム情報の収集 ────────────────────────────────────────────────────────

def _extract_frame_number(filename: str) -> Optional[int]:
    """frame_0062_25pct.jpg などから 62 を抽出する。"""
    m = re.match(r"frame_(\d+)_", filename)
    return int(m.group(1)) if m else None


def _detect_phase_key(filename: str) -> Optional[str]:
    """ファイル名から _PHASE_MAP のキーを検出する。"""
    name_lower = filename.lower()
    for key in _PHASE_MAP:
        if key in name_lower:
            return key
    return None


def _get_wrist_data_for_frame(csv_lookup: dict[int, dict],
                               frame_num: Optional[int]) -> tuple[str, str]:
    """frame 番号に対応する右手首の高さと時刻を返す。"""
    if frame_num is None or not csv_lookup:
        return "—", "—"
    row = csv_lookup.get(frame_num)
    if not row:
        return "—", "—"
    # height = 1 - y (MediaPipe: y=0 が画面上端、y=1 が下端)
    try:
        wy = float(row.get("right_wrist_y", ""))
        height_norm = round(1.0 - wy, 4)
        height_str = f"{height_norm:.4f} (norm)"
    except (TypeError, ValueError):
        height_str = "—"
    try:
        t = float(row.get("time_sec", ""))
        time_str = f"{t:.3f} 秒"
    except (TypeError, ValueError):
        time_str = "—"
    return height_str, time_str


# ── PDF ストーリー構築 ────────────────────────────────────────────────────────

def _build_story(job_dir: Path, styles: dict) -> list:
    from datetime import datetime
    story = []

    report_dir = job_dir / "report"
    frames_dir = report_dir / "frames"
    csv_path   = report_dir / "pose_landmarks.csv"

    # タイトルブロック
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(_safe("キーフレームシート"), styles["title"]))
    story.append(Paragraph("Key Frame Sheet  —  Javelin Video Analysis", styles["subtitle"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(HRFlowable(width=CONTENT_W * 0.5, color=BRAND_ORANGE,
                             hAlign="CENTER", thickness=2))
    story.append(Spacer(1, 0.25 * cm))

    # Job ID + 日時
    job = _load_json(job_dir / "job.json") or {}
    ci  = _load_json(job_dir / "customer_info.json") or {}
    job_id   = job.get("job_id", "—")
    name     = ci.get("customer_name") or "—"
    gen_at   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph(_safe(f"Job ID: {job_id}  |  {name}  |  出力日: {gen_at}"),
                           styles["date_line"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        _safe("各フレームの右手首高さは 1 − y の正規化値（0=画面下端 / 1=画面上端）です。参考推定値です。"),
        styles["intro"],
    ))

    # CSVルックアップ
    csv_lookup = _load_csv_lookup(csv_path) if csv_path.exists() else {}

    # フレーム画像収集
    if frames_dir.exists():
        frame_files = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.png"))
    else:
        frame_files = []

    if not frame_files:
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph(_safe("代表フレーム画像が見つかりませんでした。"),
                               styles["missing"]))
        story.append(Spacer(1, 0.5 * cm))
    else:
        # 2列グリッドでフレームを並べる
        # 各セルの内容: [phase_title, image or placeholder, meta_table, comment_area]
        cell_w = (CONTENT_W - 0.5 * cm) / 2  # 2列、間隔 0.5 cm
        img_h  = 4.5 * cm

        # フレームを2つずつ処理してTableで並べる
        cells: list = []
        for frame_path in frame_files:
            phase_key  = _detect_phase_key(frame_path.name)
            phase_info = _PHASE_MAP.get(phase_key, ("", "", "")) if phase_key else ("", "", "")
            frame_num  = _extract_frame_number(frame_path.name)
            wrist_h, time_str = _get_wrist_data_for_frame(csv_lookup, frame_num)

            jp_name, en_name, phase_comment = phase_info

            cell_story: list = []

            # フェーズ見出し
            if jp_name:
                cell_story.append(Paragraph(_safe(jp_name), styles["phase_title"]))
                cell_story.append(Paragraph(en_name, styles["phase_subtitle"]))
            else:
                cell_story.append(Paragraph(_safe(frame_path.stem), styles["phase_title"]))

            # フレーム画像
            if frame_path.exists() and frame_path.stat().st_size > 0:
                try:
                    iw, ih = _scale_image(frame_path, cell_w - 0.2 * cm, img_h)
                    cell_story.append(Image(str(frame_path), width=iw, height=ih))
                except Exception:
                    cell_story.append(Paragraph(_safe("(画像読み込みエラー)"),
                                                styles["missing"]))
            else:
                cell_story.append(Spacer(1, img_h))

            # メタ情報テーブル（小さいフォント）
            meta_pairs = [
                ("フレーム",       str(frame_num) if frame_num is not None else "—"),
                ("時刻",          time_str),
                ("右手首高さ",     wrist_h),
            ]
            meta_data = [
                [Paragraph(_safe(k), styles["meta_key"]),
                 Paragraph(_safe(v), styles["meta_val"])]
                for k, v in meta_pairs
            ]
            meta_tbl = Table(
                meta_data,
                colWidths=[cell_w * 0.40, cell_w * 0.60],
                hAlign="LEFT",
            )
            meta_tbl.setStyle(TableStyle([
                ("FONTSIZE",      (0, 0), (-1, -1), 7),
                ("TOPPADDING",    (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING",   (0, 0), (-1, -1), 3),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
                ("GRID",          (0, 0), (-1, -1), 0.25, MID_GRAY),
                ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_GRAY),
            ]))
            cell_story.append(Spacer(1, 0.1 * cm))
            cell_story.append(meta_tbl)

            # コメント欄
            cell_story.append(Spacer(1, 0.1 * cm))
            cell_story.append(Paragraph(_safe("コメント:"), styles["comment_label"]))
            comment_box = Table(
                [[Paragraph(_safe(phase_comment if jp_name else ""), styles["comment_space"])]],
                colWidths=[cell_w - 0.2 * cm],
            )
            comment_box.setStyle(TableStyle([
                ("BOX",           (0, 0), (-1, -1), 0.5, MID_GRAY),
                ("TOPPADDING",    (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ("LEFTPADDING",   (0, 0), (-1, -1), 4),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            ]))
            cell_story.append(comment_box)

            cells.append(cell_story)

        # 2列ずつ Table に詰める
        row_pairs: list[list] = []
        for i in range(0, len(cells), 2):
            left  = cells[i]
            right = cells[i + 1] if i + 1 < len(cells) else [[Spacer(1, 1)]]
            row_pairs.append([left, right])

        for pair in row_pairs:
            grid = Table(
                [pair],
                colWidths=[cell_w, cell_w],
                hAlign="LEFT",
            )
            grid.setStyle(TableStyle([
                ("VALIGN",  (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING",  (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING",   (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
                ("BOX",          (0, 0), (-1, -1), 0.5, MID_GRAY),
                ("LINEBEFORE",   (1, 0), (1, -1), 0.5, MID_GRAY),
            ]))
            story.append(grid)
            story.append(Spacer(1, 0.4 * cm))

    # 免責文
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Paragraph(_safe(_DISCLAIMER), styles["disclaimer"]))

    return story


# ── エントリポイント ──────────────────────────────────────────────────────────

def generate_key_frame_sheet_for_job(job_dir: Path) -> Path:
    """キーフレームシート PDF を生成して返す。

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ

    Returns
    -------
    Path
        生成された PDF のパス: ``<job_dir>/report/key_frame_sheet.pdf``
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "key_frame_sheet.pdf"

    styles = _make_styles()
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN + 1.0 * cm,
        bottomMargin=MARGIN + 0.8 * cm,
        title="Key Frame Sheet — Javelin Video Analysis",
        author="Javelin Video Analysis",
    )
    doc.build(
        _build_story(job_dir, styles),
        onFirstPage=_draw_header_footer,
        onLaterPages=_draw_header_footer,
    )
    logger.info("[key_frame_sheet] PDF 生成完了: %s", out_path)
    return out_path
