import cv2
import numpy as np
import yaml

def load_color_ranges(config_path):
    with open(config_path, 'r') as file:
        color_ranges = yaml.safe_load(file)
    return color_ranges

def visualize_speed(frame, speed, color_ranges):
    color = (0, 0, 0)  # Default color
    for speed_range, color_value in color_ranges.items():
        min_speed, max_speed = speed_range
        if min_speed <= speed <= max_speed:
            color = color_value
            break

    cv2.putText(frame, f'Speed: {speed:.2f} m/s', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
    return frame

def process_video(video_path, color_ranges):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error opening video file.")
        return

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Placeholder for speed calculation
        speed = np.random.uniform(0, 10)  # Replace with actual speed calculation logic

        frame = visualize_speed(frame, speed, color_ranges)
        cv2.imshow('Speed Visualization', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    color_ranges = load_color_ranges('../configs/color_ranges.yaml')
    process_video('../data/input/input_video.mp4', color_ranges)