"""
setup_scene.py - Blenderシーンの設定とレンダリング

ランドマークデータを使って3D人体モデルをアニメーションさせ、
背景動画と合成してオーバーレイ動画を生成する。
"""

import os
import sys
import argparse
from pathlib import Path

# Blender特有のモジュールを条件付きでインポート
try:
    import bpy
    import bmesh
    import mathutils
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False
    print("Warning: Blender modules not available. Script will only work within Blender.")

# 相対インポート
sys.path.append(os.path.dirname(__file__))
try:
    from import_landmarks import LandmarkImporter
except ImportError as e:
    print(f"Error importing LandmarkImporter: {e}")
    LandmarkImporter = None


def clear_scene():
    """シーンを初期化"""
    # すべてのオブジェクトを削除
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    
    # すべてのメッシュデータを削除
    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)
    
    # すべてのマテリアルを削除
    for material in bpy.data.materials:
        bpy.data.materials.remove(material)


def create_human_model():
    """基本的な人体モデルを作成"""
    # メタリグを追加（Rigifyアドオンが有効な場合）
    try:
        bpy.ops.object.armature_add(location=(0, 0, 0))
        armature = bpy.context.active_object
        armature.name = "Human_Armature"
        
        # ボーンを編集モードで調整
        bpy.ops.object.mode_set(mode='EDIT')
        
        # 基本的なボーン構造を作成
        edit_bones = armature.data.edit_bones
        
        # 既存のボーンをクリア
        edit_bones.clear()
        
        # 基本ボーン構造
        bone_structure = {
            'spine': (0, 0, 0.5),
            'spine.001': (0, 0, 0.8),
            'spine.002': (0, 0, 1.1),
            'neck': (0, 0, 1.4),
            'head': (0, 0, 1.6),
            
            # 右腕
            'shoulder.R': (-0.2, 0, 1.3),
            'upper_arm.R': (-0.4, 0, 1.2),
            'forearm.R': (-0.6, 0, 1.0),
            'hand.R': (-0.8, 0, 1.0),
            
            # 左腕
            'shoulder.L': (0.2, 0, 1.3),
            'upper_arm.L': (0.4, 0, 1.2),
            'forearm.L': (0.6, 0, 1.0),
            'hand.L': (0.8, 0, 1.0),
            
            # 右脚
            'thigh.R': (-0.1, 0, 0.5),
            'shin.R': (-0.1, 0, 0.25),
            'foot.R': (-0.1, 0.1, 0),
            
            # 左脚
            'thigh.L': (0.1, 0, 0.5),
            'shin.L': (0.1, 0, 0.25),
            'foot.L': (0.1, 0.1, 0),
        }
        
        # ボーンを作成
        bones = {}
        for bone_name, position in bone_structure.items():
            bone = edit_bones.new(bone_name)
            bone.head = position
            bone.tail = (position[0], position[1], position[2] + 0.1)
            bones[bone_name] = bone
        
        # ボーンの親子関係を設定
        bone_hierarchy = {
            'spine.001': 'spine',
            'spine.002': 'spine.001',
            'neck': 'spine.002',
            'head': 'neck',
            
            'shoulder.R': 'spine.002',
            'upper_arm.R': 'shoulder.R',
            'forearm.R': 'upper_arm.R',
            'hand.R': 'forearm.R',
            
            'shoulder.L': 'spine.002',
            'upper_arm.L': 'shoulder.L',
            'forearm.L': 'upper_arm.L',
            'hand.L': 'forearm.L',
            
            'thigh.R': 'spine',
            'shin.R': 'thigh.R',
            'foot.R': 'shin.R',
            
            'thigh.L': 'spine',
            'shin.L': 'thigh.L',
            'foot.L': 'shin.L',
        }
        
        for child, parent in bone_hierarchy.items():
            if child in bones and parent in bones:
                bones[child].parent = bones[parent]
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # 人体メッシュを作成（簡単な円柱ベース）
        create_simple_human_mesh(armature)
        
        return armature
        
    except Exception as e:
        print(f"Error creating human model: {e}")
        return None


