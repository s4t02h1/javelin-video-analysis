"""
src/graph_generator.py — Javelin Video Analysis グラフ自動生成モジュール

pose_landmarks.csv を読み込み、解析グラフ画像を生成する。
生成画像は report/graphs/ に保存され、PDF レポート・Instagram 素材などに使える。

使用例:
    from src.graph_generator import generate_graphs_for_job
    from pathlib import Path
    graph_paths = generate_graphs_for_job(Path("jobs/20260508_070156_518a"))
"""

import logging
from pathlib import Path
from typing import List

import matplotlib
matplotlib.use("Agg")   # GUI不要・Windows対応
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd

logger = logging.getLogger(__name__)

# ── 共通スタイル設定 ─────────────────────────────────────────────────────────
_FIG_DPI   = 150
_FIG_W     = 8.0   # inch (A4 横幅に合わせた余裕サイズ)
_FIG_H     = 4.5
_STYLE     = "seaborn-v0_8-whitegrid"


def _load_csv(csv_path: Path) -> "pd.DataFrame | None":
    """CSV を読み込んで DataFrame を返す。失敗時は None を返し警告を出す。"""
    if not csv_path.exists():
        logger.warning(f"[graph_generator] CSV が見つかりません: {csv_path}")
        return None
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
        return df
    except Exception as exc:
        logger.warning(f"[graph_generator] CSV 読み込み失敗: {csv_path} — {exc}")
        return None


def _require_cols(df: pd.DataFrame, cols: List[str], graph_name: str) -> bool:
    """必要な列が全て揃っているか確認。不足時に警告を出して False を返す。"""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        logger.warning(
            f"[graph_generator] {graph_name} のスキップ: "
            f"列 {missing} が CSV に存在しません"
        )
        return False
    return True


# ── グラフ A: 右手首の高さ変化 ──────────────────────────────────────────────
def _graph_right_wrist_height(df: pd.DataFrame, out_dir: Path) -> "Path | None":
    """right_wrist_height.png を生成して Path を返す。失敗時は None。"""
    cols = ["time_sec", "right_wrist_y"]
    if not _require_cols(df, cols, "right_wrist_height"):
        return None
    try:
        out_path = out_dir / "right_wrist_height.png"
        # y 座標は MediaPipe では上=0、下=1 なので反転
        sub = df[df["right_wrist_y"].notna()].copy()
        height_val = 1.0 - sub["right_wrist_y"]

        with plt.style.context(_STYLE):
            fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H), dpi=_FIG_DPI)
            ax.plot(sub["time_sec"], height_val, color="#2563eb", linewidth=1.5)
            ax.set_title("Right Wrist Height Over Time", fontsize=14, fontweight="bold", pad=12)
            ax.set_xlabel("Time (sec)", fontsize=11)
            ax.set_ylabel("Height (normalized, up=high)", fontsize=11)
            ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.2f"))
            ax.set_ylim(0, 1)
            fig.tight_layout()
            fig.savefig(out_path, dpi=_FIG_DPI, bbox_inches="tight")
            plt.close(fig)

        logger.info(f"[graph_generator] Saved: {out_path}")
        return out_path
    except Exception as exc:
        logger.warning(f"[graph_generator] right_wrist_height 生成失敗: {exc}")
        return None


