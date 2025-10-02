"""
test_pipeline_visuals.py - 可視化パイプライン統合テスト

実際の動画処理フローをテストし、各可視化機能が正常に動作することを確認する。
"""

import pytest
import numpy as np
import cv2
import tempfile
import os
import sys
from pathlib import Path

# テスト対象のインポートパスを追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from jva_visuals.registry import VisualPassRegistry, VisualPipeline
from jva_visuals.adapters import AdaptedLandmarks, adapt_state
from jva_visuals.trails import WristTrailPass
from jva_visuals.vectors import VectorPass
from jva_visuals.heatmap import HeatmapPass
from jva_visuals.hud import HUDPass

try:
    from src.pipelines.pose_analysis import PoseAnalyzer
    POSE_ANALYZER_AVAILABLE = True
except ImportError:
    POSE_ANALYZER_AVAILABLE = False


def create_dummy_video(filepath: str, width: int = 640, height: int = 480, 
                      fps: float = 30.0, duration_sec: float = 2.0):
    """テスト用ダミー動画を生成"""
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filepath, fourcc, fps, (width, height))
    
    total_frames = int(fps * duration_sec)
    
    for frame_idx in range(total_frames):
        # 黒背景
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # 白い円が右に移動
        t = frame_idx / total_frames
        center_x = int(50 + t * (width - 100))
        center_y = height // 2
        
        cv2.circle(frame, (center_x, center_y), 20, (255, 255, 255), -1)
        
        # フレーム番号を表示
        cv2.putText(frame, f"Frame {frame_idx}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        out.write(frame)
    
    out.release()
    return total_frames


def create_dummy_pose_state(frame_idx: int, total_frames: int):
    """ダミーのポーズ状態を生成"""
    # 移動する人物のダミーランドマーク
    t = frame_idx / total_frames
    base_x = 50 + t * 540  # 左から右へ移動
    base_y = 240
    
    # 33個のMediaPipeランドマーク
    points = [None] * 33
    
    # 主要な点を設定
    points[0] = (base_x, base_y - 100)  # 鼻
    points[11] = (base_x - 20, base_y - 50)  # 左肩
    points[12] = (base_x + 20, base_y - 50)  # 右肩
    points[13] = (base_x - 30, base_y - 20)  # 左肘
    points[14] = (base_x + 30, base_y - 20)  # 右肘
    points[15] = (base_x - 40, base_y + 10)  # 左手首
    points[16] = (base_x + 40, base_y + 10)  # 右手首（動的）
    points[23] = (base_x - 10, base_y + 20)  # 左腰
    points[24] = (base_x + 10, base_y + 20)  # 右腰
    points[25] = (base_x - 15, base_y + 80)  # 左膝
    points[26] = (base_x + 15, base_y + 80)  # 右膝
    points[27] = (base_x - 20, base_y + 140)  # 左足首
    points[28] = (base_x + 20, base_y + 140)  # 右足首
    
    # 右手首に動的な動きを追加（やり投げの動作風）
    if points[16]:
        swing_amplitude = 30 * np.sin(t * np.pi * 4)  # 振り動作
        points[16] = (points[16][0] + swing_amplitude, points[16][1])
    
    return {
        "points": points,
        "com": (base_x, base_y),  # 重心
        "velocities": np.random.rand(33) * 5  # ダミー速度
    }


@pytest.fixture
def temp_video():
    """一時的なテスト動画ファイル"""
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
        video_path = tmp.name
    
    try:
        total_frames = create_dummy_video(video_path, duration_sec=1.0)
        yield video_path, total_frames
    finally:
        if os.path.exists(video_path):
            os.unlink(video_path)


@pytest.fixture
def sample_visuals_config():
    """サンプル可視化設定"""
    return {
        "wrist_trail": True,
        "wrist_trail_cfg": {
            "max_length": 50,
            "thickness": 2,
            "color": [255, 255, 255]
        },
        "vectors": True,
        "vectors_cfg": {
            "scale": 0.5,
            "show_velocity": True,
            "target_joints": [11, 12, 15, 16]
        },
        "heatmap": True,
        "heatmap_cfg": {
            "radius": 20,
            "alpha": 0.3
        },
        "hud": True,
        "hud_cfg": {
            "show_metrics": True,
            "show_gauges": False  # ゲージは重いのでテストでは無効化
        }
    }


class TestVisualPassRegistry:
    """可視化パスレジストリのテスト"""
    
    def test_empty_config(self):
        """空設定のテスト"""
        passes = VisualPassRegistry.build_from_config({})
        assert len(passes) == 0
    
    def test_single_pass_creation(self):
        """単一パス作成のテスト"""
        config = {
            "wrist_trail": True,
            "wrist_trail_cfg": {"thickness": 3}
        }
        
        passes = VisualPassRegistry.build_from_config(config)
        
        assert len(passes) == 1
        assert isinstance(passes[0], WristTrailPass)
        assert passes[0].line_thickness == 3
    
    def test_multiple_passes_creation(self, sample_visuals_config):
        """複数パス作成のテスト"""
        passes = VisualPassRegistry.build_from_config(sample_visuals_config)
        
        # 有効化された4つのパスが作成される
        assert len(passes) == 4
        
        # 順序確認（registry.pyのpass_orderに従う）
        pass_types = [type(p).__name__ for p in passes]
        expected_order = ['WristTrailPass', 'VectorPass', 'HeatmapPass', 'HUDPass']
        assert pass_types == expected_order
    
    def test_disabled_pass_exclusion(self):
        """無効化されたパスが除外されることのテスト"""
        config = {
            "wrist_trail": True,
            "vectors": False,  # 無効化
            "heatmap": True
        }
        
        passes = VisualPassRegistry.build_from_config(config)
        
        # vectorsは除外される
        assert len(passes) == 2
        pass_types = [type(p).__name__ for p in passes]
        assert 'VectorPass' not in pass_types
        assert 'WristTrailPass' in pass_types
        assert 'HeatmapPass' in pass_types


class TestVisualPipeline:
    """可視化パイプラインのテスト"""
    
    def test_empty_pipeline(self):
        """空パイプラインのテスト"""
        pipeline = VisualPipeline([])
        
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        state = create_dummy_pose_state(0, 1)
        
        result = pipeline.apply_all(frame, state)
        
        # 何も変更されない
        np.testing.assert_array_equal(result, frame)
    
    def test_single_pass_pipeline(self):
        """単一パスパイプラインのテスト"""
        config = {"thickness": 2, "color": [255, 0, 0]}
        trail_pass = WristTrailPass(config)
        pipeline = VisualPipeline([trail_pass])
        
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # 複数フレームを処理して軌跡を作成
        for i in range(5):
            state = create_dummy_pose_state(i, 5)
            result = pipeline.apply_all(frame, state, fps=30.0)
            frame = result  # 次のフレームに引き継ぎ
        
        # 軌跡が描画されているはず
        assert not np.array_equal(result, np.zeros((480, 640, 3), dtype=np.uint8))
    
    def test_multi_pass_pipeline(self, sample_visuals_config):
        """複数パスパイプラインのテスト"""
        passes = VisualPassRegistry.build_from_config(sample_visuals_config)
        pipeline = VisualPipeline(passes)
        
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # 複数フレームを処理
        results = []
        for i in range(10):
            state = create_dummy_pose_state(i, 10)
            result = pipeline.apply_all(frame, state, fps=30.0, height_m=1.8)
            results.append(result)
        
        # 最終結果が元フレームと異なる（何らかの可視化が適用された）
        final_result = results[-1]
        assert not np.array_equal(final_result, np.zeros((480, 640, 3), dtype=np.uint8))
        
        # フレーム間で差がある（動的な可視化）
        assert not np.array_equal(results[0], results[-1])
    
    def test_error_handling(self):
        """エラーハンドリングのテスト"""
        # 意図的にエラーを起こすダミーパス
        class ErrorPass:
            def __init__(self):
                self.enabled = True
            
            def is_enabled(self):
                return True
            
            def apply(self, frame, landmarks):
                raise ValueError("Test error")
        
        pipeline = VisualPipeline([ErrorPass()])
        
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        state = create_dummy_pose_state(0, 1)
        
        # エラーが発生してもクラッシュしない
        result = pipeline.apply_all(frame, state)
        
        # 元のフレームが返される
        np.testing.assert_array_equal(result, frame)


class TestAdaptersIntegration:
    """アダプタ統合テスト"""
    
    def test_state_adaptation(self):
        """状態変換のテスト"""
        state = create_dummy_pose_state(5, 10)
        
        landmarks = adapt_state(state, fps=30.0, height_m=1.8, frame_shape=(480, 640))
        
        assert isinstance(landmarks, AdaptedLandmarks)
        assert landmarks.fps == 30.0
        assert landmarks.frame_shape == (480, 640)
        assert landmarks.points.shape == (33, 3)
        assert landmarks.right_wrist is not None
        assert landmarks.px2m > 0  # 物理スケールが設定される
    
    def test_physical_scale_calculation(self):
        """物理スケール計算のテスト"""
        state = create_dummy_pose_state(0, 1)
        
        # 身長指定あり
        landmarks_with_height = adapt_state(state, height_m=1.8)
        
        # 身長指定なし
        landmarks_without_height = adapt_state(state)
        
        # px2mが異なるはず
        assert landmarks_with_height.px2m < landmarks_without_height.px2m


@pytest.mark.skipif(not POSE_ANALYZER_AVAILABLE, 
                   reason="PoseAnalyzer not available")
class TestFullPipelineIntegration:
    """完全なパイプライン統合テスト"""
    
    def test_video_processing_flow(self, temp_video, sample_visuals_config):
        """動画処理フロー全体のテスト"""
        video_path, total_frames = temp_video
        
        # 可視化パイプライン構築
        passes = VisualPassRegistry.build_from_config(sample_visuals_config, fps=30.0)
        pipeline = VisualPipeline(passes)
        
        # 動画読み込み
        cap = cv2.VideoCapture(video_path)
        assert cap.isOpened()
        
        # 一時出力ファイル
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            output_path = tmp.name
        
        try:
            # 出力動画設定
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
            
            # フレーム処理
            frame_count = 0
            pose_analyzer = PoseAnalyzer()
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # ポーズ解析（実際のMediaPipe）
                state = pose_analyzer.process(frame, fps)
                
                # 基本描画
                result = pose_analyzer.render_basic(frame, state)
                
                # 可視化適用
                result = pipeline.apply_all(result, state, fps=fps, height_m=1.8)
                
                out.write(result)
                frame_count += 1
            
            cap.release()
            out.release()
            pose_analyzer.close()
            
            # 出力ファイルが作成されていることを確認
            assert os.path.exists(output_path)
            assert os.path.getsize(output_path) > 0
            
            # 出力動画が読み込める
            test_cap = cv2.VideoCapture(output_path)
            assert test_cap.isOpened()
            
            ret, test_frame = test_cap.read()
            assert ret
            assert test_frame is not None
            
            test_cap.release()
            
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)


def test_performance_benchmark():
    """パフォーマンステスト"""
    import time
    
    # 大きなフレームでのパフォーマンステスト
    config = {
        "wrist_trail": True,
        "vectors": True,
        "heatmap": True
    }
    
    passes = VisualPassRegistry.build_from_config(config)
    pipeline = VisualPipeline(passes)
    
    # 高解像度フレーム
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    state = create_dummy_pose_state(0, 1)
    
    # 処理時間測定
    start_time = time.time()
    
    for i in range(10):  # 10フレーム処理
        result = pipeline.apply_all(frame, state, fps=30.0)
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    # 1フレームあたりの処理時間
    time_per_frame = processing_time / 10
    
    print(f"Performance: {time_per_frame:.4f}s per frame")
    
    # リアルタイム処理可能かの簡易チェック（30FPS想定）
    real_time_threshold = 1.0 / 30.0  # 33ms
    if time_per_frame < real_time_threshold:
        print("✅ Real-time processing capable")
    else:
        print("⚠️  Processing slower than real-time")
    
    # とりあえず10秒以内に完了すれば合格
    assert processing_time < 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])