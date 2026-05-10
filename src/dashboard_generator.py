"""
src/dashboard_generator.py — Phase 13: ユーザー向けダッシュボードHTML生成

ジョブごとに user_dashboard.html をスマホ対応1ファイルHTML として生成する。

⚠️ 重要な方針
    - 解析結果はすべて参考資料として扱う
    - 断定的なフォーム評価を避ける
    - 高校生アスリート・保護者・コーチが読める日本語にする
    - 医療診断・怪我の診断・専門的競技指導の代替ではないことを明示する

Usage:
    from src.dashboard_generator import generate_user_dashboard_for_job
    from pathlib import Path

    path = generate_user_dashboard_for_job(Path("jobs/20260508_070156_518a"))
    # → jobs/20260508_070156_518a/report/user_dashboard.html
"""
from __future__ import annotations

import base64
import html as _html_escape
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.dashboard")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE_DIR = _REPO_ROOT / "templates"

# ── フェーズ表示定義 ──────────────────────────────────────────────────────────

_PHASE_LABELS: Dict[str, Dict[str, str]] = {
    "approach": {
        "label": "🏃 助走",
        "description": "助走フェーズ。スピードをのせながらリリースに向けて準備します。",
        "tip": "腰の移動方向と速度の傾向を確認してください（参考値）。",
    },
    "crossstep": {
        "label": "↗️ クロスステップ",
        "description": "クロスステップフェーズ。体幹の向きを切り替えながらブロックに備えます。",
        "tip": "肩腰の向きの変化を確認してください（2D推定・参考値）。",
    },
    "withdrawal": {
        "label": "↩️ 槍を引く局面",
        "description": "槍引きフェーズ。やりを引いてリリースのためのためを作ります。",
        "tip": "槍引き距離は参考値です。2D動画上の相対的な値です。",
    },
    "block": {
        "label": "🛑 ブロック",
        "description": "ブロックフェーズ。前足を踏み込んで体幹の前進を止めます。",
        "tip": "腰の減速比は参考値です。動画上の座標変化で算出しています。",
    },
    "release": {
        "label": "🎯 リリース",
        "description": "リリースフェーズ。やりを放す瞬間です。",
        "tip": "手首高さ・速度は相対的な参考値です。実際の距離・速度とは異なります。",
    },
    "follow_through": {
        "label": "🌀 フォロースルー",
        "description": "フォロースルーフェーズ。リリース後の動きです。",
        "tip": "フォロースルーの動きを確認してください。",
    },
    "recovery": {
        "label": "🔄 リカバリー",
        "description": "リカバリーフェーズ。投擲後のバランス回復です。",
        "tip": "着地後の安定性を確認してください。",
    },
}

# 主要指標（優先表示）
_KEY_METRICS = [
    ("release_wrist_height_normalized",       "リリース時の手首高さ（相対）"),
    ("release_wrist_velocity_normalized",      "リリース時の手首速度（相対）"),
    ("block_to_release_time_sec",              "ブロック〜リリースの時間"),
    ("shoulder_hip_separation_angle_estimate_at_release", "肩腰分離（2D推定・参考）"),
    ("hip_deceleration_ratio",                 "ブロック前後の腰中心減速比"),
    ("throwing_wrist_peak_velocity",           "投げ腕の手首最大速度（相対）"),
]

# 信頼度 → バッジHTML
_REL_BADGE = {
    "high":    '<span class="badge badge-high">🟢 高</span>',
    "medium":  '<span class="badge badge-medium">🟡 中</span>',
    "low":     '<span class="badge badge-low">🔴 低</span>',
    "unknown": '<span class="badge badge-unknown">⚪ 不明</span>',
}

# ── ユーティリティ ────────────────────────────────────────────────────────────

def _e(text: Any) -> str:
    """HTMLエスケープして文字列で返す。"""
    return _html_escape.escape(str(text) if text is not None else "")


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_config() -> Dict[str, Any]:
    """configs/dashboard.yaml を読み込む。"""
    cfg_path = _REPO_ROOT / "configs" / "dashboard.yaml"
    try:
        import yaml  # type: ignore[import-not-found]
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("[dashboard] 設定読み込み失敗: %s", e)
    return {}


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
        return {}


