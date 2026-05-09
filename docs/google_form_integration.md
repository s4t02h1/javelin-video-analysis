# Google フォーム連携ガイド

Javelin Video Analysis への解析依頼を **Google フォーム** で受け付け、
**Google Apps Script** 経由で FastAPI に自動送信する方法を説明します。

---

## 1. Googleフォームの推奨質問項目

| 質問タイトル（推奨）              | 種類             | 必須 | マッピング先フィールド              |
|----------------------------------|------------------|------|-----------------------------------|
| 名前またはニックネーム           | テキスト         | 推奨 | `name_or_nickname`                |
| 連絡先（SNS / LINE名）           | テキスト         | 推奨 | `contact`                         |
| Instagramアカウント（任意）      | テキスト         | 任意 | `instagram_account`               |
| 年齢区分                         | ラジオボタン     | 推奨 | `age_group`                       |
| 性別（任意）                     | ラジオボタン     | 任意 | `gender_optional`                 |
| 利き腕                           | ラジオボタン     | 推奨 | `dominant_arm` (right/left/unknown)|
| 身長（cm）                       | テキスト（数値） | 任意 | `height_cm`                       |
| 競技歴                           | テキスト         | 任意 | `experience_years`                |
| 自己ベスト                       | テキスト         | 任意 | `personal_best`                   |
| 所属区分                         | ラジオボタン     | 任意 | `affiliation_type`                |
| 動画本数                         | テキスト（数値） | 推奨 | `video_count`                     |
| 動画の提出方法                   | ラジオボタン     | 推奨 | `video_submission_method`         |
| 撮影角度                         | ラジオボタン     | 推奨 | `shooting_angle`                  |
| 動画種別                         | ラジオボタン     | 任意 | `video_type`                      |
| スローモーション撮影か           | チェックボックス | 任意 | `is_slow_motion`                  |
| 一番見てほしい点                 | テキスト（長文） | 推奨 | `main_request`                    |
| 希望プラン                       | ラジオボタン     | 推奨 | `desired_plan`                    |
| 解析は参考資料であることへの同意 | チェックボックス | 必須 | `consent_reference_analysis`      |
| 医療診断でないことへの同意       | チェックボックス | 必須 | `consent_not_medical`             |
| 専門的競技指導の代替でないことへの同意 | チェックボックス | 必須 | `consent_not_coaching_replacement`|
| 動画品質により精度が変わることへの同意 | チェックボックス | 推奨 | `consent_accuracy_depends_on_video`|
| 納品まで時間がかかる場合への同意 | チェックボックス | 推奨 | `consent_delivery_may_take_time`  |
| SNS掲載は別途許可制であることへの同意 | チェックボックス | 推奨 | `consent_sns_requires_permission` |

> **注意:** 氏名・連絡先・Instagram アカウントなどの個人情報は Google フォームの回答スプレッドシートに保存されます。
> アクセス権限を適切に管理し、不要になったデータは速やかに削除してください。

---

## 2. Google スプレッドシートとの連携

1. フォームの「回答」タブ → スプレッドシートアイコン → 新しいスプレッドシートを作成
2. 回答が自動的にスプレッドシートへ記録されます
3. スプレッドシートの「拡張機能」→「Apps Script」からスクリプトを追加します

---

## 3. Apps Script から FastAPI へ POST する方法

スクリプトエディタに以下を貼り付けてください。

