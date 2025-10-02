from __future__ import annotations
import argparse
from dataclasses import dataclass
from typing import Any, Dict, Optional

# 既存のPoseAnalyzerを流用するための型整合だけ行う
try:
    import mediapipe as mp
except Exception:
    mp = None  # type: ignore


@dataclass
class PoseBackend:
    use_tasks: bool = False

    def add_backend_flags(self, ap: argparse.ArgumentParser) -> None:
        ap.add_argument("--use-tasks", action="store_true", help="MediaPipe Tasksを使用（既定はSolutions）")

    def init(self, fps: float) -> Any:
        if self.use_tasks and mp is not None:
            # ここでは遅延実装: Tasksが未導入でもフラグ許容
            return self._init_tasks(fps)
        return self._init_solutions()

    def _init_solutions(self):
        # 既存のsrc.pipelines.pose_analysis.PoseAnalyzer側が内部でmp.solutions.poseを利用
        return None

    def _init_tasks(self, fps: float):
        # 将来の実装ポイント（mediapipe-tasks-python）
        # ひとまずダミーオブジェクトを返し、呼び出し側の切替起点のみ提供
        return {"backend": "tasks", "fps": fps}

