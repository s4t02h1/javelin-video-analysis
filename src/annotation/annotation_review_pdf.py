"""
src/annotation/annotation_review_pdf.py — Phase 11 アノテーション確認 PDF 生成

annotation.json の内容から管理者・研究開発用の確認 PDF を生成します。

⚠️  注意: これはユーザー向け納品物ではなく、管理者・研究開発用資料です。
    個人情報や source_video_path などの内部情報が含まれる場合があります。
    外部送付は避けてください。

出力先: data/annotations/{annotation_id}/annotation_review.pdf

Usage:
    from src.annotation.annotation_review_pdf import generate_annotation_review_pdf

    pdf_path = generate_annotation_review_pdf("ann_20260510_120000_abcd")
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

logger = logging.getLogger("jva.annotation.pdf")

_PAGE_W, _PAGE_H = A4
_MARGIN_LR = 2.0 * cm
_CONTENT_W  = _PAGE_W - 2 * _MARGIN_LR

_MODULE_DIR = Path(__file__).resolve().parent   # src/annotation/
_REPO_ROOT  = _MODULE_DIR.parent.parent          # project root


def _annotations_root() -> Path:
    import os
    from src.config import cfg
    custom = os.getenv("JVA_ANNOTATIONS_DIR", "").strip()
    if custom:
        p = Path(custom)
        return p if p.is_absolute() else (_REPO_ROOT / p)
    return cfg.DATA_DIR / "annotations"


def _load_annotation(annotation_id: str) -> Optional[Dict[str, Any]]:
    ann_path = _annotations_root() / annotation_id / "annotation.json"
    if not ann_path.exists():
        return None
    try:
        return json.loads(ann_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[annotation_pdf] 読み込み失敗: %s — %s", annotation_id, e)
        return None


def _fmt(val: Any, suffix: str = "") -> str:
    if val is None:
        return "—"
    return f"{val}{suffix}"


def _kv_table(rows: List[tuple], styles: dict, font_b: str, font_r: str) -> Table:
    """KVテーブルを生成する。"""
    data = [
        [
            Paragraph(f'<font name="{font_b}" size="9">{safe_text(k)}</font>', styles["caption"]),
            Paragraph(f'<font name="{font_r}" size="9">{safe_text(str(v))}</font>', styles["caption"]),
        ]
        for k, v in rows
    ]
    t = Table(data, colWidths=[_CONTENT_W * 0.35, _CONTENT_W * 0.55])
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("GRID",           (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
        ("TOPPADDING",     (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
    ]))
    return t


def generate_annotation_review_pdf(
    annotation_id: str,
    output_path: Optional[Path] = None,
) -> Path:
    """
    アノテーション確認 PDF を生成する。

    Parameters
    ----------
    annotation_id : str
        アノテーションID
    output_path : Path, optional
        出力先パス。None の場合は data/annotations/{annotation_id}/annotation_review.pdf

    Returns
    -------
    Path
        生成した PDF のパス

    Raises
    ------
    FileNotFoundError
        annotation.json が存在しない場合
    """
    ann = _load_annotation(annotation_id)
    if ann is None:
        raise FileNotFoundError(f"annotation.json が見つかりません: {annotation_id}")

    if output_path is None:
        output_path = _annotations_root() / annotation_id / "annotation_review.pdf"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = get_styles()
    font_b = get_font(bold=True)
    font_r = get_font(bold=False)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=_MARGIN_LR, rightMargin=_MARGIN_LR,
        topMargin=2.5 * cm, bottomMargin=2.0 * cm,
        title="アノテーション確認レポート（管理者用）",
        author="Javelin Video Analysis",
    )

    story: List[Any] = []

    # ── タイトル ──────────────────────────────────────────────────────────────
    story.append(Paragraph(
        f'<font name="{font_b}" size="16" color="{BRAND_BLUE}">アノテーション確認レポート</font>',
        styles["h1"],
    ))
    story.append(Paragraph(
        f'<font name="{font_r}" size="8" color="#CC4400">⚠️ このPDFは管理者・研究開発用資料です。外部への送付は行わないでください。</font>',
        styles["caption"],
    ))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f'<font name="{font_r}" size="9" color="{MID_GRAY}">'
        f'アノテーションID: {safe_text(annotation_id)} ／ 生成日時: {datetime.now().strftime("%Y-%m-%d %H:%M")}'
        f'</font>',
        styles["caption"],
    ))
    story.append(hr())
    story.append(section_spacer())

    # ── 基本情報 ──────────────────────────────────────────────────────────────
    story.append(Paragraph(
        f'<font name="{font_b}" size="13" color="{BRAND_BLUE}">基本情報</font>',
        styles["h2"],
    ))
    story.append(para_spacer())

    from src.annotation.manager import (
        ANNOTATION_STATUS_LABELS, CONSENT_TRAINING_LABELS, SNS_PERMISSION_LABELS,
    )

    status      = ann.get("annotation_status", "draft")
    consent     = ann.get("consent_for_training_data", "unknown")
    sns_perm    = ann.get("sns_permission", "unknown")

    basic_rows = [
        ("ジョブID",         ann.get("job_id", "—")),
        ("ステータス",       ANNOTATION_STATUS_LABELS.get(status, status)),
        ("アノテーター",     ann.get("annotator", "—")),
        ("作成日時",         ann.get("created_at", "—")),
        ("更新日時",         ann.get("updated_at", "—")),
        ("投げ腕",           ann.get("dominant_arm", "—")),
        ("FPS",              _fmt(ann.get("fps"), " fps")),
        ("総フレーム数",     _fmt(ann.get("total_frames"), " frames")),
        ("動画長",           _fmt(ann.get("duration_sec"), " 秒")),
        ("動画品質",         ann.get("video_quality_level", "—")),
        ("教師データ利用許可", CONSENT_TRAINING_LABELS.get(consent, consent)),
        ("SNS掲載許可",      SNS_PERMISSION_LABELS.get(sns_perm, sns_perm)),
    ]
    story.append(_kv_table(basic_rows, styles, font_b, font_r))
    story.append(section_spacer())

    # ── プライバシーフラグ ─────────────────────────────────────────────────────
    from src.annotation.manager import PRIVACY_FLAG_LABELS
    flags = ann.get("privacy_flags", [])
    story.append(Paragraph(
        f'<font name="{font_b}" size="13" color="{BRAND_BLUE}">プライバシーフラグ</font>',
        styles["h2"],
    ))
    story.append(para_spacer())
    if flags:
        for flag in flags:
            label = PRIVACY_FLAG_LABELS.get(flag, flag)
            color = "#CC4400" if flag in ("needs_anonymization", "training_data_excluded") else "#555555"
            story.append(Paragraph(
                f'<font name="{font_r}" size="9" color="{color}">⚑ {safe_text(label)}</font>',
                styles["body"],
            ))
    else:
        story.append(Paragraph(
            f'<font name="{font_r}" size="9" color="#888888">なし</font>',
            styles["caption"],
        ))
    story.append(section_spacer())

    # ── フェーズラベル ────────────────────────────────────────────────────────
    phase_labels = ann.get("phase_labels", {})
    story.append(Paragraph(
        f'<font name="{font_b}" size="13" color="{BRAND_BLUE}">フェーズラベル</font>',
        styles["h2"],
    ))
    story.append(para_spacer())

    _phase_jp = {
        "approach":       "助走",
        "cross_step":     "クロスステップ",
        "withdrawal":     "槍を引く",
        "block":          "ブロック",
        "release":        "リリース",
        "follow_through": "フォロースルー",
        "recovery":       "リカバリー",
    }

    from src.annotation.manager import LABEL_SOURCE_LABELS
    pl_header = [
        Paragraph(f'<font name="{font_b}" size="8">フェーズ</font>', styles["caption"]),
        Paragraph(f'<font name="{font_b}" size="8">フレーム</font>', styles["caption"]),
        Paragraph(f'<font name="{font_b}" size="8">ソース</font>', styles["caption"]),
        Paragraph(f'<font name="{font_b}" size="8">信頼度</font>', styles["caption"]),
        Paragraph(f'<font name="{font_b}" size="8">確認済</font>', styles["caption"]),
    ]
    pl_rows = [pl_header]
    for key, pl in phase_labels.items():
        jp = _phase_jp.get(key, key)
        if "start_frame" in pl:
            frame_str = f"{_fmt(pl.get('start_frame'))} - {_fmt(pl.get('end_frame'))}"
        else:
            frame_str = _fmt(pl.get("frame"))

        conf = pl.get("confidence")
        conf_str = f"{conf:.2f}" if conf is not None else "—"
        source_lbl = LABEL_SOURCE_LABELS.get(pl.get("source", "unknown"), pl.get("source", "—"))
        reviewed   = "✅" if pl.get("reviewed") else "—"
        pl_rows.append([
            Paragraph(f'<font name="{font_r}" size="8">{safe_text(jp)}</font>', styles["caption"]),
            Paragraph(f'<font name="{font_r}" size="8">{safe_text(frame_str)}</font>', styles["caption"]),
            Paragraph(f'<font name="{font_r}" size="8">{safe_text(source_lbl)}</font>', styles["caption"]),
            Paragraph(f'<font name="{font_r}" size="8">{safe_text(conf_str)}</font>', styles["caption"]),
            Paragraph(f'<font name="{font_r}" size="8">{reviewed}</font>', styles["caption"]),
        ])

    pl_table = Table(
        pl_rows,
        colWidths=[_CONTENT_W * 0.18, _CONTENT_W * 0.22, _CONTENT_W * 0.28, _CONTENT_W * 0.16, _CONTENT_W * 0.10],
    )
    pl_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#e8eaf6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(pl_table)
    story.append(section_spacer())

    # ── イベントラベル ────────────────────────────────────────────────────────
    event_labels = ann.get("event_labels", {})
    story.append(Paragraph(
        f'<font name="{font_b}" size="13" color="{BRAND_BLUE}">イベントラベル</font>',
        styles["h2"],
    ))
    story.append(para_spacer())

    _event_jp = {
        "release":       "リリース",
        "block_contact": "ブロック接地",
        "cross_start":   "クロス開始",
        "withdrawal_max": "最大引き",
        "follow_through_start": "フォロースルー開始",
    }

    ev_header = [
        Paragraph(f'<font name="{font_b}" size="8">イベント</font>', styles["caption"]),
        Paragraph(f'<font name="{font_b}" size="8">フレーム</font>', styles["caption"]),
        Paragraph(f'<font name="{font_b}" size="8">時刻(秒)</font>', styles["caption"]),
        Paragraph(f'<font name="{font_b}" size="8">ソース</font>', styles["caption"]),
        Paragraph(f'<font name="{font_b}" size="8">確認済</font>', styles["caption"]),
    ]
    ev_rows = [ev_header]
    for key, el in event_labels.items():
        jp       = _event_jp.get(key, key)
        source_lbl = LABEL_SOURCE_LABELS.get(el.get("source", "unknown"), el.get("source", "—"))
        reviewed = "✅" if el.get("reviewed") else "—"
        ev_rows.append([
            Paragraph(f'<font name="{font_r}" size="8">{safe_text(jp)}</font>', styles["caption"]),
            Paragraph(f'<font name="{font_r}" size="8">{_fmt(el.get("frame"))}</font>', styles["caption"]),
            Paragraph(f'<font name="{font_r}" size="8">{_fmt(el.get("time_sec"))}</font>', styles["caption"]),
            Paragraph(f'<font name="{font_r}" size="8">{safe_text(source_lbl)}</font>', styles["caption"]),
            Paragraph(f'<font name="{font_r}" size="8">{reviewed}</font>', styles["caption"]),
        ])

    ev_table = Table(
        ev_rows,
        colWidths=[_CONTENT_W * 0.22, _CONTENT_W * 0.18, _CONTENT_W * 0.18, _CONTENT_W * 0.28, _CONTENT_W * 0.10],
    )
    ev_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#e8eaf6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(ev_table)
    story.append(section_spacer())

    # ── 管理者メモ ────────────────────────────────────────────────────────────
    notes = ann.get("notes", "")
    if notes:
        story.append(Paragraph(
            f'<font name="{font_b}" size="13" color="{BRAND_BLUE}">管理者メモ</font>',
            styles["h2"],
        ))
        story.append(para_spacer())
        story.append(Paragraph(safe_text(notes), styles["body"]))
        story.append(section_spacer())

    # ── 免責事項 ──────────────────────────────────────────────────────────────
    story.append(disclaimer_block(
        "このアノテーションは競技動作の参考分析用データです。"
        "医療診断・怪我の診断・専門的な競技指導の代替ではありません。"
        "動画の撮影角度・画質によりラベル精度が変わります。"
        "アノテーションは完全な正解ではなく、人間による判断記録です。"
    ))

    doc.build(story, onFirstPage=make_header_footer, onLaterPages=make_header_footer)
    logger.info("[annotation_pdf] 生成完了: %s", output_path)
    return output_path


def generate_annotation_review_pdf_for_job(job_dir: Path) -> Optional[Path]:
    """
    ジョブに対応するアノテーションの確認 PDF を生成する。
    アノテーションが存在しない場合は None を返す。
    """
    from src.annotation.manager import find_annotation_for_job
    job_dir = Path(job_dir)
    ann = find_annotation_for_job(job_dir.name)
    if ann is None:
        return None
    try:
        return generate_annotation_review_pdf(ann["annotation_id"])
    except Exception as e:
        logger.warning("[annotation_pdf] 生成失敗: %s — %s", job_dir.name, e)
        return None
