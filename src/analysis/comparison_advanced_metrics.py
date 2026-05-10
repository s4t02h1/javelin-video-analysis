"""
src/analysis/comparison_advanced_metrics.py — Phase 12 高度指標の比較

2つのジョブの advanced_metrics.json を比較し、差分・解釈文を生成します。

出力先: jobs/comparisons/<comparison_id>/comparison_advanced_metrics.json
または: jobs/<job_a_id>/report/comparison_advanced_metrics_vs_<job_b_id>.json

⚠️  すべての解釈文は断定的ではなく「傾向がある」「出ている可能性がある」
    という参考的な表現を使用します。

Usage:
    from src.analysis.comparison_advanced_metrics import (
        compute_comparison_advanced_metrics,
        save_comparison_advanced_metrics,
    )
    from pathlib import Path

    result = compute_comparison_advanced_metrics(
        job_a_dir=Path("jobs/20260508_070156_518a"),
        job_b_dir=Path("jobs/20260508_081953_329a"),
    )
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jva.comparison_advanced_metrics")

_MODULE_DIR = Path(__file__).resolve().parent
_REPO_ROOT  = _MODULE_DIR.parent.parent

COMPARISON_SCHEMA_VERSION = "0.1.0"


# ── 設定読み込み ─────────────────────────────────────────────────────────────

def _load_config() -> Dict[str, Any]:
    cfg_path = _REPO_ROOT / "configs" / "advanced_metrics.yaml"
    try:
        import yaml  # type: ignore[import-not-found]
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_metric_labels() -> Dict[str, Any]:
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


# ── ユーティリティ ────────────────────────────────────────────────────────────

def _sf(val: Any, digits: int = 4) -> Optional[float]:
    try:
        v = float(val)
        return None if (math.isnan(v) or math.isinf(v)) else round(v, digits)
    except (TypeError, ValueError):
        return None


def _get_comp_val(metrics: Dict[str, Any], key: str) -> Optional[float]:
    """comparison_ready_metrics から値を取り出す。"""
    return _sf(metrics.get("comparison_ready_metrics", {}).get(key))


def _reliability_min(r1: str, r2: str) -> str:
    """2つの信頼度の低い方を返す。"""
    order = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
    v1 = order.get(r1, 0)
    v2 = order.get(r2, 0)
    reverse = {0: "unknown", 1: "low", 2: "medium", 3: "high"}
    return reverse[min(v1, v2)]


def _rel_from_quality(metrics: Dict[str, Any]) -> str:
    return metrics.get("quality", {}).get("metrics_reliability", "unknown")


# ── 解釈文生成 ──────────────────────────────────────────────────────────────

# 比較する指標ごとの解釈テンプレート
# キー: comparison_ready_metrics のキー
# 正の delta = job_b の方が大きい

_INTERP_TEMPLATES: Dict[str, Dict[str, str]] = {
    "release_wrist_height_normalized": {
        "positive": "動画Bでは、リリース時の手首の高さがやや高い傾向が出ています。",
        "negative": "動画Aでは、リリース時の手首の高さがやや高い傾向が出ています。",
        "neutral":  "リリース時の手首高さは2つの動画でほぼ同程度の傾向が出ています。",
    },
    "release_wrist_velocity_normalized": {
        "positive": "動画Bでは、リリース時の手首速度がやや大きい傾向が出ています。",
        "negative": "動画Aでは、リリース時の手首速度がやや大きい傾向が出ています。",
        "neutral":  "リリース時の手首速度は2つの動画でほぼ同程度の傾向が出ています。",
    },
    "release_arm_extension_ratio": {
        "positive": "動画Bでは、リリース時の腕の伸展率がやや高い傾向が出ています。",
        "negative": "動画Aでは、リリース時の腕の伸展率がやや高い傾向が出ています。",
        "neutral":  "リリース時の腕の伸展率は2つの動画でほぼ同程度の傾向が出ています。",
    },
    "release_trunk_angle_estimate": {
        "positive": "動画Bでは、リリース時の体幹前傾角がやや大きい傾向が出ています（2D推定）。",
        "negative": "動画Aでは、リリース時の体幹前傾角がやや大きい傾向が出ています（2D推定）。",
        "neutral":  "リリース時の体幹前傾角は2つの動画でほぼ同程度の傾向が出ています。",
    },
    "block_to_release_time_sec": {
        "positive": "動画Bでは、ブロックからリリースまでの時間がやや長い傾向が出ています。",
        "negative": "動画Aでは、ブロックからリリースまでの時間がやや長い傾向が出ています。",
        "neutral":  "ブロック〜リリース時間は2つの動画でほぼ同程度の傾向が出ています。",
    },
    "hip_deceleration_ratio": {
        "positive": "動画Bでは、ブロック前後の腰の減速率がやや大きい傾向が出ています。",
        "negative": "動画Aでは、ブロック前後の腰の減速率がやや大きい傾向が出ています。",
        "neutral":  "腰の減速率は2つの動画でほぼ同程度の傾向が出ています。",
    },
    "shoulder_hip_separation_angle_estimate": {
        "positive": "動画Bでは、リリース時の肩腰分離角がやや大きい傾向が出ています（2D推定）。",
        "negative": "動画Aでは、リリース時の肩腰分離角がやや大きい傾向が出ています（2D推定）。",
        "neutral":  "肩腰分離角は2つの動画でほぼ同程度の傾向が出ています。",
    },
    "trunk_opening_at_release": {
        "positive": "動画Bでは、リリース時の体幹の開き具合がやや大きい傾向が出ています（2D推定）。",
        "negative": "動画Aでは、リリース時の体幹の開き具合がやや大きい傾向が出ています（2D推定）。",
        "neutral":  "リリース時の体幹の開き具合は2つの動画でほぼ同程度の傾向が出ています。",
    },
    "throwing_wrist_peak_velocity": {
        "positive": "動画Bでは、投げ腕手首の最大速度がやや大きい傾向が出ています（相対値）。",
        "negative": "動画Aでは、投げ腕手首の最大速度がやや大きい傾向が出ています（相対値）。",
        "neutral":  "投げ腕の手首最大速度は2つの動画でほぼ同程度の傾向が出ています。",
    },
    "arm_pullback_distance_estimate": {
        "positive": "動画Bでは、槍引きの距離がやや大きい傾向が出ています（2D推定）。",
        "negative": "動画Aでは、槍引きの距離がやや大きい傾向が出ています（2D推定）。",
        "neutral":  "槍引き距離は2つの動画でほぼ同程度の傾向が出ています。",
    },
    "withdrawal_to_release_time_sec": {
        "positive": "動画Bでは、槍引き完了からリリースまでの時間がやや長い傾向が出ています。",
        "negative": "動画Aでは、槍引き完了からリリースまでの時間がやや長い傾向が出ています。",
        "neutral":  "槍引き〜リリースの時間は2つの動画でほぼ同程度の傾向が出ています。",
    },
    "release_shoulder_line_tilt": {
        "positive": "動画Bでは、リリース時の肩ラインの傾きがやや大きい傾向が出ています（2D推定）。",
        "negative": "動画Aでは、リリース時の肩ラインの傾きがやや大きい傾向が出ています（2D推定）。",
        "neutral":  "リリース時の肩ラインの傾きは2つの動画でほぼ同程度の傾向が出ています。",
    },
    "shoulder_rotation_change_around_block": {
        "positive": "動画Bでは、ブロック〜リリース間の肩回旋変化がやや大きい傾向が出ています（2D推定）。",
        "negative": "動画Aでは、ブロック〜リリース間の肩回旋変化がやや大きい傾向が出ています（2D推定）。",
        "neutral":  "ブロック〜リリース間の肩回旋変化は2つの動画でほぼ同程度の傾向が出ています。",
    },
    "hip_rotation_change_around_block": {
        "positive": "動画Bでは、ブロック〜リリース間の腰回旋変化がやや大きい傾向が出ています（2D推定）。",
        "negative": "動画Aでは、ブロック〜リリース間の腰回旋変化がやや大きい傾向が出ています（2D推定）。",
        "neutral":  "ブロック〜リリース間の腰回旋変化は2つの動画でほぼ同程度の傾向が出ています。",
    },
}

_RELIABILITY_CAUTION = (
    "ただし、撮影角度や姿勢推定点の安定性により数値が変動するため、参考指標として確認してください。"
)

_LOW_RELIABILITY_NOTE = (
    "この指標の信頼度が低いため、数値の差異は参考程度に留めてください。"
)


def _build_interpretation(
    key: str,
    delta: Optional[float],
    delta_percent: Optional[float],
    combined_rel: str,
    notable_threshold: float,
) -> str:
    """解釈文を生成する。"""
    template = _INTERP_TEMPLATES.get(key)
    if template is None:
        return "この指標の比較解釈は現在対応していません。"

    if delta is None:
        return "一方または両方の動画でこの指標が計算できませんでした。"

    if combined_rel in ("low", "unknown"):
        return _LOW_RELIABILITY_NOTE

    abs_dp = abs(delta_percent) if delta_percent is not None else 0.0
    if abs_dp < notable_threshold:
        interp = template["neutral"]
    elif delta > 0:
        interp = template["positive"]
    else:
        interp = template["negative"]

    return f"{interp} {_RELIABILITY_CAUTION}"


# ── メイン比較計算 ────────────────────────────────────────────────────────────

# 比較対象指標リスト
_COMPARISON_KEYS: List[str] = [
    "release_wrist_height_normalized",
    "release_wrist_velocity_normalized",
    "release_arm_extension_ratio",
    "release_trunk_angle_estimate",
    "release_shoulder_line_tilt",
    "block_to_release_time_sec",
    "hip_deceleration_ratio",
    "shoulder_rotation_change_around_block",
    "hip_rotation_change_around_block",
    "shoulder_hip_separation_angle_estimate",
    "trunk_opening_at_release",
    "throwing_wrist_peak_velocity",
    "arm_pullback_distance_estimate",
    "withdrawal_to_release_time_sec",
]


def compute_comparison_advanced_metrics(
    job_a_dir: Path,
    job_b_dir: Path,
    job_a_label: str = "動画A",
    job_b_label: str = "動画B",
) -> Dict[str, Any]:
    """
    2つのジョブの高度解析指標を比較し、差分・解釈文を生成する。

    Parameters
    ----------
    job_a_dir, job_b_dir : Path
        比較対象ジョブのディレクトリ
    job_a_label, job_b_label : str
        UI表示用のラベル（例: "動画A", "5月8日撮影"）

    Returns
    -------
    dict
        comparison_advanced_metrics dict
    """
    from src.analysis.advanced_metrics import (
        load_advanced_metrics, compute_advanced_metrics_for_job,
    )

    job_a_dir = Path(job_a_dir)
    job_b_dir = Path(job_b_dir)

    # metrics ロード（ない場合は計算）
    metrics_a = load_advanced_metrics(job_a_dir)
    if metrics_a is None or metrics_a.get("status") == "failed":
        try:
            compute_advanced_metrics_for_job(job_a_dir)
            metrics_a = load_advanced_metrics(job_a_dir)
        except Exception:
            metrics_a = {}

    metrics_b = load_advanced_metrics(job_b_dir)
    if metrics_b is None or metrics_b.get("status") == "failed":
        try:
            compute_advanced_metrics_for_job(job_b_dir)
            metrics_b = load_advanced_metrics(job_b_dir)
        except Exception:
            metrics_b = {}

    metrics_a = metrics_a or {}
    metrics_b = metrics_b or {}

    cfg = _load_config()
    notable_thresh = float(
        cfg.get("comparison", {}).get("notable_change_threshold_percent", 10.0)
    )
    min_rel_for_interp = cfg.get("comparison", {}).get(
        "min_reliability_for_interpretation", "medium"
    )
    labels = _load_metric_labels()

    rel_a = _rel_from_quality(metrics_a)
    rel_b = _rel_from_quality(metrics_b)

    # ── 各指標を比較 ──────────────────────────────────────────────────────
    comparisons: List[Dict[str, Any]] = []

    for key in _COMPARISON_KEYS:
        val_a = _get_comp_val(metrics_a, key)
        val_b = _get_comp_val(metrics_b, key)

        delta          = _sf(val_b - val_a) if (val_a is not None and val_b is not None) else None
        delta_percent  = None
        if delta is not None and val_a is not None and abs(val_a) > 1e-8:
            delta_percent = _sf((delta / abs(val_a)) * 100, 2)

        combined_rel = _reliability_min(rel_a, rel_b)
        interpretation = _build_interpretation(
            key, delta, delta_percent, combined_rel, notable_thresh)

        lbl_entry  = labels.get(key, {})
        item: Dict[str, Any] = {
            "metric":         key,
            "label":          lbl_entry.get("label", key),
            "description":    lbl_entry.get("description", ""),
            "caution":        lbl_entry.get("caution", ""),
            f"{job_a_label}_value": val_a,
            f"{job_b_label}_value": val_b,
            "delta":          delta,
            "delta_percent":  delta_percent,
            "reliability":    combined_rel,
            "interpretation": interpretation,
        }
        comparisons.append(item)

    # ── サマリー ──────────────────────────────────────────────────────────
    computed_count  = sum(1 for c in comparisons if c["delta"] is not None)
    high_rel_count  = sum(1 for c in comparisons if c.get("reliability") == "high")
    notable_changes = [
        c for c in comparisons
        if c.get("delta_percent") is not None and abs(c["delta_percent"]) >= notable_thresh
    ]

    result = {
        "schema_version":      COMPARISON_SCHEMA_VERSION,
        "generated_at":        datetime.now().isoformat(timespec="seconds"),
        "job_a_id":            metrics_a.get("job_id", job_a_dir.name),
        "job_b_id":            metrics_b.get("job_id", job_b_dir.name),
        "job_a_label":         job_a_label,
        "job_b_label":         job_b_label,
        "job_a_dominant_arm":  metrics_a.get("dominant_arm", "unknown"),
        "job_b_dominant_arm":  metrics_b.get("dominant_arm", "unknown"),
        "job_a_reliability":   rel_a,
        "job_b_reliability":   rel_b,
        "combined_reliability": _reliability_min(rel_a, rel_b),
        "summary": {
            "compared_metrics":      len(comparisons),
            "computable_metrics":    computed_count,
            "high_reliability_metrics": high_rel_count,
            "notable_changes_count": len(notable_changes),
            "notable_threshold_percent": notable_thresh,
            "notable_change_keys": [c["metric"] for c in notable_changes],
        },
        "comparison_note": (
            "この比較レポートはすべて参考値です。動画上の座標から算出した相対指標であり、"
            "実際の距離・速度とは一致しない場合があります。"
            "撮影角度・動画品質・姿勢推定精度により数値が変動するため、"
            "数値の差だけで動作の優劣を判断しないでください。"
        ),
        "comparisons": comparisons,
    }

    return result


def save_comparison_advanced_metrics(
    result: Dict[str, Any],
    save_dir: Path,
    filename: str = "comparison_advanced_metrics.json",
) -> Path:
    """比較指標 JSON を保存する。"""
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    out_path = save_dir / filename
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[comparison_advanced_metrics] 保存完了: %s", out_path)
    return out_path


def compute_comparison_advanced_metrics_for_jobs(
    job_a_dir: Path,
    job_b_dir: Path,
    comparison_id: Optional[str] = None,
    job_a_label: str = "動画A",
    job_b_label: str = "動画B",
) -> Optional[Path]:
    """
    2つのジョブの高度比較指標を計算・保存する。

    失敗しても例外を送出しない（worker 安全設計）。

    Returns
    -------
    Path or None
        comparison_advanced_metrics.json のパス
    """
    try:
        result = compute_comparison_advanced_metrics(
            job_a_dir=job_a_dir,
            job_b_dir=job_b_dir,
            job_a_label=job_a_label,
            job_b_label=job_b_label,
        )

        # 保存先の決定
        if comparison_id:
            save_dir = _REPO_ROOT / "jobs" / "comparisons" / comparison_id
        else:
            job_a_id = Path(job_a_dir).name
            job_b_id = Path(job_b_dir).name
            save_dir = Path(job_a_dir) / "report"
            filename = f"comparison_advanced_metrics_vs_{job_b_id}.json"
        
        if comparison_id:
            filename = "comparison_advanced_metrics.json"

        out = save_comparison_advanced_metrics(result, save_dir, filename)
        logger.info(
            "[comparison_advanced_metrics] ジョブ %s vs %s の比較完了",
            Path(job_a_dir).name, Path(job_b_dir).name,
        )
        return out

    except Exception as e:
        logger.error("[comparison_advanced_metrics] 比較エラー: %s", e)
        return None
