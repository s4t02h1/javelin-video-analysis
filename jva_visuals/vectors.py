"""
vectors.py - ベクトル描画モジュール

速度・加速度ベクトルを矢印で可視化する。
"""

import numpy as np
import cv2
from typing import Dict, Any, Tuple, Optional
import logging

from .registry import VisualPassBase
from .adapters import AdaptedLandmarks
from .kinematics import KinematicsBuffer, calculate_arm_vectors

logger = logging.getLogger(__name__)


class VectorPass(VisualPassBase):
    """速度・加速度ベクトルの描画"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # 描画設定
        self.scale_factor = config.get("scale", 0.6)
        self.show_velocity = config.get("show_velocity", True)
        self.show_acceleration = config.get("show_acceleration", True)
        self.velocity_color = config.get("velocity_color", (0, 255, 0))  # 緑
        self.acceleration_color = config.get("acceleration_color", (0, 0, 255))  # 赤
        self.min_vector_length = config.get("min_vector_length", 10)  # 最小描画長さ
        self.max_vector_length = config.get("max_vector_length", 100)  # 最大描画長さ
        
        # 平滑化設定
        self.smooth_method = config.get("smooth", "ema")
        self.ema_alpha = config.get("ema_alpha", 0.3)
        
        # 描画する関節の選択
        self.target_joints = config.get("target_joints", [
            11, 12,  # 肩
            13, 14,  # 肘  
            15, 16,  # 手首
            23, 24,  # 腰
        ])
        
        # 運動学バッファ
        self.kinematics = KinematicsBuffer(
            smooth_method=self.smooth_method,
            ema_alpha=self.ema_alpha
        )
        
        # フレーム カウンタ
        self.frame_count = 0
    
    def apply(self, frame: np.ndarray, landmarks: AdaptedLandmarks) -> np.ndarray:
        """ベクトルを描画"""
        if not self.enabled:
            return frame
        
        # 運動学データを更新
        timestamp = self.frame_count / landmarks.fps
        positions = landmarks.points[:, :2]  # (x, y) のみ
        self.kinematics.add_frame(positions, timestamp)
        
        # 現在の運動学データを取得
        kinematics_data = self.kinematics.get_current_kinematics()
        
        result = frame.copy()
        
        # 各関節にベクトルを描画
        for joint_idx in self.target_joints:
            if joint_idx >= len(landmarks.points):
                continue
            
            # 関節の信頼度チェック
            if landmarks.points[joint_idx, 2] < 0.5:
                continue
            
            joint_pos = landmarks.points[joint_idx, :2].astype(int)
            
            # 速度ベクトル
            if self.show_velocity and joint_idx < len(kinematics_data['velocity']):
                velocity = kinematics_data['velocity'][joint_idx] * landmarks.px2m
                self._draw_vector(result, joint_pos, velocity, 
                                self.velocity_color, "velocity")
            
            # 加速度ベクトル
            if self.show_acceleration and joint_idx < len(kinematics_data['acceleration']):
                acceleration = kinematics_data['acceleration'][joint_idx] * landmarks.px2m
                self._draw_vector(result, joint_pos, acceleration,
                                self.acceleration_color, "acceleration")
        
        self.frame_count += 1
        return result
    
    def _draw_vector(self, frame: np.ndarray, origin: np.ndarray, 
                    vector: np.ndarray, color: Tuple[int, int, int], 
                    vector_type: str):
        """ベクトルを矢印で描画"""
        # ベクトルの大きさ
        magnitude = np.linalg.norm(vector)
        if magnitude < 1e-6:
            return
        
        # スケール調整
        scaled_magnitude = magnitude * self.scale_factor
        
        # 長さ制限
        if scaled_magnitude < self.min_vector_length:
            if scaled_magnitude > 5:  # 完全に小さすぎるものは描画しない
                scaled_magnitude = self.min_vector_length
            else:
                return
        elif scaled_magnitude > self.max_vector_length:
            scaled_magnitude = self.max_vector_length
        
        # 方向ベクトル（正規化）
        direction = vector / magnitude
        
        # 終点計算
        end_point = origin + direction * scaled_magnitude
        end_point = end_point.astype(int)
        
        # 線種設定
        line_type = cv2.LINE_AA
        thickness = 2
        
        if vector_type == "acceleration":
            # 加速度は点線で描画
            self._draw_dashed_line(frame, tuple(origin), tuple(end_point), 
                                 color, thickness)
        else:
            # 速度は実線で描画
            cv2.line(frame, tuple(origin), tuple(end_point), color, thickness, line_type)
        
        # 矢印の頭を描画
        self._draw_arrow_head(frame, origin.astype(float), end_point.astype(float), 
                            color, thickness)
        
        # 数値表示（オプション）
        if hasattr(self, 'show_values') and self.show_values:
            self._draw_vector_value(frame, end_point, magnitude, vector_type)
    
    def _draw_dashed_line(self, frame: np.ndarray, start: Tuple[int, int], 
                         end: Tuple[int, int], color: Tuple[int, int, int], 
                         thickness: int, dash_length: int = 8):
        """点線を描画"""
        x1, y1 = start
        x2, y2 = end
        
        # 線分の長さと方向
        dx = x2 - x1
        dy = y2 - y1
        length = np.sqrt(dx*dx + dy*dy)
        
        if length < 1:
            return
        
        # 単位ベクトル
        ux = dx / length
        uy = dy / length
        
        # 点線パターンで描画
        current_length = 0
        draw_dash = True
        
        while current_length < length:
            start_pos = (int(x1 + ux * current_length), int(y1 + uy * current_length))
            
            remaining = length - current_length
            segment_length = min(dash_length, remaining)
            
            end_pos = (int(x1 + ux * (current_length + segment_length)),
                      int(y1 + uy * (current_length + segment_length)))
            
            if draw_dash:
                cv2.line(frame, start_pos, end_pos, color, thickness, cv2.LINE_AA)
            
            current_length += segment_length
            draw_dash = not draw_dash
    
    def _draw_arrow_head(self, frame: np.ndarray, start: np.ndarray, 
                        end: np.ndarray, color: Tuple[int, int, int], 
                        thickness: int):
        """矢印の頭を描画"""
        # 矢印の長さと角度
        arrow_length = max(8, thickness * 4)
        arrow_angle = 0.5  # radians
        
        # ベクトル方向
        direction = end - start
        length = np.linalg.norm(direction)
        
        if length < 1:
            return
        
        unit_vector = direction / length
        
        # 矢印の両翼の方向ベクトル
        cos_a = np.cos(arrow_angle)
        sin_a = np.sin(arrow_angle)
        
        # 回転行列を適用
        left_wing = np.array([
            -unit_vector[0] * cos_a + unit_vector[1] * sin_a,
            -unit_vector[0] * sin_a - unit_vector[1] * cos_a
        ]) * arrow_length
        
        right_wing = np.array([
            -unit_vector[0] * cos_a - unit_vector[1] * sin_a,
             unit_vector[0] * sin_a - unit_vector[1] * cos_a
        ]) * arrow_length
        
        # 矢印の翼を描画
        left_point = (end + left_wing).astype(int)
        right_point = (end + right_wing).astype(int)
        
        cv2.line(frame, tuple(end.astype(int)), tuple(left_point), color, thickness, cv2.LINE_AA)
        cv2.line(frame, tuple(end.astype(int)), tuple(right_point), color, thickness, cv2.LINE_AA)
    
    def _draw_vector_value(self, frame: np.ndarray, position: np.ndarray, 
                          magnitude: float, vector_type: str):
        """ベクトルの数値を表示"""
        # 単位を決定
        unit = "m/s" if vector_type == "velocity" else "m/s²"
        text = f"{magnitude:.1f} {unit}"
        
        # テキスト位置調整
        text_pos = (position[0] + 5, position[1] - 5)
        
        # 背景矩形
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.4
        thickness = 1
        
        (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)
        
        # 半透明背景
        overlay = frame.copy()
        cv2.rectangle(overlay, 
                     (text_pos[0] - 2, text_pos[1] - text_height - 2),
                     (text_pos[0] + text_width + 2, text_pos[1] + baseline + 2),
                     (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, dst=frame)
        
        # テキスト描画
        cv2.putText(frame, text, text_pos, font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)