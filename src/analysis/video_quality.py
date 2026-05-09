"""
src/analysis/video_quality.py — Javelin Video Analysis 動画品質チェック (Phase 10)

pose_landmarks.csv の姿勢推定データから動画の解析適性を評価します。

出力ファイル: jobs/<job_id>/report/video_quality_report.json

⚠️  注意事項
    - このチェックは解析の参考情報です。動画の撮影条件や解析精度の把握に使ってください。
    - 品質スコアは絶対評価ではありません。
    - 解析結果そのものを保証するものではありません。

Usage:
    from src.analysis.video_quality import check_video_quality_for_job
    from pathlib import Path

    result = check_video_quality_for_job(Path("jobs/20260508_070156_518a"))
    # -> Path("jobs/20260508_070156_518a/report/video_quality_report.json")
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.video_quality")

_MODULE_DIR = Path(__file__).resolve().parent   # src/analysis/
_REPO_ROOT  = _MODULE_DIR.parent.parent         # project root

# ── MediaPipe ランドマーク定義（data_exporter.py と対応）─────────────────────
_LANDMARK_NAMES = [
    "nose",
    "left_shoulder", "right_shoulder",
    "left_elbow",    "right_elbow",
    "left_wrist",    "right_wrist",
    "left_hip",      "right_hip",
    "left_knee",     "right_knee",
    "left_ankle",    "right_ankle",
]

# 重要ランドマーク（フェーズ推定に使用するもの）
_KEY_LANDMARKS = [
    "left_shoulder", "right_shoulder",
    "left_wrist",    "right_wrist",
    "left_elbow",    "right_elbow",
    "left_hip",      "right_hip",
    "left_ankle",    "right_ankle",
]


def _load_config() -> Dict[str, Any]:
    """configs/phase_detection.yaml の quality_thresholds を読み込む。"""
    cfg_path = _REPO_ROOT / "configs" / "phase_detection.yaml"
    try:
        import yaml  # type: ignore[import-not-found]
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return (data or {}).get("quality_thresholds", {})
    except Exception:
        pass
    return {}


def _find_csv(job_dir: Path) -> Optional[Path]:
    for candidate in [
        job_dir / "report" / "pose_landmarks.csv",
        job_dir / "output" / "pose_landmarks.csv",
        job_dir / "pose_landmarks.csv",
    ]:
        if candidate.exists():
            return candidate
    return None


def _load_csv(csv_path: Path) -> Optional[Any]:
    try:
        import pandas as pd
        df = pd.read_csv(csv_path, encoding="utf-8")
        return df if not df.empty else None
    except Exception as e:
        logger.warning("[video_quality] CSV 読み込み失敗: %s — %s", csv_path, e)
        return None


def _safe_float(val: Any, digits: int = 4) -> Optional[float]:
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return None


def _compute_quality(
    df: Any,
    fps: Optional[float],
    total_frames: Optional[int],
    thresholds: Dict[str, Any],
    dominant_arm: str = "right",
) -> Dict[str, Any]:
    """DataFrame から品質指標を計算して返す。"""
    import pandas as pd

    total = total_frames or len(df)
    warnings_list: List[str] = []
    landmark_stats: Dict[str, Any] = {}

    # ── FPS / 動画長 ─────────────────────────────────────────────────────────
    fps_estimated: Optional[float] = fps
    duration_sec: Optional[float] = None

    if "time_sec" in df.columns:
        t_vals = df["time_sec"].dropna()
        if len(t_vals) >= 2:
            duration_sec = _safe_float(t_vals.max() - t_vals.min(), 2)
            elapsed = float(t_vals.max() - t_vals.min())
            if fps_estimated is None and elapsed > 0:
                fps_estimated = _safe_float((len(t_vals) - 1) / elapsed, 2)

    # ── FPS チェック ──────────────────────────────────────────────────────────
    min_fps = float(thresholds.get("min_fps", 24.0))
    if fps_estimated is not None and fps_estimated < min_fps:
        warnings_list.append(
            f"動画のFPS（推定値: {fps_estimated:.1f}）が低めです（推奨: {min_fps:.0f} FPS 以上）。"
            "解析精度に影響する可能性があります。"
        )

    # ── 動画長チェック ────────────────────────────────────────────────────────
    min_dur = float(thresholds.get("min_duration_sec", 2.0))
    if duration_sec is not None and duration_sec < min_dur:
        warnings_list.append(
            f"動画の長さ（{duration_sec:.2f} 秒）が短い可能性があります（推奨: {min_dur:.0f} 秒以上）。"
        )

    # ── 姿勢検出率 ────────────────────────────────────────────────────────────
    # visibility 列が全て 0 のフレーム = 検出なし
    nose_vis_col = "nose_visibility"
    if nose_vis_col in df.columns:
        detected = (df[nose_vis_col].fillna(0.0) > 0.1).sum()
        pose_detection_rate = _safe_float(detected / total, 4) if total > 0 else 0.0
    else:
        pose_detection_rate = None

    min_pdr = float(thresholds.get("min_pose_detection_rate", 0.60))
    if pose_detection_rate is not None and pose_detection_rate < min_pdr:
        warnings_list.append(
            f"姿勢の検出率（{pose_detection_rate * 100:.1f}%）が低めです。"
            "背景の複雑さ・服装の色・撮影角度を確認してください。"
        )

    # ── ランドマーク欠損率 ────────────────────────────────────────────────────
    missing_rates: Dict[str, float] = {}
    for name in _LANDMARK_NAMES:
        vis_col = f"{name}_visibility"
        if vis_col in df.columns:
            missing = (df[vis_col].fillna(0.0) <= 0.1).sum()
            rate = _safe_float(missing / total, 4) if total > 0 else 0.0
            if rate is not None:
                missing_rates[name] = rate

    overall_missing = (
        _safe_float(sum(missing_rates.values()) / len(missing_rates), 4)
        if missing_rates else None
    )

    max_miss = float(thresholds.get("max_landmark_missing_rate", 0.40))
    for name in _KEY_LANDMARKS:
        rate = missing_rates.get(name)
        if rate is not None and rate > max_miss:
            label_map = {
                "left_shoulder": "左肩", "right_shoulder": "右肩",
                "left_wrist": "左手首", "right_wrist": "右手首",
                "left_elbow": "左肘", "right_elbow": "右肘",
                "left_hip": "左腰", "right_hip": "右腰",
                "left_ankle": "左足首", "right_ankle": "右足首",
            }
            jp = label_map.get(name, name)
            warnings_list.append(
                f"{jp}の推定点が一部不安定です（欠損率: {rate * 100:.1f}%）。"
                "撮影角度や服装の影響により精度が下がる場合があります。"
            )

    # ── 投げ腕の手首安定性チェック ────────────────────────────────────────────
    wrist_vel_col = f"{dominant_arm}_wrist_y"
    if wrist_vel_col in df.columns and len(df) >= 10:
        try:
            wrist_y = df[wrist_vel_col].dropna()
            wrist_jerk = wrist_y.diff().diff().abs()
            high_jerk_ratio = _safe_float((wrist_jerk > wrist_jerk.quantile(0.95)).sum() / len(wrist_y), 4)
            if high_jerk_ratio is not None and high_jerk_ratio > 0.10:
                warnings_list.append(
                    "リリース付近で投げ腕の手首推定が一部不安定です。"
                    "リリースフレームの推定は参考候補として確認してください。"
                )
        except Exception:
            pass

    # ── 身体画面外チェック ────────────────────────────────────────────────────
    # x または y が 0.05 未満 or 0.95 超 のフレームを「切れている可能性」とみなす
    out_of_frame_count = 0
    for lm in ["left_shoulder", "right_shoulder", "nose"]:
        for axis in ("x", "y"):
            col = f"{lm}_{axis}"
            if col in df.columns:
                vals = df[col].dropna()
                out_cnt = ((vals < 0.05) | (vals > 0.95)).sum()
                out_of_frame_count = max(out_of_frame_count, int(out_cnt))

    out_of_frame_ratio = _safe_float(out_of_frame_count / total, 4) if total > 0 else 0.0
    if out_of_frame_ratio is not None and out_of_frame_ratio > 0.10:
        warnings_list.append(
            f"身体の一部が画面外に切れている可能性があるフレームが"
            f"{out_of_frame_ratio * 100:.1f}% 検出されました。"
            "解析精度に影響することがあります。"
        )

    # ── 総合品質評価 ──────────────────────────────────────────────────────────
    if len(warnings_list) == 0:
        overall_quality = "good"
        overall_label   = "良好"
        overall_desc    = (
            "今回の動画では、身体全体が比較的安定して検出されています。"
            "解析に適した動画と判断されます。"
        )
    elif len(warnings_list) <= 2:
        overall_quality = "medium"
        overall_label   = "中程度"
        overall_desc    = (
            "今回の動画では身体全体は概ね検出されていますが、一部の推定点で注意が必要です。"
            "推定結果は参考候補として確認してください。"
        )
    else:
        overall_quality = "low"
        overall_label   = "低め"
        overall_desc    = (
            "今回の動画では推定点の安定性に課題が見られます。"
            "自動フェーズ推定の精度は参考程度としてください。"
            "次回の撮影時は以下のアドバイスを参考にしてください。"
        )

    # ── 次回撮影アドバイス ────────────────────────────────────────────────────
    advice: List[str] = [
        "動画は身体全体が映るように、横から全身が収まる距離から撮影してください。",
        "背景はなるべくシンプル（白壁・芝生等）にしてください。",
        "服装は身体のラインが分かりやすいもの（ピタッとしたウェア等）が向いています。",
        "逆光・強い影がないよう、光の方向を確認してください。",
        f"フレームレートは {min_fps:.0f} FPS 以上を推奨します。",
        "投てき全体が最初から最後まで映っていると精度が向上します。",
    ]

    landmark_stats = {
        "pose_detection_rate":   pose_detection_rate,
        "landmark_missing_rate": overall_missing,
        "per_landmark":          missing_rates,
        "out_of_frame_ratio":    out_of_frame_ratio,
    }

    return {
        "overall_quality":       overall_quality,
        "overall_quality_label": overall_label,
        "overall_description":   overall_desc,
        "fps":                   fps_estimated,
        "duration_sec":          duration_sec,
        "total_frames":          total,
        "pose_detection_rate":   pose_detection_rate,
        "landmark_missing_rate": overall_missing,
        "landmark_stats":        landmark_stats,
        "warnings":              warnings_list,
        "next_shooting_advice":  advice,
        "disclaimer":            (
            "この品質評価は動画の解析適性を参考情報として示すものです。"
            "品質スコアは絶対評価ではなく、動画条件により変動します。"
        ),
    }


def check_video_quality(
    csv_path: Optional[Path],
    fps: Optional[float] = None,
    total_frames: Optional[int] = None,
    dominant_arm: str = "right",
) -> Dict[str, Any]:
    """
    pose_landmarks.csv から動画品質チェック結果を返す。

    Parameters
    ----------
    csv_path : Path or None
        pose_landmarks.csv のパス
    fps : float or None
        FPS（CSV の time_sec 列から推定可能）
    total_frames : int or None
        総フレーム数
    dominant_arm : str
        投げ腕

    Returns
    -------
    dict
        video_quality_report.json の内容
    """
    thresholds = _load_config()
    generated_at = datetime.now().isoformat(timespec="seconds")

    if csv_path is None or not Path(csv_path).exists():
        return {
            "status":       "skipped",
            "reason":       "pose_landmarks.csv が見つかりません",
            "generated_at": generated_at,
            "overall_quality": "unknown",
            "warnings":     [],
        }

    df = _load_csv(csv_path)
    if df is None or len(df) < 3:
        return {
            "status":       "skipped",
            "reason":       "データが不足しています（フレーム数が少なすぎます）",
            "generated_at": generated_at,
            "overall_quality": "unknown",
            "warnings":     [],
        }

    quality = _compute_quality(
        df=df,
        fps=float(fps) if fps else None,
        total_frames=int(total_frames) if total_frames else None,
        thresholds=thresholds,
        dominant_arm=dominant_arm,
    )
    quality["status"]       = "ok"
    quality["generated_at"] = generated_at
    return quality


def load_video_quality_report(job_dir: Path) -> Optional[Dict[str, Any]]:
    """video_quality_report.json を読み込んで返す。存在しない場合は None。"""
    report_path = Path(job_dir) / "report" / "video_quality_report.json"
    if not report_path.exists():
        return None
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def check_video_quality_for_job(job_dir: Path) -> Path:
    """
    ジョブディレクトリに対して動画品質チェックを実行し、
    video_quality_report.json を生成して Path を返す。

    エラーが発生しても例外を外に出さず、status="error" として JSON を保存する。

    Parameters
    ----------
    job_dir : Path
        ジョブのルートディレクトリ

    Returns
    -------
    Path
        video_quality_report.json のパス
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "video_quality_report.json"

    try:
        # ジョブ情報
        job_data: Dict[str, Any] = {}
        job_json_path = job_dir / "job.json"
        if job_json_path.exists():
            try:
                job_data = json.loads(job_json_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # 利き腕
        dominant_arm = "right"
        ci_path = job_dir / "customer_info.json"
        if ci_path.exists():
            try:
                ci = json.loads(ci_path.read_text(encoding="utf-8"))
                hand = (ci.get("dominant_hand") or "right").strip().lower()
                if hand in ("right", "left"):
                    dominant_arm = hand
            except Exception:
                pass

        # FPS / 総フレーム数
        fps = None
        total_frames = None
        pf_path = job_dir / "phase_frames.json"
        if pf_path.exists():
            try:
                pf = json.loads(pf_path.read_text(encoding="utf-8"))
                fps = pf.get("fps")
                total_frames = pf.get("total_frames")
            except Exception:
                pass

        csv_path = _find_csv(job_dir)

        result = check_video_quality(
            csv_path=csv_path,
            fps=float(fps) if fps else None,
            total_frames=int(total_frames) if total_frames else None,
            dominant_arm=dominant_arm,
        )

        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[video_quality] 品質チェック完了: %s quality=%s",
                    job_dir.name, result.get("overall_quality"))
        return out_path

    except Exception as e:
        logger.error("[video_quality] 品質チェックエラー: %s — %s", job_dir.name, e)
        error_payload = {
            "status":       "error",
            "reason":       str(e)[:500],
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "overall_quality": "unknown",
            "warnings":     [],
        }
        try:
            out_path.write_text(json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return out_path
