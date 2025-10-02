# MediaPipe インストールガイド

現在、Python 3.7環境でMediaPipeが利用できないため、モック実装を使用しています。
実際のポーズ検出を使用するには、以下の方法をお試しください。

## 🚀 推奨: Python環境のアップグレード

### Option 1: Python 3.8+ にアップグレード

```bash
# Python 3.8以上をインストール
# https://www.python.org/downloads/ からダウンロード

# 新しい環境でMediaPipeをインストール
pip install mediapipe>=0.8.6
pip install opencv-python numpy scipy pyyaml pytest
```

### Option 2: Anaconda/Miniconda環境の作成

```bash
# 新しいPython 3.8環境を作成
conda create -n javelin-analysis python=3.8 -y
conda activate javelin-analysis

# MediaPipeとその他の依存関係をインストール
pip install mediapipe>=0.8.6
pip install opencv-python numpy scipy pyyaml pytest
```

### Option 3: Docker環境の使用

```dockerfile
FROM python:3.8-slim

RUN pip install mediapipe>=0.8.6 opencv-python numpy scipy pyyaml pytest

WORKDIR /app
COPY . .

CMD ["python", "run.py", "--help"]
```

## 🔧 現在のモック実装について

現在のシステムは以下の機能を提供しています：

### ✅ 動作する機能
- **ダミー骨格点生成**: 33個のMediaPipe互換ランドマーク
- **全可視化機能**: ベクトル、ヒートマップ、HUD、軌跡
- **動作確認**: アプリケーションの全機能をテスト可能
- **設定システム**: CLI/YAML設定が完全動作

### ⚠️ 制限事項
- **実際のポーズ検出なし**: ダミーの動きのみ
- **精度なし**: 実際の人体検出は行われません

## 🧪 動作確認済みテスト

```bash
# 基本動作（モック骨格）
python run.py --video input.mp4 --output output.mp4

# 全機能デモ（モック骨格）
python run.py --video input.mp4 --output demo.mp4 \
  --vectors --heatmap --hud --wrist-trail --height-m 1.8

# 実際の投げ槍動画（モック骨格）
python run.py --video aisa_javelin1.mp4 --output result.mp4 \
  --vectors --heatmap --hud --wrist-trail --height-m 1.75
```

## 🔄 MediaPipe利用時の自動切り替え

実際のMediaPipeがインストールされた場合、システムは自動的に検出して切り替わります：

```python
# src/pipelines/pose_analysis.py で自動判定
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    from src.utils.mock_mediapipe import mp
    MEDIAPIPE_AVAILABLE = False
```

## 📞 サポート

MediaPipeのインストールでお困りの場合：
1. Python バージョンを確認: `python --version`
2. pip を最新に: `python -m pip install --upgrade pip`
3. 環境を新規作成してクリーンインストール
4. 必要に応じてDockerまたは仮想環境を使用

---

**🎯 現在のモック実装でも、システム全体の動作確認と可視化機能のデモが完全に可能です！**