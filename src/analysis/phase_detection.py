"""
src/analysis/phase_detection.py — Javelin Video Analysis 自動フェーズ推定 (Phase 10)

やり投げ動画の姿勢推定データ（pose_landmarks.csv）から、
各投てきフェーズ（助走・クロス・槍を引く・ブロック・リリース・フォロースルー等）の
候補フレームをルールベースで推定します。

⚠️  重要な注意事項
    - 自動推定結果は「候補」です。最終判断は管理者・指導者が行ってください。
    - 動画の画質・撮影角度・服装・背景により精度が変わります。
    - 断定的な評価ではなく、参考候補として活用してください。
    - 怪我・痛みに関する判断は医療専門家にご相談ください。
    - 競技指導・医療診断の代替ではありません。

出力ファイル: jobs/<job_id>/report/phase_detection_result.json

Usage:
    from src.analysis.phase_detection import detect_phases_for_job
    from pathlib import Path

    result = detect_phases_for_job(Path("jobs/20260508_070156_518a"))
    # -> Path("jobs/20260508_070156_518a/report/phase_detection_result.json")
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jva.phase_detection")

_MODULE_DIR = Path(__file__).resolve().parent       # src/analysis/
_REPO_ROOT  = _MODULE_DIR.parent.parent             # project root

# ── 設定ファイル ─────────────────────────────────────────────────────────────

def _load_config() -> Dict[str, Any]:
    """configs/phase_detection.yaml を読み込む。読み込めない場合はデフォルトを返す。"""
    cfg_path = _REPO_ROOT / "configs" / "phase_detection.yaml"
    try:
        import yaml  # type: ignore[import-not-found]
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("[phase_detection] 設定ファイル読み込み失敗: %s", e)
    return {}


# ── 信頼度スコアのラベル変換 ─────────────────────────────────────────────────

def confidence_label(confidence: float) -> str:
    """0.0〜1.0 の confidence を日本語ラベルに変換する。"""
    if confidence >= 0.75:
        return "推定精度 高め"
    elif confidence >= 0.45:
        return "推定精度 中程度"
    else:
        return "推定精度 低め"


def confidence_warning(confidence: float) -> Optional[str]:
    """信頼度が低い場合の注意文を返す。低くない場合は None。"""
    if confidence < 0.45:
        return (
            "このフェーズ推定は、動画の撮影角度や姿勢推定点の安定性の影響を受けている"
            "可能性があります。参考候補として確認してください。"
        )
    return None


# ── CSV 読み込み ──────────────────────────────────────────────────────────────

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
    """CSV を pandas DataFrame として読み込む。失敗時は None。"""
    try:
        import pandas as pd
        df = pd.read_csv(csv_path, encoding="utf-8")
        if df.empty:
            return None
        return df
    except Exception as e:
        logger.warning("[phase_detection] CSV 読み込み失敗: %s — %s", csv_path, e)
        return None


# ── 特徴量計算ユーティリティ ─────────────────────────────────────────────────

def _smooth(series: Any, window: int = 3) -> Any:
    """簡易移動平均平滑化。"""
    try:
        return series.rolling(window=window, center=True, min_periods=1).mean()
    except Exception:
        return series


def _velocity(series: Any, fps: float) -> Any:
    """1フレーム差分から速度（単位/秒）を計算する。"""
    try:
        return series.diff().abs() * fps
    except Exception:
        return series * 0


def _safe_float(val: Any) -> Optional[float]:
    try:
        v = float(val)
        return round(v, 4)
    except (TypeError, ValueError):
        return None


def _frame_to_time_sec(df: Any, frame_num: int) -> Optional[float]:
    """frame 番号に対応する time_sec を df から安全に返す。見つからない場合は None。"""
    try:
        if "frame" not in df.columns or "time_sec" not in df.columns:
            return None
        matches = df.loc[df["frame"] == frame_num, "time_sec"]
        if len(matches) > 0:
            return _safe_float(matches.iloc[0])
    except Exception:
        pass
    return None


# ── ルールベース推定ロジック ─────────────────────────────────────────────────

def _estimate_release(
    df: Any,
    fps: float,
    dominant_arm: str,
    search_start_pct: float = 0.50,
    search_end_pct: float   = 0.95,
) -> Dict[str, Any]:
    """
    リリース候補フレームを推定する。

    ルール:
      1. 投げ腕の手首速度（diff の絶対値）が探索窓内でピーク
      2. かつ、手首の高さ（y 座標を反転）が肩より高い
      3. 以上の条件を組み合わせてスコアを算出

    Returns: phase result dict
    """
    total = len(df)
    start_idx = int(total * search_start_pct)
    end_idx   = int(total * search_end_pct)
    end_idx   = min(end_idx, total - 1)

    wrist_y_col   = f"{dominant_arm}_wrist_y"
    wrist_x_col   = f"{dominant_arm}_wrist_x"
    shoulder_y_col = f"{dominant_arm}_shoulder_y"

    # デフォルト（データ不足）
    default = _make_result(
        frame=None,
        time_sec=None,
        confidence=0.0,
        method="wrist_velocity_peak",
        reason="投げ腕の手首データが不足しているため、リリース候補を推定できませんでした。",
        is_auto=True,
        needs_review=True,
    )

    if wrist_y_col not in df.columns:
        return default

    sub = df.iloc[start_idx:end_idx + 1].copy()
    if len(sub) < 5:
        return default

    # ── 手首速度 ─────────────────────────────────────────────────────────────
    wrist_y = _smooth(sub[wrist_y_col], window=3)
    wrist_vel = _velocity(wrist_y, fps)

    # ── 手首の高さ（y は上=0 なので反転）─────────────────────────────────────
    wrist_height = 1.0 - sub[wrist_y_col]

    # ── 肩の高さ ──────────────────────────────────────────────────────────────
    if shoulder_y_col in sub.columns:
        shoulder_height = 1.0 - sub[shoulder_y_col]
    else:
        shoulder_height = wrist_height * 0 + 0.5  # フォールバック

    # ── スコア = 速度 × 手首が肩より高い補正 ─────────────────────────────────
    above_shoulder = (wrist_height > shoulder_height).astype(float)
    score = wrist_vel.fillna(0) * (1.0 + 0.5 * above_shoulder)

    if score.empty or score.max() == 0:
        return default

    best_idx = int(score.idxmax())
    best_frame = int(df.loc[best_idx, "frame"]) if "frame" in df.columns else best_idx
    best_time = _safe_float(df.loc[best_idx, "time_sec"]) if "time_sec" in df.columns else None

    # ── 信頼度スコア算出 ─────────────────────────────────────────────────────
    speed_rank = float(score.loc[best_idx]) / (float(score.max()) + 1e-9)
    wrist_above = float(above_shoulder.loc[best_idx]) if best_idx in above_shoulder.index else 0.0
    confidence = round(min(1.0, 0.5 * speed_rank + 0.3 * wrist_above + 0.2), 4)

    reason = (
        f"投げ腕（{dominant_arm}）の手首速度が探索窓内で最大付近（フレーム {best_frame}）で、"
    )
    if wrist_above > 0.5:
        reason += "手首位置が肩より高い候補フレームです。"
    else:
        reason += "手首位置が低い可能性があります（撮影角度の影響）。"

    return _make_result(
        frame=best_frame,
        time_sec=best_time,
        confidence=confidence,
        method="wrist_velocity_peak",
        reason=reason,
        is_auto=True,
        needs_review=(confidence < 0.85),
    )


def _estimate_block(
    df: Any,
    fps: float,
    dominant_arm: str,
    release_frame: Optional[int],
    search_before_frames: int = 30,
) -> Dict[str, Any]:
    """
    ブロック候補フレームを推定する。

    ルール:
      - release_frame の手前 search_before_frames フレーム以内を探索
      - 前脚側の足首移動量が最小になるフレームを候補にする
      - 左投げ: 右足首が前脚
      - 右投げ: 左足首が前脚
    """
    total = len(df)

    default = _make_result(
        frame=None,
        time_sec=None,
        confidence=0.0,
        method="front_ankle_stability",
        reason="ブロック候補の推定に必要なデータが不足しています。",
        is_auto=True,
        needs_review=True,
    )

    # 前脚 = 投げ腕と逆側
    front_leg = "right" if dominant_arm == "left" else "left"
    ankle_y_col = f"{front_leg}_ankle_y"
    ankle_x_col = f"{front_leg}_ankle_x"

    if ankle_y_col not in df.columns:
        return default

    # 探索範囲
    if release_frame is not None:
        end_idx   = min(release_frame - 1, total - 1)
        start_idx = max(0, end_idx - search_before_frames)
    else:
        # release 未推定: 後半 1/4 から 3/4 を探索
        start_idx = total // 4
        end_idx   = total * 3 // 4

    sub = df.iloc[start_idx:end_idx + 1].copy()
    if len(sub) < 3:
        return default

    ankle_vel_y = _velocity(_smooth(sub[ankle_y_col], 3), fps)
    ankle_vel_x = (
        _velocity(_smooth(sub[ankle_x_col], 3), fps)
        if ankle_x_col in sub.columns
        else ankle_vel_y * 0
    )
    ankle_speed = (ankle_vel_y.fillna(0) ** 2 + ankle_vel_x.fillna(0) ** 2) ** 0.5

    if ankle_speed.empty:
        return default

    best_idx = int(ankle_speed.idxmin())
    best_frame = int(df.loc[best_idx, "frame"]) if "frame" in df.columns else best_idx
    best_time = _safe_float(df.loc[best_idx, "time_sec"]) if "time_sec" in df.columns else None

    # ブロックは推定が難しいので confidence は低め
    confidence = round(min(0.70, 0.25 + 0.45 * (1.0 - float(ankle_speed.min()) / (float(ankle_speed.max()) + 1e-9))), 4)

    return _make_result(
        frame=best_frame,
        time_sec=best_time,
        confidence=confidence,
        method="front_ankle_stability",
        reason=(
            f"前脚（{front_leg}）の足首移動量が小さくなる付近（フレーム {best_frame}）を"
            "ブロック候補として抽出しました。"
            "撮影角度によっては精度が低い場合があります。"
        ),
        is_auto=True,
        needs_review=True,
    )


def _estimate_withdrawal(
    df: Any,
    fps: float,
    dominant_arm: str,
    release_frame: Optional[int],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    槍を引く局面（開始・終了）の候補を推定する。

    ルール:
      - 投げ腕手首が後方（x方向で後退）に動いている区間
      - 肩との水平距離が拡大している区間
    """
    total = len(df)

    default_start = _make_result(
        frame=None, time_sec=None, confidence=0.0,
        method="wrist_backward_motion",
        reason="槍を引く局面の開始候補推定に必要なデータが不足しています。",
        is_auto=True, needs_review=True,
    )
    default_end = _make_result(
        frame=None, time_sec=None, confidence=0.0,
        method="wrist_backward_motion",
        reason="槍を引く局面の終了候補推定に必要なデータが不足しています。",
        is_auto=True, needs_review=True,
    )

    wrist_x_col   = f"{dominant_arm}_wrist_x"
    shoulder_x_col = f"{dominant_arm}_shoulder_x"

    if wrist_x_col not in df.columns:
        return default_start, default_end

    # 探索範囲: 前半50%〜release_frame 前
    search_end = (release_frame or total) - 5
    search_start = max(0, total // 10)
    sub = df.iloc[search_start:search_end].copy()
    if len(sub) < 10:
        return default_start, default_end

    wrist_x   = _smooth(sub[wrist_x_col], 3)
    wrist_vel = sub[wrist_x_col].diff()  # 正 = 前進, 負 = 後退（右投げ: x増加=前進仮定）

    # 手首が後退（velocity が負方向）している連続区間を探す
    # MediaPipe の x 座標は右方向が大きい（画面左から右）
    # 右投げの場合、助走中は x が増加（前進）、引き動作で増加が鈍化・逆転
    # 簡易: wrist_x の変化が最も減少（後退方向）している区間の前後を候補とする

    # 肩との距離
    if shoulder_x_col in sub.columns:
        dist = (sub[wrist_x_col] - sub[shoulder_x_col]).abs()
        peak_dist_idx = int(dist.idxmax())
    else:
        peak_dist_idx = int(wrist_x.idxmin() if dominant_arm == "right" else wrist_x.idxmax())

    # 開始 = peak_dist の手前を探す（後退し始め）
    withdraw_window = max(5, len(sub) // 5)
    start_idx = max(sub.index[0], peak_dist_idx - withdraw_window)
    end_idx   = min(sub.index[-1], peak_dist_idx + 5)

    start_frame = int(df.loc[start_idx, "frame"]) if "frame" in df.columns else start_idx
    end_frame   = int(df.loc[end_idx,   "frame"]) if "frame" in df.columns else end_idx
    start_time  = _safe_float(df.loc[start_idx, "time_sec"]) if "time_sec" in df.columns else None
    end_time    = _safe_float(df.loc[end_idx,   "time_sec"]) if "time_sec" in df.columns else None

    confidence = 0.40  # 槍の直接検出はないため低め固定

    r_start = _make_result(
        frame=start_frame, time_sec=start_time, confidence=confidence,
        method="wrist_backward_motion",
        reason=(
            f"投げ腕（{dominant_arm}）の手首と肩の距離が拡大し始める付近（フレーム {start_frame}）を"
            "槍を引く局面の開始候補としました。やりの直接検出は行っていないため精度は参考程度です。"
        ),
        is_auto=True, needs_review=True,
    )
    r_end = _make_result(
        frame=end_frame, time_sec=end_time, confidence=confidence,
        method="wrist_backward_motion",
        reason=(
            f"手首と肩の距離が最大付近（フレーム {end_frame}）を"
            "槍を引く局面の終了候補としました。"
        ),
        is_auto=True, needs_review=True,
    )
    return r_start, r_end


def _estimate_cross_step(
    df: Any,
    fps: float,
    dominant_arm: str,
    release_frame: Optional[int],
    fallback_simple: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    クロスステップ（開始・終了）の候補を推定する。

    足首 x 座標の左右入れ替わりから推定。
    データが不足する場合、release_frame から逆算する簡易推定にフォールバック。
    """
    total = len(df)

    default_s = _make_result(
        frame=None, time_sec=None, confidence=0.0,
        method="ankle_crossover",
        reason="クロスステップ開始候補の推定に必要なデータが不足しています。",
        is_auto=True, needs_review=True,
    )
    default_e = _make_result(
        frame=None, time_sec=None, confidence=0.0,
        method="ankle_crossover",
        reason="クロスステップ終了候補の推定に必要なデータが不足しています。",
        is_auto=True, needs_review=True,
    )

    left_ankle_x  = "left_ankle_x"
    right_ankle_x = "right_ankle_x"

    # ── 足首 x 座標の入れ替わり検出 ─────────────────────────────────────────
    if left_ankle_x in df.columns and right_ankle_x in df.columns:
        # 前半60%を探索（クロスは助走後半から引き動作前）
        end_idx = min(int(total * 0.70), (release_frame or total) - 5)
        sub = df.iloc[0:end_idx].copy()
        if len(sub) >= 10:
            l = _smooth(sub[left_ankle_x], 3)
            r = _smooth(sub[right_ankle_x], 3)
            diff = l - r
            sign_changes = ((diff.shift(1) * diff) < 0)
            cross_indices = diff.index[sign_changes].tolist()

            if len(cross_indices) >= 2:
                cs_idx = cross_indices[-2]  # 最後の2番目の交差 = クロスの開始
                ce_idx = cross_indices[-1]  # 最後の交差 = クロス終了
                cs_frame = int(df.loc[cs_idx, "frame"]) if "frame" in df.columns else cs_idx
                ce_frame = int(df.loc[ce_idx, "frame"]) if "frame" in df.columns else ce_idx
                cs_time  = _safe_float(df.loc[cs_idx, "time_sec"]) if "time_sec" in df.columns else None
                ce_time  = _safe_float(df.loc[ce_idx, "time_sec"]) if "time_sec" in df.columns else None
                confidence = 0.50
                return (
                    _make_result(
                        frame=cs_frame, time_sec=cs_time, confidence=confidence,
                        method="ankle_crossover",
                        reason=(
                            f"左右足首の x 座標が入れ替わるフレーム（{cs_frame}）を"
                            "クロスステップ開始の候補としました。"
                        ),
                        is_auto=True, needs_review=True,
                    ),
                    _make_result(
                        frame=ce_frame, time_sec=ce_time, confidence=confidence,
                        method="ankle_crossover",
                        reason=(
                            f"左右足首の x 座標の2回目の入れ替わりフレーム（{ce_frame}）を"
                            "クロスステップ終了の候補としました。"
                        ),
                        is_auto=True, needs_review=True,
                    ),
                )

    # ── 簡易フォールバック: release から逆算 ─────────────────────────────────
    if fallback_simple and release_frame is not None:
        fps_safe = fps if fps > 0 else 30.0
        # クロスは通常 release の約0.5〜1.5秒前
        cs_frame = max(0, release_frame - int(fps_safe * 1.5))
        ce_frame = max(0, release_frame - int(fps_safe * 0.5))
        cs_time  = _frame_to_time_sec(df, cs_frame)
        ce_time  = _frame_to_time_sec(df, ce_frame)
        confidence = 0.25
        return (
            _make_result(
                frame=cs_frame, time_sec=cs_time, confidence=confidence,
                method="release_frame_offset",
                reason=(
                    "足首データによる推定ができなかったため、"
                    f"リリース候補フレーム（{release_frame}）から逆算した"
                    "簡易推定値です。精度は低くなります。"
                ),
                is_auto=True, needs_review=True,
            ),
            _make_result(
                frame=ce_frame, time_sec=ce_time, confidence=confidence,
                method="release_frame_offset",
                reason=(
                    "リリース候補フレームから逆算した簡易推定値です。"
                    "管理者が確認・修正してください。"
                ),
                is_auto=True, needs_review=True,
            ),
        )

    return default_s, default_e


def _estimate_approach(
    df: Any,
    fps: float,
    cross_step_start: Optional[int],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """助走フェーズ（開始・終了）を推定する。簡易推定。"""
    total = len(df)
    approach_start_frame = 0
    approach_start_time  = 0.0

    if cross_step_start is not None:
        approach_end_frame = max(0, cross_step_start - 1)
    else:
        approach_end_frame = total // 4

    approach_end_time = _frame_to_time_sec(df, approach_end_frame)

    return (
        _make_result(
            frame=approach_start_frame,
            time_sec=approach_start_time,
            confidence=0.35,
            method="first_frame",
            reason="動画の開始フレームを助走開始の候補としています。実際の助走開始フレームに修正してください。",
            is_auto=True,
            needs_review=True,
        ),
        _make_result(
            frame=approach_end_frame,
            time_sec=approach_end_time,
            confidence=0.30,
            method="cross_step_offset",
            reason=(
                "クロスステップ開始の直前フレームを助走終了の候補としています。"
                "クロスステップ推定が不正確な場合はこちらも修正が必要です。"
            ),
            is_auto=True,
            needs_review=True,
        ),
    )


def _estimate_follow_through(
    df: Any,
    fps: float,
    release_frame: Optional[int],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """フォロースルー（開始・終了）の候補を推定する。"""
    total = len(df)
    if release_frame is None:
        return (
            _make_result(None, None, 0.0, "release_offset", "リリース未推定のため推定不可", True, True),
            _make_result(None, None, 0.0, "release_offset", "リリース未推定のため推定不可", True, True),
        )

    fps_safe = fps if fps > 0 else 30.0
    ft_start = min(release_frame + 1, total - 1)
    ft_end   = min(release_frame + int(fps_safe * 0.5), total - 1)

    ft_start_time = _frame_to_time_sec(df, ft_start)
    ft_end_time   = _frame_to_time_sec(df, ft_end)

    return (
        _make_result(
            frame=ft_start, time_sec=ft_start_time, confidence=0.50,
            method="release_offset",
            reason=f"リリース候補（フレーム {release_frame}）の直後をフォロースルー開始の候補としています。",
            is_auto=True, needs_review=True,
        ),
        _make_result(
            frame=ft_end, time_sec=ft_end_time, confidence=0.40,
            method="release_offset",
            reason="リリースから約0.5秒後をフォロースルー終了の候補としています。",
            is_auto=True, needs_review=True,
        ),
    )


def _estimate_recovery(
    df: Any,
    follow_through_end: Optional[int],
    total: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """リカバリー（開始・終了）の候補を推定する。"""
    if follow_through_end is None:
        return (
            _make_result(None, None, 0.0, "follow_through_offset", "フォロースルー未推定のため推定不可", True, True),
            _make_result(None, None, 0.0, "follow_through_offset", "フォロースルー未推定のため推定不可", True, True),
        )

    rec_start = min(follow_through_end + 1, total - 1)
    rec_end   = total - 1
    rec_start_time = _frame_to_time_sec(df, rec_start)
    rec_end_time   = _frame_to_time_sec(df, rec_end)

    return (
        _make_result(
            frame=rec_start, time_sec=rec_start_time, confidence=0.30,
            method="follow_through_offset",
            reason="フォロースルー終了後をリカバリー開始の候補としています。",
            is_auto=True, needs_review=True,
        ),
        _make_result(
            frame=rec_end, time_sec=rec_end_time, confidence=0.25,
            method="last_frame",
            reason="動画の最終フレームをリカバリー終了の候補としています。",
            is_auto=True, needs_review=True,
        ),
    )


def _make_result(
    frame: Optional[int],
    time_sec: Optional[float],
    confidence: float,
    method: str,
    reason: str,
    is_auto: bool,
    needs_review: bool,
) -> Dict[str, Any]:
    """フェーズ推定結果の共通フォーマットを返す。confidence は [0.0, 1.0] にクランプされる。"""
    _c = max(0.0, min(1.0, float(confidence)))
    return {
        "frame":            frame,
        "time_sec":         time_sec,
        "confidence":       round(_c, 4),
        "confidence_label": confidence_label(_c),
        "method":           method,
        "reason":           reason,
        "is_auto_detected": is_auto,
        "needs_review":     needs_review,
        "warning":          confidence_warning(_c),
    }


# ── メイン推定処理 ─────────────────────────────────────────────────────────────

def detect_phases(
    csv_path: Optional[Path],
    dominant_arm: str = "right",
    fps: Optional[float] = None,
    total_frames: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    pose_landmarks.csv から各フェーズ候補を推定して結果 dict を返す。

    Parameters
    ----------
    csv_path : Path or None
        pose_landmarks.csv のパス。None の場合はデータ不足として推定をスキップ。
    dominant_arm : str
        投げ腕。"right" または "left"
    fps : float or None
        FPS。None の場合は CSV の time_sec 列から推定する。
    total_frames : int or None
        総フレーム数。None の場合は CSV の行数を使う。
    config : dict or None
        phase_detection.yaml の内容。None の場合は自動読み込み。

    Returns
    -------
    dict
        phase_detection_result.json の内容。
    """
    cfg = config if config is not None else _load_config()
    arm = dominant_arm if dominant_arm in ("right", "left") else "right"

    generated_at = datetime.now().isoformat(timespec="seconds")

    # ── CSV 読み込み ──────────────────────────────────────────────────────────
    df = None
    if csv_path is not None and Path(csv_path).exists():
        df = _load_csv(csv_path)

    if df is None or len(df) < 5:
        return {
            "status":       "skipped",
            "reason":       "pose_landmarks.csv が見つからないか、フレーム数が不足しています。",
            "generated_at": generated_at,
            "dominant_arm": arm,
            "phases":       {},
            "metadata":     {},
        }

    # ── FPS / 総フレーム数 ────────────────────────────────────────────────────
    total = total_frames if total_frames is not None else len(df)
    if fps is None or fps <= 0:
        if "time_sec" in df.columns:
            t_vals = df["time_sec"].dropna()
            elapsed = t_vals.max() - t_vals.min()
            fps = float((len(t_vals) - 1) / elapsed) if elapsed > 0 else 30.0
        else:
            fps = 30.0

    # ── 設定値読み込み ────────────────────────────────────────────────────────
    rel_cfg   = cfg.get("release_detection",   {})
    blk_cfg   = cfg.get("block_detection",     {})
    wd_cfg    = cfg.get("withdrawal_detection", {})
    cs_cfg    = cfg.get("cross_step_detection", {})

    sw_start = rel_cfg.get("search_window_percent", {}).get("start", 50) / 100.0
    sw_end   = rel_cfg.get("search_window_percent", {}).get("end",   95) / 100.0
    blk_before = blk_cfg.get("search_before_release_frames", 30)
    cs_fallback = cs_cfg.get("fallback_to_simple_estimation", True)

    # ── 各フェーズ推定 ────────────────────────────────────────────────────────
    phases: Dict[str, Any] = {}

    # 1. リリース（最初に推定、他のフェーズの基準になる）
    release_result = _estimate_release(df, fps, arm, sw_start, sw_end)
    phases["release"] = release_result
    release_frame = release_result.get("frame")

    # 2. ブロック（リリース前）
    if blk_cfg.get("enabled", True):
        block_result = _estimate_block(df, fps, arm, release_frame, blk_before)
        phases["block"] = block_result
    else:
        phases["block"] = _make_result(None, None, 0.0, "disabled", "設定で無効化されています", True, False)

    # 3. 槍を引く局面
    if wd_cfg.get("enabled", True):
        wd_start, wd_end = _estimate_withdrawal(df, fps, arm, release_frame)
        phases["withdrawal_start"] = wd_start
        phases["withdrawal_end"]   = wd_end
    else:
        phases["withdrawal_start"] = _make_result(None, None, 0.0, "disabled", "設定で無効化されています", True, False)
        phases["withdrawal_end"]   = _make_result(None, None, 0.0, "disabled", "設定で無効化されています", True, False)

    # 4. クロスステップ
    if cs_cfg.get("enabled", True):
        cs_start, cs_end = _estimate_cross_step(df, fps, arm, release_frame, cs_fallback)
        phases["cross_step_start"] = cs_start
        phases["cross_step_end"]   = cs_end
    else:
        phases["cross_step_start"] = _make_result(None, None, 0.0, "disabled", "設定で無効化されています", True, False)
        phases["cross_step_end"]   = _make_result(None, None, 0.0, "disabled", "設定で無効化されています", True, False)

    # 5. 助走
    cs_start_frame = phases["cross_step_start"].get("frame")
    ap_start, ap_end = _estimate_approach(df, fps, cs_start_frame)
    phases["approach_start"] = ap_start
    phases["approach_end"]   = ap_end

    # 6. フォロースルー
    ft_start, ft_end = _estimate_follow_through(df, fps, release_frame)
    phases["follow_through_start"] = ft_start
    phases["follow_through_end"]   = ft_end

    # 7. リカバリー
    ft_end_frame = ft_end.get("frame")
    rec_start, rec_end = _estimate_recovery(df, ft_end_frame, total)
    phases["recovery_start"] = rec_start
    phases["recovery_end"]   = rec_end

    # ── メタデータ ────────────────────────────────────────────────────────────
    metadata = {
        "total_frames":  total,
        "fps":           round(fps, 3),
        "dominant_arm":  arm,
        "csv_rows":      len(df),
        "disclaimer":    (
            "この推定結果は参考候補です。動画の撮影角度・画質・服装・背景により精度が変わります。"
            "最終的なフェーズ指定は管理者が確認・修正してください。"
            "競技指導・医療診断の代替ではありません。"
        ),
    }

    return {
        "status":       "ok",
        "generated_at": generated_at,
        "dominant_arm": arm,
        "phases":       phases,
        "metadata":     metadata,
    }


# ── フェーズキー → 日本語ラベル ────────────────────────────────────────────────

_PHASE_LABEL_JP: Dict[str, str] = {
    "approach_start":       "助走（開始）",
    "approach_end":         "助走（終了）",
    "cross_step_start":     "クロスステップ（開始）",
    "cross_step_end":       "クロスステップ（終了）",
    "withdrawal_start":     "槍を引く（開始）",
    "withdrawal_end":       "槍を引く（終了）",
    "block":                "ブロック",
    "release":              "リリース",
    "follow_through_start": "フォロースルー（開始）",
    "follow_through_end":   "フォロースルー（終了）",
    "recovery_start":       "リカバリー（開始）",
    "recovery_end":         "リカバリー（終了）",
}


# ── 補正履歴の保存 ─────────────────────────────────────────────────────────────

def save_phase_correction(
    job_dir: Path,
    phase_key: str,
    auto_frame: Optional[int],
    manual_frame: Optional[int],
    accepted: bool,
    confidence: float,
    admin_note: str = "",
    method: str = "",
    dominant_arm: str = "",
) -> Path:
    """
    フェーズ手動修正履歴を phase_corrections.json に追記保存する。

    Parameters
    ----------
    job_dir : Path
        ジョブルートディレクトリ
    phase_key : str
        フェーズキー（例: "release", "block", "withdrawal_start" など）
    auto_frame : int or None
        自動推定フレーム番号
    manual_frame : int or None
        管理者が設定したフレーム番号
    accepted : bool
        自動推定候補をそのまま採用したか
    confidence : float
        自動推定の信頼度スコア
    admin_note : str
        管理者メモ
    method : str
        自動推定に使用したアルゴリズム名（ML 教師データ用）
    dominant_arm : str
        投げ腕（"right" または "left"）（ML 教師データ用）

    Returns
    -------
    Path
        phase_corrections.json のパス
    """
    report_dir = Path(job_dir) / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    corr_path = report_dir / "phase_corrections.json"

    # 既存の履歴を読み込む
    corrections: Dict[str, Any] = {}
    if corr_path.exists():
        try:
            corrections = json.loads(corr_path.read_text(encoding="utf-8"))
        except Exception:
            corrections = {}

    delta = None
    if auto_frame is not None and manual_frame is not None:
        delta = manual_frame - auto_frame

    corrections[phase_key] = {
        "schema_version":         "1.0",
        "job_id":                 Path(job_dir).name,
        "phase_key":              phase_key,
        "phase_label_jp":         _PHASE_LABEL_JP.get(phase_key, phase_key),
        "dominant_arm":           dominant_arm,
        "auto_detected_frame":    auto_frame,
        "auto_method":            method,
        "manual_corrected_frame": manual_frame,
        "accepted_by_admin":      accepted,
        "correction_delta":       delta,
        "confidence":             round(float(confidence), 4),
        "updated_at":             datetime.now().isoformat(timespec="seconds"),
        "admin_note":             admin_note,
    }

    corr_path.write_text(
        json.dumps(corrections, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("[phase_detection] 修正履歴保存: %s phase=%s", job_dir.name, phase_key)
    return corr_path


def load_phase_corrections(job_dir: Path) -> Dict[str, Any]:
    """phase_corrections.json を読み込んで返す。存在しない場合は空dict。"""
    corr_path = Path(job_dir) / "report" / "phase_corrections.json"
    if not corr_path.exists():
        return {}
    try:
        return json.loads(corr_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_phase_detection_result(job_dir: Path) -> Optional[Dict[str, Any]]:
    """phase_detection_result.json を読み込んで返す。存在しない場合は None。"""
    result_path = Path(job_dir) / "report" / "phase_detection_result.json"
    if not result_path.exists():
        return None
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── ジョブ単位の実行 ─────────────────────────────────────────────────────────

def detect_phases_for_job(job_dir: Path) -> Path:
    """
    ジョブディレクトリに対して自動フェーズ推定を実行し、
    phase_detection_result.json を生成して Path を返す。

    エラーが発生しても例外を外に出さず、status="error" として JSON を保存する。
    これにより worker の通常処理が止まらないようにする。

    Parameters
    ----------
    job_dir : Path
        ジョブのルートディレクトリ

    Returns
    -------
    Path
        phase_detection_result.json のパス
    """
    job_dir = Path(job_dir)
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "phase_detection_result.json"

    try:
        # 設定読み込み
        cfg = _load_config()
        if not cfg.get("enabled", True):
            payload = {
                "status":       "disabled",
                "dominant_arm": cfg.get("default_dominant_arm", "right"),
                "reason":       "configs/phase_detection.yaml で無効化されています",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "phases":       {},
                "metadata":     {},
            }
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return out_path

        # ジョブ情報
        job_json_path = job_dir / "job.json"
        job_data: Dict[str, Any] = {}
        if job_json_path.exists():
            try:
                job_data = json.loads(job_json_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # 利き腕
        dominant_arm = cfg.get("default_dominant_arm", "right")
        ci_path = job_dir / "customer_info.json"
        if ci_path.exists():
            try:
                ci = json.loads(ci_path.read_text(encoding="utf-8"))
                hand = (ci.get("dominant_hand") or "right").strip().lower()
                if hand in ("right", "left"):
                    dominant_arm = hand
            except Exception:
                pass

        # phase_frames.json から FPS / 総フレーム数
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

        # CSV 探索
        csv_path = _find_csv(job_dir)

        result = detect_phases(
            csv_path=csv_path,
            dominant_arm=dominant_arm,
            fps=float(fps) if fps else None,
            total_frames=int(total_frames) if total_frames else None,
            config=cfg,
        )

        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[phase_detection] 推定完了: %s status=%s", job_dir.name, result.get("status"))
        return out_path

    except Exception as e:
        logger.error("[phase_detection] 推定エラー: %s — %s", job_dir.name, e)
        error_payload = {
            "status":       "error",
            "dominant_arm": "unknown",
            "reason":       str(e)[:500],
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "phases":       {},
            "metadata":     {},
        }
        try:
            out_path.write_text(json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return out_path
