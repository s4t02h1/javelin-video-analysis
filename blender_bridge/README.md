# Blender Bridge - 3D Human Model Integration

このディレクトリには、MediaPipeで検出したポーズランドマークをBlenderの3D人体モデルに適用し、元動画に重ね合わせるためのスクリプトが格納されています。

## 概要

Python側（javelin-video-analysis）で抽出したポーズデータを使って、Blenderで3D人体モデルをアニメーションさせ、元動画と合成することで教育的価値の高い解析動画を作成します。

## ファイル構成

```
blender_bridge/
├── scripts/
│   ├── import_landmarks.py     # ランドマークデータの読み込みと変換
│   ├── setup_scene.py          # Blenderシーンの設定とレンダリング
│   └── render_overlay.py       # オーバーレイ動画の生成
└── README.md                   # このファイル
```

## 使用方法

### 1. ランドマークデータの準備

まず、Python側でランドマークデータを出力します：

```bash
# input/フォルダの動画を自動選択し、output/フォルダに出力
python run.py --export-landmarks output/landmarks.json

# または明示的にファイルを指定
python run.py --video input/javelin_video.mp4 --output output/analyzed.mp4 --export-landmarks output/landmarks.json
```

### 2. Blenderでの3D合成

バックグラウンドモードでBlenderを実行：

```bash
blender --background --python scripts/setup_scene.py -- \
  --video output/analyzed.mp4 \
  --landmarks output/landmarks.json \
  --output output/overlay_3d.mp4
```

既存のBlenderファイルを使用する場合：

```bash
blender your_scene.blend --python scripts/setup_scene.py -- \
  --video analyzed.mp4 \
  --landmarks landmarks.json \
  --output overlay_3d.mp4
```

### 3. 高品質レンダリング

レンダリング品質とオプションを指定：

```bash
blender --background --python scripts/setup_scene.py -- \
  --video analyzed.mp4 \
  --landmarks landmarks.json \
  --output overlay_3d.mp4 \
  --quality HIGH \
  --transparent \
  --lighting \
  --camera-tracking
```

## パラメータ

- `--video`: 背景となる元動画ファイル
- `--landmarks`: ランドマークJSONファイル
- `--output`: 出力動画ファイル
- `--quality`: レンダリング品質（LOW/MEDIUM/HIGH）
- `--transparent`: 3Dモデルを半透明にする
- `--lighting`: 動的ライティングを適用
- `--camera-tracking`: カメラトラッキングを有効化

## 要件

- Blender 3.0以上
- 十分な計算リソース（特にGPUレンダリング時）
- FFmpeg（動画出力用）

## カスタマイズ

### 3D人体モデルの変更

`setup_scene.py` の `HUMAN_MODEL_PATH` を変更することで、異なる3D人体モデルを使用できます：

```python
HUMAN_MODEL_PATH = "path/to/your/human_model.blend"
```

### マテリアルとライティング

`setup_scene.py` 内の `setup_materials()` 関数で、3Dモデルの外観を調整できます。

### アニメーション平滑化

ランドマークデータにノイズが多い場合、`import_landmarks.py` でEMAフィルタのパラメータを調整してください：

```python
EMA_ALPHA = 0.2  # より滑らかなアニメーション
```

## トラブルシューティング

### 一般的な問題

1. **Blenderが見つからない**
   - Blenderのパスが正しく設定されているか確認
   - 環境変数 `PATH` にBlenderを追加

2. **メモリ不足**
   - レンダリング品質を `LOW` に変更
   - フレーム数を制限（テスト用に短い動画を使用）

3. **ランドマーク座標の不正確さ**
   - MediaPipeの検出信頼度を確認
   - カメラキャリブレーションデータがあれば適用

### パフォーマンス最適化

- GPU レンダリングを有効化（CUDA/OpenCL）
- 不要なライティング効果を無効化
- フレームスキップオプションを使用

## 例: 投てき解析での使用

やり投げの技術解析では以下の設定が推奨されます：

```bash
# 高品質な解析動画を生成
blender --background --python scripts/setup_scene.py -- \
  --video javelin_throw.mp4 \
  --landmarks javelin_landmarks.json \
  --output javelin_analysis_3d.mp4 \
  --quality HIGH \
  --transparent \
  --lighting \
  --camera-tracking \
  --focus-joints shoulder,elbow,wrist
```

これにより、投てき動作の3D解析動画が生成され、技術指導や研究に活用できます。

## 重要な注意事項

### Blender環境での実行

このディレクトリのスクリプトは **Blender内部でのみ実行可能** です。通常のPython環境では以下のエラーが発生します：

```
Warning: Blender modules not available. Script will only work within Blender.
RuntimeError: Blender modules are not available. This script must be run within Blender.
```

### 依存関係

- **NumPy**: ランドマーク処理に必要（`pip install numpy`）
- **Blender 3.0+**: bpy, bmesh, mathutilsモジュールが必要
- **MediaPipe**: ランドマークデータの生成に必要

### ファイル構造の維持

スクリプト間の相対インポートが正常に動作するよう、以下のディレクトリ構造を維持してください：

```
blender_bridge/
└── scripts/
    ├── import_landmarks.py
    ├── setup_scene.py
    └── render_overlay.py
```

## 開発者向け情報

これらのスクリプトはBlender外部でのテストや静的解析のため、条件付きインポート機能を実装しています。開発時にはPylanceやその他のリンターで問題が表示される場合がありますが、Blender内では正常に動作します。