def create_simple_human_mesh(armature):
    """簡単な人体メッシュを作成"""
    # 体幹
    bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=0.6, location=(0, 0, 0.8))
    torso = bpy.context.active_object
    torso.name = "Torso"
    
    # 頭
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, location=(0, 0, 1.5))
    head = bpy.context.active_object
    head.name = "Head"
    
    # 腕（右）
    bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=0.3, location=(-0.3, 0, 1.15))
    right_upper_arm = bpy.context.active_object
    right_upper_arm.name = "RightUpperArm"
    right_upper_arm.rotation_euler = (0, 0, -0.5)
    
    bpy.ops.mesh.primitive_cylinder_add(radius=0.035, depth=0.25, location=(-0.5, 0, 1.05))
    right_forearm = bpy.context.active_object
    right_forearm.name = "RightForearm"
    right_forearm.rotation_euler = (0, 0, -0.3)
    
    # 腕（左）
    bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=0.3, location=(0.3, 0, 1.15))
    left_upper_arm = bpy.context.active_object
    left_upper_arm.name = "LeftUpperArm"
    left_upper_arm.rotation_euler = (0, 0, 0.5)
    
    bpy.ops.mesh.primitive_cylinder_add(radius=0.035, depth=0.25, location=(0.5, 0, 1.05))
    left_forearm = bpy.context.active_object
    left_forearm.name = "LeftForearm"
    left_forearm.rotation_euler = (0, 0, 0.3)
    
    # 脚（右）
    bpy.ops.mesh.primitive_cylinder_add(radius=0.06, depth=0.4, location=(-0.08, 0, 0.35))
    right_thigh = bpy.context.active_object
    right_thigh.name = "RightThigh"
    
    bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.35, location=(-0.08, 0, 0.12))
    right_shin = bpy.context.active_object
    right_shin.name = "RightShin"
    
    # 脚（左）
    bpy.ops.mesh.primitive_cylinder_add(radius=0.06, depth=0.4, location=(0.08, 0, 0.35))
    left_thigh = bpy.context.active_object
    left_thigh.name = "LeftThigh"
    
    bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.35, location=(0.08, 0, 0.12))
    left_shin = bpy.context.active_object
    left_shin.name = "LeftShin"
    
    # すべてのメッシュを選択してアーマチュアに関連付け
    mesh_objects = [torso, head, right_upper_arm, right_forearm, left_upper_arm, left_forearm, 
                   right_thigh, right_shin, left_thigh, left_shin]
    
    for mesh_obj in mesh_objects:
        # アーマチュアモディファイアを追加
        modifier = mesh_obj.modifiers.new(name="Armature", type='ARMATURE')
        modifier.object = armature


def setup_materials(transparent=True):
    """マテリアルを設定"""
    # 人体用マテリアル
    human_material = bpy.data.materials.new(name="HumanMaterial")
    human_material.use_nodes = True
    
    # ノードを設定
    nodes = human_material.node_tree.nodes
    nodes.clear()
    
    # 基本ノード
    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    output = nodes.new(type='ShaderNodeOutputMaterial')
    
    # マテリアル設定
    if transparent:
        bsdf.inputs['Base Color'].default_value = (0.8, 0.6, 0.4, 0.7)  # 肌色、半透明
        bsdf.inputs['Alpha'].default_value = 0.7
        human_material.blend_method = 'BLEND'
    else:
        bsdf.inputs['Base Color'].default_value = (0.8, 0.6, 0.4, 1.0)  # 肌色
    
    bsdf.inputs['Roughness'].default_value = 0.8
    bsdf.inputs['Specular'].default_value = 0.3
    
    # ノードを接続
    human_material.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    
    # すべての人体メッシュにマテリアルを適用
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj.name.startswith(('Torso', 'Head', 'Right', 'Left')):
            if obj.data.materials:
                obj.data.materials[0] = human_material
            else:
                obj.data.materials.append(human_material)


def setup_lighting():
    """ライティングを設定"""
    # 既存のライトを削除
    for obj in bpy.context.scene.objects:
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj, do_unlink=True)
    
    # メインライト（キーライト）
    bpy.ops.object.light_add(type='SUN', location=(2, -2, 3))
    key_light = bpy.context.active_object
    key_light.name = "KeyLight"
    key_light.data.energy = 3.0
    key_light.data.color = (1.0, 0.95, 0.9)  # 暖色
    
    # フィルライト
    bpy.ops.object.light_add(type='AREA', location=(-1, 2, 2))
    fill_light = bpy.context.active_object
    fill_light.name = "FillLight"
    fill_light.data.energy = 1.5
    fill_light.data.color = (0.9, 0.9, 1.0)  # 寒色
    fill_light.data.size = 2.0


