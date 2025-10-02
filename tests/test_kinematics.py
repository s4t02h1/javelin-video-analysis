"""
test_kinematics.py - 運動学計算モジュールのテスト
"""

import pytest
import numpy as np
import sys
from pathlib import Path

# テスト対象のインポートパスを追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from jva_visuals.kinematics import (
    finite_diff, apply_ema_filter, apply_savgol_filter,
    KinematicsBuffer, calculate_arm_vectors, calculate_body_segments_speed
)


class TestFiniteDiff:
    """有限差分のテスト"""
    
    def test_constant_velocity(self):
        """等速運動のテスト"""
        # 等速運動（速度=2.0）
        positions = np.array([0, 2, 4, 6, 8], dtype=float)
        dt = 1.0
        
        velocities = finite_diff(positions, dt)
        
        # 最初の要素は0、その後は一定速度
        expected = np.array([0, 2, 2, 2, 2])
        np.testing.assert_array_almost_equal(velocities, expected)
    
    def test_acceleration(self):
        """加速運動のテスト"""
        # 等加速度運動（x = 0.5 * a * t^2, a=2）
        t = np.array([0, 1, 2, 3, 4], dtype=float)
        positions = 0.5 * 2 * t**2  # [0, 1, 4, 9, 16]
        dt = 1.0
        
        velocities = finite_diff(positions, dt)
        accelerations = finite_diff(velocities, dt)
        
        # 加速度は一定（最初の2要素は0）
        assert accelerations[0] == 0  # 境界条件
        assert accelerations[1] == 0  # 境界条件
        np.testing.assert_array_almost_equal(accelerations[2:], [2, 2, 2])
    
    def test_2d_motion(self):
        """2次元運動のテスト"""
        # 円運動のような2D運動
        positions = np.array([
            [0, 1],
            [1, 0], 
            [0, -1],
            [-1, 0],
            [0, 1]
        ], dtype=float)
        dt = 1.0
        
        velocities = finite_diff(positions, dt)
        
        # 形状チェック
        assert velocities.shape == positions.shape
        
        # 最初の要素は0
        np.testing.assert_array_almost_equal(velocities[0], [0, 0])


class TestEMAFilter:
    """EMAフィルタのテスト"""
    
    def test_steady_state(self):
        """定常状態のテスト"""
        data = np.array([5.0, 5.0, 5.0, 5.0, 5.0])
        alpha = 0.3
        
        filtered = apply_ema_filter(data, alpha)
        
        # 定常状態では入力と同じ
        np.testing.assert_array_almost_equal(filtered, data)
    
    def test_step_response(self):
        """ステップ応答のテスト"""
        data = np.array([0.0, 1.0, 1.0, 1.0, 1.0])
        alpha = 0.5
        
        filtered = apply_ema_filter(data, alpha)
        
        # 最初の値は変わらない
        assert filtered[0] == 0.0
        
        # ステップ入力に対して徐々に応答
        assert 0 < filtered[1] < 1
        assert filtered[1] < filtered[2] < filtered[3]
    
    def test_alpha_bounds(self):
        """alpha値の境界テスト"""
        data = np.array([1.0, 2.0, 3.0])
        
        # alpha=0（完全平滑化）
        filtered_0 = apply_ema_filter(data, 0.0)
        assert filtered_0[1] == filtered_0[0]  # 前の値を保持
        
        # alpha=1（平滑化なし）
        filtered_1 = apply_ema_filter(data, 1.0)
        np.testing.assert_array_almost_equal(filtered_1, data)


class TestKinematicsBuffer:
    """運動学バッファのテスト"""
    
    def test_buffer_initialization(self):
        """バッファ初期化のテスト"""
        buffer = KinematicsBuffer(max_length=10)
        
        assert len(buffer.positions) == 0
        assert len(buffer.timestamps) == 0
        assert buffer.max_length == 10
    
    def test_add_frame(self):
        """フレーム追加のテスト"""
        buffer = KinematicsBuffer(max_length=3)
        
        # フレーム追加
        positions1 = np.random.rand(5, 2)
        buffer.add_frame(positions1, 0.0)
        
        assert len(buffer.positions) == 1
        assert len(buffer.timestamps) == 1
        np.testing.assert_array_equal(buffer.positions[0], positions1)
    
    def test_buffer_overflow(self):
        """バッファオーバーフローのテスト"""
        buffer = KinematicsBuffer(max_length=2)
        
        # 3つのフレームを追加（制限は2）
        for i in range(3):
            positions = np.ones((5, 2)) * i
            buffer.add_frame(positions, float(i))
        
        # 最新2つのみが保持される
        assert len(buffer.positions) == 2
        assert buffer.timestamps == [1.0, 2.0]
    
    def test_kinematics_calculation(self):
        """運動学計算のテスト"""
        buffer = KinematicsBuffer(smooth_method="ema", ema_alpha=1.0)  # 平滑化なし
        
        # 等速運動データを追加
        for i in range(5):
            positions = np.array([[i * 2.0, 0.0], [0.0, i * 1.0]])  # 2つの点
            buffer.add_frame(positions, float(i))
        
        kinematics = buffer.get_current_kinematics()
        
        # 速度チェック
        assert 'velocity' in kinematics
        assert 'speed' in kinematics
        assert 'acceleration' in kinematics
        
        # 形状チェック
        assert kinematics['velocity'].shape[1] == 2  # 2D速度
        assert len(kinematics['speed']) == len(kinematics['velocity'])


