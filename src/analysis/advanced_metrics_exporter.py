"""
src/analysis/advanced_metrics_exporter.py — Phase 12 高度指標エクスポーター

advanced_metrics.json を JSON / CSV / JSONL 形式で exports/metrics/ に出力します。

個人情報は含みません（job_id のみ）。

出力先:
    exports/metrics/advanced_metrics.json   — 最新の全ジョブ集約 JSON
    exports/metrics/advanced_metrics.csv    — 主要指標の CSV
    exports/metrics/advanced_metrics.jsonl  — 1ジョブ1行の JSONL

Usage:
    from src.analysis.advanced_metrics_exporter import export_advanced_metrics_for_job
    from pathlib import Path

    out = export_advanced_metrics_for_job(Path("jobs/20260508_070156_518a"))
"""
from __future__ import annotations

import csv
import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.advanced_metrics_exporter")

_MODULE_DIR = Path(__file__).resolve().parent
_REPO_ROOT  = _MODULE_DIR.parent.parent


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


def _sf(val: Any, digits: int = 4) -> Optional[float]:
    try:
        v = float(val)
        return None if (math.isnan(v) or math.isinf(v)) else round(v, digits)
    except (TypeError, ValueError):
        return None


# ── 主要指標フラット化 ────────────────────────────────────────────────────────

_DEFAULT_EXPORT_KEYS = [
    "dominant_arm",
    "fps",
    "overall_quality",
    "metrics_reliability",
    "pose_detection_rate",
    "release_wrist_height_normalized",
    "release_wrist_velocity_normalized",
    "release_arm_extension_ratio",
    "release_trunk_angle_estimate",
    "block_to_release_time_sec",
    "hip_deceleration_ratio",
    "shoulder_hip_separation_angle_estimate",
    "trunk_opening_at_release",
    "throwing_wrist_peak_velocity",
    "arm_pullback_distance_estimate",
    "withdrawal_to_release_time_sec",
]


def _flatten_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """advanced_metrics dict を CSV 出力用フラット dict に変換する。"""
    flat: Dict[str, Any] = {
        "job_id":             metrics.get("job_id"),
        "dominant_arm":       metrics.get("dominant_arm"),
        "fps":                metrics.get("fps"),
        "metrics_version":    metrics.get("metrics_version"),
        "generated_at":       metrics.get("generated_at"),
        "status":             metrics.get("status"),
    }

    # quality
    q = metrics.get("quality", {})
    flat["overall_quality"]       = q.get("overall_quality")
    flat["metrics_reliability"]   = q.get("metrics_reliability")
    flat["pose_detection_rate"]   = q.get("pose_detection_rate")
    flat["filming_angle"]         = q.get("filming_angle")

    # comparison_ready_metrics（主要指標）
    cr = metrics.get("comparison_ready_metrics", {})
    for k, v in cr.items():
        flat[k] = _sf(v) if v is not None else None

    # release_metrics の追加指標
    rm = metrics.get("release_metrics", {})
    if rm.get("available"):
        flat["release_frame"]      = rm.get("release_frame")
        flat["release_time_sec"]   = rm.get("release_time_sec")
        for k in ["release_wrist_height_normalized",
                   "release_arm_extension_ratio",
                   "release_trunk_angle_estimate",
                   "release_shoulder_line_tilt",
                   "release_hip_line_tilt"]:
            if k not in flat:
                entry = rm.get(k)
                flat[k] = _sf(entry.get("value")) if isinstance(entry, dict) else _sf(entry)

    # block_metrics の追加指標
    bm = metrics.get("block_metrics", {})
    if bm.get("available"):
        flat["block_frame"] = bm.get("block_frame")
        flat["block_leg_side"] = bm.get("block_leg_side")
        for k in ["hip_deceleration_ratio", "block_to_release_time_sec"]:
            if k not in flat:
                entry = bm.get(k)
                flat[k] = _sf(entry.get("value")) if isinstance(entry, dict) else _sf(entry)

    # arm_metrics の追加指標
    am = metrics.get("arm_metrics", {})
    if am.get("available"):
        for k in ["throwing_wrist_peak_velocity", "elbow_angle_estimate_at_release",
                   "arm_pullback_distance_estimate"]:
            if k not in flat:
                entry = am.get(k)
                flat[k] = _sf(entry.get("value")) if isinstance(entry, dict) else _sf(entry)

    # フェーズ別時間
    pm = metrics.get("phase_metrics", {})
    for phase_name in ["approach", "cross_step", "withdrawal", "follow_through", "recovery"]:
        ph = pm.get(phase_name, {})
        dur = ph.get("duration_sec")
        flat[f"{phase_name}_duration_sec"] = _sf(dur) if dur is not None else None

    return flat


