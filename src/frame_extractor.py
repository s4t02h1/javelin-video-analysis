"""
src/frame_extractor.py — Javelin Video Analysis 代表フレーム切り出しユーティリティ

動画から代表フレームを JPEG 画像として保存する。

2つのモード:
  1. extract_representative_frames() — 均等割合 (0/25/50/75/90%) でフレームを抽出（後方互換）
  2. extract_smart_frames()          — pose_landmarks.csv を参照し、有効ポーズ区間から
                                       意味のあるフレーム（速度ピーク・高さ最大など）を選択

使用例:
    from src.frame_extractor import extract_representative_frames, extract_smart_frames
    paths = extract_representative_frames("input.mp4", "report/frames/")
    paths = extract_smart_frames("input.mp4", "report/frames/", csv_path="report/pose_landmarks.csv")
"""

import csv as _csv_module
import logging
from pathlib import Path
from typing import List, Optional, Union

import cv2  # type: ignore

logger = logging.getLogger(__name__)

# ── 均等割合モード用位置定義 ─────────────────────────────────────────────────
_POSITIONS = [
    (0.00, "start"),
    (0.25, "25pct"),
    (0.50, "50pct"),
    (0.75, "75pct"),
    (0.90, "90pct"),
]


def extract_representative_frames(
    video_path: Union[str, Path],
    output_dir: Union[str, Path],
    jpeg_quality: int = 92,
) -> List[str]:
    """動画の代表フレームを JPEG として保存する（均等割合モード・後方互換）。

    Args:
        video_path: 入力動画ファイルのパス。
        output_dir: 保存先ディレクトリ（存在しない場合は作成）。
        jpeg_quality: JPEG 品質（0〜100、デフォルト92）。

    Returns:
        保存された画像ファイルのパス文字列リスト。
        失敗したフレームは含まれない。
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning(f"frame_extractor: cannot open video: {video_path}")
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        logger.warning(f"frame_extractor: total_frames={total_frames}, skipping.")
        cap.release()
        return []

    saved_paths: List[str] = []
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]

    for ratio, suffix in _POSITIONS:
        frame_idx = min(int(total_frames * ratio), total_frames - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            logger.warning(
                f"frame_extractor: failed to read frame {frame_idx} ({suffix})"
            )
            continue

        filename = f"frame_{frame_idx:04d}_{suffix}.jpg"
        out_path = output_dir / filename
        ok = cv2.imwrite(str(out_path), frame, encode_params)
        if ok:
            saved_paths.append(str(out_path))
            logger.info(f"Saved representative frame: {out_path}")
        else:
            logger.warning(f"frame_extractor: imwrite failed for {out_path}")

    cap.release()
    return saved_paths


# ── スマートフレーム選択モード ─────────────────────────────────────────────────

def select_smart_frame_indices(
    csv_path: Union[str, Path],
    n_frames: int = 5,
    visibility_threshold: float = 0.5,
    valid_start_frame: Optional[int] = None,
    valid_end_frame: Optional[int] = None,
) -> List[int]:
    """pose_landmarks.csv から意味のある代表フレームの 0-based インデックスを返す。

    選択基準（優先順）:
        1. 有効ポーズ区間の先頭フレーム
        2. right_wrist の移動速度が最大のフレーム（投てき加速期）
        3. right_wrist_y が最小（= 最も高い位置）のフレーム（リリース付近）
        4. 有効区間の 75% 地点
        5. 有効ポーズ区間の末尾フレーム

    visibility_threshold を下回るフレームは「ポーズ未検出」として除外する。
    有効フレームが少ない場合は fallback として均等割合を使用する。

    Args:
        csv_path:             pose_landmarks.csv のパス。
        n_frames:             選択するフレーム数（デフォルト5）。
        visibility_threshold: right_wrist の visibility 閾値（デフォルト0.5）。
        valid_start_frame:    有効区間の開始フレーム（1-based）。None の場合は制限なし。
        valid_end_frame:      有効区間の終了フレーム（1-based）。None の場合は制限なし。

    Returns:
        0-based フレームインデックスのリスト（動画の cap.set() に渡せる値）。
        ファイルが存在しない・読み取れない場合は空リスト。
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return []

    # ── CSV 読み込み ────────────────────────────────────────────────────────
    rows: List[dict] = []
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = _csv_module.DictReader(f)
            for row in reader:
                try:
                    frame_1based = int(row.get("frame", 0))
                    if frame_1based <= 0:
                        continue
                    # 有効区間の範囲外は除外
                    if valid_start_frame is not None and frame_1based < valid_start_frame:
                        continue
                    if valid_end_frame is not None and frame_1based > valid_end_frame:
                        continue
                    vis_str = row.get("right_wrist_visibility", "")
                    vis = float(vis_str) if vis_str.strip() else 0.0
                    x_str = row.get("right_wrist_x", "")
                    y_str = row.get("right_wrist_y", "")
                    x = float(x_str) if x_str.strip() else None
                    y = float(y_str) if y_str.strip() else None
                    rows.append({
                        "frame_0": frame_1based - 1,   # 0-based (OpenCV 用)
                        "vis":     vis,
                        "x":       x,
                        "y":       y,
                    })
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        logger.warning(f"frame_extractor: CSV 読み込みエラー: {e}")
        return []

    if not rows:
        return []

    # ── 有効フレームを抽出 ─────────────────────────────────────────────────
    valid = [r for r in rows if r["vis"] >= visibility_threshold and r["x"] is not None and r["y"] is not None]
    # 閾値を下げて再試行
    if len(valid) < 3:
        valid = [r for r in rows if r["vis"] >= 0.3 and r["x"] is not None and r["y"] is not None]
    # さらに fallback: 全フレーム
    if not valid:
        valid = [r for r in rows if r["x"] is not None and r["y"] is not None]
    if not valid:
        return []

    # ── speed 計算（連続有効フレーム間の正規化座標差分） ─────────────────
    for i, r in enumerate(valid):
        if i == 0:
            r["speed"] = 0.0
        else:
            prev = valid[i - 1]
            frame_diff = max(r["frame_0"] - prev["frame_0"], 1)
            dx = (r["x"] - prev["x"]) / frame_diff
            dy = (r["y"] - prev["y"]) / frame_diff
            r["speed"] = (dx ** 2 + dy ** 2) ** 0.5

    # ── 代表フレームを選択 ─────────────────────────────────────────────────
    selected_0based: List[int] = []

    # 1. 先頭
    selected_0based.append(valid[0]["frame_0"])
    # 2. 最大速度
    max_speed_row = max(valid, key=lambda r: r["speed"])
    selected_0based.append(max_speed_row["frame_0"])
    # 3. 最高位置（right_wrist_y 最小 = 画像上方）
    min_y_row = min(valid, key=lambda r: r["y"])
    selected_0based.append(min_y_row["frame_0"])
    # 4. 75% 地点
    idx_75 = int(len(valid) * 0.75)
    selected_0based.append(valid[min(idx_75, len(valid) - 1)]["frame_0"])
    # 5. 末尾
    selected_0based.append(valid[-1]["frame_0"])

    # 重複除去・ソート・個数制限
    seen = set()
    result: List[int] = []
    for idx in sorted(selected_0based):
        if idx not in seen:
            seen.add(idx)
            result.append(idx)
        if len(result) >= n_frames:
            break

    logger.info(
        f"frame_extractor: smart selection → {len(result)} frames "
        f"from {len(valid)} valid pose frames (total {len(rows)})"
    )
    return result


