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

### 4バリアント同時出力（おすすめ）

```bash
python run.py --all-variants --height-m 1.80
```

出力例:
- skeleton_with_trail.mp4
- heatmap.mp4
- gaming_hud.mp4
- for_blender.mp4 + landmarks.json

## 📚 Docs
- Colab: docs/colab_snippet.md
- S3 CORS: docs/s3_cors.json

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

### 基本使用法（標準形式）

```bash
# 標準形式（推奨）
python run.py --input input/sample.mp4 --output-dir output --all-variants --height-m 1.80

# 後方互換: --video / --output も引き続き使用可能
python run.py --video input/sample.mp4 --output output/analysis.mp4 --all-variants
```

### 新機能を使用した解析

```bash
# ベクトルとヒートマップを追加
python run.py --input input/sample.mp4 --output-dir output --vectors --heatmap

# 🚀 超簡単スタート（input/フォルダの動画を自動選択）
python run.py --vectors --heatmap --hud

# 🎬 一番のおすすめ！4つの可視化バリエーションを同時出力
python run.py --all-variants --height-m 1.80

# すべての可視化機能を有効化
python run.py --input input/javelin_video.mp4 --output-dir output \
  --vectors --heatmap --hud --wrist-trail --glow-trail \
  --height-m 1.80

# Blender 3D連携
python run.py --input input/javelin_video.mp4 --output-dir output \
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

## � 成果物ファイルの種類

解析ジョブは `jobs/<job_id>/report/` に以下のファイルを生成します。

| ファイル | 用途 | 対象 |
|---|---|---|
| `report.pdf` | 全指標を収録した詳細レポート | 管理者・上級者 |
| `video_instruction.pdf` | 各解析動画の見方を説明 | 全ユーザー |
| `athlete_data_sheet.pdf` | 主要指標をまとめた選手向けサマリー | **アスリート** |
| `key_frame_sheet.pdf` | フェーズ別代表フレーム一覧 | **アスリート** |
| `graph_pack.pdf` | 解析グラフを解説付きでまとめたパック | **アスリート** |
| `coach_review_sheet.pdf` | フェーズ別チェックリスト＆記入欄 | **コーチ** |
| `pose_landmarks.csv` | 全フレームの姿勢推定生データ | 開発者・研究者 |

> **Note**: `pose_landmarks.csv` は生データです。一般のアスリート向けには `athlete_data_sheet.pdf` をご使用ください。

### 納品ZIPパッケージの構成

| パッケージ | 含まれるファイル |
|---|---|
| `free_preview.zip` | プレビュー動画 + 代表フレーム先頭3枚 + 動画説明書 |
| `data_sheet_package.zip` | 全動画 + 全フレーム + アスリート向けPDF3種 + Raw Data CSV |
| `full_report_package.zip` | 上記すべて + 詳細レポート + コーチレビューシート + グラフ画像 + 生データJSON |

---

## �📖 詳細ドキュメント

### API リファレンス
- [可視化プラグイン開発ガイド](docs/PLUGIN_DEVELOPMENT.md)
- [Blender連携チュートリアル](docs/BLENDER_INTEGRATION.md)
- [設定オプション完全リファレンス](docs/CONFIGURATION.md)

### 技術仕様
- **MediaPipe**: 骨格検出 v0.8.6+
- **OpenCV**: 映像処理 v4.5.0+
- **NumPy/SciPy**: 数値計算・信号処理
- **Python**: 3.8+ 対応

## 🌐 Tailscale Serveで外出先から管理画面にアクセスする

同一Wi-Fi内だけでなく、外出先からも `admin_app.py` を安全に使いたい場合は、Tailscale Serve を使うと Tailnet 内限定で公開できます。

### 1. PC側: Tailscaleをインストールしてログイン

1. [https://tailscale.com/download](https://tailscale.com/download) から Windows 版 Tailscale をインストール
2. Tailscale を起動し、管理者本人のアカウントでログイン
3. 接続状態が `Connected` になっていることを確認

### 2. スマホ側: Tailscaleアプリを入れて同じアカウントでログイン

1. iOS は App Store、Android は Google Play から Tailscale アプリをインストール
2. PCと同じ Tailscale アカウントでログイン
3. VPN/接続を ON にして、Tailnet に参加済みであることを確認

### 3. Streamlitを localhost:8501 で起動

PowerShell 例:

```bash
streamlit run admin_app.py --server.address 127.0.0.1 --server.port 8501
```

### 4. tailscale serve で localhost:8501 を公開

別ターミナルで実行:

```bash
tailscale serve --bg http://127.0.0.1:8501
```

公開状態の確認:

```bash
tailscale serve status
```

### 5. スマホからアクセス

スマホ側で Tailscale 接続を ON にした状態で、次のURLにアクセスします。

- `https://PC名.tailnet名.ts.net`

これで、外出先からでも管理者本人（同じ Tailnet にログイン済みユーザー）のみが管理画面を利用できます。

### 6. うまく接続できない場合の確認項目

- Streamlit が起動中か（`http://127.0.0.1:8501` をPC上で開けるか）
- Tailscale が PC とスマホの両方で接続済みか
- `tailscale serve status` で `http://127.0.0.1:8501` が割り当て済みか
- Windows ファイアウォールで Tailscale / Streamlit 通信がブロックされていないか

### 7. 注意事項

- 一般公開ではなく、自分の Tailnet 内だけで利用する
- 解析中は PC の電源を落とさない（停止すると外部アクセスできない）
- 大容量動画はアップロード完了まで時間がかかる

## 🗂️ ジョブ管理機能（admin_app.py）

### 概要

`admin_app.py` は Streamlit 製の管理画面です。解析ごとに専用の **ジョブフォルダ** を自動生成し、入力・出力・メタデータを整理します。将来的な FastAPI / S3 / LINE 連携を見据えた構成です。

