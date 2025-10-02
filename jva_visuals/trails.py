"""
trails.py - 軌跡描画モジュール

右手首の軌跡を描画する機能を提供。
- WristTrailPass: 通常の軌跡
- GlowTrailPass: 光るエフェクト付き軌跡
"""

import numpy as np
import cv2
from typing import Dict, Any, List, Tuple
import logging

from .registry import VisualPassBase
from .adapters import AdaptedLandmarks

logger = logging.getLogger(__name__)


class WristTrailPass(VisualPassBase):
    """右手首軌跡の描画"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.max_trail_length = config.get("max_length", 200)
        self.line_thickness = config.get("thickness", 2)
        self.color = config.get("color", (255, 255, 255))  # BGR
        self.fade_alpha = config.get("fade_alpha", True)
        
        # 軌跡バッファ
        self.trail_points: List[Tuple[int, int]] = []
    
    def apply(self, frame: np.ndarray, landmarks: AdaptedLandmarks) -> np.ndarray:
        """軌跡を描画"""
        if not self.enabled:
            return frame
        
        # 右手首の位置を取得
        right_wrist = landmarks.right_wrist
        if right_wrist is not None:
            # 整数座標に変換
            wrist_pos = (int(right_wrist[0]), int(right_wrist[1]))
            
            # フレーム境界チェック
            h, w = landmarks.frame_shape
            if 0 <= wrist_pos[0] < w and 0 <= wrist_pos[1] < h:
                self.trail_points.append(wrist_pos)
        
        # バッファサイズ制限
        if len(self.trail_points) > self.max_trail_length:
            self.trail_points = self.trail_points[-self.max_trail_length:]
        
        # 軌跡を描画
        if len(self.trail_points) >= 2:
            result = frame.copy()
            self._draw_trail(result)
            return result
        
        return frame
    
    def _draw_trail(self, frame: np.ndarray):
        """軌跡線を描画"""
        if len(self.trail_points) < 2:
            return
        
        if self.fade_alpha:
            # フェード効果付きで描画
            overlay = frame.copy()
            
            for i in range(1, len(self.trail_points)):
                # 透明度を線形に変化（古い点ほど薄く）
                alpha = i / len(self.trail_points)
                thickness = max(1, int(self.line_thickness * alpha))
                
                cv2.line(overlay, 
                        self.trail_points[i-1], 
                        self.trail_points[i],
                        self.color, 
                        thickness,
                        cv2.LINE_AA)
            
            # 半透明合成
            cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, dst=frame)
        else:
            # 均一な太さで描画
            for i in range(1, len(self.trail_points)):
                cv2.line(frame,
                        self.trail_points[i-1],
                        self.trail_points[i], 
                        self.color,
                        self.line_thickness,
                        cv2.LINE_AA)


class GlowTrailPass(WristTrailPass):
    """光軌跡エフェクト付きの手首軌跡"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.glow_radius = config.get("glow_radius", 15)
        self.glow_intensity = config.get("glow_intensity", 0.8)
        self.glow_color = config.get("glow_color", (0, 255, 255))  # シアン
        self.speed_responsive = config.get("speed_responsive", True)
        self.min_speed_threshold = config.get("min_speed_threshold", 5.0)  # px/s
        
        # 速度履歴
        self.speed_history: List[float] = []
    
    def apply(self, frame: np.ndarray, landmarks: AdaptedLandmarks) -> np.ndarray:
        """光軌跡を描画"""
        if not self.enabled:
            return frame
        
        # 速度情報を更新
        self._update_speed_history(landmarks)
        
        # 基本軌跡を描画
        result = super().apply(frame, landmarks)
        
        # グロー効果を追加
        if len(self.trail_points) >= 2:
            self._add_glow_effect(result)
        
        return result
    
    def _update_speed_history(self, landmarks: AdaptedLandmarks):
        """速度履歴を更新"""
        if landmarks.right_wrist is not None and len(self.trail_points) >= 2:
            # 直近2点から速度を推定
            recent_points = self.trail_points[-2:]
            dx = recent_points[1][0] - recent_points[0][0]
            dy = recent_points[1][1] - recent_points[0][1]
            distance = np.sqrt(dx*dx + dy*dy)
            
            # px/sに変換
            speed = distance * landmarks.fps
            self.speed_history.append(speed)
            
            # 履歴長制限
            if len(self.speed_history) > 30:  
                self.speed_history = self.speed_history[-30:]
        else:
            self.speed_history.append(0.0)
    
    def _add_glow_effect(self, frame: np.ndarray):
        """グロー効果を追加"""
        if len(self.trail_points) < 5:  # 最低限の点数が必要
            return
        
        # 速度応答の計算
        avg_speed = np.mean(self.speed_history[-10:]) if self.speed_history else 0.0
        
        if self.speed_responsive and avg_speed < self.min_speed_threshold:
            return  # 速度が低い場合はグロー効果なし
        
        # グロー強度を速度に応じて調整
        if self.speed_responsive and self.speed_history:
            max_recent_speed = max(self.speed_history[-5:])
            intensity_factor = min(1.0, max_recent_speed / 50.0)  # 50px/sで最大
        else:
            intensity_factor = 1.0
        
        # グロー用のマスクを作成
        h, w = frame.shape[:2]
        glow_mask = np.zeros((h, w), dtype=np.uint8)
        
        # 直近の点群を太い線で描画
        recent_points = self.trail_points[-min(15, len(self.trail_points)):]
        
        for i in range(1, len(recent_points)):
            # 点の新しさに応じて太さを調整
            age_factor = i / len(recent_points)
            thickness = int(self.glow_radius * age_factor * intensity_factor)
            thickness = max(2, thickness)
            
            cv2.line(glow_mask,
                    recent_points[i-1],
                    recent_points[i],
                    255,  # 白で描画
                    thickness,
                    cv2.LINE_AA)
        
        # ガウシアンブラーでグロー効果を作成
        blur_size = int(self.glow_radius * 1.5)
        if blur_size % 2 == 0:
            blur_size += 1
        
        blurred_mask = cv2.GaussianBlur(glow_mask, (blur_size, blur_size), 0)
        
        # カラーマスクに変換
        glow_colored = np.zeros_like(frame)
        glow_colored[:, :, 0] = (blurred_mask * self.glow_color[0] / 255).astype(np.uint8)
        glow_colored[:, :, 1] = (blurred_mask * self.glow_color[1] / 255).astype(np.uint8)
        glow_colored[:, :, 2] = (blurred_mask * self.glow_color[2] / 255).astype(np.uint8)
        
        # 加算合成でグロー効果を適用
        alpha = self.glow_intensity * intensity_factor
        glow_normalized = (blurred_mask / 255.0 * alpha).astype(np.float32)
        
        for c in range(3):
            frame_c = frame[:, :, c].astype(np.float32)
            glow_c = glow_colored[:, :, c].astype(np.float32)
            
            # 加算合成（オーバーフロー制限）
            result_c = frame_c + glow_c * glow_normalized
            frame[:, :, c] = np.clip(result_c, 0, 255).astype(np.uint8)


class TrailManager:
    """複数の軌跡を管理するユーティリティクラス"""
    
    def __init__(self):
        self.trails: Dict[str, List[Tuple[int, int]]] = {}
        self.max_trail_length = 200
    
    def add_point(self, trail_name: str, point: Tuple[int, int]):
        """軌跡に点を追加"""
        if trail_name not in self.trails:
            self.trails[trail_name] = []
        
        self.trails[trail_name].append(point)
        
        # 長さ制限
        if len(self.trails[trail_name]) > self.max_trail_length:
            self.trails[trail_name] = self.trails[trail_name][-self.max_trail_length:]
    
    def get_trail(self, trail_name: str) -> List[Tuple[int, int]]:
        """軌跡を取得"""
        return self.trails.get(trail_name, [])
    
    def clear_trail(self, trail_name: str):
        """軌跡をクリア"""
        if trail_name in self.trails:
            self.trails[trail_name] = []
    
    def clear_all(self):
        """すべての軌跡をクリア"""
        self.trails.clear()