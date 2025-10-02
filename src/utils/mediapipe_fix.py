"""
MediaPipe DLL問題回避とデバッグユーティリティ
"""

import sys
import os


def _in_virtualenv() -> bool:
    # 仮想環境判定: venv/virtualenv
    return getattr(sys, 'real_prefix', None) is not None or sys.prefix != getattr(sys, 'base_prefix', sys.prefix)


def fix_mediapipe_dll_issues():
    """MediaPipeのDLL読み込み問題を修正する試み。

    原則: まずは仮想環境や通常環境を汚染しない。必要時のみAnaconda DLLを追加。
    制御環境変数:
      - JVA_DISABLE_CONDA_DLLS=1 -> 常に無効化
      - JVA_FORCE_CONDA_DLLS=1   -> 仮想環境でも強制有効化
      - JVA_ANACONDA_PATH        -> 既定のAnacondaパスを上書き
    """
    try:
        if os.environ.get('JVA_DISABLE_CONDA_DLLS', '0') == '1':
            # 明示的に無効化
            return False

        in_venv = _in_virtualenv()
        force = os.environ.get('JVA_FORCE_CONDA_DLLS', '0') == '1'
        if in_venv and not force:
            # venv内ではDLLパスを追加しない（衝突回避）
            return False

        # Anaconda環境のDLLパスを追加（必要時のみ）
        anaconda_path = os.environ.get('JVA_ANACONDA_PATH', r"C:\Users\user\anaconda3")
        dll_paths = [
            os.path.join(anaconda_path, "Library", "bin"),
            os.path.join(anaconda_path, "DLLs"),
            os.path.join(anaconda_path, "Library", "mingw-w64", "bin"),
            os.path.join(anaconda_path, "Scripts"),
        ]

        for path in dll_paths:
            if os.path.exists(path) and path not in os.environ.get('PATH', ''):
                os.environ['PATH'] = path + os.pathsep + os.environ.get('PATH', '')
                print(f"Added to PATH: {path}")

        # DLL検索パスを追加（Windows 10/11）
        if hasattr(os, 'add_dll_directory'):
            for path in dll_paths:
                if os.path.exists(path):
                    try:
                        os.add_dll_directory(path)
                        print(f"Added DLL directory: {path}")
                    except (OSError, AttributeError):
                        pass

        return True
    except Exception as e:
        print(f"DLL path fix failed: {e}")
        return False


def test_mediapipe_import():
    """MediaPipeのインポートをテスト"""
    try:
        print("Testing MediaPipe import...")
        
        # DLL問題の修正を試行
        fix_mediapipe_dll_issues()
        
        # MediaPipeのインポートを試行
        import mediapipe as mp
        print(f"✅ MediaPipe imported successfully! Version: {mp.__version__}")
        
        # ポーズソリューションのテスト
        pose = mp.solutions.pose.Pose()
        print("✅ MediaPipe Pose initialized successfully!")
        pose.close()
        
        return True, mp
        
    except ImportError as e:
        print(f"❌ MediaPipe import failed: {e}")
        return False, None
    except Exception as e:
        print(f"❌ MediaPipe initialization failed: {e}")
        return False, None


if __name__ == "__main__":
    success, mp_module = test_mediapipe_import()
    if success:
        print("\n🎉 MediaPipe is ready to use!")
    else:
        print("\n⚠️ MediaPipe not available, will use mock implementation")