class TestArmVectors:
    """腕ベクトル計算のテスト"""
    
    def test_arm_vectors_calculation(self):
        """腕ベクトル計算のテスト"""
        # MediaPipeランドマーク形式のダミーデータ
        landmarks = np.zeros((33, 3))
        
        # 右腕の関節を設定（肩=12, 肘=14, 手首=16）
        landmarks[12] = [0.5, 0.3, 0.9]  # 右肩
        landmarks[14] = [0.4, 0.4, 0.8]  # 右肘
        landmarks[16] = [0.3, 0.5, 0.7]  # 右手首
        
        # 速度データ
        velocities = np.random.rand(33, 2) * 0.1  # 小さな速度
        
        arm_data = calculate_arm_vectors(landmarks, velocities, px2m=1.0)
        
        # 必要なキーが存在することを確認
        expected_keys = [
            'left_shoulder', 'left_elbow', 'left_wrist',
            'right_shoulder', 'right_elbow', 'right_wrist',
            'right_arm_angular_velocity'
        ]
        
        for key in expected_keys:
            assert key in arm_data
        
        # 右肩のデータが正しく設定されている
        right_shoulder = arm_data['right_shoulder']
        assert right_shoulder['position'] is not None
        assert len(right_shoulder['position']) == 2  # 2D座標
        assert 'velocity' in right_shoulder
        assert 'speed' in right_shoulder


class TestBodySegmentsSpeed:
    """身体部位速度計算のテスト"""
    
    def test_body_segments_calculation(self):
        """身体部位速度計算のテスト"""
        # ダミーランドマークデータ
        landmarks = np.random.rand(33, 3)
        landmarks[:, 2] = 0.8  # 信頼度を高く設定
        
        # ダミー速度データ
        velocities = np.random.rand(33, 2)
        
        segment_speeds = calculate_body_segments_speed(landmarks, velocities)
        
        # 期待される部位が含まれている
        expected_segments = [
            'head', 'torso', 'left_upper_arm', 'left_forearm',
            'right_upper_arm', 'right_forearm', 'left_thigh',
            'left_shin', 'right_thigh', 'right_shin'
        ]
        
        for segment in expected_segments:
            assert segment in segment_speeds
            assert isinstance(segment_speeds[segment], (int, float))
            assert segment_speeds[segment] >= 0  # 速度は非負


@pytest.fixture
def sample_motion_data():
    """サンプル運動データフィクスチャ"""
    # 5フレーム分の3つの点の運動データ
    frames = []
    for i in range(5):
        # 点1: 右方向等速運動
        # 点2: 上方向等速運動  
        # 点3: 円運動
        t = i * 0.1
        positions = np.array([
            [t * 10, 0.0],  # 等速直線運動
            [0.0, t * 5],   # 等速直線運動
            [np.cos(t), np.sin(t)]  # 円運動
        ])
        frames.append(positions)
    
    return frames, 0.1  # positions, dt


def test_integration_motion_analysis(sample_motion_data):
    """統合テスト: 運動解析の全体フロー"""
    positions_list, dt = sample_motion_data
    
    buffer = KinematicsBuffer(smooth_method="ema", ema_alpha=0.5)
    
    # データを順次追加
    for i, positions in enumerate(positions_list):
        buffer.add_frame(positions, i * dt)
    
    # 運動学データを取得
    kinematics = buffer.get_current_kinematics()
    
    # 基本チェック
    assert kinematics['velocity'].shape == (3, 2)
    assert len(kinematics['speed']) == 3
    assert kinematics['acceleration'].shape == (3, 2)
    
    # 等速運動の点1の速度がほぼ一定であることを確認
    speed_point1 = kinematics['speed'][0]
    expected_speed1 = 10.0 / 10  # 10 pixels per 0.1 seconds = 100 px/s → 10 px/frame
    
    # 速度の大まかな検証（平滑化により完全一致はしない）
    assert abs(speed_point1 - expected_speed1) < expected_speed1 * 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])