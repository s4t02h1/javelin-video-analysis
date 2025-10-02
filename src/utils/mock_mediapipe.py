"""
モックMediaPipeモジュール - MediaPipeが利用できない環境向け

このモジュールはMediaPipeが利用できない場合に基本的な機能を提供します。
実際のポーズ検出は行いませんが、ダミーの骨格点を生成してアプリケーションの動作確認をサポートします。
"""

import numpy as np
from typing import NamedTuple, Optional, List


class Landmark:
    """MediaPipe Landmarkのモック"""
    def __init__(self, x=0.0, y=0.0, z=0.0, visibility=0.0):
        self.x = x
        self.y = y  
        self.z = z
        self.visibility = visibility


class PoseLandmarks:
    """MediaPipe PoseLandmarksのモック"""
    def __init__(self):
        # 33個のランドマークを初期化
        self.landmark = [Landmark() for _ in range(33)]


class PoseResults:
    """MediaPipe Pose結果のモック"""
    def __init__(self):
        self.pose_landmarks = None


class MockPose:
    """MediaPipe Poseクラスのモック"""
    def __init__(self, **kwargs):
        print("WARNING: Using mock MediaPipe - generating dummy pose landmarks")
        self.frame_count = 0
        pass
    
    def process(self, image):
        """モック処理 - ダミーの骨格点を生成"""
        self.frame_count += 1
        result = PoseResults()
        
        # ダミーの人体ポーズを生成（33個のランドマーク）
        result.pose_landmarks = self._generate_dummy_pose(image.shape, self.frame_count)
        
        return result
    
    def _generate_dummy_pose(self, image_shape, frame_num):
        """ダミーの人体ポーズを生成"""
        h, w = image_shape[:2]
        landmarks = PoseLandmarks()
        
        # 画面中央を基準にした人体のダミーポーズ
        center_x = 0.5
        center_y = 0.5
        
        # 時間による動きを追加（投げ動作をシミュレート）
        t = frame_num * 0.1
        arm_swing = 0.1 * np.sin(t)
        
        # MediaPipeの33個のランドマーク位置を設定
        # 0-10: 顔・頭部
        for i in range(11):
            landmarks.landmark[i] = Landmark(
                x=center_x + 0.05 * np.sin(i * 0.5),
                y=center_y - 0.2 + 0.02 * i,
                z=0.0,
                visibility=0.9
            )
        
        # 11-22: 上半身
        # 11: 左肩, 12: 右肩
        landmarks.landmark[11] = Landmark(x=center_x - 0.15, y=center_y - 0.1, z=0.0, visibility=0.95)
        landmarks.landmark[12] = Landmark(x=center_x + 0.15, y=center_y - 0.1, z=0.0, visibility=0.95)
        
        # 13: 左肘, 14: 右肘
        landmarks.landmark[13] = Landmark(x=center_x - 0.2, y=center_y + 0.1, z=0.0, visibility=0.9)
        landmarks.landmark[14] = Landmark(x=center_x + 0.25 + arm_swing, y=center_y + 0.1, z=0.0, visibility=0.9)
        
        # 15: 左手首, 16: 右手首（投げ手）
        landmarks.landmark[15] = Landmark(x=center_x - 0.25, y=center_y + 0.2, z=0.0, visibility=0.9)
        landmarks.landmark[16] = Landmark(x=center_x + 0.35 + arm_swing * 2, y=center_y + 0.05, z=0.0, visibility=0.95)
        
        # 17-22: 手のひら（簡略化）
        for i in range(17, 23):
            landmarks.landmark[i] = Landmark(
                x=center_x + 0.4 + arm_swing * 2,
                y=center_y + 0.05 + (i-17) * 0.01,
                z=0.0,
                visibility=0.8
            )
        
        # 23-32: 下半身
        # 23: 左腰, 24: 右腰
        landmarks.landmark[23] = Landmark(x=center_x - 0.1, y=center_y + 0.3, z=0.0, visibility=0.9)
        landmarks.landmark[24] = Landmark(x=center_x + 0.1, y=center_y + 0.3, z=0.0, visibility=0.9)
        
        # 25: 左膝, 26: 右膝
        landmarks.landmark[25] = Landmark(x=center_x - 0.08, y=center_y + 0.5, z=0.0, visibility=0.9)
        landmarks.landmark[26] = Landmark(x=center_x + 0.08, y=center_y + 0.5, z=0.0, visibility=0.9)
        
        # 27: 左足首, 28: 右足首
        landmarks.landmark[27] = Landmark(x=center_x - 0.06, y=center_y + 0.7, z=0.0, visibility=0.9)
        landmarks.landmark[28] = Landmark(x=center_x + 0.06, y=center_y + 0.7, z=0.0, visibility=0.9)
        
        # 29-32: 足先
        for i in range(29, 33):
            side = -1 if i % 2 == 1 else 1
            landmarks.landmark[i] = Landmark(
                x=center_x + side * 0.08,
                y=center_y + 0.72 + (i-29) * 0.01,
                z=0.0,
                visibility=0.8
            )
        
        return landmarks
    
    def close(self):
        pass


class MockSolutions:
    """MediaPipe solutionsのモック"""
    class pose:
        Pose = MockPose
        # MediaPipeの標準的な骨格接続を定義
        POSE_CONNECTIONS = [
            # 顔の接続
            (0, 1), (1, 2), (2, 3), (3, 7),
            (0, 4), (4, 5), (5, 6), (6, 8),
            (9, 10),
            # 上半身の接続
            (11, 12),  # 肩
            (11, 13), (13, 15),  # 左腕
            (12, 14), (14, 16),  # 右腕
            (11, 23), (12, 24),  # 肩から腰
            (23, 24),  # 腰
            # 下半身の接続
            (23, 25), (25, 27),  # 左脚
            (24, 26), (26, 28),  # 右脚
            (27, 29), (27, 31),  # 左足
            (28, 30), (28, 32),  # 右足
            # 手のひらの接続（簡略化）
            (15, 17), (16, 18),
            (17, 19), (18, 20),
            (19, 21), (20, 22)
        ]


# MediaPipeモジュール構造をモック
class MockMediaPipe:
    solutions = MockSolutions()


# グローバルなモックオブジェクト
mp = MockMediaPipe()