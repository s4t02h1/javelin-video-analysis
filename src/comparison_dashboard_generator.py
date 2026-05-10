"""
src/comparison_dashboard_generator.py — Phase 13: 比較ダッシュボードHTML生成

2ジョブの比較結果を1ファイルHTMLとして生成する。

⚠️ 方針
    - 比較結果は「傾向」として表示し、断定しない
    - 撮影条件の違いによる誤差に言及する
    - 医療診断・専門的競技指導の代替ではないことを明示する

Usage:
    from src.comparison_dashboard_generator import generate_comparison_dashboard_for_jobs
    from pathlib import Path

    path = generate_comparison_dashboard_for_jobs(
        job_a_dir=Path("jobs/20260508_070156_518a"),
        job_b_dir=Path("jobs/20260508_081953_329a"),
        job_a_label="5月8日 試技1",
        job_b_label="5月8日 試技2",
    )
    # → jobs/20260508_070156_518a/report/comparison_dashboard.html
"""
from __future__ import annotations

import base64
import html as _html_escape
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.comparison_dashboard")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE_DIR = _REPO_ROOT / "templates"

_REL_BADGE = {
    "high":    '<span class="badge badge-high">🟢 高</span>',
    "medium":  '<span class="badge badge-medium">🟡 中</span>',
    "low":     '<span class="badge badge-low">🔴 低</span>',
    "unknown": '<span class="badge badge-unknown">⚪ 不明</span>',
}

_PHASE_LABELS = {
    "approach": "🏃 助走",
    "crossstep": "↗️ クロスステップ",
    "withdrawal": "↩️ 槍引き",
    "block": "🛑 ブロック",
    "release": "🎯 リリース",
    "follow_through": "🌀 フォロースルー",
    "recovery": "🔄 リカバリー",
}

_COMPARISON_KEY_LABELS = {
    "release_wrist_height_normalized":        "リリース時の手首高さ（相対）",
    "release_wrist_velocity_normalized":       "リリース時の手首速度（相対）",
    "release_arm_extension_ratio":             "リリース時の腕伸展率",
    "release_trunk_angle_estimate":            "リリース時の体幹前傾（2D推定）",
    "release_shoulder_line_tilt":              "リリース時の肩ライン傾き（2D推定）",
    "block_to_release_time_sec":               "ブロック〜リリースの時間",
    "hip_deceleration_ratio":                  "ブロック前後の腰中心減速比",
    "shoulder_rotation_change_around_block":   "ブロック〜リリース間の肩回旋変化（2D推定）",
    "hip_rotation_change_around_block":        "ブロック〜リリース間の腰回旋変化（2D推定）",
    "shoulder_hip_separation_angle_estimate":  "肩腰分離の推定角度（2D推定）",
    "trunk_opening_at_release":                "体幹前傾変化量（2D推定）",
    "throwing_wrist_peak_velocity":            "投げ腕の手首最大速度（相対）",
    "arm_pullback_distance_estimate":          "槍引き距離推定（相対）",
    "withdrawal_to_release_time_sec":          "槍引き〜リリースの時間",
}


def _e(text: Any) -> str:
    return _html_escape.escape(str(text) if text is not None else "")


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_config() -> Dict[str, Any]:
    cfg_path = _REPO_ROOT / "configs" / "dashboard.yaml"
    try:
        import yaml  # type: ignore[import-not-found]
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _load_template(name: str) -> str:
    path = _TEMPLATE_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"テンプレートが見つかりません: {path}")


def _fmt_val(v: Any) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        if abs(f - round(f)) < 0.001:
            return str(int(round(f)))
        return f"{f:.3f}"
    except (TypeError, ValueError):
        return _e(v)


def _fmt_expires(iso: str) -> str:
    if not iso:
        return "不明"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y年%m月%d日 %H:%M")
    except Exception:
        return _e(iso)


def _build_ab_info_section(
    job_a_data: Dict[str, Any], job_b_data: Dict[str, Any],
    label_a: str, label_b: str,
    job_a_id: str, job_b_id: str,
) -> str:
    return f"""
<div class="card" id="ab-info">
  <h2>📋 比較対象</h2>
  <div class="ab-grid">
    <div class="ab-col col-a">
      <h3>🅰 {_e(label_a)}</h3>
      <p style="font-size:.85rem;color:#555">ジョブID: <code>{_e(job_a_id)}</code></p>
      <p style="font-size:.85rem">作成日: {_e(job_a_data.get('created_at', '—'))}</p>
    </div>
    <div class="ab-col col-b">
      <h3>🅱 {_e(label_b)}</h3>
      <p style="font-size:.85rem;color:#555">ジョブID: <code>{_e(job_b_id)}</code></p>
      <p style="font-size:.85rem">作成日: {_e(job_b_data.get('created_at', '—'))}</p>
    </div>
  </div>
</div>"""


