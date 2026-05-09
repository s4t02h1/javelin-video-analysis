"""
src/data_exporter.py — Javelin Video Analysis データエクスポートユーティリティ

フレームごとの姿勢推定ランドマーク情報を CSV として出力する。

使用例:
    from src.data_exporter import export_pose_landmarks_csv
    csv_path = export_pose_landmarks_csv(landmarks_rows, output_path, fps=30.0)
"""

import csv
import logging
from pathlib import Path
from typing import List, Optional, Union

logger = logging.getLogger(__name__)

# ── 対象ランドマーク定義（MediaPipe Pose index） ──────────────────────────────
LANDMARK_TARGETS = [
    ("nose",            0),
    ("left_shoulder",  11),
    ("right_shoulder", 12),
    ("left_elbow",     13),
    ("right_elbow",    14),
    ("left_wrist",     15),
    ("right_wrist",    16),
    ("left_hip",       23),
    ("right_hip",      24),
    ("left_knee",      25),
    ("right_knee",     26),
    ("left_ankle",     27),
    ("right_ankle",    28),
]

# CSV ヘッダー
_HEADER = ["frame", "time_sec"]
for _name, _ in LANDMARK_TARGETS:
    for _col in ("x", "y", "z", "visibility"):
        _HEADER.append(f"{_name}_{_col}")


def export_pose_landmarks_csv(
    landmarks_rows: List[dict],
    output_path: Union[str, Path],
) -> Path:
    """姿勢ランドマークデータをCSVに書き出す。

    Args:
        landmarks_rows: フレームごとのランドマーク情報リスト。各要素は以下の形式：
            {
                "frame": int,                         # フレーム番号 (1-based)
                "time_sec": float | None,             # 経過秒数
                "raw_landmarks": list | None,         # MediaPipe生データ (33要素)
                    # 各要素: {"x": float, "y": float, "z": float, "visibility": float}
                    #         または None (検出なし)
            }
        output_path: 出力CSVのパス。

    Returns:
        書き出したCSVのPathオブジェクト。

    Raises:
        OSError: ファイル書き込みに失敗した場合。
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_HEADER)

        for row in landmarks_rows:
            frame    = row.get("frame", "")
            time_sec = row.get("time_sec")
            time_str = f"{time_sec:.4f}" if time_sec is not None else ""
            raw      = row.get("raw_landmarks")  # list of 33 dicts or None

            line = [frame, time_str]
            for name, idx in LANDMARK_TARGETS:
                lm = None
                if raw and idx < len(raw):
                    lm = raw[idx]
                if lm is not None:
                    line.extend([
                        f"{lm['x']:.6f}",
                        f"{lm['y']:.6f}",
                        f"{lm.get('z', ''):.6f}" if lm.get('z') is not None else "",
                        f"{lm.get('visibility', ''):.4f}" if lm.get('visibility') is not None else "",
                    ])
                else:
                    line.extend(["", "", "", ""])
            writer.writerow(line)

    logger.info(f"Pose landmarks CSV saved: {out} ({len(landmarks_rows)} frames)")
    return out