# ── グラフ B: 右肩・右肘・右手首の2D軌跡 ────────────────────────────────────
def _graph_right_arm_trajectory(df: pd.DataFrame, out_dir: Path) -> "Path | None":
    """right_arm_trajectory.png を生成して Path を返す。失敗時は None。"""
    cols = [
        "right_shoulder_x", "right_shoulder_y",
        "right_elbow_x",    "right_elbow_y",
        "right_wrist_x",    "right_wrist_y",
    ]
    if not _require_cols(df, cols, "right_arm_trajectory"):
        return None
    try:
        out_path = out_dir / "right_arm_trajectory.png"
        # 有効フレームのみ (visibility > 0.3 を想定: 列があれば使う)
        mask = pd.Series([True] * len(df), index=df.index)
        for col in cols:
            mask &= df[col].notna()
        sub = df[mask].copy()

        # y を反転（MediaPipe: 上=0→表示上も上）
        sh_x, sh_y = sub["right_shoulder_x"], 1 - sub["right_shoulder_y"]
        el_x, el_y = sub["right_elbow_x"],    1 - sub["right_elbow_y"]
        wr_x, wr_y = sub["right_wrist_x"],    1 - sub["right_wrist_y"]

        with plt.style.context(_STYLE):
            fig, ax = plt.subplots(figsize=(_FIG_H, _FIG_H), dpi=_FIG_DPI)  # 正方形

            n = len(sub)
            # 時間に沿って色変化（薄→濃）
            cmap = plt.get_cmap("Blues")
            for i in range(n - 1):
                alpha = 0.3 + 0.7 * i / max(n - 1, 1)
                ax.plot(sh_x.iloc[i:i+2], sh_y.iloc[i:i+2], color=cmap(0.4 + 0.5 * i / max(n-1,1)), alpha=alpha, linewidth=1.2)
                ax.plot(el_x.iloc[i:i+2], el_y.iloc[i:i+2], color=plt.get_cmap("Oranges")(0.4 + 0.5 * i / max(n-1,1)), alpha=alpha, linewidth=1.2)
                ax.plot(wr_x.iloc[i:i+2], wr_y.iloc[i:i+2], color=plt.get_cmap("Greens")(0.4 + 0.5 * i / max(n-1,1)), alpha=alpha, linewidth=1.2)

            # 凡例用ダミー
            ax.plot([], [], color="#2563eb", label="Shoulder")
            ax.plot([], [], color="#ea580c", label="Elbow")
            ax.plot([], [], color="#16a34a", label="Wrist")

            # スタート/エンドマーカー
            ax.scatter([sh_x.iloc[0], el_x.iloc[0], wr_x.iloc[0]],
                       [sh_y.iloc[0], el_y.iloc[0], wr_y.iloc[0]],
                       color="gray", s=30, zorder=5, label="Start")
            ax.scatter([sh_x.iloc[-1], el_x.iloc[-1], wr_x.iloc[-1]],
                       [sh_y.iloc[-1], el_y.iloc[-1], wr_y.iloc[-1]],
                       color="red", s=30, zorder=5, label="End")

            ax.set_title("Right Arm 2D Trajectory", fontsize=14, fontweight="bold", pad=12)
            ax.set_xlabel("X (normalized, right=1)", fontsize=10)
            ax.set_ylabel("Y (normalized, up=1)", fontsize=10)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_aspect("equal", adjustable="box")
            ax.legend(fontsize=8, loc="upper left")
            fig.tight_layout()
            fig.savefig(out_path, dpi=_FIG_DPI, bbox_inches="tight")
            plt.close(fig)

        logger.info(f"[graph_generator] Saved: {out_path}")
        return out_path
    except Exception as exc:
        logger.warning(f"[graph_generator] right_arm_trajectory 生成失敗: {exc}")
        return None


