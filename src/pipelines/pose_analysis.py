import cv2
import numpy as np
import mediapipe as mp
import math
from typing import Optional, Tuple

COLORMAPS = {
    "jet": cv2.COLORMAP_JET,
    "turbo": getattr(cv2, "COLORMAP_TURBO", cv2.COLORMAP_JET),
    "plasma": cv2.COLORMAP_PLASMA,
    "viridis": cv2.COLORMAP_VIRIDIS,
    "hot": cv2.COLORMAP_HOT,
}

def _normalize01(value: Optional[float], vmin: float, vmax: float) -> float:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return 0.0
    if vmax <= vmin:
        return 0.0
    x = max(vmin, min(vmax, float(value)))
    return (x - vmin) / (vmax - vmin)

def to_bgr(value: Optional[float], vmin: float, vmax: float, cmap_name: str = "turbo") -> Tuple[int, int, int]:
    """Map scalar to BGR color tuple using OpenCV colormaps."""
    norm = _normalize01(value, vmin, vmax)
    idx = int(round(norm * 255.0))
    arr = np.array([[idx]], dtype=np.uint8)
    cmap = COLORMAPS.get(cmap_name, cv2.COLORMAP_JET)
    colored = cv2.applyColorMap(arr, cmap)
    b, g, r = colored[0, 0].tolist()
    return int(b), int(g), int(r)

RIGHT_WRIST_IDX = 16
VIS_THRESH = 0.5

