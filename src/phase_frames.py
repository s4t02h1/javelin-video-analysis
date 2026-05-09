"""
src/phase_frames.py — Javelin Video Analysis フェーズ別代表フレーム抽出モジュール

phase_frames.json に記録されたフレーム番号を使って、指定動画から
フェーズ別の代表フレーム画像（JPEG）を抽出する。

出力ファイル名:
  <output_dir>/phase_<phase_key>.jpg          (is_range=False / 開始フレーム)
  <output_dir>/phase_<phase_key>_start.jpg    (is_range=True の開始)
  <output_dir>/phase_<phase_key>_end.jpg      (is_range=True の終了)

Usage:
    from src.phase_frames import extract_phase_frames
    from pathlib import Path

    results = extract_phase_frames(
        video_path=Path("jobs/20260508_070156_518a/input/video.mp4"),
        output_dir=Path("jobs/20260508_070156_518a/report/phase_frames"),
        phase_frames_dict={
            "approach_start_frame": 10,
            "approach_end_frame": 80,
            "block_frame": 120,
            ...
        },
        fps=30.0,
    )
    # -> {"approach_start": Path(...), "approach_end": Path(...), "block": Path(...), ...}
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("javelin.phase_frames")

# フレームキー → 出力ファイルサフィックスのマッピング
# キー形式: <phase_key>_start_frame / <phase_key>_end_frame / <phase_key>_frame
_JPEG_QUALITY = 92


def _parse_frame_keys(phase_frames_dict: dict) -> dict[str, Optional[int]]:
    """phase_frames_dict からフレーム番号キーのみを抽出する。

    Returns
    -------
    dict[str, Optional[int]]
        例: {"approach_start": 10, "approach_end": 80, "block": 120, ...}
        フレーム番号が None のものも含む（skip 判断は呼び出し元）
    """
    result: dict[str, Optional[int]] = {}
    for k, v in phase_frames_dict.items():
        if k.endswith("_start_frame"):
            stem = k[: -len("_start_frame")]
            result[f"{stem}_start"] = _to_int(v)
        elif k.endswith("_end_frame"):
            stem = k[: -len("_end_frame")]
            result[f"{stem}_end"] = _to_int(v)
        elif k.endswith("_frame"):
            stem = k[: -len("_frame")]
            result[stem] = _to_int(v)
    return result


def _to_int(val) -> Optional[int]:
    """値を int に変換。None / 変換不能は None を返す。"""
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def extract_phase_frames(
    video_path: Path,
    output_dir: Path,
    phase_frames_dict: dict,
    fps: Optional[float] = None,
    jpeg_quality: int = _JPEG_QUALITY,
) -> dict[str, Path]:
    """動画から指定フレームを抽出して JPEG 保存する。

    Parameters
    ----------
    video_path : Path
        元動画ファイルのパス
    output_dir : Path
        JPEG 保存先ディレクトリ（なければ自動作成）
    phase_frames_dict : dict
        job_manager.get_phase_frames() で取得した dict
    fps : float, optional
        動画の FPS。None の場合は phase_frames_dict["fps"] を使用する。
    jpeg_quality : int
        JPEG 品質 (1–100)

    Returns
    -------
    dict[str, Path]
        保存成功したもの。例: {"approach_start": Path(...), "block": Path(...)}
        フレーム番号が None のものは含まれない。
    """
    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError:
        logger.error("[phase_frames] OpenCV (cv2) が未インストールです")
        return {}

    video_path = Path(video_path)
    output_dir = Path(output_dir)

    if not video_path.exists():
        logger.warning("[phase_frames] 動画ファイルが見つかりません: %s", video_path)
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)

    # FPS の決定
    effective_fps = fps or phase_frames_dict.get("fps")

    # フレームキー → フレーム番号
    frame_map = _parse_frame_keys(phase_frames_dict)

    # 指定フレーム番号のうち None でないものだけを抽出
    targets: dict[str, int] = {k: v for k, v in frame_map.items() if v is not None}
    if not targets:
        logger.info("[phase_frames] 有効なフレーム番号が 0 件です — 抽出をスキップ")
        return {}

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error("[phase_frames] 動画を開けませんでした: %s", video_path)
        return {}

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS) or effective_fps or 30.0
    saved: dict[str, Path] = {}

    try:
        for stem, frame_no in targets.items():
            # 範囲チェック
            if frame_no < 0 or (total_frames > 0 and frame_no >= total_frames):
                logger.warning(
                    "[phase_frames] フレーム番号 %d が範囲外 (total=%d) — %s をスキップ",
                    frame_no,
                    total_frames,
                    stem,
                )
                continue

            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning(
                    "[phase_frames] フレーム %d の読み込みに失敗しました — %s をスキップ",
                    frame_no,
                    stem,
                )
                continue

            out_path = output_dir / f"phase_{stem}.jpg"
            ok = cv2.imwrite(
                str(out_path),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
            )
            if ok:
                saved[stem] = out_path
                logger.info("[phase_frames] 保存: %s (frame=%d)", out_path.name, frame_no)
            else:
                logger.warning("[phase_frames] JPEG 書き込み失敗: %s", out_path)
    finally:
        cap.release()

    return saved


def extract_phase_frames_for_job(job_dir: Path) -> dict[str, Path]:
    """ジョブディレクトリから自動的に動画と phase_frames.json を解決して抽出する。

    入力動画は job_dir/input/ 以下で最初に見つかった動画ファイルを使用する。
    出力先は job_dir/report/phase_frames/ 。

    Returns
    -------
    dict[str, Path]
        保存された画像の dict。 {} の場合は動画またはフレーム情報なし。
    """
    import json

    job_dir = Path(job_dir)

    # phase_frames.json の読み込み
    pf_path = job_dir / "phase_frames.json"
    if not pf_path.exists():
        logger.info("[phase_frames] phase_frames.json が見つかりません: %s", pf_path)
        return {}
    try:
        with open(pf_path, "r", encoding="utf-8") as f:
            phase_frames_dict: dict = json.load(f)
    except Exception as _e:
        logger.warning("[phase_frames] phase_frames.json 読み込み失敗: %s", _e)
        return {}

    # 入力動画の検索（input/ 以下の最初の動画）
    input_dir = job_dir / "input"
    video_path: Path | None = None
    if input_dir.exists():
        for ext in (".mp4", ".mov", ".avi", ".mkv", ".MP4", ".MOV"):
            matches = list(input_dir.glob(f"*{ext}"))
            if matches:
                video_path = matches[0]
                break

    if video_path is None:
        logger.warning("[phase_frames] 入力動画が見つかりません: %s", input_dir)
        return {}

    output_dir = job_dir / "report" / "phase_frames"
    return extract_phase_frames(
        video_path=video_path,
        output_dir=output_dir,
        phase_frames_dict=phase_frames_dict,
    )
