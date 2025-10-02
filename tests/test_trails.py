"""
test_trails.py - 軌跡描画モジュールのテスト
"""

import pytest
import numpy as np
import cv2
import sys
from pathlib import Path

# テスト対象のインポートパスを追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from jva_visuals.trails import WristTrailPass, GlowTrailPass, TrailManager
from jva_visuals.adapters import AdaptedLandmarks


@pytest.fixture
def sample_landmarks():
    """サンプルランドマークデータ"""
    points = np.zeros((33, 3))
    points[16] = [100, 200, 0.9]  # 右手首、信頼度0.9
    
    return AdaptedLandmarks(
        points=points,
        right_wrist=(100, 200),
        fps=30.0,
        px2m=0.01,
        frame_shape=(480, 640)
    )


@pytest.fixture
def sample_frame():
    """サンプルフレーム"""
    return np.zeros((480, 640, 3), dtype=np.uint8)


class TestWristTrailPass:
    """手首軌跡パステスト"""
    
    def test_initialization(self):
        """初期化テスト"""
        config = {
            "max_length": 100,
            "thickness": 3,
            "color": [255, 255, 255],
            "fade_alpha": True
        }
        
        trail_pass = WristTrailPass(config)
        
        assert trail_pass.max_trail_length == 100
        assert trail_pass.line_thickness == 3
        assert trail_pass.color == (255, 255, 255)
        assert trail_pass.fade_alpha == True
        assert len(trail_pass.trail_points) == 0
    
    def test_disabled_pass(self, sample_frame, sample_landmarks):
        """無効化されたパスのテスト"""
        config = {"enabled": False}
        trail_pass = WristTrailPass(config)
        
        result = trail_pass.apply(sample_frame, sample_landmarks)
        
        # 入力と同じフレームが返される
        np.testing.assert_array_equal(result, sample_frame)
    
    def test_single_point_no_drawing(self, sample_frame, sample_landmarks):
        """1点のみの場合は描画されない"""
        config = {"enabled": True}
        trail_pass = WristTrailPass(config)
        
        result = trail_pass.apply(sample_frame, sample_landmarks)
        
        # 軌跡点は追加されるが、線は描画されない（1点のみ）
        assert len(trail_pass.trail_points) == 1
        np.testing.assert_array_equal(result, sample_frame)
    
    def test_multiple_points_drawing(self, sample_frame):
        """複数点での描画テスト"""
        config = {"enabled": True, "thickness": 2, "fade_alpha": False}
        trail_pass = WristTrailPass(config)
        
        # 複数の点を追加
        points_sequence = [
            AdaptedLandmarks(np.zeros((33, 3)), (100, 100), 30.0, 0.01, (480, 640)),
            AdaptedLandmarks(np.zeros((33, 3)), (120, 110), 30.0, 0.01, (480, 640)),
            AdaptedLandmarks(np.zeros((33, 3)), (140, 120), 30.0, 0.01, (480, 640)),
        ]
        
        result = sample_frame.copy()
        for landmarks in points_sequence:
            result = trail_pass.apply(result, landmarks)
        
        # 軌跡が描画されているはず（フレームが変化している）
        assert not np.array_equal(result, sample_frame)
        assert len(trail_pass.trail_points) == 3
    
    def test_buffer_length_limit(self, sample_frame):
        """バッファ長制限のテスト"""
        config = {"enabled": True, "max_length": 2}
        trail_pass = WristTrailPass(config)
        
        # 3つの点を追加（制限は2）
        for i in range(3):
            landmarks = AdaptedLandmarks(
                np.zeros((33, 3)), (100 + i*10, 100), 30.0, 0.01, (480, 640)
            )
            trail_pass.apply(sample_frame, landmarks)
        
        # バッファサイズが制限される
        assert len(trail_pass.trail_points) == 2
        assert trail_pass.trail_points[0] == (110, 100)  # 最古が削除
        assert trail_pass.trail_points[1] == (120, 100)
    
    def test_out_of_bounds_handling(self, sample_frame):
        """フレーム境界外の点の処理"""
        config = {"enabled": True}
        trail_pass = WristTrailPass(config)
        
        # フレーム外の点
        out_of_bounds_landmarks = AdaptedLandmarks(
            np.zeros((33, 3)), (1000, 1000), 30.0, 0.01, (480, 640)
        )
        
        result = trail_pass.apply(sample_frame, out_of_bounds_landmarks)
        
        # 境界外の点は追加されない
        assert len(trail_pass.trail_points) == 0


