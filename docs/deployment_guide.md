# デプロイメントガイド (Phase 8)

## 概要

Javelin Video Analysis は以下の3サービスで構成されます。

| サービス | 役割 | デフォルトポート |
|---|---|---|
| `api` | FastAPI（ジョブ管理 / intake API） | 8000 |
| `admin` | Streamlit 管理画面 | 8501 |
| `worker` | バックグラウンドジョブワーカー | — |

---

## ローカル開発（Docker なし）

### 前提条件

- Python 3.11（Streamlit / MediaPipe 互換）または Python 3.12（テスト用）
- [requirements.txt](../requirements.txt) に記載のパッケージ

### セットアップ

```bash
# 1. 仮想環境を作成
python -m venv .venv
source .venv/bin/activate  # Mac/Linux
.\.venv\Scripts\Activate.ps1  # Windows

# 2. 依存パッケージをインストール
pip install -r requirements.txt

# 3. 環境変数ファイルを作成
cp .env.example .env  # Mac/Linux
copy .env.example .env  # Windows
# .env を編集して必要な値を設定

# 4. データディレクトリを作成
mkdir data data/queue outputs logs uploads
```

### 起動（PowerShell スクリプト）

```powershell
# FastAPI
.\scripts\dev_api.ps1      # http://127.0.0.1:8000

# Streamlit 管理画面
.\scripts\dev_admin.ps1    # http://127.0.0.1:8501

# ワーカー
.\scripts\dev_worker.ps1
```

### 起動（手動）

```bash
# FastAPI
uvicorn server.app:app --host 127.0.0.1 --port 8000 --reload

# Streamlit 管理画面
streamlit run admin_app.py

# ワーカー（1件処理してテスト）
python worker.py --once

# ワーカー（継続ポーリング）
python worker.py --poll-interval 5
```

---

## Docker Compose（推奨）

### 前提条件

- Docker Desktop（Windows / Mac）または Docker Engine（Linux）
- `docker compose` コマンドが利用可能

### クイックスタート

```powershell
# Windows PowerShell
.\scripts\docker_up.ps1

# または手動
cp .env.example .env
# .env を編集
docker compose build
docker compose up -d
```

### 確認

```bash
# サービス一覧
docker compose ps

# API ヘルスチェック
curl http://localhost:8000/health
curl http://localhost:8000/ready

# ログ確認
docker compose logs api
docker compose logs worker
docker compose logs admin
```

### 停止

```powershell
.\scripts\docker_down.ps1

# または
docker compose down

# ボリュームごと削除（データも削除されます）
docker compose down -v
```

---

## 環境変数リファレンス

詳細は [.env.example](../.env.example) を参照してください。

| 変数 | デフォルト | 説明 |
|---|---|---|
| `JVA_ENV` | `local` | 実行環境（local / staging / production） |
| `JVA_DATA_DIR` | `data` | データディレクトリ |
| `JVA_LOG_DIR` | `logs` | ログディレクトリ |
| `JVA_ADMIN_TOKEN` | `""` | `GET /api/upload-receipts` を保護する管理者トークン |
| `JVA_MAX_UPLOAD_MB` | `300` | Web受付のアップロード上限サイズ（MB） |
| `JVA_API_KEY` | `""` | API 認証キー（本番では必須） |
| `JVA_BUCKET` | `your-bucket-name` | S3 バケット名 |
| `JVA_WORKER_POLL_INTERVAL_SECONDS` | `5` | ワーカーポーリング間隔（秒） |
| `LINE_WEBHOOK_ENABLED` | `false` | LINE Webhook の有効化 |

フロントエンド側は `frontend/.env.local` またはデプロイ先の環境変数で `VITE_API_BASE_URL` を設定してください。
この値は `/upload` 画面から送信される API リクエストの送信先になります。

---

## 本番デプロイ前チェック（Web受付導線）

ローカルで確認済みの以下の導線を、本番URLでも再現できることをリリース前に確認してください。

```text
/upload → 動画アップロード → receiptId 発行 → 管理画面で受付一覧確認
→ 管理画面から解析実行 → outputs/{receiptId}/ 生成 → result.zip ダウンロード
```

### 1. 本番環境変数

バックエンド `.env`:

```env
JVA_ENV=production
JVA_ADMIN_TOKEN=<32文字以上のランダム文字列>
JVA_MAX_UPLOAD_MB=300
```

生成例:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

フロントエンド `frontend/.env.local` またはホスティング環境:

```env
VITE_API_BASE_URL=https://<your-api-domain>
```

確認ポイント:

