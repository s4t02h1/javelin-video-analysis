"""
intro_pdf_generator.py — 納品ZIPの「00_最初に読んでください.pdf」生成

高校生アスリート・保護者・コーチが受け取って最初に読む案内PDFを生成する。
専門用語を避け、スマホで読みやすい文字サイズ・レイアウトにする。

Usage:
    from src.intro_pdf_generator import generate_intro_pdf_for_job
    pdf_path = generate_intro_pdf_for_job(Path("jobs/20260510_012144_0513"))
    # -> Path("jobs/20260510_012144_0513/report/00_最初に読んでください.pdf")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors

from src.pdf_styles import (
    BODY_BOT_MARGIN,
    BODY_TOP_MARGIN,
    BRAND_BLUE,
    BRAND_ORANGE,
    CARD_BG,
    CONTENT_W,
    LIGHT_GRAY,
    MARGIN_H,
    MID_GRAY,
    TEXT_DARK,
    TEXT_GRAY,
    WARN_BG,
    WARN_BORDER,
    get_font,
    get_styles,
    hr,
    make_header_footer,
    para_spacer,
    safe_text,
    section_spacer,
    warn_box,
)

logger = logging.getLogger(__name__)

_PDF_LABEL = "はじめにお読みください"
_draw_header_footer = make_header_footer(_PDF_LABEL)


# ── ユーティリティ ────────────────────────────────────────────────────────────

def _p(text: str, style) -> Paragraph:
    return Paragraph(safe_text(text), style)


def _load_job_meta(job_dir: Path) -> tuple[dict, dict]:
    """job.json と customer_info.json を読み込む。なければ空 dict。"""
    job, ci = {}, {}
    try:
        job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    try:
        ci = json.loads((job_dir / "customer_info.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    return job, ci


def _detect_plan(job_dir: Path, ci: dict) -> str:
    """プランを判定。free_preview / data_sheet / full_report"""
    plan = ci.get("plan", "")
    if plan in ("data_sheet", "full_report"):
        return plan
    # deliverables があれば推定
    deliv = job_dir / "deliverables"
    if (deliv / "full_report_package.zip").exists():
        return "full_report"
    if (deliv / "data_sheet_package.zip").exists():
        return "data_sheet"
    return "free_preview"


# ── セクション生成関数 ────────────────────────────────────────────────────────

def _build_cover(job: dict, ci: dict, plan: str, styles: dict) -> list:
    """表紙ブロック"""
    story = []

    # タイトル
    story.append(Spacer(1, 0.8 * cm))
    story.append(_p("やり投げ動作解析", styles["doc_title"]))
    story.append(_p("成果物パッケージ　はじめにお読みください", styles["doc_subtitle"]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(hr())
    story.append(Spacer(1, 0.4 * cm))

    # 選手情報
    name      = ci.get("customer_name") or "—"
    event_str = ci.get("event") or "やり投げ"
    job_id    = job.get("job_id", "—")
    now_str   = datetime.now().strftime("%Y年%m月%d日")
    plan_label = {
        "free_preview": "無料プレビュー",
        "data_sheet":   "有料データシート",
        "full_report":  "有料フルレポート",
    }.get(plan, "—")

    info_data = [
        ["選手氏名", safe_text(name)],
        ["種　　目", safe_text(event_str)],
        ["プラン",   safe_text(plan_label)],
        ["解析ID",  safe_text(job_id)],
        ["発行日",   now_str],
    ]
    fn = get_font()
    fn_b = get_font(bold=True)
    tbl = Table(
        info_data,
        colWidths=[4.0 * cm, CONTENT_W - 4.0 * cm],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (0, -1), CARD_BG),
        ("TEXTCOLOR",   (0, 0), (0, -1), BRAND_BLUE),
        ("FONTNAME",    (0, 0), (0, -1), fn_b),
        ("FONTNAME",    (1, 0), (1, -1), fn),
        ("FONTSIZE",    (0, 0), (-1, -1), 11),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("LINEBELOW",   (0, 0), (-1, -2), 0.3, MID_GRAY),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [LIGHT_GRAY, colors.white]),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.6 * cm))

    # 冒頭ご挨拶
    intro = (
        "このたびはやり投げ動作解析をご利用いただきありがとうございます。"
        "このPDFでは、お届けした成果物の内容と、最初に何を見ればよいかをご説明します。"
        "スマートフォンでご覧の場合は、まずこのPDFを最後まで読んでから各ファイルをご確認ください。"
    )
    story.append(_p(intro, styles["body"]))
    story.append(section_spacer())
    return story


def _build_file_guide(plan: str, styles: dict) -> list:
    """ファイル構成と見る順番"""
    story = []
    story.append(_p("📂 このパッケージに入っているもの", styles["section"]))
    story.append(hr())
    story.append(para_spacer())

    fn   = get_font()
    fn_b = get_font(bold=True)

    # プラン別ファイル定義
    _common = [
        ("00_最初に読んでください.pdf", "このファイルです。最初にお読みください。", "必読", BRAND_BLUE),
        ("01_解析動画フォルダ", "骨格・ヒートマップ・HUDなどの解析動画（MP4）が入っています。", "動画確認", BRAND_ORANGE),
        ("解析動画の見方.pdf", "各動画の意味と見方を説明した説明書です。動画を見る前に読んでください。", "必読", BRAND_BLUE),
    ]
    _data_sheet_extra = [
        ("選手向けサマリー.pdf", "手首の高さ・速度・体幹移動など主要指標をまとめた1〜2ページのシートです。", "まず読む", BRAND_ORANGE),
        ("代表フレームシート.pdf", "動作フェーズごとの重要な瞬間を切り出した画像シートです。", "フォーム確認", BRAND_ORANGE),
        ("グラフ解説.pdf", "各種グラフを解説付きで掲載したPDFです。数値の読み方も記載しています。", "詳細確認", BRAND_ORANGE),
        ("04_研究・開発用データフォルダ", "pose_landmarks.csv などの生データが入っています。通常は開かなくて構いません。", "研究・開発用", TEXT_GRAY),
    ]
    _full_extra = [
        ("コーチ向けレビューシート.pdf", "コーチが記入するフェーズ別チェックリストとフリーメモ欄です。", "指導者向け", BRAND_ORANGE),
        ("report.pdf", "システムが自動生成した詳細解析レポートです（A4縦向き）。", "詳細確認", BRAND_ORANGE),
    ]

    files = list(_common)
    if plan in ("data_sheet", "full_report"):
        files += _data_sheet_extra
    if plan == "full_report":
        files += _full_extra

    tbl_data = [["ファイル名", "内容", "用途"]]
    for fname, desc, usage, _ in files:
        tbl_data.append([safe_text(fname), safe_text(desc), safe_text(usage)])

    col_w = [4.5 * cm, CONTENT_W - 4.5 * cm - 2.5 * cm, 2.5 * cm]
    tbl = Table(tbl_data, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), fn_b),
        ("FONTSIZE",      (0, 0), (-1, 0), 9),
        ("FONTNAME",      (0, 1), (-1, -1), fn),
        ("FONTSIZE",      (0, 1), (-1, -1), 9),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(tbl)
    story.append(section_spacer())
    return story


def _build_viewing_order(plan: str, styles: dict) -> list:
    """最初に見る順番"""
    story = []
    story.append(_p("👀 最初に見る順番", styles["section"]))
    story.append(hr())
    story.append(para_spacer())

    if plan == "free_preview":
        steps = [
            ("Step 1", "この「はじめに読んでください」を最後まで読む"),
            ("Step 2", "「解析動画の見方.pdf」を読んで、各動画の意味を理解する"),
            ("Step 3", "「01_解析動画」フォルダを開き、骨格トレース動画から順に見る"),
            ("Step 4", "気になったシーンをスクリーンショットしてメモする"),
        ]
    elif plan == "data_sheet":
        steps = [
            ("Step 1", "この「はじめに読んでください」を最後まで読む"),
            ("Step 2", "「解析動画の見方.pdf」を読む"),
            ("Step 3", "「選手向けサマリー.pdf」を開き、主要指標を確認する"),
            ("Step 4", "「代表フレームシート.pdf」を見て、フォームの動きを振り返る"),
            ("Step 5", "「01_解析動画」フォルダを開き、動画で動作全体の流れを確認する"),
            ("Step 6", "「グラフ解説.pdf」で数値の変化を確認する（必要な場合）"),
            ("Step 7", "「04_研究・開発用データ」はコーチや研究者向けのため、通常は不要"),
        ]
    else:  # full_report
        steps = [
            ("Step 1", "この「はじめに読んでください」を最後まで読む"),
            ("Step 2", "「解析動画の見方.pdf」を読む"),
            ("Step 3", "「選手向けサマリー.pdf」で主要指標を確認する"),
            ("Step 4", "「代表フレームシート.pdf」でフォームの動きを振り返る"),
            ("Step 5", "「01_解析動画」フォルダで動画を確認する"),
            ("Step 6", "「グラフ解説.pdf」で数値の変化を確認する"),
            ("Step 7", "指導者の方は「コーチ向けレビューシート.pdf」にメモを記入する"),
            ("Step 8", "詳細は「report.pdf」を参照する（技術的な詳細レポート）"),
        ]

    fn   = get_font()
    fn_b = get_font(bold=True)
    tbl_data = [[safe_text(s), safe_text(t)] for s, t in steps]
    tbl = Table(tbl_data, colWidths=[2.2 * cm, CONTENT_W - 2.2 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), BRAND_ORANGE),
        ("TEXTCOLOR",     (0, 0), (0, -1), colors.white),
        ("FONTNAME",      (0, 0), (0, -1), fn_b),
        ("FONTNAME",      (1, 0), (1, -1), fn),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [None, LIGHT_GRAY]),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.3, MID_GRAY),
    ]))
    story.append(tbl)
    story.append(section_spacer())
    return story


def _build_video_guide(styles: dict) -> list:
    """解析動画の見方説明"""
    story = []
    story.append(_p("🎬 解析動画について", styles["section"]))
    story.append(hr())
    story.append(para_spacer())

    story.append(_p(
        "解析動画には、AIが動画から推定した身体の骨格ラインや軌跡を重ね合わせて表示しています。"
        "それぞれの動画は見る目的が異なります。",
        styles["body"]
    ))
    story.append(para_spacer())

    fn   = get_font()
    fn_b = get_font(bold=True)
    video_info = [
        ("骨格トレース＋軌跡",
         "身体の骨格ラインと右手首の軌跡を表示した動画です。投げ動作全体の流れや腕の通り道を確認するのに最適です。まずこの動画から見ることをおすすめします。"),
        ("ヒートマップ",
         "速度の変化を色（青→赤）で表現した動画です。赤い部分ほど速く動いていることを示します。どの部位が速く動いているかを視覚的に確認できます。"),
        ("HUD（情報付き）",
         "手首の速度・高さなどの数値情報をリアルタイムに重ね合わせた動画です。数値と動きの対応関係を確認したい場合に見てください。"),
        ("スティックマン",
         "骨格だけをシンプルな棒人間で表示した動画です。全体の動きのパターンを確認するのに向いています。"),
        ("速度・加速度ベクトル",
         "各関節の動く方向と速さを矢印で表示した動画です。どの部位がどの方向に動いているかを確認できます。"),
    ]

    for title, desc in video_info:
        row = KeepTogether([
            Table(
                [[safe_text(title), safe_text(desc)]],
                colWidths=[3.5 * cm, CONTENT_W - 3.5 * cm],
                style=TableStyle([
                    ("BACKGROUND",    (0, 0), (0, 0), CARD_BG),
                    ("FONTNAME",      (0, 0), (0, 0), fn_b),
                    ("FONTNAME",      (1, 0), (1, 0), fn),
                    ("FONTSIZE",      (0, 0), (-1, -1), 10),
                    ("TOPPADDING",    (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                    ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW",     (0, 0), (-1, -1), 0.3, MID_GRAY),
                ]),
            ),
        ])
        story.append(row)

    story.append(para_spacer())
    story.append(_p(
        "💡 スマホで見るときのコツ：動画は横向きにして、全身が映るように再生してください。"
        "骨格ラインが体から少しズレることがありますが、姿勢推定の誤差の範囲であれば問題ありません。",
        styles["note"]
    ))
    story.append(section_spacer())
    return story


def _build_frame_guide(styles: dict) -> list:
    """代表フレーム画像の見方"""
    story = []
    story.append(_p("🖼️ 代表フレーム画像について", styles["section"]))
    story.append(hr())
    story.append(para_spacer())

    story.append(_p(
        "代表フレーム画像は、投げ動作の重要な瞬間をピックアップした静止画です。"
        "「助走開始」「クロスステップ」「リリース付近」「手首速度のピーク」など、"
        "動作の節目ごとに切り出しています。",
        styles["body"]
    ))
    story.append(para_spacer())
    story.append(_p(
        "画像には骨格ラインが重ねて表示されていますが、"
        "撮影角度・照明・動きの速さによって、推定位置が実際の関節位置と完全に一致しないことがあります。"
        "細かい位置の誤差よりも、全体的な動きの流れとタイミングの確認にお使いください。",
        styles["body"]
    ))
    story.append(para_spacer())
    story.append(_p(
        "各フレームには「フレーム番号」「時刻」「手首の高さ（推定値）」などの情報を付記しています。"
        "「キーフレームシート.pdf」では複数フレームを並べて確認できます。",
        styles["body"]
    ))
    story.append(section_spacer())
    return story


def _build_graph_guide(styles: dict) -> list:
    """グラフの見方"""
    story = []
    story.append(_p("📈 グラフについて", styles["section"]))
    story.append(hr())
    story.append(para_spacer())

    story.append(_p(
        "グラフは動作中の身体の動きを数値化して表したものです。"
        "「グラフ解説.pdf」では各グラフの見方を詳しく説明していますが、ここでは簡単なポイントをご紹介します。",
        styles["body"]
    ))
    story.append(para_spacer())

    fn   = get_font()
    fn_b = get_font(bold=True)
    graph_points = [
        ("横軸（X軸）", "基本的に「フレーム番号」または「時間（秒）」を表します。左から右へ時間が進みます。"),
        ("縦軸（Y軸）", "各グラフで異なります。グラフタイトルや軸ラベルをご確認ください。"),
        ("ピーク値",   "数値が最大になる瞬間を「ピーク」と呼びます。ピークのタイミングが重要です。"),
        ("数値の意味", "数値が大きい・小さいだけで良し悪しを判断するのではなく、動きのパターンとセットで確認してください。"),
    ]
    tbl = Table(
        [[safe_text(k), safe_text(v)] for k, v in graph_points],
        colWidths=[3.2 * cm, CONTENT_W - 3.2 * cm],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), CARD_BG),
        ("FONTNAME",      (0, 0), (0, -1), fn_b),
        ("FONTNAME",      (1, 0), (1, -1), fn),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.3, MID_GRAY),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT_GRAY]),
    ]))
    story.append(tbl)
    story.append(para_spacer())
    story.append(_p(
        "⚠️ グラフの数値はあくまで参考値です。撮影条件（カメラ位置・フレームレート・画角）によって"
        "数値が変わります。比較するときは同じ条件で撮影した動画のグラフ同士で比較することをおすすめします。",
        styles["note"]
    ))
    story.append(section_spacer())
    return story


def _build_csv_guide(styles: dict) -> list:
    """CSVファイルの説明"""
    story = []
    story.append(_p("📄 CSVファイルについて（研究・開発用）", styles["section"]))
    story.append(hr())
    story.append(para_spacer())

    story.append(_p(
        "「pose_landmarks.csv」は、動画内のすべてのフレームにおける身体の各部位の推定座標を"
        "記録した生データファイルです。",
        styles["body"]
    ))
    story.append(para_spacer())
    story.append(_p(
        "このファイルは研究者・開発者・コーチが詳細な数値分析を行うためのものです。"
        "通常の確認には必要ありません。選手・保護者の方は「選手向けサマリー.pdf」や"
        "「グラフ解説.pdf」をご覧ください。",
        styles["body"]
    ))
    story.append(para_spacer())

    fn   = get_font()
    fn_b = get_font(bold=True)
    csv_cols = [
        ("frame", "フレーム番号（動画の何コマ目か）"),
        ("time_s", "時刻（秒）"),
        ("landmark_*_x/y/z", "各関節の推定座標（0〜1に正規化）"),
        ("visibility", "各関節が映像中に映っている確度（0〜1）"),
    ]
    tbl = Table(
        [[safe_text(k), safe_text(v)] for k, v in csv_cols],
        colWidths=[4.0 * cm, CONTENT_W - 4.0 * cm],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), LIGHT_GRAY),
        ("FONTNAME",      (0, 0), (0, -1), fn_b),
        ("FONTNAME",      (1, 0), (1, -1), fn),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.3, MID_GRAY),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT_GRAY]),
    ]))
    story.append(tbl)
    story.append(section_spacer())
    return story


def _build_disclaimer(styles: dict) -> list:
    """免責事項"""
    story = []
    story.append(_p("⚠️ ご注意事項・免責事項", styles["section"]))
    story.append(hr())
    story.append(para_spacer())

    disclaimer_items = [
        "本解析は、動画から取得した姿勢推定データをもとにした参考資料です。"
        "競技指導、医療判断、怪我の診断を代替するものではありません。"
        "最終的な練習内容や技術判断は、指導者・専門家と相談しながら行ってください。",

        "解析に使用するAI姿勢推定（MediaPipe）は、撮影角度・照明・動きの速さ・"
        "カメラ解像度の影響を受けます。数値や骨格ラインは参考値としてご理解ください。",

        "本解析データおよびPDFの第三者への再配布・商用利用はご遠慮ください。",

        "解析結果に基づく判断による損害について、当サービスは責任を負いかねます。",
    ]

    for item in disclaimer_items:
        story.append(_p(f"・ {item}", styles["body"]))
        story.append(Spacer(1, 0.2 * cm))

    story.append(section_spacer())
    return story


def _build_contact(job: dict, ci: dict, styles: dict) -> list:
    """問い合わせ情報"""
    story = []
    story.append(_p("📬 お問い合わせ・再解析のご依頼", styles["section"]))
    story.append(hr())
    story.append(para_spacer())

    story.append(_p(
        "解析内容についてご不明な点がある場合や、追加解析をご希望の場合は、"
        "以下の情報をあわせてお問い合わせください。",
        styles["body"]
    ))
    story.append(para_spacer())

    fn   = get_font()
    fn_b = get_font(bold=True)
    contact_info = [
        ("解析ID",  safe_text(job.get("job_id", "—"))),
        ("氏名",    safe_text(ci.get("customer_name", "—"))),
        ("お問い合わせ内容の例",
         "「○ページのグラフが見方がわからない」「別の動画も解析したい」など"),
    ]
    tbl = Table(
        contact_info,
        colWidths=[3.5 * cm, CONTENT_W - 3.5 * cm],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), CARD_BG),
        ("FONTNAME",      (0, 0), (0, -1), fn_b),
        ("FONTNAME",      (1, 0), (1, -1), fn),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.3, MID_GRAY),
    ]))
    story.append(tbl)
    story.append(section_spacer())
    return story


# ── メイン ────────────────────────────────────────────────────────────────────

def _build_story(job_dir: Path) -> list:
    styles = get_styles(prefix="intro_")
    job, ci = _load_job_meta(job_dir)
    plan = _detect_plan(job_dir, ci)

    story = []
    story += _build_cover(job, ci, plan, styles)
    story += _build_file_guide(plan, styles)
    story += _build_viewing_order(plan, styles)
    story += _build_video_guide(styles)
    story += _build_frame_guide(styles)
    story += _build_graph_guide(styles)
    if plan in ("data_sheet", "full_report"):
        story += _build_csv_guide(styles)
    story += _build_disclaimer(styles)
    story += _build_contact(job, ci, styles)
    return story


def generate_intro_pdf_for_job(job_dir: Path) -> Path:
    """
    「00_最初に読んでください.pdf」を生成する。

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ

    Returns
    -------
    Path
        jobs/<job_id>/report/00_最初に読んでください.pdf
    """
    job_dir = Path(job_dir)
    out_dir = job_dir / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "00_最初に読んでください.pdf"

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN_H,
        rightMargin=MARGIN_H,
        topMargin=BODY_TOP_MARGIN,
        bottomMargin=BODY_BOT_MARGIN,
        title="はじめにお読みください — やり投げ動作解析",
        author="やり投げ動作解析システム",
    )

    story = _build_story(job_dir)
    doc.build(
        story,
        onFirstPage=_draw_header_footer,
        onLaterPages=_draw_header_footer,
    )
    logger.info(f"[intro_pdf] 生成完了: {out_path}")
    return out_path
