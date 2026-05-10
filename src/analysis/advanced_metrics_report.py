"""
src/analysis/advanced_metrics_report.py — Phase 12 高度指標 PDF レポート生成

advanced_metrics.json をもとに、advanced_metrics_report.pdf を生成します。

対象読者: 高校生アスリート、保護者、コーチ（専門用語を使いすぎない文体）
位置づけ: 参考資料（医療診断・競技指導の代替ではありません）

出力先: jobs/<job_id>/report/advanced_metrics_report.pdf

Usage:
    from src.analysis.advanced_metrics_report import generate_advanced_metrics_report_for_job
    from pathlib import Path

    out = generate_advanced_metrics_report_for_job(Path("jobs/20260508_070156_518a"))
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
    BRAND_ORANGE,
    MID_GRAY,
    LIGHT_GRAY,
    WARN_BG,
    WARN_BORDER,
    TEXT_GRAY,
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

logger = logging.getLogger("jva.advanced_metrics_report")

_MODULE_DIR = Path(__file__).resolve().parent
_REPO_ROOT  = _MODULE_DIR.parent.parent

_PAGE_W, _PAGE_H = A4
_MARGIN_LR = 1.8 * cm
_CONTENT_W = _PAGE_W - 2 * _MARGIN_LR


# ── ラベルデータ読み込み ─────────────────────────────────────────────────────

def _load_metric_labels() -> Dict[str, Any]:
    """configs/metric_labels.yaml を読み込む。"""
    cfg_path = _REPO_ROOT / "configs" / "metric_labels.yaml"
    try:
        import yaml  # type: ignore[import-not-found]
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _label(key: str, labels: Dict[str, Any]) -> str:
    return labels.get(key, {}).get("label", key)


def _caution(key: str, labels: Dict[str, Any]) -> str:
    return labels.get(key, {}).get("caution", "")


# ── フォーマットユーティリティ ───────────────────────────────────────────────

def _fmt(val: Any, digits: int = 3, suffix: str = "") -> str:
    if val is None:
        return "—"
    try:
        return f"{round(float(val), digits)}{suffix}"
    except (TypeError, ValueError):
        return str(val)


def _fmt_met(metric_entry: Any) -> str:
    """メトリクスエントリ dict または生値を文字列化する。"""
    if isinstance(metric_entry, dict):
        v = metric_entry.get("value")
        u = metric_entry.get("unit", "")
        return f"{_fmt(v)} {u}".strip() if v is not None else "—"
    return _fmt(metric_entry)


def _reliability_icon(rel: str) -> str:
    icons = {"high": "🟢 高", "medium": "🟡 中", "low": "🔴 低", "unknown": "⚪ 不明"}
    return icons.get(rel, rel)


def _rel_color(rel: str) -> Any:
    mapping = {
        "high":    colors.HexColor("#27AE60"),
        "medium":  colors.HexColor("#F39C12"),
        "low":     colors.HexColor("#E74C3C"),
        "unknown": colors.HexColor("#95A5A6"),
    }
    return mapping.get(rel, colors.HexColor("#95A5A6"))


# ── テーブル生成ヘルパー ─────────────────────────────────────────────────────

def _kv_table(
    rows: List[tuple],
    styles: dict,
    font_b: str,
    font_r: str,
    col_widths: Optional[List[float]] = None,
) -> Table:
    """KVテーブルを生成する。"""
    data = [
        [
            Paragraph(f'<font name="{font_b}" size="8.5">{safe_text(str(k))}</font>', styles["kv_key"]),
            Paragraph(f'<font name="{font_r}" size="8.5">{safe_text(str(v))}</font>', styles["kv_val"]),
        ]
        for k, v in rows
    ]
    cw = col_widths or [_CONTENT_W * 0.42, _CONTENT_W * 0.52]
    t = Table(data, colWidths=cw)
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f5f8ff")]),
        ("GRID",           (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
        ("TOPPADDING",     (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _section_header(title: str, styles: dict, font_b: str) -> Paragraph:
    return Paragraph(
        f'<font name="{font_b}" size="13" color="{BRAND_BLUE.hexval()}">{safe_text(title)}</font>',
        styles["section"],
    )


def _subsection_header(title: str, styles: dict, font_b: str) -> Paragraph:
    return Paragraph(
        f'<font name="{font_b}" size="10.5" color="{BRAND_BLUE.hexval()}">{safe_text(title)}</font>',
        styles["subsection"],
    )


def _note_para(text: str, styles: dict, font_r: str) -> Paragraph:
    return Paragraph(
        f'<font name="{font_r}" size="8" color="{TEXT_GRAY.hexval()}">{safe_text(text)}</font>',
        styles["note"],
    )


def _warn_box(text: str, styles: dict, font_b: str, font_r: str) -> Table:
    """警告ボックス。"""
    inner = [
        Paragraph(f'<font name="{font_b}" size="9">⚠️ 注意</font>', styles["warn"]),
        Paragraph(f'<font name="{font_r}" size="8.5">{safe_text(text)}</font>', styles["warn_body"]),
    ]
    t = Table([[inner]], colWidths=[_CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), WARN_BG),
        ("BOX",          (0, 0), (-1, -1), 0.8, WARN_BORDER),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
    ]))
    return t


# ── 指標セクション生成 ───────────────────────────────────────────────────────

def _metrics_section(
    title: str,
    metrics_dict: Dict[str, Any],
    key_list: List[tuple],  # (key, label_key)
    labels: Dict[str, Any],
    styles: dict,
    font_b: str,
    font_r: str,
) -> List[Any]:
    """指標テーブルセクションを story リストとして返す。"""
    story: List[Any] = []
    story.append(_subsection_header(title, styles, font_b))
    story.append(para_spacer())

    rows = []
    for key, label_key in key_list:
        entry = metrics_dict.get(key)
        val_str = _fmt_met(entry)
        lbl = _label(label_key or key, labels)
        rel = "unknown"
        if isinstance(entry, dict):
            rel = entry.get("reliability", "unknown")
        rel_str = _reliability_icon(rel)
        rows.append((lbl, f"{val_str}  {rel_str}"))

    if rows:
        story.append(_kv_table(rows, styles, font_b, font_r))
    else:
        story.append(_note_para("指標データがありません。", styles, font_r))

    story.append(Spacer(1, 3 * mm))
    return story


# ── メイン生成関数 ────────────────────────────────────────────────────────────

def generate_advanced_metrics_report(
    metrics: Dict[str, Any],
    job_dir: Path,
    output_path: Optional[Path] = None,
) -> Path:
    """
    advanced_metrics dict から PDF を生成して返す。

    Parameters
    ----------
    metrics : dict
        compute_advanced_metrics() の戻り値
    job_dir : Path
    output_path : Path, optional
    """
    report_dir = Path(job_dir) / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = report_dir / "advanced_metrics_report.pdf"

    labels = _load_metric_labels()
    styles = get_styles("am_")
    font_b = get_font(bold=True)
    font_r = get_font(bold=False)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=_MARGIN_LR, rightMargin=_MARGIN_LR,
        topMargin=2.5 * cm, bottomMargin=2.0 * cm,
        title="解析指標レポート（参考資料）",
        author="Javelin Video Analysis",
    )

    story: List[Any] = []

    # ── タイトル ──────────────────────────────────────────────────────────────
    story.append(Paragraph(
        f'<font name="{font_b}" size="18" color="{BRAND_BLUE.hexval()}">解析指標レポート</font>',
        styles["doc_title"],
    ))
    story.append(Paragraph(
        f'<font name="{font_r}" size="9" color="#CC4400">⚠️ このレポートは参考資料です。医療診断・競技指導の代替ではありません。</font>',
        styles["caption"],
    ))
    story.append(Spacer(1, 2 * mm))

    job_id     = metrics.get("job_id", "—")
    gen_at     = metrics.get("generated_at", "—")
    mv         = metrics.get("metrics_version", "—")
    dom_arm    = "右投げ" if metrics.get("dominant_arm") == "right" else "左投げ"
    story.append(Paragraph(
        f'<font name="{font_r}" size="9" color="{TEXT_GRAY.hexval()}">'
        f'ジョブID: {safe_text(job_id)}　利き腕: {dom_arm}　'
        f'生成日時: {safe_text(gen_at)}　バージョン: {mv}'
        f'</font>',
        styles["caption"],
    ))
    story.append(hr())
    story.append(section_spacer())

    # ── このレポートについて ───────────────────────────────────────────────────
    story.append(_section_header("このレポートについて", styles, font_b))
    story.append(para_spacer())
    story.append(Paragraph(
        f'<font name="{font_r}" size="9">'
        "このレポートは、やり投げ動画の姿勢推定データをもとに、動作の参考指標を"
        "まとめたものです。数値はいずれも「動画上の座標から算出した参考値」であり、"
        "実際の距離・速度・角度と完全に一致するわけではありません。"
        "撮影角度・動画品質・姿勢推定の精度によって数値が変動します。"
        "このレポートの数値だけでフォームや記録の良し悪しを判断しないでください。"
        "</font>",
        styles["body"],
    ))
    story.append(Spacer(1, 2 * mm))
    story.append(_warn_box(
        "このレポートは、専門的な競技指導・医療診断・怪我の診断を代替するものではありません。"
        "動作改善・ケガ予防に関しては、専門家（コーチ、トレーナー、医師）にご相談ください。",
        styles, font_b, font_r,
    ))
    story.append(section_spacer())

    # ── 動画品質と信頼度 ──────────────────────────────────────────────────────
    story.append(_section_header("動画品質と指標信頼度", styles, font_b))
    story.append(para_spacer())

    quality_info = metrics.get("quality", {})
    overall_q    = quality_info.get("overall_quality", "unknown")
    overall_rel  = quality_info.get("metrics_reliability", "unknown")
    det_rate     = quality_info.get("pose_detection_rate", 0.0)
    angle        = quality_info.get("filming_angle", "unknown")
    warnings     = quality_info.get("warnings", [])

    q_rows = [
        ("動画品質",           overall_q),
        ("指標の総合信頼度",   _reliability_icon(overall_rel)),
        ("姿勢推定検出率",     f"{det_rate:.0%}" if isinstance(det_rate, float) else str(det_rate)),
        ("撮影角度",           safe_text(angle)),
        ("FPS",               f"{metrics.get('fps', '—')} fps"),
    ]
    story.append(_kv_table(q_rows, styles, font_b, font_r))
    story.append(Spacer(1, 2 * mm))

    story.append(Paragraph(
        f'<font name="{font_b}" size="9">■ 信頼度の見方</font>',
        styles["body_bold"],
    ))
    rel_rows = [
        ("🟢 高（high）",    "動画品質・検出率がよく、信頼性の高い参考値です"),
        ("🟡 中（medium）",  "一定の精度はありますが、参考値として確認してください"),
        ("🔴 低（low）",     "動画品質や検出率が低く、数値の解釈には注意が必要です"),
        ("⚪ 不明（unknown）","データ不足または計算できませんでした"),
    ]
    story.append(_kv_table(rel_rows, styles, font_b, font_r))

    if warnings:
        story.append(Spacer(1, 2 * mm))
        for w in warnings:
            story.append(Paragraph(
                f'<font name="{font_r}" size="8" color="#CC4400">⚠️ {safe_text(w)}</font>',
                styles["note"],
            ))
    story.append(section_spacer())

    # ── リリース関連指標 ──────────────────────────────────────────────────────
    release = metrics.get("release_metrics", {})
    story.append(_section_header("リリース関連指標", styles, font_b))
    story.append(para_spacer())
    story.append(Paragraph(
        f'<font name="{font_r}" size="9">'
        "リリース（やりを手放す瞬間）の候補フレームを基準に計算した指標です。"
        "手首の高さ・速度・腕の伸びなどを参考値として確認できます。"
        "</font>",
        styles["body"],
    ))
    story.append(Spacer(1, 2 * mm))

    if not release.get("available", False):
        story.append(_note_para(
            f"リリース指標が計算できませんでした: {release.get('reason', '不明')}",
            styles, font_r))
    else:
        r_frame = release.get("release_frame")
        r_time  = release.get("release_time_sec")
        story.append(_note_para(
            f"リリース候補フレーム: {r_frame}　"
            f"時刻: {r_time:.2f} 秒" if r_time is not None else f"リリース候補フレーム: {r_frame}",
            styles, font_r))
        story.append(Spacer(1, 1 * mm))

        r_keys = [
            ("release_wrist_height_normalized",          "release_wrist_height_normalized"),
            ("release_wrist_height_relative_to_shoulder","release_wrist_height_relative_to_shoulder"),
            ("release_elbow_height_relative_to_shoulder","release_elbow_height_relative_to_shoulder"),
            ("release_shoulder_height",                   "release_shoulder_height"),
            ("release_hand_to_shoulder_distance",         "release_hand_to_shoulder_distance"),
            ("release_wrist_velocity_px_per_sec",         "release_wrist_velocity_px_per_sec"),
            ("release_wrist_velocity_normalized",         "release_wrist_velocity_normalized"),
            ("release_arm_extension_ratio",               "release_arm_extension_ratio"),
            ("release_trunk_angle_estimate",              "release_trunk_angle_estimate"),
            ("release_shoulder_line_tilt",                "release_shoulder_line_tilt"),
            ("release_hip_line_tilt",                     "release_hip_line_tilt"),
        ]
        story += _metrics_section("", release, r_keys, labels, styles, font_b, font_r)

        story.append(_note_para(
            "動画上の座標から算出した相対指標です。実際の距離・速度とは一致しない場合があります。",
            styles, font_r))
    story.append(section_spacer())

    # ── ブロック関連指標 ──────────────────────────────────────────────────────
    block = metrics.get("block_metrics", {})
    story.append(_section_header("ブロック関連指標", styles, font_b))
    story.append(para_spacer())
    story.append(Paragraph(
        f'<font name="{font_r}" size="9">'
        "ブロック（踏み込み脚の接地）候補フレームを基準に計算した指標です。"
        "腰の動き・体幹変化・ブロック〜リリースの時間などを参考値として確認できます。"
        f"{block.get('block_leg_note', '')}"
        "</font>",
        styles["body"],
    ))
    story.append(Spacer(1, 2 * mm))

    if not block.get("available", False):
        story.append(_note_para(
            f"ブロック指標が計算できませんでした: {block.get('reason', '不明')}",
            styles, font_r))
    else:
        b_keys = [
            ("block_to_release_time_sec",                "block_to_release_time_sec"),
            ("front_ankle_stability_score",              "front_ankle_stability_score"),
            ("front_knee_stability_score",               "front_knee_stability_score"),
            ("hip_center_velocity_before_block",         "hip_center_velocity_before_block"),
            ("hip_center_velocity_after_block",          "hip_center_velocity_after_block"),
            ("hip_deceleration_ratio",                   "hip_deceleration_ratio"),
            ("trunk_forward_change_around_block",        "trunk_tilt_estimate"),
            ("shoulder_rotation_change_around_block",    "shoulder_rotation_change_around_block"),
            ("hip_rotation_change_around_block",         "hip_rotation_change_around_block"),
        ]
        story += _metrics_section("", block, b_keys, labels, styles, font_b, font_r)
    story.append(section_spacer())

    # ── 体幹・肩腰分離指標 ────────────────────────────────────────────────────
    trunk = metrics.get("trunk_metrics", {})
    story.append(_section_header("体幹・肩腰分離指標（2D推定）", styles, font_b))
    story.append(para_spacer())
    story.append(Paragraph(
        f'<font name="{font_r}" size="9">'
        "肩ラインと腰ラインの向きをもとに、体幹の回旋・前傾を2D動画から推定した参考値です。"
        "3Dの正確な角度ではなく、あくまで2D画像上の見かけの角度推定です。"
        "横方向からの撮影条件が最適です。"
        "</font>",
        styles["body"],
    ))
    story.append(Spacer(1, 2 * mm))

    if not trunk.get("available", False):
        story.append(_note_para("体幹指標が計算できませんでした。", styles, font_r))
    else:
        t_keys = [
            ("shoulder_hip_separation_angle_estimate_at_block",   "shoulder_hip_separation_angle_estimate"),
            ("shoulder_hip_separation_angle_estimate_at_release",  "shoulder_hip_separation_angle_estimate"),
            ("shoulder_hip_separation_max",                        "shoulder_hip_separation_angle_estimate"),
            ("trunk_tilt_estimate_at_block",                       "trunk_tilt_estimate"),
            ("trunk_tilt_estimate_at_release",                     "trunk_tilt_estimate"),
            ("trunk_opening_change_from_block_to_release",         "trunk_opening_at_release"),
        ]
        story += _metrics_section("", trunk, t_keys, labels, styles, font_b, font_r)
        story.append(_note_para(
            "2D動画上の見かけの角度推定です。3Dの正確な回旋角ではありません。"
            "横方向または斜め方向の撮影条件に影響されます。",
            styles, font_r))
    story.append(section_spacer())

    # ── 投げ腕指標 ───────────────────────────────────────────────────────────
    arm = metrics.get("arm_metrics", {})
    story.append(_section_header("投げ腕指標", styles, font_b))
    story.append(para_spacer())
    story.append(Paragraph(
        f'<font name="{font_r}" size="9">'
        "投げ腕（利き腕）の手首・肘・肩の動きから算出した参考指標です。"
        "手首軌跡の長さ・速度・槍引き距離などを確認できます。"
        "</font>",
        styles["body"],
    ))
    story.append(Spacer(1, 2 * mm))

    if not arm.get("available", False):
        story.append(_note_para("投げ腕指標が計算できませんでした。", styles, font_r))
    else:
        a_keys = [
            ("throwing_wrist_max_height",              "throwing_wrist_peak_velocity"),
            ("throwing_wrist_min_height",              "throwing_wrist_peak_velocity"),
            ("throwing_wrist_path_length",             "throwing_wrist_path_length"),
            ("throwing_wrist_peak_velocity",           "throwing_wrist_peak_velocity"),
            ("throwing_wrist_velocity_at_release",     "throwing_wrist_velocity_at_release"),
            ("elbow_angle_estimate_at_release",        "elbow_angle_estimate_at_release"),
            ("shoulder_elbow_wrist_alignment_score",   "shoulder_elbow_wrist_alignment_score"),
            ("arm_pullback_distance_estimate",         "arm_pullback_distance_estimate"),
            ("withdrawal_to_release_time_sec",         "withdrawal_to_release_time_sec"),
        ]
        story += _metrics_section("", arm, a_keys, labels, styles, font_b, font_r)
    story.append(section_spacer())

    # ── フェーズ別指標 ────────────────────────────────────────────────────────
    phase = metrics.get("phase_metrics", {})
    story.append(_section_header("フェーズ別指標", styles, font_b))
    story.append(para_spacer())
    story.append(Paragraph(
        f'<font name="{font_r}" size="9">'
        "各フェーズ（助走・クロスステップ・槍引き・フォロースルー・リカバリー）の"
        "時間・体の動き量を参考値として整理しています。"
        "フェーズが指定されていない場合は「—」と表示されます。"
        "</font>",
        styles["body"],
    ))
    story.append(Spacer(1, 2 * mm))

    phase_name_ja = {
        "approach":       "助走",
        "cross_step":     "クロスステップ",
        "withdrawal":     "槍引き",
        "block":          "ブロック",
        "release":        "リリース",
        "follow_through": "フォロースルー",
        "recovery":       "リカバリー",
    }
    phase_rows: List[tuple] = []
    for ph_key, ph_ja in phase_name_ja.items():
        ph_data = phase.get(ph_key, {})
        dur_frames = ph_data.get("duration_frames", "—")
        dur_sec    = ph_data.get("duration_sec", "—")
        ph_rel     = ph_data.get("phase_reliability", "unknown")
        det_rate   = ph_data.get("pose_detection_rate_in_phase")
        det_str    = f"{det_rate:.0%}" if isinstance(det_rate, float) else "—"
        phase_rows.append((
            ph_ja,
            f"フレーム数: {dur_frames}　時間: {_fmt(dur_sec, 2, 's')}　検出率: {det_str}　信頼度: {_reliability_icon(ph_rel)}",
        ))
    if phase_rows:
        story.append(_kv_table(phase_rows, styles, font_b, font_r, [_CONTENT_W * 0.22, _CONTENT_W * 0.72]))
    else:
        story.append(_note_para("フェーズ情報がありません。", styles, font_r))
    story.append(section_spacer())

    # ── 次回撮影の改善ポイント ────────────────────────────────────────────────
    story.append(_section_header("次回撮影時の確認ポイント（参考）", styles, font_b))
    story.append(para_spacer())

    tips: List[str] = []
    if quality_info.get("overall_quality") in ("low", "unknown"):
        tips.append("動画品質を上げると、指標の精度が向上します。明るい場所・高解像度での撮影をお試しください。")
    if quality_info.get("pose_detection_rate", 1.0) < 0.65:
        tips.append("姿勢推定の検出率が低めです。選手全体が映るよう撮影距離・画角を調整してください。")
    if quality_info.get("filming_angle", "unknown") not in ("side", "unknown"):
        tips.append("横方向（側面）からの撮影が、体幹・肩腰分離指標の精度向上に効果的です。")
    if not release.get("available"):
        tips.append("リリースフレームが指定されていません。管理画面でフレームを指定すると、より詳細な指標が計算できます。")
    if not block.get("available"):
        tips.append("ブロックフレームが指定されていません。管理画面でフレームを指定すると、ブロック関連指標が計算できます。")
    if not tips:
        tips.append("現在の撮影条件でおおむね指標を計算できています。引き続き動画解析にご活用ください。")

    for tip in tips:
        story.append(Paragraph(
            f'<font name="{font_r}" size="9">• {safe_text(tip)}</font>',
            styles["body"],
        ))
    story.append(section_spacer())

    # ── 注意事項 ─────────────────────────────────────────────────────────────
    story.append(_section_header("注意事項", styles, font_b))
    story.append(para_spacer())
    cautions = [
        "このレポートの数値はすべて「参考値」です。動画上の座標から算出しており、実際の物理的な値とは異なります。",
        "撮影角度・動画品質・服装・背景により、姿勢推定の精度が変わります。特に2D角度推定は横方向の撮影が最適です。",
        "「信頼度 低」の指標は誤差が大きい場合があります。参考程度に留めてください。",
        "このレポートは医療診断・怪我の診断の代替ではありません。",
        "このレポートは専門的な競技指導の代替ではありません。コーチ・トレーナーの判断を最優先してください。",
        "高校生アスリートの成長段階には個人差があります。数値だけで評価しないでください。",
    ]
    for c in cautions:
        story.append(Paragraph(
            f'<font name="{font_r}" size="9">• {safe_text(c)}</font>',
            styles["body"],
        ))
    story.append(section_spacer())
    story.extend(disclaimer_block(styles))

    doc.build(story, onFirstPage=make_header_footer("解析指標レポート（参考資料）"),
              onLaterPages=make_header_footer("解析指標レポート（参考資料）"))

    logger.info("[advanced_metrics_report] PDF 生成完了: %s", output_path)
    return output_path


def generate_advanced_metrics_report_for_job(job_dir: Path) -> Optional[Path]:
    """
    ジョブディレクトリから advanced_metrics_report.pdf を生成する。

    advanced_metrics.json がない場合は先に計算する。
    失敗しても例外を送出しない（worker 安全設計）。
    """
    job_dir = Path(job_dir)
    try:
        from src.analysis.advanced_metrics import (
            load_advanced_metrics, compute_advanced_metrics_for_job,
        )
        metrics = load_advanced_metrics(job_dir)
        if metrics is None or metrics.get("status") == "failed":
            compute_advanced_metrics_for_job(job_dir)
            metrics = load_advanced_metrics(job_dir)

        if metrics is None:
            logger.warning("[advanced_metrics_report] metrics が読み込めませんでした: %s", job_dir.name)
            return None

        out_path = generate_advanced_metrics_report(metrics, job_dir)
        return out_path

    except Exception as e:
        logger.error("[advanced_metrics_report] PDF 生成エラー: %s — %s", job_dir.name, e)
        return None
