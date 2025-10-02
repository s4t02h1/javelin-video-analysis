"""
jva_visuals - Javelin Video Analysis 可視化プラグインパッケージ

このパッケージには以下の可視化機能が含まれます：
- ベクトル描画（速度・加速度）
- ヒートマップ
- HUD（ゲーム風UI）
- 光軌跡（グロー効果）
- Blender連携
"""

__version__ = "0.1.0"
__author__ = "javelin-video-analysis team"

from .registry import VisualPassRegistry, VisualPassBase
from .adapters import AdaptedLandmarks, adapt_state

__all__ = [
    "VisualPassRegistry",
    "VisualPassBase", 
    "AdaptedLandmarks",
    "adapt_state"
]