# Javelin Video Analysis

> **本リポジトリは、やり投げ動作解析プロジェクトの公開デモ版です。**  
> β版サービスで使用しているレポート生成、ユーザー管理、納品フロー、独自解析ロジック等は別リポジトリで管理しています。

MediaPipe ベースのポーズ推定を使ったやり投げ動作解析・可視化ツールキットです。  
速度ヒートマップ、ベクトルオーバーレイ、ゲーム風HUD、Blender 3D 連携など、複数の可視化プラグインを提供します。

---

## ⚠️ 免責事項

本ツールが出力する数値・グラフは、動画から自動推定した**参考値**です。

- 医療診断・怪我の診断・専門的競技指導を代替するものではありません
- 動画の画質・撮影角度・服装・背景によって精度が変わります
- 出力結果の利用は自己責任でお願いします

---

## ✨ 機能一覧

| 機能 | 説明 |
|---|---|
| 🦴 **ポーズ推定** | MediaPipe で骨格を自動検出 |
| 🎯 **先端トラッキング** | カラーマーカーでやり先端を追跡 |
| ⚡ **速度可視化** | 部位ごとの速度を色分けして表示 |
| 🔥 **加速度ヒートマップ** | 加速度を身体上に重畳 |
| ➡️ **ベクトル描画** | 速度・加速度を矢印で可視化 |
| 🎮 **ゲーム風HUD** | リアルタイム速度・角速度・ゲージ表示 |
| ✨ **光軌跡エフェクト** | 手首/やり先端の軌跡をグロー描画 |
| 🎭 **Blender 3D 連携** | 3D 人体モデルとの合成 |
| 🔧 **プラグイン方式** | 機能の個別 ON/OFF が可能 |

---

## 🚀 クイックスタート

### 1. インストール

```bash
# リポジトリをクローン
git clone https://github.com/YOUR_USERNAME/javelin-video-analysis.git
cd javelin-video-analysis

# 依存関係をインストール
pip install -r requirements.txt
```

MediaPipe のインストールで問題が起きた場合は [MEDIAPIPE_INSTALL_GUIDE.md](MEDIAPIPE_INSTALL_GUIDE.md) を参照してください。

### 2. テスト動画の生成

```bash
# サンプル動画を生成（実際の動画がない場合）
python create_test_video.py
```

### 3. 基本解析の実行

```bash
# 最小構成で実行（input/ フォルダの動画を自動選択）
python run.py

# 可視化オプション付き
python run.py --vectors --heatmap --hud

# 4バリエーション同時出力（推奨）
python run.py --all-variants --height-m 1.80
```

### 4. 結果の確認

```bash
ls output/
# 出力例:
# sample_skeleton_with_trail.mp4
# sample_heatmap.mp4
# sample_gaming_hud.mp4
# sample_for_blender.mp4
# landmarks.json
```

---

## 📋 CLI オプション

```
python run.py --help

オプション:
  --input PATH          入力動画ファイルパス（省略時は input/ を自動選択）
  --output-dir PATH     出力ディレクトリ（デフォルト: output/）
  --height-m FLOAT      被写体の身長（m）— 物理単位の速度表示に使用
  --vectors             速度・加速度ベクトルを描画
  --heatmap             速度ヒートマップを描画
  --hud                 ゲーム風 HUD を表示
  --wrist-trail         手首軌跡を描画
  --glow-trail          グロー（光）軌跡を描画
  --blender-overlay     Blender 連携用フォーマットで出力
  --export-landmarks    ランドマーク JSON を出力
  --all-variants        全バリエーションを同時出力
  --config PATH         YAML 設定ファイルを指定
```

---

## 🔥 可視化機能の詳細

### 4バリエーション同時出力 (`--all-variants`)

1. **骨格+軌跡** (`*_skeleton_with_trail.mp4`) — 基本骨格 + 手首軌跡
2. **ヒートマップ** (`*_heatmap.mp4`) — 速度ヒートマップ重畳
3. **ゲーム風HUD** (`*_gaming_hud.mp4`) — ゲーム的な速度・ゲージ表示
4. **Blender 連携用** (`*_for_blender.mp4`) — 3D 合成用（ランドマーク付き）

### ベクトル描画 (`--vectors`)

- 速度: 緑の実線矢印
- 加速度: 赤の点線矢印
- EMA / Savitzky-Golay 平滑化対応

### 速度ヒートマップ (`--heatmap`)

- 身体部位の速度を色（青→緑→赤）で表示
- 動的スケール調整、カラーバー付き

### ゲーム風HUD (`--hud`)

- リアルタイム速度・角速度メトリクス
- リリース検知とフラッシュ効果
- 円形ゲージ

### Blender 3D 連携 (`--blender-overlay`)

```bash
# 1. ランドマークデータを出力
python run.py --export-landmarks output/landmarks.json

# 2. Blender で 3D 合成
blender --background --python blender_bridge/scripts/setup_scene.py -- \
  --video output/analysis.mp4 --landmarks output/landmarks.json \
  --output output/3d_overlay.mp4
```

詳細は [docs/BLENDER_INTEGRATION.md](docs/BLENDER_INTEGRATION.md) を参照してください。

---