### ジョブフォルダ構造

```
jobs/
└── YYYYMMDD_HHMMSS_xxxx/   ← ジョブID（例: 20260508_143022_a3f1）
    ├── input/
    │   └── original.mp4            ← アップロードされた動画
    ├── output/
    │   ├── analysis_*.mp4          ← 解析結果動画
    │   └── *_report.json           ← 解析レポート（バリアントごと）
    ├── report/
    │   └── pose_landmarks.csv      ← 姿勢ランドマーク CSV データシート
    └── job.json                    ← ジョブメタデータ
```

### 📊 姿勢ランドマーク CSV データシート

解析完了後、`jobs/<job_id>/report/pose_landmarks.csv` が自動生成されます。

#### 列構成

| 列名 | 説明 |
|---|---|
| `frame` | フレーム番号（1始まり） |
| `time_sec` | 経過時間（秒）= frame / FPS |
| `<部位>_x` | 正規化 X 座標（0〜1、左端=0） |
| `<部位>_y` | 正規化 Y 座標（0〜1、上端=0） |
| `<部位>_z` | 深度 Z（MediaPipe 推定値） |
| `<部位>_visibility` | 可視性スコア（0〜1） |

#### 対象ランドマーク（13部位）

`nose` / `left_shoulder` / `right_shoulder` / `left_elbow` / `right_elbow` / `left_wrist` / `right_wrist` / `left_hip` / `right_hip` / `left_knee` / `right_knee` / `left_ankle` / `right_ankle`

#### 利用例

```python
import pandas as pd
df = pd.read_csv("jobs/<job_id>/report/pose_landmarks.csv")
print(df[["frame", "time_sec", "right_wrist_x", "right_wrist_y"]].head())
```

#### Streamlit 管理画面での確認

ジョブ詳細画面の「出力ファイル」欄で `pose_landmarks.csv` の先頭5行をプレビュー表示し、全フレームのデータをダウンロードできます。

#### report.json への追記

`report.json` の `data_files` フィールドに CSV のパスが記録されます：

```json
{
  "data_files": {
    "pose_landmarks_csv": "report/pose_landmarks.csv"
  }
}
```

#### 注意事項

- CSV 生成に失敗しても動画解析全体は失敗扱いにならず、警告ログのみ出力されます
- `all_variants` モード（6 種同時出力）では、最初のバリアントの処理時に 1 度だけ生成されます（上書きなし）
- ランドマークが検出されなかったフレームは `x / y / z / visibility` が空欄になります

---

### 🖼️ 代表フレーム画像の出力

解析完了後、入力動画の代表フレームが `jobs/<job_id>/report/frames/` に自動保存されます。

#### 保存位置と命名規則

| ファイル名 | 説明 |
|---|---|
| `frame_0000_start.jpg` | 動画の先頭フレーム（0%） |
| `frame_XXXX_25pct.jpg` | 全体の25%位置のフレーム |
| `frame_XXXX_50pct.jpg` | 全体の50%位置のフレーム（中央付近） |
| `frame_XXXX_75pct.jpg` | 全体の75%位置のフレーム |
| `frame_XXXX_90pct.jpg` | 全体の90%位置のフレーム（リリース後） |

`XXXX` は実際のフレーム番号（ゼロ埋め4桁）です。

#### report.json への追記

```json
{
  "visual_files": {
    "representative_frames": [
      "report/frames/frame_0000_start.jpg",
      "report/frames/frame_0062_25pct.jpg",
      "report/frames/frame_0124_50pct.jpg",
      "report/frames/frame_0186_75pct.jpg",
      "report/frames/frame_0224_90pct.jpg"
    ]
  }
}
```

#### Streamlit 管理画面での確認

ジョブ詳細画面の「出力ファイル」欄が4セクションに整理されています：

- **🖼️ 代表フレーム画像** — 5枚の静止画をグリッド表示・個別ダウンロード
- **📈 解析グラフ** — 3枚のグラフ画像をグリッド表示・個別ダウンロード
- **📊 CSVデータシート** — `pose_landmarks.csv` の先頭5行プレビュー・全データDL
- **🎬 解析動画** — 各バリアント動画の再生・ダウンロード

#### 注意事項

- フレーム切り出しに失敗してもジョブ全体は `failed` にならず、警告ログのみ出力されます
- `all_variants` 等で複数回呼ばれる場合、`frames/` ディレクトリが既に存在する場合はスキップされます

---

### 📈 グラフ画像の自動生成

解析完了後、`pose_landmarks.csv` を元に3種類のグラフ画像が `jobs/<job_id>/report/graphs/` に自動保存されます。

#### 利き腕に応じたグラフ生成

`customer_info.json` の `dominant_hand` フィールドに応じて、手首・腕軌跡グラフの対象関節を自動切替します。

| `dominant_hand` | 使用する関節 |
|---|---|
| `"right"`（デフォルト）| right_wrist / right_elbow / right_shoulder |
| `"left"` | left_wrist / left_elbow / left_shoulder |
| `"unknown"` またはファイルなし | right（デフォルト）|

#### 生成されるグラフ

| ファイル名 | 内容 |
|---|---|
| `right_wrist_height.png` または `left_wrist_height.png` | 投げ腕の手首高さ変化（時系列）|
| `right_arm_trajectory.png` または `left_arm_trajectory.png` | 投げ腕の肩・肘・手首 2D 軌跡 |
| `torso_center_trajectory.png` | 肩中心・腰中心の移動軌跡（左右共通） |

#### グラフの座標系

MediaPipe の画像座標は y=0 が画面上部・y=1 が下部のため、高さ表示では `1 - y` に変換しています（上方向への変化が上向きのグラフになります）。

#### report.json への追記

