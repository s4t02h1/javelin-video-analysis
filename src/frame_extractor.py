"""
src/frame_extractor.py — Javelin Video Analysis 代表フレーム切り出しユーティリティ

動画から代表位置（0%, 25%, 50%, 75%, 90%）のフレームを JPEG 画像として保存する。

使用例:
    from src.frame_extractor import extract_representative_frames
    paths = extract_representative_frames("input.mp4", "report/frames/")
"""

import logging
from pathlib import Path
from typing import List, Optional, Union

import cv2  # type: ignore

logger = logging.getLogger(__name__)

# 切り出し位置の定義: (割合, ファイル名サフィックス)
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
    """動画の代表フレームを JPEG として保存する。

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
