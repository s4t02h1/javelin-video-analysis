"""
graph_pack_generator.py — グラフパック PDF 生成

report/graphs/ 配下のグラフ PNG を1冊の PDF にまとめ、各グラフに説明文を付ける。

Usage:
    from src.graph_pack_generator import generate_graph_pack_for_job
    pdf_path = generate_graph_pack_for_job(Path("jobs/20260510_012144_0513"))
    # -> Path("jobs/20260510_012144_0513/report/graph_pack.pdf")
"""

from __future__ import annotations

import logging
from datetime import datetime
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
            logger.info("[graph_pack] 日本語フォント登録: %s", font_path)
            return font_name, bold_name
        except Exception as exc:
            logger.warning("[graph_pack] フォント登録失敗 (%s): %s", font_path, exc)
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
MARGIN    = 2.0 * cm
CONTENT_W = PAGE_W - 2 * MARGIN
MAX_IMG_H = 10.0 * cm   # グラフ1枚あたりの最大高さ

BRAND_BLUE   = colors.HexColor("#1A4D8F")
BRAND_ORANGE = colors.HexColor("#E86A2E")
LIGHT_GRAY   = colors.HexColor("#F5F5F5")
MID_GRAY     = colors.HexColor("#CCCCCC")
TEXT_DARK    = colors.HexColor("#1A1A1A")
TEXT_GRAY    = colors.HexColor("#666666")

_DISCLAIMER = (
    "本資料は参考資料です。競技指導・医療判断・怪我の診断を代替するものではありません。"
    "グラフの数値は撮影条件・姿勢推定精度の影響を受ける参考推定値です。"
)

# グラフファイル名キーワード → (タイトル, 説明文)
_GRAPH_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "right_wrist_height": (
        "右手首の高さ変化 / Right Wrist Height",
        "投てき動作全体を通じた右手首の上下動を示しています。"
        "縦軸は正規化高さ（0=画面下端 / 1=画面上端）で、"
        "横軸は時間（秒）または フレーム番号です。"
        "手首が最も高い時刻がリリース付近の候補になります。",
    ),
    "right_arm_trajectory": (
        "右腕の軌道 / Right Arm Trajectory",
        "右肩・右肘・右手首の軌跡を2D平面上に重ねた図です。"
        "腕の通り道・ひじの引きつけ・手首のスナップを確認できます。",
    ),
    "torso_center_trajectory": (
        "体幹中心の移動 / Torso Center Trajectory",
        "肩中心と腰中心の移動軌跡を示しています。"
        "重心移動のパターンや左右のバランスを確認するのに役立ちます。",
    ),
    "right_wrist_speed": (
        "右手首速度の変化 / Right Wrist Speed",
        "各フレームにおける右手首の推定速度変化を示しています。"
        "速度ピーク付近がリリース動作の候補です。数値は参考推定値です。",
    ),
    "arm_chain_speed": (
        "肩・肘・手首の速度比較 / Arm Chain Speed",
        "右肩・右肘・右手首の速度を同一グラフに重ねて表示しています。"
        "肩→肘→手首の順に速度がピークに達する（運動連鎖）かを確認できます。",
    ),
}

# フォールバック: ファイル名ステムから説明文を生成
def _fallback_description(stem: str) -> tuple[str, str]:
    title = stem.replace("_", " ").title()
    return title, f"解析グラフ: {stem}"


# ── スタイル ──────────────────────────────────────────────────────────────────

