from __future__ import annotations
from typing import Dict, Any, Optional
import time, numpy as np, cv2
from .adapters import adapt_state

class HudPass:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self.th = float(self.cfg.get("release_speed_threshold_ms", 22.0))
        self.last_flash_at: Optional[float] = None
        self.win = 0.5
    def _gauge(self, img, center, value, vmin, vmax, label):
        cx, cy = center; r = 48
        val = float(np.clip((value - vmin) / max(1e-6, (vmax - vmin)), 0, 1))
        end = int(180 * val)
        cv2.ellipse(img, (cx, cy), (r, r), 0, 0, 180, (80, 80, 80), 4)
        cv2.ellipse(img, (cx, cy), (r, r), 0, 0, end, (0, 200, 255), 6)
        cv2.putText(img, f"{label}: {value:.1f}", (cx - 60, cy + 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1, cv2.LINE_AA)
    def apply(self, frame, state: Dict[str, Any]):
        ad = adapt_state(state, height_m=state.get("height_m"))
        speed_ms = 0.0
        if ad.right_wrist is not None and "velocities" in state:
            idx = 16; v = state["velocities"][idx] if idx < len(state["velocities"]) else None
            if v is not None:
                mag_px = (v[0]**2 + v[1]**2) ** 0.5
                speed_ms = float(mag_px * ad.px2m)
        if speed_ms >= self.th:
            self.last_flash_at = time.time()
        img = frame
        self._gauge(img, (120, 120), speed_ms, 0, max(self.th, 30.0), "Release spd[m/s]")
        active = self.last_flash_at is not None and (time.time() - self.last_flash_at) <= self.win
        if active:
            cv2.putText(img, "RELEASE!", (80, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,0,255), 3, cv2.LINE_AA)
        return img