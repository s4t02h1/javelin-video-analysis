# Add project root to sys.path before other imports
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
import os
import glob
import cv2
import argparse
import json
from src.pipelines.pose_analysis import PoseAnalyzer
from jva_visuals.registry import VisualPassRegistry

def run_pipeline(input_video_path, output_stem, export_rgba_sequence=False, args=None):
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

    config = locals().get("config", {}) or {}
    vconf = (config.get("visuals") or {}).copy()
    if args.vectors: vconf["vectors"] = True
    if args.heatmap: vconf["heatmap"] = True
    if args.hud: vconf["hud"] = True
    if args.glow_trail:
        vconf["wrist_trail"] = True
        vconf["glow_trail"] = True
    visual_passes = VisualPassRegistry.build_from_config(vconf)

    export = {"names": [f"J{i}" for i in range(33)], "frames": []} if args.export_landmarks else None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        state = analyzer.process(frame, fps)

        basic_frame   = analyzer.render_basic(frame, state)
        heatmap_frame = analyzer.render_heatmap(frame, state)
        stick_frame   = analyzer.render_stickman(frame.shape, state, background='green')

        state["height_m"] = args.height_m
        frame = VisualPassRegistry.apply_all(frame, state, visual_passes)
        if export is not None:
            export["frames"].append([(int(p[0]), int(p[1])) if p is not None else None for p in (state.get("points") or [])])

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

    if export is not None and args.export_landmarks:
        with open(args.export_landmarks, "w", encoding="utf-8") as f:
            json.dump(export, f)
        if args.blender_overlay:
            print("blender --background --python blender_bridge/scripts/setup_scene.py -- "
                  f"--video outputs/throw.mp4 --landmarks {args.export_landmarks} --out outputs/throw_blender_overlay.mp4")

    print(f"Saved: {output_stem}_pose_basic.mp4")
    print(f"Saved: {output_stem}_pose_heatmap.mp4")
    print(f"Saved: {output_stem}_pose_stickman_green.mp4")
    if export_rgba_sequence:
        print(f"Saved RGBA PNG sequence: {rgba_dir}\\%06d.png")

def process_all_videos(input_directory, output_directory, args=None):
    video_files = []
    for ext in ["*.mp4", "*.MP4", "*.mov", "*.MOV", "*.avi", "*.AVI"]:
        video_files.extend(glob.glob(os.path.join(input_directory, ext)))
    video_files = sorted(set(video_files))

    if not video_files:
        print(f"No video files found in {input_directory}")
        return

    print(f"Found {len(video_files)} video files to process:")
    for f in video_files:
        print(f"  - {os.path.basename(f)}")

    for i, input_video_path in enumerate(video_files, 1):
        basename = os.path.splitext(os.path.basename(input_video_path))[0]
        output_stem = os.path.join(output_directory, basename)
        print(f"\n[{i}/{len(video_files)}] Processing: {os.path.basename(input_video_path)}")
        run_pipeline(input_video_path, output_stem, export_rgba_sequence=False, args=args)
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", action="store_true", help="Enable vector overlay")
    parser.add_argument("--heatmap", action="store_true", help="Enable heatmap overlay")
    parser.add_argument("--hud", action="store_true", help="Enable HUD overlay")
    parser.add_argument("--glow-trail", dest="glow_trail", action="store_true", help="Enable glow wrist trail")
    parser.add_argument("--height-m", type=float, default=None, help="Athlete height in meters")
    parser.add_argument("--export-landmarks", type=str, default=None, help="Export landmarks JSON path")
    parser.add_argument("--blender-overlay", action="store_true", help="Print Blender overlay command")
    args = parser.parse_args()
    config = locals().get("config", {}) or {}
    vconf = (config.get("visuals") or {}).copy()
    if args.vectors: vconf["vectors"] = True
    if args.heatmap: vconf["heatmap"] = True
    if args.hud: vconf["hud"] = True
    if args.glow_trail:
        vconf["wrist_trail"] = True
        vconf["glow_trail"] = True
    visual_passes = VisualPassRegistry.build_from_config(vconf)

    export = {"names": [f"J{i}" for i in range(33)], "frames": []} if args.export_landmarks else None

    input_directory = "data/input"
    output_directory = "data/output"
    process_all_videos(input_directory, output_directory, args)

if __name__ == "__main__":
    main()