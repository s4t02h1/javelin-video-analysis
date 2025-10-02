#!/usr/bin/env python3
"""
テスト用ダミー動画生成スクリプト
"""

import cv2
import numpy as np
import os


def create_test_video(output_path="test_input.mp4", duration_sec=5, fps=30):
    """テスト用のダミー動画を生成"""
    
    # 動画設定
    width, height = 640, 480
    total_frames = duration_sec * fps
    
    # 動画ライター初期化
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    print(f"Creating test video: {output_path}")
    print(f"Duration: {duration_sec}s, FPS: {fps}, Frames: {total_frames}")
    
    for frame_num in range(total_frames):
        # カラフルな背景を作成
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # グラデーション背景
        for y in range(height):
            for x in range(width):
                frame[y, x] = [
                    int(255 * x / width),
                    int(255 * y / height), 
                    int(255 * (frame_num % 30) / 30)
                ]
        
        # 移動する円（疑似人物）
        center_x = int(width * 0.3 + (width * 0.4) * (frame_num / total_frames))
        center_y = int(height * 0.5 + 50 * np.sin(2 * np.pi * frame_num / 60))
        
        cv2.circle(frame, (center_x, center_y), 30, (255, 255, 255), -1)
        cv2.circle(frame, (center_x, center_y), 25, (0, 0, 255), -1)
        
        # フレーム番号を表示
        cv2.putText(frame, f"Frame {frame_num+1}/{total_frames}", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        out.write(frame)
    
    out.release()
    print(f"Test video created: {output_path}")
    return output_path


if __name__ == "__main__":
    create_test_video()