```json
{
  "visual_files": {
    "representative_frames": ["report/frames/frame_0000_start.jpg"],
    "graphs": [
      "report/graphs/right_wrist_height.png",
      "report/graphs/right_arm_trajectory.png",
      "report/graphs/torso_center_trajectory.png"
    ]
  }
}
```

#### Streamlit 管理画面での確認

ジョブ詳細 → 出力ファイル の **📈 解析グラフ** セクションで3枚を横並び表示・個別ダウンロードできます。

#### 注意事項

- CSV が存在しない場合・必要な列が欠けている場合は、そのグラフだけスキップし警告ログを出力します
- `all_variants` 等で複数回呼ばれる場合、`graphs/` ディレクトリが既に存在する場合はスキップされます
- グラフ生成に失敗しても動画解析・CSV・代表フレームの出力には影響しません
- 生成モジュール: `src/graph_generator.py`（`generate_graphs_for_job(job_dir)` 関数）

---

### 📄 PDFレポートの自動生成

解析完了後、代表フレーム画像・グラフ画像・解析メトリクスをまとめたA4 PDF レポートが `jobs/<job_id>/report/report.pdf` に自動保存されます。

#### PDF構成

| ページ | 内容 |
|---|---|
| 1ページ目（表紙） | タイトル・Job ID・日時・身長・モード・入力ファイル名 |
| 2ページ目 | 動画情報・解析メトリクス・出力ファイルサマリ |
| 3ページ目〜 | 代表フレーム画像（2列×2行、最大4枚/ページ） |
| 次ページ〜 | グラフ画像（1〜2枚/ページ） |
| 最終ページ | 免責事項（Disclaimer） |

#### report.json への追記

```json
{
  "report_files": {
    "pdf": "report/report.pdf"
  }
}
```

#### Streamlit 管理画面での操作

- ジョブ詳細画面の **📄 PDFレポート** セクションから `report.pdf` をダウンロードできます
- **🔄 PDF を再生成** ボタンで任意のタイミングで再生成できます（データ更新後に再実行する場合など）

#### 注意事項

- `frames/` や `graphs/` が存在しない場合でも "No representative frames found." 等の文言を挿入して PDF 生成を継続します
- PDF 生成に失敗しても動画解析・CSV・グラフ出力には影響しません
- Windows 環境のみで動作確認済み（ReportLab 使用、日本語フォント未使用・英語中心）
- 生成モジュール: `src/pdf_report_generator.py`（`generate_pdf_report_for_job(job_dir)` 関数）
- 依存ライブラリ: `reportlab>=4.0.0`（`requirements.txt` 記載）

---

### 🗂️ Streamlit 管理画面の成果物分類

ジョブ詳細画面は成果物の用途に応じて **A〜K の各セクション** に分かれています。

| セクション | 内容 |
|---|---|
| 🗂️ A. Job Summary | Job ID・ステータス・選手名・プラン・日時・ステータス変更ボタン |
| 🆓 B. Free Preview Outputs | 解析動画（骨格/ヒートマップ/HUD等）・代表フレーム画像 |
| 📊 C. Data Sheet Outputs | pose_landmarks.csv・解析グラフ画像 |
| 📄 D. PDF Report | report.pdf ダウンロード・再生成ボタン・生成日時 |
| 🔒 E. Admin/Internal Files | job.json・report.json・その他管理者専用ファイル |
| 📦 F. 納品用ZIPパッケージ | 3種類の ZIP 生成・ダウンロード |

#### ファイル分類ロジック

`admin_app.py` の `_classify_job_files(job_dir, output_files)` 関数が出力ファイルをカテゴリ別に分類します。

- **preview_mp4s**: ファイル名に `skeleton / trail / heatmap / hud / stickman / vectors / gaming` を含む MP4
- **frame_files**: パスに `frames/` を含む画像ファイル
- **graph_files**: パスに `graphs/` を含む PNG 画像
- **csv_files**: `.csv` ファイル
- **pdf_path**: `report.pdf` という名前の PDF
- **admin_files**: `.json` ファイル
- **other_files**: 上記に該当しないファイル

---

### 📦 納品用ZIPパッケージ生成

各ジョブの成果物を3種類の ZIP にまとめて `jobs/<job_id>/deliverables/` に保存できます。

#### 生成される ZIP

| ファイル名 | 含まれるもの |
|---|---|
| `free_preview.zip` | 解析動画（プレビュー用）+ 代表フレーム先頭3枚 |
| `data_sheet_package.zip` | pose_landmarks.csv + グラフ画像 + 全代表フレーム画像 |
| `full_report_package.zip` | report.pdf + CSV + グラフ + フレーム + 全出力動画 |

#### 使い方（コード）

```python
from pathlib import Path
from src.deliverable_packager import create_deliverable_packages_for_job

zips = create_deliverable_packages_for_job(Path("jobs/20260508_181930_c4bd"))
# -> {
#      "free_preview":        Path(".../deliverables/free_preview.zip"),
#      "data_sheet_package":  Path(".../deliverables/data_sheet_package.zip"),
#      "full_report_package": Path(".../deliverables/full_report_package.zip"),
#    }
```

#### report.json への追記

```json
{
  "deliverables": {
    "free_preview_zip":          "deliverables/free_preview.zip",
    "data_sheet_package_zip":    "deliverables/data_sheet_package.zip",
    "full_report_package_zip":   "deliverables/full_report_package.zip"
  }
}
```

#### Streamlit 管理画面での操作

- **🔒 E. 管理者内部用** → report.json で `deliverables` フィールドを確認
- **📦 F. 納品用ZIPパッケージ** → 「🗜️ ZIPを全て生成」ボタンで一括生成
- 生成済みの各 ZIP はサイズ・生成日時付きで表示され、ダウンロードボタンから取得可能

#### 注意事項

