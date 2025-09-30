import cv2
from pipelines.speed_visualization import visualize_speed
from pipelines.acceleration_heatmap import generate_acceleration_heatmap
from pipelines.tip_tracking import track_javelin_tip
from io.video_reader import read_video
from io.video_writer import write_video

def main():
    video_path = "data/input/input_video.mp4"  # Input video path
    output_path = "data/output/output_video.mp4"  # Output video path

    # Read video
    frames = read_video(video_path)

    # Process frames for speed visualization
    speed_visualization_frames = visualize_speed(frames)

    # Generate acceleration heatmap
    acceleration_heatmap_frames = generate_acceleration_heatmap(speed_visualization_frames)

    # Track javelin tip
    tracked_frames = track_javelin_tip(acceleration_heatmap_frames)

    # Write processed video
    write_video(output_path, tracked_frames)

if __name__ == "__main__":
    main()