def _load_template(name: str) -> str:
    """テンプレートファイルを読み込む。"""
    path = _TEMPLATE_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"テンプレートが見つかりません: {path}")


def _embed_image_as_data_uri(img_path: Path) -> Optional[str]:
    """画像をdata URIとして埋め込む（Base64エンコード）。"""
    if not img_path.exists():
        return None
    ext = img_path.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif"}.get(ext, "image/jpeg")
    try:
        data = base64.b64encode(img_path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"
    except Exception:
        return None


def _fmt_val(v: Any) -> str:
    """指標値を表示用文字列にする。"""
    if v is None:
        return "—"
    try:
        f = float(v)
        # 整数に近ければ整数表示
        if abs(f - round(f)) < 0.001:
            return str(int(round(f)))
        return f"{f:.3f}"
    except (TypeError, ValueError):
        return _e(v)


def _fmt_expires(iso: str) -> str:
    """ISO 8601 を日本語日時表示に変換する。"""
    if not iso:
        return "不明"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y年%m月%d日 %H:%M")
    except Exception:
        return _e(iso)


# ── セクション生成 ────────────────────────────────────────────────────────────

def _build_video_section(job_dir: Path, presigned_urls: Optional[Dict[str, str]], cfg: Dict[str, Any]) -> str:
    """解析動画セクションのHTML を生成する。"""
    if not cfg.get("include_videos", True):
        return ""

    output_dir = job_dir / "output"
    if not output_dir.exists():
        return ""

    video_defs = [
        ("skeleton", "骨格線つき動画",
         "姿勢推定点（関節位置の推定）を骨格線として重ねた動画です。動きの流れを確認できます。関節位置は推定であり、完全に正確とは限りません。"),
        ("heatmap", "ヒートマップ動画",
         "手首や腰など各部位の動きの軌跡を色で表した動画です。動作パターンの参考にしてください。"),
        ("hud", "HUDつき動画",
         "速度・角度などの参考情報をオーバーレイ表示した動画です。値は動画上の座標から算出した参考値です。"),
        ("comparison", "比較動画",
         "複数の試技を並べて比較した動画です（比較解析を実施した場合のみ表示されます）。"),
    ]

    items_html: List[str] = []
    for keyword, label, caption in video_defs:
        # output/ から該当動画を探す
        mp4_files = sorted(output_dir.glob(f"*{keyword}*.mp4"))
        if not mp4_files:
            continue

        mp4 = mp4_files[0]
        # presigned URL があれば優先
        url_display = ""
        if presigned_urls:
            for key, url in presigned_urls.items():
                if keyword in key.lower() and key.endswith(".mp4"):
                    url_display = url
                    break

        if url_display:
            video_html = (
                f'<div class="video-container">'
                f'<video controls preload="metadata" playsinline>'
                f'<source src="{_e(url_display)}" type="video/mp4">'
                f'お使いのブラウザは動画再生に対応していません。'
                f'</video></div>'
                f'<a class="btn btn-primary" href="{_e(url_display)}" target="_blank" rel="noopener noreferrer">'
                f'▶ {_e(label)}を別タブで開く</a>'
            )
        else:
            # ローカルファイル（相対パス参照）
            rel = mp4.relative_to(job_dir / "report").as_posix() if mp4.is_relative_to(job_dir / "report") else f"../output/{mp4.name}"
            video_html = (
                f'<div class="video-container">'
                f'<video controls preload="metadata" playsinline>'
                f'<source src="{_e(rel)}" type="video/mp4">'
                f'お使いのブラウザは動画再生に対応していません。'
                f'</video></div>'
            )

        items_html.append(
            f'<div style="margin-bottom:20px">'
            f'<p class="video-label">{_e(label)}</p>'
            f'{video_html}'
            f'<p class="video-caption">💡 {_e(caption)}</p>'
            f'</div>'
        )

    if not items_html:
        return ""

    inner = "\n".join(items_html)
    return f"""
<div class="card" id="videos">
  <h2>🎬 解析動画</h2>
  <div class="alert alert-warning" style="font-size:.85rem">
    動画内の骨格線・数値はすべて推定値です。関節位置や速度の値は参考としてご確認ください。
  </div>
  {inner}
</div>"""


def _build_phase_images_section(job_dir: Path, phase_frames_data: Optional[Dict[str, Any]], cfg: Dict[str, Any]) -> str:
    """代表フレーム・フェーズ別画像セクションのHTMLを生成する。"""
    if not cfg.get("include_phase_images", True):
        return ""

    frames_dir = job_dir / "report" / "frames"
    phase_keys = list(_PHASE_LABELS.keys())

    items: List[str] = []
    for phase_key in phase_keys:
        info = _PHASE_LABELS[phase_key]
        label = info["label"]
        description = info["description"]
        tip = info["tip"]

        # 画像を探す
        img_path: Optional[Path] = None
        for ext in ["png", "jpg", "jpeg"]:
            candidates = list(frames_dir.glob(f"*{phase_key}*.{ext}")) if frames_dir.exists() else []
            if candidates:
                img_path = candidates[0]
                break

        # フレーム番号・時刻情報
        frame_num = None
        frame_sec = None
        is_manual = False
        confidence_str = ""
        if phase_frames_data:
            pf = phase_frames_data.get(f"{phase_key}_frame") or phase_frames_data.get(phase_key)
            if pf is not None:
                frame_num = pf
            sec = phase_frames_data.get(f"{phase_key}_time_sec")
            if sec is not None:
                frame_sec = float(sec)
            is_manual = bool(phase_frames_data.get("is_manual", False))

        meta_parts: List[str] = []
        if frame_num is not None:
            meta_parts.append(f"フレーム: {frame_num}")
        if frame_sec is not None:
            meta_parts.append(f"{frame_sec:.2f} 秒")
        if is_manual:
            meta_parts.append("手動指定")
        elif frame_num is not None:
            meta_parts.append("自動推定")
        meta_str = " ｜ ".join(meta_parts)

        if img_path and img_path.exists():
            # 画像埋め込み（Baseサイズが大きくなりすぎないよう注意: 1フレームは数十KB〜数百KB程度）
            data_uri = _embed_image_as_data_uri(img_path)
            if data_uri:
                img_tag = f'<img src="{data_uri}" alt="{_e(label)}" loading="lazy">'
            else:
                img_tag = f'<div class="phase-missing">画像を読み込めませんでした</div>'
            items.append(
                f'<div class="phase-item">'
                f'{img_tag}'
                f'<div class="phase-label">{_e(label)}</div>'
                f'<div class="phase-meta">{_e(meta_str)}<br>'
                f'💡 {_e(tip)}</div>'
                f'</div>'
            )
        else:
            items.append(
                f'<div class="phase-item">'
                f'<div class="phase-missing">📷 このフェーズ画像はありません</div>'
                f'<div class="phase-label">{_e(label)}</div>'
                f'<div class="phase-meta">{_e(description)}</div>'
                f'</div>'
            )

    if not items:
        return ""

    grid_items = "\n".join(items)
    return f"""
<div class="card" id="phase-images">
  <h2>🖼️ 代表フレーム・フェーズ別画像</h2>
  <p style="font-size:.88rem;color:#555;margin-bottom:10px">
    各フェーズの代表フレームです。姿勢推定・フェーズ推定は自動処理による参考表示です。
  </p>
  <div class="phase-grid">
    {grid_items}
  </div>
</div>"""


def _build_metrics_section(
    job_dir: Path,
    advanced_metrics: Optional[Dict[str, Any]],
    metric_labels: Dict[str, Any],
    cfg: Dict[str, Any],
) -> str:
    """主要指標カードセクションのHTMLを生成する。"""
    if not cfg.get("include_advanced_metrics", True):
        return ""

    if not advanced_metrics or advanced_metrics.get("status") in ("failed", "disabled"):
        return """
<div class="card" id="metrics">
  <h2>📊 主要指標（参考）</h2>
  <p style="color:#888;font-size:.9rem">指標データが生成されていません。</p>
</div>"""

    # 品質情報
    quality = advanced_metrics.get("quality", {})
    overall_rel = quality.get("metrics_reliability", "unknown")
    rel_badge = _REL_BADGE.get(overall_rel, _REL_BADGE["unknown"])
    det_rate = quality.get("pose_detection_rate", 0)
    overall_q = quality.get("overall_quality", "unknown")
    fps = advanced_metrics.get("fps", "—")

    quality_html = (
        f'<div style="margin-bottom:12px;font-size:.88rem">'
        f'動画品質: <strong>{_e(overall_q)}</strong> &nbsp;|&nbsp; '
        f'指標信頼度: {rel_badge} &nbsp;|&nbsp; '
        f'検出率: <strong>{det_rate:.0%}</strong> &nbsp;|&nbsp; '
        f'FPS: <strong>{_e(fps)}</strong>'
        f'</div>'
    )

    # 主要指標カード
    rm = advanced_metrics.get("release_metrics", {})
    bm = advanced_metrics.get("block_metrics", {})
    am = advanced_metrics.get("arm_metrics", {})

    all_metric_data: Dict[str, Any] = {}
    if isinstance(rm, dict) and rm.get("available"):
        all_metric_data.update(rm)
    if isinstance(bm, dict) and bm.get("available"):
        all_metric_data.update(bm)
    if isinstance(am, dict) and am.get("available"):
        all_metric_data.update(am)

    cards_html: List[str] = []
    for key, fallback_label in _KEY_METRICS:
        metric_def = all_metric_data.get(key)
        if not isinstance(metric_def, dict):
            continue

        val = metric_def.get("value")
        unit = metric_def.get("unit", "")
        rel = metric_def.get("reliability", "unknown")
        note = metric_def.get("note", "")

        ml = metric_labels.get(key, {})
        display_label = ml.get("label") or fallback_label
        description = ml.get("description", "")
        caution = ml.get("caution", "")
        display_unit = ml.get("unit") or unit

        rel_badge_sm = _REL_BADGE.get(rel, _REL_BADGE["unknown"])

        cards_html.append(
            f'<div class="metric-card">'
            f'<div class="m-label">{_e(display_label)}</div>'
            f'<div>'
            f'  <span class="m-value">{_fmt_val(val)}</span>'
            f'  <span class="m-unit">{_e(display_unit)}</span>'
            f'</div>'
            f'<div style="margin-top:4px">{rel_badge_sm}</div>'
            f'<div class="m-caution">{_e(caution or description[:80])}</div>'
            f'</div>'
        )

    if not cards_html:
        return """
<div class="card" id="metrics">
  <h2>📊 主要指標（参考）</h2>
  <p style="color:#888;font-size:.9rem">リリース・ブロックフレームが特定できなかったため、主要指標を表示できません。</p>
</div>"""

    cards_grid = "\n".join(cards_html)

    # 詳細指標（折りたたみ式）
    detail_sections = _build_detail_metrics(advanced_metrics, metric_labels)

    return f"""
<div class="card" id="metrics">
  <h2>📊 主要指標（参考）</h2>
  <div class="alert alert-warning" style="font-size:.85rem">
    以下の指標はすべて <strong>参考値</strong> です。動画上の座標から算出した相対値であり、
    実際の距離・速度・角度とは異なります。撮影角度・解像度の影響を受けます。
  </div>
  {quality_html}
  <div class="metric-grid">
    {cards_grid}
  </div>
  {detail_sections}
</div>"""


def _build_detail_metrics(advanced_metrics: Dict[str, Any], metric_labels: Dict[str, Any]) -> str:
    """詳細指標（折りたたみ式）のHTMLを生成する。"""

    def _cat_rows(category_dict: Optional[Dict[str, Any]], exclude_keys: Optional[set] = None) -> str:
        if not isinstance(category_dict, dict) or not category_dict.get("available"):
            return "<p style='color:#999;font-size:.85rem'>データなし</p>"
        rows: List[str] = []
        for k, v in category_dict.items():
            if k in ("available", "reason"):
                continue
            if exclude_keys and k in exclude_keys:
                continue
            if not isinstance(v, dict):
                continue
            ml = metric_labels.get(k, {})
            label = ml.get("label") or k
            val_str = _fmt_val(v.get("value"))
            unit = ml.get("unit") or v.get("unit", "")
            rel = v.get("reliability", "unknown")
            rel_b = _REL_BADGE.get(rel, "")
            rows.append(
                f'<div class="metric-diff">'
                f'<span class="d-label">{_e(label)}</span>'
                f'<span style="float:right">{_e(val_str)} <span style="font-size:.75rem;color:#666">{_e(unit)}</span> {rel_b}</span>'
                f'</div>'
            )
        return "\n".join(rows) if rows else "<p style='color:#999;font-size:.85rem'>データなし</p>"

    rm = advanced_metrics.get("release_metrics")
    bm = advanced_metrics.get("block_metrics")
    tm = advanced_metrics.get("trunk_metrics")
    am = advanced_metrics.get("arm_metrics")
    tr = advanced_metrics.get("trajectory_metrics")
    pm = advanced_metrics.get("phase_metrics", {})

    # フェーズ別指標
    pm_rows: List[str] = []
    for pkey, pval in pm.items():
        if not isinstance(pval, dict):
            continue
        p_info = _PHASE_LABELS.get(pkey, {})
        p_label = p_info.get("label", pkey)
        dur = _fmt_val(pval.get("duration_sec", {}).get("value") if isinstance(pval.get("duration_sec"), dict) else pval.get("duration_sec"))
        pm_rows.append(f'<div class="metric-diff"><span class="d-label">{_e(p_label)}</span><span style="float:right">{dur} 秒</span></div>')
    pm_html = "\n".join(pm_rows) if pm_rows else "<p style='color:#999;font-size:.85rem'>データなし</p>"

    return f"""
<details style="margin-top:16px">
  <summary>📋 詳細指標をすべて表示する</summary>
  <div class="detail-inner">
    <p style="font-size:.82rem;color:#888;margin-bottom:12px">
      以下の詳細指標もすべて参考値です。信頼度が低い場合は特に注意してください。
    </p>
    <details>
      <summary>リリース指標</summary>
      <div class="detail-inner">{_cat_rows(rm)}</div>
    </details>
    <details>
      <summary>ブロック指標</summary>
      <div class="detail-inner">{_cat_rows(bm)}</div>
    </details>
    <details>
      <summary>体幹・肩腰分離指標（2D推定）</summary>
      <div class="detail-inner">
        <p style="font-size:.82rem;color:#888;margin-bottom:8px">
          ※ 肩腰分離の数値は3Dの正確な回旋角ではなく、2D動画上の見かけの角度推定です。
        </p>
        {_cat_rows(tm)}
      </div>
    </details>
    <details>
      <summary>投げ腕指標</summary>
      <div class="detail-inner">{_cat_rows(am)}</div>
    </details>
    <details>
      <summary>軌跡指標</summary>
      <div class="detail-inner">{_cat_rows(tr)}</div>
    </details>
    <details>
      <summary>フェーズ別時間</summary>
      <div class="detail-inner">{pm_html}</div>
    </details>
  </div>
</details>"""


def _build_graphs_section(job_dir: Path, cfg: Dict[str, Any]) -> str:
    """グラフセクションのHTMLを生成する。"""
    if not cfg.get("include_graphs", True):
        return ""

    graphs_dir = job_dir / "report" / "graphs"
    if not graphs_dir.exists():
        return ""

    graph_defs = [
        ("wrist_height", "手首高さグラフ",
         "フレームごとの投げ腕手首高さの変化です。リリース前後の動きを確認できます。"),
        ("wrist_velocity", "手首速度グラフ",
         "フレームごとの手首速度の変化です。加速のタイミングの傾向を確認できます（参考値）。"),
        ("trunk_angle", "体幹角度グラフ",
         "フレームごとの体幹前傾角度の変化です（2D推定・参考値）。"),
        ("phase", "フェーズ別グラフ",
         "フェーズ区切りとその時間を示すグラフです。"),
        ("comparison", "比較グラフ",
         "複数試技の比較グラフです（比較解析実施時のみ）。"),
    ]

    items_html: List[str] = []
    for keyword, label, caption in graph_defs:
        imgs = list(graphs_dir.glob(f"*{keyword}*.png")) + list(graphs_dir.glob(f"*{keyword}*.jpg"))
        if not imgs:
            continue
        for img_path in imgs[:1]:  # 最初の1枚だけ
            data_uri = _embed_image_as_data_uri(img_path)
            if data_uri:
                items_html.append(
                    f'<figure class="graph-item">'
                    f'<img src="{data_uri}" alt="{_e(label)}" loading="lazy">'
                    f'<figcaption>📈 {_e(label)} — {_e(caption)}</figcaption>'
                    f'</figure>'
                )

    # グラフ解説PDFリンク
    graph_pdf = job_dir / "report" / "graph_explanation.pdf"
    pdf_link = ""
    if graph_pdf.exists():
        pdf_link = '<p style="margin-top:12px"><a class="btn btn-secondary" href="../report/graph_explanation.pdf" target="_blank">📄 グラフ解説PDFを開く</a></p>'

    if not items_html and not pdf_link:
        return ""

    inner = "\n".join(items_html)
    return f"""
<div class="card" id="graphs">
  <h2>📈 グラフ</h2>
  <p style="font-size:.88rem;color:#555;margin-bottom:10px">
    グラフの値は動画上の座標から算出した参考値です。縦軸・横軸の単位は動画の座標系に依存します。
  </p>
  {inner}
  {pdf_link}
</div>"""


def _build_downloads_section(
    job_dir: Path,
    presigned_urls: Optional[Dict[str, str]],
    cfg: Dict[str, Any],
) -> str:
    """ダウンロードセクションのHTMLを生成する。"""
    if not cfg.get("include_download_links", True):
        return ""

    def _make_link(rel_path: str, label: str, icon: str = "📄",
                   btn_class: str = "btn btn-dl", external_url: Optional[str] = None) -> str:
        full_path = job_dir / rel_path
        if not full_path.exists():
            return (
                f'<div class="dl-item">'
                f'<span class="dl-icon">{icon}</span>'
                f'<span class="dl-label">{_e(label)}</span>'
                f'<span class="dl-unavailable">（未生成）</span>'
                f'</div>'
            )
        url = external_url or rel_path.replace("\\", "/")
        return (
            f'<div class="dl-item">'
            f'<span class="dl-icon">{icon}</span>'
            f'<span class="dl-label">'
            f'<a class="{btn_class}" href="{_e(url)}" target="_blank" rel="noopener noreferrer">'
            f'{_e(label)}</a>'
            f'</span>'
            f'</div>'
        )

    def _get_presigned(keyword: str) -> Optional[str]:
        if not presigned_urls:
            return None
        for key, url in presigned_urls.items():
            if keyword in key:
                return url
        return None

    sections_html: List[str] = []

    # 最初に読む資料
    sections_html.append(f"""
<div class="dl-category">
  <h3>📋 最初に読む資料</h3>
  {_make_link("report/00_最初に読んでください.pdf", "00_最初に読んでください.pdf", "📋",
              external_url=_get_presigned("最初に読んでください") or _get_presigned("intro"))}
  {_make_link("report/video_instruction.pdf", "解析動画の見方.pdf", "🎬",
              external_url=_get_presigned("video_instruction"))}
</div>""")

    # 選手向け資料
    sections_html.append(f"""
<div class="dl-category">
  <h3>📊 選手向け資料</h3>
  {_make_link("report/athlete_data_sheet.pdf", "選手データシート.pdf", "📊",
              external_url=_get_presigned("athlete_data_sheet"))}
  {_make_link("report/athlete_summary.pdf", "解析サマリー.pdf", "📊",
              external_url=_get_presigned("athlete_summary"))}
  {_make_link("report/phase_summary.pdf", "フェーズ別サマリー.pdf", "🔍",
              external_url=_get_presigned("phase_summary"))}
</div>""")

    # 高度解析レポート
    sections_html.append(f"""
<div class="dl-category">
  <h3>📈 高度解析レポート（参考）</h3>
  {_make_link("report/advanced_metrics_report.pdf", "高度解析指標レポート.pdf", "📈",
              external_url=_get_presigned("advanced_metrics_report"))}
  {_make_link("report/graph_explanation.pdf", "グラフ解説.pdf", "📈",
              external_url=_get_presigned("graph_explanation"))}
</div>""")

    # コーチ向け資料
    sections_html.append(f"""
<div class="dl-category">
  <h3>👤 コーチ向け資料</h3>
  {_make_link("report/coach_review_sheet.pdf", "コーチ用レビューシート.pdf", "👤",
              external_url=_get_presigned("coach_review_sheet"))}
  {_make_link("report/comparison_report.pdf", "比較レポート.pdf", "⚖️",
              external_url=_get_presigned("comparison_report"))}
  {_make_link("report/comparison_advanced_report.pdf", "比較高度指標レポート.pdf", "⚖️",
              external_url=_get_presigned("comparison_advanced_report"))}
</div>""")

    # 一括ダウンロード
    sections_html.append(f"""
<div class="dl-category">
  <h3>📦 一括ダウンロード</h3>
  {_make_link("deliverables/full_report_package.zip", "全資料一括ダウンロード（ZIP）", "📦", "btn btn-dl",
              external_url=_get_presigned("full_report_package"))}
  {_make_link("deliverables/data_sheet_package.zip", "データシートパッケージ（ZIP）", "📦", "btn btn-secondary",
              external_url=_get_presigned("data_sheet_package"))}
</div>""")

    # 研究・開発用データ
    if cfg.get("include_research_data_section", True):
        sections_html.append(f"""
<div class="dl-category">
  <h3>🔬 研究・開発用データ</h3>
  <p style="font-size:.82rem;color:#888;margin-bottom:8px">
    以下のデータは研究・開発用途のファイルです。通常は開く必要はありません。
  </p>
  {_make_link("report/pose_landmarks.csv", "姿勢推定データ CSV", "🔬", "btn btn-research",
              external_url=_get_presigned("pose_landmarks"))}
  {_make_link("report/advanced_metrics.json", "高度解析指標 JSON", "🔬", "btn btn-research",
              external_url=_get_presigned("advanced_metrics.json"))}
  {_make_link("report/phase_detection_result.json", "フェーズ推定結果 JSON", "🔬", "btn btn-research",
              external_url=_get_presigned("phase_detection_result"))}
</div>""")

    inner = "\n".join(sections_html)
    return f"""
<div class="card" id="downloads">
  <h2>📥 ダウンロード</h2>
  {inner}
</div>"""


# ── メイン生成関数 ────────────────────────────────────────────────────────────

def generate_user_dashboard(
    job_dir: Path,
    presigned_urls: Optional[Dict[str, str]] = None,
    url_expires_at: str = "",
) -> str:
    """ユーザー向けダッシュボードHTMLを生成して返す（保存はしない）。

    Parameters
    ----------
    job_dir : Path
        ジョブディレクトリ
    presigned_urls : dict, optional
        s3_key → presigned URL のマッピング
    url_expires_at : str
        URL 有効期限（ISO 8601）

    Returns
    -------
    str
        生成されたHTML文字列
    """
    job_dir = Path(job_dir)
    cfg = _load_config()
    metric_labels = _load_metric_labels()

    # データ読み込み
    job_data = _load_json(job_dir / "job.json") or {}
    customer_info = _load_json(job_dir / "customer_info.json") or {}
    phase_frames_data = _load_json(job_dir / "phase_frames.json") or {}
    advanced_metrics = _load_json(job_dir / "report" / "advanced_metrics.json")

    # ── 表示用情報 ────────────────────────────────────────────────────────────
    job_id = job_data.get("job_id", job_dir.name)
    athlete_name = (customer_info.get("customer_name") or customer_info.get("nickname") or "").strip()
    plan_name = customer_info.get("plan", job_data.get("mode", "スタンダード"))
    created_at = job_data.get("created_at", "")
    delivered_at = _fmt_expires(created_at) if created_at else datetime.now().strftime("%Y年%m月%d日")
    generated_at = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    metrics_version = (advanced_metrics or {}).get("metrics_version", "—") if advanced_metrics else "—"

    title = "解析結果ダッシュボード"
    if athlete_name:
        title = f"{athlete_name} — {title}"

    athlete_name_display = f"👤 {_e(athlete_name)} &nbsp;|&nbsp; " if athlete_name else ""
    plan_display = f"📋 プラン: {_e(plan_name)} &nbsp;|&nbsp; " if plan_name else ""

    # ── セクション生成 ─────────────────────────────────────────────────────────
    video_section = _build_video_section(job_dir, presigned_urls, cfg)
    phase_images_section = _build_phase_images_section(job_dir, phase_frames_data, cfg)
    metrics_section = _build_metrics_section(job_dir, advanced_metrics, metric_labels, cfg)
    graphs_section = _build_graphs_section(job_dir, cfg)
    downloads_section = _build_downloads_section(job_dir, presigned_urls, cfg)

    # ── テンプレート展開 ───────────────────────────────────────────────────────
    template = _load_template("user_dashboard.html")

    html = template
    html = html.replace("{{ title }}", _e(title))
    html = html.replace("{{ job_id }}", _e(job_id))
    html = html.replace("{{ athlete_name_display }}", athlete_name_display)
    html = html.replace("{{ plan_display }}", plan_display)
    html = html.replace("{{ plan_name }}", _e(plan_name))
    html = html.replace("{{ delivered_at }}", _e(delivered_at))
    html = html.replace("{{ generated_at }}", _e(generated_at))
    html = html.replace("{{ metrics_version }}", _e(metrics_version))
    html = html.replace("{{ url_expires_at_display }}", _e(_fmt_expires(url_expires_at)))
    html = html.replace("{{ video_section }}", video_section)
    html = html.replace("{{ phase_images_section }}", phase_images_section)
    html = html.replace("{{ metrics_section }}", metrics_section)
    html = html.replace("{{ graphs_section }}", graphs_section)
    html = html.replace("{{ downloads_section }}", downloads_section)

    return html


def generate_user_dashboard_for_job(
    job_dir: Path,
    presigned_urls: Optional[Dict[str, str]] = None,
    url_expires_at: str = "",
) -> Optional[Path]:
    """ユーザー向けダッシュボードHTMLを生成して保存する。

    失敗した場合は None を返す（例外を発生させない）。

    Returns
    -------
    Path | None
        生成されたファイルのパス。失敗時は None。
    """
    job_dir = Path(job_dir)
    cfg = _load_config()

    if not cfg.get("enabled", True) or not cfg.get("generate_static_html", True):
        logger.info("[dashboard] ダッシュボード生成は無効に設定されています: %s", job_dir.name)
        return None

    try:
        html = generate_user_dashboard(job_dir, presigned_urls, url_expires_at)
    except Exception as e:
        logger.warning("[dashboard] HTML生成失敗: %s — %s", job_dir.name, e)
        return None

    try:
        report_dir = job_dir / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        out_path = report_dir / "user_dashboard.html"
        out_path.write_text(html, encoding="utf-8")
        logger.info("[dashboard] user_dashboard.html 生成完了: %s", out_path)
        return out_path
    except Exception as e:
        logger.warning("[dashboard] 保存失敗: %s — %s", job_dir.name, e)
        return None


def generate_dashboard_delivery_message(
    job_id: str,
    dashboard_url: Optional[str],
    url_expires_at: str = "",
) -> str:
    """ダッシュボードURLを含む納品メッセージを生成する。"""
    expires_display = _fmt_expires(url_expires_at) if url_expires_at else "不明"

    if dashboard_url:
        url_section = (
            f"解析結果はこちらのダッシュボードからご確認ください。\n\n"
            f"  {dashboard_url}\n\n"
            f"まずはページ上部の「最初に見る順番」に沿ってご確認ください。\n"
            f"PDFや動画も同じページ内から確認できます。\n\n"
            f"URLの有効期限: {expires_display}\n"
            f"期限切れの場合は再発行しますのでご連絡ください。"
        )
    else:
        url_section = f"ダッシュボードURLの生成に失敗しました。お問い合わせください（ジョブID: {job_id}）。"

    message = (
        f"【解析結果のお届け】\n\n"
        f"{url_section}\n\n"
        f"---\n"
        f"本解析は動画から取得した姿勢推定データをもとにした参考資料です。\n"
        f"競技指導、医療判断、怪我の診断を代替するものではありません。\n"
        f"数値は傾向把握の参考としてご活用ください。\n\n"
        f"ジョブID: {job_id}"
    )
    return message
