"""
registry.py - 可視化パスの登録と管理

プラグイン方式で各種可視化機能を組み合わせて適用する。
デフォルトでは何も有効にならず、後方互換性を保つ。
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import numpy as np
import cv2

from .adapters import AdaptedLandmarks, adapt_state

logger = logging.getLogger(__name__)


class VisualPassBase(ABC):
    """可視化パスの基底クラス"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("enabled", True)
    
    @abstractmethod
    def apply(self, frame: np.ndarray, landmarks: AdaptedLandmarks) -> np.ndarray:
        """
        フレームに可視化を適用
        
        Args:
            frame: 入力フレーム (BGR)
            landmarks: 標準化されたランドマーク
        
        Returns:
            np.ndarray: 可視化を適用したフレーム
        """
        pass
    
    def is_enabled(self) -> bool:
        return self.enabled


class VisualPassRegistry:
    """可視化パスのレジストリ"""
    
    @staticmethod
    def build_from_config(visuals_config: Dict[str, Any], 
                         fps: float = 30.0, 
                         height_m: Optional[float] = None) -> List[VisualPassBase]:
        """
        設定から可視化パスのリストを構築
        
        Args:
            visuals_config: 可視化設定辞書
            fps: フレームレート
            height_m: 身長（メートル）
        
        Returns:
            List[VisualPassBase]: 有効な可視化パスのリスト
        """
        if not visuals_config:
            return []  # 設定が空の場合は何も追加しない（後方互換）
        
        passes = []
        
        # 適用順序の定義（重要：描画の重なり順）
        pass_order = [
            "wrist_trail",
            "vectors", 
            "heatmap",
            "hud",
            "glow_trail"  # 最後に適用（最前面）
        ]
        
        for pass_name in pass_order:
            if visuals_config.get(pass_name, False):
                pass_config = visuals_config.get(f"{pass_name}_cfg", {})
                pass_config["fps"] = fps
                pass_config["height_m"] = height_m
                
                visual_pass = VisualPassRegistry._create_pass(pass_name, pass_config)
                if visual_pass and visual_pass.is_enabled():
                    passes.append(visual_pass)
                    logger.info(f"Enabled visual pass: {pass_name}")
        
        logger.info(f"Created {len(passes)} visual passes")
        return passes
    
    @staticmethod
    def _create_pass(pass_name: str, config: Dict[str, Any]) -> Optional[VisualPassBase]:
        """個別の可視化パスを作成"""
        try:
            if pass_name == "wrist_trail":
                from .trails import WristTrailPass
                return WristTrailPass(config)
            elif pass_name == "glow_trail":
                from .trails import GlowTrailPass
                return GlowTrailPass(config)
            elif pass_name == "vectors":
                from .vectors import VectorPass
                return VectorPass(config)
            elif pass_name == "heatmap":
                from .heatmap import HeatmapPass
                return HeatmapPass(config)
            elif pass_name == "hud":
                from .hud import HUDPass
                return HUDPass(config)
            else:
                logger.warning(f"Unknown visual pass: {pass_name}")
                return None
        except ImportError as e:
            logger.warning(f"Failed to import visual pass {pass_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create visual pass {pass_name}: {e}")
            return None


class VisualPipeline:
    """可視化パイプライン"""
    
    def __init__(self, passes: List[VisualPassBase]):
        self.passes = passes
    
    def apply_all(self, frame: np.ndarray, state: Dict[str, Any], 
                  fps: float = 30.0, height_m: Optional[float] = None) -> np.ndarray:
        """
        すべての可視化パスを順次適用
        
        Args:
            frame: 入力フレーム
            state: PoseAnalyzer状態
            fps: フレームレート
            height_m: 身長（メートル）
        
        Returns:
            np.ndarray: 可視化適用後のフレーム
        """
        if not self.passes:
            return frame  # パスがない場合はそのまま返す
        
        # 状態を標準形式に変換
        landmarks = adapt_state(state, fps, height_m, frame.shape[:2])
        
        # 各パスを順次適用
        result = frame.copy()
        for visual_pass in self.passes:
            try:
                result = visual_pass.apply(result, landmarks)
            except Exception as e:
                logger.error(f"Error in visual pass {type(visual_pass).__name__}: {e}")
                continue
        
        return result