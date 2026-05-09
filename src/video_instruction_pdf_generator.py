"""
video_instruction_pdf_generator.py — 解析動画 説明書 PDF 生成

各解析動画の見方を説明した instruction PDF を生成する。

Usage:
    from src.video_instruction_pdf_generator import generate_video_instruction_pdf_for_job
    pdf_path = generate_video_instruction_pdf_for_job(Path("jobs/20260510_012144_0513"))
    # -> Path("jobs/20260510_012144_0513/report/video_instruction.pdf")
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


# ── 定数 ───────────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN = MARGIN_H
CONTENT_W = PAGE_W - 2 * MARGIN

BRAND_BLUE   = colors.HexColor("#1A4D8F")
BRAND_ORANGE = colors.HexColor("#E86A2E")
LIGHT_GRAY   = colors.HexColor("#F5F5F5")
MID_GRAY     = colors.HexColor("#CCCCCC")
TEXT_DARK    = colors.HexColor("#1A1A1A")
TEXT_GRAY    = colors.HexColor("#666666")

# ── 動画メタ情報 ───────────────────────────────────────────────────────────────

# 解析動画の定義: (ファイル名ステム, 日本語タイトル, 説明文)
_VIDEO_DEFS: list[tuple[str, str, str]] = [
    (
        "analysis_original_skeleton",
        "骨格トレース＋手首軌跡",
        (
            "カメラ映像にAIが推定した身体の骨格ラインを重ね合わせた動画です。"
            "右手首の軌跡も表示されるため、投てき動作全体の流れ、腕の通り道、"
            "リリースまでの動きを確認するのに適しています。"
        ),
    ),
    (
        "analysis_original_vectors",
        "速度・加速度ベクトル",
        (
            "各関節に矢印を重ね、動きの方向と大きさを可視化した動画です。"
            "緑の矢印は速度、赤の矢印は加速度を示します。"
            "肩・肘・手首・腰などがどの方向へ動いているかを確認するのに役立ちます。"
        ),
    ),
    (
        "analysis_original_stickman",
        "スティックマン",
        (
            "背景を黒にし、身体を線と点でシンプルに表現した動画です。"
            "余計な背景情報を減らすことで、フォームの輪郭、姿勢、タイミングを"
            "確認しやすくなります。コーチや選手との振り返り資料として使いやすい形式です。"
        ),
    ),
    (
        "analysis_original_hud",
        "HUD / 数値ダッシュボード",
        (
            "動画上に速度や最大速度などの数値情報を重ねて表示するモードです。"
            "右手首の速度変化や、リリース付近の動きを直感的に確認できます。"
            "数値は2D動画からの参考推定値です。"
        ),
    ),
    (
        "analysis_original_analysis",
        "コーチング解析 / 統合オーバーレイ",
        (
            "複数の解析情報を1本にまとめた動画です。"
            "フェーズ表示、関節角度、リリース情報、軌道予測、運動連鎖などをまとめて確認できます。"
            "最も情報量が多いため、詳細な振り返りや比較に向いています。"
        ),
    ),
]

_DISCLAIMER = (
    "【免責事項】本解析は、動画から身体の動きや軌跡を可視化し、練習の振り返りを補助するための"
    "参考資料です。競技指導、医療判断、怪我の診断を代替するものではありません。"
    "速度・角度・軌跡などの数値は、撮影条件や姿勢推定精度の影響を受ける参考推定値です。"
)

# ── スタイル ──────────────────────────────────────────────────────────────────


def _make_styles() -> dict:
    def s(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    return {
        "title": s(
            "VITitle",
            fontName=_fn(bold=True),
            fontSize=22,
            textColor=BRAND_BLUE,
            spaceAfter=4,
            alignment=TA_CENTER,
        ),
        "subtitle": s(
            "VISubtitle",
            fontName=_fn(),
            fontSize=12,
            textColor=BRAND_ORANGE,
            spaceAfter=2,
            alignment=TA_CENTER,
        ),
        "date_line": s(
            "VIDateLine",
            fontName=_fn(),
            fontSize=9,
            textColor=colors.grey,
            alignment=TA_CENTER,
        ),
        "section": s(
            "VISection",
            fontName=_fn(bold=True),
            fontSize=13,
            textColor=BRAND_BLUE,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "kv_key": s(
            "VIKVKey",
            fontName=_fn(bold=True),
            fontSize=10,
            textColor=BRAND_BLUE,
        ),
        "kv_val": s(
            "VIKVVal",
            fontName=_fn(),
            fontSize=10,
            textColor=TEXT_DARK,
        ),
        "video_title": s(
            "VIVideoTitle",
            fontName=_fn(bold=True),
            fontSize=11,
            textColor=TEXT_DARK,
            spaceBefore=4,
            spaceAfter=2,
        ),
        "video_filename": s(
            "VIVideoFilename",
            fontName=_fn(),
            fontSize=9,
            textColor=TEXT_GRAY,
            spaceAfter=2,
        ),
        "video_desc": s(
            "VIVideoDesc",
            fontName=_fn(),
            fontSize=10,
            textColor=TEXT_DARK,
            leading=17,
            spaceAfter=4,
        ),
        "not_generated": s(
            "VINotGenerated",
            fontName=_fn(),
            fontSize=9,
            textColor=colors.grey,
            spaceAfter=4,
        ),
        "disclaimer": s(
            "VIDisclaimer",
            fontName=_fn(),
            fontSize=8,
            textColor=TEXT_GRAY,
            leading=14,
            alignment=TA_LEFT,
            spaceBefore=8,
        ),
        "body": s(
            "VIBody",
            fontName=_fn(),
            fontSize=10,
            textColor=TEXT_DARK,
            leading=17,
        ),
    }


_draw_header_footer = _make_hf("解析動画の説明書")

def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── KV テーブル ───────────────────────────────────────────────────────────────

def _kv_table(pairs: list[tuple[str, str]], styles: dict) -> Table:
    data = [
        [Paragraph(_safe(k), styles["kv_key"]), Paragraph(_safe(v), styles["kv_val"])]
        for k, v in pairs
    ]
    col_w = [CONTENT_W * 0.40, CONTENT_W * 0.60]
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


# ── データ取得 ────────────────────────────────────────────────────────────────

def _collect_job_metadata(job_dir: Path) -> dict:
    """job.json / *_report.json / analysis_summary.json から必要なデータを収集する。"""
    result: dict = {
        "job_id":              "—",
        "generated_at":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "height_m":            "—",
        "duration_sec":        "—",
        "resolution":          "—",
        "fps":                 "—",
        "wrist_max_speed_kmh": "—",
        "pose_detection_rate": "—",
    }

    # job.json
    job_json = _load_json(job_dir / "job.json") or {}
    if job_json.get("job_id"):
        result["job_id"] = job_json["job_id"]
    h = job_json.get("height_m")
    if isinstance(h, (int, float)):
        result["height_m"] = f"{h:.2f} m"

    # analysis_summary.json（新旧両形式に対応）
    summary = _load_json(job_dir / "report" / "analysis_summary.json") or {}
    if summary.get("status") not in (None, "skipped"):
        # 新形式
        if "video" in summary:
            vid = summary.get("video") or {}
            dur = vid.get("duration_sec")
            if isinstance(dur, (int, float)):
                result["duration_sec"] = f"{dur:.2f} 秒"
        # 旧形式
        elif summary.get("duration_sec") is not None:
            dur = summary["duration_sec"]
            if isinstance(dur, (int, float)):
                result["duration_sec"] = f"{dur:.2f} 秒"

    # *_report.json（output/ 配下の先頭1件から video_info / analysis を取得）
    output_dir = job_dir / "output"
    if output_dir.exists():
        rep_jsons = sorted(output_dir.glob("*_report.json"))
        if rep_jsons:
            rep = _load_json(rep_jsons[0]) or {}
            vi = rep.get("video_info") or {}
            w, h_px = vi.get("width"), vi.get("height")
            if w and h_px:
                result["resolution"] = f"{w} × {h_px} px"
            fps = vi.get("fps")
            if fps:
                result["fps"] = f"{fps:.3f}" if isinstance(fps, float) else str(fps)
            ana = rep.get("analysis") or {}
            spd = ana.get("wrist_max_speed_kmh")
            if isinstance(spd, (int, float)):
                result["wrist_max_speed_kmh"] = f"{spd:.1f} km/h"
            rate = ana.get("pose_detection_rate")
            if isinstance(rate, (int, float)):
                result["pose_detection_rate"] = f"{rate * 100:.1f} %"

    return result


def _find_existing_videos(job_dir: Path) -> list[tuple[str, str, str, bool]]:
    """
    解析動画の存在確認を行い、各動画の (stem, title, description, exists) リストを返す。
    存在する動画が先頭に来るようソートする。
    """
    output_dir = job_dir / "output"
    result: list[tuple[str, str, str, bool]] = []
    for stem, title, desc in _VIDEO_DEFS:
        mp4 = output_dir / f"{stem}.mp4" if output_dir.exists() else Path(f"{stem}.mp4")
        exists = mp4.exists()
        result.append((stem + ".mp4", title, desc, exists))
    return result


# ── PDF ストーリー構築 ────────────────────────────────────────────────────────

def _build_story(job_dir: Path, styles: dict) -> list:
    meta = _collect_job_metadata(job_dir)
    videos = _find_existing_videos(job_dir)
    existing_count = sum(1 for _, _, _, exists in videos if exists)

    story = []

    # ── 表紙ブロック ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(_safe("解析動画 説明書"), styles["title"]))
    story.append(Paragraph("Javelin Video Analysis", styles["subtitle"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width=CONTENT_W * 0.5, color=BRAND_ORANGE, hAlign="CENTER", thickness=2))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(_safe(f"出力日: {meta['generated_at']}"), styles["date_line"]))
    story.append(Spacer(1, 0.5 * cm))

    # ── 基本情報テーブル ──────────────────────────────────────────────────────
    story.append(Paragraph(_safe("基本情報"), styles["section"]))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Spacer(1, 0.2 * cm))

    kv_pairs: list[tuple[str, str]] = [
        ("Job ID",              meta["job_id"]),
        ("Generated at",        meta["generated_at"]),
        ("身長 / Height",        meta["height_m"]),
        ("動画尺 / Duration",    meta["duration_sec"]),
        ("解像度 / Resolution",  meta["resolution"]),
        ("フレームレート / FPS",  meta["fps"]),
        ("手首最大速度",          meta["wrist_max_speed_kmh"]),
        ("ポーズ検出率",          meta["pose_detection_rate"]),
    ]
    story.append(_kv_table(kv_pairs, styles))
    story.append(Spacer(1, 0.5 * cm))

    # ── 解析動画一覧 ──────────────────────────────────────────────────────────
    count_label = f"以下の{existing_count}本" if existing_count > 0 else "解析動画"
    story.append(
        Paragraph(
            _safe(f"解析動画の見方（{count_label}）"),
            styles["section"],
        )
    )
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Spacer(1, 0.3 * cm))

    for idx, (filename, title, desc, exists) in enumerate(videos):
        # 動画番号ラベル
        num_label = f"【{idx + 1}】"

        # ファイル名 + タイトル行
        story.append(
            Paragraph(
                _safe(f"{num_label} {title}"),
                styles["video_title"],
            )
        )
        story.append(
            Paragraph(
                _safe(f"ファイル名: {filename}"),
                styles["video_filename"],
            )
        )

        if exists:
            story.append(Paragraph(_safe(desc), styles["video_desc"]))
        else:
            story.append(
                Paragraph(
                    _safe("未生成 / Not generated"),
                    styles["not_generated"],
                )
            )

        story.append(Spacer(1, 0.25 * cm))
        story.append(HRFlowable(width=CONTENT_W, color=LIGHT_GRAY, thickness=0.5))
        story.append(Spacer(1, 0.15 * cm))

    # ── 免責文 ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Paragraph(_safe(_DISCLAIMER), styles["disclaimer"]))

    return story


# ── エントリポイント ──────────────────────────────────────────────────────────

def generate_video_instruction_pdf_for_job(job_dir: Path) -> Path:
    """
    解析動画説明書PDFを生成して返す。

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ（例: jobs/20260510_012144_0513）

    Returns
    -------
    Path
        生成された PDF のパス: ``<job_dir>/report/video_instruction.pdf``
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "video_instruction.pdf"

    styles = _make_styles()

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN_H,
        rightMargin=MARGIN_H,
        topMargin=BODY_TOP_MARGIN,
        bottomMargin=BODY_BOT_MARGIN,
        title="解析動画の説明書 — やり投げ動作解析",
        author="やり投げ動作解析システム",
    )

    story = _build_story(job_dir, styles)

    doc.build(
        story,
        onFirstPage=_draw_header_footer,
        onLaterPages=_draw_header_footer,
    )

    logger.info("[video_instruction_pdf] PDF 生成完了: %s", out_path)
    return out_path
