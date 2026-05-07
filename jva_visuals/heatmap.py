from __future__ import annotations
from typing import Dict, Any
import numpy as np, cv2
from .adapters import adapt_state
from .kinematics import KinematicsHelper

def _color(val, vmin, vmax):
    if not np.isfinite(val) or vmax <= vmin: return (0,0,0)
    t = float(np.clip((val - vmin) / (vmax - vmin), 0, 1))
    r = int(255 * t); b = int(255 * (1 - t)); g = int(255 * (0.5 * (1 - abs(2 * t - 1))))
    return (b, g, r)

class HeatmapPass:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self.radius = int(self.cfg.get("radius", 24))
        self.alpha = float(self.cfg.get("alpha", 0.35))
        self.helper = KinematicsHelper()
        self.hist: list[float] = []
    def apply(self, frame, state: Dict[str, Any]):
        ad = adapt_state(state, height_m=None)
        pts = ad.points[:, :2]
        kin = self.helper.update(pts, 1.0 / max(1.0, ad.fps))
        speed = np.linalg.norm(kin["vel"], axis=1)
        finite = speed[np.isfinite(speed)]
        if finite.size:
            self.hist.extend(finite.tolist()); self.hist = self.hist[-4000:]
        vmin = np.nanquantile(self.hist, 0.05) if self.hist else 0.0
        vmax = np.nanquantile(self.hist, 0.95) if self.hist else 1.0
        heat = np.zeros_like(frame, np.uint8)
        for i in range(pts.shape[0]):
            x, y = pts[i]
            if not np.isfinite(x + y): continue
            cv2.circle(heat, (int(x), int(y)), self.radius, _color(float(speed[i]), vmin, vmax), -1, lineType=cv2.LINE_AA)
        return cv2.addWeighted(frame, 1.0, heat, self.alpha, 0)