## ⚙️ 設定ファイル

```bash
# 設定テンプレートをコピーして編集
cp configs/visuals.example.yaml configs/visuals.yaml
python run.py --config configs/visuals.yaml
```

主な設定項目（`configs/visuals.example.yaml` 参照）:

| セクション | 設定例 |
|---|---|
| `vectors.scale` | 矢印の長さスケール |
| `heatmap.colormap` | カラーマップ名（`jet`, `plasma` 等） |
| `hud.font_scale` | HUD 文字サイズ |
| `trails.length` | 軌跡の表示フレーム数 |

設定オプションの全リストは [docs/CONFIGURATION.md](docs/CONFIGURATION.md) を参照してください。

---

## 🧪 テスト実行

```bash
# 全テスト実行
python -m pytest tests/ -v

# カバレッジ付き
python -m pytest tests/ --cov=jva_visuals --cov-report=html

# 特定テストのみ
python -m pytest tests/test_kinematics.py -v
```

---

## 📁 プロジェクト構造（公開デモ版）

```
javelin-video-analysis/
├── src/
│   ├── app.py                       # 基本エントリーポイント
│   ├── pipelines/
│   │   ├── pose_analysis.py         # MediaPipe ポーズ解析
│   │   ├── speed_visualization.py   # 速度可視化
│   │   ├── acceleration_heatmap.py  # 加速度ヒートマップ
│   │   └── tip_tracking.py          # やり先端トラッキング
│   ├── tracking/
│   │   ├── marker_based.py          # カラーマーカートラッキング
│   │   └── object_tracking.py       # オブジェクトトラッキング
│   ├── io/
│   │   ├── video_reader.py          # 動画読み込み
│   │   └── video_writer.py          # 動画書き出し
│   ├── utils/
│   │   ├── geometry.py              # 幾何計算
│   │   ├── filters.py               # データフィルタ（EMA, Savitzky-Golay）
│   │   ├── color_maps.py            # カラーマッピング
│   │   └── visualization.py         # 描画ユーティリティ
│   └── types/
│       └── __init__.py              # 型定義
├── jva_visuals/                     # 可視化プラグインパッケージ
│   ├── __init__.py
│   ├── registry.py                  # プラグイン管理
│   ├── adapters.py                  # データ変換アダプター
│   ├── kinematics.py                # 運動学計算
│   ├── vectors.py                   # ベクトル描画
│   ├── heatmap.py                   # ヒートマップ
│   ├── hud.py                       # ゲーム風HUD
│   ├── trails.py                    # 軌跡エフェクト
│   └── stickman.py                  # スティックマン描画
├── blender_bridge/                  # Blender 3D 連携
│   ├── scripts/
│   └── README.md
├── configs/
│   ├── default.yaml                 # 基本設定
│   ├── color_ranges.yaml            # カラーレンジ定義
│   ├── tracking.yaml                # トラッキング設定
│   └── visuals.example.yaml         # 可視化設定サンプル
├── scripts/
│   ├── run_pipeline.py              # バッチ処理スクリプト
│   └── export_metrics.py            # メトリクス出力
├── tests/
│   ├── test_tip_tracking.py
│   ├── test_speed_visualization.py
│   ├── test_acceleration_heatmap.py
│   ├── test_trails.py
│   ├── test_pipeline_visuals.py
│   └── test_kinematics.py
├── run.py                           # メイン実行スクリプト
├── create_test_video.py             # テスト動画生成
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 📚 ドキュメント

- [プラグイン開発ガイド](docs/PLUGIN_DEVELOPMENT.md) — 独自可視化プラグインの作り方
- [Blender 連携ガイド](docs/BLENDER_INTEGRATION.md) — 3D 合成のセットアップ
- [設定リファレンス](docs/CONFIGURATION.md) — 全設定オプション
- [Colab デモ](docs/colab_snippet.md) — Google Colab でのサンプル実行

---

## 🛠️ 技術スタック

| ライブラリ | 用途 |
|---|---|
| MediaPipe ≥ 0.8.6 | 骨格検出（33 ランドマーク） |
| OpenCV ≥ 4.5.0 | 映像処理・描画 |
| NumPy | 数値計算 |
| SciPy | 信号処理（Savitzky-Golay フィルタ） |
| Matplotlib / Seaborn | グラフ描画 |
| Python ≥ 3.10 | 実行環境 |

---

## 🤝 コントリビュート

Issue・Pull Request を歓迎します。  
詳細は [CONTRIBUTING.md](CONTRIBUTING.md) および [行動規範](CODE_OF_CONDUCT.md) をご覧ください。

---

## 📄 ライセンス

[MIT License](LICENSE)

---

## 🔗 関連リンク

- [MediaPipe](https://mediapipe.dev/) — Google の姿勢推定ライブラリ
- [Blender](https://www.blender.org/) — 3D 合成に使用
- [やり投げ（Wikipedia）](https://ja.wikipedia.org/wiki/%E3%82%84%E3%82%8A%E6%8A%95%E3%81%92)

---

> **Note**: β版サービスで使用しているレポート生成・ユーザー管理・納品フロー・独自解析ロジック・管理画面・S3 連携・課金処理等は、本リポジトリには含まれていません。
