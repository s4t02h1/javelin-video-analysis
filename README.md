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

## 📥 β版Web動画受付 API 仕様

### POST `/api/upload`

- 役割: β版Webappからの動画受付
- Content-Type: `multipart/form-data`
- 受信フィールド:
  - `name` (必須)
  - `sns` (必須)
  - `event` (任意, 既定: `javelin`)
  - `snsConsent` (任意)
  - `agree` (必須, `true` 必須)
  - `file` (必須)
- 対応拡張子: `.mp4`, `.mov`, `.MOV`（内部判定は小文字化）
- サイズ上限: 300MB（`JVA_MAX_UPLOAD_MB` で変更可）
- 成功レスポンス例:

```json
{
  "ok": true,
  "receiptId": "JMA-20260514-0001"
}
```

### GET `/api/upload-receipts`（管理者用）

- 役割: 受付一覧の確認（個人情報を含むため管理者専用）
- 必須ヘッダー: `X-Admin-Token: <token>`
- 照合先環境変数: `JVA_ADMIN_TOKEN`
- トークン不一致: `403 forbidden`
- `JVA_ADMIN_TOKEN` 未設定: `503`（管理者トークン未設定エラー）

開発時の確認例:

```bash
curl -H "X-Admin-Token: dev-admin-token" http://localhost:8000/api/upload-receipts
```

環境変数設定例（PowerShell）:

```powershell
$env:JVA_ADMIN_TOKEN="dev-admin-token"
uvicorn server.app:app --reload --port 8000
```

---

## 🗂️ 動画保存・受付データ保存

- 動画保存先: `uploads/YYYYMMDD/`
- 受付データ保存先: `data/upload_receipts/receipts.json`
- `receipts.json` の `filePath` は**相対パス**で保存されます。
  - 例: `uploads/20260514/JMA-20260514-0001_xxxxx.mov`
- 実ファイル操作時は、サーバー側でリポジトリルート基準に絶対パスへ安全に解決します。

---

## 🔑 本番環境変数の設定（LINE誘導前に必須）

### バックエンド（`.env`）

```bash
cp .env.example .env
```

`.env` を編集して以下を設定してください：

| 変数名 | 説明 | 設定例 |
|---|---|---|
| `JVA_ADMIN_TOKEN` | 管理API保護トークン（**必須**） | `python -c "import secrets; print(secrets.token_urlsafe(32))"`の出力値 |
| `JVA_MAX_UPLOAD_MB` | アップロード上限（任意、デフォルト300） | `300` |

> ⚠️ `JVA_ADMIN_TOKEN` を空のまま起動すると `/api/upload-receipts` が 503 を返します。

### フロントエンド（`frontend/.env.local`）

```bash
cd frontend
cp .env.example .env.local
```

`frontend/.env.local` を編集：

```env
# ローカル確認時
VITE_API_BASE_URL=http://localhost:8000

# 本番（例: Tailscale Serve 経由でLINEユーザーにも届く場合）
VITE_API_BASE_URL=https://<PC名>.<tailnet名>.ts.net
```

### LINE誘導URL

LINEユーザーに共有するアップロードページのURLは以下の形式です：

```
http://localhost:5173/upload              # ローカル確認用
https://<PC名>.<tailnet名>.ts.net/upload  # Tailscale Serve 経由（β版本番）
```

フロントエンドをビルドして FastAPI から静的配信する場合：

```bash
cd frontend
npm run build
# dist/ が生成される → FastAPI の StaticFiles マウントまたは nginx で配信
```

> **確認ポイント**: LINEに貼るURL の `/upload` が正しく表示されるか、スマートフォンの実機ブラウザで開いて確認してください。

---

## ✅ β版公開前の動作確認手順（Web受付）

1. バックエンド起動

```bash
uvicorn server.app:app --reload --port 8000
```

2. フロントエンド起動

```bash
cd frontend
npm run dev
```

3. Webアップロード確認

- `/upload` から `.mp4/.mov/.MOV` を投稿できる
- `receiptId` が `JMA-YYYYMMDD-0001` 形式で発行される
- `uploads/YYYYMMDD/` に動画が保存される
- `data/upload_receipts/receipts.json` に受付データが保存される

4. 受付一覧 API 保護確認