def _build_ab_video_section(
    job_a_dir: Path, job_b_dir: Path,
    label_a: str, label_b: str,
    presigned_urls_a: Optional[Dict[str, str]],
    presigned_urls_b: Optional[Dict[str, str]],
) -> str:
    def _find_mp4(job_dir: Path, keyword: str) -> Optional[Path]:
        out = job_dir / "output"
        if not out.exists():
            return None
        files = list(out.glob(f"*{keyword}*.mp4"))
        return files[0] if files else None

    def _video_item(job_dir: Path, label: str, keyword: str,
                    col_class: str, presigned: Optional[Dict[str, str]]) -> str:
        mp4 = _find_mp4(job_dir, keyword)
        url = None
        if presigned:
            for k, u in presigned.items():
                if keyword in k.lower() and k.endswith(".mp4"):
                    url = u
                    break
        if mp4 and url:
            return (
                f'<div class="ab-col {col_class}">'
                f'<h3>{_e(label)}</h3>'
                f'<video controls preload="metadata" playsinline style="width:100%;border-radius:6px">'
                f'<source src="{_e(url)}" type="video/mp4">動画再生非対応</video>'
                f'</div>'
            )
        elif mp4:
            rel = f"../output/{mp4.name}"
            return (
                f'<div class="ab-col {col_class}">'
                f'<h3>{_e(label)}</h3>'
                f'<video controls preload="metadata" playsinline style="width:100%;border-radius:6px">'
                f'<source src="{_e(rel)}" type="video/mp4">動画再生非対応</video>'
                f'</div>'
            )
        else:
            return (
                f'<div class="ab-col {col_class}">'
                f'<h3>{_e(label)}</h3>'
                f'<p style="color:#999;font-size:.85rem">動画ファイルがありません</p>'
                f'</div>'
            )

    a_html = _video_item(job_a_dir, f"🅰 {label_a}", "skeleton", "col-a", presigned_urls_a)
    b_html = _video_item(job_b_dir, f"🅱 {label_b}", "skeleton", "col-b", presigned_urls_b)

    return f"""
<div class="card" id="ab-videos">
  <h2>🎬 解析動画の比較</h2>
  <p style="font-size:.85rem;color:#555;margin-bottom:10px">
    骨格線は推定値です。撮影角度・距離が異なる場合、比較精度が低下します。
  </p>
  <div class="ab-grid">
    {a_html}
    {b_html}
  </div>
</div>"""


def _build_ab_phase_images_section(
    job_a_dir: Path, job_b_dir: Path,
    label_a: str, label_b: str,
) -> str:
    items_html: List[str] = []

    for phase_key, phase_label in _PHASE_LABELS.items():
        def _find_img(job_dir: Path) -> Optional[str]:
            frames_dir = job_dir / "report" / "frames"
            if not frames_dir.exists():
                return None
            for ext in ["png", "jpg", "jpeg"]:
                imgs = list(frames_dir.glob(f"*{phase_key}*.{ext}"))
                if imgs:
                    try:
                        suffix = imgs[0].suffix.lower()
                        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(suffix, "image/jpeg")
                        data = base64.b64encode(imgs[0].read_bytes()).decode("ascii")
                        return f"data:{mime};base64,{data}"
                    except Exception:
                        return None
            return None

        img_a = _find_img(job_a_dir)
        img_b = _find_img(job_b_dir)

        a_content = (
            f'<img src="{img_a}" alt="{_e(phase_label)}" loading="lazy" style="width:100%">'
            if img_a else '<div class="phase-missing">画像なし</div>'
        )
        b_content = (
            f'<img src="{img_b}" alt="{_e(phase_label)}" loading="lazy" style="width:100%">'
            if img_b else '<div class="phase-missing">画像なし</div>'
        )

        items_html.append(
            f'<div style="margin-bottom:20px">'
            f'<p style="font-weight:600;margin-bottom:6px">{_e(phase_label)}</p>'
            f'<div class="ab-grid">'
            f'<div class="ab-col col-a"><p style="font-size:.82rem;margin-bottom:4px">🅰 {_e(label_a)}</p>{a_content}</div>'
            f'<div class="ab-col col-b"><p style="font-size:.82rem;margin-bottom:4px">🅱 {_e(label_b)}</p>{b_content}</div>'
            f'</div></div>'
        )

    if not items_html:
        return ""

    return f"""
<div class="card" id="ab-phases">
  <h2>🖼️ フェーズ別画像比較</h2>
  <p style="font-size:.85rem;color:#555;margin-bottom:10px">
    各フェーズの代表フレームをA/B並べて比較します。画像がない場合は「画像なし」と表示されます。
  </p>
  {"".join(items_html)}
</div>"""


