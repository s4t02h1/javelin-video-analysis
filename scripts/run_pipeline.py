import os
import glob
import cv2
from src.pipelines.pose_analysis import PoseAnalyzer

def run_pipeline(input_video_path, output_stem, export_rgba_sequence=False):
    if not os.path.exists(input_video_path):
        print(f"Input video path '{input_video_path}' does not exist.")
        return

    print(f"Processing: {input_video_path}")
    cap = cv2.VideoCapture(input_video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {input_video_path}")
        return

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_basic   = cv2.VideoWriter(f"{output_stem}_pose_basic.mp4",    fourcc, fps, (width, height))
    out_heatmap = cv2.VideoWriter(f"{output_stem}_pose_heatmap.mp4",  fourcc, fps, (width, height))
    out_stick   = cv2.VideoWriter(f"{output_stem}_pose_stickman_green.mp4", fourcc, fps, (width, height))

    rgba_dir = f"{output_stem}_pose_stickman_rgba"
    if export_rgba_sequence:
        os.makedirs(rgba_dir, exist_ok=True)

    analyzer = PoseAnalyzer()
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        state = analyzer.process(frame, fps)

        basic_frame   = analyzer.render_basic(frame, state)
        heatmap_frame = analyzer.render_heatmap(frame, state)
        stick_frame   = analyzer.render_stickman(frame.shape, state, background='green')

        out_basic.write(basic_frame)
        out_heatmap.write(heatmap_frame)
        out_stick.write(stick_frame)

        if export_rgba_sequence:
            rgba = analyzer.render_stickman_rgba(frame.shape, state)
            cv2.imwrite(os.path.join(rgba_dir, f"{frame_count:06d}.png"), rgba)

        frame_count += 1
        if frame_count % 30 == 0:
            print(f"  Processed {frame_count} frames...")

    cap.release()
    out_basic.release()
    out_heatmap.release()
    out_stick.release()
    analyzer.close()

    print(f"Saved: {output_stem}_pose_basic.mp4")
    print(f"Saved: {output_stem}_pose_heatmap.mp4")
    print(f"Saved: {output_stem}_pose_stickman_green.mp4")
    if export_rgba_sequence:
        print(f"Saved RGBA PNG sequence: {rgba_dir}\\%06d.png")

def process_all_videos(input_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    video_files = glob.glob(os.path.join(input_dir, "*.mp4"))
    if not video_files:
        print(f"No MP4 files found in '{input_dir}'")
        return

    print(f"Found {len(video_files)} video files to process:")
    for video_file in video_files:
        print(f"  - {os.path.basename(video_file)}")

    for i, input_video_path in enumerate(video_files, 1):
        filename = os.path.basename(input_video_path)
        name, _ = os.path.splitext(filename)
        output_stem = os.path.join(output_dir, name)
        print(f"\n[{i}/{len(video_files)}] Processing: {filename}")
        run_pipeline(input_video_path, output_stem, export_rgba_sequence=False)  # TrueでPNG透過も出力

if __name__ == "__main__":
    input_directory = "input"
    output_directory = "output"
    process_all_videos(input_directory, output_directory)