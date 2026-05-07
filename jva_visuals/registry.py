from __future__ import annotations
from typing import List, Dict, Any
import numpy as np

class VisualPassBase:
    def __init__(self, cfg: Dict[str, Any] | None = None) -> None:
        self.cfg = cfg or {}

    def apply(self, frame: np.ndarray, state: Dict[str, Any]) -> np.ndarray:
        return frame

class VisualPassRegistry:
    @staticmethod
    def build_from_config(vconf: Dict[str, Any] | None) -> List[VisualPassBase]:
        vconf = vconf or {}
        passes: List[VisualPassBase] = []
        from .trails import WristTrailPass, GlowTrailPass
        from .vectors import VectorsPass
        from .heatmap import HeatmapPass
        from .hud import HudPass

        if vconf.get("wrist_trail", False):
            passes.append(WristTrailPass(vconf.get("trail_cfg", {})))
        if vconf.get("vectors", False):
            passes.append(VectorsPass(vconf.get("vectors_cfg", {})))
        if vconf.get("heatmap", False):
            passes.append(HeatmapPass(vconf.get("heatmap_cfg", {})))
        if vconf.get("hud", False):
            passes.append(HudPass(vconf.get("hud_cfg", {})))
        if vconf.get("glow_trail", False):
            passes.append(GlowTrailPass(vconf.get("glow_trail_cfg", {})))
        return passes

    @staticmethod
    def apply_all(frame: np.ndarray, state: Dict[str, Any], passes: List[VisualPassBase]) -> np.ndarray:
        out = frame
        for p in passes:
            try:
                out = p.apply(out, state)
            except Exception:
                # 例外は握りつぶして可視化のみ無効化（本流は継続）
                continue
        return out