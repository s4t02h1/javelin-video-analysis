"""
src/analysis/advanced_metrics.py — Phase 12 解析指標の高度化

MediaPipe 姿勢推定データと Phase 10/11 のフェーズ・イベントラベルをもとに、
やり投げ動作を競技的に理解しやすい参考指標として算出します。

⚠️  重要な注意事項
    - このモジュールが算出する指標は「参考値」です。
    - 動画上の座標から算出した相対指標であり、実際の距離・速度とは一致しない場合があります。
    - 撮影角度・姿勢推定精度・動画品質により数値が変動します。
    - 医療診断・怪我の診断・専門的競技指導の代替ではありません。
    - 断定的なフォーム評価ではなく、参考指標として活用してください。

出力ファイル: jobs/<job_id>/report/advanced_metrics.json
軌跡詳細:     jobs/<job_id>/report/advanced_trajectories.json

Usage:
    from src.analysis.advanced_metrics import compute_advanced_metrics_for_job
    from pathlib import Path

    out = compute_advanced_metrics_for_job(Path("jobs/20260508_070156_518a"))
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jva.advanced_metrics")

_MODULE_DIR   = Path(__file__).resolve().parent   # src/analysis/
_REPO_ROOT    = _MODULE_DIR.parent.parent          # project root

METRICS_VERSION = "0.1.0"

# ── 設定読み込み ──────────────────────────────────────────────────────────────

def _load_config() -> Dict[str, Any]:
    """configs/advanced_metrics.yaml を読み込む。"""
    cfg_path = _REPO_ROOT / "configs" / "advanced_metrics.yaml"
    try:
        import yaml  # type: ignore[import-not-found]
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("[advanced_metrics] 設定読み込み失敗: %s", e)
    return {}


# ── ファイルユーティリティ ────────────────────────────────────────────────────

def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[advanced_metrics] JSON 読み込み失敗: %s — %s", path.name, e)
        return None


def _find_csv(job_dir: Path) -> Optional[Path]:
    """pose_landmarks.csv を report/ → output/ → job_dir/ の順に探す。"""
    for candidate in [
        job_dir / "report" / "pose_landmarks.csv",
        job_dir / "output" / "pose_landmarks.csv",
        job_dir / "pose_landmarks.csv",
    ]:
        if candidate.exists():
            return candidate
    return None


def _load_csv(csv_path: Path) -> Optional[Any]:
    """CSV を pandas DataFrame として読み込む。"""
    try:
        import pandas as pd
        df = pd.read_csv(csv_path, encoding="utf-8")
        return df if not df.empty else None
    except Exception as e:
        logger.warning("[advanced_metrics] CSV 読み込み失敗: %s — %s", csv_path.name, e)
        return None


# ── 型安全ユーティリティ ──────────────────────────────────────────────────────

def _sf(val: Any, digits: int = 4) -> Optional[float]:
    """安全な float 変換。"""
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, digits)
    except (TypeError, ValueError):
        return None


def _si(val: Any) -> Optional[int]:
    """安全な int 変換。"""
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


# ── FPS 解決 ──────────────────────────────────────────────────────────────────

def _resolve_fps(
    quality_report: Optional[Dict[str, Any]],
    phase_frames: Optional[Dict[str, Any]],
    df: Any,
) -> float:
    """FPS を各ソースから解決する。デフォルト 30.0。"""
    # video_quality_report
    if quality_report:
        v = _sf(quality_report.get("fps"))
        if v and v > 0:
            return v
    # phase_frames.json
    if phase_frames:
        v = _sf(phase_frames.get("fps"))
        if v and v > 0:
            return v
    # DataFrame から推定
    if df is not None and "time_sec" in df.columns:
        try:
            t = df["time_sec"].dropna()
            if len(t) >= 2:
                elapsed = float(t.max() - t.min())
                if elapsed > 0:
                    return round((len(t) - 1) / elapsed, 2)
        except Exception:
            pass
    return 30.0


# ── フェーズフレーム解決 ──────────────────────────────────────────────────────

def _resolve_phase_frames(
    phase_frames_data: Optional[Dict[str, Any]],
    detection_result: Optional[Dict[str, Any]],
    corrections: Optional[Dict[str, Any]],
    annotation: Optional[Dict[str, Any]],
) -> Dict[str, Optional[int]]:
    """
    利用可能なソースから各フェーズのフレーム番号を解決する。

    優先順: annotation(confirmed) > phase_frames.json(手動) > corrections > auto detection
    """
    out: Dict[str, Optional[int]] = {}
    key_map = {
        "release_frame":              "release_frame",
        "block_frame":                "block_frame",
        "approach_start_frame":       "approach_start_frame",
        "approach_end_frame":         "approach_end_frame",
        "cross_step_start_frame":     "cross_step_start_frame",
        "cross_step_end_frame":       "cross_step_end_frame",
        "withdrawal_start_frame":     "withdrawal_start_frame",
        "withdrawal_end_frame":       "withdrawal_end_frame",
        "follow_through_start_frame": "follow_through_start_frame",
        "follow_through_end_frame":   "follow_through_end_frame",
        "recovery_start_frame":       "recovery_start_frame",
        "recovery_end_frame":         "recovery_end_frame",
    }

    # phase_frames.json (手動指定が最優先の現行設計)
    pf = phase_frames_data or {}

    # corrections から補完
    corr = corrections or {}
    # detection phases
    det_phases = {}
    if detection_result and detection_result.get("status") == "ok":
        det_phases = detection_result.get("phases", {})

    # Annotation からフレーム取得（confirmed の場合に使用）
    ann_frames: Dict[str, Optional[int]] = {}
    if annotation:
        pl = annotation.get("phase_labels", {})
        el = annotation.get("event_labels", {})
        ann_frames["release_frame"]              = _si(el.get("release", {}).get("frame"))
        ann_frames["block_frame"]                = _si(el.get("block_contact", {}).get("frame"))
        ann_frames["approach_start_frame"]       = _si(pl.get("approach", {}).get("start_frame"))
        ann_frames["approach_end_frame"]         = _si(pl.get("approach", {}).get("end_frame"))
        ann_frames["cross_step_start_frame"]     = _si(pl.get("cross_step", {}).get("start_frame"))
        ann_frames["cross_step_end_frame"]       = _si(pl.get("cross_step", {}).get("end_frame"))
        ann_frames["withdrawal_start_frame"]     = _si(pl.get("withdrawal", {}).get("start_frame"))
        ann_frames["withdrawal_end_frame"]       = _si(pl.get("withdrawal", {}).get("end_frame"))
        ann_frames["follow_through_start_frame"] = _si(pl.get("follow_through", {}).get("start_frame"))
        ann_frames["follow_through_end_frame"]   = _si(pl.get("follow_through", {}).get("end_frame"))
        ann_frames["recovery_start_frame"]       = _si(pl.get("recovery", {}).get("start_frame"))
        ann_frames["recovery_end_frame"]         = _si(pl.get("recovery", {}).get("end_frame"))

    # detection → corrections → phase_frames → annotation の順で priority
    # (手動確認済みを最優先)
    det_key_map = {
        "release_frame": "release",
        "block_frame": "block",
        "approach_start_frame": "approach_start",
        "approach_end_frame": "approach_end",
        "cross_step_start_frame": "cross_step_start",
        "cross_step_end_frame": "cross_step_end",
        "withdrawal_start_frame": "withdrawal_start",
        "withdrawal_end_frame": "withdrawal_end",
        "follow_through_start_frame": "follow_through_start",
        "follow_through_end_frame": "follow_through_end",
        "recovery_start_frame": "recovery_start",
        "recovery_end_frame": "recovery_end",
    }

    for k in key_map:
        v: Optional[int] = None
        # 1. auto detection
        det_k = det_key_map.get(k)
        if det_k and det_k in det_phases:
            v = _si(det_phases[det_k].get("frame"))
        # 2. corrections (manual_corrected_frame)
        if det_k and det_k in corr:
            corr_frame = corr[det_k].get("manual_corrected_frame")
            if corr_frame is not None:
                v = _si(corr_frame)
        # 3. phase_frames.json
        if pf.get(k) is not None:
            v = _si(pf[k])
        # 4. annotation (最優先)
        if ann_frames.get(k) is not None:
            v = ann_frames[k]
        out[k] = v

    return out


# ── フレームから time_sec を取得 ──────────────────────────────────────────────

def _frame_to_time(df: Any, frame: int, fps: float) -> Optional[float]:
    """frame番号に対応する time_sec を取得。なければ frame/fps で推定。"""
    try:
        if "frame" in df.columns:
            matches = df.loc[df["frame"] == frame, "time_sec"]
            if len(matches) > 0:
                return _sf(matches.iloc[0])
        # row-index方式
        if "time_sec" in df.columns and frame < len(df):
            return _sf(df.iloc[frame]["time_sec"])
    except Exception:
        pass
    return _sf(frame / fps) if fps > 0 else None


# ── 特定フレームのランドマーク値を取得 ────────────────────────────────────────

def _at(df: Any, frame: int, col: str) -> Optional[float]:
    """指定フレームの指定列の値を返す。"""
    try:
        if "frame" in df.columns:
            matches = df.loc[df["frame"] == frame, col]
            if len(matches) > 0:
                return _sf(matches.iloc[0])
        if col in df.columns and frame < len(df):
            return _sf(df.iloc[frame][col])
    except Exception:
        pass
    return None


def _at_range(df: Any, start: int, end: int, col: str) -> Any:
    """start〜end フレーム範囲の列を安全にスライスして返す。"""
    try:
        if "frame" in df.columns:
            mask = (df["frame"] >= start) & (df["frame"] <= end)
            return df.loc[mask, col].dropna() if col in df.columns else None
        n = len(df)
        s = max(0, start)
        e = min(n - 1, end)
        if s > e:
            return None
        return df.iloc[s:e + 1][col].dropna() if col in df.columns else None
    except Exception:
        return None


# ── 速度計算 ──────────────────────────────────────────────────────────────────

def _velocity_series(df: Any, col: str, fps: float, smooth: int = 3) -> Any:
    """指定列の速度系列（px/秒相当）を計算して返す。"""
    try:
        s = df[col].copy()
        if smooth > 1:
            s = s.rolling(window=smooth, center=True, min_periods=1).mean()
        return s.diff().abs() * fps
    except Exception:
        return None


def _velocity_at_frame(df: Any, frame: int, col: str, fps: float) -> Optional[float]:
    """指定フレーム付近の速度を返す。"""
    try:
        if "frame" in df.columns:
            idx_list = df.index[df["frame"] == frame].tolist()
            if not idx_list:
                return None
            idx = idx_list[0]
        else:
            idx = frame if frame < len(df) else None
            if idx is None:
                return None

        vel_series = _velocity_series(df, col, fps)
        if vel_series is None:
            return None
        return _sf(vel_series.iloc[idx])
    except Exception:
        return None


# ── 身体スケール（正規化基準）計算 ───────────────────────────────────────────

def _body_scale(df: Any, frame: Optional[int] = None) -> Optional[float]:
    """
    身体スケールを計算する（左右肩距離 or 肩〜腰距離の平均）。

    正規化の基準値として使用します。
    """
    try:
        cols = ["left_shoulder_x", "right_shoulder_x",
                "left_shoulder_y", "right_shoulder_y",
                "left_hip_y", "right_hip_y"]
        if not all(c in df.columns for c in cols):
            return None

        if frame is not None:
            row_l_sh_x = _at(df, frame, "left_shoulder_x")
            row_r_sh_x = _at(df, frame, "right_shoulder_x")
            row_l_sh_y = _at(df, frame, "left_shoulder_y")
            row_r_sh_y = _at(df, frame, "right_shoulder_y")
            row_l_hip_y = _at(df, frame, "left_hip_y")
            row_r_hip_y = _at(df, frame, "right_hip_y")
        else:
            # 動画全体の中央フレーム
            mid = len(df) // 2
            row_l_sh_x  = _sf(df.iloc[mid].get("left_shoulder_x"))
            row_r_sh_x  = _sf(df.iloc[mid].get("right_shoulder_x"))
            row_l_sh_y  = _sf(df.iloc[mid].get("left_shoulder_y"))
            row_r_sh_y  = _sf(df.iloc[mid].get("right_shoulder_y"))
            row_l_hip_y = _sf(df.iloc[mid].get("left_hip_y"))
            row_r_hip_y = _sf(df.iloc[mid].get("right_hip_y"))

        scales = []
        # 肩の横幅
        if row_l_sh_x is not None and row_r_sh_x is not None:
            scales.append(abs(row_l_sh_x - row_r_sh_x))
        # 左肩〜腰
        if row_l_sh_y is not None and row_l_hip_y is not None:
            scales.append(abs(row_l_hip_y - row_l_sh_y))
        # 右肩〜腰
        if row_r_sh_y is not None and row_r_hip_y is not None:
            scales.append(abs(row_r_hip_y - row_r_sh_y))

        if scales:
            return _sf(sum(scales) / len(scales))
    except Exception:
        pass
    return None


# ── ポーズ検出率 ──────────────────────────────────────────────────────────────

def _pose_detection_rate(df: Any, cols: Optional[List[str]] = None) -> float:
    """指定列群の検出率（非NaN率）を返す。"""
    try:
        key_cols = cols or [
            "left_shoulder_x", "right_shoulder_x",
            "left_wrist_x", "right_wrist_x",
            "left_hip_x", "right_hip_x",
        ]
        available = [c for c in key_cols if c in df.columns]
        if not available:
            return 0.0
        sub = df[available]
        total = len(sub) * len(available)
        valid = sub.count().sum()
        return round(valid / total, 4) if total > 0 else 0.0
    except Exception:
        return 0.0


# ── Reliability 計算 ─────────────────────────────────────────────────────────

def _reliability(
    video_quality: str = "unknown",
    pose_detection_rate: float = 0.0,
    is_manual_frame: bool = False,
    confidence: Optional[float] = None,
    filming_angle: str = "unknown",
) -> str:
    """
    指標の信頼度を 4段階（high / medium / low / unknown）で返す。

    高い信頼度の条件:
    - 動画品質が good
    - 姿勢推定検出率が high 基準以上
    - 手動フレーム指定済み
    - 撮影角度が side（横方向）
    """
    cfg = _load_config().get("reliability", {})
    min_high   = float(cfg.get("min_pose_detection_rate_high",   0.85))
    min_medium = float(cfg.get("min_pose_detection_rate_medium", 0.65))
    low_conf   = float(cfg.get("low_confidence_threshold",       0.45))

    # 即 low 条件
    if video_quality == "low":
        return "low"
    if pose_detection_rate < min_medium:
        return "low"
    if confidence is not None and confidence < low_conf:
        return "low"

    # high 条件
    score = 0
    if video_quality == "good":
        score += 2
    elif video_quality == "medium":
        score += 1

    if pose_detection_rate >= min_high:
        score += 2
    elif pose_detection_rate >= min_medium:
        score += 1

    if is_manual_frame:
        score += 1

    if confidence is not None and confidence >= 0.75:
        score += 1

    if filming_angle in ("side",):
        score += 1

    if score >= 5:
        return "high"
    elif score >= 2:
        return "medium"
    elif score > 0:
        return "low"
    return "unknown"


def _met(value: Any, unit: str = "", reliability: str = "unknown",
         note: str = "") -> Dict[str, Any]:
    """メトリクスエントリ dict を生成する。"""
    return {
        "value":       _sf(value) if isinstance(value, (int, float)) else value,
        "unit":        unit,
        "reliability": reliability,
        "note":        note or "動画上の座標から算出した参考値です。実際の値とは異なる場合があります。",
    }


# ── 角度計算 ─────────────────────────────────────────────────────────────────

def _angle_2d(
    p1x: float, p1y: float,
    vertex_x: float, vertex_y: float,
    p2x: float, p2y: float,
) -> Optional[float]:
    """
    3点の2D角度（vertex における p1-vertex-p2 の角度, 度）を計算する。
    """
    try:
        v1x, v1y = p1x - vertex_x, p1y - vertex_y
        v2x, v2y = p2x - vertex_x, p2y - vertex_y
        mag1 = math.sqrt(v1x ** 2 + v1y ** 2)
        mag2 = math.sqrt(v2x ** 2 + v2y ** 2)
        if mag1 < 1e-8 or mag2 < 1e-8:
            return None
        cos_val = (v1x * v2x + v1y * v2y) / (mag1 * mag2)
        cos_val = max(-1.0, min(1.0, cos_val))
        return _sf(math.degrees(math.acos(cos_val)), 2)
    except Exception:
        return None


def _line_angle(x1: float, y1: float, x2: float, y2: float) -> Optional[float]:
    """2点を結ぶ直線の水平に対する角度（度）を返す。"""
    try:
        dx, dy = x2 - x1, y2 - y1
        return _sf(math.degrees(math.atan2(-dy, dx)), 2)  # y反転（MediaPipe座標系）
    except Exception:
        return None


# ── リリース関連指標 ──────────────────────────────────────────────────────────

def _compute_release_metrics(
    df: Any,
    fps: float,
    dominant_arm: str,
    phase_frames: Dict[str, Optional[int]],
    body_scale: Optional[float],
    video_quality: str,
    filming_angle: str,
    is_manual_release: bool,
    detection_confidence: Optional[float],
) -> Dict[str, Any]:
    """リリース関連指標を計算する。"""
    release_frame = phase_frames.get("release_frame")
    if release_frame is None:
        return {"available": False, "reason": "release_frame が指定されていません"}

    rel = reliability = _reliability(
        video_quality=video_quality,
        pose_detection_rate=_pose_detection_rate(df),
        is_manual_frame=is_manual_release,
        confidence=detection_confidence,
        filming_angle=filming_angle,
    )

    wrist_y_col     = f"{dominant_arm}_wrist_y"
    wrist_x_col     = f"{dominant_arm}_wrist_x"
    elbow_y_col     = f"{dominant_arm}_elbow_y"
    shoulder_y_col  = f"{dominant_arm}_shoulder_y"
    shoulder_x_col  = f"{dominant_arm}_shoulder_x"

    release_time = _frame_to_time(df, release_frame, fps)

    # 手首高さ（MediaPipe: y=0が上 → 高さ = 1-y）
    wrist_y   = _at(df, release_frame, wrist_y_col)
    wrist_h   = _sf(1.0 - wrist_y) if wrist_y is not None else None

    # 肩高さ
    sh_y      = _at(df, release_frame, shoulder_y_col)
    sh_h      = _sf(1.0 - sh_y) if sh_y is not None else None

    # 肘高さ
    elbow_y   = _at(df, release_frame, elbow_y_col)
    elbow_h   = _sf(1.0 - elbow_y) if elbow_y is not None else None

    # 手首高さ正規化（body_scale で割る）
    wrist_h_norm = _sf(wrist_h / body_scale) if (wrist_h is not None and body_scale and body_scale > 0) else None

    # 手首高さ vs 肩（相対）
    wrist_h_rel_sh = _sf(wrist_h - sh_h) if (wrist_h is not None and sh_h is not None) else None

    # 肘高さ vs 肩（相対）
    elbow_h_rel_sh = _sf(elbow_h - sh_h) if (elbow_h is not None and sh_h is not None) else None

    # 手首速度
    wrist_vel_y = _velocity_at_frame(df, release_frame, wrist_y_col, fps)
    wrist_vel_x = _velocity_at_frame(df, release_frame, wrist_x_col, fps)
    wrist_vel = None
    if wrist_vel_y is not None and wrist_vel_x is not None:
        wrist_vel = _sf(math.sqrt(wrist_vel_y ** 2 + wrist_vel_x ** 2))
    elif wrist_vel_y is not None:
        wrist_vel = wrist_vel_y

    # wrist_vel は already in normalized_coord/sec。body_scale で割るだけで body_scale/sec になる
    wrist_vel_norm = _sf(wrist_vel / body_scale) if (
        wrist_vel is not None and body_scale and body_scale > 0
    ) else None

    # 肩手首距離（腕の伸び具合）
    wrist_x  = _at(df, release_frame, wrist_x_col)
    sh_x     = _at(df, release_frame, shoulder_x_col)
    hand_sh_dist = None
    if wrist_x is not None and wrist_y is not None and sh_x is not None and sh_y is not None:
        hand_sh_dist = _sf(math.sqrt((wrist_x - sh_x) ** 2 + (wrist_y - sh_y) ** 2))

    # 腕伸展率（肩〜手首距離 / 肩〜肘〜手首合計）
    arm_ext_ratio = None
    if dominant_arm + "_elbow_x" in df.columns if df is not None else False:
        elbow_x = _at(df, release_frame, f"{dominant_arm}_elbow_x")
        if (elbow_x is not None and elbow_y is not None
                and sh_x is not None and sh_y is not None
                and wrist_x is not None and wrist_y is not None):
            seg1 = math.sqrt((elbow_x - sh_x) ** 2 + (elbow_y - sh_y) ** 2)
            seg2 = math.sqrt((wrist_x - elbow_x) ** 2 + (wrist_y - elbow_y) ** 2)
            seg_total = seg1 + seg2
            straight  = math.sqrt((wrist_x - sh_x) ** 2 + (wrist_y - sh_y) ** 2)
            if seg_total > 1e-8:
                arm_ext_ratio = _sf(straight / seg_total)

    # 体幹前傾推定（リリース時）
    trunk_angle = _trunk_angle_at_frame(df, release_frame)

    # 肩ライン傾き
    sh_line_tilt = _shoulder_line_angle_at(df, release_frame)

    # 腰ライン傾き
    hip_line_tilt = _hip_line_angle_at(df, release_frame)

    return {
        "available":                         True,
        "release_frame":                     release_frame,
        "release_time_sec":                  release_time,
        "release_wrist_height_px":           _met(wrist_h, "px(normalized)", rel),
        "release_wrist_height_normalized":   _met(wrist_h_norm, "body_scale", rel),
        "release_wrist_height_relative_to_shoulder": _met(wrist_h_rel_sh, "body_scale", rel,
            "手首高さから肩高さを引いた相対値（正=手首が肩より高い）"),
        "release_elbow_height_relative_to_shoulder": _met(elbow_h_rel_sh, "body_scale", rel,
            "肘高さから肩高さを引いた相対値"),
        "release_shoulder_height":           _met(sh_h, "px(normalized)", rel),
        "release_hand_to_shoulder_distance": _met(hand_sh_dist, "px(normalized)", rel,
            "リリース時の肩〜手首間距離（相対値）"),
        "release_wrist_velocity_px_per_sec": _met(wrist_vel, "px/sec(relative)", rel,
            "動画フレーム間の手首移動速度（相対値・実速度とは異なります）"),
        "release_wrist_velocity_normalized": _met(wrist_vel_norm, "body_scale/sec", rel),
        "release_arm_extension_ratio":       _met(arm_ext_ratio, "ratio(0-1)", rel,
            "腕の直線的伸展度（肩〜手首の直線距離 / 肩〜肘〜手首経路距離）"),
        "release_trunk_angle_estimate":      _met(trunk_angle, "degrees(2D estimate)", rel,
            "リリース時の体幹前傾推定（2D画像上の見かけ角度）"),
        "release_shoulder_line_tilt":        _met(sh_line_tilt, "degrees(2D estimate)", rel,
            "リリース時の肩ラインの傾き（2D推定）"),
        "release_hip_line_tilt":             _met(hip_line_tilt, "degrees(2D estimate)", rel,
            "リリース時の腰ラインの傾き（2D推定）"),
    }


# ── 角度計算ヘルパー ─────────────────────────────────────────────────────────

def _shoulder_line_angle_at(df: Any, frame: int) -> Optional[float]:
    """指定フレームの肩ライン角度（水平からの傾き度）を返す。"""
    l_x = _at(df, frame, "left_shoulder_x")
    l_y = _at(df, frame, "left_shoulder_y")
    r_x = _at(df, frame, "right_shoulder_x")
    r_y = _at(df, frame, "right_shoulder_y")
    if None in (l_x, l_y, r_x, r_y):
        return None
    return _line_angle(l_x, l_y, r_x, r_y)  # type: ignore[arg-type]


def _hip_line_angle_at(df: Any, frame: int) -> Optional[float]:
    """指定フレームの腰ライン角度を返す。"""
    l_x = _at(df, frame, "left_hip_x")
    l_y = _at(df, frame, "left_hip_y")
    r_x = _at(df, frame, "right_hip_x")
    r_y = _at(df, frame, "right_hip_y")
    if None in (l_x, l_y, r_x, r_y):
        return None
    return _line_angle(l_x, l_y, r_x, r_y)  # type: ignore[arg-type]


def _trunk_angle_at_frame(df: Any, frame: int) -> Optional[float]:
    """指定フレームの体幹前傾角（肩中心〜腰中心を結ぶ直線の垂直からの角度）を返す。"""
    try:
        l_sh_x = _at(df, frame, "left_shoulder_x")
        r_sh_x = _at(df, frame, "right_shoulder_x")
        l_sh_y = _at(df, frame, "left_shoulder_y")
        r_sh_y = _at(df, frame, "right_shoulder_y")
        l_hp_x = _at(df, frame, "left_hip_x")
        r_hp_x = _at(df, frame, "right_hip_x")
        l_hp_y = _at(df, frame, "left_hip_y")
        r_hp_y = _at(df, frame, "right_hip_y")

        if None in (l_sh_x, r_sh_x, l_sh_y, r_sh_y, l_hp_x, r_hp_x, l_hp_y, r_hp_y):
            return None

        sc_x = (l_sh_x + r_sh_x) / 2  # type: ignore[operator]
        sc_y = (l_sh_y + r_sh_y) / 2  # type: ignore[operator]
        hc_x = (l_hp_x + r_hp_x) / 2  # type: ignore[operator]
        hc_y = (l_hp_y + r_hp_y) / 2  # type: ignore[operator]

        # 垂直方向に対する角度（MediaPipe: y下方向）
        dx = sc_x - hc_x
        dy = hc_y - sc_y  # 下向きが正（腰が下）
        if abs(dy) < 1e-8:
            return None
        angle = math.degrees(math.atan2(abs(dx), abs(dy)))
        return _sf(angle, 2)
    except Exception:
        return None


# ── ブロック関連指標 ──────────────────────────────────────────────────────────

def _compute_block_metrics(
    df: Any,
    fps: float,
    dominant_arm: str,
    phase_frames: Dict[str, Optional[int]],
    body_scale: Optional[float],
    video_quality: str,
    filming_angle: str,
    is_manual_block: bool,
    detection_confidence: Optional[float],
) -> Dict[str, Any]:
    """ブロック関連指標を計算する。"""
    block_frame   = phase_frames.get("block_frame")
    release_frame = phase_frames.get("release_frame")

    if block_frame is None:
        return {"available": False, "reason": "block_frame が指定されていません"}

    rel = _reliability(
        video_quality=video_quality,
        pose_detection_rate=_pose_detection_rate(df),
        is_manual_frame=is_manual_block,
        confidence=detection_confidence,
        filming_angle=filming_angle,
    )

    # ブロック脚は投げ腕の逆側
    block_leg_side = "left" if dominant_arm == "right" else "right"

    block_time  = _frame_to_time(df, block_frame, fps)
    release_time = _frame_to_time(df, release_frame, fps) if release_frame else None

    # ブロック〜リリース間
    b2r_frames = None
    b2r_sec    = None
    if release_frame is not None and block_frame is not None:
        b2r_frames = release_frame - block_frame
        if block_time is not None and release_time is not None:
            b2r_sec = _sf(release_time - block_time)

    # ブロック脚の足首・膝安定性（ブロック前後数フレームの位置変動）
    ankle_col = f"{block_leg_side}_ankle_y"
    knee_col  = f"{block_leg_side}_knee_y"
    window    = max(1, int(fps * 0.1))  # ±0.1秒

    ankle_stab = _landmark_stability(df, block_frame, ankle_col, window)
    knee_stab  = _landmark_stability(df, block_frame, knee_col, window)

    # 腰中心速度（ブロック前後）
    hip_vel_before = _hip_velocity_before(df, block_frame, fps, window)
    hip_vel_after  = _hip_velocity_after(df, block_frame, fps, window)
    decel_ratio = None
    if hip_vel_before is not None and hip_vel_after is not None and hip_vel_before > 1e-8:
        decel_ratio = _sf(hip_vel_after / hip_vel_before)

    # 体幹前傾変化（ブロック前後）
    trunk_at_block   = _trunk_angle_at_frame(df, block_frame)
    trunk_at_release = _trunk_angle_at_frame(df, release_frame) if release_frame else None
    trunk_change = None
    if trunk_at_block is not None and trunk_at_release is not None:
        trunk_change = _sf(trunk_at_release - trunk_at_block)

    # 肩回旋変化（ブロック前後の肩ライン角度差）
    sh_at_block   = _shoulder_line_angle_at(df, block_frame)
    sh_at_release = _shoulder_line_angle_at(df, release_frame) if release_frame else None
    sh_rot_change = None
    if sh_at_block is not None and sh_at_release is not None:
        sh_rot_change = _sf(sh_at_release - sh_at_block)

    # 腰回旋変化
    hip_at_block   = _hip_line_angle_at(df, block_frame)
    hip_at_release = _hip_line_angle_at(df, release_frame) if release_frame else None
    hip_rot_change = None
    if hip_at_block is not None and hip_at_release is not None:
        hip_rot_change = _sf(hip_at_release - hip_at_block)

    return {
        "available":                    True,
        "block_frame":                  block_frame,
        "block_time_sec":               block_time,
        "block_leg_side":               block_leg_side,
        "block_leg_note":               f"{'右' if dominant_arm == 'right' else '左'}投げのため{'左' if block_leg_side == 'left' else '右'}脚がブロック脚候補です（手動変更可）",
        "front_ankle_stability_score":  _met(ankle_stab, "std(normalized)", rel,
            "ブロック前後の足首位置安定性（値が小さいほど安定）"),
        "front_knee_stability_score":   _met(knee_stab, "std(normalized)", rel,
            "ブロック前後の膝位置安定性（値が小さいほど安定）"),
        "hip_center_velocity_before_block": _met(hip_vel_before, "px/sec(relative)", rel,
            "ブロック直前の腰中心速度（相対値）"),
        "hip_center_velocity_after_block":  _met(hip_vel_after, "px/sec(relative)", rel,
            "ブロック直後の腰中心速度（相対値）"),
        "hip_deceleration_ratio":       _met(decel_ratio, "ratio(after/before)", rel,
            "ブロック前後の腰速度比（1.0=変化なし, <1.0=減速）"),
        "trunk_forward_change_around_block": _met(trunk_change, "degrees(2D estimate)", rel,
            "ブロック時からリリースまでの体幹前傾変化量（2D推定）"),
        "shoulder_rotation_change_around_block": _met(sh_rot_change, "degrees(2D estimate)", rel,
            "ブロック〜リリース間の肩ライン回旋変化量（2D推定）"),
        "hip_rotation_change_around_block":      _met(hip_rot_change, "degrees(2D estimate)", rel,
            "ブロック〜リリース間の腰ライン回旋変化量（2D推定）"),
        "block_to_release_frames":      b2r_frames,
        "block_to_release_time_sec":    _met(b2r_sec, "sec", rel,
            "ブロック候補フレームからリリース候補フレームまでの時間（参考値）"),
    }


def _landmark_stability(df: Any, frame: int, col: str, window: int) -> Optional[float]:
    """指定フレーム前後 window フレームのランドマーク位置標準偏差を返す。"""
    try:
        start = max(0, frame - window)
        end   = min(len(df) - 1, frame + window)
        series = _at_range(df, start, end, col)
        if series is None or len(series) < 2:
            return None
        return _sf(float(series.std()), 4)
    except Exception:
        return None


def _hip_velocity_before(df: Any, frame: int, fps: float, window: int) -> Optional[float]:
    """ブロック直前の腰中心速度（平均）。"""
    return _hip_center_velocity(df, max(0, frame - window), frame, fps)


def _hip_velocity_after(df: Any, frame: int, fps: float, window: int) -> Optional[float]:
    """ブロック直後の腰中心速度（平均）。"""
    return _hip_center_velocity(df, frame, min(len(df) - 1, frame + window), fps)


def _hip_center_velocity(df: Any, start: int, end: int, fps: float) -> Optional[float]:
    """指定フレーム範囲の腰中心速度（平均）を計算する。"""
    try:
        if not all(c in df.columns for c in ["left_hip_x", "right_hip_x"]):
            return None
        sx = _at_range(df, start, end, "left_hip_x")
        rx = _at_range(df, start, end, "right_hip_x")
        if sx is None or rx is None:
            return None
        import pandas as pd
        cx = (sx.reset_index(drop=True) + rx.reset_index(drop=True)) / 2
        vel = cx.diff().abs() * fps
        return _sf(float(vel.mean()))
    except Exception:
        return None


# ── 体幹・肩腰分離指標 ──────────────────────────────────────────────────────

def _compute_trunk_metrics(
    df: Any,
    fps: float,
    phase_frames: Dict[str, Optional[int]],
    body_scale: Optional[float],
    video_quality: str,
    filming_angle: str,
) -> Dict[str, Any]:
    """体幹・肩腰分離指標を計算する。"""
    block_frame   = phase_frames.get("block_frame")
    release_frame = phase_frames.get("release_frame")

    rel = _reliability(
        video_quality=video_quality,
        pose_detection_rate=_pose_detection_rate(df),
        filming_angle=filming_angle,
    )

    def _separation_at(frame: Optional[int]) -> Optional[float]:
        if frame is None:
            return None
        sh_a = _shoulder_line_angle_at(df, frame)
        hp_a = _hip_line_angle_at(df, frame)
        if sh_a is None or hp_a is None:
            return None
        return _sf(abs(sh_a - hp_a))

    # 全フレームにわたる肩腰分離角の最大・平均
    sep_series = _shoulder_hip_separation_series(df)
    sep_max    = _sf(float(sep_series.max())) if sep_series is not None else None
    sep_mean   = _sf(float(sep_series.mean())) if sep_series is not None else None

    # ブロック時・リリース時・変化量
    sep_at_block   = _separation_at(block_frame)
    sep_at_release = _separation_at(release_frame)
    sep_change = None
    if sep_at_block is not None and sep_at_release is not None:
        sep_change = _sf(sep_at_release - sep_at_block)

    # 体幹傾き系列から統計
    trunk_at_block   = _trunk_angle_at_frame(df, block_frame) if block_frame else None
    trunk_at_release = _trunk_angle_at_frame(df, release_frame) if release_frame else None

    # ブロック前の体幹前傾（前傾が大きいほど踏み込みが積極的な傾向）
    trunk_forward_before_block = None
    if block_frame is not None:
        pre_window = max(1, int(fps * 0.15))
        pre_start  = max(0, block_frame - pre_window)
        trunk_vals = []
        for f in range(pre_start, block_frame + 1):
            v = _trunk_angle_at_frame(df, f)
            if v is not None:
                trunk_vals.append(v)
        if trunk_vals:
            trunk_forward_before_block = _sf(sum(trunk_vals) / len(trunk_vals))

    note_2d = "2D動画上の見かけの角度推定です。3Dの正確な回旋角とは異なります。撮影角度（横方向が最適）の影響を受けます。"

    return {
        "available":                              True,
        "shoulder_line_angle_at_block":           _met(
            _shoulder_line_angle_at(df, block_frame) if block_frame else None,
            "degrees(2D estimate)", rel, note_2d),
        "shoulder_line_angle_at_release":         _met(
            _shoulder_line_angle_at(df, release_frame) if release_frame else None,
            "degrees(2D estimate)", rel, note_2d),
        "hip_line_angle_at_block":                _met(
            _hip_line_angle_at(df, block_frame) if block_frame else None,
            "degrees(2D estimate)", rel, note_2d),
        "hip_line_angle_at_release":              _met(
            _hip_line_angle_at(df, release_frame) if release_frame else None,
            "degrees(2D estimate)", rel, note_2d),
        "shoulder_hip_separation_angle_estimate_at_block":   _met(sep_at_block, "degrees(2D estimate)", rel, note_2d),
        "shoulder_hip_separation_angle_estimate_at_release": _met(sep_at_release, "degrees(2D estimate)", rel, note_2d),
        "shoulder_hip_separation_max":            _met(sep_max, "degrees(2D estimate)", rel, note_2d),
        "shoulder_hip_separation_mean":           _met(sep_mean, "degrees(2D estimate)", rel, note_2d),
        "trunk_tilt_estimate_at_block":           _met(trunk_at_block, "degrees(2D estimate)", rel, note_2d),
        "trunk_tilt_estimate_at_release":         _met(trunk_at_release, "degrees(2D estimate)", rel, note_2d),
        "trunk_opening_before_release":           _met(trunk_forward_before_block, "degrees(2D estimate)", rel, note_2d),
        "trunk_opening_at_release":               _met(sep_at_release, "degrees(2D estimate)", rel, note_2d),
        "trunk_opening_change_from_block_to_release": _met(sep_change, "degrees(2D estimate)", rel, note_2d),
    }


def _shoulder_hip_separation_series(df: Any) -> Any:
    """全フレームの肩腰分離角系列を返す。"""
    try:
        import pandas as pd
        results = []
        for i in range(len(df)):
            sh = _shoulder_line_angle_at(df, i)
            hp = _hip_line_angle_at(df, i)
            if sh is not None and hp is not None:
                results.append(abs(sh - hp))
            else:
                results.append(None)
        s = pd.Series(results).dropna()
        return s if len(s) > 0 else None
    except Exception:
        return None


# ── 投げ腕関連指標 ──────────────────────────────────────────────────────────

def _compute_arm_metrics(
    df: Any,
    fps: float,
    dominant_arm: str,
    phase_frames: Dict[str, Optional[int]],
    body_scale: Optional[float],
    video_quality: str,
    filming_angle: str,
    detection_confidence: Optional[float],
) -> Dict[str, Any]:
    """投げ腕関連指標を計算する。"""
    release_frame   = phase_frames.get("release_frame")
    withdrawal_start = phase_frames.get("withdrawal_start_frame")
    withdrawal_end   = phase_frames.get("withdrawal_end_frame")

    rel = _reliability(
        video_quality=video_quality,
        pose_detection_rate=_pose_detection_rate(df),
        filming_angle=filming_angle,
        confidence=detection_confidence,
    )

    wrist_y_col  = f"{dominant_arm}_wrist_y"
    wrist_x_col  = f"{dominant_arm}_wrist_x"
    elbow_x_col  = f"{dominant_arm}_elbow_x"
    elbow_y_col  = f"{dominant_arm}_elbow_y"
    sh_x_col     = f"{dominant_arm}_shoulder_x"
    sh_y_col     = f"{dominant_arm}_shoulder_y"

    # 手首軌跡（全体）
    wrist_y = df[wrist_y_col].dropna() if wrist_y_col in df.columns else None
    wrist_x = df[wrist_x_col].dropna() if wrist_x_col in df.columns else None

    path_len = None
    if wrist_x is not None and wrist_y is not None:
        try:
            import pandas as pd
            wx = df[wrist_x_col].ffill().bfill()
            wy = df[wrist_y_col].ffill().bfill()
            dx = wx.diff()
            dy = wy.diff()
            path_len = _sf(float((dx ** 2 + dy ** 2).pow(0.5).sum()))
        except Exception:
            pass

    # 手首最高高さ
    wrist_max_h = _sf(1.0 - float(df[wrist_y_col].min())) if wrist_y_col in df.columns else None
    wrist_min_h = _sf(1.0 - float(df[wrist_y_col].max())) if wrist_y_col in df.columns else None

    # 手首速度ピーク
    wrist_peak_vel = None
    if wrist_y_col in df.columns:
        try:
            vel_x = _velocity_series(df, wrist_x_col, fps) if wrist_x_col in df.columns else None
            vel_y = _velocity_series(df, wrist_y_col, fps)
            if vel_x is not None and vel_y is not None:
                import pandas as pd
                total_vel = (vel_x ** 2 + vel_y ** 2).pow(0.5)
                wrist_peak_vel = _sf(float(total_vel.max()))
            elif vel_y is not None:
                wrist_peak_vel = _sf(float(vel_y.max()))
        except Exception:
            pass

    # リリース時の手首速度
    wrist_vel_at_rel = None
    if release_frame is not None:
        wrist_vel_at_rel = _velocity_at_frame(df, release_frame, wrist_y_col, fps)

    # 肘角度（リリース時）
    elbow_angle_at_rel = None
    elbow_angle_rel = "unknown"
    if release_frame is not None:
        sh_x  = _at(df, release_frame, sh_x_col)
        sh_y  = _at(df, release_frame, sh_y_col)
        el_x  = _at(df, release_frame, elbow_x_col)
        el_y  = _at(df, release_frame, elbow_y_col)
        wr_x  = _at(df, release_frame, wrist_x_col)
        wr_y  = _at(df, release_frame, wrist_y_col)
        if None not in (sh_x, sh_y, el_x, el_y, wr_x, wr_y):
            elbow_angle_at_rel = _angle_2d(
                sh_x, sh_y, el_x, el_y, wr_x, wr_y  # type: ignore[arg-type]
            )
            elbow_angle_rel = rel

    # 肩肘手首整列スコア（リリース時の直線性）
    alignment_score = None
    if release_frame is not None:
        sh_x = _at(df, release_frame, sh_x_col)
        sh_y = _at(df, release_frame, sh_y_col)
        el_x = _at(df, release_frame, elbow_x_col)
        el_y = _at(df, release_frame, elbow_y_col)
        wr_x = _at(df, release_frame, wrist_x_col)
        wr_y = _at(df, release_frame, wrist_y_col)
        if None not in (sh_x, sh_y, el_x, el_y, wr_x, wr_y):
            a = elbow_angle_at_rel or 180.0
            # 肘角度が180度に近いほど整列度が高い
            alignment_score = _sf(min(1.0, a / 180.0))

    # 引き動作距離推定（withdrawal フェーズの手首X移動量）
    pullback_dist = None
    withdrawal_max_frame = withdrawal_end
    if withdrawal_start is not None and withdrawal_end is not None:
        wr_start = _at(df, withdrawal_start, wrist_x_col)
        wr_end   = _at(df, withdrawal_end, wrist_x_col)
        if wr_start is not None and wr_end is not None:
            pullback_dist = _sf(abs(wr_end - wr_start))

    # withdrawal〜release 時間
    w2r_sec = None
    if withdrawal_end is not None and release_frame is not None:
        t_w = _frame_to_time(df, withdrawal_end, fps)
        t_r = _frame_to_time(df, release_frame, fps)
        if t_w is not None and t_r is not None:
            w2r_sec = _sf(t_r - t_w)

    note = "2D動画上の推定値です。撮影角度・姿勢推定精度の影響を受けます。"
    return {
        "available":                       True,
        "throwing_wrist_path_length":      _met(path_len, "px(relative)", rel,
            "投げ腕手首の全軌跡長（相対値）"),
        "throwing_wrist_max_height":       _met(wrist_max_h, "px(normalized)", rel),
        "throwing_wrist_min_height":       _met(wrist_min_h, "px(normalized)", rel),
        "throwing_wrist_peak_velocity":    _met(wrist_peak_vel, "px/sec(relative)", rel,
            "投げ腕手首の最大速度（相対値）"),
        "throwing_wrist_velocity_at_release": _met(wrist_vel_at_rel, "px/sec(relative)", rel),
        "elbow_angle_estimate_at_release": _met(elbow_angle_at_rel, "degrees(2D estimate)",
            elbow_angle_rel, "リリース時の肘角度2D推定（正面・背面撮影では誤差が大きくなります）"),
        "shoulder_elbow_wrist_alignment_score": _met(alignment_score, "ratio(0-1)", rel,
            "リリース時の肩〜肘〜手首の整列度（1.0=完全直線、参考値）"),
        "arm_pullback_distance_estimate":  _met(pullback_dist, "px(relative)", rel,
            "槍引き動作中の手首移動距離推定（相対値）"),
        "withdrawal_max_frame":            withdrawal_max_frame,
        "withdrawal_to_release_time_sec":  _met(w2r_sec, "sec", rel,
            "槍引き完了からリリースまでの時間（参考値）"),
    }


# ── 軌跡指標 ─────────────────────────────────────────────────────────────────

def _compute_trajectory_metrics(
    df: Any,
    fps: float,
    dominant_arm: str,
    phase_frames: Dict[str, Optional[int]],
    body_scale: Optional[float],
    video_quality: str,
    filming_angle: str,
) -> Dict[str, Any]:
    """軌跡関連指標を計算する。詳細軌跡は advanced_trajectories.json に保存する。"""
    release_frame = phase_frames.get("release_frame")

    rel = _reliability(
        video_quality=video_quality,
        pose_detection_rate=_pose_detection_rate(df),
        filming_angle=filming_angle,
    )

    wrist_y_col  = f"{dominant_arm}_wrist_y"
    wrist_x_col  = f"{dominant_arm}_wrist_x"

    # 手首軌跡ピーク高さフレーム
    wrist_peak_h_frame = None
    if wrist_y_col in df.columns:
        try:
            wrist_h_series = 1.0 - df[wrist_y_col]
            wrist_peak_h_frame = int(wrist_h_series.idxmax())
        except Exception:
            pass

    # 手首軌跡スムーズネス（速度系列の変動係数）
    smoothness = None
    if wrist_y_col in df.columns:
        try:
            vel_y = _velocity_series(df, wrist_y_col, fps)
            if vel_y is not None:
                m = float(vel_y.mean())
                s = float(vel_y.std())
                smoothness = _sf(s / m) if m > 1e-8 else None
        except Exception:
            pass

    # リリース窓（±5フレーム）の手首高さ統計
    release_window_stats = {}
    if release_frame is not None and wrist_y_col in df.columns:
        try:
            w_start = max(0, release_frame - 5)
            w_end   = min(len(df) - 1, release_frame + 5)
            series  = _at_range(df, w_start, w_end, wrist_y_col)
            if series is not None and len(series) > 0:
                release_window_stats = {
                    "mean_wrist_height": _sf(float(1.0 - series.mean())),
                    "std_wrist_height":  _sf(float(series.std())),
                }
        except Exception:
            pass

    # 腰中心前方トレンド（X方向の移動傾向）
    forward_trend = None
    if all(c in df.columns for c in ["left_hip_x", "right_hip_x"]):
        try:
            cx = (df["left_hip_x"] + df["right_hip_x"]) / 2.0
            cx_clean = cx.dropna()
            if len(cx_clean) >= 2:
                forward_trend = _sf(float(cx_clean.iloc[-1] - cx_clean.iloc[0]))
        except Exception:
            pass

    # 肩中心軌跡
    sh_path_len = None
    if all(c in df.columns for c in ["left_shoulder_x", "right_shoulder_x",
                                      "left_shoulder_y", "right_shoulder_y"]):
        try:
            scx = (df["left_shoulder_x"] + df["right_shoulder_x"]) / 2
            scy = (df["left_shoulder_y"] + df["right_shoulder_y"]) / 2
            dx  = scx.diff()
            dy  = scy.diff()
            sh_path_len = _sf(float((dx ** 2 + dy ** 2).pow(0.5).sum()))
        except Exception:
            pass

    # 安定性スコア（速度変動の小ささ）
    traj_stab = None
    if smoothness is not None:
        traj_stab = "high" if smoothness < 0.5 else "medium" if smoothness < 1.0 else "low"

    return {
        "available":                       True,
        "wrist_trajectory_peak_height_frame": wrist_peak_h_frame,
        "wrist_trajectory_smoothness":     _met(smoothness, "CV(coeff_of_variation)", rel,
            "手首速度の変動係数（小さいほど滑らか）"),
        "wrist_trajectory_release_window": release_window_stats,
        "hip_center_forward_trend":        _met(forward_trend, "px(relative)", rel,
            "動画全体での腰中心の前方移動量（正=前進）"),
        "shoulder_center_path_length":     _met(sh_path_len, "px(relative)", rel,
            "肩中心の全軌跡長（相対値）"),
        "trajectory_stability_score":      traj_stab,
        "note":                            "詳細軌跡データは advanced_trajectories.json に保存されます。",
    }


def _build_trajectories(
    df: Any,
    dominant_arm: str,
    phase_frames: Dict[str, Optional[int]],
    fps: float,
) -> Dict[str, Any]:
    """advanced_trajectories.json 用のデータを構築する。"""
    def _series_to_list(col: str) -> List[Optional[float]]:
        if col not in df.columns:
            return []
        try:
            return [_sf(v) for v in df[col].tolist()]
        except Exception:
            return []

    result: Dict[str, Any] = {
        "fps":           fps,
        "total_frames":  len(df),
        "phase_frames":  {k: v for k, v in phase_frames.items()},
    }

    for side in ("left", "right"):
        for lm in ("wrist", "elbow", "shoulder", "hip", "knee", "ankle"):
            for axis in ("x", "y"):
                col = f"{side}_{lm}_{axis}"
                if col in df.columns:
                    result[col] = _series_to_list(col)

    if "time_sec" in df.columns:
        result["time_sec"] = _series_to_list("time_sec")

    return result


# ── フェーズ別指標 ────────────────────────────────────────────────────────────

def _compute_phase_metrics(
    df: Any,
    fps: float,
    dominant_arm: str,
    phase_frames: Dict[str, Optional[int]],
    body_scale: Optional[float],
    video_quality: str,
) -> Dict[str, Any]:
    """フェーズ別指標を計算する。"""
    phase_defs = [
        ("approach",       "approach_start_frame",       "approach_end_frame"),
        ("cross_step",     "cross_step_start_frame",     "cross_step_end_frame"),
        ("withdrawal",     "withdrawal_start_frame",     "withdrawal_end_frame"),
        ("follow_through", "follow_through_start_frame", "follow_through_end_frame"),
        ("recovery",       "recovery_start_frame",       "recovery_end_frame"),
    ]
    point_phases = [
        ("block",   "block_frame"),
        ("release", "release_frame"),
    ]

    result: Dict[str, Any] = {}
    wrist_y_col = f"{dominant_arm}_wrist_y"

    def _phase_rel(start: Optional[int], end: Optional[int]) -> str:
        if start is None or end is None:
            return "unknown"
        return _reliability(video_quality=video_quality,
                            pose_detection_rate=_pose_detection_rate(df))

    for phase_name, start_key, end_key in phase_defs:
        s = phase_frames.get(start_key)
        e = phase_frames.get(end_key)
        dur_frames = (e - s) if (s is not None and e is not None) else None
        dur_sec    = _sf(dur_frames / fps) if (dur_frames is not None and fps > 0) else None

        # 手首高さ変化
        wh_change = None
        if s is not None and e is not None and wrist_y_col in df.columns:
            wy_s = _at(df, s, wrist_y_col)
            wy_e = _at(df, e, wrist_y_col)
            if wy_s is not None and wy_e is not None:
                wh_change = _sf((1.0 - wy_e) - (1.0 - wy_s))

        # 腰中心移動
        hip_move = None
        if s is not None and e is not None:
            hip_cx_s = _hip_center_x(df, s)
            hip_cx_e = _hip_center_x(df, e)
            if hip_cx_s is not None and hip_cx_e is not None:
                hip_move = _sf(abs(hip_cx_e - hip_cx_s))

        # 肩中心移動
        sh_move = None
        if s is not None and e is not None:
            sh_cx_s = _shoulder_center_x(df, s)
            sh_cx_e = _shoulder_center_x(df, e)
            if sh_cx_s is not None and sh_cx_e is not None:
                sh_move = _sf(abs(sh_cx_e - sh_cx_s))

        # 体幹角度変化
        trunk_change = None
        if s is not None and e is not None:
            ta_s = _trunk_angle_at_frame(df, s)
            ta_e = _trunk_angle_at_frame(df, e)
            if ta_s is not None and ta_e is not None:
                trunk_change = _sf(ta_e - ta_s)

        # 検出率（このフェーズ内の主要ランドマーク検出率）
        phase_det_rate = None
        if s is not None and e is not None:
            try:
                sub = df.iloc[max(0, s):min(len(df), e + 1)]
                phase_det_rate = _sf(_pose_detection_rate(sub))
            except Exception:
                pass

        rel = _phase_rel(s, e)

        result[phase_name] = {
            "start_frame":              s,
            "end_frame":                e,
            "duration_frames":          dur_frames,
            "duration_sec":             dur_sec,
            "wrist_height_change":      _met(wh_change, "px(normalized)", rel,
                "フェーズ開始〜終了の手首高さ変化（正=上昇傾向）"),
            "hip_center_movement":      _met(hip_move, "px(relative)", rel,
                "フェーズ内の腰中心X軸移動量（相対値）"),
            "shoulder_center_movement": _met(sh_move, "px(relative)", rel,
                "フェーズ内の肩中心X軸移動量（相対値）"),
            "trunk_angle_change":       _met(trunk_change, "degrees(2D estimate)", rel,
                "フェーズ内の体幹前傾角変化量（2D推定）"),
            "pose_detection_rate_in_phase": phase_det_rate,
            "phase_reliability":        rel,
        }

    # 点フェーズ（block, release）
    for phase_name, frame_key in point_phases:
        f = phase_frames.get(frame_key)
        time_s = _frame_to_time(df, f, fps) if f is not None else None
        rel = _reliability(video_quality=video_quality,
                           pose_detection_rate=_pose_detection_rate(df)) if f else "unknown"
        result[phase_name] = {
            "frame":              f,
            "time_sec":           time_s,
            "phase_reliability":  rel,
        }

    return result


def _hip_center_x(df: Any, frame: int) -> Optional[float]:
    l_x = _at(df, frame, "left_hip_x")
    r_x = _at(df, frame, "right_hip_x")
    if l_x is None or r_x is None:
        return None
    return _sf((l_x + r_x) / 2)


def _shoulder_center_x(df: Any, frame: int) -> Optional[float]:
    l_x = _at(df, frame, "left_shoulder_x")
    r_x = _at(df, frame, "right_shoulder_x")
    if l_x is None or r_x is None:
        return None
    return _sf((l_x + r_x) / 2)


# ── 比較用指標 ──────────────────────────────────────────────────────────────

def _comparison_ready_metrics(
    release_metrics: Dict[str, Any],
    block_metrics: Dict[str, Any],
    trunk_metrics: Dict[str, Any],
    arm_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    """比較ジョブで使いやすい主要指標をフラット化して返す。"""
    def _val(d: Dict[str, Any], key: str) -> Optional[float]:
        entry = d.get(key)
        if isinstance(entry, dict):
            return entry.get("value")
        return _sf(entry) if entry is not None else None

    out: Dict[str, Any] = {}

    if release_metrics.get("available"):
        out["release_wrist_height_normalized"]   = _val(release_metrics, "release_wrist_height_normalized")
        out["release_wrist_velocity_normalized"]  = _val(release_metrics, "release_wrist_velocity_normalized")
        out["release_arm_extension_ratio"]        = _val(release_metrics, "release_arm_extension_ratio")
        out["release_trunk_angle_estimate"]       = _val(release_metrics, "release_trunk_angle_estimate")
        out["release_shoulder_line_tilt"]         = _val(release_metrics, "release_shoulder_line_tilt")

    if block_metrics.get("available"):
        out["block_to_release_time_sec"]  = _val(block_metrics, "block_to_release_time_sec")
        out["hip_deceleration_ratio"]     = _val(block_metrics, "hip_deceleration_ratio")
        out["shoulder_rotation_change_around_block"] = _val(block_metrics, "shoulder_rotation_change_around_block")
        out["hip_rotation_change_around_block"]      = _val(block_metrics, "hip_rotation_change_around_block")

    if trunk_metrics.get("available"):
        out["shoulder_hip_separation_angle_estimate"] = _val(
            trunk_metrics, "shoulder_hip_separation_angle_estimate_at_release")
        out["trunk_opening_at_release"]   = _val(trunk_metrics, "trunk_opening_at_release")

    if arm_metrics.get("available"):
        out["throwing_wrist_peak_velocity"]  = _val(arm_metrics, "throwing_wrist_peak_velocity")
        out["arm_pullback_distance_estimate"] = _val(arm_metrics, "arm_pullback_distance_estimate")
        out["withdrawal_to_release_time_sec"] = _val(arm_metrics, "withdrawal_to_release_time_sec")

    return out


# ── メイン計算関数 ────────────────────────────────────────────────────────────

def compute_advanced_metrics(
    job_dir: Path,
    annotation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    ジョブディレクトリから高度解析指標を計算して返す（保存はしない）。

    Parameters
    ----------
    job_dir : Path
    annotation_id : str, optional
        指定すると annotation.json からフレーム情報を優先使用する

    Returns
    -------
    dict
        advanced_metrics dict
    """
    job_dir = Path(job_dir)
    cfg = _load_config()

    if not cfg.get("enabled", True):
        return {
            "job_id":          job_dir.name,
            "status":          "disabled",
            "metrics_version": METRICS_VERSION,
            "generated_at":    datetime.now().isoformat(timespec="seconds"),
        }

    # ── データ読み込み ────────────────────────────────────────────────────────
    job_data         = _load_json(job_dir / "job.json") or {}
    customer_info    = _load_json(job_dir / "customer_info.json") or {}
    phase_frames_raw = _load_json(job_dir / "phase_frames.json") or {}
    detection_result = _load_json(job_dir / "report" / "phase_detection_result.json") or {}
    corrections      = _load_json(job_dir / "report" / "phase_corrections.json") or {}
    quality_report   = _load_json(job_dir / "report" / "video_quality_report.json") or {}

    annotation: Optional[Dict[str, Any]] = None
    if annotation_id and cfg.get("use_annotations_if_available", True):
        try:
            from src.annotation.manager import load_annotation
            annotation = load_annotation(annotation_id)
        except Exception:
            pass
    elif cfg.get("use_annotations_if_available", True):
        # job_id から annotation を自動検索
        try:
            from src.annotation.manager import find_annotation_for_job
            annotation = find_annotation_for_job(job_dir.name)
        except Exception:
            pass

    # ── 基本情報 ──────────────────────────────────────────────────────────────
    job_id = job_data.get("job_id") or job_dir.name
    dominant_arm = (
        customer_info.get("dominant_arm")
        or customer_info.get("dominant_hand")
        or detection_result.get("dominant_arm")
        or "right"
    )
    filming_angle = (
        customer_info.get("filming_angle")
        or customer_info.get("camera_angle")
        or "unknown"
    )

    # ── CSV 読み込み ──────────────────────────────────────────────────────────
    csv_path = _find_csv(job_dir)
    df = _load_csv(csv_path) if csv_path else None
    has_csv = df is not None

    # ── FPS ──────────────────────────────────────────────────────────────────
    fps = _resolve_fps(quality_report or None, phase_frames_raw or None, df)

    # ── フェーズフレーム解決 ──────────────────────────────────────────────────
    use_manual_first = cfg.get("use_manual_phase_labels_first", True)
    phase_frames = _resolve_phase_frames(
        phase_frames_raw if use_manual_first else None,
        detection_result or None,
        corrections or None,
        annotation,
    )

    # ── 動画品質 ──────────────────────────────────────────────────────────────
    overall_quality = quality_report.get("overall_quality", "unknown") if quality_report else "unknown"

    # ── 姿勢推定検出率 ────────────────────────────────────────────────────────
    pose_det_rate = _pose_detection_rate(df) if has_csv else 0.0

    # ── メトリクス信頼度（全体） ──────────────────────────────────────────────
    overall_reliability = _reliability(
        video_quality=overall_quality,
        pose_detection_rate=pose_det_rate,
        filming_angle=filming_angle,
    )

    # ── 警告リスト ────────────────────────────────────────────────────────────
    warnings: List[str] = []
    if not has_csv:
        warnings.append("pose_landmarks.csv が見つかりません。姿勢推定データが使用できません。")
    if overall_quality in ("low", "unknown"):
        warnings.append(f"動画品質が '{overall_quality}' です。指標の信頼度が低くなる場合があります。")
    if pose_det_rate < 0.65:
        warnings.append(f"姿勢推定検出率が低めです（{pose_det_rate:.0%}）。欠損フレームが多い場合があります。")
    if filming_angle not in ("side", "unknown"):
        warnings.append(f"撮影角度 '{filming_angle}' では2D角度推定の誤差が大きくなる可能性があります。")

    # ── 身体スケール ──────────────────────────────────────────────────────────
    bs = _body_scale(df) if has_csv else None

    # ── 手動/自動 フレーム判定 ────────────────────────────────────────────────
    is_manual_release = phase_frames_raw.get("release_frame") is not None
    is_manual_block   = phase_frames_raw.get("block_frame") is not None
    det_confidence = None
    if detection_result and detection_result.get("status") == "ok":
        rel_phase = detection_result.get("phases", {}).get("release", {})
        det_confidence = _sf(rel_phase.get("confidence"))

    # ── 各種指標計算 ──────────────────────────────────────────────────────────
    if has_csv:
        release_metrics  = _compute_release_metrics(
            df, fps, dominant_arm, phase_frames, bs, overall_quality,
            filming_angle, is_manual_release, det_confidence)
        block_metrics    = _compute_block_metrics(
            df, fps, dominant_arm, phase_frames, bs, overall_quality,
            filming_angle, is_manual_block, det_confidence)
        trunk_metrics    = _compute_trunk_metrics(
            df, fps, phase_frames, bs, overall_quality, filming_angle)
        arm_metrics      = _compute_arm_metrics(
            df, fps, dominant_arm, phase_frames, bs, overall_quality,
            filming_angle, det_confidence)
        trajectory_metrics = _compute_trajectory_metrics(
            df, fps, dominant_arm, phase_frames, bs, overall_quality, filming_angle)
        phase_metrics    = _compute_phase_metrics(
            df, fps, dominant_arm, phase_frames, bs, overall_quality)
    else:
        no_data = {"available": False, "reason": "姿勢推定データ（CSV）がありません"}
        release_metrics = block_metrics = trunk_metrics = arm_metrics = no_data
        trajectory_metrics = no_data
        phase_metrics = {}

    comp_metrics = _comparison_ready_metrics(
        release_metrics, block_metrics, trunk_metrics, arm_metrics)

    result: Dict[str, Any] = {
        "job_id":            job_id,
        "dominant_arm":      dominant_arm,
        "fps":               fps,
        "metrics_version":   METRICS_VERSION,
        "generated_at":      datetime.now().isoformat(timespec="seconds"),
        "status":            "ok",
        "quality": {
            "overall_quality":    overall_quality,
            "metrics_reliability": overall_reliability,
            "pose_detection_rate": pose_det_rate,
            "filming_angle":       filming_angle,
            "warnings":            warnings,
        },
        "release_metrics":          release_metrics,
        "block_metrics":            block_metrics,
        "trunk_metrics":            trunk_metrics,
        "arm_metrics":              arm_metrics,
        "trajectory_metrics":       trajectory_metrics,
        "phase_metrics":            phase_metrics,
        "comparison_ready_metrics": comp_metrics,
    }

    return result