```javascript
// =====================================================================
// Javelin Video Analysis — Google フォーム → FastAPI 連携スクリプト
// onFormSubmit トリガーを設定してください（フォーム送信時に自動実行）
// =====================================================================

var JVA_API_URL = "https://your-server.example.com/v1/intakes";  // ← 実際のURLに変更
var JVA_API_KEY = "";  // ← PropertiesService で管理を推奨（直接書かない）

/**
 * フォーム送信時に呼ばれるトリガー関数
 * スクリプトエディタの「トリガー」から onFormSubmit イベントに設定してください。
 */
function onFormSubmit(e) {
  try {
    var payload = buildPayload(e);
    var result  = postToJva(payload);
    Logger.log("JVA intake 作成成功: " + JSON.stringify(result));
  } catch (err) {
    Logger.log("JVA intake 送信エラー: " + err.message);
    // 必要に応じてメール通知なども追加できます
  }
}

/**
 * フォーム回答からペイロードを組み立てる
 */
function buildPayload(e) {
  // APIキーは ScriptProperties に保存することを推奨
  var apiKey = PropertiesService.getScriptProperties().getProperty("JVA_API_KEY") || JVA_API_KEY;

  var responses = e.response.getItemResponses();
  var raw = {};
  responses.forEach(function(item) {
    raw[item.getItem().getTitle()] = item.getResponse();
  });

  // フィールドマッピング（質問タイトルに応じて調整してください）
  var payload = {
    source:               "google_form",
    name_or_nickname:     raw["名前またはニックネーム"]  || "",
    contact:              raw["連絡先（SNS / LINE名）"] || "",
    instagram_account:    raw["Instagramアカウント（任意）"] || "",
    age_group:            raw["年齢区分"]         || "",
    gender_optional:      raw["性別（任意）"]      || "",
    dominant_arm:         mapDominantArm(raw["利き腕"]),
    height_cm:            parseFloat(raw["身長（cm）"]) || null,
    experience_years:     raw["競技歴"]            || "",
    personal_best:        raw["自己ベスト"]         || "",
    affiliation_type:     raw["所属区分"]           || "",
    video_count:          parseInt(raw["動画本数"]) || 1,
    video_submission_method: raw["動画の提出方法"]  || "",
    shooting_angle:       mapShootingAngle(raw["撮影角度"]),
    video_type:           raw["動画種別"]           || "",
    is_slow_motion:       raw["スローモーション撮影か"] === "はい",
    main_request:         raw["一番見てほしい点"]   || "",
    desired_plan:         mapPlan(raw["希望プラン"]),
    consent_reference_analysis:        isChecked(raw["解析は参考資料であることへの同意"]),
    consent_not_medical:               isChecked(raw["医療診断でないことへの同意"]),
    consent_not_coaching_replacement:  isChecked(raw["専門的競技指導の代替でないことへの同意"]),
    consent_accuracy_depends_on_video: isChecked(raw["動画品質により精度が変わることへの同意"]),
    consent_delivery_may_take_time:    isChecked(raw["納品まで時間がかかる場合への同意"]),
    consent_sns_requires_permission:   isChecked(raw["SNS掲載は別途許可制であることへの同意"]),
    raw_payload: raw,  // フォーム全体を生データとして保存
  };
  return payload;
}

/**
 * JVA API に POST する
 */
function postToJva(payload) {
  var apiKey = PropertiesService.getScriptProperties().getProperty("JVA_API_KEY") || JVA_API_KEY;
  var options = {
    method:      "post",
    contentType: "application/json",
    headers: {
      "X-JVA-API-Key": apiKey
    },
    payload:     JSON.stringify(payload),
    muteHttpExceptions: true,
  };
  var response = UrlFetchApp.fetch(JVA_API_URL, options);
  var code = response.getResponseCode();
  if (code < 200 || code >= 300) {
    throw new Error("API エラー HTTP " + code + ": " + response.getContentText());
  }
  return JSON.parse(response.getContentText());
}

// ── ヘルパー関数 ─────────────────────────────────────────────────────────────

function mapDominantArm(val) {
  if (!val) return "unknown";
  if (val.indexOf("右") >= 0) return "right";
  if (val.indexOf("左") >= 0) return "left";
  return "unknown";
}

function mapShootingAngle(val) {
  if (!val) return "unknown";
  if (val.indexOf("側面") >= 0) return "side";
  if (val.indexOf("斜め") >= 0) return "diagonal_back";
  if (val.indexOf("正面") >= 0) return "front";
  return "unknown";
}

function mapPlan(val) {
  if (!val) return "undecided";
  if (val.indexOf("フルレポート") >= 0 || val.indexOf("full") >= 0) return "full_report";
  if (val.indexOf("データシート") >= 0 || val.indexOf("data") >= 0) return "data_sheet";
  if (val.indexOf("無料") >= 0 || val.indexOf("プレビュー") >= 0) return "free_preview";
  if (val.indexOf("比較") >= 0) return "comparison";
  return "undecided";
}

function isChecked(val) {
  return val === true || val === "はい" || val === "同意します" || val === "TRUE";
}
```

