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
| `JVA_API_KEY` | `""` | API 認証キー（本番では必須） |
| `JVA_BUCKET` | `your-bucket-name` | S3 バケット名 |
| `JVA_WORKER_POLL_INTERVAL_SECONDS` | `5` | ワーカーポーリング間隔（秒） |
| `LINE_WEBHOOK_ENABLED` | `false` | LINE Webhook の有効化 |

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
