"""
stickman.py - スティックマン描画モジュール

元映像の代わりに黒背景 + 白ライン + 関節円だけで
シンプルなスティックマンをレンダリングする。
"""

import cv2
import numpy as np
from typing import Dict, Any, List, Tuple, Optional

from .registry import VisualPassBase
from .adapters import AdaptedLandmarks

# MediaPipe Pose のランドマークインデックス
# https://developers.google.com/mediapipe/solutions/vision/pose_landmarker
_CONNECTIONS: List[Tuple[int, int]] = [
    # 顔
    (0, 1), (1, 2), (2, 3), (3, 7),
    (0, 4), (4, 5), (5, 6), (6, 8),
    # 肩
    (11, 12),
    # 左腕
    (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    # 右腕
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    # 胴体
    (11, 23), (12, 24), (23, 24),
    # 左脚
    (23, 25), (25, 27), (27, 29), (27, 31), (29, 31),
    # 右脚
    (24, 26), (26, 28), (28, 30), (28, 32), (30, 32),
]

# 部位別カラー (BGR)
_PART_COLOR: Dict[str, Tuple[int, int, int]] = {
    "face":        (200, 200, 200),
    "left_arm":    (100, 200, 255),   # 水色
    "right_arm":   (255, 160,  80),   # オレンジ
    "torso":       (180, 255, 180),   # 薄緑
    "left_leg":    ( 80, 120, 255),   # 青
    "right_leg":   (255,  80, 120),   # 赤
    "joint":       (255, 255, 255),   # 白
}

# コネクション → 部位のマッピング
_CONN_PART: Dict[Tuple[int, int], str] = {
    **{c: "face"      for c in [(0,1),(1,2),(2,3),(3,7),(0,4),(4,5),(5,6),(6,8)]},
    **{c: "torso"     for c in [(11,12),(11,23),(12,24),(23,24)]},
    **{c: "left_arm"  for c in [(11,13),(13,15),(15,17),(15,19),(15,21),(17,19)]},
    **{c: "right_arm" for c in [(12,14),(14,16),(16,18),(16,20),(16,22),(18,20)]},
    **{c: "left_leg"  for c in [(23,25),(25,27),(27,29),(27,31),(29,31)]},
    **{c: "right_leg" for c in [(24,26),(26,28),(28,30),(28,32),(30,32)]},
}


class StickmanPass(VisualPassBase):
    """
    黒背景にスティックマンを描画するパス。

    元フレームの映像情報を捨て、ランドマークの骨格線・関節のみを描画する。
    やり投げ動作のシルエットを簡潔に確認したい場合に使用する。
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.line_thickness: int   = config.get("line_thickness", 2)
        self.joint_radius:   int   = config.get("joint_radius", 4)
        self.bg_color: Tuple       = tuple(config.get("bg_color", (10, 10, 10)))
        self.vis_threshold: float  = config.get("vis_threshold", 0.3)
        self.show_trail:    bool   = config.get("show_trail", True)
        self.trail_length:  int    = config.get("trail_length", 60)
        self.trail_color: Tuple    = tuple(config.get("trail_color", (0, 220, 255)))

        # リリース後フェードアウト設定
        self.release_threshold: float = config.get("release_threshold", 20.0)  # m/s
        self.fade_frames: int         = config.get("fade_frames", 8)
        self._released: bool          = False
        self._prev_wrist: Optional[Tuple[int, int]] = None

        # 右手首の軌跡バッファ
        self._wrist_trail: List[Tuple[int, int]] = []

    # ── public ───────────────────────────────────────────────────────────────

    def apply(self, frame: np.ndarray, landmarks: AdaptedLandmarks) -> np.ndarray:
        h, w = frame.shape[:2]
        canvas = np.full((h, w, 3), self.bg_color, dtype=np.uint8)

        pts = landmarks.points  # (33, 3) → (x, y, visibility)

        # 骨格線
        for (a, b), part in _CONN_PART.items():
            if a >= len(pts) or b >= len(pts):
                continue
            va, vb = pts[a, 2], pts[b, 2]
            if va < self.vis_threshold or vb < self.vis_threshold:
                continue
            pa = (int(pts[a, 0]), int(pts[a, 1]))
            pb = (int(pts[b, 0]), int(pts[b, 1]))
            color = _PART_COLOR[part]
            cv2.line(canvas, pa, pb, color, self.line_thickness, cv2.LINE_AA)

        # 関節円
        for i in range(len(pts)):
            if pts[i, 2] < self.vis_threshold:
                continue
            cx, cy = int(pts[i, 0]), int(pts[i, 1])
            cv2.circle(canvas, (cx, cy), self.joint_radius,
                       _PART_COLOR["joint"], -1, cv2.LINE_AA)

        # 右手首の軌跡
        if self.show_trail:
            rw = landmarks.right_wrist
            if rw is not None and not self._released:
                wrist_pos = (int(rw[0]), int(rw[1]))
                # リリース検知
                if (self._prev_wrist is not None and
                        landmarks.px2m < 0.5):  # キャリブレーション済みのみ
                    dx = wrist_pos[0] - self._prev_wrist[0]
                    dy = wrist_pos[1] - self._prev_wrist[1]
                    speed_ms = np.sqrt(dx*dx + dy*dy) * landmarks.px2m * landmarks.fps
                    if speed_ms > self.release_threshold:
                        self._released = True
                if not self._released:
                    self._wrist_trail.append(wrist_pos)
                self._prev_wrist = wrist_pos
            # リリース後: 急速フェードアウト
            if self._released and self._wrist_trail:
                remove_n = max(8, len(self._wrist_trail) // self.fade_frames)
                self._wrist_trail = self._wrist_trail[remove_n:]
            if len(self._wrist_trail) > self.trail_length:
                self._wrist_trail = self._wrist_trail[-self.trail_length:]
            self._draw_trail(canvas)

        return canvas

    # ── private ──────────────────────────────────────────────────────────────

    def _draw_trail(self, canvas: np.ndarray) -> None:
        n = len(self._wrist_trail)
        if n < 2:
            return
        for i in range(1, n):
            alpha = i / n          # 古いほど薄く
            r = int(self.trail_color[0] * alpha)
            g = int(self.trail_color[1] * alpha)
            b = int(self.trail_color[2] * alpha)
            thickness = max(1, int(self.line_thickness * alpha))
            cv2.line(canvas, self._wrist_trail[i - 1], self._wrist_trail[i],
                     (r, g, b), thickness, cv2.LINE_AA)
