#!/usr/bin/env python3
"""
run.py - javelin-video-analysis メインエントリーポイント

既存機能に加えて、新しい可視化機能をCLIオプションで制御できる。
すべての新機能はデフォルトOFFで後方互換性を保つ。
"""

import argparse
import os
import sys
import logging
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

import cv2
import numpy as np

# 既存モジュール
from src.pipelines.pose_analysis import PoseAnalyzer

# 新しい可視化モジュール
try:
    from jva_visuals.registry import VisualPipeline, VisualPassRegistry
    from jva_visuals.adapters import adapt_state
    VISUALS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Visual enhancements not available: {e}")
    VISUALS_AVAILABLE = False

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """設定ファイルを読み込み"""
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
            
            # デフォルト設定をファイル設定で更新
            config = {**default_config}
            config.update(file_config)
            
            logger.info(f"Loaded config from: {config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config file {config_path}: {e}")
    
    return default_config


def override_config_with_args(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    """CLIオプションで設定をオーバーライド"""
    
    # 身長設定
    if args.height_m:
        config["height_m"] = args.height_m
    
    # 可視化設定
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
    
    # 出力設定
    output = config.get("output", {})
    if args.export_landmarks:
        output["export_landmarks"] = True
        output["landmarks_filename"] = args.export_landmarks
    
    # Blender設定
    blender = config.get("blender", {})
    if args.blender_overlay:
        blender["enabled"] = True
        blender["render_overlay"] = True
    
    config["visuals"] = visuals
    config["output"] = output
    config["blender"] = blender
    
    return config


def export_landmarks_json(landmarks_data: list, output_path: str):
    """ランドマークデータをJSON形式で出力"""
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
    """Blender実行コマンドを表示"""
    blender_script = project_root / "blender_bridge" / "scripts" / "setup_scene.py"
    
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
    """4つの可視化バリエーションを同時出力"""
    logger.info("🎬 4つの可視化バリエーションを同時出力します...")
    
    # 出力ファイル名を生成
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
        
        # 設定を上書き
        variant_config = config.copy()
        variant_config.update(variant["config_override"])
        
        # 出力パス
        output_path = output_dir / variant["filename"]
        
        # Blender連携用の場合はランドマークも出力
        if variant["name"] == "Blender連携用":
            landmarks_path = output_dir / f"{base_name}_landmarks.json"
            variant_config["output"]["landmarks_filename"] = str(landmarks_path)
        
        # 処理実行
        if process_video(input_path, str(output_path), variant_config):
            success_count += 1
            logger.info(f"✅ {variant['name']}: {output_path}")
        else:
            logger.error(f"❌ {variant['name']}の処理に失敗")
    
    # Blender連携コマンドの表示
    if success_count >= 3:  # Blender連携用も成功している場合
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
    """動画を処理"""
    logger.info(f"Processing video: {input_path}")
    
    # 入力チェック
    if not os.path.exists(input_path):
        logger.error(f"Input video not found: {input_path}")
        return False
    
    # 出力ディレクトリ作成
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # 動画の読み込み
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        logger.error(f"Failed to open video: {input_path}")
        return False
    
    # 動画プロパティ
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    logger.info(f"Video: {width}x{height}, {fps} fps, {total_frames} frames")
    
    # 出力動画の設定
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    if not out.isOpened():
        logger.error(f"Failed to create output video: {output_path}")
        cap.release()
        return False
    
    # PoseAnalyzerの初期化
    pose_analyzer = PoseAnalyzer()
    if config.get("height_m"):
        pose_analyzer.set_scale_from_reference(height * 0.8, config["height_m"] * 0.8)
    
    # 可視化パイプラインの初期化
    visual_pipeline = None
    if VISUALS_AVAILABLE and config.get("visuals"):
        visual_passes = VisualPassRegistry.build_from_config(
            config["visuals"], fps, config.get("height_m")
        )
        if visual_passes:
            visual_pipeline = VisualPipeline(visual_passes)
            logger.info(f"Initialized {len(visual_passes)} visual passes")
    
    # ランドマークデータの保存用
    landmarks_data = []
    export_landmarks = config.get("output", {}).get("export_landmarks", False)
    
    # フレーム処理
    frame_count = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            if frame_count % 30 == 0:  # 30フレームごとに進捗表示
                progress = (frame_count / total_frames) * 100 if total_frames > 0 else 0
                elapsed_time = (frame_count / fps) if fps > 0 else 0
                logger.info(f"Processing frame {frame_count}/{total_frames} ({progress:.1f}%) - Elapsed: {elapsed_time:.1f}s")
            
            # ポーズ解析
            state = pose_analyzer.process(frame, fps)
            
            # 基本の骨格描画
            result = pose_analyzer.render_basic(frame, state)
            
            # 可視化エフェクトを適用
            if visual_pipeline:
                try:
                    result = visual_pipeline.apply_all(
                        result, state, fps, config.get("height_m")
                    )
                except Exception as e:
                    logger.error(f"Visual pipeline error at frame {frame_count}: {e}")
            
            # ランドマークデータの保存
            if export_landmarks and state.get("points"):
                frame_landmarks = []
                for i, point in enumerate(state["points"]):
                    if point is not None:
                        frame_landmarks.append({
                            "id": i,
                            "x": float(point[0]) / width,  # 正規化座標
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
            
            # フレーム出力
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
    
    # 処理完了の詳細情報
    processing_time = frame_count / fps if fps > 0 else 0
    logger.info(f"Video processing completed: {output_path}")
    logger.info(f"Processed {frame_count} frames in {processing_time:.2f}s of video content")
    
    # ランドマークのエクスポート
    if export_landmarks and landmarks_data:
        landmarks_filename = config.get("output", {}).get("landmarks_filename", "landmarks.json")
        # 既にパスが含まれている場合はそのまま使う
        if os.path.isabs(landmarks_filename) or os.path.dirname(landmarks_filename):
            landmarks_path = landmarks_filename
        else:
            landmarks_path = os.path.join(output_dir, landmarks_filename) if output_dir else landmarks_filename
        export_landmarks_json(landmarks_data, landmarks_path)
        
        # Blenderコマンドの表示
        if config.get("blender", {}).get("enabled", False):
            blender_output = output_path.replace(".mp4", "_blender_overlay.mp4")
            print_blender_commands(output_path, landmarks_path, blender_output)
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Javelin Video Analysis with Enhanced Visualizations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 基本の骨格表示のみ（既存機能、後方互換）
  python run.py --video input.mp4 --output output.mp4

  # ベクトルとヒートマップを追加
  python run.py --video input.mp4 --output output.mp4 --vectors --heatmap

  # すべての可視化機能を有効化 + Blender連携
  python run.py --video input.mp4 --output output.mp4 --vectors --heatmap --hud --glow-trail \\
                --height-m 1.80 --export-landmarks landmarks.json --blender-overlay

  # 🎬 4つのバリエーションを同時出力（推奨！）
  python run.py --all-variants --height-m 1.80

  # 設定ファイルを使用
  python run.py --video input.mp4 --output output.mp4 --config configs/visuals.yaml
        """
    )
    
    # 入出力ファイル（デフォルトでinput/outputフォルダを使用）
    parser.add_argument("--video", help="入力動画ファイルのパス（デフォルト: input/内の最初の.mp4ファイル）")
    parser.add_argument("--output", help="出力動画ファイルのパス（デフォルト: output/analysis_<input_name>.mp4）")
    
    # 設定ファイル
    parser.add_argument("--config", help="設定ファイルのパス（YAML）")
    
    # 身長設定
    parser.add_argument("--height-m", type=float, help="被写体の身長（メートル）")
    
    # 可視化オプション
    parser.add_argument("--vectors", action="store_true", help="速度・加速度ベクトルを表示")
    parser.add_argument("--heatmap", action="store_true", help="速度ヒートマップを表示")  
    parser.add_argument("--hud", action="store_true", help="ゲーム風HUDを表示")
    parser.add_argument("--wrist-trail", action="store_true", help="右手首軌跡を表示")
    parser.add_argument("--glow-trail", action="store_true", help="光軌跡エフェクトを表示")
    
    # マルチ出力オプション
    parser.add_argument("--all-variants", action="store_true", 
                       help="4つの可視化バリエーションを同時出力（骨格+軌跡、ヒートマップ、ゲーム風、Blender連携）")
    
    # 出力オプション
    parser.add_argument("--export-landmarks", help="ランドマークをJSONで出力（ファイル名を指定）")
    
    # Blender連携
    parser.add_argument("--blender-overlay", action="store_true", 
                       help="Blender実行コマンドを表示（要 --export-landmarks）")
    
    # デバッグ
    parser.add_argument("--verbose", action="store_true", help="詳細ログを出力")
    
    args = parser.parse_args()
    
    # ログレベル設定
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # デフォルト入出力パス設定
    if not args.video:
        # inputフォルダから最初の.mp4ファイルを探す
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
        # 入力ファイル名から出力ファイル名を生成
        input_path = Path(args.video)
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)  # outputフォルダを作成（存在しない場合）
        args.output = str(output_dir / f"analysis_{input_path.name}")
        logger.info(f"自動設定された出力パス: {args.output}")
    
    # 設定読み込み
    config = load_config(args.config)
    config = override_config_with_args(config, args)
    
    # 可視化機能の利用可能性チェック
    if not VISUALS_AVAILABLE and any([args.vectors, args.heatmap, args.hud, args.wrist_trail, args.glow_trail, args.all_variants]):
        logger.warning("可視化機能が利用できません。基本機能のみで実行します。")
    
    # 動画処理実行
    if args.all_variants:
        # 4つのバリエーションを同時出力
        success = process_video_all_variants(args.video, args.output, config)
    else:
        # 通常の単一出力
        success = process_video(args.video, args.output, config)
    
    if success:
        if args.all_variants:
            print(f"\n🎉 全バリエーション処理完了！")
            print(f"📁 出力フォルダ: {Path(args.output).parent}")
        else:
            print(f"\n✅ 処理完了: {args.output}")
            
            # 設定内容の表示
            enabled_features = []
            visuals = config.get("visuals", {})
            if visuals.get("vectors"): enabled_features.append("ベクトル")
            if visuals.get("heatmap"): enabled_features.append("ヒートマップ")
            if visuals.get("hud"): enabled_features.append("HUD")
            if visuals.get("wrist_trail"): enabled_features.append("手首軌跡")
            if visuals.get("glow_trail"): enabled_features.append("光軌跡")
            
            if enabled_features:
                print(f"📊 有効な機能: {', '.join(enabled_features)}")
            else:
                print("📊 基本骨格表示のみ（後方互換モード）")
        
        if config.get("height_m"):
            print(f"📏 身長設定: {config['height_m']:.2f}m")
        
        sys.exit(0)
    else:
        print("❌ 処理中にエラーが発生しました。")
        sys.exit(1)


if __name__ == "__main__":
    main()