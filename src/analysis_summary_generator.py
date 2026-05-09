"""
src/analysis_summary_generator.py — Javelin Video Analysis 解析サマリー生成モジュール (v2)

pose_landmarks.csv を読み込み、ネスト構造の解析サマリーを
jobs/<job_id>/report/analysis_summary.json に保存する。

既存の src/analysis_summary.py とは別モジュール。
出力 JSON は video / pose_quality / key_metrics / warnings の4セクション構成。

Usage:
    from src.analysis_summary_generator import generate_analysis_summary_for_job
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

# ── 解析対象ランドマーク（可視性平均を計算する列） ────────────────────────────
_VISIBILITY_LANDMARKS = [
    "right_shoulder",
    "right_elbow",
    "right_wrist",
    "left_shoulder",
    "left_elbow",
    "left_wrist",
]

# ── torso center を計算するための肩・腰列 ────────────────────────────────────
_TORSO_COLS = [
    "left_shoulder_x", "left_shoulder_y",
    "right_shoulder_x", "right_shoulder_y",
    "left_hip_x", "left_hip_y",
    "right_hip_x", "right_hip_y",
]


# ── ユーティリティ ────────────────────────────────────────────────────────────

def _load_json(path: Path) -> Optional[dict]:
    """JSON ファイルを読み込む。失敗時は None を返す。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_json(path: Path, data: dict) -> None:
    """dict を UTF-8 の JSON ファイルとして保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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


# ── CSV 解析ロジック ─────────────────────────────────────────────────────────

def _compute_video_section(df: pd.DataFrame, warnings: list[str]) -> dict[str, Any]:
    """video セクション: duration_sec / frame_count を算出する。"""
    frame_count: int = len(df)
    duration_sec: Optional[float] = None

    if "time_sec" in df.columns:
        t_vals = df["time_sec"].dropna()
        if len(t_vals) >= 2:
            duration_sec = _safe_float(t_vals.max() - t_vals.min(), 3)
        else:
            warnings.append("time_sec 列の有効値が 2 件未満のため duration_sec を算出できませんでした。")
    else:
        warnings.append("time_sec 列が存在しないため duration_sec を算出できませんでした。")

    return {
        "duration_sec": duration_sec,
        "frame_count":  frame_count,
    }


def _compute_pose_quality_section(
    df: pd.DataFrame, warnings: list[str]
) -> dict[str, Any]:
    """
    pose_quality セクション:
      - right_wrist_missing_ratio: right_wrist_x が NaN のフレーム割合
      - average_visibility: 各ランドマークの visibility 平均
    """
    total = len(df)
    missing_ratio: Optional[float] = None

    if "right_wrist_x" in df.columns:
        n_missing = int(df["right_wrist_x"].isna().sum())
        missing_ratio = _safe_float(n_missing / total if total > 0 else 0.0, 4)
    else:
        warnings.append("right_wrist_x 列が存在しないため missing_ratio を算出できませんでした。")

    avg_visibility: dict[str, Optional[float]] = {}
    for lm in _VISIBILITY_LANDMARKS:
        col = f"{lm}_visibility"
        if col in df.columns:
            vals = df[col].dropna()
            avg_visibility[lm] = _safe_float(vals.mean(), 4) if len(vals) > 0 else None
        else:
            avg_visibility[lm] = None
            warnings.append(f"{col} 列が存在しないため {lm} の visibility を算出できませんでした。")

    return {
        "right_wrist_missing_ratio": missing_ratio,
        "average_visibility":        avg_visibility,
    }


def _compute_key_metrics_section(
    df: pd.DataFrame, warnings: list[str]
) -> dict[str, Any]:
    """
    key_metrics セクション:
      - right_wrist_max_height_time_sec: 右手首が最高到達時の time_sec
      - right_wrist_max_height_norm: その時の正規化高さ（1 - y）
      - torso_center_x_start / torso_center_x_end: 胴体中心 X の始点・終点
    """
    wrist_max_time: Optional[float] = None
    wrist_max_norm: Optional[float] = None

    required = ["time_sec", "right_wrist_y"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        warnings.append(
            f"right_wrist_max_height を算出するために必要な列がありません: {missing_cols}"
        )
    else:
        sub = df[["time_sec", "right_wrist_y"]].dropna()
        if sub.empty:
            warnings.append("time_sec / right_wrist_y の有効データが 0 件です。")
        else:
            # MediaPipe: y=0 が画面上部 → 高さ = 1 - y
            height = 1.0 - sub["right_wrist_y"]
            peak_loc = int(height.idxmax())
            wrist_max_norm = _safe_float(height.loc[peak_loc], 4)
            wrist_max_time = _safe_float(sub.loc[peak_loc, "time_sec"], 4)

    # torso center X（肩中心と腰中心の平均）
    torso_start: Optional[float] = None
    torso_end:   Optional[float] = None
    torso_missing = [c for c in _TORSO_COLS if c not in df.columns]
    if torso_missing:
        warnings.append(
            f"torso_center を算出するために必要な列がありません: {torso_missing}"
        )
    else:
        torso_df = df[_TORSO_COLS].dropna()
        if torso_df.empty:
            warnings.append("torso center 計算用の有効行が 0 件です。")
        else:
            shoulder_center_x = (
                torso_df["left_shoulder_x"] + torso_df["right_shoulder_x"]
            ) / 2.0
            hip_center_x = (
                torso_df["left_hip_x"] + torso_df["right_hip_x"]
            ) / 2.0
            torso_cx = (shoulder_center_x + hip_center_x) / 2.0
            torso_start = _safe_float(torso_cx.iloc[0],  4)
            torso_end   = _safe_float(torso_cx.iloc[-1], 4)

    return {
        "right_wrist_max_height_time_sec": wrist_max_time,
        "right_wrist_max_height_norm":     wrist_max_norm,
        "torso_center_x_start":            torso_start,
        "torso_center_x_end":              torso_end,
    }


def _build_summary(
    job_id: str,
    df: pd.DataFrame,
) -> dict[str, Any]:
    """DataFrame から最終的なサマリー dict を組み立てる。"""
    warnings: list[str] = []

    video_section       = _compute_video_section(df, warnings)
    pose_quality_section = _compute_pose_quality_section(df, warnings)
    key_metrics_section = _compute_key_metrics_section(df, warnings)

    return {
        "job_id":       job_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status":       "ok",
        "video":        video_section,
        "pose_quality": pose_quality_section,
        "key_metrics":  key_metrics_section,
        "warnings":     warnings,
    }


# ── report.json / job.json への追記 ─────────────────────────────────────────

def _append_summary_path_to_meta(
    job_dir: Path, rel_path: str
) -> None:
    """
    job.json または report.json に analysis_summary_json パスを追記する。
    どちらも存在しない場合はスキップ（例外を出さない）。
    """
    for meta_name in ("report.json", "job.json"):
        candidates = [
            job_dir / meta_name,
            job_dir / "output" / meta_name,
        ]
        for meta_path in candidates:
            if not meta_path.exists():
                continue
            try:
                meta = _load_json(meta_path) or {}
                if meta_name == "report.json":
                    meta.setdefault("report_files", {})["analysis_summary_json"] = rel_path
                else:
                    meta["analysis_summary_json"] = rel_path
                _save_json(meta_path, meta)
                logger.debug(
                    "[analysis_summary_generator] Updated %s with analysis_summary_json",
                    meta_path,
                )
            except Exception as exc:
                logger.warning(
                    "[analysis_summary_generator] %s 更新失敗 (スキップ): %s", meta_path, exc
                )
            break  # 最初に見つかったファイルだけ更新


# ── パブリック API ────────────────────────────────────────────────────────────

def generate_analysis_summary_for_job(job_dir: Path) -> Path:
    """
    ジョブディレクトリの CSV を読み込み、解析サマリー JSON を生成して返す。

    生成先: <job_dir>/report/analysis_summary.json

    Parameters
    ----------
    job_dir : Path
        jobs/<job_id>/ のパス。

    Returns
    -------
    Path
        生成された JSON ファイルのパス。

    Notes
    -----
    - CSV が存在しない・列が不足している場合でも例外を送出せず、
      status="skipped" の JSON を生成して返す。
    - MediaPipe の y 座標は上端=0 / 下端=1 のため、高さは 1 - y として扱う。
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "analysis_summary.json"

    # job_id を job.json から取得。なければディレクトリ名を使う
    job_meta = _load_json(job_dir / "job.json") or {}
    job_id: str = job_meta.get("job_id") or job_dir.name

    # CSV を探す
    csv_path = _find_csv(job_dir)
    if csv_path is None:
        payload: dict[str, Any] = {
            "job_id":       job_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "status":       "skipped",
            "reason":       "pose_landmarks.csv が見つかりません。",
            "video":        {"duration_sec": None, "frame_count": 0},
            "pose_quality": {
                "right_wrist_missing_ratio": None,
                "average_visibility":        {lm: None for lm in _VISIBILITY_LANDMARKS},
            },
            "key_metrics": {
                "right_wrist_max_height_time_sec": None,
                "right_wrist_max_height_norm":     None,
                "torso_center_x_start":            None,
                "torso_center_x_end":              None,
            },
            "warnings": ["pose_landmarks.csv が見つかりません。"],
        }
        _save_json(out_path, payload)
        logger.warning("[analysis_summary_generator] CSV not found → skipped: %s", job_dir)
        return out_path

    # CSV 読み込み
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except Exception as exc:
        payload = {
            "job_id":       job_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "status":       "skipped",
            "reason":       f"CSV 読み込みエラー: {exc}",
            "video":        {"duration_sec": None, "frame_count": 0},
            "pose_quality": {
                "right_wrist_missing_ratio": None,
                "average_visibility":        {lm: None for lm in _VISIBILITY_LANDMARKS},
            },
            "key_metrics": {
                "right_wrist_max_height_time_sec": None,
                "right_wrist_max_height_norm":     None,
                "torso_center_x_start":            None,
                "torso_center_x_end":              None,
            },
            "warnings": [f"CSV 読み込みエラー: {exc}"],
        }
        _save_json(out_path, payload)
        logger.warning("[analysis_summary_generator] CSV read error → skipped: %s", exc)
        return out_path

    if df.empty:
        payload = {
            "job_id":       job_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "status":       "skipped",
            "reason":       "pose_landmarks.csv が空です。",
            "video":        {"duration_sec": None, "frame_count": 0},
            "pose_quality": {
                "right_wrist_missing_ratio": None,
                "average_visibility":        {lm: None for lm in _VISIBILITY_LANDMARKS},
            },
            "key_metrics": {
                "right_wrist_max_height_time_sec": None,
                "right_wrist_max_height_norm":     None,
                "torso_center_x_start":            None,
                "torso_center_x_end":              None,
            },
            "warnings": ["pose_landmarks.csv が空です。"],
        }
        _save_json(out_path, payload)
        logger.warning("[analysis_summary_generator] CSV is empty → skipped: %s", csv_path)
        return out_path

    # サマリー計算
    try:
        summary = _build_summary(job_id, df)
    except Exception as exc:  # 予期しないエラーのセーフガード
        payload = {
            "job_id":       job_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "status":       "skipped",
            "reason":       f"サマリー計算エラー: {exc}",
            "video":        {"duration_sec": None, "frame_count": 0},
            "pose_quality": {
                "right_wrist_missing_ratio": None,
                "average_visibility":        {lm: None for lm in _VISIBILITY_LANDMARKS},
            },
            "key_metrics": {
                "right_wrist_max_height_time_sec": None,
                "right_wrist_max_height_norm":     None,
                "torso_center_x_start":            None,
                "torso_center_x_end":              None,
            },
            "warnings": [f"サマリー計算エラー: {exc}"],
        }
        _save_json(out_path, payload)
        logger.error("[analysis_summary_generator] Unexpected error: %s", exc, exc_info=True)
        return out_path

    summary["csv_source"] = str(csv_path.relative_to(job_dir))
    _save_json(out_path, summary)

    # report.json / job.json に相対パスを追記
    _append_summary_path_to_meta(job_dir, "report/analysis_summary.json")

    logger.info(
        "[analysis_summary_generator] Saved: %s  (frames=%d, warnings=%d)",
        out_path,
        df.shape[0],
        len(summary.get("warnings", [])),
    )
    return out_path
