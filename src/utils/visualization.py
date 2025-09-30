import cv2
import numpy as np

def overlay_heatmap(frame, heatmap_value):
    """
    フレームにヒートマップをオーバーレイする
    heatmap_value: 0-255の範囲のスカラー値
    """
    # heatmap_valueがスカラーの場合、フレームサイズの配列に変換
    if np.isscalar(heatmap_value):
        height, width = frame.shape[:2]
        heatmap_array = np.full((height, width), heatmap_value, dtype=np.uint8)
    else:
        heatmap_array = heatmap_value.astype(np.uint8)
    
    # カラーマップを適用
    heatmap_colored = cv2.applyColorMap(heatmap_array, cv2.COLORMAP_JET)
    
    # フレームとヒートマップをブレンド
    overlay = cv2.addWeighted(frame, 0.7, heatmap_colored, 0.3, 0)
    
    return overlay

def draw_tracking_path(frame, points, color=(0, 255, 0), thickness=2):
    """Draw the tracking path on the video frame."""
    for i in range(1, len(points)):
        if points[i - 1] is not None and points[i] is not None:
            cv2.line(frame, points[i - 1], points[i], color, thickness)

def display_frame(frame, window_name='Video'):
    """Display a video frame."""
    cv2.imshow(window_name, frame)
    cv2.waitKey(1)

def save_frame(video_writer, frame):
    """Save a processed frame to the video writer."""
    video_writer.write(frame)