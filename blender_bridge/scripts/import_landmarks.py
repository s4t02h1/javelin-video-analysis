"""
import_landmarks.py - MediaPipeランドマークデータの読み込みとBlenderへの適用

JSONファイルからランドマークデータを読み込み、Blenderの3D人体モデルに適用する。
"""

import json
import argparse
import sys
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

# Blender特有のモジュールを条件付きでインポート
try:
    import bpy
    import bmesh
    import mathutils
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False
    print("Warning: Blender modules not available. Script will only work within Blender.")
    # 型ヒント用のダミー型を定義
    if TYPE_CHECKING:
        import bpy  # type: ignore
        import mathutils  # type: ignore

# NumPy のインポート
try:
    import numpy as np
except ImportError:
    print("Error: NumPy is required. Please install with: pip install numpy")
    sys.exit(1)


# MediaPipeポーズランドマークのインデックスマッピング
MEDIAPIPE_POSE_INDICES = {
    # 顔・頭部
    'nose': 0,
    'left_eye_inner': 1, 'left_eye': 2, 'left_eye_outer': 3,
    'right_eye_inner': 4, 'right_eye': 5, 'right_eye_outer': 6,
    'left_ear': 7, 'right_ear': 8,
    'mouth_left': 9, 'mouth_right': 10,
    
    # 上半身
    'left_shoulder': 11, 'right_shoulder': 12,
    'left_elbow': 13, 'right_elbow': 14,
    'left_wrist': 15, 'right_wrist': 16,
    
    # 手
    'left_pinky': 17, 'right_pinky': 18,
    'left_index': 19, 'right_index': 20,
    'left_thumb': 21, 'right_thumb': 22,
    
    # 下半身
    'left_hip': 23, 'right_hip': 24,
    'left_knee': 25, 'right_knee': 26,
    'left_ankle': 27, 'right_ankle': 28,
    
    # 足
    'left_heel': 29, 'right_heel': 30,
    'left_foot_index': 31, 'right_foot_index': 32
}


# Blenderボーンとの対応マッピング（Rigifyアーマチュアを想定）
BONE_MAPPING = {
    # 脊椎・体幹
    'spine': ['left_shoulder', 'right_shoulder', 'left_hip', 'right_hip'],
    'spine.001': ['left_shoulder', 'right_shoulder'],
    'spine.002': ['left_shoulder', 'right_shoulder'],
    'spine.003': ['left_shoulder', 'right_shoulder'],
    
    # 頭・首
    'neck': ['nose', 'left_ear', 'right_ear'],
    'head': ['nose'],
    
    # 左腕
    'shoulder.L': ['left_shoulder'],
    'upper_arm.L': ['left_shoulder', 'left_elbow'],
    'forearm.L': ['left_elbow', 'left_wrist'],
    'hand.L': ['left_wrist'],
    
    # 右腕
    'shoulder.R': ['right_shoulder'],
    'upper_arm.R': ['right_shoulder', 'right_elbow'],
    'forearm.R': ['right_elbow', 'right_wrist'],
    'hand.R': ['right_wrist'],
    
    # 左脚
    'thigh.L': ['left_hip', 'left_knee'],
    'shin.L': ['left_knee', 'left_ankle'],
    'foot.L': ['left_ankle', 'left_foot_index'],
    
    # 右脚
    'thigh.R': ['right_hip', 'right_knee'],
    'shin.R': ['right_knee', 'right_ankle'],
    'foot.R': ['right_ankle', 'right_foot_index'],
}


