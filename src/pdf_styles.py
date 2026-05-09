"""
pdf_styles.py — PDF 生成共通スタイル・フォント管理

全 PDF 生成モジュールで共有する:
 - 日本語フォント登録
 - カラーパレット・余白定数
 - ParagraphStyle セット
 - ヘッダー/フッター描画関数
 - 画像スケールユーティリティ
 - KV テーブル・警告ボックス生成

Usage:
    from src.pdf_styles import get_font, get_styles, draw_header_footer, BRAND_BLUE, ...
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# 1. 日本語フォント登録
# ══════════════════════════════════════════════════════════════════════════════

# フォント候補: (登録名, 通常ファイルパス, subfontIndex, ボールドファイルパス, subfontIndex)
_FONT_CANDIDATES: list[tuple[str, str, int, Optional[str], int]] = [
    # Windows — Meiryo (UI用途のため最優先)
    ("JaFont", "C:/Windows/Fonts/meiryo.ttc",  0,
               "C:/Windows/Fonts/meiryob.ttc", 0),
    # Windows — MS Gothic (fallback)
    ("JaFont", "C:/Windows/Fonts/msgothic.ttc", 0,
               "C:/Windows/Fonts/msgothic.ttc", 1),
    # Windows — Yu Gothic
    ("JaFont", "C:/Windows/Fonts/YuGothM.ttc",  0,
               "C:/Windows/Fonts/YuGothB.ttc",  0),
    # macOS — Hiragino
    ("JaFont", "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", 0,
               "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", 0),
    # Linux — Noto Sans CJK
    ("JaFont", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0,
               "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",   0),
    ("JaFont", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 0,
               "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",   0),
]

_FONT_REGISTERED = False
_JP_FONT_NORMAL = ""
_JP_FONT_BOLD   = ""


def _register_fonts() -> None:
    global _FONT_REGISTERED, _JP_FONT_NORMAL, _JP_FONT_BOLD

    if _FONT_REGISTERED:
        return

    for (fname, norm_path, norm_idx, bold_path, bold_idx) in _FONT_CANDIDATES:
        if not Path(norm_path).exists():
            continue
        try:
            # 既登録チェック
            try:
                pdfmetrics.getFont("JaFont")
                _JP_FONT_NORMAL = "JaFont"
                try:
                    pdfmetrics.getFont("JaFontBold")
                    _JP_FONT_BOLD = "JaFontBold"
                except KeyError:
                    _JP_FONT_BOLD = "JaFont"
                _FONT_REGISTERED = True
                return
            except KeyError:
                pass

            pdfmetrics.registerFont(TTFont("JaFont", norm_path, subfontIndex=norm_idx))
            _JP_FONT_NORMAL = "JaFont"

            # Bold
            if bold_path and Path(bold_path).exists():
                try:
                    pdfmetrics.registerFont(TTFont("JaFontBold", bold_path,
                                                   subfontIndex=bold_idx))
                    _JP_FONT_BOLD = "JaFontBold"
                except Exception:
                    _JP_FONT_BOLD = "JaFont"
            else:
                _JP_FONT_BOLD = "JaFont"

            logger.info("[pdf_styles] 日本語フォント登録完了: %s", norm_path)
            _FONT_REGISTERED = True
            return
        except Exception as exc:
            logger.warning("[pdf_styles] フォント登録失敗 (%s): %s", norm_path, exc)

    logger.warning("[pdf_styles] 日本語フォントが見つかりませんでした。豆腐文字が出る可能性があります。")
    _FONT_REGISTERED = True  # 再試行しない


def get_font(bold: bool = False) -> str:
    """日本語フォント名を返す。未登録なら Helvetica 系を返す。"""
    _register_fonts()
    if bold:
        return _JP_FONT_BOLD if _JP_FONT_BOLD else "Helvetica-Bold"
    return _JP_FONT_NORMAL if _JP_FONT_NORMAL else "Helvetica"


def safe_text(text: str) -> str:
    """日本語フォントが使えない場合にマルチバイト文字を '?' に変換する。"""
    _register_fonts()
    if _JP_FONT_NORMAL:
        return text
    return "".join(c if c.encode("latin-1", errors="ignore") else "?" for c in text)


# ══════════════════════════════════════════════════════════════════════════════
# 2. カラーパレット / 余白定数
# ══════════════════════════════════════════════════════════════════════════════

# ブランドカラー
BRAND_BLUE   = colors.HexColor("#1A4D8F")
BRAND_ORANGE = colors.HexColor("#E86A2E")

# 背景・枠
LIGHT_GRAY   = colors.HexColor("#F5F5F5")
CARD_BG      = colors.HexColor("#F0F4FA")   # 薄い青系カード背景
MID_GRAY     = colors.HexColor("#CCCCCC")
WARN_BG      = colors.HexColor("#FFF8E1")   # 警告ボックス背景
WARN_BORDER  = colors.HexColor("#FFC107")   # 警告ボックス枠
WRITE_LINE   = colors.HexColor("#E0E0E0")   # 記入欄罫線

# テキスト
TEXT_DARK    = colors.HexColor("#222222")
TEXT_GRAY    = colors.HexColor("#666666")
TEXT_LIGHT   = colors.HexColor("#999999")
FOOTER_TEXT  = colors.HexColor("#777777")

# ページ設定
PAGE_W, PAGE_H = A4
MARGIN_H = 1.8 * cm    # 左右余白
MARGIN_V = 1.8 * cm    # 上下余白（本文部分）
HEADER_H = 1.1 * cm    # ヘッダー高さ
FOOTER_H = 0.9 * cm    # フッター高さ
CONTENT_W = PAGE_W - 2 * MARGIN_H

# 本文開始 y座標（ヘッダー下端）
BODY_TOP_MARGIN = MARGIN_V + HEADER_H
BODY_BOT_MARGIN = MARGIN_V + FOOTER_H

# ══════════════════════════════════════════════════════════════════════════════
# 3. 共通スタイル
# ══════════════════════════════════════════════════════════════════════════════

def get_styles(prefix: str = "") -> dict[str, ParagraphStyle]:
    """
    共通 ParagraphStyle セットを返す。

    prefix: スタイル名の衝突回避プレフィックス（モジュール略称推奨）
    """
    _register_fonts()
    fn  = get_font(False)
    fnb = get_font(True)

    def s(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(f"{prefix}{name}", **kw)

    return {
        # ── タイトル系 ─────────────────────────────────────────────────────
        "doc_title": s("DocTitle",
            fontName=fnb, fontSize=22, textColor=BRAND_BLUE,
            spaceAfter=4, alignment=TA_CENTER, leading=28),
        "doc_subtitle": s("DocSubtitle",
            fontName=fn, fontSize=11, textColor=BRAND_ORANGE,
            spaceAfter=2, alignment=TA_CENTER, leading=16),
        "doc_date": s("DocDate",
            fontName=fn, fontSize=8, textColor=TEXT_GRAY,
            alignment=TA_CENTER, leading=12, spaceAfter=4),

        # ── セクション見出し ────────────────────────────────────────────────
        "section": s("Section",
            fontName=fnb, fontSize=14, textColor=BRAND_BLUE,
            spaceBefore=10, spaceAfter=4, leading=20),
        "subsection": s("Subsection",
            fontName=fnb, fontSize=11, textColor=BRAND_BLUE,
            spaceBefore=6, spaceAfter=3, leading=16),
        "label": s("Label",
            fontName=fnb, fontSize=9.5, textColor=BRAND_BLUE,
            spaceBefore=4, spaceAfter=2, leading=14),

        # ── 本文 ───────────────────────────────────────────────────────────
        "body": s("Body",
            fontName=fn, fontSize=10, textColor=TEXT_DARK,
            leading=17, spaceAfter=4),
        "body_sm": s("BodySm",
            fontName=fn, fontSize=8.5, textColor=TEXT_GRAY,
            leading=13, spaceAfter=2),
        "body_bold": s("BodyBold",
            fontName=fnb, fontSize=10, textColor=TEXT_DARK,
            leading=17, spaceAfter=4),

        # ── キャプション・注記 ────────────────────────────────────────────
        "caption": s("Caption",
            fontName=fn, fontSize=8, textColor=TEXT_GRAY,
            alignment=TA_CENTER, leading=11, spaceAfter=3),
        "caption_left": s("CaptionLeft",
            fontName=fn, fontSize=8, textColor=TEXT_GRAY,
            alignment=TA_LEFT, leading=11, spaceAfter=3),
        "note": s("Note",
            fontName=fn, fontSize=8, textColor=TEXT_GRAY,
            leading=12, spaceAfter=2),
        "disclaimer": s("Disclaimer",
            fontName=fn, fontSize=7.5, textColor=TEXT_GRAY,
            leading=12, alignment=TA_LEFT, spaceAfter=2),

        # ── KV テーブル用 ─────────────────────────────────────────────────
        "kv_key": s("KvKey",
            fontName=fnb, fontSize=9, textColor=BRAND_BLUE,
            leading=13),
        "kv_val": s("KvVal",
            fontName=fn, fontSize=9, textColor=TEXT_DARK,
            leading=13),
        "kv_val_sm": s("KvValSm",
            fontName=fn, fontSize=8.5, textColor=TEXT_DARK,
            leading=13),

        # ── カード用 ─────────────────────────────────────────────────────
        "card_key": s("CardKey",
            fontName=fn, fontSize=8, textColor=TEXT_GRAY,
            alignment=TA_CENTER, leading=11),
        "card_val": s("CardVal",
            fontName=fnb, fontSize=13, textColor=BRAND_BLUE,
            alignment=TA_CENTER, leading=17),
        "card_unit": s("CardUnit",
            fontName=fn, fontSize=8, textColor=TEXT_GRAY,
            alignment=TA_CENTER, leading=11),

        # ── グラフ解説 ────────────────────────────────────────────────────
        "graph_title": s("GraphTitle",
            fontName=fnb, fontSize=13, textColor=BRAND_BLUE,
            spaceBefore=8, spaceAfter=3, leading=18),
        "graph_desc": s("GraphDesc",
            fontName=fn, fontSize=9.5, textColor=TEXT_DARK,
            leading=16, spaceAfter=6),
        "graph_bullet": s("GraphBullet",
            fontName=fn, fontSize=9, textColor=TEXT_DARK,
            leading=14, spaceAfter=2, leftIndent=12),

        # ── フレームシート ────────────────────────────────────────────────
        "phase_title": s("PhaseTitle",
            fontName=fnb, fontSize=12, textColor=BRAND_BLUE,
            spaceBefore=4, spaceAfter=2, leading=16),
        "phase_sub": s("PhaseSub",
            fontName=fn, fontSize=8.5, textColor=BRAND_ORANGE,
            spaceAfter=2, leading=12),
        "meta_key": s("MetaKey",
            fontName=fnb, fontSize=8, textColor=TEXT_GRAY, leading=12),
        "meta_val": s("MetaVal",
            fontName=fn, fontSize=8, textColor=TEXT_DARK, leading=12),

        # ── コーチレビュー ────────────────────────────────────────────────
        "write_label": s("WriteLabel",
            fontName=fnb, fontSize=10, textColor=TEXT_DARK,
            spaceBefore=3, spaceAfter=1, leading=15),
        "checkbox_item": s("CheckboxItem",
            fontName=fn, fontSize=9.5, textColor=TEXT_DARK,
            leading=16, leftIndent=8),

        # ── 警告ボックス ─────────────────────────────────────────────────
        "warn": s("Warn",
            fontName=fnb, fontSize=9.5, textColor=colors.HexColor("#7B4800"),
            leading=15),
        "warn_body": s("WarnBody",
            fontName=fn, fontSize=9, textColor=colors.HexColor("#5C3000"),
            leading=14),

        # ── ヘッダー(Platypus外描画なので参考) ───────────────────────────
        "missing": s("Missing",
            fontName=fn, fontSize=9, textColor=TEXT_GRAY,
            alignment=TA_CENTER, leading=13),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. ヘッダー / フッター描画
# ══════════════════════════════════════════════════════════════════════════════

_FOOTER_TEXT = "参考資料｜医療診断・競技指導を代替するものではありません"


def make_header_footer(pdf_label: str):
    """
    ヘッダー/フッター描画関数を返す。

    Parameters
    ----------
    pdf_label : str
        ヘッダー右側に表示するPDF種別名（日本語）
        例: "解析レポート", "アスリート向けデータシート", "キーフレームシート"
    """
    _register_fonts()
    fn  = get_font(False)
    fnb = get_font(True)

    def _draw(canvas, doc):
        canvas.saveState()

        # ── ヘッダー ──────────────────────────────────────────────────────
        canvas.setFillColor(BRAND_BLUE)
        canvas.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, fill=1, stroke=0)

        canvas.setFillColor(colors.white)
        # 左: システム名
        canvas.setFont(fnb, 8)
        canvas.drawString(MARGIN_H, PAGE_H - HEADER_H * 0.62,
                          "やり投げ動作解析")
        # 右: PDF種別
        canvas.setFont(fn, 8)
        canvas.drawRightString(PAGE_W - MARGIN_H,
                               PAGE_H - HEADER_H * 0.62,
                               safe_text(pdf_label))

        # ── フッター ──────────────────────────────────────────────────────
        canvas.setFillColor(LIGHT_GRAY)
        canvas.rect(0, 0, PAGE_W, FOOTER_H, fill=1, stroke=0)

        canvas.setFillColor(FOOTER_TEXT)
        canvas.setFont(fn, 6.5)
        canvas.drawString(MARGIN_H, FOOTER_H * 0.38,
                          safe_text(_FOOTER_TEXT))
        canvas.drawRightString(PAGE_W - MARGIN_H, FOOTER_H * 0.38,
                               f"{doc.page}")

        canvas.restoreState()

    return _draw


# ══════════════════════════════════════════════════════════════════════════════
# 5. Platypus ユーティリティ
# ══════════════════════════════════════════════════════════════════════════════

def hr(width_ratio: float = 1.0, color=MID_GRAY, thickness: float = 0.5) -> HRFlowable:
    """水平線を返す。"""
    return HRFlowable(width=CONTENT_W * width_ratio, color=color,
                      thickness=thickness, hAlign="LEFT")


def section_spacer() -> Spacer:
    return Spacer(1, 0.5 * cm)


def para_spacer() -> Spacer:
    return Spacer(1, 0.3 * cm)


def title_block(title_ja: str, subtitle_en: str, info_line: str,
                styles: dict) -> list:
    """表紙タイトルブロックを生成する。"""
    return [
        Spacer(1, 0.4 * cm),
        Paragraph(safe_text(title_ja), styles["doc_title"]),
        Paragraph(subtitle_en, styles["doc_subtitle"]),
        Spacer(1, 0.15 * cm),
        HRFlowable(width=CONTENT_W * 0.5, color=BRAND_ORANGE,
                   hAlign="CENTER", thickness=2),
        Spacer(1, 0.15 * cm),
        Paragraph(safe_text(info_line), styles["doc_date"]),
        Spacer(1, 0.3 * cm),
    ]


def kv_table(pairs: list[tuple[str, str]], styles: dict,
             col_ratio: float = 0.42) -> Table:
    """キー・バリュー形式の小テーブルを生成する。"""
    key_w = CONTENT_W * col_ratio
    val_w = CONTENT_W * (1 - col_ratio)
    data = [
        [Paragraph(safe_text(k), styles["kv_key"]),
         Paragraph(safe_text(v), styles["kv_val"])]
        for k, v in pairs
    ]
    tbl = Table(data, colWidths=[key_w, val_w], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_GRAY),
        ("GRID",          (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def warn_box(message: str, styles: dict) -> Table:
    """警告ボックス（黄色系）を生成する。"""
    data = [[Paragraph(safe_text("⚠️  " + message), styles["warn"])]]
    tbl = Table(data, colWidths=[CONTENT_W], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), WARN_BG),
        ("BOX",           (0, 0), (-1, -1), 1.0, WARN_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    return tbl


def metric_cards(metrics: list[tuple[str, str, str]],
                 styles: dict, cols: int = 3) -> Table:
    """
    指標カードを cols 列で並べたテーブルを生成する。

    Parameters
    ----------
    metrics : list of (label, value, unit)
    styles  : get_styles() の結果
    cols    : 列数 (2 or 3)
    """
    card_w = (CONTENT_W - (cols - 1) * 0.3 * cm) / cols
    cards = []
    for label, value, unit in metrics:
        cell = Table(
            [[Paragraph(safe_text(label), styles["card_key"])],
             [Paragraph(safe_text(value), styles["card_val"])],
             [Paragraph(safe_text(unit),  styles["card_unit"])]],
            colWidths=[card_w],
        )
        cell.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), CARD_BG),
            ("BOX",           (0, 0), (-1, -1), 0.5, MID_GRAY),
            ("TOPPADDING",    (0, 0), (-1, 0),  6),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
            ("TOPPADDING",    (0, 1), (-1, 1),  2),
            ("BOTTOMPADDING", (0, 1), (-1, 1),  2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ]))
        cards.append(cell)

    # cols 列ずつ行に分割
    rows: list[list] = []
    gap = Spacer(0.3 * cm, 1)
    for i in range(0, len(cards), cols):
        row_cells = cards[i : i + cols]
        # 足りない列を空白で埋める
        while len(row_cells) < cols:
            empty = Table([[""]], colWidths=[card_w])
            empty.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.white)]))
            row_cells.append(empty)
        rows.append(row_cells)

    col_widths = [card_w] * cols
    tbl = Table(rows, colWidths=col_widths, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def write_box(label: str, line_count: int, styles: dict,
              line_h: float = 0.65 * cm) -> list:
    """
    ラベル付き手書き記入欄を生成する。

    Returns
    -------
    list : [Label Paragraph, Table (記入欄)]
    """
    items: list = [Paragraph(safe_text(label), styles["write_label"])]
    # 1行ずつ薄い罫線を生成
    line_data = [[""]] * line_count
    tbl = Table(
        line_data,
        colWidths=[CONTENT_W],
        rowHeights=[line_h] * line_count,
    )
    tbl.setStyle(TableStyle([
        ("BOX",           (0, 0),  (-1, -1), 0.5, MID_GRAY),
        ("LINEBELOW",     (0, 0),  (-1, -2), 0.4, WRITE_LINE),
        ("TOPPADDING",    (0, 0),  (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0),  (-1, -1), 0),
        ("LEFTPADDING",   (0, 0),  (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0),  (-1, -1), 4),
    ]))
    items.append(tbl)
    return items


def scale_image(img_path: Path, max_w: float, max_h: float) -> tuple[float, float]:
    """アスペクト比を維持して画像サイズを計算する。"""
    try:
        ir = ImageReader(str(img_path))
        iw, ih = ir.getSize()
        scale = min(max_w / iw, max_h / ih, 1.0)
        return iw * scale, ih * scale
    except Exception:
        return max_w, max_w * 0.56


def disclaimer_block(styles: dict,
                     text: str = "本資料は参考資料です。競技指導・医療判断・怪我の診断を"
                                 "代替するものではありません。速度等の数値は撮影条件・姿勢"
                                 "推定精度の影響を受ける参考推定値です。") -> list:
    """免責文ブロックを返す。"""
    return [
        HRFlowable(width=CONTENT_W, color=MID_GRAY, thickness=0.4),
        Spacer(1, 0.15 * cm),
        Paragraph(safe_text(text), styles["disclaimer"]),
    ]


# ── グラフ解説文 ────────────────────────────────────────────────────────────────

_GRAPH_BULLETS: dict[str, list[str]] = {
    "right_arm_trajectory": [
        "腕の軌道が大きく乱れていないか",
        "手首の通り道がスムーズか",
        "肩・肘・手首の動きが極端に離れていないか",
    ],
    "right_wrist_height": [
        "手首がリリース付近に向けて大きく沈み込んでいないか",
        "急激な上下動がないか",
        "速度ピークやリリース候補の時刻と照らし合わせられるか",
    ],
    "torso_center_trajectory": [
        "肩と腰の移動が大きくズレていないか",
        "前方への移動がスムーズか",
        "大きな横ブレがないか",
    ],
    "right_wrist_speed": [
        "速度ピーク付近がリリース時刻の候補",
        "助走〜加速の速度が右肩上がりになっているか",
        "ピーク後に速度が急落しているか",
    ],
    "arm_chain_speed": [
        "肩→肘→手首の順に速度ピークが来ているか（運動連鎖）",
        "手首の最大速度が肩より大きくなっているか",
        "ピークのタイミングが揃いすぎていないか",
    ],
}

_GRAPH_DESC: dict[str, tuple[str, str]] = {
    "right_arm_trajectory": (
        "右腕の軌跡",
        "右肩・右肘・右手首の位置変化を2D平面上に重ねた図です。"
        "投げ腕がどのような通り道を通っているか、肘の引きつけや手首の動きを確認できます。",
    ),
    "right_wrist_height": (
        "右手首の高さ変化",
        "時間ごとの右手首の高さを示すグラフです。"
        "縦軸は正規化高さ（0 = 画面下端 / 1 = 画面上端）、横軸は時間です。"
        "リリースに向けて手首がどのように変化しているかを見る参考資料です。",
    ),
    "torso_center_trajectory": (
        "体幹中心の移動",
        "肩中心と腰中心の移動を示すグラフです。"
        "助走から投げに入る局面で、体幹がどの方向へ移動しているかを確認できます。",
    ),
    "right_wrist_speed": (
        "右手首の速度変化",
        "各フレームにおける右手首の推定速度変化を示しています。"
        "速度が最大になる時刻がリリース動作の候補です。",
    ),
    "arm_chain_speed": (
        "運動連鎖の速度変化",
        "右肩・右肘・右手首の速度を同一グラフに重ねて表示しています。"
        "肩 → 肘 → 手首の順に速度のピークが来ているか（運動連鎖）を確認できます。",
    ),
}

_GRAPH_COMMON_NOTE = (
    "※ 本グラフは2D動画からの姿勢推定データをもとにした参考可視化です。"
    "撮影角度・距離・照明・服装・ポーズ検出精度の影響を受けます。"
)


def get_graph_info(stem: str) -> tuple[str, str, list[str]]:
    """
    グラフファイルのステムからタイトル・説明文・チェックポイントを返す。

    Returns
    -------
    (title_ja, description, bullet_points)
    """
    stem_lower = stem.lower()
    for key, (title, desc) in _GRAPH_DESC.items():
        if key in stem_lower:
            bullets = _GRAPH_BULLETS.get(key, [])
            return title, desc, bullets
    # fallback
    title = stem.replace("_", " ").title()
    return title, "解析グラフです。参考可視化として活用してください。", []


def graph_section(img_path: Path, styles: dict,
                  max_img_w: Optional[float] = None,
                  max_img_h: float = 11.0 * cm) -> list:
    """
    グラフ1枚分のセクション（タイトル + 説明 + 画像 + チェックポイント + 注記）を生成する。

    Parameters
    ----------
    img_path   : グラフ画像パス
    styles     : get_styles() の返値
    max_img_w  : 最大幅（None なら CONTENT_W）
    max_img_h  : 最大高さ
    """
    from reportlab.platypus import KeepTogether
    from reportlab.platypus import Image as RLImage

    if max_img_w is None:
        max_img_w = CONTENT_W

    title, desc, bullets = get_graph_info(img_path.stem)

    block: list = []
    block.append(Paragraph(safe_text(title), styles["graph_title"]))
    block.append(HRFlowable(width=CONTENT_W, color=MID_GRAY, thickness=0.4))
    block.append(Spacer(1, 0.1 * cm))
    block.append(Paragraph(safe_text(desc), styles["graph_desc"]))

    if img_path.exists() and img_path.stat().st_size > 0:
        try:
            iw, ih = scale_image(img_path, max_img_w, max_img_h)
            img = RLImage(str(img_path), width=iw, height=ih, hAlign="CENTER")
            block.append(img)
            block.append(Paragraph(safe_text(img_path.name), styles["caption"]))
        except Exception as exc:
            logger.warning("[pdf_styles] 画像読み込みエラー (%s): %s", img_path, exc)
            block.append(Paragraph(safe_text(f"⚠ 画像読み込みエラー: {img_path.name}"),
                                   styles["missing"]))
    else:
        block.append(Paragraph(safe_text(f"⚠ 画像未生成: {img_path.name}"),
                               styles["missing"]))

    if bullets:
        block.append(Spacer(1, 0.15 * cm))
        block.append(Paragraph(safe_text("【チェックポイント】"), styles["caption_left"]))
        for b in bullets:
            block.append(Paragraph(safe_text(f"・{b}"), styles["graph_bullet"]))

    block.append(Spacer(1, 0.15 * cm))
    block.append(Paragraph(safe_text(_GRAPH_COMMON_NOTE), styles["note"]))

    return block