# ── エクスポート関数 ─────────────────────────────────────────────────────────

def export_advanced_metrics_for_job(job_dir: Path) -> Optional[Path]:
    """
    1つのジョブの高度指標を exports/metrics/ にエクスポートする。

    advanced_metrics.json が存在しない場合は計算してから書き出す。
    失敗しても例外を送出しない（worker 安全設計）。

    Returns
    -------
    Path or None
        advanced_metrics.jsonl のパス
    """
    try:
        from src.analysis.advanced_metrics import (
            load_advanced_metrics, compute_advanced_metrics_for_job,
        )

        job_dir = Path(job_dir)
        metrics = load_advanced_metrics(job_dir)
        if metrics is None or metrics.get("status") == "failed":
            compute_advanced_metrics_for_job(job_dir)
            metrics = load_advanced_metrics(job_dir)

        if metrics is None:
            logger.warning("[advanced_metrics_exporter] metrics が読み込めません: %s", job_dir.name)
            return None

        cfg      = _load_config()
        out_dir  = _REPO_ROOT / cfg.get("export", {}).get("output_dir", "exports/metrics")
        out_dir.mkdir(parents=True, exist_ok=True)

        flat = _flatten_metrics(metrics)

        # ── JSONL: 1ジョブ1行 ─────────────────────────────────────────────
        jsonl_path = out_dir / "advanced_metrics.jsonl"
        _append_to_jsonl(jsonl_path, flat)

        logger.info("[advanced_metrics_exporter] JSONL 書き出し完了: %s", jsonl_path)
        return jsonl_path

    except Exception as e:
        logger.error("[advanced_metrics_exporter] エクスポートエラー: %s — %s",
                     Path(job_dir).name, e)
        return None


def _append_to_jsonl(jsonl_path: Path, record: Dict[str, Any]) -> None:
    """JSONL ファイルにレコードを追記する（同じ job_id があれば上書き）。"""
    job_id = record.get("job_id")
    records: List[Dict[str, Any]] = []

    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("job_id") != job_id:
                    records.append(r)
            except Exception:
                records.append({"_raw": line})

    records.append(record)
    jsonl_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def export_all_advanced_metrics(base_jobs_dir: Optional[Path] = None) -> Path:
    """
    jobs/ 配下の全ジョブの高度指標を集約して CSV / JSON / JSONL に書き出す。

    Parameters
    ----------
    base_jobs_dir : Path, optional
        jobs/ ディレクトリ（デフォルトはリポジトリルートの jobs/）

    Returns
    -------
    Path
        CSV 出力パス
    """
    jobs_dir = base_jobs_dir or (_REPO_ROOT / "jobs")
    cfg      = _load_config()
    out_dir  = _REPO_ROOT / cfg.get("export", {}).get("output_dir", "exports/metrics")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_records: List[Dict[str, Any]] = []
    error_jobs: List[str] = []

    for job_dir in sorted(jobs_dir.iterdir()):
        if not job_dir.is_dir() or job_dir.name.startswith("_"):
            continue
        metrics_path = job_dir / "report" / "advanced_metrics.json"
        if not metrics_path.exists():
            continue
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            if metrics.get("status") == "failed":
                continue
            flat = _flatten_metrics(metrics)
            all_records.append(flat)
        except Exception as e:
            logger.warning("[advanced_metrics_exporter] ジョブスキップ: %s — %s", job_dir.name, e)
            error_jobs.append(job_dir.name)

    # ── JSON 集約 ─────────────────────────────────────────────────────────
    json_path = out_dir / "advanced_metrics.json"
    json_path.write_text(
        json.dumps({
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "total_jobs":  len(all_records),
            "error_jobs":  error_jobs,
            "records":     all_records,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── CSV ───────────────────────────────────────────────────────────────
    csv_path = out_dir / "advanced_metrics.csv"
    if all_records:
        fieldnames = list(all_records[0].keys())
        for r in all_records[1:]:
            for k in r:
                if k not in fieldnames:
                    fieldnames.append(k)

        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in all_records:
                writer.writerow({k: ("" if v is None else v) for k, v in r.items()
                                 for k in fieldnames if k in r})
    else:
        csv_path.write_text("no_data\n", encoding="utf-8-sig")

    # ── JSONL 再生成 ─────────────────────────────────────────────────────
    jsonl_path = out_dir / "advanced_metrics.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in all_records) + "\n",
        encoding="utf-8",
    )

    logger.info(
        "[advanced_metrics_exporter] 全ジョブエクスポート完了: %d件 → %s",
        len(all_records), out_dir,
    )
    return csv_path
