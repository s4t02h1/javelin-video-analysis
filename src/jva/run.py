#!/usr/bin/env python3
"""
jva.run - javelin-video-analysis メインエントリーポイント（パッケージ版）
"""

import argparse
import os
import sys
import logging
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional

# リポジトリルートを推定して src を import パスへ
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "src"))

import cv2  # type: ignore
import numpy as np  # type: ignore

from src.pipelines.pose_analysis import PoseAnalyzer

try:
    from jva_visuals.registry import VisualPipeline, VisualPassRegistry
    from jva_visuals.adapters import adapt_state  # noqa: F401
    VISUALS_AVAILABLE = True
except Exception as e:
    print(f"Warning: Visual enhancements not available: {e}")
    VISUALS_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    default_config = {
        "height_m": None,
        "visuals": {},
        "output": {"export_landmarks": False},
        "blender": {"enabled": False},
        "debug": {"profile_performance": False}
    }
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f) or {}
            cfg = {**default_config}
            cfg.update(file_config)
            logger.info(f"Loaded config from: {config_path}")
            return cfg
        except Exception as e:
            logger.error(f"Failed to load config file {config_path}: {e}")
    return default_config


def override_config_with_args(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    if args.height_m:
        config["height_m"] = args.height_m
    visuals = config.get("visuals", {})
    if args.vectors:
        visuals["vectors"] = True
    if args.heatmap:
        visuals["heatmap"] = True
    if args.hud:
        visuals["hud"] = True
    if args.wrist_trail:
        visuals["wrist_trail"] = True
    if args.glow_trail:
        visuals["glow_trail"] = True
    output = config.get("output", {})
    if args.export_landmarks:
        output["export_landmarks"] = True
        output["landmarks_filename"] = args.export_landmarks
    blender = config.get("blender", {})
    if args.blender_overlay:
        blender["enabled"] = True
        blender["render_overlay"] = True
    config["visuals"] = visuals
    config["output"] = output
    config["blender"] = blender
    return config


def export_landmarks_json(landmarks_data: list, output_path: str):
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "format": "mediapipe_pose_landmarks",
                "version": "1.0",
                "frame_count": len(landmarks_data),
                "landmarks": landmarks_data
            }, f, indent=2)
        logger.info(f"Exported landmarks to: {output_path}")
    except Exception as e:
        logger.error(f"Failed to export landmarks: {e}")


def print_blender_commands(video_path: str, landmarks_path: str, output_path: str):
    blender_script = repo_root / "blender_bridge" / "scripts" / "setup_scene.py"
    commands = [
        "# Blender連携コマンド例:",
        f"blender --background --python {blender_script} -- \\",
        f"  --video {video_path} \\",
        f"  --landmarks {landmarks_path} \\", 
        f"  --output {output_path}",
        "",
        "# または既存のBlenderファイルに適用:",
        f"blender your_scene.blend --python {blender_script} -- \\",
        f"  --video {video_path} \\",
        f"  --landmarks {landmarks_path} \\",
        f"  --output {output_path}"
    ]
    print("\n" + "\n".join(commands) + "\n")


def process_video_all_variants(input_path: str, base_output_path: str, config: Dict[str, Any]) -> bool:
    logger.info("🎬 4つの可視化バリエーションを同時出力します...")
    base_name = Path(base_output_path).stem
    output_dir = Path(base_output_path).parent
    variants = [
        {
            "name": "骨格+軌跡",
            "filename": f"{base_name}_skeleton_with_trail.mp4",
            "config_override": {
                "visuals": {
                    "trails": {"enabled": True, "right_wrist": True},
                    "vectors": {"enabled": False},
                    "heatmap": {"enabled": False},
                    "hud": {"enabled": False}
                }
            }
        },
        {
            "name": "ヒートマップ",
            "filename": f"{base_name}_heatmap.mp4",
            "config_override": {
                "visuals": {
                    "heatmap": {"enabled": True, "show_colorbar": True},
                    "vectors": {"enabled": False},
                    "trails": {"enabled": False},
                    "hud": {"enabled": False}
                }
            }
        },
        {
            "name": "ゲーム風HUD",
            "filename": f"{base_name}_gaming_hud.mp4",
            "config_override": {
                "visuals": {
                    "hud": {"enabled": True, "show_metrics": True},
                    "vectors": {"enabled": False},
                    "heatmap": {"enabled": False},
                    "trails": {"enabled": False}
                }
            }
        },
        {
            "name": "Blender連携用",
            "filename": f"{base_name}_for_blender.mp4",
            "config_override": {
                "visuals": {
                    "vectors": {"enabled": True},
                    "heatmap": {"enabled": True},
                    "trails": {"enabled": True, "right_wrist": True},
                    "hud": {"enabled": False}
                },
                "output": {"export_landmarks": True}
            }
        }
    ]
    success_count = 0
    total_variants = len(variants)
    for i, variant in enumerate(variants, 1):
        print(f"\n📊 [{i}/{total_variants}] {variant['name']}を処理中...")
        variant_config = config.copy()
        variant_config.update(variant["config_override"])
        output_path = output_dir / variant["filename"]
        if variant["name"] == "Blender連携用":
            landmarks_path = output_dir / f"{base_name}_landmarks.json"
            variant_config["output"]["landmarks_filename"] = str(landmarks_path)
        if process_video(input_path, str(output_path), variant_config):
            success_count += 1
            logger.info(f"✅ {variant['name']}: {output_path}")
        else:
            logger.error(f"❌ {variant['name']}の処理に失敗")
    if success_count >= 3:
        blender_video = output_dir / f"{base_name}_for_blender.mp4"
        landmarks_file = output_dir / f"{base_name}_landmarks.json"
        blender_output = output_dir / f"{base_name}_3d_overlay.mp4"
        print(f"\n🎭 Blender 3D連携コマンド:")
        print(f"blender --background --python blender_bridge/scripts/setup_scene.py -- \\")
        print(f"  --video {blender_video} \\")
        print(f"  --landmarks {landmarks_file} \\")
        print(f"  --output {blender_output}")
    print(f"\n🎉 完了: {success_count}/{total_variants} バリエーションを出力しました")
    return success_count == total_variants


