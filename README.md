# Javelin Video Analysis

高度な可視化機能を備えたやり投げ動作解析システム。MediaPipeベースのポーズ解析に加え、ベクトル描画、ヒートマップ、ゲーム風HUD、Blender 3D連携を提供します。

## ✨ 新機能（v2.0）

- 🎯 **ベクトル描画**: 速度・加速度を矢印で可視化
- 🔥 **ヒートマップ**: 身体部位の速度を色分け表示
- 🎮 **ゲーム風HUD**: リアルタイムメトリクス表示
- ✨ **光軌跡エフェクト**: SNS映えする軌跡描画
- 🎭 **Blender 3D連携**: 3D人体モデルとの合成
- 🔧 **プラグイン方式**: 機能の個別ON/OFF可能
- 📐 **物理単位対応**: 身長設定で実測値表示

**すべての新機能はデフォルトOFFで、既存システムと完全互換です。**

## 🚀 クイックスタート

### 1. 動画ファイルの準備
```bash
# input/フォルダに解析したい動画ファイル(.mp4)を配置
cp your_video.mp4 input/
```

### 2. 基本解析の実行
```bash
# 最もシンプルな実行（input/から動画を自動選択、output/に結果を保存）
python run.py

# 可視化機能付きで実行
python run.py --vectors --heatmap --hud
```

### 3. 結果の確認
```bash
# output/フォルダに解析結果が保存されます
ls output/
```

**これだけです！** 詳細な設定は後述の使用方法をご覧ください。

## 🧪 最小SaaSデモ（FastAPI + S3直PUT）

前提: AWSクレデンシャルが環境に設定済み、`.env` に `AWS_REGION` と `JVA_BUCKET` を設定。

起動:

```bash
uvicorn server.app:app --reload --port 8000
```

エンドポイント:
- POST /v1/jobs: 事前署名URLを返す
- POST /v1/jobs/{id}/process: バックグラウンドで解析実行→S3に結果格納
- GET  /v1/jobs/{id}: ステータス取得

## Project Structure

```
javelin-video-analysis
├── input/                          # 📂 入力動画ファイル（.mp4）
├── output/                         # 📂 解析結果の出力先
├── src/
│   ├── app.py                      # Main entry point for the application
│   ├── pipelines/
│   │   ├── pose_analysis.py        # MediaPipeベースのポーズ解析
│   │   ├── speed_visualization.py  # Functions for visualizing speed with color ranges
│   │   ├── acceleration_heatmap.py # Calculates and visualizes acceleration heatmap
│   │   └── tip_tracking.py         # Implements javelin tip tracking
│   ├── tracking/
│   │   ├── marker_based.py         # Marker-based tracking functions
│   │   └── object_tracking.py      # Object tracking algorithms
│   ├── io/
│   │   ├── video_reader.py         # Functionality to read video files
│   │   └── video_writer.py         # Handles writing processed video files
│   ├── utils/
│   │   ├── geometry.py             # Utility functions for geometric calculations
│   │   ├── filters.py              # Functions for applying data filters
│   │   ├── color_maps.py           # Color mapping functions for visualization
│   │   └── visualization.py        # Functions for rendering visualizations
│   └── types/
│       └── __init__.py             # Custom types and data structures
├── jva_visuals/                    # 🎨 新しい可視化機能
│   ├── vectors.py                  # ベクトル描画
│   ├── heatmap.py                  # ヒートマップ
│   ├── hud.py                      # ゲーム風HUD
│   ├── trails.py                   # 軌跡エフェクト
│   └── ...
├── blender_bridge/                 # 🎭 Blender連携
│   ├── scripts/
│   │   ├── import_landmarks.py
│   │   ├── setup_scene.py
│   │   └── render_overlay.py
│   └── README.md
├── configs/
│   ├── default.yaml                # Default settings (input/output paths updated)
│   ├── color_ranges.yaml           # Fixed color ranges for speed visualization
│   └── tracking.yaml               # Settings for tracking algorithms
├── scripts/
│   ├── run_pipeline.py             # バッチ処理用スクリプト
│   └── export_metrics.py          # メトリクス出力
└── tests/
    ├── test_tip_tracking.py        # Unit tests for tip tracking functionality
    ├── test_speed_visualization.py # Unit tests for speed visualization
    └── test_acceleration_heatmap.py # Unit tests for acceleration heatmap
├── scripts
│   ├── run_pipeline.py             # Script to run the video analysis pipeline
│   └── export_metrics.py           # Script to export analysis metrics
├── requirements.txt                # Project dependencies
├── pyproject.toml                  # Project configuration
└── README.md                       # Project documentation
```

## 🚀 クイックスタート

### インストール

```bash
# リポジトリをクローン
git clone <repository-url>
cd javelin-video-analysis

# 依存関係をインストール
pip install -r requirements.txt
```

### 基本使用法（既存機能のみ）

```bash
# 基本の骨格表示（後方互換モード）
python run.py --video input.mp4 --output output.mp4
```

### 新機能を使用した解析