- ファイルが存在しない場合はスキップし、ZIP 生成全体は止まりません
- 生成モジュール: `src/deliverable_packager.py`（`create_deliverable_packages_for_job(job_dir)` 関数）
- ZIP はデフォルトで DEFLATE 圧縮（動画はすでに圧縮済みのため圧縮率は低いことがあります）

---

### job.json のフィールド

| フィールド | 内容 |
|---|---|
| `job_id` | `YYYYMMDD_HHMMSS_xxxx` 形式の一意なID |
| `status` | `created` / `running` / `completed` / `failed` |
| `created_at` | ジョブ作成日時（ISO 8601） |
| `updated_at` | 最終更新日時（ISO 8601） |
| `height_m` | 被写体の身長（メートル、任意） |
| `mode` | 解析モード |
| `input_file` | 入力動画のフルパス |
| `output_files` | 出力ファイルのパスリスト |
| `error` | エラーメッセージ（失敗時のみ） |

### 管理画面の起動

```bash
streamlit run admin_app.py --server.address 127.0.0.1 --server.port 8501
```

ブラウザで `http://localhost:8501` を開く。

### 画面構成

- **▶ 新規ジョブ**: 動画アップロード → 解析モード選択 → 解析実行
- **📋 ジョブ履歴**: 過去ジョブの一覧表示・動画・ファイルの確認

### 解析モード一覧

| モード | 説明 |
|---|---|
| `basic` | 骨格表示のみ |
| `heatmap` | 速度ヒートマップ |
| `vectors` | 速度・加速度ベクトル |
| `hud` | ゲーム風 HUD |
| `all_variants` | 上記4種類を同時出力 |

### コマンドライン連携（新規オプション）

`run.py` に以下のオプションを追加しました。既存の動作は変わりません。

```bash
# 標準形式（admin_app.py が使用する形式）
python run.py --input jobs/20260508_143022_a3f1/input/original.mp4 \
              --output-dir jobs/20260508_143022_a3f1/output

# 後方互換: --video も引き続き使用可能
python run.py --video input/my_video.mp4
```

### jobs/ ディレクトリの除外設定

`.gitignore` に以下を追加することを推奨します。

```
jobs/
```

---

## 🗺️ 動画解析サービス運用ロードマップ

> 久しぶりに開いたときの自分向け運用メモ。サービス化の手順と注意点をまとめています。

### ✅ 現在できること

- Streamlit 管理画面（`admin_app.py`）での依頼受付〜納品管理
- ジョブ管理（ジョブ作成・ステータス追跡・顧客情報紐付け）
- CSVデータシート（`pose_landmarks.csv`）の自動出力
- 代表フレーム画像の自動切り出し
- グラフ画像の自動生成（手首高さ・腕軌跡・体幹軌跡）
- PDFレポートの自動生成（日本語対応・顧客情報反映・コーチコメント欄付き）
- 納品用 ZIP の自動生成（無料プレビュー / データシート / フルレポートの3種）
- Tailscale 経由での外出先アクセス（Tailnet 内限定）
- 解析サマリー JSON（`analysis_summary.json`）の自動生成
- 2ジョブ比較機能（`compare_jobs.py`）
- 運用チェックリストタブ（受付〜SNS掲載前確認まで8セクション）

### 🔜 次にやること

- PDF の日本語フォント対応（完了済み: meiryo / msgothic / YuGothM フォールバック）
- 利き腕対応グラフ生成（完了済み: `dominant_hand` に応じた関節切替）
- 顧客情報の PDF 反映（完了済み: 全フィールド 2 ページ目に表示）
- `analysis_summary.json` による解析要点の要約（完了済み）
- 複数動画比較（完了済み: 比較タブ実装）
- **残課題**: LINE / DM テンプレート自動生成、S3 / クラウドストレージ連携、顧客ポータル画面

### 💴 有料メニュー案

| プラン | 内容 |
|---|---|
| 無料プレビュー | 解析動画（骨格/ヒートマップ）+ 代表フレーム3枚 |
| データシート版 | CSV + グラフ3種 + 代表フレーム全枚 |
| フルレポート版 | PDF + CSV + グラフ + 全動画 |
| 2動画比較版 | 2ジョブの比較サマリー + 差分グラフ |

### ⚠️ 注意事項

- 本解析は**競技指導・医療判断・怪我の診断を代替しない**可視化参考資料です
- 納品物にも「参考資料であり診断ではない」旨を必ず記載すること
- SNS 掲載前に**顧客本人の掲載許可**を必ず確認すること
- 動画・個人情報（顧客名・ID等）はローカルの `jobs/` フォルダにのみ保存し、外部共有に注意すること
- `jobs/` フォルダは `.gitignore` に追加して Git 管理外にすること

### 🖥️ Windows での起動コマンド

```powershell
# Python 仮想環境を有効化してから実行
C:\venvs\javelin312\Scripts\python.exe -m streamlit run admin_app.py --server.address 127.0.0.1 --server.port 8501
```

ブラウザで `http://localhost:8501` を開く。

### 🌐 Tailscale 経由で使う場合の注意

- **一般公開しない** — Tailscale Serve は自分の Tailnet 内限定で使用する
- **Tailnet 内限定** — スマホと PC を同じ Tailscale アカウントに接続した状態で `https://PC名.tailnet名.ts.net` にアクセス
- **解析中は PC を落とさない** — 処理中にスリープ/シャットダウンすると外部アクセスが途絶える
- ファイアウォールで Tailscale / Streamlit 通信がブロックされていないか確認すること

---

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

