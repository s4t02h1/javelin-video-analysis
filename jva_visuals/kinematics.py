from __future__ import annotations
from typing import Optional, Dict, Any
import numpy as np

class EMA:
    def __init__(self, alpha: float = 0.3):
        self.alpha = float(alpha)
        self._y: Optional[np.ndarray] = None
    def update(self, x: Optional[np.ndarray]) -> Optional[np.ndarray]:
        if x is None: return self._y
        x = np.asarray(x, dtype=np.float32)
        self._y = x if self._y is None else self.alpha * x + (1.0 - self.alpha) * self._y
        return self._y

class KinematicsHelper:
    def __init__(self, smooth: str = "ema", ema_alpha: float = 0.3):
        self.prev_pts: Optional[np.ndarray] = None
        self.prev_vel: Optional[np.ndarray] = None
        self.ema_v = EMA(ema_alpha) if smooth == "ema" else None
        self.ema_a = EMA(ema_alpha) if smooth == "ema" else None
    def update(self, pts_xy: np.ndarray, dt: float) -> Dict[str, Any]:
        N = pts_xy.shape[0]
        vel = np.full((N, 2), np.nan, np.float32)
        acc = np.full((N, 2), np.nan, np.float32)
        if self.prev_pts is not None and dt > 0:
            vel = (pts_xy - self.prev_pts) / dt
            if self.ema_v: vel = self.ema_v.update(vel)  # type: ignore
        if self.prev_vel is not None and dt > 0:
            acc = (vel - self.prev_vel) / dt
            if self.ema_a: acc = self.ema_a.update(acc)  # type: ignore
        self.prev_pts, self.prev_vel = pts_xy, vel
        return {"vel": vel, "acc": acc}