- `X-Admin-Token` なしで `GET /api/upload-receipts` → 403 または 503（未設定時）
- 正しい `X-Admin-Token` で `GET /api/upload-receipts` → 200

5. 管理画面確認

- `streamlit run admin_app.py` で管理画面起動
- 「📨 受付一覧」内「📥 Webアップロード受付一覧」に反映される
- `status` 絞り込み、`receiptId/name/sns` 検索が機能する
- ファイル存在確認列が正しく表示される

---

## ▶ Web受付から解析実行までの手順（β版運用）

1. ユーザーが `/upload` から動画を提出し、`receiptId` が発行される
2. 管理画面 `admin_app.py` の「📨 受付一覧 > 📥 Webアップロード受付一覧」で受付内容を確認する
3. 受付動画を目視確認し、必要に応じて `status` を `checking` に変更する
4. 問題なければ「🚀 解析を実行」を押して既存 `run.py` フローへ投入する
5. 解析成功時は `outputs/{receiptId}/` に成果物が生成され、`result.zip` が作成される
6. 管理画面から `result.zip` をダウンロードして納品する
7. 納品完了後は `status=delivered` へ更新する

補足:

- 任意で「🆕 解析ジョブを作成 (jobs/)」を使うと、既存 `jobs/` ベース運用にも接続可能
- `filePath` は相対パス保存のため、管理画面側で安全に絶対パス解決して処理する

---

## 🧭 Web受付ステータス定義

- `uploaded`: 受付済み
- `checking`: 確認中
- `processing`: 解析中
- `completed`: 解析完了
- `failed`: 解析失敗
- `needs_resubmission`: 再投稿依頼
- `delivered`: 送付済み

解析実行時の自動遷移:

- 実行開始時に `processing`
- 成功時に `completed`
- 失敗時に `failed`（`errorMessage` に理由記録）
- 再投稿依頼へ回す場合は管理画面で `needs_resubmission` を手動設定
- 成果物送付後は管理画面で `delivered` を手動設定（`deliveredAt` を記録）

---

## 📦 成果物保存先（Web受付）

Web受付の成果物は `receiptId` 単位で分離して保存します。

推奨構成（既存処理の出力名は保持しつつ、最終的に集約）:

```text
outputs/
  {receiptId}/
    01_report.pdf
    02_summary.png
    03_graphs/
    04_data.csv
    05_analyzed_video.mp4
    result.zip
```

```text
outputs/
  {receiptId}/
    ... run.py 生成物 ...
    logs/
      command.txt
      stdout.txt
      stderr.txt
    result.zip
```

例:

```text
outputs/JMA-20260514-0004/
  05_analyzed_video.mp4
  report.pdf
  graphs/
  result.zip
```

`data/upload_receipts/receipts.json` の各受付には、必要に応じて以下が更新されます。

- `outputDir`: 成果物ディレクトリ（相対パス）
- `resultZipPath`: ZIPファイル（相対パス）
- `completedAt`: 解析完了時刻
- `deliveredAt`: 送付完了時刻

---

## ⚠️ 解析失敗時の対応

1. 管理画面で `errorMessage` を確認
2. 必要に応じて `note` に原因を記録
3. 再解析が難しい場合は `needs_resubmission` へ変更
4. 再投稿依頼時は撮影条件の改善点を明記

記録例:

- 被写体が遠すぎる
- スマホ縦撮り
- 暗い / 逆光
- ブレが大きい
- 身体が画面外に出ている
- 骨格点が十分に検出できない
- 対応外の動画形式

---

## 🔁 再投稿依頼に回す手順

1. 対象受付を選択
2. `status` を `needs_resubmission` に変更
3. `note` または `errorMessage` に再投稿理由を記載
4. 公式LINEで再投稿ガイドを案内

---

## ✅ β版公開前チェック（運用）

- Web受付後に管理画面一覧へ反映される
- 受付動画の存在確認ができる
- `status` 更新と `note/errorMessage` 保存ができる
- 解析実行で `processing -> completed/failed` が反映される
- `outputs/{receiptId}/result.zip` が生成される
- `result.zip` を管理画面からダウンロードできる
- 解析不能ケースを `needs_resubmission` へ回せる

---

> **Note**: β版サービスで使用しているレポート生成・ユーザー管理・納品フロー・独自解析ロジック・管理画面・S3 連携・課金処理等は、本リポジトリには含まれていません。
