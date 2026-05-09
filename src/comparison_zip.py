"""
src/comparison_zip.py — Javelin Video Analysis 比較パッケージ ZIP 生成

2動画比較ジョブの成果物を 1 つの ZIP にまとめる。

出力先: comparisons/<comparison_id>/comparison_package.zip

ZIP 内部構造:
  comparison_package/
  ├── 00_最初に読んでください/
  │   └── readme.txt          # 構成説明テキスト
  ├── 01_比較レポート/
  │   └── comparison_report.pdf
  ├── 02_フェーズ別比較画像/
  │   └── phase_<phase_key>_<stem>.jpg  (A / B 両方)
  ├── 03_グラフ/
  │   └── <graph_name>_A.png / <graph_name>_B.png
  ├── 04_フェーズ別サマリー/
  │   ├── phase_summary_A.pdf
  │   └── phase_summary_B.pdf
  └── 99_注意事項/
      └── disclaimer.txt

Usage:
    from src.comparison_zip import create_comparison_zip
    from pathlib import Path

    zip_path = create_comparison_zip(
        comparison_dir=Path("comparisons/20260510_012144_cmp"),
        job_dir_a=Path("jobs/20260508_054525_147f"),
        job_dir_b=Path("jobs/20260508_054854_fffe"),
        label_a="改善前",
        label_b="改善後",
    )
    # -> Path("comparisons/20260510_012144_cmp/comparison_package.zip")
"""

from __future__ import annotations

import logging
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("javelin.comparison_zip")

_DISCLAIMER_TEXT = """\
【注意事項】

このパッケージに含まれるレポート・画像・グラフは、動作の傾向を確認するための参考資料です。

1. 記載された数値・評価は解析ツールによる自動計算であり、誤差を含む場合があります。
2. このレポートは医療的アドバイス・コーチング指導の代替として使用しないでください。
3. 競技成績・けが防止の保証をするものではありません。
4. 第三者への無断転載・商用利用はお控えください。

ご不明な点はコーチや専門家にご相談ください。

--- Javelin Video Analysis ---
"""

_README_TEXT_TEMPLATE = """\
【比較パッケージ — 構成説明】

動画A: {label_a}
動画B: {label_b}
生成日時: {generated_at}

■ フォルダ構成

  01_比較レポート/
    comparison_report.pdf  ← 2動画の比較レポート（メインドキュメント）

  02_フェーズ別比較画像/
    各フェーズの代表フレームを A・B 並べて保存しています。
    ファイル名: phase_<フェーズ名>_<A または B>.jpg

  03_グラフ/
    動作の時系列グラフです。A・B それぞれを保存しています。

  04_フェーズ別サマリー/
    各動画のフェーズ別解析サマリー PDF です。

  99_注意事項/
    disclaimer.txt  ← 必ずお読みください

■ ご利用にあたって
このパッケージは参考資料です。医療的アドバイス・指導の代替として使用しないでください。

--- Javelin Video Analysis ---
"""


def _safe_name(name: str) -> str:
    """ファイル名に使えない文字を除去する。"""
    return "".join(c for c in name if c.isalnum() or c in "-_. ()").strip()


def create_comparison_zip(
    comparison_dir: Path,
    job_dir_a: Path,
    job_dir_b: Path,
    label_a: str = "動画A",
    label_b: str = "動画B",
) -> Path:
    """比較パッケージ ZIP を生成して返す。

    Parameters
    ----------
    comparison_dir : Path
        比較ジョブのルートディレクトリ（出力先も同じ）
    job_dir_a : Path
        比較元ジョブのルートディレクトリ
    job_dir_b : Path
        比較先ジョブのルートディレクトリ
    label_a : str
        動画 A の表示名
    label_b : str
        動画 B の表示名

    Returns
    -------
    Path
        生成された ZIP のパス
    """
    comparison_dir = Path(comparison_dir)
    job_dir_a = Path(job_dir_a)
    job_dir_b = Path(job_dir_b)
    comparison_dir.mkdir(parents=True, exist_ok=True)

    out_path = comparison_dir / "comparison_package.zip"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ZIP 内のルートフォルダ名
    zip_root = "comparison_package"

    with zipfile.ZipFile(str(out_path), "w", compression=zipfile.ZIP_DEFLATED) as zf:

        # ── 00_最初に読んでください ─────────────────────────────────────────
        readme_text = _README_TEXT_TEMPLATE.format(
            label_a=label_a,
            label_b=label_b,
            generated_at=generated_at,
        )
        zf.writestr(f"{zip_root}/00_最初に読んでください/readme.txt", readme_text)

        # ── 01_比較レポート ─────────────────────────────────────────────────
        report_pdf = comparison_dir / "comparison_report.pdf"
        if report_pdf.exists():
            zf.write(str(report_pdf), f"{zip_root}/01_比較レポート/comparison_report.pdf")
            logger.info("[comparison_zip] 比較レポート追加: comparison_report.pdf")
        else:
            logger.warning("[comparison_zip] 比較レポート PDF が見つかりません: %s", report_pdf)

        # ── 02_フェーズ別比較画像 ────────────────────────────────────────────
        phase_dir_a = job_dir_a / "report" / "phase_frames"
        phase_dir_b = job_dir_b / "report" / "phase_frames"

        added_phase_imgs = 0
        for phase_dir, side_label in [(phase_dir_a, "A"), (phase_dir_b, "B")]:
            if not phase_dir.exists():
                continue
            for img_path in sorted(phase_dir.glob("phase_*.jpg")):
                stem = img_path.stem  # e.g. "phase_block"
                arcname = f"{zip_root}/02_フェーズ別比較画像/{stem}_{side_label}.jpg"
                zf.write(str(img_path), arcname)
                added_phase_imgs += 1
        if added_phase_imgs > 0:
            logger.info("[comparison_zip] フェーズ別比較画像 %d 件追加", added_phase_imgs)
        else:
            logger.info("[comparison_zip] フェーズ別比較画像なし")

        # ── 03_グラフ ─────────────────────────────────────────────────────
        graphs_dir_a = job_dir_a / "report" / "graphs"
        graphs_dir_b = job_dir_b / "report" / "graphs"

        added_graphs = 0
        for graphs_dir, side_label in [(graphs_dir_a, "A"), (graphs_dir_b, "B")]:
            if not graphs_dir.exists():
                continue
            for graph_path in sorted(graphs_dir.glob("*.png")):
                arcname = f"{zip_root}/03_グラフ/{graph_path.stem}_{side_label}.png"
                zf.write(str(graph_path), arcname)
                added_graphs += 1
        if added_graphs > 0:
            logger.info("[comparison_zip] グラフ %d 件追加", added_graphs)

        # ── 04_フェーズ別サマリー ────────────────────────────────────────────
        for job_dir, side_label in [(job_dir_a, "A"), (job_dir_b, "B")]:
            ps_pdf = job_dir / "report" / "phase_summary.pdf"
            if ps_pdf.exists():
                arcname = f"{zip_root}/04_フェーズ別サマリー/phase_summary_{side_label}.pdf"
                zf.write(str(ps_pdf), arcname)
                logger.info("[comparison_zip] フェーズ別サマリー追加: phase_summary_%s.pdf", side_label)

        # ── 99_注意事項 ──────────────────────────────────────────────────────
        zf.writestr(f"{zip_root}/99_注意事項/disclaimer.txt", _DISCLAIMER_TEXT)

    logger.info("[comparison_zip] ZIP 生成完了: %s", out_path)
    return out_path