class PoseAnalyzer:
    def __init__(self, model_complexity=1, min_det_conf=0.5, min_track_conf=0.5, max_path_len=300, meters_per_pixel=None):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            enable_segmentation=False,
            min_detection_confidence=min_det_conf,
            min_tracking_confidence=min_track_conf
        )
        self.connections = list(self.mp_pose.POSE_CONNECTIONS)
        self.prev_points = None
        self.velocities = None
        self.right_wrist_path = []
        self.max_path_len = max_path_len
        self.max_speed = 1.0     # カラーマップのダイナミックレンジ
        self.m_per_px = meters_per_pixel  # 実寸換算スケール（m/px） 未指定ならpx/s

    # スケール設定
    def set_scale(self, meters_per_pixel: float):
        if meters_per_pixel and meters_per_pixel > 0:
            self.m_per_px = float(meters_per_pixel)

    def set_scale_from_reference(self, reference_pixels: float, reference_meters: float):
        if reference_pixels and reference_meters and reference_pixels > 0:
            self.m_per_px = float(reference_meters) / float(reference_pixels)

    def close(self):
        if hasattr(self.pose, "close"):
            self.pose.close()

    # 内部ユーティリティ
    def _landmarks_to_points(self, frame_shape, landmarks):
        h, w = frame_shape[:2]
        pts = [None] * 33
        for i, lm in enumerate(landmarks.landmark):
            if lm.visibility is None or lm.visibility < VIS_THRESH:
                pts[i] = None
            else:
                x = int(lm.x * w); y = int(lm.y * h)
                pts[i] = (x, y) if (0 <= x < w and 0 <= y < h) else None
        return pts

    def _compute_com(self, points):
        xs, ys = [], []
        for p in points:
            if p is not None:
                xs.append(p[0]); ys.append(p[1])
        if not xs:
            return None
        return (int(np.mean(xs)), int(np.mean(ys)))

    def _compute_velocities(self, points, fps):
        if self.prev_points is None:
            self.velocities = np.zeros(33, dtype=np.float32)
            return
        v = np.zeros(33, dtype=np.float32)
        for i in range(33):
            p0 = self.prev_points[i]; p1 = points[i]
            if p0 is not None and p1 is not None and fps > 0:
                dist_px = float(np.hypot(p1[0]-p0[0], p1[1]-p0[1]))
                dist = dist_px * self.m_per_px if self.m_per_px else dist_px  # m or px
                v[i] = dist * fps  # m/s or px/s
            else:
                v[i] = 0.0
        self.velocities = v
        max_v = float(np.max(v))
        if max_v > self.max_speed:
            self.max_speed = max_v

    def _speed_to_bgr(self, speed):
        # 0..max_speed -> 0..255 に正規化して RAINBOW（赤橙黄緑青藍紫）
        denom = max(self.max_speed, 1e-6)
        val = int(np.clip(speed / denom, 0.0, 1.0) * 255)
        cm = cv2.applyColorMap(np.array([[val]], dtype=np.uint8), cv2.COLORMAP_RAINBOW)
        return (int(cm[0,0,0]), int(cm[0,0,1]), int(cm[0,0,2]))  # BGR

    def _draw_colorbar(self, img, max_speed, unit='px/s', width=26, margin=8):
        h, w = img.shape[:2]
        bar_h = int(h * 0.8)
        bar_w = width
        x0 = w - bar_w - margin
        y0 = int((h - bar_h) / 2)

        # 縦グラデーション 0..255
        grad = np.linspace(255, 0, bar_h, dtype=np.uint8).reshape(bar_h, 1)
        grad = np.repeat(grad, bar_w, axis=1)
        grad_color = cv2.applyColorMap(grad, cv2.COLORMAP_RAINBOW)

        # 右端に貼り付け
        img[y0:y0+bar_h, x0:x0+bar_w] = cv2.addWeighted(
            img[y0:y0+bar_h, x0:x0+bar_w], 0.3, grad_color, 0.7, 0
        )

        # 枠
        cv2.rectangle(img, (x0, y0), (x0+bar_w, y0+bar_h), (255, 255, 255), 1)

        # 目盛りとラベル
        font = cv2.FONT_HERSHEY_SIMPLEX
        top_val = f"{max_speed:.1f} {unit}"
        mid_val = f"{max_speed/2:.1f}"
        bot_val = "0.0"
        cv2.putText(img, top_val, (x0 - 5 - 8*len(top_val), y0 + 10), font, 0.45, (255,255,255), 1, cv2.LINE_AA)
        cv2.putText(img, mid_val, (x0 - 5 - 8*len(mid_val), y0 + bar_h//2 + 4), font, 0.45, (255,255,255), 1, cv2.LINE_AA)
        cv2.putText(img, bot_val, (x0 - 5 - 8*len(bot_val), y0 + bar_h), font, 0.45, (255,255,255), 1, cv2.LINE_AA)

    def _draw_axes(self, img, origin=None, axis_len=150, color=(0, 0, 0)):
        h, w = img.shape[:2]
        ox, oy = (40, h - 40) if origin is None else origin
        thickness = 2

        # X軸（右向き）
        cv2.arrowedLine(img, (ox, oy), (ox + axis_len, oy), color, thickness, tipLength=0.05)
        cv2.putText(img, 'X', (ox + axis_len + 8, oy + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

        # Y軸（上向き）
        cv2.arrowedLine(img, (ox, oy), (ox, oy - axis_len), color, thickness, tipLength=0.05)
        cv2.putText(img, 'Y', (ox - 12, oy - axis_len - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

        # 薄いグリッド
        overlay = img.copy()
        step = 50
        grid_color = (0, 0, 0)

        for x in range(ox, w, step):
            cv2.line(overlay, (x, 0), (x, h), grid_color, 1)
        for x in range(ox, 0, -step):
            cv2.line(overlay, (x, 0), (x, h), grid_color, 1)
        for y in range(oy, h, step):
            cv2.line(overlay, (0, y), (w, y), grid_color, 1)
        for y in range(oy, 0, -step):
            cv2.line(overlay, (0, y), (w, y), grid_color, 1)

        img[:] = cv2.addWeighted(overlay, 0.15, img, 0.85, 0)

    # メイン処理
    def process(self, frame, fps):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = self.pose.process(rgb)

        points = [None] * 33
        if res.pose_landmarks:
            points = self._landmarks_to_points(frame.shape, res.pose_landmarks)

        self._compute_velocities(points, fps)

        # 右手首の軌跡更新
        rw = points[RIGHT_WRIST_IDX] if RIGHT_WRIST_IDX < len(points) else None
        if rw is not None:
            self.right_wrist_path.append(rw)
            if len(self.right_wrist_path) > self.max_path_len:
                self.right_wrist_path = self.right_wrist_path[-self.max_path_len:]

        com = self._compute_com(points)
        self.prev_points = points

        return {"points": points, "com": com, "velocities": self.velocities}

    # 可視化
    def render_basic(self, frame, state):
        img = frame.copy()
        # 細い白線（変更なし）
        for a, b in self.connections:
            pa = state["points"][a] if a < len(state["points"]) else None
            pb = state["points"][b] if b < len(state["points"]) else None
            if pa is not None and pb is not None:
                cv2.line(img, pa, pb, (255, 255, 255), 1)
        # 白点のみ（黒枠なし／サイズ半分程度）
        for p in state["points"]:
            if p is not None:
                cv2.circle(img, p, 3, (255, 255, 255), -1)
        # 重心（赤）
        if state["com"] is not None:
            cv2.circle(img, state["com"], 8, (0,0,255), -1)
        # 右手首の軌跡（白・半透明）
        if len(self.right_wrist_path) >= 2:
            overlay = img.copy()
            for i in range(1, len(self.right_wrist_path)):
                cv2.line(overlay, self.right_wrist_path[i-1], self.right_wrist_path[i], (255,255,255), 2)
            img = cv2.addWeighted(overlay, 0.45, img, 0.55, 0)

        return img

    def render_heatmap(self, frame, state):
        base = frame.copy()
        v = state["velocities"] if state["velocities"] is not None else np.zeros(33, dtype=np.float32)

        # まず白線をそのまま描画（線は変化なし）
        result = base.copy()
        for a, b in self.connections:
            pa = state["points"][a] if a < len(state["points"]) else None
            pb = state["points"][b] if b < len(state["points"]) else None
            if pa is not None and pb is not None:
                cv2.line(result, pa, pb, (255, 255, 255), 1)

        # 点だけ速度カラーでオーバーレイ（控えめにブレンド）
        overlay = np.zeros_like(base)
        for i, p in enumerate(state["points"]):
            if p is not None:
                color = self._speed_to_bgr(float(v[i]))  # RAINBOW
                cv2.circle(overlay, p, 3, color, -1)

        # 光量控えめに合成
        img = cv2.addWeighted(result, 0.8, overlay, 0.2, 0)

        # カラーバー（右側）
        unit = "m/s" if self.m_per_px else "px/s"
        self._draw_colorbar(img, max_speed=self.max_speed, unit=unit)
        return img

    def render_stickman(self, frame, state):
        img = frame.copy()
        for a, b in self.connections:
            pa = state["points"][a] if a < len(state["points"]) else None
            pb = state["points"][b] if b < len(state["points"]) else None
            if pa is not None and pb is not None:
                cv2.line(img, pa, pb, (255, 255, 255), 3)
        for p in state["points"]:
            if p is not None:
                cv2.circle(img, p, 5, (255, 255, 255), -1)
        if state["com"] is not None:
            cv2.circle(img, state["com"], 8, (0, 0, 255), -1)
        return img

    def render_stickman_rgba(self, frame_shape, state):
        h, w = frame_shape[:2]
        img = np.zeros((h, w, 4), dtype=np.uint8)  # BGRA
        for a, b in self.connections:
            pa = state["points"][a] if a < len(state["points"]) else None
            pb = state["points"][b] if b < len(state["points"]) else None
            if pa is not None and pb is not None:
                cv2.line(img, pa, pb, (255, 255, 255, 255), 3)
        for p in state["points"]:
            if p is not None:
                cv2.circle(img, p, 5, (255, 255, 255, 255), -1)
        if state["com"] is not None:
            cv2.circle(img, state["com"], 8, (0, 0, 255, 255), -1)
        return img