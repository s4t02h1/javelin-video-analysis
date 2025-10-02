"""
OpenCV DNN ベースのポーズ推定実装
MediaPipeの代替として軽量なポーズ検出を提供
"""

import cv2
import numpy as np
import os
from typing import List, Tuple, Optional, Dict


class OpenCVPoseEstimator:
    """OpenCV DNN を使用したポーズ推定"""
    
    def __init__(self):
        self.available = False
        self.net = None
        self.input_width = 368
        self.input_height = 368
        self.threshold = 0.1
        
        # COCO ポーズモデルのキーポイント定義
        self.pose_pairs = [
            [1, 2], [1, 5], [2, 3], [3, 4], [5, 6], [6, 7],
            [1, 8], [8, 9], [9, 10], [1, 11], [11, 12], [12, 13],
            [1, 0], [0, 14], [14, 16], [0, 15], [15, 17],
            [2, 16], [5, 17]
        ]
        
        # MediaPipeスタイルのランドマーク定義（COCO->MediaPipeマッピング）
        self.coco_to_mediapipe = {
            0: 0,   # nose -> nose
            1: 11,  # neck -> left_shoulder (近似)
            2: 13,  # right_shoulder -> left_elbow (近似)
            3: 15,  # right_elbow -> left_wrist (近似)
            4: 16,  # right_wrist -> right_wrist
            5: 12,  # left_shoulder -> right_shoulder (近似)
            6: 14,  # left_elbow -> right_elbow (近似)
            7: 16,  # left_wrist -> right_wrist (近似)
            8: 24,  # right_hip -> right_hip (近似)
            9: 26,  # right_knee -> right_knee (近似)
            10: 28, # right_ankle -> right_ankle (近似)
            11: 23, # left_hip -> left_hip (近似)
            12: 25, # left_knee -> left_knee (近似)
            13: 27, # left_ankle -> left_ankle (近似)
            14: None, # right_eye (スキップ)
            15: None, # left_eye (スキップ)
            16: None, # right_ear (スキップ)
            17: None, # left_ear (スキップ)
        }
        
        self._try_load_model()
    
    def _try_load_model(self):
        """OpenPoseモデルの読み込みを試行"""
        # COCOモデルのパス（一般的な配置場所）
        model_paths = [
            "models/pose_coco.prototxt",
            "models/pose_coco.caffemodel",
            "../models/pose_coco.prototxt", 
            "../models/pose_coco.caffemodel"
        ]
        
        try:
            # 簡略化: ファイルが存在しない場合はスキップ
            prototxt_path = "models/pose_coco.prototxt"
            caffemodel_path = "models/pose_coco.caffemodel"
            
            if os.path.exists(prototxt_path) and os.path.exists(caffemodel_path):
                self.net = cv2.dnn.readNetFromCaffe(prototxt_path, caffemodel_path)
                self.available = True
                print("OpenCV DNN pose model loaded successfully")
            else:
                print("OpenCV DNN pose model files not found - using fallback")
                self.available = False
        except Exception as e:
            print(f"Failed to load OpenCV DNN model: {e}")
            self.available = False
    
    def detect_pose(self, image) -> List[Tuple[int, int, float]]:
        """ポーズ検出を実行"""
        if not self.available:
            return []
        
        try:
            # 前処理
            blob = cv2.dnn.blobFromImage(
                image, 1.0/255, (self.input_width, self.input_height), 
                (0, 0, 0), swapRB=False, crop=False
            )
            
            self.net.setInput(blob)
            output = self.net.forward()
            
            # 後処理
            points = []
            h, w = image.shape[:2]
            
            for i in range(18):  # COCO 18キーポイント
                prob_map = output[0, i, :, :]
                min_val, prob, min_loc, point = cv2.minMaxLoc(prob_map)
                
                x = int((w * point[0]) / output.shape[3])
                y = int((h * point[1]) / output.shape[2])
                
                if prob > self.threshold:
                    points.append((x, y, prob))
                else:
                    points.append((0, 0, 0.0))
            
            return points
        except Exception as e:
            print(f"Pose detection error: {e}")
            return []
    
    def convert_to_mediapipe_format(self, coco_points, image_shape):
        """COCOフォーマットをMediaPipe風に変換"""
        h, w = image_shape[:2]
        mediapipe_points = [None] * 33
        
        for coco_idx, mp_idx in self.coco_to_mediapipe.items():
            if mp_idx is not None and coco_idx < len(coco_points):
                x, y, conf = coco_points[coco_idx]
                if conf > 0.1:
                    # 正規化座標に変換
                    mediapipe_points[mp_idx] = (int(x), int(y))
        
        return mediapipe_points


# グローバルインスタンス
opencv_pose_estimator = OpenCVPoseEstimator()