def setup_camera_and_background(video_path=None):
    """カメラと背景を設定"""
    # カメラ設定
    bpy.ops.object.camera_add(location=(3, -3, 1.5))
    camera = bpy.context.active_object
    camera.name = "MainCamera"
    
    # カメラを人体モデルに向ける
    constraint = camera.constraints.new(type='TRACK_TO')
    
    # 背景動画の設定
    if video_path and os.path.exists(video_path):
        # Compositor用の設定
        bpy.context.scene.use_nodes = True
        tree = bpy.context.scene.node_tree
        
        # 既存ノードをクリア
        for node in tree.nodes:
            tree.nodes.remove(node)
        
        # レンダーレイヤー
        render_layers = tree.nodes.new(type='CompositorNodeRLayers')
        
        # 動画入力
        movie_clip = tree.nodes.new(type='CompositorNodeMovieClip')
        # 実際の動画ファイルを読み込み（Blender内で行う）
        
        # アルファオーバー（合成）
        alpha_over = tree.nodes.new(type='CompositorNodeAlphaOver')
        
        # 出力
        composite = tree.nodes.new(type='CompositorNodeComposite')
        
        # ノード接続
        tree.links.new(movie_clip.outputs['Image'], alpha_over.inputs[1])  # 背景
        tree.links.new(render_layers.outputs['Image'], alpha_over.inputs[2])  # 3Dレンダー
        tree.links.new(alpha_over.outputs['Image'], composite.inputs['Image'])


def setup_render_settings(quality='MEDIUM', output_path='output.mp4'):
    """レンダリング設定"""
    scene = bpy.context.scene
    render = scene.render
    
    # 解像度設定
    if quality == 'LOW':
        render.resolution_x = 640
        render.resolution_y = 480
        render.resolution_percentage = 50
    elif quality == 'HIGH':
        render.resolution_x = 1920
        render.resolution_y = 1080
        render.resolution_percentage = 100
    else:  # MEDIUM
        render.resolution_x = 1280
        render.resolution_y = 720
        render.resolution_percentage = 75
    
    # 動画出力設定
    render.image_settings.file_format = 'FFMPEG'
    render.ffmpeg.format = 'MPEG4'
    render.ffmpeg.codec = 'H264'
    render.ffmpeg.constant_rate_factor = 'MEDIUM'
    
    # 出力パス
    render.filepath = output_path
    
    # フレーム設定
    scene.frame_start = 1
    scene.frame_step = 1
    
    # エンジン設定
    render.engine = 'EEVEE'  # 高速レンダリング
    
    # EEVEE設定
    eevee = scene.eevee
    eevee.use_bloom = True
    eevee.use_ssr = True  # スクリーンスペース反射
    eevee.use_motion_blur = True


def main():
    """メイン処理"""
    # Blender環境チェック
    if not BLENDER_AVAILABLE:
        print("Error: This script must be run within Blender.")
        print("Usage: blender --python setup_scene.py -- --landmarks landmarks.json")
        return
    
    # コマンドライン引数の解析
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    
    parser = argparse.ArgumentParser(description="Setup Blender scene for human pose overlay")
    parser.add_argument("--video", help="Background video file")
    parser.add_argument("--landmarks", required=True, help="Landmarks JSON file")
    parser.add_argument("--output", default="output.mp4", help="Output video file")
    parser.add_argument("--quality", choices=['LOW', 'MEDIUM', 'HIGH'], default='MEDIUM')
    parser.add_argument("--transparent", action='store_true', help="Make 3D model transparent")
    parser.add_argument("--lighting", action='store_true', help="Enable dynamic lighting")
    parser.add_argument("--camera-tracking", action='store_true', help="Enable camera tracking")
    
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print("Usage: blender --python setup_scene.py -- --landmarks landmarks.json")
        return
    
    print("Setting up Blender scene...")
    
    # シーン初期化
    clear_scene()
    
    # 人体モデル作成
    armature = create_human_model()
    if not armature:
        print("Failed to create human model")
        return
    
    # マテリアル設定
    setup_materials(transparent=args.transparent)
    
    # ライティング設定
    if args.lighting:
        setup_lighting()
    
    # カメラと背景設定
    setup_camera_and_background(args.video)
    
    # レンダリング設定
    setup_render_settings(args.quality, args.output)
    
    # ランドマークアニメーション適用
    print("Importing landmark animation...")
    if LandmarkImporter is None:
        print("Error: LandmarkImporter not available.")
        return
    
    importer = LandmarkImporter()
    importer.armature_obj = armature
    importer.import_animation(args.landmarks)
    
    print("Scene setup completed!")
    print(f"Ready to render: {args.output}")
    print("To render animation, run: bpy.ops.render.render(animation=True)")
    
    # 自動レンダリング（オプション）
    if len(argv) > 0 and "--render" in argv:
        print("Starting render...")
        bpy.ops.render.render(animation=True)
        print("Render completed!")


if __name__ == "__main__":
    main()