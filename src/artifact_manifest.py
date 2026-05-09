"""
src/artifact_manifest.py — Javelin Video Analysis 成果物マニフェスト生成

ジョブディレクトリ内の成果物を自動検出し、S3キー・Content-Type・カテゴリ情報と合わせて
artifact_manifest.json に保存する。

出力先: job_dir/artifact_manifest.json

Usage:
    from src.artifact_manifest import build_artifact_manifest, save_artifact_manifest
    from pathlib import Path

    manifest = build_artifact_manifest(
        job_dir=Path("jobs/20260508_054525_147f"),
        job_id="20260508_054525_147f",
    )
    save_artifact_manifest(Path("jobs/20260508_054525_147f"), manifest)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.storage.s3_storage import build_s3_key_for_job, infer_content_type

logger = logging.getLogger("javelin.artifact_manifest")

# ── カテゴリ定義（表示順） ────────────────────────────────────────────────────

_CATEGORY_ORDER = [
    "最初に読む資料",
    "解析動画",
    "選手向け資料",
    "フェーズ別資料",
    "グラフ",
    "代表フレーム画像",
    "比較資料",
    "研究・開発用データ",
    "納品ZIP",
]


def _entry(
    category: str,
    label: str,
    local_path: Path,
    job_dir: Path,
    job_id: str,
    s3_subdir: str,
    required: bool = False,
    content_type: Optional[str] = None,
) -> dict:
    """成果物エントリを生成する。"""
    exists = local_path.exists() and local_path.is_file()
    # ローカルパスは常に相対表現で持つ
    try:
        rel_path = local_path.relative_to(job_dir).as_posix()
    except ValueError:
        rel_path = str(local_path)

    s3_key = build_s3_key_for_job(job_id, f"{s3_subdir}/{local_path.name}")
    ct = content_type or infer_content_type(local_path)

    return {
        "category":     category,
        "label":        label,
        "local_path":   rel_path,
        "s3_key":       s3_key,
        "content_type": ct,
        "required":     required,
        "exists":       exists,
        "size_bytes":   local_path.stat().st_size if exists else None,
    }


def build_artifact_manifest(
    job_dir: Path,
    job_id: str,
) -> dict:
    """ジョブディレクトリの成果物を自動検出してマニフェストを構築する。

    Parameters
    ----------
    job_dir : Path
        ジョブのルートディレクトリ
    job_id : str
        ジョブID

    Returns
    -------
    dict
        artifact_manifest.json に保存する内容
    """
    job_dir = Path(job_dir)
    artifacts: list[dict] = []

    def add(category, label, path, s3_subdir, required=False, content_type=None):
        artifacts.append(_entry(category, label, path, job_dir, job_id, s3_subdir,
                                required=required, content_type=content_type))

    # ── 最初に読む資料 ─────────────────────────────────────────────────────────
    add("最初に読む資料", "最初に読んでください",
        job_dir / "report" / "00_最初に読んでください.pdf", "docs", required=True)
    add("最初に読む資料", "解析動画の見方（説明書）",
        job_dir / "report" / "video_instruction.pdf", "docs")
    # output/ 直下に出力される場合もある（旧形式）
    if not (job_dir / "report" / "video_instruction.pdf").exists():
        _old_instr = job_dir / "output" / "説明書.pdf"
        if _old_instr.exists():
            add("最初に読む資料", "解析動画の見方（説明書）", _old_instr, "docs")
    # HTML形式の説明書（旧形式）
    _instr_html = job_dir / "output" / "説明書.html"
    if _instr_html.exists():
        add("最初に読む資料", "解析動画の見方（HTML版）", _instr_html, "docs")

    # ── 解析動画 ────────────────────────────────────────────────────────────────
    output_dir = job_dir / "output"
    if output_dir.exists():
        for mp4 in sorted(output_dir.glob("*.mp4")):
            _label = _mp4_label(mp4.stem)
            add("解析動画", _label, mp4, "videos")

    # ── 選手向け資料 ────────────────────────────────────────────────────────────
    report_dir = job_dir / "report"
    _report_pdfs = {
        "report.pdf":               "解析レポート（メインPDF）",
        "athlete_data_sheet.pdf":   "選手向けデータシート",
        "key_frame_sheet.pdf":      "代表フレームシート",
        "graph_pack.pdf":           "グラフ解説PDF",
        "coach_review_sheet.pdf":   "コーチ向けレビューシート",
        "analysis_summary.pdf":     "解析サマリーPDF",
    }
    for fn, label in _report_pdfs.items():
        p = report_dir / fn
        if p.exists():
            add("選手向け資料", label, p, "reports")

    # ── フェーズ別資料 (Phase 4) ─────────────────────────────────────────────
    _phase_summary = report_dir / "phase_summary.pdf"
    if _phase_summary.exists():
        add("フェーズ別資料", "フェーズ別解析サマリーPDF", _phase_summary, "reports")

    _phase_frames_dir = report_dir / "phase_frames"
    if _phase_frames_dir.exists():
        for img in sorted(_phase_frames_dir.glob("phase_*.jpg")):
            _phase_label = _phase_img_label(img.stem)
            add("フェーズ別資料", _phase_label, img, "phase_frames")

    # ── グラフ ──────────────────────────────────────────────────────────────────
    graphs_dir = report_dir / "graphs"
    if graphs_dir.exists():
        for g in sorted(graphs_dir.glob("*.png")):
            add("グラフ", g.stem, g, "graphs")
        for g in sorted(graphs_dir.glob("*.pdf")):
            add("グラフ", g.stem, g, "graphs")

    # ── 代表フレーム画像 ─────────────────────────────────────────────────────
    frames_dir = report_dir / "frames"
    if frames_dir.exists():
        for img in sorted(frames_dir.glob("*.jpg")):
            add("代表フレーム画像", img.stem, img, "frames")
    # output/frames/ (旧形式)
    old_frames = output_dir / "frames" if output_dir.exists() else None
    if old_frames and old_frames.exists():
        for img in sorted(old_frames.glob("*.jpg")):
            add("代表フレーム画像", img.stem, img, "frames")

    # ── 研究・開発用データ ───────────────────────────────────────────────────
    _data_patterns = [
        (report_dir / "pose_landmarks.csv",  "姿勢推定データ CSV"),
        (report_dir / "analysis_summary.json", "解析サマリー JSON"),
    ]
    if output_dir.exists():
        for _csv in sorted(output_dir.glob("*.csv")):
            _data_patterns.append((_csv, f"{_csv.stem} (CSV)"))
        for _jrpt in sorted(output_dir.glob("*_report.json")):
            _data_patterns.append((_jrpt, f"{_jrpt.stem} (JSON)"))

    _seen_data: set[Path] = set()
    for path, label in _data_patterns:
        if path.exists() and path not in _seen_data:
            add("研究・開発用データ", label, path, "data")
            _seen_data.add(path)

    # ── 納品ZIP ──────────────────────────────────────────────────────────────
    deliverables_dir = job_dir / "deliverables"
    if deliverables_dir.exists():
        _zip_labels = {
            "free_preview.zip":          "無料プレビュー版 ZIP",
            "data_sheet_package.zip":    "データシート版 ZIP",
            "full_report_package.zip":   "フルレポート版 ZIP",
        }
        for fn, label in _zip_labels.items():
            p = deliverables_dir / fn
            if p.exists():
                add("納品ZIP", label, p, "zip", required=True)
        # その他の ZIP
        for z in sorted(deliverables_dir.glob("*.zip")):
            if z.name not in _zip_labels:
                add("納品ZIP", f"{z.stem} ZIP", z, "zip")

    # ── 納品ページ HTML (Phase 5) ────────────────────────────────────────────
    _html_page = report_dir / "delivery_page.html"
    if _html_page.exists():
        artifacts.append(_entry(
            "納品ページ", "納品ページ HTML",
            _html_page, job_dir, job_id, "delivery",
            required=True, content_type="text/html",
        ))

    # ── 重複除去（同じ local_path が入った場合） ─────────────────────────────
    seen_paths: set[str] = set()
    deduped: list[dict] = []
    for a in artifacts:
        if a["local_path"] not in seen_paths:
            deduped.append(a)
            seen_paths.add(a["local_path"])

    # ── カテゴリ順にソート ────────────────────────────────────────────────────
    def _sort_key(a):
        cat = a["category"]
        idx = _CATEGORY_ORDER.index(cat) if cat in _CATEGORY_ORDER else len(_CATEGORY_ORDER)
        return (idx, a["label"])

    deduped.sort(key=_sort_key)

    exists_count = sum(1 for a in deduped if a["exists"])
    missing_count = len(deduped) - exists_count

    return {
        "job_id":           job_id,
        "generated_at":     datetime.now().isoformat(timespec="seconds"),
        "total_count":      len(deduped),
        "exists_count":     exists_count,
        "missing_count":    missing_count,
        "artifacts":        deduped,
    }


def build_comparison_artifact_manifest(
    comparison_dir: Path,
    comparison_id: str,
    job_dir_a: Optional[Path] = None,
    job_dir_b: Optional[Path] = None,
    label_a: str = "動画A",
    label_b: str = "動画B",
) -> dict:
    """比較ジョブの成果物マニフェストを構築する。

    Parameters
    ----------
    comparison_dir : Path
        比較ジョブのルートディレクトリ
    comparison_id : str
        比較ジョブID
    """
    from src.storage.s3_storage import build_s3_key_for_comparison

    comparison_dir = Path(comparison_dir)
    artifacts: list[dict] = []

    def add_cmp(category, label, path, subdir, required=False):
        if not path.is_absolute():
            path = comparison_dir / path
        exists = path.exists() and path.is_file()
        try:
            rel = path.relative_to(comparison_dir).as_posix()
        except ValueError:
            rel = str(path)
        s3_key = build_s3_key_for_comparison(comparison_id, f"{subdir}/{path.name}")
        artifacts.append({
            "category":     category,
            "label":        label,
            "local_path":   rel,
            "s3_key":       s3_key,
            "content_type": infer_content_type(path),
            "required":     required,
            "exists":       exists,
            "size_bytes":   path.stat().st_size if exists else None,
        })

    # 比較レポート PDF
    add_cmp("比較資料", "2動画比較レポート PDF",
            comparison_dir / "comparison_report.pdf", "reports", required=True)

    # 比較パッケージ ZIP
    add_cmp("納品ZIP", "比較パッケージ ZIP",
            comparison_dir / "comparison_package.zip", "zip", required=True)

    # 比較サマリー JSON (開発用)
    csjson = comparison_dir / "comparison_summary.json"
    if csjson.exists():
        add_cmp("研究・開発用データ", "比較サマリー JSON", csjson, "data")

    # フェーズ別比較画像（Job A/B のフェーズ画像を別途参照）
    if job_dir_a:
        pf_dir_a = Path(job_dir_a) / "report" / "phase_frames"
        if pf_dir_a.exists():
            for img in sorted(pf_dir_a.glob("phase_*.jpg")):
                s3_key = build_s3_key_for_comparison(comparison_id, f"images/{img.stem}_{label_a}.jpg")
                artifacts.append({
                    "category":     "比較画像",
                    "label":        f"{img.stem} ({label_a})",
                    "local_path":   str(img),
                    "s3_key":       s3_key,
                    "content_type": "image/jpeg",
                    "required":     False,
                    "exists":       True,
                    "size_bytes":   img.stat().st_size,
                })
    if job_dir_b:
        pf_dir_b = Path(job_dir_b) / "report" / "phase_frames"
        if pf_dir_b.exists():
            for img in sorted(pf_dir_b.glob("phase_*.jpg")):
                s3_key = build_s3_key_for_comparison(comparison_id, f"images/{img.stem}_{label_b}.jpg")
                artifacts.append({
                    "category":     "比較画像",
                    "label":        f"{img.stem} ({label_b})",
                    "local_path":   str(img),
                    "s3_key":       s3_key,
                    "content_type": "image/jpeg",
                    "required":     False,
                    "exists":       True,
                    "size_bytes":   img.stat().st_size,
                })

    # 納品ページ HTML
    html_page = comparison_dir / "delivery_page.html"
    if html_page.exists():
        s3_key = build_s3_key_for_comparison(comparison_id, "delivery/delivery_page.html")
        artifacts.append({
            "category":     "納品ページ",
            "label":        "比較ジョブ納品ページ HTML",
            "local_path":   "delivery_page.html",
            "s3_key":       s3_key,
            "content_type": "text/html",
            "required":     True,
            "exists":       True,
            "size_bytes":   html_page.stat().st_size,
        })

    exists_count = sum(1 for a in artifacts if a.get("exists"))
    return {
        "comparison_id":  comparison_id,
        "generated_at":   datetime.now().isoformat(timespec="seconds"),
        "total_count":    len(artifacts),
        "exists_count":   exists_count,
        "missing_count":  len(artifacts) - exists_count,
        "artifacts":      artifacts,
    }


def save_artifact_manifest(job_dir: Path, manifest: dict) -> Path:
    """artifact_manifest.json を保存する。"""
    job_dir = Path(job_dir)
    out = job_dir / "artifact_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[artifact_manifest] 保存: %s (%d 件)", out.name, manifest.get("total_count", 0))
    return out


def load_artifact_manifest(job_dir: Path) -> Optional[dict]:
    """artifact_manifest.json を読み込む。存在しない場合は None を返す。"""
    p = Path(job_dir) / "artifact_manifest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[artifact_manifest] 読み込み失敗: %s", e)
        return None


# ── 内部ヘルパー ─────────────────────────────────────────────────────────────

def _mp4_label(stem: str) -> str:
    """MP4 ファイルのステムから表示ラベルを生成する。"""
    _map = {
        "skeleton":   "骨格線つき動画",
        "heatmap":    "ヒートマップ動画",
        "hud":        "ゲーム風HUD動画",
        "stickman":   "スティックマン動画",
        "vectors":    "ベクトル動画",
        "analysis":   "コーチング解析動画",
        "trail":      "軌跡動画",
    }
    for kw, label in _map.items():
        if kw in stem.lower():
            return label
    return stem


def _phase_img_label(stem: str) -> str:
    """フェーズ画像ファイルのステムから表示ラベルを生成する。"""
    _phase_names = {
        "approach":      "助走",
        "cross_step":    "クロスステップ",
        "withdrawal":    "槍を引く局面",
        "block":         "ブロック",
        "release":       "リリース",
        "follow_through": "フォロースルー",
        "recovery":      "リカバリー",
    }
    parts = stem.replace("phase_", "").split("_")
    for i in range(len(parts), 0, -1):
        key = "_".join(parts[:i])
        if key in _phase_names:
            suffix = "_".join(parts[i:])
            suffix_label = {"start": "（開始）", "end": "（終了）"}.get(suffix, "")
            return f"{_phase_names[key]}{suffix_label}"
    return stem
