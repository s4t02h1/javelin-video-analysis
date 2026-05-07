from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple
import numpy as np

RIGHT_WRIST_IDX = 16

@dataclass
class AdaptedLandmarks:
    points: np.ndarray  # (N,3) x,y,vis
    right_wrist: Optional[Tuple[int, int]]
    fps: float
    px2m: float

def _estimate_px2m(points_xy: np.ndarray, height_m: Optional[float]) -> float:
    if height_m is None or height_m <= 0 or points_xy.size == 0:
        return 1.0
    ys = points_xy[:, 1]
    finite = np.isfinite(ys)
    if not finite.any():
        return 1.0
    h_px = float(np.nanmax(ys[finite]) - np.nanmin(ys[finite]))
    return (float(height_m) / h_px) if h_px > 1 else 1.0

def adapt_state(state: Dict[str, Any], height_m: Optional[float]) -> AdaptedLandmarks:
    pts_list = state.get("points") or []
    N = len(pts_list)
    pts = np.zeros((N, 3), dtype=np.float32)
    for i, p in enumerate(pts_list):
        if p is None:
            pts[i] = (np.nan, np.nan, 0.0)
        else:
            pts[i] = (float(p[0]), float(p[1]), 1.0)
    rw = None
    if N > RIGHT_WRIST_IDX and pts_list[RIGHT_WRIST_IDX] is not None:
        rw = (int(pts_list[RIGHT_WRIST_IDX][0]), int(pts_list[RIGHT_WRIST_IDX][1]))
    fps = float(state.get("fps") or state.get("FPS") or 30.0)
    px2m = _estimate_px2m(pts[:, :2], height_m)
    return AdaptedLandmarks(points=pts, right_wrist=rw, fps=fps, px2m=px2m)