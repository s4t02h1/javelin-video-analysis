from __future__ import annotations
from collections import deque
from typing import Dict, Any, Deque, Tuple
import numpy as np, cv2
from .adapters import adapt_state

class WristTrailPass:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self.maxlen = int(self.cfg.get("maxlen", 120))
        self.color = tuple(self.cfg.get("color", (0, 255, 255)))
        self.thickness = int(self.cfg.get("thickness", 3))
        self._trail: Deque[Tuple[int,int]] = deque(maxlen=self.maxlen)
    def apply(self, frame, state: Dict[str, Any]):
        ad = adapt_state(state, height_m=None)
        if ad.right_wrist is not None:
            self._trail.append(ad.right_wrist)
        if len(self._trail) >= 2:
            cv2.polylines(frame, [np.array(self._trail, np.int32)], False, self.color, self.thickness, lineType=cv2.LINE_AA)
        return frame

class GlowTrailPass(WristTrailPass):
    def apply(self, frame, state: Dict[str, Any]):
        ad = adapt_state(state, height_m=None)
        if ad.right_wrist is not None:
            self._trail.append(ad.right_wrist)
        h, w = frame.shape[:2]
        layer = np.zeros((h, w, 3), np.uint8)
        if len(self._trail) >= 2:
            L = len(self._trail)
            for i, p in enumerate(self._trail):
                r = max(1, int(2 + 8 * (i / L)))
                cv2.circle(layer, p, r, (0, 255, 255), -1, lineType=cv2.LINE_AA)
            layer = cv2.GaussianBlur(layer, (0, 0), 9)
        return cv2.add(frame, layer)