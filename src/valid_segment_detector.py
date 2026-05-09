"""
src/valid_segment_detector.py — Javelin Video Analysis 有効解析区間検出

pose_landmarks.csv から「ポーズが安定して検出されている最長連続区間」を検出し、
解析の対象範囲を絞り込む。

使用例:
    from src.valid_segment_detector import detect_valid_pose_segment, save_valid_segment
    result = detect_valid_pose_segment(Path("report/pose_landmarks.csv"))
    save_valid_segment(result, Path("report/valid_segment.json"))
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

# ── 有効判定の閾値 ───────────────────────────────────────────────────────────

_VIS_THRESHOLD    = 0.3   # right_wrist / right_shoulder の visibility 下限
_MAX_GAP_FRAMES   = 5     # 有効区間の連結許容ギャップ（フレーム数）
_MIN_VALID_FRAMES = 3     # 有効区間の最小長（これ未満は無視）


def _parse_float(value: str) -> Optional[float]:
    """CSV セルの文字列を float に変換する。空・変換不可は None。"""
    v = (value or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def detect_valid_pose_segment(
    csv_path: Union[str, Path],
    vis_threshold: float = _VIS_THRESHOLD,
    max_gap: int = _MAX_GAP_FRAMES,
) -> dict:
    """pose_landmarks.csv から有効解析区間を検出する。

    有効フレームの条件（全て満たすこと）:
        - right_wrist_x / right_wrist_y が存在する
        - right_shoulder_x / right_shoulder_y が存在する
        - right_wrist_visibility     >= vis_threshold
        - right_shoulder_visibility  >= vis_threshold

    連続する有効フレームのうち最長の区間を返す。
    隣接する有効ブロック間のギャップが max_gap フレーム以内であれば
    同一区間として扱う（小さな検出抜けに対してロバスト）。

    Args:
        csv_path:       pose_landmarks.csv のパス。
        vis_threshold:  visibility の有効判定閾値（デフォルト 0.3）。
        max_gap:        区間を結合するギャップ上限フレーム数（デフォルト 5）。

    Returns:
        以下のキーを持つ dict:
            valid_start_frame   (int)  : 有効区間の開始フレーム番号（1-based）
            valid_end_frame     (int)  : 有効区間の終了フレーム番号（1-based）
            valid_start_time_sec(float): 有効区間の開始時刻（秒）
            valid_end_time_sec  (float): 有効区間の終了時刻（秒）
            valid_frame_count   (int)  : 有効フレーム数
            total_frame_count   (int)  : CSVの全フレーム数
            valid_ratio         (float): valid_frame_count / total_frame_count
            warnings            (list) : 警告メッセージリスト
    """
    csv_path = Path(csv_path)

    # CSV 存在チェック
    if not csv_path.exists():
        logger.warning("valid_segment_detector: CSV が見つかりません: %s", csv_path)
        return _empty_result(0, warnings=["pose_landmarks.csv が存在しません。"])

    # ── CSV 読み込み ─────────────────────────────────────────────────────────
    frames: list[dict] = []   # {frame, time_sec, valid}
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                frame_num = int((row.get("frame") or "0").strip() or "0")
                if frame_num <= 0:
                    continue

                time_sec = _parse_float(row.get("time_sec", ""))

                # 有効判定
                rw_vis = _parse_float(row.get("right_wrist_visibility", ""))
                rs_vis = _parse_float(row.get("right_shoulder_visibility", ""))
                rw_x   = _parse_float(row.get("right_wrist_x", ""))
                rw_y   = _parse_float(row.get("right_wrist_y", ""))
                rs_x   = _parse_float(row.get("right_shoulder_x", ""))
                rs_y   = _parse_float(row.get("right_shoulder_y", ""))

                valid = (
                    rw_x is not None
                    and rw_y is not None
                    and rs_x is not None
                    and rs_y is not None
                    and (rw_vis or 0.0) >= vis_threshold
                    and (rs_vis or 0.0) >= vis_threshold
                )
                frames.append({
                    "frame":    frame_num,
                    "time_sec": time_sec,
                    "valid":    valid,
                })
    except Exception as exc:
        logger.warning("valid_segment_detector: CSV 読み込みエラー: %s", exc)
        return _empty_result(0, warnings=[f"CSV 読み込みエラー: {exc}"])

    total = len(frames)
    if total == 0:
        return _empty_result(0, warnings=["CSVにフレームデータがありません。"])

    # ── 有効ブロックを列挙し、ギャップ許容で結合 ────────────────────────────
    # ブロック: {'start': idx, 'end': idx, 'count': int}  (idxはframes配列の添字)
    blocks: list[dict] = []
    in_block = False
    block_start = 0

    for i, fr in enumerate(frames):
        if fr["valid"]:
            if not in_block:
                block_start = i
                in_block = True
        else:
            if in_block:
                blocks.append({"start": block_start, "end": i - 1})
                in_block = False

    if in_block:
        blocks.append({"start": block_start, "end": len(frames) - 1})

    # ギャップ許容で隣接ブロックを結合
    if blocks:
        merged: list[dict] = [blocks[0]]
        for blk in blocks[1:]:
            gap = frames[blk["start"]]["frame"] - frames[merged[-1]["end"]]["frame"] - 1
            if gap <= max_gap:
                merged[-1]["end"] = blk["end"]
            else:
                merged.append(blk)
        blocks = merged

    # 最長ブロックを採択（最小長未満は除外）
    best: Optional[dict] = None
    for blk in blocks:
        length = blk["end"] - blk["start"] + 1
        if length >= _MIN_VALID_FRAMES:
            if best is None or length > (best["end"] - best["start"] + 1):
                best = blk

    warnings: list[str] = []
    valid_in_segment = 0

    if best is None:
        logger.info("valid_segment_detector: 有効区間が見つかりませんでした。全区間を使用します。")
        warnings.append(
            f"有効なポーズ検出区間が見つかりませんでした（閾値 visibility >= {vis_threshold}）。"
            " 全区間を代替として使用します。"
        )
        # フォールバック: 全区間
        start_fr = frames[0]
        end_fr   = frames[-1]
        valid_count = sum(1 for fr in frames if fr["valid"])
        valid_ratio = valid_count / total if total > 0 else 0.0
    else:
        start_fr    = frames[best["start"]]
        end_fr      = frames[best["end"]]
        # valid_frame_count は区間内で valid == True のフレームのみカウント
        valid_in_segment = sum(1 for fr in frames[best["start"]: best["end"] + 1] if fr["valid"])
        valid_count = valid_in_segment
        valid_ratio = valid_count / total

    # ── 警告メッセージ生成 ───────────────────────────────────────────────────
    if valid_ratio < 0.30:
        warnings.append(
            f"ポーズ検出率が非常に低い値です（{valid_ratio:.0%}）。"
            " 動画品質・照明・カメラアングルを確認してください。"
        )
    elif valid_ratio < 0.70:
        warnings.append(
            f"解析精度に注意してください（有効率: {valid_ratio:.0%}）。"
            " 一部区間でポーズ検出ができていません。"
        )

    # 開始が遅い場合（全フレームの 20% 超過後から検出開始）
    start_ratio = (start_fr["frame"] - 1) / total if total > 0 else 0.0
    if start_ratio > 0.20:
        t = start_fr["time_sec"]
        t_str = f"{t:.2f}秒" if t is not None else f"フレーム{start_fr['frame']}"
        warnings.append(
            f"ポーズ検出の開始が遅い（{t_str}から）。"
            " 助走開始から選手が映るよう撮影してください。"
        )

    result = {
        "valid_start_frame":    start_fr["frame"],
        "valid_end_frame":      end_fr["frame"],
        "valid_start_time_sec": start_fr["time_sec"],
        "valid_end_time_sec":   end_fr["time_sec"],
        "valid_frame_count":    valid_count,
        "total_frame_count":    total,
        "valid_ratio":          round(valid_ratio, 4),
        "warnings":             warnings,
    }

    logger.info(
        "valid_segment_detector: 有効区間 frame %d–%d  valid %d/%d  ratio %.1f%%",
        result["valid_start_frame"],
        result["valid_end_frame"],
        result["valid_frame_count"],
        result["total_frame_count"],
        result["valid_ratio"] * 100,
    )
    return result


def save_valid_segment(result: dict, out_path: Union[str, Path]) -> Path:
    """detect_valid_pose_segment の結果を JSON として保存する。

    Args:
        result:   detect_valid_pose_segment() の返り値。
        out_path: 保存先パス（例: report/valid_segment.json）。

    Returns:
        保存したファイルのパス。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("valid_segment_detector: valid_segment.json 保存: %s", out_path)
    return out_path


def _empty_result(total: int, warnings: list[str]) -> dict:
    """有効区間が取得できない場合のデフォルト結果。"""
    return {
        "valid_start_frame":    None,
        "valid_end_frame":      None,
        "valid_start_time_sec": None,
        "valid_end_time_sec":   None,
        "valid_frame_count":    0,
        "total_frame_count":    total,
        "valid_ratio":          0.0,
        "warnings":             warnings,
    }