def extract_smart_frames(
    video_path: Union[str, Path],
    output_dir: Union[str, Path],
    csv_path: Optional[Union[str, Path]] = None,
    jpeg_quality: int = 92,
    n_frames: int = 5,
    valid_segment: Optional[dict] = None,
) -> List[str]:
    """pose_landmarks.csv を使って意味のある代表フレームを抽出する。

    CSV が存在しない・有効フレームが取得できない場合は
    extract_representative_frames() にフォールバックする。

    Args:
        video_path:     入力動画ファイルのパス。
        output_dir:     保存先ディレクトリ（存在しない場合は作成）。
        csv_path:       pose_landmarks.csv のパス（None の場合は均等割合で抽出）。
        jpeg_quality:   JPEG 品質（デフォルト92）。
        n_frames:       抽出するフレーム数（デフォルト5）。
        valid_segment:  detect_valid_pose_segment() の結果 dict。
                        指定すると valid_start_frame〜valid_end_frame の範囲でのみ
                        フレームを選択する。None の場合は全区間を対象にする。

    Returns:
        保存された画像ファイルのパス文字列リスト。
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]

    # 有効区間の範囲を取得
    seg_start: Optional[int] = None
    seg_end: Optional[int] = None
    if valid_segment is not None:
        seg_start = valid_segment.get("valid_start_frame")  # 1-based or None
        seg_end   = valid_segment.get("valid_end_frame")    # 1-based or None

    # CSV からスマートインデックスを取得
    smart_indices: List[int] = []
    if csv_path is not None:
        smart_indices = select_smart_frame_indices(
            csv_path,
            n_frames=n_frames,
            valid_start_frame=seg_start,
            valid_end_frame=seg_end,
        )

    # インデックスが取得できなければ均等割合モードにフォールバック
    if not smart_indices:
        logger.info("frame_extractor: CSV 未使用またはインデックス取得失敗 → 均等割合モードで抽出")
        return extract_representative_frames(video_path, output_dir, jpeg_quality)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning(f"frame_extractor: cannot open video: {video_path}")
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    saved_paths: List[str] = []
    labels = ["first", "speed_peak", "height_peak", "75pct", "last"]

    for i, frame_0 in enumerate(smart_indices):
        safe_idx = min(frame_0, total_frames - 1)
        label = labels[i] if i < len(labels) else f"extra{i}"
        cap.set(cv2.CAP_PROP_POS_FRAMES, safe_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            logger.warning(f"frame_extractor: failed to read frame {safe_idx} ({label})")
            continue

        filename = f"frame_{safe_idx:04d}_{label}.jpg"
        out_path = output_dir / filename
        ok = cv2.imwrite(str(out_path), frame, encode_params)
        if ok:
            saved_paths.append(str(out_path))
            logger.info(f"Saved smart frame: {out_path}")
        else:
            logger.warning(f"frame_extractor: imwrite failed for {out_path}")

    cap.release()
    return saved_paths