# ── グラフ C: 肩中心・腰中心の移動軌跡 ─────────────────────────────────────
def _graph_torso_center_trajectory(df: pd.DataFrame, out_dir: Path) -> "Path | None":
    """torso_center_trajectory.png を生成して Path を返す。失敗時は None。"""
    cols = [
        "left_shoulder_x",  "left_shoulder_y",
        "right_shoulder_x", "right_shoulder_y",
        "left_hip_x",       "left_hip_y",
        "right_hip_x",      "right_hip_y",
    ]
    if not _require_cols(df, cols, "torso_center_trajectory"):
        return None
    try:
        out_path = out_dir / "torso_center_trajectory.png"
        mask = pd.Series([True] * len(df), index=df.index)
        for col in cols:
            mask &= df[col].notna()
        sub = df[mask].copy()

        sc_x = (sub["left_shoulder_x"] + sub["right_shoulder_x"]) / 2
        sc_y = 1 - (sub["left_shoulder_y"] + sub["right_shoulder_y"]) / 2
        hc_x = (sub["left_hip_x"] + sub["right_hip_x"]) / 2
        hc_y = 1 - (sub["left_hip_y"] + sub["right_hip_y"]) / 2
        t    = sub["time_sec"] if "time_sec" in sub.columns else pd.RangeIndex(len(sub))

        with plt.style.context(_STYLE):
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(_FIG_W, _FIG_H), dpi=_FIG_DPI)

            # 左: 時系列で x 変化
            ax1.plot(t, sc_x, color="#7c3aed", linewidth=1.5, label="Shoulder center X")
            ax1.plot(t, hc_x, color="#b45309", linewidth=1.5, linestyle="--", label="Hip center X")
            ax1.set_title("Torso Center X (horizontal)", fontsize=11, fontweight="bold")
            ax1.set_xlabel("Time (sec)", fontsize=10)
            ax1.set_ylabel("X (normalized)", fontsize=10)
            ax1.legend(fontsize=8)

            # 右: 2D 軌跡
            n = len(sub)
            cmap_s = plt.get_cmap("Purples")
            cmap_h = plt.get_cmap("Oranges")
            for i in range(n - 1):
                frac = 0.3 + 0.7 * i / max(n - 1, 1)
                ax2.plot(sc_x.iloc[i:i+2], sc_y.iloc[i:i+2], color=cmap_s(frac), linewidth=1.2)
                ax2.plot(hc_x.iloc[i:i+2], hc_y.iloc[i:i+2], color=cmap_h(frac), linewidth=1.2)

            ax2.plot([], [], color="#7c3aed", label="Shoulder center")
            ax2.plot([], [], color="#b45309", label="Hip center")
            ax2.scatter([sc_x.iloc[-1], hc_x.iloc[-1]],
                        [sc_y.iloc[-1], hc_y.iloc[-1]],
                        color="red", s=30, zorder=5)
            ax2.set_title("Torso Center 2D Trajectory", fontsize=11, fontweight="bold")
            ax2.set_xlabel("X (normalized)", fontsize=10)
            ax2.set_ylabel("Y (normalized, up=1)", fontsize=10)
            ax2.set_xlim(0, 1)
            ax2.set_ylim(0, 1)
            ax2.set_aspect("equal", adjustable="box")
            ax2.legend(fontsize=8, loc="upper left")

            fig.suptitle("Shoulder and Hip Center Trajectory", fontsize=14, fontweight="bold", y=1.02)
            fig.tight_layout()
            fig.savefig(out_path, dpi=_FIG_DPI, bbox_inches="tight")
            plt.close(fig)

        logger.info(f"[graph_generator] Saved: {out_path}")
        return out_path
    except Exception as exc:
        logger.warning(f"[graph_generator] torso_center_trajectory 生成失敗: {exc}")
        return None


# ── パブリック API ────────────────────────────────────────────────────────────
def generate_graphs_for_job(job_dir: Path) -> List[Path]:
    """
    ジョブディレクトリの CSV からグラフ画像を生成し、report/graphs/ に保存する。

    Args:
        job_dir: ジョブのルートディレクトリ（例: jobs/20260508_070156_518a）

    Returns:
        生成できたグラフ画像の Path リスト。1 枚も生成できなかった場合は空リスト。
    """
    job_dir = Path(job_dir)

    # CSV 検索: report/ > output/ > job_dir/
    csv_path: "Path | None" = None
    for candidate in [
        job_dir / "report" / "pose_landmarks.csv",
        job_dir / "output" / "pose_landmarks.csv",
        job_dir / "pose_landmarks.csv",
    ]:
        if candidate.exists():
            csv_path = candidate
            break

    if csv_path is None:
        logger.warning(f"[graph_generator] pose_landmarks.csv が見つかりません: {job_dir}")
        return []

    df = _load_csv(csv_path)
    if df is None or df.empty:
        return []

    # 出力ディレクトリ
    out_dir = job_dir / "report" / "graphs"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning(f"[graph_generator] graphs ディレクトリ作成失敗: {exc}")
        return []

    generated: List[Path] = []
    for fn in (
        _graph_right_wrist_height,
        _graph_right_arm_trajectory,
        _graph_torso_center_trajectory,
    ):
        result = fn(df, out_dir)
        if result is not None:
            generated.append(result)

    logger.info(f"[graph_generator] {len(generated)}/3 グラフ生成完了: {out_dir}")
    return generated