```bash
# ベクトルとヒートマップを追加
python run.py --video input.mp4 --output output.mp4 --vectors --heatmap

# 🚀 超簡単スタート（input/フォルダの動画を自動選択）
python run.py --vectors --heatmap --hud

# 🎬 一番のおすすめ！4つの可視化バリエーションを同時出力
python run.py --all-variants --height-m 1.80

# すべての可視化機能を有効化
python run.py --video input/javelin_video.mp4 --output output/analysis.mp4 \
  --vectors --heatmap --hud --wrist-trail --glow-trail \
  --height-m 1.80

# Blender 3D連携
python run.py --video input/javelin_video.mp4 --output output/analyzed.mp4 \
  --vectors --heatmap --export-landmarks output/landmarks.json --blender-overlay
```

### 設定ファイルを使用

```bash
# 設定例をコピー
cp configs/visuals.example.yaml configs/visuals.yaml

# 設定ファイルで実行
python run.py --config configs/visuals.yaml
```

## 📊 可視化機能詳細

### 🎬 マルチ出力機能 (`--all-variants`)
**一回の実行で4つの可視化バリエーションを同時出力！**

1. **骨格+軌跡** (`*_skeleton_with_trail.mp4`): 基本骨格 + 右手首軌跡
2. **ヒートマップ** (`*_heatmap.mp4`): 速度ヒートマップ重畳
3. **ゲーム風HUD** (`*_gaming_hud.mp4`): ゲーム的な表示
4. **Blender連携用** (`*_for_blender.mp4`): 3D合成用（ランドマーク付き）

```bash
# 一度の実行で4つ全て生成
python run.py --all-variants --height-m 1.80
```

### ベクトル描画 (`--vectors`)
- 速度: 緑の実線矢印
- 加速度: 赤の点線矢印
- EMA/Savitzky-Golay平滑化対応

### ヒートマップ (`--heatmap`)
- 身体部位の速度を色分け表示
- 動的スケール調整
- カラーバー付き

### ゲーム風HUD (`--hud`)
- リアルタイム速度・角速度表示
- リリース検知とフラッシュ効果
- 円形ゲージ

### 軌跡描画
- `--wrist-trail`: 通常の右手首軌跡
- `--glow-trail`: 光エフェクト付き軌跡

### Blender 3D連携 (`--blender-overlay`)
```bash
# 1. ランドマークデータを出力（input/フォルダから自動選択）
python run.py --export-landmarks output/landmarks.json

# 2. Blenderで3D合成（自動表示されるコマンドを使用）
blender --background --python blender_bridge/scripts/setup_scene.py -- \
  --video output/analysis_*.mp4 --landmarks output/landmarks.json --output output/3d_overlay.mp4
```

## ⚙️ 設定オプション

### CLIオプション
```bash
python run.py --help
```

### 設定ファイル（YAML）
詳細設定は `configs/visuals.example.yaml` を参照してください。

### 身長設定（物理単位）
```bash
--height-m 1.80  # 被写体の身長（メートル）
```
これにより速度が m/s 単位で表示されます。

## 🧪 テスト実行

```bash
# 全テスト実行
pytest tests/ -v

# 特定モジュールのテスト
pytest tests/test_kinematics.py -v

# カバレッジ付きテスト
pytest tests/ --cov=jva_visuals --cov-report=html
```

## 🏗️ プロジェクト構造

```
javelin-video-analysis/
├── jva_visuals/               # 🆕 可視化プラグインパッケージ
│   ├── __init__.py
│   ├── registry.py           # プラグイン管理
│   ├── adapters.py           # データ変換
│   ├── kinematics.py         # 運動学計算
│   ├── vectors.py            # ベクトル描画
│   ├── heatmap.py            # ヒートマップ
│   ├── hud.py                # ゲーム風HUD
│   └── trails.py             # 軌跡描画
├── blender_bridge/           # 🆕 Blender連携スクリプト
│   ├── scripts/
│   │   ├── setup_scene.py
│   │   ├── import_poses.py
│   │   └── render_overlay.py
│   └── templates/
├── run.py                    # 🔄 強化されたメインスクリプト
├── configs/
│   └── visuals.example.yaml  # 🆕 可視化設定例
└── tests/                    # 🆕 包括的テストスイート
    ├── test_kinematics.py
    ├── test_trails.py
    └── test_pipeline.py
```

## 📖 詳細ドキュメント

### API リファレンス
- [可視化プラグイン開発ガイド](docs/PLUGIN_DEVELOPMENT.md)
- [Blender連携チュートリアル](docs/BLENDER_INTEGRATION.md)
- [設定オプション完全リファレンス](docs/CONFIGURATION.md)

### 技術仕様
- **MediaPipe**: 骨格検出 v0.8.6+
- **OpenCV**: 映像処理 v4.5.0+
- **NumPy/SciPy**: 数値計算・信号処理
- **Python**: 3.8+ 対応

## 🤝 コントリビューション

プラグイン方式により新しい可視化機能を簡単に追加できます：

1. `jva_visuals/` に新しいパスクラスを作成
2. `VisualPassBase` を継承
3. `registry.py` に登録
4. テストを追加

詳細は [CONTRIBUTING.md](CONTRIBUTING.md) をご覧ください。

## 📄 ライセンス

MIT License - 詳細は [LICENSE](LICENSE) ファイルをご覧ください。

---

**🎯 投げ槍技術分析に特化した次世代ビデオ解析ツール**  
バイオメカニクス研究・コーチング・パフォーマンス向上に
