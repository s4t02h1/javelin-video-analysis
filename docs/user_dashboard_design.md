# ユーザー向けダッシュボード 設計ドキュメント (Phase 13)

## 概要

Phase 13 では、既存のPDF・ZIP納品に加えて、スマートフォンブラウザで見やすいHTMLダッシュボードを生成します。

> **重要な方針**: ダッシュボードに表示される解析指標はすべて**参考値**です。医療診断・怪我の診断・専門的競技指導の代替にはなりません。

---

## アーキテクチャ

```
job_dir/
├── customer_info.json          ← 選手情報
├── job.json                    ← ジョブメタデータ（dashboard_url を追記）
├── phase_frames.json           ← フェーズ区切りフレーム番号
├── report/
│   ├── advanced_metrics.json   ← 高度解析指標 (Phase 12)
│   ├── frames/                 ← 代表フレーム画像（PNGまたはJPG）
│   ├── graphs/                 ← グラフ画像 PNG
│   └── user_dashboard.html     ← ← 生成物
└── output/
    └── *.mp4                   ← 解析動画
```

---

## テンプレートシステム

`templates/user_dashboard.html` を使用します。Jinja2 ではなく Python の `str.replace()` で変数を置換します。

```python
html = template.replace("{{ title }}", "解析ダッシュボード")
```

### 利用可能な変数

| プレースホルダー | 内容 |
|---|---|
| `{{ title }}` | ページタイトル |
| `{{ job_id }}` | ジョブID |
| `{{ athlete_name_display }}` | 選手名（customer_info.json より） |
| `{{ plan_display }}` | プラン表示名 |
| `{{ plan_name }}` | プラン名（rawキー） |
| `{{ delivered_at }}` | 作成日時 |
| `{{ generated_at }}` | ダッシュボード生成日時 |
| `{{ metrics_version }}` | 指標バージョン |
| `{{ url_expires_at_display }}` | URL有効期限 |
| `{{ video_section }}` | 動画セクションHTML |
| `{{ phase_images_section }}` | フェーズ画像セクションHTML |
| `{{ metrics_section }}` | 指標カードセクションHTML |
| `{{ graphs_section }}` | グラフセクションHTML |
| `{{ downloads_section }}` | ダウンロードセクションHTML |

---

## セクションビルダー

| 関数 | 役割 |
|---|---|
| `_build_video_section()` | presigned URL または相対パスで動画埋め込み |
| `_build_phase_images_section()` | 各フェーズの代表フレーム画像（Base64埋め込み） |
| `_build_metrics_section()` | 主要指標カード（2カラムグリッド）+ 詳細 `<details>` |
| `_build_graphs_section()` | グラフ画像（Base64埋め込み） |
| `_build_downloads_section()` | カテゴリ分けされたダウンロードリンク |

---

## 画像埋め込み

すべての画像は Base64 データURIとして埋め込まれます。これにより、生成された HTML は単一ファイルとして自己完結し、サーバー不要でスマホに送るだけで表示できます。

```python
data = base64.b64encode(img_path.read_bytes()).decode("ascii")
return f"data:image/png;base64,{data}"
```

---

## モバイルファーストデザイン

- `max-width: 720px` のコンテナ、余白付き中央寄せ
- フォントサイズ: 本文 15px、指標値 1.4rem
- 指標グリッド: 2カラム（モバイル）→ 1カラム（超小型）
- 外部CDN依存ゼロ（フォント・JS・アイコン等を外部から読み込まない）
- `<video>` に `playsinline` 属性（iOSフルスクリーン自動化防止）

---

## 注意事項バナー

ダッシュボード上部に常時表示される注意書き:

> ⚠️ 本ダッシュボードに表示される解析結果は参考指標です。撮影角度・距離・解像度の違いにより精度が変動します。身体の異常・怪我・競技指導に関する判断には、必ず専門家（医師・コーチ等）にご相談ください。

---

## 出力先

```
job_dir/report/user_dashboard.html
```

S3アップロード後は `job.json` に以下フィールドが追記されます:

```json
{
  "user_dashboard_url": "https://...",
  "user_dashboard_s3_key": "jobs/JOB_ID/report/user_dashboard.html",
  "dashboard_url_expires_at": "2026-05-24T00:00:00",
  "dashboard_generated_at": "2026-05-10T12:00:00",
  "dashboard_upload_status": "complete"
}
```