def _build_ab_metrics_section(
    comparison_data: Optional[Dict[str, Any]],
    label_a: str, label_b: str,
    cfg: Dict[str, Any],
) -> str:
    """比較指標セクションのHTMLを生成する。"""
    if not comparison_data:
        return """
<div class="card" id="ab-metrics">
  <h2>📊 指標比較（参考）</h2>
  <p style="color:#888;font-size:.9rem">比較指標データがありません。</p>
</div>"""

    comparisons: List[Dict[str, Any]] = comparison_data.get("comparisons", [])
    if not comparisons:
        return """
<div class="card" id="ab-metrics">
  <h2>📊 指標比較（参考）</h2>
  <p style="color:#888;font-size:.9rem">比較指標がありません。</p>
</div>"""

    notable_threshold = cfg.get("comparison", {}).get("notable_change_display_threshold_percent", 10.0)

    rows_html: List[str] = []
    for comp in comparisons:
        key = comp.get("key", "")
        label = _COMPARISON_KEY_LABELS.get(key, key)
        val_a = _fmt_val(comp.get("value_a"))
        val_b = _fmt_val(comp.get("value_b"))
        delta = comp.get("delta")
        delta_pct = comp.get("delta_percent")
        rel_a = comp.get("reliability_a", "unknown")
        rel_b = comp.get("reliability_b", "unknown")
        interp = comp.get("interpretation", "")
        notable = False
        if delta_pct is not None:
            try:
                notable = abs(float(delta_pct)) >= notable_threshold
            except Exception:
                pass

        notable_badge = '<span class="badge-notable">差あり</span>' if notable else ""
        delta_str = _fmt_val(delta)
        delta_pct_str = f"({delta_pct:+.1f}%)" if delta_pct is not None else ""

        rows_html.append(
            f'<div class="metric-diff">'
            f'<span class="d-label">{_e(label)}</span> {notable_badge}<br>'
            f'<span class="d-val-a">🅰 {_e(val_a)}</span> &nbsp;→&nbsp; '
            f'<span class="d-val-b">🅱 {_e(val_b)}</span>'
            f'<div class="d-delta">差: {_e(delta_str)} {_e(delta_pct_str)} &nbsp; '
            f'信頼度A:{_REL_BADGE.get(rel_a, "")} B:{_REL_BADGE.get(rel_b, "")}</div>'
            f'{"<div class=d-interp>" + _e(interp) + "</div>" if interp else ""}'
            f'</div>'
        )

    inner = "\n".join(rows_html)

    return f"""
<div class="card" id="ab-metrics">
  <h2>📊 指標比較（参考）</h2>
  <div class="alert alert-warning" style="font-size:.85rem">
    以下の差異はすべて <strong>参考値の比較</strong> です。どちらが優れているかを断定するものではありません。
    撮影条件・姿勢推定精度の違いにより差が生じることがあります。
  </div>
  {inner}
</div>"""


def _build_ab_downloads_section(
    job_a_dir: Path,
    presigned_urls_a: Optional[Dict[str, str]],
) -> str:
    """比較ダッシュボード用ダウンロードセクション。"""
    def _link(rel_path: str, label: str, presigned: Optional[Dict[str, str]], keyword: str) -> str:
        full = job_a_dir / rel_path
        url = None
        if presigned:
            for k, u in presigned.items():
                if keyword in k:
                    url = u
                    break
        if full.exists() or url:
            href = url or rel_path
            return (
                f'<div class="dl-item">'
                f'<span class="dl-icon">📄</span>'
                f'<a class="btn btn-dl" href="{_e(href)}" target="_blank" rel="noopener noreferrer">{_e(label)}</a>'
                f'</div>'
            )
        return (
            f'<div class="dl-item">'
            f'<span class="dl-icon">📄</span>'
            f'<span class="dl-label">{_e(label)}</span>'
            f'<span class="dl-unavailable">（未生成）</span>'
            f'</div>'
        )

    return f"""
<div class="card" id="ab-downloads">
  <h2>📥 ダウンロード</h2>
  {_link("report/comparison_advanced_report.pdf", "比較高度指標レポート.pdf", presigned_urls_a, "comparison_advanced")}
  {_link("report/comparison_report.pdf", "比較レポート.pdf", presigned_urls_a, "comparison_report")}
  {_link("report/comparison_advanced_metrics.json", "比較指標データ JSON（開発用）", presigned_urls_a, "comparison_advanced_metrics")}
</div>"""


