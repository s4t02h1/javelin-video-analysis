"""
adapters.py - 既存のPoseAnalyzer状態を標準化された形式に変換

既存のコードを変更せずに、可視化プラグインが一貫した形式でデータを受け取れるようにする。
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class AdaptedLandmarks:
    """標準化されたランドマーク形式"""
    points: np.ndarray  # shape: (N, 3) -> (x_px, y_px, visibility)
    right_wrist: Optional[tuple]  # (x_px, y_px) | None
    fps: float
    px2m: float  # pixel to meter conversion factor
    frame_shape: tuple  # (height, width)


def adapt_state(state: Dict[str, Any], fps: float = 30.0, height_m: Optional[float] = None, 
                frame_shape: tuple = (480, 640)) -> AdaptedLandmarks:
    """
    既存のPoseAnalyzer状態を標準形式に変換
    
    Args:
        state: PoseAnalyzer.process()の戻り値
        fps: フレームレート
        height_m: 人物の身長（メートル）。Noneの場合はピクセル単位
        frame_shape: フレームサイズ (height, width)
    
    Returns:
        AdaptedLandmarks: 標準化されたデータ
    """
    # pointsの変換
    points_list = state.get("points", [None] * 33)
    points_array = np.zeros((33, 3), dtype=np.float32)  # (x, y, visibility)
    
    for i, point in enumerate(points_list):
        if point is not None:
            points_array[i] = [point[0], point[1], 1.0]  # x, y, visible
        else:
            points_array[i] = [0.0, 0.0, 0.0]  # invisible
    
    # 右手首の位置（MediaPipeのインデックス16）
    right_wrist = None
    if len(points_list) > 16 and points_list[16] is not None:
        right_wrist = points_list[16]
    
    # px2m（ピクセル→メートル変換）の計算
    px2m = 1.0  # デフォルトはピクセル単位
    if height_m is not None and height_m > 0:
        # 人物の大まかな身長をピクセル高さから推定
        # 肩から足首までの距離を身長の約80%と仮定
        shoulder_y = points_array[11, 1] if points_array[11, 2] > 0 else points_array[12, 1]
        ankle_y = max(points_array[27, 1], points_array[28, 1])  # 左右足首の下側
        
        if shoulder_y > 0 and ankle_y > 0:
            person_height_px = abs(ankle_y - shoulder_y)
            if person_height_px > 0:
                person_height_m = height_m * 0.8  # 肩から足首は身長の約80%
                px2m = person_height_m / person_height_px
    
    return AdaptedLandmarks(
        points=points_array,
        right_wrist=right_wrist,
        fps=fps,
        px2m=px2m,
        frame_shape=frame_shape
    )


def estimate_physical_scale(landmarks: AdaptedLandmarks, reference_height_m: float) -> float:
    """
    ランドマークから物理スケールを推定
    
    Args:
        landmarks: 標準化されたランドマーク
        reference_height_m: 参照身長（メートル）
    
    Returns:
        float: ピクセル→メートル変換係数
    """
    if reference_height_m <= 0:
        return 1.0
    
    # 頭頂から足首までの距離を測定
    head_y = 0
    ankle_y = landmarks.frame_shape[0]  # フレーム底辺をデフォルト
    
    # 鼻（インデックス0）を頭頂の代用
    if landmarks.points[0, 2] > 0:  # visible
        head_y = landmarks.points[0, 1]
    
    # 左右足首の平均
    left_ankle = landmarks.points[27]   # left ankle
    right_ankle = landmarks.points[28]  # right ankle
    
    valid_ankles = []
    if left_ankle[2] > 0:
        valid_ankles.append(left_ankle[1])
    if right_ankle[2] > 0:
        valid_ankles.append(right_ankle[1])
    
    if valid_ankles:
        ankle_y = max(valid_ankles)  # より下側の足首
    
    person_height_px = abs(ankle_y - head_y)
    if person_height_px > 50:  # 最低限のサイズチェック
        return reference_height_m / person_height_px
    
    return 1.0  # フォールバック