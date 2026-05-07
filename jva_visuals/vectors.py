from __future__ import annotations
from typing import Dict, Any
import numpy as np, cv2
from .adapters import adapt_state
from .kinematics import KinematicsHelper

class VectorsPass:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self.scale = float(self.cfg.get("scale", 0.6))
        self.helper = KinematicsHelper(
            smooth=str(self.cfg.get("smooth", "ema")),
            ema_alpha=float(self.cfg.get("ema_alpha", 0.3)),
        )
    def _arrow(self, img, p, v, color, dotted=False):
        if not np.all(np.isfinite(v)): return
        p = (int(p[0]), int(p[1]))
        p2 = (int(p[0] + v[0] * self.scale), int(p[1] + v[1] * self.scale))
        if dotted:
            for t in np.linspace(0, 1, 12):
                q = (int(p[0] + (p2[0]-p[0])*t), int(p[1] + (p2[1]-p[1])*t))
                cv2.circle(img, q, 2, color, -1, lineType=cv2.LINE_AA)
        else:
            cv2.arrowedLine(img, p, p2, color, 2, tipLength=0.2)
    def apply(self, frame, state: Dict[str, Any]):
        ad = adapt_state(state, height_m=None)
        pts = ad.points[:, :2]
        kin = self.helper.update(pts, 1.0 / max(1.0, ad.fps))
        for i in range(pts.shape[0]):
            x, y = pts[i]
            if not np.isfinite(x + y): continue
            self._arrow(frame, (x, y), kin["vel"][i], (50, 220, 50), dotted=False)
            self._arrow(frame, (x, y), kin["acc"][i], (50, 50, 230), dotted=True)
        return frame