| 📊 C. Data Sheet Outputs | CSVデータシート・解析グラフ画像 |
| 📄 D. PDF Report | report.pdf の表示・再生成 |
| 📖 D2. 解析動画説明書 | video_instruction.pdf |
| 🔒 E. 管理者内部用 | job.json / 解析レポート JSON / その他管理ファイル |
| 📦 F. 納品用ZIPパッケージ | free_preview / data_sheet / full_report の3種ZIP生成 |
| 👤 G. 顧客情報 | 選手情報・プラン・SNS許可・メモの編集フォーム |
| ✉️ H. 納品メッセージ | プラン別コピペ用納品文・SNS許可確認文の自動生成 |
| 📊 J. 解析サマリー | analysis_summary.json の表示・再生成 |
| 📋 K. User-friendly Reports | 00_最初に読んでください.pdf・選手向け各PDF の生成 |

---

## 🚀 Phase 2 — 管理画面・納品運用の安定化

### ジョブステータス一覧

| ステータス | 意味 |
|---|---|
| `created` | 受付済み（ジョブ作成直後） |
| `uploaded` | 動画アップロード済み |
| `running` | 解析中 |
| `completed` | 解析完了 |
| `reviewing` | 内容確認中 |
| `ready_to_deliver` | 納品準備完了 |
| `delivered` | 納品済み |
| `failed` | エラー（解析失敗） |
| `archived` | 保管済み |

ステータスはジョブ詳細画面の「A. Job Summary」セクションから変更できます。  
「納品準備完了」「納品済み」「エラーリセット」「アーカイブ」のクイックボタンも用意されています。

---

### 納品までの基本フロー

```
1. 動画受取・ジョブ作成  →  created
2. 解析実行             →  running → completed (or failed)
3. 内容確認・PDF生成     →  reviewing
4. ZIP生成・最終確認     →  ready_to_deliver
5. 顧客へ納品           →  delivered
```

---

### プラン別成果物

| 成果物 | 無料プレビュー | データシート | フルレポート |
|---|---|---|---|
| 00_最初に読んでください.pdf | ✅ | ✅ | ✅ |
| 解析動画 (プレビュー) | ✅ | — | — |
| 解析動画 (全バリエーション) | — | ✅ | ✅ |
| 解析動画の見方.pdf | ✅ | ✅ | ✅ |
| 代表フレーム画像 (3枚) | ✅ | — | — |
| 代表フレーム画像 (全枚) | — | ✅ | ✅ |
| 選手向けサマリー.pdf | — | ✅ | ✅ |
| 代表フレームシート.pdf | — | ✅ | ✅ |
| グラフ解説.pdf | — | ✅ | ✅ |
| report.pdf（詳細レポート） | — | — | ✅ |
| コーチ向けレビューシート.pdf | — | — | ✅ |
| pose_landmarks.csv | — | ✅ | ✅ |
| analysis_summary.json | — | — | ✅ |
| グラフ画像 | — | — | ✅ |

---

### SNS掲載許可の扱い

SNS掲載許可ステータスは `customer_info.json` に保存されます。

| ステータス | 意味 |
|---|---|
| `unknown` | 未確認（デフォルト） |
| `allowed` | 掲載許可あり |
| `anonymous` | 匿名加工なら許可 |
| `denied` | 掲載不可 |

「H. 納品メッセージ」セクションから、SNS掲載許可確認用のメッセージを自動生成できます。  
返答後は「G. 顧客情報」欄でステータスを更新してください。

匿名化が必要な場合は「匿名化メモ」欄に記録できます（例: 名前を出さない / 顔を隠す など）。

---

### エラー発生時の確認方法

1. ジョブ詳細の「A. Job Summary」にエラー内容が赤字で表示されます
2. 「I. 解析ログ」セクションを展開し、`stderr.txt` を確認します
3. `logs/job_log.txt` に操作ログが JSON 形式で記録されます
4. 「エラーをリセット」ボタンで `completed` に戻し、再処理できます

---

### Phase 2 で追加・変更されたファイル

| ファイル | 内容 |
|---|---|
| `job_manager.py` | ステータス定数 (`JOB_STATUSES`, `JOB_STATUS_LABELS`) を追加。メタデータにニックネーム・競技歴・SNS許可（4値）・匿名化メモ・管理者メモ・受付日・納品予定メモ・納品済み日時を追加 |
| `src/job_logger.py` | ジョブ別操作ログ (`jobs/<id>/logs/job_log.txt`) の書き込み・読み込みモジュール（新規） |
| `admin_app.py` | ジョブ一覧にフィルタ機能・詳細情報を追加。ステータス変更・クイック操作ボタンを追加。顧客情報フォームを拡張。H. セクションにSNS許可確認メッセージ生成を追加。K. セクションに一括PDF再生成ボタンを追加。F. セクションに個別ZIP生成ボタンを追加 |

---

## Phase 3: 受付フォーム・顧客情報管理・プラン設計

### 受付情報（intake_info.json）

各ジョブには `jobs/<job_id>/intake_info.json` として受付情報が保存されます。  
管理画面の「📝 N. 受付情報」セクションから入力・編集できます。

**主な収集項目:**

| カテゴリ | フィールド |
|---|---|
| 基本情報 | 名前/連絡先/年齢区分/性別/競技歴/自己ベスト/利き腕★/身長★/所属区分 |
| 動画情報 | 撮影日/撮影状況/撮影角度★/動画種別★/スロー動画/動画本数/優先順位メモ |
| 相談内容 | 一番見てほしい点★/フォーカスチェックボックス6項目/自由記述 |
| 希望プラン | free_preview / light / data_sheet / full_report / comparison / undecided |
| 同意事項 | 6項目のブーリアン（全 False がデフォルトの安全側） |

★ = 解析・納品に特に重要な項目

---

### plans.yaml によるプラン設計

`configs/plans.yaml` でサービスプランを定義できます。