# ── メイン生成関数 ────────────────────────────────────────────────────────────

def generate_comparison_dashboard(
    job_a_dir: Path,
    job_b_dir: Path,
    job_a_label: str = "動画A",
    job_b_label: str = "動画B",
    comparison_id: str = "",
    presigned_urls_a: Optional[Dict[str, str]] = None,
    presigned_urls_b: Optional[Dict[str, str]] = None,
    url_expires_at: str = "",
) -> str:
    """比較ダッシュボードHTMLを生成して返す（保存はしない）。"""
    job_a_dir = Path(job_a_dir)
    job_b_dir = Path(job_b_dir)
    cfg = _load_config()

    job_a_data = _load_json(job_a_dir / "job.json") or {}
    job_b_data = _load_json(job_b_dir / "job.json") or {}

    job_a_id = job_a_data.get("job_id", job_a_dir.name)
    job_b_id = job_b_data.get("job_id", job_b_dir.name)

    if not comparison_id:
        comparison_id = f"{job_a_id}_vs_{job_b_id}"

    # comparison_advanced_metrics.json を探す
    comparison_data = (
        _load_json(job_a_dir / "report" / "comparison_advanced_metrics.json")
        or _load_json(job_a_dir / "comparison_advanced_metrics.json")
    )

    # セクション生成
    ab_info = _build_ab_info_section(job_a_data, job_b_data, job_a_label, job_b_label, job_a_id, job_b_id)
    ab_videos = _build_ab_video_section(job_a_dir, job_b_dir, job_a_label, job_b_label, presigned_urls_a, presigned_urls_b)
    ab_phases = _build_ab_phase_images_section(job_a_dir, job_b_dir, job_a_label, job_b_label)
    ab_metrics = _build_ab_metrics_section(comparison_data, job_a_label, job_b_label, cfg)
    ab_downloads = _build_ab_downloads_section(job_a_dir, presigned_urls_a)

    title = f"比較ダッシュボード — {job_a_label} vs {job_b_label}"
    generated_at = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    template = _load_template("comparison_dashboard.html")
    html = template
    html = html.replace("{{ title }}", _e(title))
    html = html.replace("{{ label_a }}", _e(job_a_label))
    html = html.replace("{{ label_b }}", _e(job_b_label))
    html = html.replace("{{ comparison_id }}", _e(comparison_id))
    html = html.replace("{{ job_a_id }}", _e(job_a_id))
    html = html.replace("{{ job_b_id }}", _e(job_b_id))
    html = html.replace("{{ generated_at }}", _e(generated_at))
    html = html.replace("{{ url_expires_at_display }}", _e(_fmt_expires(url_expires_at)))
    html = html.replace("{{ ab_info_section }}", ab_info)
    html = html.replace("{{ ab_video_section }}", ab_videos)
    html = html.replace("{{ ab_phase_images_section }}", ab_phases)
    html = html.replace("{{ ab_metrics_section }}", ab_metrics)
    html = html.replace("{{ ab_downloads_section }}", ab_downloads)

    return html


def generate_comparison_dashboard_for_jobs(
    job_a_dir: Path,
    job_b_dir: Path,
    job_a_label: str = "動画A",
    job_b_label: str = "動画B",
    comparison_id: str = "",
    presigned_urls_a: Optional[Dict[str, str]] = None,
    presigned_urls_b: Optional[Dict[str, str]] = None,
    url_expires_at: str = "",
    output_path: Optional[Path] = None,
) -> Optional[Path]:
    """比較ダッシュボードHTMLを生成して保存する。

    失敗した場合は None を返す（例外を発生させない）。
    """
    job_a_dir = Path(job_a_dir)
    cfg = _load_config()

    if not cfg.get("enabled", True) or not cfg.get("comparison", {}).get("enabled", True):
        logger.info("[comparison_dashboard] 比較ダッシュボード生成は無効です")
        return None

    try:
        html = generate_comparison_dashboard(
            job_a_dir, job_b_dir, job_a_label, job_b_label,
            comparison_id, presigned_urls_a, presigned_urls_b, url_expires_at,
        )
    except Exception as e:
        logger.warning("[comparison_dashboard] HTML生成失敗: %s", e)
        return None

    try:
        if output_path is None:
            report_dir = job_a_dir / "report"
            report_dir.mkdir(parents=True, exist_ok=True)
            output_path = report_dir / "comparison_dashboard.html"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info("[comparison_dashboard] comparison_dashboard.html 生成完了: %s", output_path)
        return output_path
    except Exception as e:
        logger.warning("[comparison_dashboard] 保存失敗: %s", e)
        return None
