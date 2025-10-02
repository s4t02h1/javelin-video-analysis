"""
render_overlay.py - オーバーレイ動画のレンダリング

setup_scene.pyで設定したシーンをレンダリングし、
背景動画と3D人体モデルを合成したオーバーレイ動画を生成する。
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# Blender特有のモジュールを条件付きでインポート
try:
    import bpy
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False
    print("Warning: Blender modules not available. Script will only work within Blender.")


def load_background_video(video_path):
    """背景動画をBlenderに読み込み"""
    if not os.path.exists(video_path):
        print(f"Background video not found: {video_path}")
        return False
    
    try:
        # Movie Clip を作成
        clip = bpy.data.movieclips.load(video_path)
        print(f"Loaded background video: {video_path}")
        print(f"Duration: {clip.frame_duration} frames")
        
        # シーンのフレーム設定を動画に合わせる
        scene = bpy.context.scene
        scene.frame_end = clip.frame_duration
        
        # Compositor での背景設定
        if not scene.use_nodes:
            scene.use_nodes = True
        
        tree = scene.node_tree
        
        # Movie Clip ノードを検索または作成
        movie_node = None
        for node in tree.nodes:
            if node.type == 'MOVIECLIP':
                movie_node = node
                break
        
        if not movie_node:
            movie_node = tree.nodes.new(type='CompositorNodeMovieClip')
        
        movie_node.clip = clip
        
        return True
        
    except Exception as e:
        print(f"Error loading background video: {e}")
        return False


def setup_compositor_for_overlay():
    """コンポジターでオーバーレイ合成を設定"""
    scene = bpy.context.scene
    if not scene.use_nodes:
        scene.use_nodes = True
    
    tree = scene.node_tree
    
    # 既存ノードをクリア
    for node in tree.nodes:
        tree.nodes.remove(node)
    
    # レンダーレイヤー（3Dモデル）
    render_layers = tree.nodes.new(type='CompositorNodeRLayers')
    render_layers.location = (0, 0)
    
    # Movie Clip（背景動画）
    movie_clip = tree.nodes.new(type='CompositorNodeMovieClip')
    movie_clip.location = (0, -300)
    
    # スケール調整（必要に応じて）
    scale_bg = tree.nodes.new(type='CompositorNodeScale')
    scale_bg.location = (300, -300)
    scale_bg.space = 'RENDER_SIZE'
    scale_bg.frame_method = 'STRETCH'
    
    # アルファオーバー（合成）
    alpha_over = tree.nodes.new(type='CompositorNodeAlphaOver')
    alpha_over.location = (600, 0)
    alpha_over.inputs['Fac'].default_value = 1.0  # 完全合成
    
    # カラー補正（オプション）
    color_balance = tree.nodes.new(type='CompositorNodeColorBalance')
    color_balance.location = (300, 0)
    color_balance.correction_method = 'LIFT_GAMMA_GAIN'
    
    # 出力
    composite = tree.nodes.new(type='CompositorNodeComposite')
    composite.location = (900, 0)
    
    # ファイル出力（中間ファイル保存用）
    file_output = tree.nodes.new(type='CompositorNodeOutputFile')
    file_output.location = (900, -200)
    file_output.format.file_format = 'PNG'
    file_output.base_path = '/tmp/blender_render/'
    
    # ノード接続
    tree.links.new(movie_clip.outputs['Image'], scale_bg.inputs['Image'])
    tree.links.new(scale_bg.outputs['Image'], alpha_over.inputs[1])  # 背景
    
    tree.links.new(render_layers.outputs['Image'], color_balance.inputs['Image'])
    tree.links.new(color_balance.outputs['Image'], alpha_over.inputs[2])  # 前景（3D）
    
    tree.links.new(alpha_over.outputs['Image'], composite.inputs['Image'])
    tree.links.new(alpha_over.outputs['Image'], file_output.inputs['Image'])
    
    return True


def optimize_render_settings(quality='MEDIUM'):
    """レンダリング最適化設定"""
    scene = bpy.context.scene
    render = scene.render
    
    # 基本設定
    render.engine = 'EEVEE'  # 高速レンダリング
    
    # EEVEE最適化
    eevee = scene.eevee
    
    if quality == 'LOW':
        # 低品質・高速設定
        eevee.taa_render_samples = 16
        eevee.use_bloom = False
        eevee.use_ssr = False
        eevee.use_motion_blur = False
        render.resolution_percentage = 50
    elif quality == 'HIGH':
        # 高品質設定
        eevee.taa_render_samples = 128
        eevee.use_bloom = True
        eevee.use_ssr = True
        eevee.use_motion_blur = True
        eevee.motion_blur_shutter = 0.5
        render.resolution_percentage = 100
    else:  # MEDIUM
        # バランス設定
        eevee.taa_render_samples = 64
        eevee.use_bloom = True
        eevee.use_ssr = False
        eevee.use_motion_blur = False
        render.resolution_percentage = 75
    
    # パフォーマンス設定
    eevee.use_volumetric_lighting = False  # 重い処理を無効化
    eevee.volumetric_tile_size = '16'
    
    # GPU設定（可能な場合）
    preferences = bpy.context.preferences
    cycles_preferences = preferences.addons['cycles'].preferences
    
    # 利用可能なGPUを確認
    cycles_preferences.get_devices()
    if cycles_preferences.devices:
        for device in cycles_preferences.devices:
            if device.type == 'CUDA' or device.type == 'OPENCL':
                device.use = True
                print(f"Enabled GPU: {device.name}")


def render_animation(output_path, start_frame=None, end_frame=None):
    """アニメーションをレンダリング"""
    scene = bpy.context.scene
    render = scene.render
    
    # フレーム範囲設定
    if start_frame is not None:
        scene.frame_start = start_frame
    if end_frame is not None:
        scene.frame_end = end_frame
    
    # 出力設定
    render.filepath = output_path
    
    print(f"Rendering animation...")
    print(f"Frame range: {scene.frame_start} - {scene.frame_end}")
    print(f"Output: {output_path}")
    print(f"Resolution: {render.resolution_x}x{render.resolution_y}")
    
    try:
        # レンダリング実行
        bpy.ops.render.render(animation=True)
        print("Render completed successfully!")
        return True
        
    except Exception as e:
        print(f"Render failed: {e}")
        return False


def post_process_video(input_path, output_path, background_video_path=None):
    """FFmpegを使用した後処理"""
    try:
        # FFmpegコマンドを構築
        if background_video_path and os.path.exists(background_video_path):
            # 背景動画と合成
            cmd = [
                'ffmpeg', '-y',
                '-i', background_video_path,  # 背景
                '-i', input_path,             # Blenderレンダー結果
                '-filter_complex', '[1:v][0:v]overlay=0:0[out]',
                '-map', '[out]',
                '-map', '0:a?',  # 音声があれば取得
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '20',
                output_path
            ]
        else:
            # 単純な再エンコード
            cmd = [
                'ffmpeg', '-y',
                '-i', input_path,
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '20',
                output_path
            ]
        
        print(f"Post-processing with FFmpeg...")
        print(f"Command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Post-processing completed successfully!")
            return True
        else:
            print(f"FFmpeg error: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print("FFmpeg not found. Please install FFmpeg for post-processing.")
        return False
    except Exception as e:
        print(f"Post-processing error: {e}")
        return False


def main():
    """メイン処理"""
    # Blender環境チェック
    if not BLENDER_AVAILABLE:
        print("Error: This script must be run within Blender.")
        print("Usage: blender --python render_overlay.py -- --background video.mp4 --output output.mp4")
        return
    
    # コマンドライン引数の解析
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    
    parser = argparse.ArgumentParser(description="Render human pose overlay video")
    parser.add_argument("--background", help="Background video file")
    parser.add_argument("--output", default="overlay_output.mp4", help="Output video file")
    parser.add_argument("--quality", choices=['LOW', 'MEDIUM', 'HIGH'], default='MEDIUM')
    parser.add_argument("--start-frame", type=int, help="Start frame")
    parser.add_argument("--end-frame", type=int, help="End frame")
    parser.add_argument("--post-process", action='store_true', help="Apply post-processing with FFmpeg")
    
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print("Usage: blender --python render_overlay.py -- --output output.mp4")
        return
    
    print("Starting overlay video rendering...")
    
    # 背景動画の読み込み
    if args.background:
        if not load_background_video(args.background):
            print("Failed to load background video")
            return
    
    # コンポジター設定
    setup_compositor_for_overlay()
    
    # レンダリング設定最適化
    optimize_render_settings(args.quality)
    
    # 出力パスの準備
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # レンダリング実行
    success = render_animation(args.output, args.start_frame, args.end_frame)
    
    if success:
        print(f"✅ Rendering completed: {args.output}")
        
        # 後処理
        if args.post_process and args.background:
            post_output = args.output.replace('.mp4', '_processed.mp4')
            if post_process_video(args.output, post_output, args.background):
                print(f"✅ Post-processing completed: {post_output}")
            else:
                print("⚠️  Post-processing failed, but render succeeded")
        
    else:
        print("❌ Rendering failed")
        sys.exit(1)


if __name__ == "__main__":
    main()