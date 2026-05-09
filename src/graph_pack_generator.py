"""
graph_pack_generator.py — グラフパック PDF 生成 (pdf_styles 統合版)

report/graphs/ 配下のグラフ PNG を1冊の PDF にまとめ、
各グラフに日本語タイトル・解説文・チェックポイントを付ける。
フォント・ヘッダー/フッターは src.pdf_styles に委譲。

Usage:
    from src.graph_pack_generator import generate_graph_pack_for_job
    pdf_path = generate_graph_pack_for_job(Path("jobs/20260510_012144_0513"))
    # -> Path("jobs/20260510_012144_0513/report/graph_pack.pdf")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, PageBreak, SimpleDocTemplate, Spacer

from src.pdf_styles import (
    BODY_BOT_MARGIN,
    BODY_TOP_MARGIN,
    CONTENT_W,
    MARGIN_H,
    disclaimer_block,
    get_styles,
    graph_section,
    make_header_footer,
    safe_text,
    title_block,
)

logger = logging.getLogger(__name__)

_PDF_LABEL = "解析グラフ解説"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_story(job_dir: Path) -> list:
    styles = get_styles("GP_")
    story: list = []

    report_dir = job_dir / "report"
    graphs_dir = report_dir / "graphs"

    job = _load_json(job_dir / "job.json")
    ci  = _load_json(job_dir / "customer_info.json")
    job_id  = job.get("job_id", "—")
    name    = ci.get("customer_name") or "—"
    gen_at  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    info_line = f"Job ID: {job_id}  |  {name}  |  出力日: {gen_at}"
    story += title_block(_PDF_LABEL, "Graph Pack — Javelin Video Analysis",
                         info_line, styles)

    # グラフファイル収集
    graph_files: list[Path] = []
    if graphs_dir.exists():
        graph_files = sorted(
            list(graphs_dir.glob("*.png")) + list(graphs_dir.glob("*.jpg"))
        )

    if not graph_files:
        from reportlab.platypus import Paragraph
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph(
            safe_text("グラフ画像が見つかりませんでした。解析を実行してください。"),
            styles["missing"]))
    else:
        for i, gp in enumerate(graph_files):
            if i > 0:
                story.append(PageBreak())
            block = graph_section(gp, styles,
                                  max_img_w=CONTENT_W,
                                  max_img_h=10.5 * cm)
            try:
                story.append(KeepTogether(block))
            except Exception:
                story += block
            story.append(Spacer(1, 0.4 * cm))

    story += disclaimer_block(styles)
    return story


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

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN_H,
        rightMargin=MARGIN_H,
        topMargin=BODY_TOP_MARGIN,
        bottomMargin=BODY_BOT_MARGIN,
        title=f"{_PDF_LABEL} — やり投げ動作解析",
        author="やり投げ動作解析システム",
    )
    hf = make_header_footer(_PDF_LABEL)
    doc.build(_build_story(job_dir), onFirstPage=hf, onLaterPages=hf)
    logger.info("[graph_pack] PDF 生成完了: %s", out_path)
    return out_path
