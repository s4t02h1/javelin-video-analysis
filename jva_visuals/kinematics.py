"""
kinematics.py - 運動学的解析モジュール

ランドマークの時系列データから速度、加速度、角速度を計算する。
平滑化フィルタ（EMA、Savitzky-Golay）をサポート。
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Union
from scipy.signal import savgol_filter
import logging

logger = logging.getLogger(__name__)


def finite_diff(series: np.ndarray, dt: float) -> np.ndarray:
    """
    有限差分による微分計算
    
    Args:
        series: 時系列データ (N,) または (N, D)
        dt: 時間間隔
    
    Returns:
        np.ndarray: 微分値（最初の要素は0）
    """
    if len(series) < 2:
        return np.zeros_like(series)
    
    # 前進差分を使用（最初の要素は0で埋める）
    diff = np.zeros_like(series)
    if series.ndim == 1:
        diff[1:] = np.diff(series) / dt
    else:
        diff[1:] = np.diff(series, axis=0) / dt
    
    return diff


def apply_ema_filter(data: np.ndarray, alpha: float = 0.3) -> np.ndarray:
    """
    指数移動平均（EMA）フィルタを適用
    
    Args:
        data: 入力データ (N,) または (N, D)
        alpha: 平滑化係数 (0 < alpha <= 1)
    
    Returns:
        np.ndarray: 平滑化されたデータ
    """
    if len(data) == 0:
        return data
    
    alpha = np.clip(alpha, 0.01, 1.0)
    
    if data.ndim == 1:
        filtered = np.zeros_like(data)
        filtered[0] = data[0]
        for i in range(1, len(data)):
            filtered[i] = alpha * data[i] + (1 - alpha) * filtered[i-1]
    else:
        filtered = np.zeros_like(data)
        filtered[0] = data[0]
        for i in range(1, len(data)):
            filtered[i] = alpha * data[i] + (1 - alpha) * filtered[i-1]
    
    return filtered


def apply_savgol_filter(data: np.ndarray, window_length: int = 5, poly_order: int = 2) -> np.ndarray:
    """
    Savitzky-Golay フィルタを適用
    
    Args:
        data: 入力データ (N,) または (N, D)
        window_length: 窓長（奇数）
        poly_order: 多項式次数
    
    Returns:
        np.ndarray: 平滑化されたデータ
    """
    if len(data) < window_length:
        return data
    
    # 窓長を奇数に調整
    if window_length % 2 == 0:
        window_length += 1
    
    # poly_orderを調整
    poly_order = min(poly_order, window_length - 1)
    
    try:
        if data.ndim == 1:
            return savgol_filter(data, window_length, poly_order)
        else:
            return savgol_filter(data, window_length, poly_order, axis=0)
    except Exception as e:
        logger.warning(f"Savitzky-Golay filter failed: {e}")
        return data


class KinematicsBuffer:
    """運動学データのバッファ"""
    
    def __init__(self, max_length: int = 60, smooth_method: str = "ema", 
                 ema_alpha: float = 0.3, savgol_window: int = 5):
        self.max_length = max_length
        self.smooth_method = smooth_method.lower()
        self.ema_alpha = ema_alpha
        self.savgol_window = savgol_window
        
        # データバッファ
        self.positions: List[np.ndarray] = []  # [(N, 2), ...] for each frame
        self.timestamps: List[float] = []
        
        # キャッシュされた計算結果
        self._velocities: Optional[np.ndarray] = None
        self._accelerations: Optional[np.ndarray] = None
        self._speeds: Optional[np.ndarray] = None
        self._cache_valid = False
    
    def add_frame(self, positions: np.ndarray, timestamp: float):
        """
        新しいフレームのデータを追加
        
        Args:
            positions: ランドマーク位置 (N, 2) または (N, 3)
            timestamp: タイムスタンプ
        """
        # (x, y) のみを保持
        if positions.shape[1] > 2:
            positions = positions[:, :2]
        
        self.positions.append(positions.copy())
        self.timestamps.append(timestamp)
        
        # バッファサイズ制限
        if len(self.positions) > self.max_length:
            self.positions = self.positions[-self.max_length:]
            self.timestamps = self.timestamps[-self.max_length:]
        
        self._cache_valid = False
    
    def _compute_kinematics(self):
        """運動学的量を計算"""
        if len(self.positions) < 2:
            return
        
        n_frames = len(self.positions)
        n_joints = self.positions[0].shape[0]
        
        # 時系列配列を作成 (frames, joints, 2)
        pos_array = np.array(self.positions)  # (frames, joints, 2)
        time_array = np.array(self.timestamps)
        
        # 時間間隔
        dt_array = np.diff(time_array)
        dt_mean = np.mean(dt_array) if len(dt_array) > 0 else 1/30.0
        
        # 速度計算（各関節ごと）
        velocities = np.zeros((n_frames, n_joints, 2))
        for joint_idx in range(n_joints):
            joint_positions = pos_array[:, joint_idx, :]  # (frames, 2)
            
            # 平滑化
            if self.smooth_method == "ema":
                smoothed_pos = apply_ema_filter(joint_positions, self.ema_alpha)
            elif self.smooth_method == "savgol":
                smoothed_pos = apply_savgol_filter(joint_positions, self.savgol_window)
            else:
                smoothed_pos = joint_positions
            
            # 速度計算
            joint_vel = finite_diff(smoothed_pos, dt_mean)
            velocities[:, joint_idx, :] = joint_vel
        
        # 速度の大きさ
        speeds = np.linalg.norm(velocities, axis=2)  # (frames, joints)
        
        # 加速度計算
        accelerations = np.zeros_like(velocities)
        for joint_idx in range(n_joints):
            joint_vel = velocities[:, joint_idx, :]  # (frames, 2)
            joint_acc = finite_diff(joint_vel, dt_mean)
            accelerations[:, joint_idx, :] = joint_acc
        
        self._velocities = velocities
        self._accelerations = accelerations
        self._speeds = speeds
        self._cache_valid = True
    
    def get_current_kinematics(self) -> Dict[str, np.ndarray]:
        """
        現在フレームの運動学的データを取得
        
        Returns:
            Dict: {
                'velocity': (N, 2),      # 各関節の速度ベクトル
                'acceleration': (N, 2),  # 各関節の加速度ベクトル  
                'speed': (N,),           # 各関節の速度の大きさ
                'positions': (N, 2)      # 現在の位置
            }
        """
        if not self._cache_valid:
            self._compute_kinematics()
        
        if len(self.positions) == 0:
            return {
                'velocity': np.zeros((33, 2)),
                'acceleration': np.zeros((33, 2)),
                'speed': np.zeros(33),
                'positions': np.zeros((33, 2))
            }
        
        current_idx = -1  # 最新フレーム
        
        return {
            'velocity': self._velocities[current_idx] if self._velocities is not None else np.zeros((33, 2)),
            'acceleration': self._accelerations[current_idx] if self._accelerations is not None else np.zeros((33, 2)),
            'speed': self._speeds[current_idx] if self._speeds is not None else np.zeros(33),
            'positions': self.positions[-1]
        }


def calculate_arm_vectors(landmarks: np.ndarray, velocities: np.ndarray, px2m: float = 1.0) -> Dict[str, Dict]:
    """
    腕の運動学的ベクトルを計算
    
    Args:
        landmarks: ランドマーク座標 (N, 3)
        velocities: 速度ベクトル (N, 2)  
        px2m: ピクセル→メートル変換係数
    
    Returns:
        Dict: 腕の運動学的データ
    """
    # MediaPipe ポーズランドマークのインデックス
    LEFT_SHOULDER = 11
    LEFT_ELBOW = 13
    LEFT_WRIST = 15
    RIGHT_SHOULDER = 12
    RIGHT_ELBOW = 14
    RIGHT_WRIST = 16
    
    def get_joint_data(idx: int) -> Dict:
        if idx >= len(landmarks) or landmarks[idx, 2] < 0.5:  # 信頼度チェック
            return {
                'position': None,
                'velocity': np.array([0.0, 0.0]),
                'speed': 0.0
            }
        
        pos = landmarks[idx, :2] * px2m  # メートル単位に変換
        vel = velocities[idx] * px2m if idx < len(velocities) else np.array([0.0, 0.0])
        speed = np.linalg.norm(vel)
        
        return {
            'position': pos,
            'velocity': vel,
            'speed': speed
        }
    
    # 各関節のデータ
    result = {
        'left_shoulder': get_joint_data(LEFT_SHOULDER),
        'left_elbow': get_joint_data(LEFT_ELBOW),
        'left_wrist': get_joint_data(LEFT_WRIST),
        'right_shoulder': get_joint_data(RIGHT_SHOULDER),
        'right_elbow': get_joint_data(RIGHT_ELBOW),
        'right_wrist': get_joint_data(RIGHT_WRIST),
    }
    
    # 右腕の角速度計算（簡易版）
    right_arm_angular_velocity = 0.0
    if (result['right_shoulder']['position'] is not None and 
        result['right_elbow']['position'] is not None and
        result['right_wrist']['position'] is not None):
        
        # 肩-肘、肘-手首ベクトル
        upper_arm = result['right_elbow']['position'] - result['right_shoulder']['position']
        forearm = result['right_wrist']['position'] - result['right_elbow']['position']
        
        # 角度計算（簡易）
        if np.linalg.norm(upper_arm) > 0 and np.linalg.norm(forearm) > 0:
            # 肘の角度変化率を近似的に計算（実際は前フレームとの比較が必要）
            dot_product = np.dot(upper_arm, forearm)
            cross_product = np.cross(upper_arm, forearm)
            angle = np.arctan2(cross_product, dot_product)
            
            # 速度から角速度を推定（粗い近似）
            elbow_speed = result['right_elbow']['speed']
            arm_length = np.linalg.norm(upper_arm)
            if arm_length > 0:
                right_arm_angular_velocity = elbow_speed / arm_length  # rad/s
    
    result['right_arm_angular_velocity'] = right_arm_angular_velocity
    
    return result


def calculate_body_segments_speed(landmarks: np.ndarray, velocities: np.ndarray) -> Dict[str, float]:
    """
    身体各部位の代表速度を計算
    
    Args:
        landmarks: ランドマーク座標 (N, 3)
        velocities: 速度ベクトル (N, 2)
    
    Returns:
        Dict[str, float]: 各部位の速度
    """
    # 部位の定義（MediaPipeインデックス）
    segments = {
        'head': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],  # 顔部分
        'torso': [11, 12, 23, 24],  # 肩と腰
        'left_upper_arm': [11, 13],   # 左上腕
        'left_forearm': [13, 15],     # 左前腕
        'right_upper_arm': [12, 14],  # 右上腕  
        'right_forearm': [14, 16],    # 右前腕
        'left_thigh': [23, 25],       # 左大腿
        'left_shin': [25, 27],        # 左下腿
        'right_thigh': [24, 26],      # 右大腿
        'right_shin': [26, 28],       # 右下腿
    }
    
    segment_speeds = {}
    
    for segment_name, indices in segments.items():
        valid_speeds = []
        for idx in indices:
            if idx < len(landmarks) and idx < len(velocities):
                if landmarks[idx, 2] > 0.5:  # 信頼度チェック
                    speed = np.linalg.norm(velocities[idx])
                    valid_speeds.append(speed)
        
        # 平均速度
        if valid_speeds:
            segment_speeds[segment_name] = np.mean(valid_speeds)
        else:
            segment_speeds[segment_name] = 0.0
    
    return segment_speeds