"""
analysis.py — 統合コーチング解析パス

5 種の可視化を 1 パスに統合:
  1. 投擲フェーズバー       — 動画下部に局面を帯状表示
  2. 関節角度アーク         — 肘・肩・腰のリアルタイム角度弧
  3. リリーススナップショット — 検出後 3 秒間の情報パネル
  4. 軌道予測アーク         — リリース後の放物線シミュレーション
  5. 運動連鎖タイムライン   — 部位別速度バー + ピーク順序マーカー
"""

import cv2
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from collections import deque
import logging

from .registry import VisualPassBase
from .adapters import AdaptedLandmarks

logger = logging.getLogger(__name__)

# ── フェーズ定数 ───────────────────────────────────────────────────────────────
PHASE_APPROACH      = 0
PHASE_DELIVERY      = 1
PHASE_RELEASE       = 2
PHASE_FOLLOWTHROUGH = 3

PHASE_NAMES: List[str] = [
    "アプローチ", "デリバリー", "リリース", "フォロースルー"
]

# BGR カラー
PHASE_COLORS: List[Tuple[int, int, int]] = [
    ( 60, 190,  60),   # 緑      — アプローチ
    ( 30, 160, 255),   # オレンジ — デリバリー
    ( 40,  40, 230),   # 赤      — リリース
    (180, 200,  50),   # 黄      — フォロースルー
]

# ── MediaPipe 関節インデックス ─────────────────────────────────────────────────
_R_SHOULDER = 12
_R_ELBOW    = 14
_R_WRIST    = 16
_R_HIP      = 24
_R_KNEE     = 26
_R_ANKLE    = 28

# カメラ動き補正用: 体幹の代表関節 (左肩=11, 右肩=12, 左腰=23, 右腰=24)
_TORSO_REFS = [11, 12, 23, 24]

# 運動連鎖 (近位 → 遠位)
_CHAIN: List[Tuple[int, str]] = [
    (_R_ANKLE,    "Ankle"),
    (_R_KNEE,     "Knee "),
    (_R_HIP,      "Hip  "),
    (_R_SHOULDER, "Shldr"),
    (_R_ELBOW,    "Elbow"),
    (_R_WRIST,    "Wrist"),
]

_G = 9.81  # 重力加速度 m/s²


def _angle_3pts(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """b を頂点とする ∠abc を度で返す。"""
    ba = a - b
    bc = c - b
    cos_v = np.clip(
        np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-9),
        -1.0, 1.0
    )
    return float(np.degrees(np.arccos(cos_v)))


