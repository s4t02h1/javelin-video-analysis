"""
athlete_data_sheet_generator.py — アスリート向け解析データシート PDF 生成

pose_landmarks.csv などの生データを読み込み、アスリートが理解しやすい形式に
変換した PDF を生成する。

Usage:
    from src.athlete_data_sheet_generator import generate_athlete_data_sheet_for_job
    pdf_path = generate_athlete_data_sheet_for_job(Path("jobs/20260510_012144_0513"))
    # -> Path("jobs/20260510_012144_0513/report/athlete_data_sheet.pdf")
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
            logger.info("[athlete_data_sheet] 日本語フォント登録: %s", font_path)
            return font_name, bold_name
        except Exception as exc:
            logger.warning("[athlete_data_sheet] フォント登録失敗 (%s): %s", font_path, exc)
    return "", ""


_JP_FONT, _JP_FONT_BOLD = _setup_japanese_font()


def _fn(bold: bool = False) -> str:
    if bold:
        return _JP_FONT_BOLD if _JP_FONT_BOLD else "Helvetica-Bold"
    return _JP_FONT if _JP_FONT else "Helvetica"


def _safe(text: str) -> str:
    if _JP_FONT:
        return text
    return "".join(
        c if c.encode("latin-1", errors="ignore") else "?" for c in text
    )


# ── 定数 ──────────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN = 2.0 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

BRAND_BLUE   = colors.HexColor("#1A4D8F")
BRAND_ORANGE = colors.HexColor("#E86A2E")
LIGHT_GRAY   = colors.HexColor("#F5F5F5")
MID_GRAY     = colors.HexColor("#CCCCCC")
TEXT_DARK    = colors.HexColor("#1A1A1A")
TEXT_GRAY    = colors.HexColor("#666666")
WARN_BG      = colors.HexColor("#FFF3CD")
WARN_BORDER  = colors.HexColor("#FFC107")

_DISCLAIMER = (
    "【免責事項】本資料は、動画から身体の動きや軌跡を可視化し、練習の振り返りを補助するための"
    "参考資料です。競技指導、医療判断、怪我の診断を代替するものではありません。"
    "速度・角度・軌跡などの数値は、撮影条件や姿勢推定精度の影響を受ける参考推定値です。"
)


# ── スタイル ──────────────────────────────────────────────────────────────────

def _make_styles() -> dict:
    def s(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    return {
        "title": s("ADSTitle", fontName=_fn(True), fontSize=22,
                   textColor=BRAND_BLUE, spaceAfter=4, alignment=TA_CENTER),
        "subtitle": s("ADSSubtitle", fontName=_fn(), fontSize=12,
                      textColor=BRAND_ORANGE, spaceAfter=2, alignment=TA_CENTER),
        "date_line": s("ADSDateLine", fontName=_fn(), fontSize=9,
                       textColor=colors.grey, alignment=TA_CENTER),
        "section": s("ADSSection", fontName=_fn(True), fontSize=13,
                     textColor=BRAND_BLUE, spaceBefore=10, spaceAfter=4),
        "kv_key": s("ADSKVKey", fontName=_fn(True), fontSize=10,
                    textColor=BRAND_BLUE),
        "kv_val": s("ADSKVVal", fontName=_fn(), fontSize=10,
                    textColor=TEXT_DARK),
        "body": s("ADSBody", fontName=_fn(), fontSize=10,
                  textColor=TEXT_DARK, leading=17, spaceAfter=3),
        "body_sm": s("ADSBodySm", fontName=_fn(), fontSize=9,
                     textColor=TEXT_GRAY, leading=14, spaceAfter=2),
        "warn": s("ADSWarn", fontName=_fn(True), fontSize=10,
                  textColor=colors.HexColor("#856404"), leading=16),
        "disclaimer": s("ADSDisclaimer", fontName=_fn(), fontSize=8,
                        textColor=TEXT_GRAY, leading=13, alignment=TA_LEFT),
        "note_label": s("ADSNoteLabel", fontName=_fn(True), fontSize=10,
                        textColor=TEXT_DARK, spaceBefore=6, spaceAfter=2),
    }


# ── ヘッダー・フッター ────────────────────────────────────────────────────────

def _draw_header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(BRAND_BLUE)
    canvas.rect(0, PAGE_H - 1.1 * cm, PAGE_W, 1.1 * cm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(MARGIN, PAGE_H - 0.72 * cm, "Javelin Video Analysis")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 0.72 * cm,
                           "Athlete Data Sheet / アスリート向けデータシート")
    canvas.setFillColor(MID_GRAY)
    canvas.rect(0, 0, PAGE_W, 0.9 * cm, fill=1, stroke=0)
    canvas.setFillColor(TEXT_GRAY)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(MARGIN, 0.32 * cm,
                      "Generated by Javelin Video Analysis  |  Not for medical use  |  Reference estimates only")
    canvas.drawRightString(PAGE_W - MARGIN, 0.32 * cm, f"Page {doc.page}")
    canvas.restoreState()


# ── JSON / CSV ヘルパー ──────────────────────────────────────────────────────

def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _fmt(val, suffix: str = "", digits: int = 2, fallback: str = "—") -> str:
    """数値を文字列にフォーマット。None / 空の場合は fallback を返す。"""
    if val is None:
        return fallback
    try:
        f = float(val)
        return f"{f:.{digits}f}{suffix}"
    except (TypeError, ValueError):
        v = str(val).strip()
        return (v + suffix) if v else fallback


def _pct(val, fallback: str = "—") -> str:
    if val is None:
        return fallback
    try:
        return f"{float(val) * 100:.1f} %"
    except (TypeError, ValueError):
        return fallback


# ── KV テーブル ───────────────────────────────────────────────────────────────

def _kv_table(pairs: list[tuple[str, str]], styles: dict,
              key_w: float = 0.42) -> Table:
    data = [
        [Paragraph(_safe(k), styles["kv_key"]),
         Paragraph(_safe(v), styles["kv_val"])]
        for k, v in pairs
    ]
    tbl = Table(data, colWidths=[CONTENT_W * key_w, CONTENT_W * (1 - key_w)],
                hAlign="LEFT")
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


# ── 警告ボックス ──────────────────────────────────────────────────────────────

def _warn_table(text: str, styles: dict) -> Table:
    data = [[Paragraph(_safe(f"⚠ {text}"), styles["warn"])]]
    tbl = Table(data, colWidths=[CONTENT_W], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), WARN_BG),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 1.0, WARN_BORDER),
    ]))
    return tbl


# ── データ収集 ───────────────────────────────────────────────────────────────

def _collect_metadata(job_dir: Path) -> dict:
    """job.json / customer_info.json / analysis_summary.json / *_report.json から
    必要な情報を収集して返す。"""
    meta: dict = {
        "job_id":              "—",
        "generated_at":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "customer_name":       "—",
        "event":               "—",
        "dominant_arm":        "—",
        "height_m":            "—",
        "filming_angle":       "—",
        # 動画情報
        "duration_sec":        None,
        "fps":                 None,
        "total_frames":        None,
        "resolution":          "—",
        # 解析品質
        "pose_detection_rate": None,
        "pose_detection_rate_str": "—",
        "low_quality":         False,
        # 速度指標
        "wrist_max_speed_kmh": None,
        "wrist_mean_speed_kmh": None,
        # 手首高さ
        "wrist_height_peak_time_sec": None,
        "wrist_height_max":    None,
        "wrist_height_range":  None,
        # 重心移動
        "shoulder_x_delta":    None,
        "hip_x_delta":         None,
        # 有効区間
        "valid_start_time":    "—",
        "valid_end_time":      "—",
        "valid_ratio":         None,
        # 警告
        "warnings":            [],
    }

    # ── job.json ─────────────────────────────────────────────────────────────
    job = _load_json(job_dir / "job.json") or {}
    if job.get("job_id"):
        meta["job_id"] = job["job_id"]
    h = job.get("height_m")
    if isinstance(h, (int, float)):
        meta["height_m"] = f"{h:.2f} m"

    # ── customer_info.json ────────────────────────────────────────────────────
    ci = _load_json(job_dir / "customer_info.json") or {}
    name = ci.get("customer_name") or ""
    meta["customer_name"] = name if name else "—"
    meta["event"]         = ci.get("event") or "—"
    arm = ci.get("dominant_arm") or ci.get("dominant_hand") or ""
    meta["dominant_arm"]  = {"right": "右 (Right)", "left": "左 (Left)"}.get(arm, arm or "—")
    angle = ci.get("filming_angle") or ci.get("camera_angle") or ""
    meta["filming_angle"] = {"side": "側面 (Side)", "back": "後方 (Back)",
                              "front": "正面 (Front)", "diagonal": "斜め (Diagonal)"}.get(angle, angle or "—")

    # ── analysis_summary.json（新旧両形式）────────────────────────────────────
    summary = _load_json(job_dir / "report" / "analysis_summary.json") or {}
    if summary.get("status") not in (None, "skipped"):
        # 新形式
        if "video" in summary:
            vid = summary.get("video") or {}
            dur = vid.get("duration_sec")
            if isinstance(dur, (int, float)):
                meta["duration_sec"] = dur
            fc = vid.get("frame_count")
            if fc is not None:
                meta["total_frames"] = fc
        # 旧形式
        elif summary.get("duration_sec") is not None:
            meta["duration_sec"] = summary["duration_sec"]
        if summary.get("total_frames") is not None:
            meta["total_frames"] = summary["total_frames"]

        # 手首高さ
        meta["wrist_height_peak_time_sec"] = summary.get("wrist_height_peak_time_sec")
        meta["wrist_height_max"]   = summary.get("wrist_height_max")
        meta["wrist_height_range"] = summary.get("wrist_height_range")

        # 重心移動
        sc_s = summary.get("shoulder_center_x_start")
        sc_e = summary.get("shoulder_center_x_end")
        if isinstance(sc_s, (int, float)) and isinstance(sc_e, (int, float)):
            meta["shoulder_x_delta"] = round(sc_e - sc_s, 4)
        hc_s = summary.get("hip_center_x_start")
        hc_e = summary.get("hip_center_x_end")
        if isinstance(hc_s, (int, float)) and isinstance(hc_e, (int, float)):
            meta["hip_x_delta"] = round(hc_e - hc_s, 4)

        # fps: フラット形式の fps_estimated を読む（report.json があれば後で上書きされる）
        if summary.get("fps_estimated") is not None and meta.get("fps") is None:
            meta["fps"] = summary["fps_estimated"]

        # 新形式 key_metrics
        km = summary.get("key_metrics") or {}
        if km.get("right_wrist_max_height_time_sec") is not None:
            meta["wrist_height_peak_time_sec"] = km["right_wrist_max_height_time_sec"]

        # 新形式 warnings
        warns = summary.get("warnings") or []
        meta["warnings"].extend(warns)

    # ── *_report.json（output/ 配下の先頭1件）────────────────────────────────
    output_dir = job_dir / "output"
    if output_dir.exists():
        rep_jsons = sorted(output_dir.glob("*_report.json"))
        if rep_jsons:
            rep = _load_json(rep_jsons[0]) or {}
            vi = rep.get("video_info") or {}
            w, h_px = vi.get("width"), vi.get("height")
            if w and h_px:
                meta["resolution"] = f"{w} × {h_px} px"
            fps = vi.get("fps")
            if fps is not None:
                meta["fps"] = fps
            if meta["total_frames"] is None:
                meta["total_frames"] = vi.get("total_frames")
            if meta["duration_sec"] is None:
                meta["duration_sec"] = vi.get("duration_s")

            ana = rep.get("analysis") or {}
            rate = ana.get("pose_detection_rate")
            if rate is not None:
                meta["pose_detection_rate"] = rate
                meta["pose_detection_rate_str"] = f"{rate * 100:.1f} %"
                if rate < 0.70:
                    meta["low_quality"] = True
            spd_max = ana.get("wrist_max_speed_kmh")
            if spd_max is not None:
                meta["wrist_max_speed_kmh"] = spd_max
            spd_mean = ana.get("wrist_mean_speed_kmh")
            if spd_mean is not None:
                meta["wrist_mean_speed_kmh"] = spd_mean

    # ── valid_segment.json ────────────────────────────────────────────────────
    vs = _load_json(job_dir / "report" / "valid_segment.json") or {}
    vs_start = vs.get("valid_start_time_sec")
    vs_end   = vs.get("valid_end_time_sec")
    vs_ratio = vs.get("valid_ratio")
    if isinstance(vs_start, (int, float)):
        meta["valid_start_time"] = f"{vs_start:.2f} 秒"
    if isinstance(vs_end, (int, float)):
        meta["valid_end_time"] = f"{vs_end:.2f} 秒"
    if isinstance(vs_ratio, (int, float)):
        meta["valid_ratio"] = vs_ratio

    return meta


# ── PDF ストーリー構築 ────────────────────────────────────────────────────────

def _build_story(job_dir: Path, styles: dict) -> list:
    meta = _collect_metadata(job_dir)
    story = []

    # ── タイトルブロック ───────────────────────────────────────────────────
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(_safe("アスリート向け解析データシート"), styles["title"]))
    story.append(Paragraph("Athlete Data Sheet  —  Javelin Video Analysis", styles["subtitle"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width=CONTENT_W * 0.5, color=BRAND_ORANGE,
                             hAlign="CENTER", thickness=2))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(_safe(f"出力日: {meta['generated_at']}"), styles["date_line"]))
    story.append(Spacer(1, 0.4 * cm))

    # ── 注意: 参考推定値である旨 ──────────────────────────────────────────
    story.append(Paragraph(
        _safe("本資料の数値はすべて 2D 動画からの参考推定値です。競技判断や医療診断には使用しないでください。"),
        styles["body_sm"],
    ))
    story.append(Spacer(1, 0.2 * cm))

    # ── 警告ボックス ──────────────────────────────────────────────────────
    if meta["low_quality"]:
        story.append(_warn_table(
            f"解析精度に注意: ポーズ検出率が {meta['pose_detection_rate_str']} と低めです。"
            "撮影角度・照明・服装によって精度が下がることがあります。",
            styles,
        ))
        story.append(Spacer(1, 0.2 * cm))
    for w_msg in meta["warnings"]:
        story.append(_warn_table(str(w_msg), styles))
        story.append(Spacer(1, 0.15 * cm))

    # ── セクション 1: 選手情報 ────────────────────────────────────────────
    story.append(Paragraph(_safe("1. 選手情報"), styles["section"]))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_kv_table([
        ("Job ID",          meta["job_id"]),
        ("出力日",           meta["generated_at"]),
        ("氏名 / Name",     meta["customer_name"]),
        ("種目 / Event",    meta["event"]),
        ("利き腕 / Dominant Arm", meta["dominant_arm"]),
        ("身長 / Height",   meta["height_m"]),
        ("撮影方向 / Camera Angle", meta["filming_angle"]),
    ], styles))
    story.append(Spacer(1, 0.4 * cm))

    # ── セクション 2: 動画情報 ────────────────────────────────────────────
    story.append(Paragraph(_safe("2. 動画情報"), styles["section"]))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Spacer(1, 0.2 * cm))

    dur_str = _fmt(meta["duration_sec"], " 秒") if meta["duration_sec"] is not None else "—"
    fps_str = _fmt(meta["fps"], "", digits=3) if meta["fps"] is not None else "—"
    fr_str  = str(int(meta["total_frames"])) if meta["total_frames"] is not None else "—"
    story.append(_kv_table([
        ("動画時間 / Duration",  dur_str),
        ("フレームレート / FPS", fps_str),
        ("総フレーム数 / Frames", fr_str),
        ("解像度 / Resolution",  meta["resolution"]),
    ], styles))
    story.append(Spacer(1, 0.4 * cm))

    # ── セクション 3: 解析品質 ────────────────────────────────────────────
    story.append(Paragraph(_safe("3. 解析品質"), styles["section"]))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Spacer(1, 0.2 * cm))

    story.append(_kv_table([
        ("ポーズ検出率 / Detection Rate",
         meta["pose_detection_rate_str"] + (" ⚠ 低め" if meta["low_quality"] else "")),
        ("有効解析区間 開始", meta["valid_start_time"]),
        ("有効解析区間 終了", meta["valid_end_time"]),
        ("有効区間比率 / Valid Ratio",
         _pct(meta["valid_ratio"]) if meta["valid_ratio"] is not None else "—"),
    ], styles))
    story.append(Spacer(1, 0.4 * cm))

    # ── セクション 4: 主要指標（参考推定値）──────────────────────────────
    story.append(Paragraph(_safe("4. 主要指標（すべて参考推定値）"), styles["section"]))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Spacer(1, 0.2 * cm))

    spd_max_str  = (_fmt(meta["wrist_max_speed_kmh"], " km/h") + " ※推定値"
                    if meta["wrist_max_speed_kmh"] is not None else "未計算")
    spd_mean_str = (_fmt(meta["wrist_mean_speed_kmh"], " km/h") + " ※推定値"
                    if meta["wrist_mean_speed_kmh"] is not None else "未計算")
    peak_t_str   = (_fmt(meta["wrist_height_peak_time_sec"], " 秒")
                    if meta["wrist_height_peak_time_sec"] is not None else "—")
    wh_max_str   = (_fmt(meta["wrist_height_max"], "", digits=4) + " (norm 0–1)"
                    if meta["wrist_height_max"] is not None else "—")
    wh_range_str = (_fmt(meta["wrist_height_range"], "", digits=4)
                    if meta["wrist_height_range"] is not None else "—")
    sh_delta_str = (_fmt(meta["shoulder_x_delta"], "", digits=4) + " (norm)"
                    if meta["shoulder_x_delta"] is not None else "—")
    hip_delta_str= (_fmt(meta["hip_x_delta"], "", digits=4) + " (norm)"
                    if meta["hip_x_delta"] is not None else "—")

    story.append(_kv_table([
        ("右手首 最大速度 ※推定",   spd_max_str),
        ("右手首 平均速度 ※推定",   spd_mean_str),
        ("右手首 最高到達時刻",      peak_t_str),
        ("右手首 最高到達高さ (norm)", wh_max_str),
        ("右手首 高さ可動域 (norm)",  wh_range_str),
        ("肩中心 X 移動量 (norm)",   sh_delta_str),
        ("腰中心 X 移動量 (norm)",   hip_delta_str),
    ], styles))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(
        _safe("※ norm（正規化座標）は画面幅・高さを 1.0 としたときの相対値です。"
              "実際の距離とは異なります。"),
        styles["body_sm"],
    ))
    story.append(Spacer(1, 0.4 * cm))

    # ── セクション 5: 見るべき解析動画 ───────────────────────────────────
    story.append(Paragraph(_safe("5. 見るべき解析動画"), styles["section"]))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Spacer(1, 0.2 * cm))

    video_guide = [
        ("analysis_original_skeleton.mp4",
         "骨格トレース — 全体の動きの流れ・腕の軌道・リリースを確認"),
        ("analysis_original_vectors.mp4",
         "速度・加速度ベクトル — 各関節がどの方向に動いているかを確認"),
        ("analysis_original_stickman.mp4",
         "スティックマン — フォームの輪郭・姿勢・タイミングを確認"),
        ("analysis_original_hud.mp4",
         "HUD ダッシュボード — 速度変化の数値を直感的に確認"),
        ("analysis_original_analysis.mp4",
         "統合コーチング解析 — フェーズ・角度・運動連鎖を総合的に確認"),
    ]
    # 実際に存在するものだけ表示
    output_dir = job_dir / "output"
    shown = []
    for fname, desc in video_guide:
        mp4 = output_dir / fname if output_dir.exists() else Path(fname)
        exists_mark = "✓" if mp4.exists() else "（未生成）"
        shown.append((f"{exists_mark}  {fname}", desc))

    story.append(_kv_table(shown, styles, key_w=0.45))
    story.append(Spacer(1, 0.4 * cm))

    # ── セクション 6: 次に確認するとよいポイント ─────────────────────────
    story.append(Paragraph(_safe("6. 次に確認するとよいポイント"), styles["section"]))
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Spacer(1, 0.2 * cm))

    next_checks = [
        "スローモーション再生で助走〜リリースの流れを確認する",
        "statistics_original_skeleton.mp4 で手首の軌跡が滑らかかどうか確認する",
        "ベクトル動画で肩→肘→手首の順に加速しているか（運動連鎖）を確認する",
        "HUD 動画でリリース付近の速度ピークを確認する",
        "フォームの左右対称性をスティックマン動画で確認する",
        "ポーズ検出率が低い場合は撮影条件（横からの撮影・明るさ）を改善する",
    ]
    for chk in next_checks:
        story.append(Paragraph(_safe(f"• {chk}"), styles["body"]))
    story.append(Spacer(1, 0.4 * cm))

    # ── 免責文 ────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=CONTENT_W, color=MID_GRAY))
    story.append(Paragraph(_safe(_DISCLAIMER), styles["disclaimer"]))

    return story


# ── エントリポイント ──────────────────────────────────────────────────────────

def generate_athlete_data_sheet_for_job(job_dir: Path) -> Path:
    """アスリート向けデータシート PDF を生成して返す。

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ（例: jobs/20260510_012144_0513）

    Returns
    -------
    Path
        生成された PDF のパス: ``<job_dir>/report/athlete_data_sheet.pdf``
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "athlete_data_sheet.pdf"

    styles = _make_styles()
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN + 1.1 * cm,
        bottomMargin=MARGIN + 0.9 * cm,
        title="Athlete Data Sheet — Javelin Video Analysis",
        author="Javelin Video Analysis",
    )
    doc.build(
        _build_story(job_dir, styles),
        onFirstPage=_draw_header_footer,
        onLaterPages=_draw_header_footer,
    )
    logger.info("[athlete_data_sheet] PDF 生成完了: %s", out_path)
    return out_path
