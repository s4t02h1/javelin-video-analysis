import cv2
import numpy as np
import mediapipe as mp

class PoseVisualizer:
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles

    def visualize_pose(self, frame):
        """
        フレームに骨格点を描画する
        """
        # BGRからRGBに変換
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # ポーズ検出
        results = self.pose.process(rgb_frame)
        
        # 描画用のフレームをコピー
        annotated_frame = frame.copy()
        
        if results.pose_landmarks:
            # 骨格点と接続線を描画
            self.mp_drawing.draw_landmarks(
                annotated_frame,
                results.pose_landmarks,
                self.mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=self.mp_drawing_styles.get_default_pose_landmarks_style()
            )
            
            # やり投げに重要な点を強調表示
            self.highlight_key_points(annotated_frame, results.pose_landmarks)
        
        return annotated_frame
    
    def highlight_key_points(self, frame, landmarks):
        """
        やり投げに重要な骨格点を強調表示
        """
        height, width = frame.shape[:2]
        
        # 重要な点のインデックス（MediaPose基準）
        key_points = {
            'LEFT_SHOULDER': 11,
            'RIGHT_SHOULDER': 12,
            'LEFT_ELBOW': 13,
            'RIGHT_ELBOW': 14,
            'LEFT_WRIST': 15,
            'RIGHT_WRIST': 16,
            'LEFT_HIP': 23,
            'RIGHT_HIP': 24,
            'LEFT_KNEE': 25,
            'RIGHT_KNEE': 26,
            'LEFT_ANKLE': 27,
            'RIGHT_ANKLE': 28
        }
        
        for name, idx in key_points.items():
            if idx < len(landmarks.landmark):
                landmark = landmarks.landmark[idx]
                x = int(landmark.x * width)
                y = int(landmark.y * height)
                
                # 重要な点を大きな円で強調
                cv2.circle(frame, (x, y), 8, (0, 255, 255), -1)  # 黄色の円
                cv2.circle(frame, (x, y), 10, (0, 0, 255), 2)    # 赤い枠
    
    def release(self):
        """
        リソースを解放
        """
        self.pose.close()