# ── 保存・読み込み ────────────────────────────────────────────────────────────

def save_advanced_metrics(metrics: Dict[str, Any], job_dir: Path) -> Path:
    """advanced_metrics.json を job_dir/report/ に保存する。"""
    report_dir = Path(job_dir) / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "advanced_metrics.json"
    out_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[advanced_metrics] 保存完了: %s", out_path)
    return out_path


def save_advanced_trajectories(df: Any, dominant_arm: str,
                                phase_frames: Dict[str, Optional[int]],
                                fps: float, job_dir: Path) -> Optional[Path]:
    """advanced_trajectories.json を job_dir/report/ に保存する。"""
    try:
        report_dir = Path(job_dir) / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        traj_path = report_dir / "advanced_trajectories.json"
        traj_data = _build_trajectories(df, dominant_arm, phase_frames, fps)
        traj_path.write_text(
            json.dumps(traj_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("[advanced_metrics] 軌跡データ保存完了: %s", traj_path)
        return traj_path
    except Exception as e:
        logger.warning("[advanced_metrics] 軌跡データ保存失敗: %s", e)
        return None


def load_advanced_metrics(job_dir: Path) -> Optional[Dict[str, Any]]:
    """advanced_metrics.json を読み込む。存在しない場合は None を返す。"""
    return _load_json(Path(job_dir) / "report" / "advanced_metrics.json")


# ── メインエントリーポイント ──────────────────────────────────────────────────

def compute_advanced_metrics_for_job(job_dir: Path) -> Path:
    """
    高度解析指標を計算して保存し、パスを返す。

    失敗時は status=failed の JSON を保存して例外を送出しない（worker 安全設計）。

    Parameters
    ----------
    job_dir : Path

    Returns
    -------
    Path
        advanced_metrics.json のパス
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "advanced_metrics.json"

    try:
        metrics = compute_advanced_metrics(job_dir)
        save_advanced_metrics(metrics, job_dir)

        # 軌跡データも保存
        csv_path = _find_csv(job_dir)
        df = _load_csv(csv_path) if csv_path else None
        if df is not None:
            phase_frames_raw = _load_json(job_dir / "phase_frames.json") or {}
            detection_result = _load_json(job_dir / "report" / "phase_detection_result.json") or {}
            corrections      = _load_json(job_dir / "report" / "phase_corrections.json") or {}
            customer_info    = _load_json(job_dir / "customer_info.json") or {}
            dominant_arm = (
                customer_info.get("dominant_arm")
                or customer_info.get("dominant_hand")
                or detection_result.get("dominant_arm")
                or "right"
            )
            quality_report = _load_json(job_dir / "report" / "video_quality_report.json") or {}
            fps = _resolve_fps(quality_report or None, phase_frames_raw or None, df)
            phase_frames = _resolve_phase_frames(
                phase_frames_raw or None,
                detection_result or None,
                corrections or None,
                None,
            )
            save_advanced_trajectories(df, dominant_arm, phase_frames, fps, job_dir)

        logger.info("[advanced_metrics] ジョブ %s の高度指標計算完了", job_dir.name)
        return out_path

    except Exception as e:
        logger.error("[advanced_metrics] 計算エラー: %s — %s", job_dir.name, e)
        failed_payload = {
            "job_id":          job_dir.name,
            "status":          "failed",
            "error":           str(e)[:500],
            "metrics_version": METRICS_VERSION,
            "generated_at":    datetime.now().isoformat(timespec="seconds"),
        }
        out_path.write_text(
            json.dumps(failed_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return out_path