```yaml
free_preview:
  label: "無料プレビュー"
  price_hint: "無料"
  description: "まず解析の雰囲気を確認したい方向け"
  includes:
    - readme_pdf
    - video_instruction_pdf
    - representative_frames
    - preview_video
light:
  label: "ライト版"
  ...
```

`src/plan_loader.py` がこのファイルを読み込み、管理画面・受付フォームに反映されます。  
PyYAML が未インストールの場合もフォールバックで動作します。

---

### Googleフォームとの連携（CSVインポート）

Googleフォームの回答CSVを管理画面「📥 CSVインポート」タブからインポートできます。

**推奨手順:**

1. `docs/google_form_template.md` の質問テンプレートをコピーしてGoogleフォームを作成
2. 回答スプレッドシートを CSV でダウンロード
3. 管理画面「📥 CSVインポート」タブでアップロード
4. 列マッピングを確認（推奨タイトルなら自動マッピング）
5. 行を選択して「🚀 取り込む」

> 身長（cm）は 10 を超える場合に自動でメートル換算されます。

---

### 納品前チェックリスト

各ジョブに `jobs/<job_id>/delivery_checklist.json` が保存されます。  
管理画面「✅ L. 納品前チェックリスト」セクションから確認・更新できます。

**チェック項目（13項目）:**

1. 受付情報を確認した
2. 利き腕を確認した（右/左）
3. 身長を確認した
4. 撮影角度を確認した
5. PDFが生成されている
6. 解析動画が生成されている
7. 納品ZIPが生成されている
8. ZIP内に「00_最初に読んでください.pdf」がある
9. ZIP内に解析動画の見方PDFがある
10. ZIP内に免責事項ファイルがある
11. 希望プランと納品物の内容が一致している
12. SNS掲載許可ステータスを確認した
13. 納品メッセージを生成した

全13項目がチェック済みになると「🎉 納品準備完了」と表示されます。

---

### 動画提出ガイド・同意事項テンプレート

| ファイル | 用途 |
|---|---|
| `docs/video_submission_guide.md` | アスリート向け動画提出ガイド |
| `docs/consent_template.md` | 同意事項テンプレート（Googleフォーム用文面） |
| `docs/google_form_template.md` | Googleフォーム推奨質問項目 |

---

### Phase 3 で追加・変更されたファイル

| ファイル | 内容 |
|---|---|
| `configs/plans.yaml` | サービスプラン定義（5プラン） |
| `src/plan_loader.py` | plans.yaml 読み込みモジュール（新規） |
| `job_manager.py` | `get_intake_info` / `update_intake_info` / `get_delivery_checklist` / `update_delivery_checklist` を追加 |
| `admin_app.py` | 「📝 N. 受付情報」「✅ L. 納品前チェックリスト」「📥 CSVインポート」タブを追加 |
| `docs/video_submission_guide.md` | アスリート向け動画提出ガイド（新規） |
| `docs/consent_template.md` | 同意事項テンプレート（新規） |
| `docs/google_form_template.md` | Googleフォーム推奨テンプレート（新規） |
| `tests/test_phase3.py` | Phase 3 ユニットテスト（新規） |

---

## Phase 4: 2動画比較・フェーズ別解析

投てき動作を 7 フェーズに分割し、2本の動画を並べて比較できる機能を追加しました。

### 主な新機能

#### フェーズ別解析
- **フェーズ定義** (`configs/phases.yaml`): 助走・クロスステップ・槍を引く・ブロック・リリース・フォロースルー・リカバリー の 7 フェーズを定義
- **フェーズ指定 UI** (管理画面「🎬 O. フェーズ指定」): 各フェーズのフレーム番号を手動指定。FPS から秒数を自動計算して表示
- **フェーズ別代表フレーム生成**: 指定フレームを JPEG 保存 (`report/phase_frames/phase_<key>.jpg`)
- **フェーズ別サマリー PDF** (`report/phase_summary.pdf`): 各フェーズの画像・説明・確認ポイントをまとめた PDF

#### 2動画比較
- **比較ジョブ管理**: 2本のジョブを選んで「比較ジョブ」として登録 (`comparisons/<id>/comparison.json`)
- **比較レポート PDF** (`comparison_report.pdf`): フェーズ別の 2列並置画像、数値差分テーブル、グラフ比較を収録。すべて非断定的な表現を使用
- **比較パッケージ ZIP** (`comparison_package.zip`): レポート・画像・グラフ・サマリーを整理した ZIP
- **管理画面の比較タブ強化**: 比較ジョブ作成・一覧・レポート生成・ZIP 生成・ダウンロードを一括管理

#### プラン更新
- `comparison` プランに `phase_summary_pdf` / `comparison_phase_images` を追加

### Phase 4 で追加・変更されたファイル

| ファイル | 変更内容 |
|---------|---------|
| `configs/phases.yaml` | フェーズ定義 YAML（新規） |
| `configs/plans.yaml` | comparison プラン更新 |
| `src/phase_loader.py` | phases.yaml ローダー（新規） |
| `src/phase_frames.py` | フェーズ別フレーム抽出（新規） |
| `src/phase_summary_pdf.py` | フェーズ別サマリー PDF（新規） |
| `src/comparison_report_pdf.py` | 2動画比較レポート PDF（新規） |
| `src/comparison_zip.py` | 比較パッケージ ZIP 生成（新規） |
| `job_manager.py` | フェーズフレーム・比較ジョブ管理関数を追加 |
| `admin_app.py` | O. フェーズ指定セクション、比較タブ UI 強化 |
| `tests/test_phase4.py` | Phase 4 ユニットテスト（新規） |

---

## Phase 5: S3保存・納品URL生成・スマホ閲覧対応

### 概要

解析成果物を Amazon S3 にアップロードし、presigned URL を使ってお客様がスマホから直接閲覧できる
**納品ページ HTML** を生成します。ZIP を送る代わりに URL 1本で完結する納品フローを実現します。

