"""
src/analysis_summary.py — Javelin Video Analysis 解析サマリー生成モジュール

pose_landmarks.csv と customer_info.json を読み込み、
解析結果の要点を jobs/<job_id>/report/analysis_summary.json に保存する。

Usage:
    from src.analysis_summary import generate_analysis_summary_for_job
    from pathlib import Path
    summary_path = generate_analysis_summary_for_job(Path("jobs/20260508_181930_c4bd"))
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _load_json(path: Path) -> Optional[dict]:
    """JSON ファイルを読み込む。失敗時は None を返す。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_csv(csv_path: Path) -> "Optional[pd.DataFrame]":
    """CSV を読み込んで DataFrame を返す。失敗時は None を返す。"""
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
        if df.empty:
            return None
        return df
    except Exception as exc:
        logger.warning("[analysis_summary] CSV 読み込み失敗: %s — %s", csv_path, exc)
        return None


def _safe_float(val: Any, digits: int = 4) -> Optional[float]:
    """数値に変換できれば round して返す。失敗時は None。"""
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return None


def _find_csv(job_dir: Path) -> Optional[Path]:
    """pose_landmarks.csv を report/ > output/ > job_dir/ の順に探す。"""
    for candidate in [
        job_dir / "report" / "pose_landmarks.csv",
        job_dir / "output" / "pose_landmarks.csv",
        job_dir / "pose_landmarks.csv",
    ]:
        if candidate.exists():
            return candidate
    return None


def _compute_summary(df: pd.DataFrame, dominant_hand: str) -> dict[str, Any]:
    """DataFrame から各種統計値を計算して dict で返す。"""
    side = dominant_hand if dominant_hand in ("right", "left") else "right"

    total_frames: int = len(df)

    # FPS 推定: time_sec 列があれば使う
    fps_estimated: Optional[float] = None
    duration_sec: Optional[float] = None
    if "time_sec" in df.columns:
        t_vals = df["time_sec"].dropna()
        if len(t_vals) >= 2:
            duration_sec = _safe_float(t_vals.max() - t_vals.min(), 2)
            elapsed = t_vals.max() - t_vals.min()
            if elapsed > 0:
                fps_estimated = _safe_float((len(t_vals) - 1) / elapsed, 2)

    result: dict[str, Any] = {
        "total_frames":  total_frames,
        "duration_sec":  duration_sec,
        "fps_estimated": fps_estimated,
        "dominant_hand": dominant_hand,
    }

    # ── 手首高さ（MediaPipe: 上=0 なので反転して高さに）─────────────────────
    wrist_y_col = f"{side}_wrist_y"
    if "time_sec" in df.columns and wrist_y_col in df.columns:
        wrist_df = df[[wrist_y_col, "time_sec"]].dropna()
        if not wrist_df.empty:
            # 反転して "高さ" にする（0=低、1=高）
            height_series = 1.0 - wrist_df[wrist_y_col]
            peak_idx = int(height_series.idxmax())

            result.update({
                "wrist_height_min":        _safe_float(height_series.min()),
                "wrist_height_max":        _safe_float(height_series.max()),
                "wrist_height_range":      _safe_float(height_series.max() - height_series.min()),
                "wrist_height_peak_frame": int(peak_idx),
                "wrist_height_peak_time_sec": _safe_float(
                    wrist_df.loc[peak_idx, "time_sec"]
                ),
            })
    else:
        result.update({
            "wrist_height_min":           None,
            "wrist_height_max":           None,
            "wrist_height_range":         None,
            "wrist_height_peak_frame":    None,
            "wrist_height_peak_time_sec": None,
        })

    # ── 肩中心 X（横方向移動）────────────────────────────────────────────────
    sh_l_x = "left_shoulder_x"
    sh_r_x = "right_shoulder_x"
    if sh_l_x in df.columns and sh_r_x in df.columns:
        sh_df = df[[sh_l_x, sh_r_x]].dropna()
        if not sh_df.empty:
            sc_x = (sh_df[sh_l_x] + sh_df[sh_r_x]) / 2.0
            result["shoulder_center_x_start"] = _safe_float(sc_x.iloc[0])
            result["shoulder_center_x_end"]   = _safe_float(sc_x.iloc[-1])
        else:
            result["shoulder_center_x_start"] = None
            result["shoulder_center_x_end"]   = None
    else:
        result["shoulder_center_x_start"] = None
        result["shoulder_center_x_end"]   = None

    # ── 腰中心 X ─────────────────────────────────────────────────────────────
    hip_l_x = "left_hip_x"
    hip_r_x = "right_hip_x"
    if hip_l_x in df.columns and hip_r_x in df.columns:
        hip_df = df[[hip_l_x, hip_r_x]].dropna()
        if not hip_df.empty:
            hc_x = (hip_df[hip_l_x] + hip_df[hip_r_x]) / 2.0
            result["hip_center_x_start"] = _safe_float(hc_x.iloc[0])
            result["hip_center_x_end"]   = _safe_float(hc_x.iloc[-1])
        else:
            result["hip_center_x_start"] = None
            result["hip_center_x_end"]   = None
    else:
        result["hip_center_x_start"] = None
        result["hip_center_x_end"]   = None

    return result


def generate_analysis_summary_for_job(job_dir: Path) -> Path:
    """
    ジョブディレクトリの CSV を読み込み、解析サマリー JSON を生成して返す。

    生成先: jobs/<job_id>/report/analysis_summary.json

    Parameters
    ----------
    job_dir : Path
        ジョブのルートディレクトリ（例: jobs/20260508_070156_518a）

    Returns
    -------
    Path
        生成した analysis_summary.json のパス

    Notes
    -----
    CSV が存在しない / 読み込めない場合は status="skipped" の JSON を生成し、
    例外は送出しない。
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "analysis_summary.json"

    # ─ dominant_hand を customer_info.json から取得 ──────────────────────────
    dominant_hand = "right"
    ci_path = job_dir / "customer_info.json"
    if ci_path.exists():
        ci = _load_json(ci_path) or {}
        hand = (ci.get("dominant_hand") or "right").strip().lower()
        if hand == "left":
            dominant_hand = "left"

    # ─ CSV を探す ─────────────────────────────────────────────────────────────
    csv_path = _find_csv(job_dir)
    if csv_path is None:
        payload: dict[str, Any] = {
            "status":       "skipped",
            "reason":       "pose_landmarks.csv が見つかりませんでした",
            "dominant_hand": dominant_hand,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.warning("[analysis_summary] CSV なし → skipped: %s", job_dir)
        return out_path

    # ─ CSV 読み込み ───────────────────────────────────────────────────────────
    df = _load_csv(csv_path)
    if df is None:
        payload = {
            "status":       "skipped",
            "reason":       f"CSV の読み込みに失敗しました: {csv_path.name}",
            "dominant_hand": dominant_hand,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.warning("[analysis_summary] CSV 読み込み失敗 → skipped: %s", csv_path)
        return out_path

    # ─ 統計計算 ───────────────────────────────────────────────────────────────
    try:
        stats = _compute_summary(df, dominant_hand)
    except Exception as exc:
        payload = {
            "status":       "skipped",
            "reason":       f"計算エラー: {exc}",
            "dominant_hand": dominant_hand,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.warning("[analysis_summary] 計算エラー → skipped: %s", exc)
        return out_path

    payload = {
        "status":       "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "csv_source":   str(csv_path.relative_to(job_dir)),
        **stats,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        "[analysis_summary] Saved: %s  (frames=%d, hand=%s)",
        out_path, stats.get("total_frames", 0), dominant_hand,
    )
    return out_path
