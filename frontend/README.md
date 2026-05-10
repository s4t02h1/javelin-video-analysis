# Javelin Video Analysis — フロントエンド (Phase 14)

Vite + React + TypeScript によるモバイルファーストのダッシュボードビューアー。

## セットアップ

```bash
cd frontend
cp .env.example .env.local
# .env.local の VITE_API_BASE_URL を設定
npm install
npm run dev
```

ブラウザで `http://localhost:5173/dashboard/<token>` を開いてください。

## 環境変数

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `VITE_API_BASE_URL` | `http://localhost:8000` | バックエンド FastAPI の URL |
| `VITE_APP_NAME` | `Javelin Video Analysis` | アプリ表示名 |

## ルーティング

| パス | 説明 |
|------|------|
| `/dashboard/:token` | ダッシュボード閲覧 |
| `/expired` | 期限切れ画面 |
| `*` | 404 画面 |

## ビルド

```bash
npm run build
# dist/ に静的ファイルが生成される
```

静的ファイルは FastAPI の `StaticFiles` マウントまたは nginx/CloudFront で配信できます。

## API

バックエンドの `GET /v1/public/dashboards/{token}` を呼び出します。

詳細は [`docs/public_dashboard_api.md`](../docs/public_dashboard_api.md) を参照。

## 技術スタック

- Vite 5 + React 18 + TypeScript 5
- react-router-dom v6
- 外部 CSS フレームワーク不使用（vanilla CSS）
- 最大横幅 720px のモバイルファースト設計