def process_video(input_path: str, output_path: str, config: Dict[str, Any]) -> bool:
    logger.info(f"Processing video: {input_path}")
    if not os.path.exists(input_path):
        logger.error(f"Input video not found: {input_path}")
        return False
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        logger.error(f"Failed to open video: {input_path}")
        return False
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    logger.info(f"Video: {width}x{height}, {fps} fps, {total_frames} frames")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    if not out.isOpened():
        logger.error(f"Failed to create output video: {output_path}")
        cap.release()
        return False
    pose_analyzer = PoseAnalyzer()
    if config.get("height_m"):
        pose_analyzer.set_scale_from_reference(height * 0.8, config["height_m"] * 0.8)
    visual_pipeline = None
    if VISUALS_AVAILABLE and config.get("visuals"):
        visual_passes = VisualPassRegistry.build_from_config(
            config["visuals"], fps, config.get("height_m")
        )
        if visual_passes:
            visual_pipeline = VisualPipeline(visual_passes)
            logger.info(f"Initialized {len(visual_passes)} visual passes")
    landmarks_data = []
    export_landmarks = config.get("output", {}).get("export_landmarks", False)
    frame_count = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1
            if frame_count % 30 == 0:
                progress = (frame_count / total_frames) * 100 if total_frames > 0 else 0
                elapsed_time = (frame_count / fps) if fps > 0 else 0
                logger.info(f"Processing frame {frame_count}/{total_frames} ({progress:.1f}%) - Elapsed: {elapsed_time:.1f}s")
            state = pose_analyzer.process(frame, fps)
            result = pose_analyzer.render_basic(frame, state)
            if visual_pipeline:
                try:
                    result = visual_pipeline.apply_all(
                        result, state, fps, config.get("height_m")
                    )
                except Exception as e:
                    logger.error(f"Visual pipeline error at frame {frame_count}: {e}")
            if export_landmarks and state.get("points"):
                frame_landmarks = []
                for i, point in enumerate(state["points"]):
                    if point is not None:
                        frame_landmarks.append({
                            "id": i,
                            "x": float(point[0]) / width,
                            "y": float(point[1]) / height,
                            "visibility": 1.0
                        })
                    else:
                        frame_landmarks.append({
                            "id": i,
                            "x": 0.0,
                            "y": 0.0,
                            "visibility": 0.0
                        })
                landmarks_data.append({
                    "frame": frame_count,
                    "timestamp": frame_count / fps,
                    "landmarks": frame_landmarks
                })
            out.write(result)
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        return False
    finally:
        cap.release()
        out.release()
        pose_analyzer.close()
    processing_time = frame_count / fps if fps > 0 else 0
    logger.info(f"Video processing completed: {output_path}")
    logger.info(f"Processed {frame_count} frames in {processing_time:.2f}s of video content")
    if export_landmarks and landmarks_data:
        landmarks_filename = config.get("output", {}).get("landmarks_filename", "landmarks.json")
        if os.path.isabs(landmarks_filename) or os.path.dirname(landmarks_filename):
            landmarks_path = landmarks_filename
        else:
            landmarks_path = os.path.join(output_dir, landmarks_filename) if output_dir else landmarks_filename
        export_landmarks_json(landmarks_data, landmarks_path)
        if config.get("blender", {}).get("enabled", False):
            blender_output = output_path.replace(".mp4", "_blender_overlay.mp4")
            print_blender_commands(output_path, landmarks_path, blender_output)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Javelin Video Analysis with Enhanced Visualizations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "\n使用例:\n"
            "  # 基本の骨格表示のみ（既存機能、後方互換）\n"
            "  python run.py --video input.mp4 --output output.mp4\n\n"
            "  # ベクトルとヒートマップを追加\n"
            "  python run.py --video input.mp4 --output output.mp4 --vectors --heatmap\n\n"
            "  # すべての可視化機能を有効化 + Blender連携\n"
            "  python run.py --video input.mp4 --output output.mp4 --vectors --heatmap --hud --glow-trail \\\n+                --height-m 1.80 --export-landmarks landmarks.json --blender-overlay\n\n"
            "  # 🎬 4つのバリエーションを同時出力（推奨！）\n"
            "  python run.py --all-variants --height-m 1.80\n\n"
            "  # 設定ファイルを使用\n"
            "  python run.py --video input.mp4 --output output.mp4 --config configs/visuals.yaml\n"
        )
    )
    parser.add_argument("--video", help="入力動画ファイルのパス（デフォルト: input/内の最初の.mp4ファイル）")
    parser.add_argument("--output", help="出力動画ファイルのパス（デフォルト: output/analysis_<input_name>.mp4）")
    parser.add_argument("--config", help="設定ファイルのパス（YAML）")
    parser.add_argument("--height-m", type=float, help="被写体の身長（メートル）")
    parser.add_argument("--vectors", action="store_true", help="速度・加速度ベクトルを表示")
    parser.add_argument("--heatmap", action="store_true", help="速度ヒートマップを表示")
    parser.add_argument("--hud", action="store_true", help="ゲーム風HUDを表示")
    parser.add_argument("--wrist-trail", action="store_true", help="右手首軌跡を表示")
    parser.add_argument("--glow-trail", action="store_true", help="光軌跡エフェクトを表示")
    parser.add_argument("--all-variants", action="store_true", help="4つの可視化バリエーションを同時出力")
    parser.add_argument("--export-landmarks", help="ランドマークをJSONで出力（ファイル名を指定）")
    parser.add_argument("--blender-overlay", action="store_true", help="Blender実行コマンドを表示（要 --export-landmarks）")
    parser.add_argument("--verbose", action="store_true", help="詳細ログを出力")
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    if not args.video:
        input_dir = Path("input")
        if input_dir.exists():
            video_files = list(input_dir.glob("*.mp4"))
            if video_files:
                args.video = str(video_files[0])
                logger.info(f"自動選択された入力動画: {args.video}")
            else:
                logger.error("inputフォルダに.mp4ファイルが見つかりません")
                return False
        else:
            logger.error("inputフォルダが存在しません")
            return False
    if not args.output:
        input_path = Path(args.video)
        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)
        args.output = str(out_dir / f"analysis_{input_path.name}")
        logger.info(f"自動設定された出力パス: {args.output}")
    config = load_config(args.config)
    config = override_config_with_args(config, args)
    if not VISUALS_AVAILABLE and any([args.vectors, args.heatmap, args.hud, args.wrist_trail, args.glow_trail, args.all_variants]):
        logger.warning("可視化機能が利用できません。基本機能のみで実行します。")
    if args.all_variants:
        success = process_video_all_variants(args.video, args.output, config)
    else:
        success = process_video(args.video, args.output, config)
    if success:
        if args.all_variants:
            print(f"\n🎉 全バリエーション処理完了！")
            print(f"📁 出力フォルダ: {Path(args.output).parent}")
        else:
            print(f"\n✅ 処理完了: {args.output}")
            enabled = []
            vis = config.get("visuals", {})
            if vis.get("vectors"): enabled.append("ベクトル")
            if vis.get("heatmap"): enabled.append("ヒートマップ")
            if vis.get("hud"): enabled.append("HUD")
            if vis.get("wrist_trail"): enabled.append("手首軌跡")
            if vis.get("glow_trail"): enabled.append("光軌跡")
            print(f"📊 有効な機能: {', '.join(enabled)}" if enabled else "📊 基本骨格表示のみ（後方互換モード）")
        if config.get("height_m"):
            print(f"📏 身長設定: {config['height_m']:.2f}m")
        sys.exit(0)
    else:
        print("❌ 処理中にエラーが発生しました。")
        sys.exit(1)


if __name__ == "__main__":
    main()
