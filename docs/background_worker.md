# バックグラウンドワーカー / ジョブキュー (Phase 7)

## 概要

Phase 7 では、動画解析のような重い処理を API リクエスト中に直接実行するのではなく、**ファイルベースのジョブキュー**に積み、**ワーカープロセスが順番に処理**する半自動処理基盤を実装しました。

```
クライアント → POST /v1/jobs → ジョブ作成
            → POST /v1/jobs/{id}/enqueue → キューに投入
                                        ↓
                              data/queue/pending/{queue_id}.json
                                        ↓ (worker.py がポーリング)
                              data/queue/running/{queue_id}.json
                                        ↓
                              解析→PDF→ZIP→S3→納品URL
                                        ↓
                              data/queue/completed/{queue_id}.json
```

---

## ディレクトリ構造

```
data/queue/
    pending/    待機中のキュージョブ
    running/    処理中のキュージョブ
    completed/  完了したキュージョブ
    failed/     失敗したキュージョブ
    cancelled/  キャンセルされたキュージョブ
```

各ファイル名は `{queue_id}.json` の形式で、`queue_id` は `qjob_YYYYMMDD_HHMMSS_xxxx` 形式です。

---

## ワーカーの起動

```bash
# 1件だけ処理（テスト用）
python worker.py --once

# 継続ポーリング（本番用）
python worker.py

# ポーリング間隔を変更（秒）
python worker.py --poll-interval 10

# 最大件数を指定して終了
python worker.py --max-jobs 5

# ロック取得なし（テスト・デバッグ用）
python worker.py --no-lock
```

### 環境変数

| 変数名 | デフォルト | 説明 |
|---|---|---|
| `JVA_WORKER_POLL_INTERVAL_SECONDS` | `5` | ポーリング間隔（秒） |
| `JVA_WORKER_MAX_RETRIES` | `1` | 失敗時の最大リトライ回数 |
| `JVA_QUEUE_DIR` | `data/queue` | キューディレクトリのパス |

---

## パイプラインステップ

`full_pipeline` ジョブタイプで実行されるステップ一覧:

| ステップ | 説明 | 失敗時の動作 |
|---|---|---|
| `validate_inputs` | 入力ファイル・パラメータの検証 | **即終了**（致命的） |
| `run_analysis` | 解析実行（`run.py` を subprocess 呼び出し） | **即終了**（致命的） |
| `generate_artifacts` | 成果物生成（フレーム、トラッキングデータ等） | **即終了**（致命的） |
| `generate_reports` | PDF・レポート生成 | 警告・継続 |
| `generate_packages` | ZIP パッケージ生成 | 警告・継続 |
| `upload_to_s3` | S3 アップロード（S3 未設定時はスキップ） | 警告・継続 |
| `generate_delivery_page` | 納品ページ生成（S3 未設定時はスキップ） | 警告・継続 |
| `update_delivery_url` | 納品 URL をジョブに記録 | 警告・継続 |
| `mark_ready` | ジョブステータスを `delivery_ready` に更新 | 警告・継続 |

---

## ジョブキュー API

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/v1/jobs/health` | ヘルスチェック |
| `POST` | `/v1/jobs` | ジョブ作成（`enqueue=true` で同時投入可） |
| `GET` | `/v1/jobs` | ジョブ一覧 |
| `GET` | `/v1/jobs/{job_id}` | ジョブ詳細 |
| `POST` | `/v1/jobs/{job_id}/enqueue` | キュー投入（二重投入は 409） |
| `POST` | `/v1/jobs/{job_id}/cancel` | キャンセル |
| `POST` | `/v1/jobs/{job_id}/retry` | リトライ（`failed`/`cancelled` → `pending`） |
| `GET` | `/v1/jobs/{job_id}/queue-status` | キュー状態 |
| `GET` | `/v1/jobs/{job_id}/artifacts` | 成果物一覧 |
| `GET` | `/v1/jobs/{job_id}/delivery` | 納品情報（S3 URL 含む） |
| `GET` | `/v1/queue` | キュー全体一覧・件数 |

### 認証

```bash
# X-JVA-API-Key ヘッダー
curl -H "X-JVA-API-Key: your-key" http://localhost:8000/v1/jobs

# Authorization Bearer
curl -H "Authorization: Bearer your-key" http://localhost:8000/v1/jobs
```

---

## ステータス遷移

```
pending → running → completed
pending → cancelled
running → failed
running → completed
failed  → pending (retry)
cancelled → pending (retry)
```

---

## キャンセルの仕組み

- **pending** ジョブ: 即座にキャンセル（ファイルを `cancelled/` に移動）
- **running** ジョブ: `cancel_requested` フラグを立てる。ワーカーは各ステップの前にフラグを確認し、セットされていれば処理を中断します（強制停止ではありません）

---

## S3 未設定時の動作

`JVA_BUCKET` が `your-bucket-name` のままか未設定の場合:

- `upload_to_s3` ステップをスキップ（エラーにならない）
- `generate_delivery_page` ステップをスキップ
- ローカルファイルの解析・PDF 生成・ZIP 生成は正常に実行される

---

## 管理画面でのキュー管理

管理画面（`admin_app.py`）の **⚙️ キュー管理** タブから以下の操作ができます:

- キュー件数サマリー（待機中 / 処理中 / 完了 / 失敗 / キャンセル）
- キュー一覧（ステータス別・ステップ詳細）
- ジョブをキューに投入
- キャンセル・リトライ

---

## トラブルシューティング

### ワーカーが起動しない

```bash
# Python バージョン確認
python --version

# 依存パッケージ確認
pip install -r requirements.txt
```

### ジョブが `failed` になる

```bash
# キュージョブのファイルを直接確認
cat data/queue/failed/qjob_YYYYMMDD_HHMMSS_xxxx.json
```

`last_error` と `failed_step` フィールドにエラー詳細が記録されています。

### 二重起動防止

ワーカーは `data/queue/worker.lock` にPIDを記録します。ロックファイルが残っている場合:

```bash
# ロックファイルを削除（ワーカーが停止していることを確認してから）
del data\queue\worker.lock
```

または `--no-lock` オプションで起動してください（テスト用）。

---

## 実装ファイル一覧

| ファイル | 役割 |
|---|---|
| `src/queue_manager.py` | キューの CRUD・ステータス遷移ロジック |
| `worker.py` | ポーリングワーカー（CLI） |
| `server/jobs_api.py` | FastAPI Jobs API ルーター |
| `server/app.py` | FastAPI アプリ（`jobs_router` をインクルード） |
| `admin_app.py` | Streamlit 管理画面（Tab 7: キュー管理） |
| `tests/test_phase7.py` | Phase 7 ユニットテスト |