- `JVA_ADMIN_TOKEN` が未設定だと `/api/upload-receipts` は `503` を返す
- `VITE_API_BASE_URL` はブラウザから到達できる FastAPI の本番URLを指す
- LINE で案内する URL は `https://<your-frontend-domain>/upload` を使用する

### 2. API保護確認

本番反映後に以下を確認:

```bash
curl https://<your-api-domain>/api/upload-receipts
# 期待値: 403 または 503

curl -H "X-Admin-Token: <JVA_ADMIN_TOKEN>" https://<your-api-domain>/api/upload-receipts
# 期待値: 200
```

### 3. スマホ実機確認

- iPhone / Android の実機ブラウザで `https://<your-frontend-domain>/upload` が表示される
- フォーム送信後に `receiptId` が表示される
- mp4 / MOV の両方で受付できる
- 日本語ファイル名 / 空白入りファイル名でも受付できる

### 4. 管理画面からの運用確認

- 管理画面で「📨 受付一覧 > 📥 Webアップロード受付一覧」に対象受付が表示される
- `filePath` が `uploads/YYYYMMDD/...` の相対パスで保存されている
- 「🚀 解析を実行」で `outputs/{receiptId}/` が作成される
- `result.zip` が生成され、管理画面からダウンロードできる

### 5. Git管理除外の確認

デプロイ前に以下が Git へ入っていないことを確認:

```bash
git ls-files .env uploads/ outputs/ data/
git ls-files frontend/node_modules/ frontend/dist/
git ls-files "*.mp4" "*.mov" "*.MOV" "*.zip" "*.pdf"
```

期待値: いずれも本番データ・秘密情報・生成物は出力されないこと。

---

## 本番デプロイ（VPS / AWS / Render など）

### 最小構成（VPS: さくらVPS・ConoHa等）

```bash
# Docker + docker compose のインストール後
git clone <repo> /opt/jva
cd /opt/jva
cp .env.example .env
# .env を本番値で編集

# Nginx リバースプロキシの設定（省略）
docker compose up -d
```

### AWS ECS / App Runner

1. `Dockerfile` でイメージをビルドし、ECR にプッシュ
2. ECS タスク定義で3サービス（api / admin / worker）を定義
3. 環境変数は Secrets Manager または Parameter Store から注入
4. EFS ボリュームを `/app/data`, `/app/logs` にマウント

### Render

1. Web Service（api）: `uvicorn server.app:app --host 0.0.0.0 --port $PORT`
2. Web Service（admin）: `streamlit run admin_app.py --server.address=0.0.0.0 --server.port=$PORT`
3. Background Worker（worker）: `python worker.py --poll-interval 5`
4. Persistent Disk を `/app/data` にマウント

### AWS Lightsail

1. Lightsail コンテナサービスを作成
2. 3コンテナ（api / admin / worker）を同一サービスにデプロイ
3. Public endpoint を api コンテナに向ける

---

## ヘルスチェックエンドポイント

| エンドポイント | 説明 | 成功条件 |
|---|---|---|
| `GET /health` | 稼働確認 | 常に 200 |
| `GET /ready` | 準備状態確認 | data_dir・queue_dir が存在すること |

```bash
# ヘルスチェック例
curl -f http://localhost:8000/health
# {"status":"ok","app":"javelin-video-analysis"}

curl -f http://localhost:8000/ready
# {"status":"ok","app":"javelin-video-analysis","env":"local","checks":{...}}
```

---

## データの永続化

コンテナを削除してもデータが消えないよう、以下のディレクトリはホスト側にマウントします。

```
./data/         → /app/data       ジョブデータ・キュー・受付データ
./outputs/      → /app/outputs    解析出力ファイル
./logs/         → /app/logs       ログファイル
./uploads/      → /app/uploads    アップロードファイル
```

---

## トラブルシューティング

### ポートが使用中

```bash
docker compose down
# または別ポートで起動
```

### MediaPipe / OpenCV エラー

Docker イメージは `opencv-python-headless` を使用するため、GUI 機能は不要です。
`cv2.imshow()` を呼び出しているコードがある場合はエラーになります。

### S3 未設定でも動く

`JVA_BUCKET=your-bucket-name` のままでも API とワーカーは起動します。
S3 を使う機能（presigned URL 生成など）のみ無効化されます。
`/ready` の `s3_configured` は `false` になりますが、HTTP 200 を返します。

### ログの確認

```bash
# Docker
docker compose logs -f api
docker compose logs -f worker

# ローカル
cat logs/api.log
cat logs/worker.log
cat logs/errors.log
```
