"""
hud.py - HUD（ヘッドアップディスプレイ）モジュール

ゲーム風のUIで運動解析データを表示する。
"""

import numpy as np
import cv2
from typing import Dict, Any, List, Tuple, Optional
import logging
import time

from .registry import VisualPassBase
from .adapters import AdaptedLandmarks
from .kinematics import KinematicsBuffer, calculate_arm_vectors

logger = logging.getLogger(__name__)


class HUDPass(VisualPassBase):
    """ゲーム風HUDの描画"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # 表示設定
        self.show_metrics = config.get("show_metrics", True)
        self.show_gauges = config.get("show_gauges", True)
        self.show_events = config.get("show_events", True)
        
        # イベント検知設定
        self.release_speed_threshold = config.get("release_speed_threshold_ms", 22.0)  # m/s
        self.release_flash_duration = config.get("release_flash_duration", 0.5)  # seconds
        
        # UI設定
        self.hud_alpha = config.get("alpha", 0.8)
        self.panel_color = config.get("panel_color", (0, 0, 0))  # 黒
        self.text_color = config.get("text_color", (255, 255, 255))  # 白
        self.accent_color = config.get("accent_color", (0, 255, 255))  # シアン
        self.warning_color = config.get("warning_color", (0, 0, 255))  # 赤
        
        # フォント設定
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.font_scale_large = 0.7
        self.font_scale_medium = 0.5
        self.font_scale_small = 0.4
        self.font_thickness = 1
        
        # 運動学バッファ
        self.kinematics = KinematicsBuffer()
        
        # イベント管理
        self.event_history = []
        self.last_release_time = 0
        self.flash_start_time = 0
        self.is_flashing = False
        
        # メトリクス履歴
        self.max_speed_recorded = 0.0
        self.frame_count = 0
    
    def apply(self, frame: np.ndarray, landmarks: AdaptedLandmarks) -> np.ndarray:
        """HUDを描画"""
        if not self.enabled:
            return frame
        
        # 運動学データを更新
        timestamp = self.frame_count / landmarks.fps
        positions = landmarks.points[:, :2]
        self.kinematics.add_frame(positions, timestamp)
        
        # 現在のメトリクス計算
        current_metrics = self._calculate_metrics(landmarks)
        
        # イベント検知
        self._detect_events(current_metrics, timestamp)
        
        # HUDを描画
        result = frame.copy()
        
        if self.show_metrics:
            result = self._draw_metrics_panel(result, current_metrics)
        
        if self.show_gauges:
            result = self._draw_gauges(result, current_metrics)
        
        if self.show_events:
            result = self._draw_events(result, timestamp)
        
        self.frame_count += 1
        return result
    
    def _calculate_metrics(self, landmarks: AdaptedLandmarks) -> Dict[str, Any]:
        """現在のメトリクスを計算"""
        kinematics_data = self.kinematics.get_current_kinematics()
        
        # 右手首の速度（リリース速度）
        right_wrist_speed = 0.0
        if landmarks.right_wrist is not None and len(kinematics_data['speed']) > 16:
            right_wrist_speed = kinematics_data['speed'][16] * landmarks.px2m
            self.max_speed_recorded = max(self.max_speed_recorded, right_wrist_speed)
        
        # 腕の運動学データ
        arm_data = calculate_arm_vectors(landmarks.points, kinematics_data['velocity'], landmarks.px2m)
        
        # 肩の分離度（左右肩の距離）
        shoulder_separation = 0.0
        if (landmarks.points[11, 2] > 0.5 and landmarks.points[12, 2] > 0.5):  # 左右肩が見える
            left_shoulder = landmarks.points[11, :2]
            right_shoulder = landmarks.points[12, :2]
            shoulder_separation = np.linalg.norm(right_shoulder - left_shoulder) * landmarks.px2m
        
        # 体の傾斜角度（肩の水平線からの角度）
        body_angle = 0.0
        if (landmarks.points[11, 2] > 0.5 and landmarks.points[12, 2] > 0.5):
            left_shoulder = landmarks.points[11, :2]
            right_shoulder = landmarks.points[12, :2]
            
            dx = right_shoulder[0] - left_shoulder[0]
            dy = right_shoulder[1] - left_shoulder[1]
            body_angle = np.degrees(np.arctan2(dy, dx))
        
        return {
            'right_wrist_speed': right_wrist_speed,
            'max_speed_recorded': self.max_speed_recorded,
            'arm_angular_velocity': arm_data.get('right_arm_angular_velocity', 0.0),
            'shoulder_separation': shoulder_separation,
            'body_angle': body_angle,
            'fps': landmarks.fps,
            'timestamp': self.frame_count / landmarks.fps
        }
    
    def _detect_events(self, metrics: Dict[str, Any], timestamp: float):
        """イベントを検知"""
        # リリース検知（速度閾値超過）
        if (metrics['right_wrist_speed'] > self.release_speed_threshold and 
            timestamp - self.last_release_time > 1.0):  # 1秒以上間隔
            
            self.event_history.append({
                'type': 'release',
                'timestamp': timestamp,
                'speed': metrics['right_wrist_speed'],
                'message': f"RELEASE! {metrics['right_wrist_speed']:.1f} m/s"
            })
            
            self.last_release_time = timestamp
            self.flash_start_time = timestamp
            self.is_flashing = True
            
            logger.info(f"Release detected: {metrics['right_wrist_speed']:.1f} m/s")
        
        # フラッシュ終了チェック
        if self.is_flashing and timestamp - self.flash_start_time > self.release_flash_duration:
            self.is_flashing = False
        
        # 古いイベントを削除
        self.event_history = [event for event in self.event_history 
                             if timestamp - event['timestamp'] < 5.0]
    
    def _draw_metrics_panel(self, frame: np.ndarray, metrics: Dict[str, Any]) -> np.ndarray:
        """メトリクスパネルを描画"""
        h, w = frame.shape[:2]
        
        # パネル設定
        panel_width = 280
        panel_height = 120
        panel_x = 10
        panel_y = 10
        
        # 半透明背景パネル
        overlay = frame.copy()
        cv2.rectangle(overlay, (panel_x, panel_y), 
                     (panel_x + panel_width, panel_y + panel_height),
                     self.panel_color, -1)
        cv2.addWeighted(overlay, self.hud_alpha, frame, 1 - self.hud_alpha, 0, dst=frame)
        
        # 枠線
        cv2.rectangle(frame, (panel_x, panel_y),
                     (panel_x + panel_width, panel_y + panel_height),
                     self.accent_color, 2)
        
        # メトリクステキスト
        y_offset = panel_y + 25
        line_spacing = 20
        
        metrics_text = [
            f"Release Speed: {metrics['right_wrist_speed']:.1f} m/s",
            f"Max Speed: {metrics['max_speed_recorded']:.1f} m/s", 
            f"Arm Angular Vel: {np.degrees(metrics['arm_angular_velocity']):.1f} deg/s",
            f"Body Angle: {metrics['body_angle']:.1f}°",
            f"FPS: {metrics['fps']:.1f}"
        ]
        
        for i, text in enumerate(metrics_text):
            y_pos = y_offset + i * line_spacing
            
            # 重要な値は色を変える
            color = self.text_color
            if i == 0 and metrics['right_wrist_speed'] > self.release_speed_threshold * 0.8:
                color = self.warning_color
            elif i == 1:
                color = self.accent_color
            
            cv2.putText(frame, text, (panel_x + 10, y_pos),
                       self.font, self.font_scale_small, color, 
                       self.font_thickness, cv2.LINE_AA)
        
        return frame
    
    def _draw_gauges(self, frame: np.ndarray, metrics: Dict[str, Any]) -> np.ndarray:
        """ゲージを描画"""
        h, w = frame.shape[:2]
        
        # 速度ゲージ
        gauge_center = (w - 80, 80)
        gauge_radius = 50
        
        self._draw_circular_gauge(frame, gauge_center, gauge_radius,
                                metrics['right_wrist_speed'], 0, 30,
                                "Speed", "m/s", self.accent_color)
        
        # 角速度ゲージ（簡易版）
        angular_vel_deg = np.degrees(metrics['arm_angular_velocity'])
        gauge_center2 = (w - 80, 180)
        
        self._draw_circular_gauge(frame, gauge_center2, 40,
                                angular_vel_deg, 0, 360,
                                "Angular", "deg/s", (255, 128, 0))
        
        return frame
    
    def _draw_circular_gauge(self, frame: np.ndarray, center: Tuple[int, int], 
                           radius: int, value: float, min_val: float, max_val: float,
                           label: str, unit: str, color: Tuple[int, int, int]):
        """円形ゲージを描画"""
        # 背景円
        cv2.circle(frame, center, radius, (50, 50, 50), 2)
        
        # 値を角度に変換（-90度から270度の範囲）
        normalized_value = np.clip((value - min_val) / (max_val - min_val), 0.0, 1.0)
        angle = -90 + normalized_value * 270  # 時計回り
        
        # ゲージの弧を描画
        if normalized_value > 0:
            # OpenCVの楕円弧描画
            axes = (radius - 5, radius - 5)
            angle_start = -90
            angle_end = angle
            
            # 複数の線で弧を近似
            num_segments = max(1, int(abs(angle_end - angle_start) / 5))
            for i in range(num_segments):
                a1 = angle_start + (angle_end - angle_start) * i / num_segments
                a2 = angle_start + (angle_end - angle_start) * (i + 1) / num_segments
                
                # 開始点と終了点を計算
                x1 = center[0] + (radius - 5) * np.cos(np.radians(a1))
                y1 = center[1] + (radius - 5) * np.sin(np.radians(a1))
                x2 = center[0] + (radius - 5) * np.cos(np.radians(a2))
                y2 = center[1] + (radius - 5) * np.sin(np.radians(a2))
                
                cv2.line(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 3)
        
        # 針を描画
        needle_length = radius - 10
        needle_x = center[0] + needle_length * np.cos(np.radians(angle))
        needle_y = center[1] + needle_length * np.sin(np.radians(angle))
        
        cv2.line(frame, center, (int(needle_x), int(needle_y)), color, 2)
        cv2.circle(frame, center, 3, color, -1)
        
        # ラベルと値
        text = f"{value:.1f} {unit}"
        text_size = cv2.getTextSize(text, self.font, self.font_scale_small, 1)[0]
        text_x = center[0] - text_size[0] // 2
        text_y = center[1] + radius + 15
        
        cv2.putText(frame, text, (text_x, text_y), self.font, 
                   self.font_scale_small, color, 1, cv2.LINE_AA)
        
        # ラベル
        label_size = cv2.getTextSize(label, self.font, self.font_scale_small, 1)[0]
        label_x = center[0] - label_size[0] // 2
        label_y = text_y + 15
        
        cv2.putText(frame, label, (label_x, label_y), self.font,
                   self.font_scale_small, self.text_color, 1, cv2.LINE_AA)
    
    def _draw_events(self, frame: np.ndarray, timestamp: float) -> np.ndarray:
        """イベント表示を描画"""
        h, w = frame.shape[:2]
        
        # フラッシュ効果
        if self.is_flashing:
            flash_intensity = 0.5 * (1 + np.sin(timestamp * 20))  # 高速点滅
            overlay = frame.copy()
            overlay[:] = self.warning_color
            cv2.addWeighted(overlay, flash_intensity * 0.3, frame, 1 - flash_intensity * 0.3, 0, dst=frame)
            
            # "RELEASE!" テキスト
            release_text = "RELEASE!"
            text_size = cv2.getTextSize(release_text, self.font, self.font_scale_large * 2, 3)[0]
            text_x = (w - text_size[0]) // 2
            text_y = h // 2
            
            # 背景
            cv2.rectangle(frame, (text_x - 20, text_y - text_size[1] - 10),
                         (text_x + text_size[0] + 20, text_y + 10),
                         (0, 0, 0), -1)
            
            cv2.putText(frame, release_text, (text_x, text_y), self.font,
                       self.font_scale_large * 2, self.warning_color, 3, cv2.LINE_AA)
        
        # イベント履歴表示
        event_y = h - 30
        for event in reversed(self.event_history[-3:]):  # 最新3件
            age = timestamp - event['timestamp']
            alpha = max(0, 1 - age / 5.0)  # 5秒でフェードアウト
            
            if alpha > 0:
                color = tuple(int(c * alpha) for c in self.accent_color)
                cv2.putText(frame, event['message'], (10, event_y), self.font,
                           self.font_scale_medium, color, 1, cv2.LINE_AA)
                event_y -= 25
        
        return frame