class AnalysisPass(VisualPassBase):
    """5 種統合コーチング解析パス。"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.fps: float = float(config.get("fps", 30.0))

        # 速度閾値 (m/s)
        self._delivery_thr: float = float(config.get("delivery_threshold_ms",  4.0))
        self._release_thr:  float = float(config.get("release_threshold_ms",  20.0))
        self._spike_cap:    float = float(config.get("speed_spike_cap_ms",    60.0))

        # 表示設定
        self._snap_dur: float = float(config.get("snapshot_duration",    3.0))   # s
        self._traj_dur: float = float(config.get("traj_duration",        2.0))   # s
        self._win:      int   =   int(config.get("chain_window_frames",  180))
        self._bar_h:    int   =   int(config.get("phasebar_height",       28))

        # 実行状態
        self._fc:        int   = 0
        self._phase:     int   = PHASE_APPROACH
        self._px2m:      Optional[float]       = None
        self._prev_pts:  Optional[np.ndarray]  = None
        self._hi_frames: int   = 0

        # 速度バッファ {joint_idx: deque[speed_ms]}  ← タイムライン履歴
        self._spd_hist: Dict[int, deque] = {
            idx: deque(maxlen=self._win) for idx, _ in _CHAIN
        }
        # 各関節の5フレーム rolling average バッファ (HUDと同等のスムージング)
        self._spd_smooth: Dict[int, deque] = {
            idx: deque([0.0] * 5, maxlen=5) for idx, _ in _CHAIN
        }
        # ピーク検出済みフレーム番号 {joint_idx: frame | None}
        self._peak_fc: Dict[int, Optional[int]] = {
            idx: None for idx, _ in _CHAIN
        }

        # フェーズ履歴 (最大 4000 フレーム ≈ 133 s @30fps)
        self._phase_hist: deque = deque(maxlen=4000)

        # 右手首速度スムージングバッファ (スパイク除去)
        self._wrist_spd_buf: deque = deque([0.0] * 5, maxlen=5)
        self._wrist_vx_buf:  deque = deque([0.0] * 3, maxlen=3)
        self._wrist_vy_buf:  deque = deque([0.0] * 3, maxlen=3)

        # リリース情報
        self._released:  bool            = False
        self._rel_fc:    int             = -1
        self._rel_spd:   float           = 0.0   # m/s
        self._rel_angle: float           = 0.0   # 度 (上方向が正)
        self._rel_pos:   Optional[Tuple[int, int]] = None
        self._rel_vx:    float           = 0.0   # px/s
        self._rel_vy:    float           = 0.0   # px/s

    # ─────────────────────────────────── apply ───────────────────────────────

    def apply(self, frame: np.ndarray, landmarks: AdaptedLandmarks) -> np.ndarray:
        if not self.enabled:
            return frame

        # px2m キャッシュ更新
        if landmarks.px2m < 0.5:
            self._px2m = landmarks.px2m
        px2m = self._px2m

        pts = landmarks.points  # (33, 3): x, y, vis

        # ── 速度計算 ──────────────────────────────────────────────────────────
        spd: Dict[int, float] = {idx: 0.0 for idx, _ in _CHAIN}
        wvx = wvy = 0.0

        if self._prev_pts is not None and px2m is not None:
            # カメラ動き推定: 体幹関節の中央変位 (パンニング補正)
            cam_dxs, cam_dys = [], []
            for ti in _TORSO_REFS:
                if self._prev_pts[ti, 2] > 0.3 and pts[ti, 2] > 0.3:
                    cam_dxs.append(float(pts[ti, 0] - self._prev_pts[ti, 0]))
                    cam_dys.append(float(pts[ti, 1] - self._prev_pts[ti, 1]))
            cam_dx = float(np.median(cam_dxs)) if cam_dxs else 0.0
            cam_dy = float(np.median(cam_dys)) if cam_dys else 0.0

            for idx, _ in _CHAIN:
                if self._prev_pts[idx, 2] > 0.3 and pts[idx, 2] > 0.3:
                    dx = (pts[idx, 0] - self._prev_pts[idx, 0]) - cam_dx
                    dy = (pts[idx, 1] - self._prev_pts[idx, 1]) - cam_dy
                    spd[idx] = min(
                        float(np.hypot(dx, dy)) * px2m * self.fps,
                        self._spike_cap
                    )
            if self._prev_pts[_R_WRIST, 2] > 0.3 and pts[_R_WRIST, 2] > 0.3:
                wvx = ((pts[_R_WRIST, 0] - self._prev_pts[_R_WRIST, 0]) - cam_dx) * self.fps
                wvy = ((pts[_R_WRIST, 1] - self._prev_pts[_R_WRIST, 1]) - cam_dy) * self.fps

        for idx, _ in _CHAIN:
            self._spd_hist[idx].append(spd[idx])
            self._spd_smooth[idx].append(spd[idx])

        # ── 速度スムージング (5フレーム移動平均でスパイク除去) ─────────────────
        self._wrist_spd_buf.append(spd[_R_WRIST])
        self._wrist_vx_buf.append(wvx)
        self._wrist_vy_buf.append(wvy)
        wrist_ms   = float(np.mean(self._wrist_spd_buf))
        wvx_smooth = float(np.mean(self._wrist_vx_buf))
        wvy_smooth = float(np.mean(self._wrist_vy_buf))

        # ── フェーズ更新 ──────────────────────────────────────────────────────
        self._update_phase(wrist_ms, px2m, wvx_smooth, wvy_smooth)
        self._phase_hist.append(self._phase)

        if self._phase in (PHASE_DELIVERY, PHASE_RELEASE):
            self._detect_peaks()

        # ── 描画 ──────────────────────────────────────────────────────────────
        result = frame.copy()
        result = self._draw_angle_arcs(result, pts)
        result = self._draw_chain_panel(result)
        if self._released:
            result = self._draw_traj_arc(result, px2m)
            result = self._draw_snapshot(result)
        result = self._draw_phase_bar(result)   # 最後に描画（最前面）

        self._prev_pts = pts.copy()
        self._fc += 1
        return result

    # ─────────────────────────────── フェーズ管理 ────────────────────────────

    def _update_phase(self, wrist_ms: float, px2m: Optional[float],
                      vx: float, vy: float) -> None:
        if self._released:
            self._phase = PHASE_FOLLOWTHROUGH
            return
        if px2m is None:
            return

        self._hi_frames = self._hi_frames + 1 if wrist_ms > self._release_thr else 0

        if self._hi_frames >= 2:
            self._released  = True
            self._rel_fc    = self._fc
            self._rel_spd   = wrist_ms   # スムージング済みm/s
            self._rel_vx    = vx
            self._rel_vy    = vy
            # 上方向が正（画像 y 軸は下が正なので符号反転）
            # vx/vyもスムージング済みなので角度も安定
            self._rel_angle = float(np.degrees(np.arctan2(-vy, vx)))
            if self._prev_pts is not None and self._prev_pts[_R_WRIST, 2] > 0.3:
                self._rel_pos = (
                    int(self._prev_pts[_R_WRIST, 0]),
                    int(self._prev_pts[_R_WRIST, 1]),
                )
            self._phase = PHASE_RELEASE
            return

        self._phase = PHASE_DELIVERY if wrist_ms > self._delivery_thr else PHASE_APPROACH

    def _detect_peaks(self) -> None:
        """各関節の速度ピーク（極大値）フレームを記録する。"""
        for idx, _ in _CHAIN:
            if self._peak_fc[idx] is not None:
                continue
            h = list(self._spd_hist[idx])
            if len(h) >= 3 and h[-2] > h[-3] and h[-2] > h[-1] and h[-2] > 1.0:
                self._peak_fc[idx] = self._fc - 1

    # ──────────────────────────── 1. 関節角度アーク ──────────────────────────

    def _draw_angle_arcs(self, frame: np.ndarray, pts: np.ndarray) -> np.ndarray:
        VIS = 0.4
        # (頂点, 辺A端点, 辺B端点, 色BGR)
        arc_defs: List[Tuple[int, int, int, Tuple]] = [
            (_R_ELBOW,    _R_SHOULDER, _R_WRIST, (100, 220, 255)),  # 肘 — シアン
            (_R_SHOULDER, _R_ELBOW,    _R_HIP,   (255, 170,  50)),  # 肩 — オレンジ
            (_R_HIP,      _R_SHOULDER, _R_KNEE,  (140, 255, 120)),  # 腰 — 黄緑
        ]
        for apex, ai, bi, color in arc_defs:
            if pts[apex, 2] < VIS or pts[ai, 2] < VIS or pts[bi, 2] < VIS:
                continue
            pa = pts[apex, :2].astype(float)
            aa = pts[ai,   :2].astype(float)
            ab = pts[bi,   :2].astype(float)

            angle = _angle_3pts(aa, pa, ab)
            r = 22

            va = aa - pa;  va /= np.linalg.norm(va) + 1e-9
            vb = ab - pa;  vb /= np.linalg.norm(vb) + 1e-9
            ang_a = float(np.degrees(np.arctan2(va[1], va[0])))
            ang_b = float(np.degrees(np.arctan2(vb[1], vb[0])))

            # 短い方向で弧を描く
            if (ang_b - ang_a + 360) % 360 > 180:
                ang_a, ang_b = ang_b, ang_a

            cv2.ellipse(frame, (int(pa[0]), int(pa[1])), (r, r),
                        0, ang_a, ang_b, color, 2, cv2.LINE_AA)

            # 角度テキスト（弧の中間方向に配置）
            mid = np.radians((ang_a + ang_b) / 2.0)
            tx = int(pa[0] + (r + 14) * np.cos(mid))
            ty = int(pa[1] + (r + 14) * np.sin(mid))
            cv2.putText(frame, f"{angle:.0f}",
                        (tx - 10, ty + 4), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, color, 1, cv2.LINE_AA)

        return frame

    # ──────────────────────────── 2. フェーズバー ─────────────────────────────

    def _draw_phase_bar(self, frame: np.ndarray) -> np.ndarray:
        fh, fw = frame.shape[:2]
        y0 = fh - self._bar_h

        # 半透明背景
        ov = frame.copy()
        cv2.rectangle(ov, (0, y0), (fw, fh), (15, 15, 15), -1)
        cv2.addWeighted(ov, 0.78, frame, 0.22, 0, dst=frame)
        cv2.line(frame, (0, y0), (fw, y0), (70, 70, 70), 1)

        # フェーズ履歴を帯に描画（n > fw ならダウンサンプル）
        ph_list = list(self._phase_hist)
        n = len(ph_list)
        if n > 1:
            step = max(1, n // fw)
            sampled = ph_list[::step]
            ns = len(sampled)
            for i, ph in enumerate(sampled):
                x1 = int(i * fw / ns)
                x2 = int((i + 1) * fw / ns)
                col = PHASE_COLORS[ph]
                if i == ns - 1:
                    col = tuple(min(255, c + 70) for c in col)
                cv2.rectangle(frame, (x1, y0 + 3), (x2, fh - 3), col, -1)

        # 現在フェーズ名（左）
        cv2.putText(frame, PHASE_NAMES[self._phase],
                    (8, y0 + self._bar_h - 7),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, PHASE_COLORS[self._phase],
                    1, cv2.LINE_AA)

        # リリース速度（右）
        if self._released and self._rel_spd > 0:
            txt = f"Release: {self._rel_spd * 3.6:.1f} km/h  @{self._rel_fc / self.fps:.2f}s"
            tw = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)[0][0]
            cv2.putText(frame, txt, (fw - tw - 8, y0 + self._bar_h - 7),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 255), 1, cv2.LINE_AA)

        return frame

    # ──────────────────── 3. リリーススナップショット ─────────────────────────

    def _draw_snapshot(self, frame: np.ndarray) -> np.ndarray:
        elapsed = (self._fc - self._rel_fc) / self.fps
        if elapsed > self._snap_dur:
            return frame

        alpha = max(0.0, 1.0 - elapsed / self._snap_dur)
        fh, fw = frame.shape[:2]
        pw, php = 270, 132
        px_p = (fw - pw) // 2
        py_p = fh // 4

        ov = frame.copy()
        cv2.rectangle(ov, (px_p, py_p), (px_p + pw, py_p + php), (10, 10, 10), -1)
        cv2.rectangle(ov, (px_p, py_p), (px_p + pw, py_p + php), (50, 50, 230), 2)
        cv2.addWeighted(ov, alpha * 0.88, frame, 1.0 - alpha * 0.88, 0, dst=frame)

        lines: List[Tuple[str, Tuple, float, int]] = [
            ("RELEASE!",
             (60, 60, 245), 0.75, 2),
            (f"Speed:  {self._rel_spd * 3.6:.1f} km/h",
             (240, 240, 240), 0.52, 1),
            (f"Angle:  {self._rel_angle:.1f}°",
             (200, 200, 200), 0.45, 1),
            (f"Time:   {self._rel_fc / self.fps:.2f} s",
             (170, 170, 170), 0.45, 1),
        ]
        yc = py_p + 30
        for txt, col, sc, th in lines:
            c = tuple(min(255, int(v * alpha + 10)) for v in col)
            cv2.putText(frame, txt, (px_p + 14, yc),
                        cv2.FONT_HERSHEY_SIMPLEX, sc, c, th, cv2.LINE_AA)
            yc += int(sc * 44 + 4)

        return frame

    # ──────────────────────────── 4. 軌道予測アーク ──────────────────────────

    def _draw_traj_arc(self, frame: np.ndarray,
                       px2m: Optional[float]) -> np.ndarray:
        if self._rel_pos is None or px2m is None:
            return frame

        fh, fw = frame.shape[:2]
        x0, y0_px = self._rel_pos
        vx, vy = self._rel_vx, self._rel_vy
        g_px = _G / px2m          # px/s²（下が正）

        steps = 80
        dt = self._traj_dur / steps
        traj: List[Tuple[int, int]] = []
        for i in range(steps + 1):
            t = i * dt
            xi = int(x0 + vx * t)
            yi = int(y0_px + vy * t + 0.5 * g_px * t * t)
            if xi < -300 or xi > fw + 300 or yi < -300 or yi > fh + 500:
                break
            traj.append((xi, yi))

        n = len(traj)
        for i in range(0, n - 1, 2):
            a = max(0.15, 1.0 - i / max(n, 1))
            cv2.line(frame, traj[i], traj[i + 1],
                     (int(60 * a), int(200 * a), int(255 * a)), 2, cv2.LINE_AA)
        if n >= 2:
            cv2.arrowedLine(frame, traj[-2], traj[-1],
                            (40, 110, 200), 2, cv2.LINE_AA, tipLength=0.4)

        return frame

    # ──────────────────── 5. 運動連鎖タイムライン ─────────────────────────────

    def _draw_chain_panel(self, frame: np.ndarray) -> np.ndarray:
        fh, fw = frame.shape[:2]
        n_j     = len(_CHAIN)
        row_h   = 20
        lbl_w   = 28
        bar_w   = 120
        val_w   = 36
        pad     = 6
        title_h = 18
        pw  = pad + lbl_w + bar_w + val_w + pad
        php = title_h + n_j * row_h + pad

        px_p = fw - pw - 6
        py_p = 6

        ov = frame.copy()
        cv2.rectangle(ov, (px_p, py_p), (px_p + pw, py_p + php), (10, 10, 10), -1)
        cv2.rectangle(ov, (px_p, py_p), (px_p + pw, py_p + php), (75, 75, 75), 1)
        cv2.addWeighted(ov, 0.72, frame, 0.28, 0, dst=frame)

        is_calibrated = self._px2m is not None

        cv2.putText(frame, "Kinetic Chain",
                    (px_p + pad, py_p + 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (170, 170, 170), 1, cv2.LINE_AA)
        # キャリブレーション状態をタイトル右側に表示
        cal_label = "CAL" if is_calibrated else "---"
        cal_color = (80, 200, 80) if is_calibrated else (80, 80, 200)
        cv2.putText(frame, cal_label,
                    (px_p + pw - 30, py_p + 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, cal_color, 1, cv2.LINE_AA)
        cv2.putText(frame, "km/h",
                    (px_p + pad + lbl_w + bar_w + 3, py_p + 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, (110, 110, 110), 1, cv2.LINE_AA)

        bar_x0 = px_p + pad + lbl_w

        # 全関節の速度最大値でスケーリング（現在フレームのみでなく履歴全体）
        hist_max = 1.0
        for idx, _ in _CHAIN:
            hh = list(self._spd_hist[idx])
            if hh:
                hist_max = max(hist_max, max(hh))

        for row, (idx, lbl) in enumerate(_CHAIN):
            ry = py_p + title_h + row * row_h

            # ラベル
            cv2.putText(frame, lbl,
                        (px_p + pad, ry + row_h - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (155, 155, 155), 1, cv2.LINE_AA)

            hh = list(self._spd_hist[idx])
            # 5フレーム rolling average (HUDと同等のスムージング)
            cur = float(np.mean(self._spd_smooth[idx]))
            blen = int(bar_w * min(cur / hist_max, 1.0))

            # 近位(青)→遠位(オレンジ) グラデーション
            t = row / max(n_j - 1, 1)
            rc = int( 60 + 195 * t)
            gc = int(180 - 120 * t)
            bc = int(255 - 175 * t)

            # バー背景
            cv2.rectangle(frame,
                          (bar_x0, ry + 3), (bar_x0 + bar_w, ry + row_h - 3),
                          (35, 35, 35), -1)
            # バー本体
            if blen > 0:
                cv2.rectangle(frame,
                              (bar_x0, ry + 3), (bar_x0 + blen, ry + row_h - 3),
                              (bc, gc, rc), -1)

            # ピークマーカー (◆ 黄色)
            pk = self._peak_fc[idx]
            if pk is not None and hh:
                hist_start = self._fc - len(hh)
                if pk >= hist_start:
                    rel = (pk - hist_start) / max(len(hh) - 1, 1)
                    pkx = bar_x0 + int(bar_w * min(rel, 1.0))
                    pky = ry + row_h // 2
                    diam = np.array([
                        [pkx,     pky - 4],
                        [pkx + 4, pky    ],
                        [pkx,     pky + 4],
                        [pkx - 4, pky    ],
                    ], np.int32)
                    cv2.fillPoly(frame, [diam], (40, 220, 255))

            # 現在速度数値 (km/h 表示、キャリブレーション済みのみ)
            val_text = f"{cur * 3.6:.0f}" if is_calibrated else " --"
            cv2.putText(frame, val_text,
                        (bar_x0 + bar_w + 3, ry + row_h - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (140, 140, 140), 1, cv2.LINE_AA)

        return frame
