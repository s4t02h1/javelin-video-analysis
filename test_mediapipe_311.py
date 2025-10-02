#!/usr/bin/env python3
"""
Python 3.11でMediaPipeの動作テスト
"""

import sys
print(f"Python version: {sys.version}")

try:
    import mediapipe as mp
    import cv2
    import numpy as np
    print(f"✅ MediaPipe version: {mp.__version__}")
    print(f"✅ OpenCV version: {cv2.__version__}")
    print(f"✅ NumPy version: {np.__version__}")
    
    # MediaPipe Poseの初期化テスト
    mp_pose = mp.solutions.pose
    mp_drawing = mp.solutions.drawing_utils
    
    with mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as pose:
        print("✅ MediaPipe Pose initialized successfully!")
        
        # ダミー画像でテスト
        dummy_image = np.zeros((480, 640, 3), dtype=np.uint8)
        results = pose.process(dummy_image)
        print("✅ MediaPipe Pose processing test successful!")
        
        if results.pose_landmarks:
            print("✅ Pose landmarks detected!")
        else:
            print("ℹ️  No pose detected in dummy image (expected)")
    
    print("\n🎉 All tests passed! MediaPipe is working correctly.")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
except Exception as e:
    print(f"❌ Runtime error: {e}")

input("Press Enter to exit...")