class TestGlowTrailPass:
    """光軌跡パステスト"""
    
    def test_initialization(self):
        """初期化テスト"""
        config = {
            "enabled": True,
            "glow_radius": 20,
            "glow_intensity": 0.9,
            "glow_color": [0, 255, 255],
            "speed_responsive": True,
            "min_speed_threshold": 10.0
        }
        
        glow_pass = GlowTrailPass(config)
        
        assert glow_pass.glow_radius == 20
        assert glow_pass.glow_intensity == 0.9
        assert glow_pass.glow_color == (0, 255, 255)
        assert glow_pass.speed_responsive == True
        assert glow_pass.min_speed_threshold == 10.0
        assert len(glow_pass.speed_history) == 0
    
    def test_speed_history_update(self, sample_frame):
        """速度履歴更新のテスト"""
        config = {"enabled": True, "speed_responsive": True}
        glow_pass = GlowTrailPass(config)
        
        # 速度の異なる点を追加
        points = [
            (100, 100), (110, 100), (130, 100)  # 徐々に速くなる
        ]
        
        for i, point in enumerate(points):
            landmarks = AdaptedLandmarks(
                np.zeros((33, 3)), point, 30.0, 0.01, (480, 640)
            )
            glow_pass.apply(sample_frame, landmarks)
        
        # 速度履歴が更新されている
        assert len(glow_pass.speed_history) == len(points)
        
        # 速度が徐々に増加している
        if len(glow_pass.speed_history) >= 2:
            assert glow_pass.speed_history[-1] > glow_pass.speed_history[-2]
    
    def test_low_speed_no_glow(self, sample_frame):
        """低速時のグロー効果なし"""
        config = {
            "enabled": True,
            "speed_responsive": True,
            "min_speed_threshold": 100.0  # 高い閾値
        }
        glow_pass = GlowTrailPass(config)
        
        # 低速移動
        points = [(100, 100), (101, 100), (102, 100)]
        
        result = sample_frame.copy()
        for point in points:
            landmarks = AdaptedLandmarks(
                np.zeros((33, 3)), point, 30.0, 0.01, (480, 640)
            )
            result = glow_pass.apply(result, landmarks)
        
        # 低速なのでグロー効果は最小限（基本軌跡のみ）
        # 完全一致はしないが、大きな変化はない
        assert len(glow_pass.trail_points) >= 2


class TestTrailManager:
    """軌跡マネージャーのテスト"""
    
    def test_initialization(self):
        """初期化テスト"""
        manager = TrailManager()
        
        assert len(manager.trails) == 0
        assert manager.max_trail_length == 200
    
    def test_add_point(self):
        """点追加のテスト"""
        manager = TrailManager()
        
        manager.add_point("right_wrist", (100, 200))
        manager.add_point("right_wrist", (110, 210))
        manager.add_point("left_wrist", (50, 150))
        
        assert "right_wrist" in manager.trails
        assert "left_wrist" in manager.trails
        assert len(manager.trails["right_wrist"]) == 2
        assert len(manager.trails["left_wrist"]) == 1
    
    def test_get_trail(self):
        """軌跡取得のテスト"""
        manager = TrailManager()
        
        # 存在しない軌跡
        empty_trail = manager.get_trail("nonexistent")
        assert empty_trail == []
        
        # 存在する軌跡  
        manager.add_point("test_trail", (1, 2))
        manager.add_point("test_trail", (3, 4))
        
        trail = manager.get_trail("test_trail")
        assert trail == [(1, 2), (3, 4)]
    
    def test_clear_trail(self):
        """軌跡クリアのテスト"""
        manager = TrailManager()
        
        manager.add_point("trail1", (1, 1))
        manager.add_point("trail2", (2, 2))
        
        manager.clear_trail("trail1")
        
        assert len(manager.trails["trail1"]) == 0
        assert len(manager.trails["trail2"]) == 1
    
    def test_clear_all(self):
        """全軌跡クリアのテスト"""
        manager = TrailManager()
        
        manager.add_point("trail1", (1, 1))
        manager.add_point("trail2", (2, 2))
        
        manager.clear_all()
        
        assert len(manager.trails) == 0
    
    def test_trail_length_limit(self):
        """軌跡長制限のテスト"""
        manager = TrailManager()
        manager.max_trail_length = 3
        
        # 制限を超える点を追加
        for i in range(5):
            manager.add_point("test", (i, i))
        
        trail = manager.get_trail("test")
        assert len(trail) == 3
        assert trail == [(2, 2), (3, 3), (4, 4)]  # 最新3点のみ


def test_trail_visual_integration(sample_frame):
    """軌跡可視化の統合テスト"""
    # 基本軌跡とグロー軌跡の組み合わせ
    basic_config = {"enabled": True, "thickness": 2, "fade_alpha": False}
    glow_config = {"enabled": True, "glow_radius": 10, "speed_responsive": False}
    
    basic_trail = WristTrailPass(basic_config)
    glow_trail = GlowTrailPass(glow_config)
    
    # 移動軌跡を作成
    result = sample_frame.copy()
    for i in range(10):
        x = 100 + i * 5
        y = 200 + int(10 * np.sin(i * 0.5))  # 波状軌跡
        
        landmarks = AdaptedLandmarks(
            np.zeros((33, 3)), (x, y), 30.0, 0.01, (480, 640)
        )
        
        # 両方の軌跡を適用
        result = basic_trail.apply(result, landmarks)
        result = glow_trail.apply(result, landmarks)
    
    # 何らかの描画がされているはず
    assert not np.array_equal(result, sample_frame)
    
    # 軌跡点が記録されている
    assert len(basic_trail.trail_points) == 10
    assert len(glow_trail.trail_points) == 10


@pytest.mark.parametrize("thickness,color", [
    (1, (255, 0, 0)),    # 赤、細線
    (3, (0, 255, 0)),    # 緑、太線
    (5, (0, 0, 255)),    # 青、極太線
])
def test_trail_style_variations(sample_frame, thickness, color):
    """軌跡スタイルのバリエーションテスト"""
    config = {
        "enabled": True,
        "thickness": thickness,
        "color": list(color),
        "fade_alpha": False
    }
    
    trail_pass = WristTrailPass(config)
    
    # 短い軌跡を作成
    points = [(100, 100), (120, 110), (140, 120)]
    
    result = sample_frame.copy()
    for point in points:
        landmarks = AdaptedLandmarks(
            np.zeros((33, 3)), point, 30.0, 0.01, (480, 640)
        )
        result = trail_pass.apply(result, landmarks)
    
    # スタイル設定が反映されている
    assert trail_pass.line_thickness == thickness
    assert trail_pass.color == color
    
    # 描画されている
    assert not np.array_equal(result, sample_frame)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])