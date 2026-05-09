# セキュリティチェックリスト (Phase 8)

本番環境へデプロイする前に、以下の項目を確認してください。

---

## 必須チェック

### 認証・APIキー

- [ ] `JVA_API_KEY` に強力なランダム文字列を設定している
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- [ ] `.env` ファイルを Git にコミットしていない（`.gitignore` に `.env` が含まれていること）
- [ ] `.env.example` に実際の機密値を書いていない
- [ ] API キーをコード中にハードコードしていない

### ネットワーク

- [ ] FastAPI（ポート 8000）はリバースプロキシ（Nginx / ALB）の背後に配置している
- [ ] Streamlit 管理画面（ポート 8501）は社内 IP またはVPN に制限している
- [ ] 本番環境でHTTPSを使用している（TLS 終端はリバースプロキシで行う）

### コンテナ

- [ ] コンテナは非 root ユーザー（uid=1001）で起動している
- [ ] 不要なポートを公開していない
- [ ] イメージのベースは定期的に更新している

### ログ

- [ ] ログに presigned URL を出力していない
- [ ] ログに APIキー・パスワードを出力していない
- [ ] ログに顧客の個人情報（氏名・連絡先）を出力していない

---

## 推奨チェック

### S3 / AWS

- [ ] AWS IAM ポリシーは最小権限（対象バケットの GetObject / PutObject のみ）
- [ ] S3 バケットはパブリックアクセスをブロックしている
- [ ] S3 バケットの暗号化（SSE-S3 または SSE-KMS）を有効化している
- [ ] presigned URL の有効期限を必要最小限に設定している（デフォルト 7日間）

### LINE

- [ ] `LINE_CHANNEL_SECRET` でリクエストの署名を検証している
- [ ] `LINE_WEBHOOK_ENABLED=false` のままで LINE を使わない場合は無効化している

### 管理画面

- [ ] `JVA_ADMIN_PASSWORD` を設定している（空の場合は認証なしでアクセス可能）
- [ ] 管理画面 URL を外部に公開していない

### データ保護

- [ ] `data/`, `logs/`, `uploads/` のバックアップを定期的に取っている
- [ ] ジョブデータに個人情報が含まれる場合の保持期間ポリシーを定めている

---

## OWASP Top 10 対応状況

| リスク | 対応状況 | 実装箇所 |
|---|---|---|
| A01: Broken Access Control | ✅ | `secrets.compare_digest()` による APIキー検証（jobs_api.py） |
| A02: Cryptographic Failures | ✅ | presigned URL は HTTPS 経由でのみ有効 |
| A03: Injection | ✅ | `subprocess` コマンドはリスト形式（シェルインジェクション回避） |
| A04: Insecure Design | ✅ | 非 root コンテナ実行、最小権限 IAM |
| A05: Security Misconfiguration | ⚠️ | `JVA_API_KEY` の設定を強く推奨（未設定でも動作する） |
| A06: Vulnerable Components | ⚠️ | `pip audit` または Dependabot で定期確認が必要 |
| A07: Auth Failures | ✅ | タイミング攻撃対策済み（compare_digest） |
| A08: Software Integrity | ✅ | requirements.txt でバージョン固定推奨 |
| A09: Logging Failures | ✅ | エラーログ集約（logs/errors.log） |
| A10: SSRF | N/A | 外部 URL 呼び出しは S3 / LINE のみ（固定ドメイン） |

---

## インシデント対応

### APIキーが漏洩した場合

1. 即座に新しい `JVA_API_KEY` を生成して `.env` を更新
2. コンテナを再起動: `docker compose restart api`
3. 旧キーでのアクセスログを確認
4. 必要に応じて S3 バケットポリシーを一時ブロック

### S3 バケットへの不正アクセスが疑われる場合

1. AWS CloudTrail でアクセスログを確認
2. IAM ポリシーを即座に無効化
3. バケットポリシーでパブリックアクセスをブロック
4. presigned URL を無効化（バケットへの直接アクセス権限を変更）
