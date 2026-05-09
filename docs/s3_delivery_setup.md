# S3 納品セットアップガイド

このドキュメントでは Javelin Video Analysis の「S3 保存・納品URL生成」機能（Phase 5）の
設定手順を説明します。

## 前提条件

- AWS アカウント（IAM ユーザーまたは IAM ロール）
- Python 環境に `boto3` がインストールされている
  ```bash
  pip install boto3
  ```

---

## 1. S3 バケット作成

AWS コンソール または AWS CLI でバケットを作成します。

```bash
aws s3api create-bucket \
  --bucket YOUR_BUCKET_NAME \
  --region ap-northeast-1 \
  --create-bucket-configuration LocationConstraint=ap-northeast-1
```

### セキュリティ設定（必須）

バケットを **完全非公開** に設定してください。

```bash
# Block All Public Access を有効化
aws s3api put-public-access-block \
  --bucket YOUR_BUCKET_NAME \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

ファイルの共有は **presigned URL** を使って行います（デフォルト: 7日間有効）。

---

## 2. IAM 設定

### IAM ユーザー（ローカル開発）

1. AWS コンソールで IAM ユーザーを作成
2. アクセスキーを発行
3. `~/.aws/credentials` に設定:
   ```ini
   [default]
   aws_access_key_id = AKIAXXXXXXXXXXXXXXXX
   aws_secret_access_key = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

### IAM ポリシー（最小権限）

ユーザーまたはロールに以下のポリシーをアタッチしてください:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::YOUR_BUCKET_NAME",
        "arn:aws:s3:::YOUR_BUCKET_NAME/*"
      ]
    }
  ]
}
```

> **注意**: `s3:*` など広い権限は付与しないでください。

---

## 3. 環境変数設定

`.env.example` をコピーして `.env` を作成し、設定を記入します:

```bash
cp .env.example .env
```

`.env` を編集:

```dotenv
AWS_REGION=ap-northeast-1
JVA_BUCKET=your-actual-bucket-name
JVA_S3_PREFIX=javelin-analysis
JVA_PRESIGNED_URL_EXPIRES_SECONDS=604800
```

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `AWS_REGION` | S3 バケットのリージョン | `ap-northeast-1` |
| `JVA_BUCKET` | S3 バケット名（必須） | プレースホルダー（未設定） |
| `JVA_S3_PREFIX` | S3 キーのプレフィックス | `javelin-analysis` |
| `JVA_PRESIGNED_URL_EXPIRES_SECONDS` | presigned URL の有効期限（秒） | `604800`（7日） |

> **重要**: `.env` は Git に**コミットしないでください**（`.gitignore` で除外済み）。

---

## 4. Streamlit での環境変数読み込み

`admin_app.py` は `python-dotenv` を使って `.env` を自動読み込みします。

```bash
pip install python-dotenv
```

または、OS 環境変数として直接設定することもできます:

```bash
export JVA_BUCKET=your-bucket-name
export AWS_REGION=ap-northeast-1
streamlit run admin_app.py
```

---

## 5. S3 キー構造

アップロードされた成果物の S3 キーは以下の構造になります:

```
{JVA_S3_PREFIX}/
├── jobs/
│   └── {job_id}/
│       ├── docs/          # 説明書 PDF
│       ├── videos/        # 解析済み動画
│       ├── reports/       # レポート PDF
│       ├── frames/        # 代表フレーム画像
│       ├── phase_frames/  # フェーズ別フレーム画像
│       ├── graphs/        # グラフ画像
│       ├── zip/           # 納品 ZIP
│       ├── data/          # CSV / JSON（開発用）
│       └── delivery/      # 納品ページ HTML
└── comparisons/
    └── {comparison_id}/
        ├── reports/       # 比較レポート PDF
        ├── images/        # 比較画像
        ├── zip/           # 比較パッケージ ZIP
        └── delivery/      # 比較納品ページ HTML
```

> S3 キーに個人名・学校名などの個人情報を含めないよう設計されています。

---

## 6. 動作確認

### 設定確認

```python
from src.storage.s3_storage import is_s3_configured, get_s3_config
print(is_s3_configured())   # True になるはず
print(get_s3_config())
```

### テスト実行

```bash
C:/venvs/javelin312/Scripts/python.exe -m pytest tests/test_phase5.py -v
```

### Streamlit 管理画面での操作

1. `streamlit run admin_app.py` を起動
2. 完了済みジョブを選択
3. 「P. S3納品 / 納品URL発行」エクスパンダーを開く
4. 「📋 マニフェスト生成 / 更新」→ 成果物一覧を確認
5. 「☁️ 成果物を S3 にアップロード」→ アップロード実行
6. 「🌐 納品ページHTMLを生成して S3 にアップロード」→ URL 発行
7. 発行された URL を LINE や メールでお客様に送付

---

## 7. セキュリティ注意事項

- **バケットは必ず非公開（Block All Public Access）にしてください**
- presigned URL の有効期限は最大 7 日（`604800` 秒）を推奨
  - AWS の署名バージョン 4 の制限により、IAM ユーザーキーの場合は最大 7 日
  - IAM ロール（EC2/Lambda）の場合はさらに短い制限があります
- AWSアクセスキーをコードに直書きしないでください
- `.env` を Git にコミットしないでください
- アップロードログ（`logs/s3_upload.log`）に presigned URL は記録されません
- S3 キーに個人名・学校名などを含めないようにしてください（job_id のみを使用）

---

## 8. トラブルシューティング

| 症状 | 確認事項 |
|------|----------|
| S3 が「未設定」と表示される | `JVA_BUCKET` が設定されているか確認。プレースホルダーになっていないか確認 |
| アップロードが AccessDenied | IAM ポリシーに `s3:PutObject` 権限があるか確認 |
| presigned URL にアクセスできない | URL の有効期限が切れていないか確認。バケットが非公開設定になっているか確認 |
| boto3 が見つからない | `pip install boto3` でインストール |
| 認証エラー | `~/.aws/credentials` の設定を確認。`aws sts get-caller-identity` で確認 |