### 主な機能

- **S3 自動アップロード**: 解析動画・PDF・グラフ・ZIP など全成果物を一括アップロード
- **成果物マニフェスト**: 何がアップロード済みかを `artifact_manifest.json` で管理
- **スマホ対応納品ページ**: 1ファイル完結 HTML（外部 CSS 依存なし）を自動生成
- **presigned URL**: バケットを非公開のまま、有効期限付き URL でセキュアに共有
- **LINEで送れるURL**: 管理画面から URL をコピーしてそのまま LINE 送信
- **S3 未設定でも動作**: 環境変数未設定時はローカル運用を継続（ダウングレードなし）

### セキュリティ設計

- バケットは **Block All Public Access** のまま使用
- S3 キーに個人名・学校名を含めない（job_id のみ使用）
- presigned URL をログに記録しない
- AWSキーをコードに直書きしない（`.env` または IAM ロール）
- `.env` は Git 管理しない

### セットアップ

```bash
pip install boto3
cp .env.example .env   # JVA_BUCKET などを編集
```

詳細: [docs/s3_delivery_setup.md](docs/s3_delivery_setup.md)

### 管理画面での操作

ジョブ詳細の「**☁️ P. S3納品 / 納品URL発行**」エクスパンダーから操作:

1. 📋 マニフェスト生成 → 成果物一覧を確認
2. ☁️ S3 アップロード → 全成果物をアップロード
3. 🌐 納品ページ生成 → URL 発行
4. URL をコピーして LINE 等で送付

### Phase 5 で追加・変更されたファイル

| ファイル | 内容 |
|---------|------|
| `src/storage/__init__.py` | S3 ストレージパッケージ（新規） |
| `src/storage/s3_storage.py` | S3 アップロード・presigned URL ユーティリティ（新規） |
| `src/artifact_manifest.py` | 成果物マニフェスト生成・管理（新規） |
| `src/delivery_page.py` | スマホ向け納品 HTML 生成（新規） |
| `job_manager.py` | S3 納品フィールド管理関数を追加 |
| `admin_app.py` | P. S3納品セクション追加、`build_delivery_message` に URL 差し込み |
| `.env.example` | S3 設定項目追加 |
| `docs/s3_delivery_setup.md` | S3 セットアップガイド（新規） |
| `tests/test_phase5.py` | Phase 5 ユニットテスト（新規） |

---

## Phase 6: 公式LINE・Googleフォーム・FastAPI受付連携

解析依頼の受付を効率化するための受付管理（intake）システムを追加しました。

### 主な機能

- **intake データモデル**: `intakes/{intake_id}/intake.json` で受付情報を管理
- **FastAPI 受付 API**: `POST /v1/intakes` 等のエンドポイントで受付情報を作成・管理
- **管理画面 intake 一覧タブ**: フィルタ・詳細編集・ジョブ化操作
- **Googleフォーム連携**: Apps Script から POST する方法を `docs/google_form_integration.md` に記載
- **公式 LINE 運用ガイド**: `docs/line_official_account_guide.md` に運用フローを記載

### 受付 API エンドポイント

```
POST   /v1/intakes                         受付情報を作成
GET    /v1/intakes                         受付一覧（?status=&source= フィルタ対応）
GET    /v1/intakes/{id}                    受付詳細
PATCH  /v1/intakes/{id}                    受付情報更新
POST   /v1/intakes/{id}/convert-to-job    ジョブ化（二重変換防止）
POST   /v1/intakes/{id}/archive           アーカイブ
POST   /v1/intakes/{id}/reject            対応不可
GET    /v1/intakes/health                  ヘルスチェック（認証不要）
```

**認証:** `X-JVA-API-Key` ヘッダーまたは `Authorization: Bearer {key}`

### 環境変数

```bash
JVA_API_KEY=your-secret-key        # APIキー（未設定時は開発モード・警告あり）
JVA_ENABLE_INTAKE_API=true         # API の有効化フラグ
LINE_CHANNEL_SECRET=               # LINE Webhook 用（将来対応）
LINE_CHANNEL_ACCESS_TOKEN=         # LINE Webhook 用（将来対応）
LINE_WEBHOOK_ENABLED=false         # LINE Webhook 有効化フラグ
```

### ステータス遷移

```
received → needs_review → ready_for_job → converted
                       ↘ rejected
any → archived
```

### 同意事項

以下の 6 項目の同意状態を管理します。デフォルトはすべて `false`（安全側）。

| フィールド | 説明 |
|---|---|
| `consent_reference_analysis` | 解析は参考資料であることへの同意 |
| `consent_not_medical` | 医療診断・怪我の診断でないことへの同意 |
| `consent_not_coaching_replacement` | 専門的競技指導の代替でないことへの同意 |
| `consent_accuracy_depends_on_video` | 動画品質により精度が変わることへの同意 |
| `consent_delivery_may_take_time` | 納品まで時間がかかる場合への同意 |
| `consent_sns_requires_permission` | SNS掲載は別途許可制であることへの同意 |

### Phase 6 で追加・変更されたファイル

| ファイル | 内容 |
|---|---|
| `src/intake_manager.py` | intake データモデル・管理関数（新規） |
| `server/intake_api.py` | FastAPI intake ルーター（新規） |
| `server/app.py` | intake_router のインクルード（変更） |
| `admin_app.py` | 受付一覧タブの追加（変更） |
| `docs/google_form_integration.md` | Googleフォーム連携ガイド（新規） |
| `docs/line_official_account_guide.md` | 公式 LINE 運用ガイド（新規） |
| `.env.example` | Phase 6 環境変数の追加（変更） |
| `tests/test_phase6.py` | Phase 6 ユニットテスト・44件（新規） |

---

## Phase 7: FastAPI 本格化・ジョブキュー・バックグラウンド処理