---

## 4. APIキーの設定方法

### 方法A: Apps Script の PropertiesService を使う（推奨）

スクリプトエディタで「プロジェクトの設定」→「スクリプト プロパティ」に追加:

| プロパティ名 | 値 |
|---|---|
| `JVA_API_KEY` | あなたのAPIキー |

スクリプト内からは `PropertiesService.getScriptProperties().getProperty("JVA_API_KEY")` で参照できます。

### 方法B: サーバー側 .env ファイル

サーバーの `.env` ファイルに設定:

```
JVA_API_KEY=your-secret-key-here
JVA_ENABLE_INTAKE_API=true
```

> **重要:** APIキーをスクリプトに直接書かないでください。
> Google スプレッドシートを共有した場合にキーが漏洩します。

---

## 5. 送信するJSONの例

```json
{
  "source": "google_form",
  "name_or_nickname": "やり投げ太郎",
  "contact": "@javelin_taro",
  "age_group": "大学生",
  "dominant_arm": "right",
  "height_cm": 178.5,
  "video_count": 2,
  "shooting_angle": "side",
  "main_request": "助走のリズムと最終ステップを見てほしい",
  "desired_plan": "full_report",
  "consent_reference_analysis": true,
  "consent_not_medical": true,
  "consent_not_coaching_replacement": true,
  "consent_accuracy_depends_on_video": true,
  "consent_delivery_may_take_time": true,
  "consent_sns_requires_permission": true,
  "raw_payload": { "...": "フォーム全体の生データ" }
}
```

---

## 6. よくあるエラー

| エラー | 原因 | 対処 |
|---|---|---|
| `HTTP 401` | APIキーが無効または未設定 | `JVA_API_KEY` を確認 |
| `HTTP 503` | `JVA_ENABLE_INTAKE_API=false` | `.env` で `true` に変更 |
| `HTTP 500` | サーバー内部エラー | サーバーログを確認 |
| `TypeError: Cannot read property` | フォームの質問名と Apps Script のキーが不一致 | スクリプトの `buildPayload` を修正 |
| `UrlFetchApp quota exceeded` | API 呼び出し上限 | Google ドメインの割り当てを確認 |

---

## 7. 個人情報の取り扱いについて

- 氏名・連絡先・Instagram アカウントなどの個人情報は **サーバーのログに出力されません**
- `intake.json` にはこれらの情報が保存されます。アクセス制御を適切に行ってください
- Google フォームの回答スプレッドシートは **編集権限を持つ人を最小限に** してください
- 不要になったデータは速やかに削除してください
- `raw_payload` には送信されたフォーム全体が保存されます。個人情報が含まれる場合があります

---

## 8. 同意事項の設計

フォームに以下の同意チェックボックスを設置することを推奨します（必須）:

1. **解析は参考資料です** — 「本解析は、動画から取得した姿勢推定データをもとにした参考資料であることに同意します」
2. **医療診断ではありません** — 「本解析は医療診断・怪我の診断・治療を目的とするものではないことに同意します」
3. **競技指導の代替ではありません** — 「本解析は専門的な競技指導を代替するものではないことに同意します」
4. **精度は動画に依存します** — 「動画の画質・撮影角度・照明により解析精度が変わる場合があることに同意します」
5. **納品まで時間がかかる場合があります** — 「解析・納品まで数日かかる場合があることに同意します」
6. **SNS掲載は別途許可制です** — 「SNS（Instagram等）への解析事例掲載は別途確認のうえ行われることに同意します」

> **推奨:** 同意項目は必須チェックにし、未チェックの場合はフォームを送信できないようにしてください。
> これにより、管理画面での `consent_*` フィールドが `true` になります。
