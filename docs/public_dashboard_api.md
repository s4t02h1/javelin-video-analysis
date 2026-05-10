# Public Dashboard API — 仕様書

Phase 14 で追加された認証不要の読み取り専用 API です。  
`dashboard_token` を知っている人のみが解析結果を閲覧できます。

---

## エンドポイント一覧

| メソッド | パス | 認証 | 説明 |
|---|---|---|---|
| `GET` | `/v1/public/healthz` | なし | ヘルスチェック |
| `GET` | `/v1/public/dashboards/{dashboard_token}` | なし（token のみ） | マニフェスト取得 |

---

## GET /v1/public/healthz

### レスポンス例

```json
{
  "status": "ok",
  "api": "public-dashboards",
  "enabled": true,
  "manifest_module": true
}
```

---

## GET /v1/public/dashboards/{dashboard_token}

### パスパラメータ

| パラメータ | 型 | 説明 |
|---|---|---|
| `dashboard_token` | string | `"dash_"` で始まる 27 文字前後のトークン |

### レスポンス

#### 200 OK — マニフェスト JSON

```json
{
  "schema_version": "1.0",
  "dashboard_token": "dash_xxxxxxxxxxxxxxxxxxxx",
  "job_id": "20260510_120000_abcd",
  "dashboard_type": "single",
  "display_name": "山田 太郎",
  "plan_label": "スタンダード",
  "delivered_at": "2026-05-10",
  "generated_at": "2026-05-10T12:00:00",
  "token_expires_at": "2026-05-24T12:00:00+00:00",
  "url_expires_at": "",
  "metrics_version": "0.1.0",
  "overall_quality": "good",
  "metrics_reliability": "high",
  "sections": {
    "videos": true,
    "phase_images": true,
    "metrics": true,
    "graphs": false,
    "downloads": true,
    "research_data": true
  },
  "notices": [
    "この解析結果は動画上の姿勢推定をもとにした参考資料です。",
    "医療診断・怪我の診断・専門的競技指導の代替ではありません。"
  ],
  "videos": [
    {
      "key": "skeleton",
      "label": "骨格線つき動画",
      "description": "姿勢推定点を骨格線として重ねた動画です。",
      "filename": "analysis_skeleton.mp4",
      "url": "https://s3.example.com/presigned-url...",
      "content_type": "video/mp4",
      "available": true
    }
  ],
  "phase_images": [
    {
      "phase_key": "release",
      "label": "🎯 リリース",
      "description": "投擲フェーズ。",
      "tip": "手首高さ・速度は相対参考値です。",
      "filename": "release_frame.png",
      "url": "https://s3.example.com/presigned-url...",
      "frame_num": 100,
      "frame_time_sec": 3.33,
      "available": true
    }
  ],
  "key_metrics": [
    {
      "key": "release_wrist_height_normalized",
      "label": "リリース時の手首高さ（相対）",
      "value": 1.24,
      "unit": "body_scale",
      "reliability": "high",
      "reliability_label": "信頼度：高め",
      "reliability_description": "動画内の姿勢推定点が比較的安定している指標です。",
      "caution": "動画上の座標から算出した参考指標です。",
      "note": ""
    }
  ],
  "detail_metrics": {
    "release": [...],
    "block": [...],
    "trunk": [...],
    "arm": [...],
    "trajectory": [...]
  },
  "graphs": [],
  "downloads": {
    "intro": [{ "label": "解析動画の見方.pdf", "filename": "video_instruction.pdf", "url": "...", "available": true, "is_research": false, "category": "intro" }],
    "athlete": [...],
    "advanced": [...],
    "coach": [...],
    "packages": [...],
    "research": [
      { "label": "姿勢推定データ CSV", "filename": "pose_landmarks.csv", "url": "...", "available": true, "is_research": true, "category": "research" }
    ]
  },
  "disclaimer": "本解析は動画から取得した姿勢推定データをもとにした参考資料です。...",
  "inquiry_info": {
    "job_id": "20260510_120000_abcd",
    "delivered_at": "2026-05-10",
    "plan_label": "スタンダード"
  }
}
```

#### 404 Not Found

```json
{ "detail": "ダッシュボードが見つかりません。" }
```

以下のケースで返ります：
- トークンが存在しない
- トークン形式が不正（`dash_` で始まらない、または 80 文字超）
- マニフェストが未生成

#### 410 Gone — トークン期限切れ

```json
{
  "detail": "このダッシュボードの公開期限が切れています。",
  "token_expires_at": "2026-05-24T12:00:00+00:00",
  "code": "token_expired"
}
```

#### 503 Service Unavailable

```json
{ "detail": "パブリックダッシュボード API は無効です。" }
```

環境変数 `JVA_PUBLIC_DASHBOARD_ENABLED=false` のとき。

---

## セキュリティ設計

### トークン形式

```
dash_<22文字の URL-safe base64>
```

- `secrets.token_urlsafe(16)` で生成（128 bit エントロピー）
- URL に `job_id` を含まない
- トークンインデックス（`jobs/_token_index.json`）はサーバー内部でのみ管理

### レスポンスのサニタイズ

`GET /v1/public/dashboards/{token}` のレスポンスから以下を除去します：

| フィールド | 除去理由 |
|---|---|
| `s3_key` | S3 バケット構造の露出防止 |
| `relative_path` | サーバー内部パスの露出防止 |

### 個人情報

マニフェストに含まれる個人情報は `display_name`（氏名のみ）に限定しています。  
メールアドレス・電話番号・住所は含みません。

---

## 環境変数

| 変数 | デフォルト | 説明 |
|---|---|---|
| `JVA_PUBLIC_DASHBOARD_ENABLED` | `true` | API を有効にするか |
| `JVA_DASHBOARD_TOKEN_EXPIRES_DAYS` | `14` | トークン有効期間（日） |
| `JVA_CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | 許可する CORS オリジン（カンマ区切り） |
| `JVA_FRONTEND_BASE_URL` | `""` | フロントエンドのベース URL（管理画面 URL 生成用） |

---

## CORS 設定

`server/app.py` で `CORSMiddleware` を設定しています：

```python
_CORS_ORIGINS = [o.strip() for o in os.getenv("JVA_CORS_ORIGINS", "...").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["X-JVA-API-Key", "Authorization", "Content-Type"],
)
```

フロントエンドのオリジンを `JVA_CORS_ORIGINS` に追加してください。

---

## レート制限

現時点では実装していません。本番環境では Nginx / Cloudflare / API Gateway のレート制限を使用してください。

---

## フロントエンドとの連携

```
スマホ → /dashboard/dash_xxx
          ↓
    DashboardPage.tsx
          ↓ fetchDashboard(token)
    GET /v1/public/dashboards/dash_xxx
          ↓
    マニフェスト JSON
          ↓
    各セクションを表示
```

フロントエンドは Vite 5 + React 18 + TypeScript 5 で実装されています。  
詳細は [frontend/README.md](../frontend/README.md) を参照してください。