### 概要

動画解析のような重い処理を API リクエスト中に直接実行するのではなく、**ファイルベースのジョブキューに積み**、**ワーカーが順番に処理**し、解析・PDF 生成・ZIP 生成・S3 アップロード・納品 URL 生成まで自動または半自動で進められるようにしました。

### API からジョブを作る流れ

```bash
# 1. ジョブを作成
curl -X POST http://localhost:8000/v1/jobs \
  -H "X-JVA-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"height_m": 1.75}'

# 2. キューに投入
curl -X POST http://localhost:8000/v1/jobs/{job_id}/enqueue \
  -H "X-JVA-API-Key: your-key"

# 3. ステータス確認
curl http://localhost:8000/v1/jobs/{job_id}/queue-status \
  -H "X-JVA-API-Key: your-key"

# 4. ワーカーを起動（別ターミナル）
python worker.py --poll-interval 5
```

### ワーカー起動方法

```bash
python worker.py              # 継続ポーリング（本番）
python worker.py --once       # 1件のみ処理（テスト）
python worker.py --max-jobs 5 # 5件処理して終了
```

### ジョブキューステータス

| ステータス | 説明 |
|---|---|
| `pending` | 待機中（ワーカー取得待ち） |
| `running` | ワーカーが処理中 |
| `completed` | 正常完了 |
| `failed` | 失敗（`last_error` に詳細） |
| `cancelled` | キャンセル済み |

### キャンセルとリトライ

```bash
# キャンセル
curl -X POST http://localhost:8000/v1/jobs/{job_id}/cancel \
  -H "X-JVA-API-Key: your-key"

# リトライ（failed/cancelled → pending）
curl -X POST http://localhost:8000/v1/jobs/{job_id}/retry \
  -H "X-JVA-API-Key: your-key"
```

### S3 未設定時のローカル動作

`JVA_BUCKET` を設定しなくても、ローカルでの解析・PDF 生成・ZIP 生成は正常に動作します。S3 アップロードと納品ページ生成のステップは自動的にスキップされます。

### 管理画面でのキュー管理

`streamlit run admin_app.py` を起動し、**⚙️ キュー管理** タブを開くと:

- キュー件数のリアルタイム確認
- 各キュージョブの詳細・ステップ履歴
- キャンセル・リトライ操作
- 手動でのキュー投入

### Phase 7 で追加・変更されたファイル

| ファイル | 説明 |
|---|---|
| `src/queue_manager.py` | ファイルベースキューの CRUD・ステータス遷移（新規） |
| `worker.py` | ポーリングワーカー CLI（新規） |
| `server/jobs_api.py` | FastAPI Jobs API ルーター（新規） |
| `server/app.py` | jobs_api ルーター追加・旧エンドポイント削除（変更） |
| `admin_app.py` | Tab 7 キュー管理追加（変更） |
| `docs/background_worker.md` | バックグラウンドワーカー詳細ドキュメント（新規） |
| `.env.example` | Phase 7 環境変数の追加（変更） |
| `tests/test_phase7.py` | Phase 7 ユニットテスト（新規） |

詳細は [docs/background_worker.md](docs/background_worker.md) を参照してください。

---

## Phase 8: Docker 化・デプロイ準備・本番運用基盤

### 概要

ローカル開発・手動起動中心の構成を **Docker / docker compose** で再現可能に起動できる構成にします。

```
docker compose up
```

で `api / admin / worker` の3サービスが起動します。

### クイックスタート

```powershell
# Windows
copy .env.example .env
# .env を編集（最低限 JVA_API_KEY を設定）
.\scripts\docker_up.ps1
```

```bash
# Mac/Linux
cp .env.example .env
docker compose build && docker compose up -d
```

| URL | 説明 |
|---|---|
| http://localhost:8000 | FastAPI |
| http://localhost:8000/docs | API ドキュメント |
| http://localhost:8000/health | ヘルスチェック |
| http://localhost:8000/ready | 準備状態確認 |
| http://localhost:8501 | Streamlit 管理画面 |

### ローカル起動（Docker なし）

```powershell
# 各サービスを別ウィンドウで起動
.\scripts\dev_api.ps1
.\scripts\dev_admin.ps1
.\scripts\dev_worker.ps1
```

### Phase 8 で追加・変更されたファイル

| ファイル | 変更内容 |
|---|---|
| `Dockerfile` | マルチサービス対応（新規） |
| `.dockerignore` | Docker ビルド除外設定（新規） |
| `docker-compose.yml` | api / admin / worker 3サービス（新規） |
| `src/config.py` | 環境変数の一元管理（新規） |
| `src/logging_config.py` | ログ設定の一元管理（新規） |
| `server/app.py` | `/health`, `/ready` エンドポイント追加 |
| `admin_app.py` | 環境情報セクション追加（キュー管理タブ） |
| `.env.example` | Phase 8 変数を追加しカテゴリ別に整理 |
| `requirements.txt` | `streamlit`, `httpx`, `python-multipart` を追加 |
| `scripts/dev_api.ps1` | FastAPI 開発起動スクリプト（新規） |
| `scripts/dev_admin.ps1` | Streamlit 開発起動スクリプト（新規） |
| `scripts/dev_worker.ps1` | ワーカー開発起動スクリプト（新規） |
| `scripts/docker_up.ps1` | Docker Compose 起動スクリプト（新規） |
| `scripts/docker_down.ps1` | Docker Compose 停止スクリプト（新規） |
| `docs/deployment_guide.md` | デプロイメントガイド（新規） |
| `docs/security_checklist.md` | セキュリティチェックリスト（新規） |
| `tests/test_phase8.py` | Phase 8 ユニットテスト（新規） |

詳細は [docs/deployment_guide.md](docs/deployment_guide.md) を参照してください。