def _make_styles() -> dict:
    def s(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    return {
        "title": s("GPTitle", fontName=_fn(True), fontSize=20,
                   textColor=BRAND_BLUE, spaceAfter=4, alignment=TA_CENTER),
        "subtitle": s("GPSubtitle", fontName=_fn(), fontSize=11,
                      textColor=BRAND_ORANGE, spaceAfter=2, alignment=TA_CENTER),
        "date_line": s("GPDate", fontName=_fn(), fontSize=8,
                       textColor=colors.grey, alignment=TA_CENTER),
        "graph_title": s("GPGraphTitle", fontName=_fn(True), fontSize=12,
                         textColor=BRAND_BLUE, spaceBefore=8, spaceAfter=3),
        "graph_desc": s("GPGraphDesc", fontName=_fn(), fontSize=9,
                        textColor=TEXT_DARK, leading=15, spaceAfter=4),
        "missing": s("GPMissing", fontName=_fn(), fontSize=9,
                     textColor=colors.grey, alignment=TA_CENTER),
        "caption": s("GPCaption", fontName=_fn(), fontSize=8,
                     textColor=colors.grey, alignment=TA_CENTER, spaceAfter=4),
        "disclaimer": s("GPDisclaimer", fontName=_fn(), fontSize=7,
                        textColor=TEXT_GRAY, leading=12, alignment=TA_LEFT),
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
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 0.65 * cm, "Graph Pack")
    canvas.setFillColor(MID_GRAY)
    canvas.rect(0, 0, PAGE_W, 0.8 * cm, fill=1, stroke=0)
    canvas.setFillColor(TEXT_GRAY)
    canvas.setFont("Helvetica", 6)
    canvas.drawString(MARGIN, 0.28 * cm,
                      "Not for medical use  |  Reference estimates only")
    canvas.drawRightString(PAGE_W - MARGIN, 0.28 * cm, f"Page {doc.page}")
    canvas.restoreState()


# ── 画像スケール ────────────────────────────────────────────────────────────

def _scale_image(img_path: Path, max_w: float, max_h: float) -> tuple[float, float]:
    try:
        ir = ImageReader(str(img_path))
        iw, ih = ir.getSize()
        scale = min(max_w / iw, max_h / ih, 1.0)
        return iw * scale, ih * scale
    except Exception:
        return max_w, max_w * 0.5


# ── PDF ストーリー構築 ────────────────────────────────────────────────────────

def _build_story(job_dir: Path, styles: dict) -> list:
    from pathlib import Path as _Path
    import json as _json

    story = []
    report_dir = job_dir / "report"
    graphs_dir = report_dir / "graphs"

    # Job / 顧客情報
    def _lj(p: Path) -> dict:
        try:
            return _json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    job = _lj(job_dir / "job.json")
    ci  = _lj(job_dir / "customer_info.json")
    job_id = job.get("job_id", "—")
    name   = ci.get("customer_name") or "—"
    gen_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # タイトルブロック
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(_safe("グラフパック"), styles["title"]))
    story.append(Paragraph("Graph Pack  —  Javelin Video Analysis", styles["subtitle"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(HRFlowable(width=CONTENT_W * 0.5, color=BRAND_ORANGE,
                             hAlign="CENTER", thickness=2))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph(_safe(f"Job ID: {job_id}  |  {name}  |  出力日: {gen_at}"),
                           styles["date_line"]))
    story.append(Spacer(1, 0.4 * cm))

    # グラフ収集
    if graphs_dir.exists():
        graph_files = sorted(
            list(graphs_dir.glob("*.png")) + list(graphs_dir.glob("*.jpg"))
        )
    else:
        graph_files = []

    if not graph_files:
        story.append(Paragraph(_safe("グラフ画像が見つかりませんでした。未生成の場合は解析を再実行してください。"),
                               styles["missing"]))
    else:
        for gp in graph_files:
            stem = gp.stem.lower()
            # 説明文検索
            title, desc = _fallback_description(gp.stem)
            for key, (t, d) in _GRAPH_DESCRIPTIONS.items():
                if key in stem:
                    title, desc = t, d
                    break

            story.append(Paragraph(_safe(title), styles["graph_title"]))
            story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY, thickness=0.5))
            story.append(Spacer(1, 0.15 * cm))
            story.append(Paragraph(_safe(desc), styles["graph_desc"]))

            if gp.exists() and gp.stat().st_size > 0:
                try:
                    iw, ih = _scale_image(gp, CONTENT_W, MAX_IMG_H)
                    img = Image(str(gp), width=iw, height=ih, hAlign="CENTER")
                    story.append(img)
                    story.append(Paragraph(_safe(gp.name), styles["caption"]))
                except Exception as e:
                    story.append(Paragraph(
                        _safe(f"(画像読み込みエラー: {gp.name})"), styles["missing"]
                    ))
            else:
                story.append(Paragraph(_safe(f"未生成 / Not generated: {gp.name}"),
                                       styles["missing"]))

            story.append(Spacer(1, 0.5 * cm))

    # 免責文
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Paragraph(_safe(_DISCLAIMER), styles["disclaimer"]))

    return story


# ── エントリポイント ──────────────────────────────────────────────────────────

def generate_graph_pack_for_job(job_dir: Path) -> Path:
    """グラフパック PDF を生成して返す。

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ

    Returns
    -------
    Path
        生成された PDF のパス: ``<job_dir>/report/graph_pack.pdf``
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "graph_pack.pdf"

    styles = _make_styles()
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN + 1.0 * cm,
        bottomMargin=MARGIN + 0.8 * cm,
        title="Graph Pack — Javelin Video Analysis",
        author="Javelin Video Analysis",
    )
    doc.build(
        _build_story(job_dir, styles),
        onFirstPage=_draw_header_footer,
        onLaterPages=_draw_header_footer,
    )
    logger.info("[graph_pack] PDF 生成完了: %s", out_path)
    return out_path