class LandmarkImporter:
    """ランドマークデータをBlenderにインポートするクラス"""
    
    def __init__(self, ema_alpha: float = 0.3):
        if not BLENDER_AVAILABLE:
            raise RuntimeError("Blender modules are not available. This script must be run within Blender.")
        
        self.ema_alpha = ema_alpha
        self.armature_obj = None
        self.previous_rotations = {}
        
    def load_landmarks_json(self, filepath: str) -> Dict:
        """JSONファイルからランドマークデータを読み込み"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"Loaded landmarks from {filepath}")
            print(f"Format: {data.get('format', 'unknown')}")
            print(f"Frame count: {data.get('frame_count', 0)}")
            
            return data
        except Exception as e:
            print(f"Error loading landmarks: {e}")
            return {}
    
    def find_or_create_armature(self, name: str = "Human") -> Optional['bpy.types.Object']:
        """アーマチュアオブジェクトを検索または作成"""
        # 既存のアーマチュアを検索
        for obj in bpy.context.scene.objects:
            if obj.type == 'ARMATURE':
                self.armature_obj = obj
                print(f"Found armature: {obj.name}")
                return obj
        
        # アーマチュアが見つからない場合は基本的なものを作成
        bpy.ops.object.armature_add(location=(0, 0, 0))
        self.armature_obj = bpy.context.active_object
        self.armature_obj.name = name
        
        print(f"Created new armature: {name}")
        return self.armature_obj
    
    def normalize_landmarks(self, landmarks: List[Dict]) -> np.ndarray:
        """ランドマークデータを正規化（0-1座標を-1〜1に変換）"""
        points = np.zeros((len(MEDIAPIPE_POSE_INDICES), 3))
        
        for landmark in landmarks:
            idx = landmark.get('id', 0)
            if idx < len(points):
                # MediaPipeの正規化座標をBlender座標系に変換
                x = (landmark.get('x', 0.5) - 0.5) * 2.0  # -1 to 1
                y = -(landmark.get('y', 0.5) - 0.5) * 2.0  # Y軸反転
                z = 0.0  # 2D→3D変換時はZ=0
                visibility = landmark.get('visibility', 0.0)
                
                if visibility > 0.5:  # 十分な信頼度がある場合のみ
                    points[idx] = [x, y, z]
        
        return points
    
    def calculate_bone_rotation(self, start_point: np.ndarray, end_point: np.ndarray) -> 'mathutils.Euler':
        """2点間からボーンの回転を計算"""
        if np.allclose(start_point, 0) or np.allclose(end_point, 0):
            return mathutils.Euler((0, 0, 0), 'XYZ')
        
        # 方向ベクトル
        direction = mathutils.Vector(end_point - start_point)
        direction.normalize()
        
        # デフォルトのボーン方向（Y軸正方向）
        default_direction = mathutils.Vector((0, 1, 0))
        
        # 回転計算
        rotation_matrix = default_direction.rotation_difference(direction).to_matrix().to_4x4()
        euler = rotation_matrix.to_euler('XYZ')
        
        return euler
    
    def apply_ema_smoothing(self, bone_name: str, rotation: 'mathutils.Euler') -> 'mathutils.Euler':
        """EMAフィルタで回転を平滑化"""
        if bone_name not in self.previous_rotations:
            self.previous_rotations[bone_name] = rotation
            return rotation
        
        prev_rot = self.previous_rotations[bone_name]
        
        # EMAフィルタ適用
        smoothed_x = self.ema_alpha * rotation.x + (1 - self.ema_alpha) * prev_rot.x
        smoothed_y = self.ema_alpha * rotation.y + (1 - self.ema_alpha) * prev_rot.y
        smoothed_z = self.ema_alpha * rotation.z + (1 - self.ema_alpha) * prev_rot.z
        
        smoothed_rotation = mathutils.Euler((smoothed_x, smoothed_y, smoothed_z), 'XYZ')
        self.previous_rotations[bone_name] = smoothed_rotation
        
        return smoothed_rotation
    
    def apply_landmarks_to_frame(self, landmarks_data: List[Dict], frame_number: int):
        """1フレーム分のランドマークをアーマチュアに適用"""
        if not self.armature_obj or not landmarks_data:
            return
        
        # ポーズモードに切り替え
        bpy.context.view_layer.objects.active = self.armature_obj
        bpy.ops.object.mode_set(mode='POSE')
        
        # ランドマーク座標を正規化
        points = self.normalize_landmarks(landmarks_data)
        
        # 各ボーンに回転を適用
        for bone_name, landmark_names in BONE_MAPPING.items():
            if bone_name not in self.armature_obj.pose.bones:
                continue
            
            pose_bone = self.armature_obj.pose.bones[bone_name]
            
            # ランドマークからボーン回転を計算
            if len(landmark_names) >= 2:
                start_idx = MEDIAPIPE_POSE_INDICES.get(landmark_names[0], 0)
                end_idx = MEDIAPIPE_POSE_INDICES.get(landmark_names[1], 0)
                
                start_point = points[start_idx]
                end_point = points[end_idx]
                
                # 回転計算
                rotation = self.calculate_bone_rotation(start_point, end_point)
                
                # 平滑化適用
                smoothed_rotation = self.apply_ema_smoothing(bone_name, rotation)
                
                # ボーンに回転を適用
                pose_bone.rotation_euler = smoothed_rotation
                
                # キーフレーム設定
                pose_bone.keyframe_insert(data_path="rotation_euler", frame=frame_number)
    
    def import_animation(self, landmarks_json_path: str, start_frame: int = 1):
        """ランドマークデータからアニメーションを作成"""
        # データ読み込み
        data = self.load_landmarks_json(landmarks_json_path)
        if not data or 'landmarks' not in data:
            print("No landmark data found")
            return
        
        # アーマチュア準備
        if not self.find_or_create_armature():
            print("Failed to set up armature")
            return
        
        # アニメーション作成
        landmarks_list = data['landmarks']
        total_frames = len(landmarks_list)
        
        print(f"Creating animation for {total_frames} frames...")
        
        for i, frame_data in enumerate(landmarks_list):
            frame_number = start_frame + i
            frame_landmarks = frame_data.get('landmarks', [])
            
            self.apply_landmarks_to_frame(frame_landmarks, frame_number)
            
            # プログレス表示
            if i % 30 == 0:  # 1秒ごと
                progress = (i / total_frames) * 100
                print(f"Progress: {progress:.1f}% (frame {frame_number})")
        
        # アニメーション範囲を設定
        bpy.context.scene.frame_start = start_frame
        bpy.context.scene.frame_end = start_frame + total_frames - 1
        
        print(f"Animation import completed: {total_frames} frames")


def main():
    """メイン関数（Blenderスクリプトとして実行）"""
    # コマンドライン引数の解析
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    
    parser = argparse.ArgumentParser(description="Import MediaPipe landmarks to Blender")
    parser.add_argument("--landmarks", required=True, help="Landmarks JSON file path")
    parser.add_argument("--ema-alpha", type=float, default=0.3, help="EMA smoothing factor")
    parser.add_argument("--start-frame", type=int, default=1, help="Start frame number")
    
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print("Usage: blender --python import_landmarks.py -- --landmarks landmarks.json")
        return
    
    # インポート実行
    importer = LandmarkImporter(ema_alpha=args.ema_alpha)
    importer.import_animation(args.landmarks, args.start_frame)
    
    print("Landmark import completed successfully!")


if __name__ == "__main__":
    main()