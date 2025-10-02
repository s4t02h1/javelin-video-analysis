"""
heatmap.py - ヒートマップ描画モジュール

身体部位の速度をカラーマップで可視化する。
"""

import numpy as np
import cv2
from typing import Dict, Any, Tuple, Optional
import logging

from .registry import VisualPassBase
from .adapters import AdaptedLandmarks
from .kinematics import KinematicsBuffer, calculate_body_segments_speed

logger = logging.getLogger(__name__)


class HeatmapPass(VisualPassBase):
    """速度ヒートマップの描画"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # 描画設定
        self.radius = config.get("radius", 24)
        self.alpha = config.get("alpha", 0.35)
        self.colormap = config.get("colormap", cv2.COLORMAP_JET)
        self.max_speed_threshold = config.get("max_speed", 50.0)  # px/s or m/s
        self.min_speed_threshold = config.get("min_speed", 2.0)
        
        # 平滑化設定
        self.smooth_method = config.get("smooth", "ema")
        self.ema_alpha = config.get("ema_alpha", 0.3)
        
        # 描画する関節の設定
        self.target_joints = config.get("target_joints", [
            11, 12,  # 肩
            13, 14,  # 肘
            15, 16,  # 手首  
            23, 24,  # 腰
            25, 26,  # 膝
            27, 28,  # 足首
        ])
        
        # 運動学バッファ
        self.kinematics = KinematicsBuffer(
            smooth_method=self.smooth_method,
            ema_alpha=self.ema_alpha
        )
        
        # 動的スケール調整
        self.adaptive_scale = config.get("adaptive_scale", True)
        self.speed_history = []
        self.max_history_length = 60  # 2秒分のフレーム数
        
        self.frame_count = 0
    
    def apply(self, frame: np.ndarray, landmarks: AdaptedLandmarks) -> np.ndarray:
        """ヒートマップを描画"""
        if not self.enabled:
            return frame
        
        # 運動学データを更新
        timestamp = self.frame_count / landmarks.fps
        positions = landmarks.points[:, :2]
        self.kinematics.add_frame(positions, timestamp)
        
        # 現在の運動学データを取得
        kinematics_data = self.kinematics.get_current_kinematics()
        speeds = kinematics_data['speed'] * landmarks.px2m  # 物理単位に変換
        
        # 速度履歴を更新（動的スケール用）
        if self.adaptive_scale:
            self._update_speed_history(speeds)
        
        # ヒートマップを描画
        result = self._draw_heatmap(frame, landmarks, speeds)
        
        self.frame_count += 1
        return result
    
    def _update_speed_history(self, speeds: np.ndarray):
        """速度履歴を更新（動的スケール調整用）"""
        valid_speeds = speeds[speeds > 0]
        if len(valid_speeds) > 0:
            max_speed = np.max(valid_speeds)
            self.speed_history.append(max_speed)
        
        # 履歴長さ制限
        if len(self.speed_history) > self.max_history_length:
            self.speed_history = self.speed_history[-self.max_history_length:]
    
    def _get_speed_scale(self) -> Tuple[float, float]:
        """現在の速度スケールを取得"""
        if self.adaptive_scale and self.speed_history:
            # 最近の最大速度の90パーセンタイルを使用
            recent_max = np.percentile(self.speed_history, 90)
            max_speed = max(self.max_speed_threshold, recent_max * 1.2)
        else:
            max_speed = self.max_speed_threshold
        
        return self.min_speed_threshold, max_speed
    
    def _draw_heatmap(self, frame: np.ndarray, landmarks: AdaptedLandmarks, 
                     speeds: np.ndarray) -> np.ndarray:
        """ヒートマップを描画"""
        h, w = frame.shape[:2]
        
        # ヒートマップレイヤーを作成
        heatmap_layer = np.zeros((h, w), dtype=np.float32)
        
        # 速度スケールを取得
        min_speed, max_speed = self._get_speed_scale()
        
        # 各関節にヒートマップを描画
        for joint_idx in self.target_joints:
            if joint_idx >= len(landmarks.points) or joint_idx >= len(speeds):
                continue
            
            # 関節の信頼度チェック
            if landmarks.points[joint_idx, 2] < 0.5:
                continue
            
            # 関節位置
            joint_pos = landmarks.points[joint_idx, :2].astype(int)
            
            # フレーム境界チェック
            if not (0 <= joint_pos[0] < w and 0 <= joint_pos[1] < h):
                continue
            
            # 速度を正規化
            speed = speeds[joint_idx]
            if speed < min_speed:
                continue
            
            normalized_speed = np.clip((speed - min_speed) / (max_speed - min_speed), 0.0, 1.0)
            
            # ガウシアン分布でヒートマップに寄与
            self._add_gaussian_heatspot(heatmap_layer, joint_pos, normalized_speed)
        
        # カラーマップを適用
        if np.max(heatmap_layer) > 0:
            result = self._apply_colormap(frame, heatmap_layer)
        else:
            result = frame
        
        # 凡例を描画（オプション）
        if hasattr(self, 'show_legend') and self.show_legend:
            result = self._draw_legend(result, min_speed, max_speed)
        
        return result
    
    def _add_gaussian_heatspot(self, heatmap: np.ndarray, center: np.ndarray, intensity: float):
        """ガウシアン分布のヒートスポットを追加"""
        h, w = heatmap.shape
        cx, cy = center
        
        # ガウシアンカーネルのサイズ
        kernel_size = self.radius * 2 + 1
        
        # カーネルの範囲を計算
        x_min = max(0, cx - self.radius)
        x_max = min(w, cx + self.radius + 1)
        y_min = max(0, cy - self.radius) 
        y_max = min(h, cy + self.radius + 1)
        
        if x_min >= x_max or y_min >= y_max:
            return
        
        # ガウシアンカーネルを生成
        y_indices, x_indices = np.mgrid[y_min:y_max, x_min:x_max]
        
        # 中心からの距離
        distances = np.sqrt((x_indices - cx)**2 + (y_indices - cy)**2)
        
        # ガウシアン分布（シグマ = radius/3）
        sigma = self.radius / 3.0
        gaussian = np.exp(-(distances**2) / (2 * sigma**2))
        
        # 強度を適用してヒートマップに加算
        heatmap[y_min:y_max, x_min:x_max] += gaussian * intensity
    
    def _apply_colormap(self, frame: np.ndarray, heatmap: np.ndarray) -> np.ndarray:
        """カラーマップを適用してフレームに合成"""
        # ヒートマップを0-255に正規化
        if np.max(heatmap) > 0:
            normalized_heatmap = (heatmap / np.max(heatmap) * 255).astype(np.uint8)
        else:
            return frame
        
        # カラーマップを適用
        colored_heatmap = cv2.applyColorMap(normalized_heatmap, self.colormap)
        
        # マスクを作成（ゼロ以外の部分のみ）
        mask = normalized_heatmap > 0
        
        # アルファブレンディングで合成
        result = frame.copy()
        
        for c in range(3):
            result[:, :, c] = np.where(
                mask,
                frame[:, :, c] * (1 - self.alpha) + colored_heatmap[:, :, c] * self.alpha,
                frame[:, :, c]
            ).astype(np.uint8)
        
        return result
    
    def _draw_legend(self, frame: np.ndarray, min_speed: float, max_speed: float) -> np.ndarray:
        """凡例を描画"""
        h, w = frame.shape[:2]
        
        # 凡例のサイズと位置
        legend_width = 20
        legend_height = 100
        margin = 10
        x = w - legend_width - margin
        y = margin
        
        # カラーバーを生成
        colorbar = np.linspace(255, 0, legend_height).astype(np.uint8)
        colorbar = np.repeat(colorbar[:, np.newaxis], legend_width, axis=1)
        colored_bar = cv2.applyColorMap(colorbar, self.colormap)
        
        # フレームに貼り付け
        frame[y:y+legend_height, x:x+legend_width] = colored_bar
        
        # 枠線
        cv2.rectangle(frame, (x, y), (x+legend_width, y+legend_height), (255, 255, 255), 1)
        
        # ラベル
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.4
        thickness = 1
        
        # 単位を決定
        unit = "m/s" if min_speed < 10 else "px/s"  # 簡易判定
        
        # 最大値ラベル
        max_label = f"{max_speed:.1f}{unit}"
        cv2.putText(frame, max_label, (x - 50, y + 10), font, font_scale, (255, 255, 255), thickness)
        
        # 最小値ラベル
        min_label = f"{min_speed:.1f}"
        cv2.putText(frame, min_label, (x - 30, y + legend_height), font, font_scale, (255, 255, 255), thickness)
        
        return frame


class SegmentHeatmapPass(HeatmapPass):
    """身体部位別ヒートマップ"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # 部位別の設定をオーバーライド
        self.segment_colors = config.get("segment_colors", {
            "head": cv2.COLORMAP_COOL,
            "torso": cv2.COLORMAP_AUTUMN,
            "arms": cv2.COLORMAP_SUMMER,
            "legs": cv2.COLORMAP_SPRING
        })
    
    def apply(self, frame: np.ndarray, landmarks: AdaptedLandmarks) -> np.ndarray:
        """部位別ヒートマップを描画"""
        if not self.enabled:
            return frame
        
        # 運動学データを更新
        timestamp = self.frame_count / landmarks.fps
        positions = landmarks.points[:, :2]
        self.kinematics.add_frame(positions, timestamp)
        
        # 部位別速度を計算
        kinematics_data = self.kinematics.get_current_kinematics()
        speeds = kinematics_data['speed'] * landmarks.px2m
        
        segment_speeds = calculate_body_segments_speed(landmarks.points, kinematics_data['velocity'])
        
        # 各部位別にヒートマップを描画
        result = frame.copy()
        
        # 実装は簡略化：基本のヒートマップを使用
        result = self._draw_heatmap(frame, landmarks, speeds)
        
        self.frame_count += 1
        return result