import numpy as np
import cv2
from src.utils.filters import apply_median_filter
from src.utils.visualization import overlay_heatmap


def calculate_acceleration_heatmap(speed_series: np.ndarray) -> np.ndarray:
    """Return a simple non-negative heatmap (N x N) from a 1D speed array.

    This is a lightweight placeholder used by tests. It constructs a matrix
    where each entry is the absolute speed difference between two timesteps,
    normalized to [0, 1], then scaled to produce a heat-like 2D array.

    Args:
        speed_series: 1D numpy array of length N representing speeds.

    Returns:
        heatmap: 2D numpy array of shape (N, N), dtype float32, non-negative.
    """
    if speed_series is None:
        speed_series = np.zeros(1, dtype=np.float32)
    speed_series = np.asarray(speed_series, dtype=np.float32).reshape(-1)
    n = int(speed_series.shape[0])
    if n == 0:
        return np.zeros((0, 0), dtype=np.float32)

    # Pairwise absolute differences
    a = speed_series.reshape(n, 1)
    b = speed_series.reshape(1, n)
    diff = np.abs(a - b).astype(np.float32)
    # Normalize to [0, 1]
    maxv = float(diff.max()) if diff.size > 0 else 0.0
    if maxv > 0:
        diff /= maxv
    return diff.astype(np.float32)

def calculate_acceleration(velocity, time_intervals):
    # time_intervalsの長さをvelocityに合わせる
    if len(time_intervals) != len(velocity) - 1:
        # フレーム間の時間間隔を計算（velocityの長さ-1）
        time_intervals = time_intervals[:len(velocity)-1] if len(time_intervals) > len(velocity)-1 else time_intervals * ((len(velocity)-1) // len(time_intervals) + 1)
        time_intervals = time_intervals[:len(velocity)-1]
    
    acceleration = np.diff(velocity) / np.array(time_intervals)
    return np.concatenate(([0], acceleration))  # Prepend 0 for the first frame

def generate_acceleration_heatmap(video_path, output_path, time_intervals=None):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Could not open video.")
        return

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    # time_intervalsがNoneまたは不適切な場合は、FPSから計算
    if time_intervals is None or len(time_intervals) == 0:
        frame_interval = 1.0 / fps if fps > 0 else 1.0/30.0
        time_intervals = [frame_interval] * (frame_count - 1)
    elif len(time_intervals) != frame_count - 1:
        # time_intervalsをframe_count-1の長さに調整
        frame_interval = 1.0 / fps if fps > 0 else 1.0/30.0
        time_intervals = [frame_interval] * (frame_count - 1)
    
    velocity = np.zeros(frame_count)
    acceleration = np.zeros(frame_count)

    # Placeholder for velocity calculation
    for i in range(frame_count):
        ret, frame = cap.read()
        if not ret:
            break
        # Here you would calculate velocity based on your specific logic
        # For demonstration, we will use a dummy velocity
        velocity[i] = np.random.rand() * 10  # Replace with actual velocity calculation

    # Calculate acceleration
    acceleration = calculate_acceleration(velocity, time_intervals)

    # Apply smoothing filter to acceleration
    smoothed_acceleration = apply_median_filter(acceleration)

    # Create a heatmap based on smoothed acceleration - 正しいデータ型に変換
    heatmap = np.zeros(frame_count, dtype=np.float32)
    for i in range(frame_count):
        heatmap[i] = smoothed_acceleration[i]
    
    # heatmapを0-255の範囲に正規化してCV_8UC1形式に変換
    heatmap_normalized = ((heatmap - heatmap.min()) / (heatmap.max() - heatmap.min() + 1e-8) * 255).astype(np.uint8)

    # Overlay heatmap on video frames
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # MP4互換のコーデックに変更
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    for i in range(frame_count):
        ret, frame = cap.read()
        if not ret:
            break
        # 正規化されたheatmap値を使用
        overlay_frame = overlay_heatmap(frame, heatmap_normalized[i])
        out.write(overlay_frame)

    cap.release()
    out.release()
    print("Acceleration heatmap video saved to:", output_path)