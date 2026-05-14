# β版リリースチェックリスト

本チェックリストは、やり投げ動画解析サービスの正式β版リリース前に確認すべき項目をまとめたものです。

---

## 1. 技術・インフラ

- [ ] `configs/beta_release_config.yaml` の内容を確認した（max_testers, default_plan 等）
- [ ] `src/beta_tester.py` が正常にインポートできる
- [ ] `src/feedback_manager.py` が正常にインポートできる
- [ ] `src/improvement_log.py` が正常にインポートできる
- [ ] `server/feedback_api.py` の `POST /v1/public/feedback` が正常に動作する
- [ ] FastAPI サーバーが起動し、`GET /health` が 200 を返す
- [ ] Streamlit 管理画面 (`admin_app.py`) の「βテスター」「フィードバック」「β版KPI」タブが表示される
- [ ] Webダッシュボード（frontend）が localhost または本番 URL で表示される
- [ ] フィードバックバナーが `feedback_form_url` が設定されている場合のみ表示される
- [ ] 全テストが通過している（`pytest tests/ -q` で 454 件以上 passing）

---

## 1-B. Web受付（β版動画アップロード導線）

- [ ] `.env` が Git に含まれていないことを確認した
- [ ] `uploads/` `data/` `outputs/` が Git に追跡されていないことを確認した（`git ls-files uploads/ data/ outputs/` が空を返す）
- [ ] `frontend/node_modules/` `frontend/dist/` が Git に追跡されていないことを確認した
- [ ] `JVA_ADMIN_TOKEN` を `.env` に設定し、FastAPI を起動した
- [ ] `/upload` ページが表示される（frontend 起動済み）
- [ ] 正常な mp4 をアップロードして `receiptId` が発行される（JMA-YYYYMMDD-NNNN 形式）
- [ ] 正常な MOV をアップロードして受付できる
- [ ] 日本語ファイル名・空白入りファイル名でもアップロードできる（savedFilename は UUID ベースで保存）
- [ ] 非対応形式（.avi 等）でエラーメッセージが表示される
- [ ] 注意事項に未同意のままでは送信できない
- [ ] SNS掲載可否を選択しないと送信できない（クライアント側で弾く）
- [ ] 300MB 超の動画でサイズ超過エラーが表示される
- [ ] `uploads/YYYYMMDD/` に動画が保存されている
- [ ] `data/upload_receipts/receipts.json` に受付データが保存されている
- [ ] `filePath` が相対パスで保存されている（`uploads/YYYYMMDD/...` 形式）
- [ ] `status` が `uploaded` で保存されている
- [ ] `name` / `sns` / `event` / `snsConsent` が正しく保存されている
- [ ] `GET /api/upload-receipts`（トークンなし）が 403 または 503 を返す
- [ ] `GET /api/upload-receipts`（正しい X-Admin-Token）が 200 を返す
- [ ] 管理画面「📨 受付一覧 > 📥 Webアップロード受付一覧」にアップロードが反映される
- [ ] ファイル存在確認列が ✅ を表示する
- [ ] `status` 変更・クイックボタンが正常に動作する
- [ ] `note` / `errorMessage` の編集・保存ができる
- [ ] 「🚀 解析を実行」が動作し `outputs/{receiptId}/` に成果物が生成される
- [ ] `result.zip` が生成される
- [ ] 管理画面から `result.zip` をダウンロードできる
- [ ] 解析失敗時に管理画面がクラッシュせず `failed` ステータスとエラー内容が表示される
- [ ] 他の受付の成果物と混在しないことを `outputs/` ディレクトリ構造で確認した

---

## 2. フォーム・受付

- [ ] β版申込フォーム（Google フォームまたは同等）が作成されている
- [ ] `configs/beta_release_config.yaml` の `application_form_url` にフォーム URL を設定した
- [ ] β版フィードバックフォームが作成されている
- [ ] `configs/beta_release_config.yaml` の `feedback_form_url` にフォーム URL を設定した
- [ ] 申込フォームの回答を intake API または管理画面の受付一覧に入力するフローが確立されている

---

## 3. 運用フロー

- [ ] β版申込者の処理フロー（申込 → 受付 → βテスター作成 → 解析 → 納品 → フィードバック依頼）が文書化されている（`docs/beta_operations_manual.md` 参照）
- [ ] 管理画面から βテスターを作成・ステータス管理できることを確認した
- [ ] 解析 → ダッシュボード生成 → 納品メッセージ（`generate_beta_delivery_message`）の手順を確認した
- [ ] フィードバックが届いた際の対応フロー（確認 → 改善ログ作成）を確認した
- [ ] 重大バグ（critical）が0件であることを確認した

---

## 4. 法務・同意

- [ ] β版利用説明文（`docs/beta_user_explanation.md`）を確認した
- [ ] β版サービスが「医療診断・怪我の診断・専門的競技指導の代替ではない」ことを利用者に明示できる
- [ ] 「β版のため機能や表示に不具合が残る可能性がある」ことを利用者に明示できる
- [ ] 未成年利用者については保護者または指導者の確認を推奨している
- [ ] SNS 掲載許可と教師データ利用許可を混同しないように管理している（beta_tester.json の `sns_permission_status` と `training_data_consent` は別フィールド）
- [ ] 個人情報（氏名・連絡先・メール）をログに出力していないことを確認した

---

## 5. SNS・告知

- [ ] SNS 投稿文を確認した（`docs/social/beta_launch_posts.md`）
- [ ] 投稿文にβ版であることと免責事項が含まれている
- [ ] 投稿文に「限定 N 名」などの上限が明示されている（max_testers の値に合わせる）
- [ ] 申込フォームへのリンクが投稿文に含まれている
- [ ] 高校生向け・指導者向けなど、対象ユーザーに合わせた投稿文を選択した

---

## 6. β版卒業判断基準

以下が全て達成された時点で、正式版移行を検討する。

- [ ] β版テスター（同意済み）が 5 人以上
- [ ] フィードバック提出率が 70% 以上
- [ ] 緊急バグ（critical）が 0 件
- [ ] 納品済みジョブが 3 件以上
- [ ] 平均納品日数が 7 日以内
- [ ] 解析・PDF・ダッシュボードが安定して動作する
- [ ] 利用規約・プライバシーポリシーの法務確認が完了している

---

> **注意**: このチェックリストは随時更新してください。β版運用中に新たな確認事項が発生した場合は追記してください。
