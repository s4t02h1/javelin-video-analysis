# 高度解析指標 — エクスポート形式仕様

## 概要

`src/analysis/advanced_metrics_exporter.py` が生成するエクスポートファイルの形式を説明します。

---

## 出力ファイル

| ファイル | 場所 | 形式 | 用途 |
|----------|------|------|------|
| `advanced_metrics.json` | `exports/metrics/` | JSON 配列 | 全ジョブのまとめ |
| `advanced_metrics.csv` | `exports/metrics/` | CSV (UTF-8-sig) | Excel / スプレッドシート用 |
| `advanced_metrics.jsonl` | `exports/metrics/` | JSONL (1行=1ジョブ) | ストリーム処理・機械学習前処理 |

---

## CSV カラム一覧

| カラム名 | 型 | 説明 |
|----------|----|------|
| `job_id` | str | ジョブ ID |
| `dominant_arm` | str | 利き腕（`right` / `left`） |
| `fps` | float | 動画フレームレート |
| `metrics_version` | str | 指標バージョン（例: `0.1.0`） |
| `generated_at` | str | 計算日時（ISO 8601） |
| `status` | str | 計算ステータス（`ok` / `partial` / `failed` / `no_data`） |
| `overall_quality` | str | 動画全体品質（`high` / `medium` / `low`） |
| `metrics_reliability` | str | 指標の信頼度（`high` / `medium` / `low` / `unknown`） |
| `pose_detection_rate` | float | 姿勢検出率（0.0–1.0） |
| `release_wrist_height_normalized` | float | リリース時手首高さ（正規化） |
| `release_wrist_velocity_normalized` | float | リリース時手首速度（正規化） |
| `release_arm_extension_ratio` | float | リリース時腕伸展率（0–1） |
| `release_trunk_angle_estimate` | float | リリース時体幹前傾角（度、2D推定） |
| `release_shoulder_line_tilt` | float | リリース時肩ライン傾き（度） |
| `block_to_release_time_sec` | float | ブロック〜リリース時間（秒） |
| `hip_deceleration_ratio` | float | ブロック時腰減速比 |
| `throwing_wrist_peak_velocity` | float | 手首最大速度（正規化相対値） |
| `arm_pullback_distance_estimate` | float | 槍引き距離推定（正規化） |
| `withdrawal_to_release_time_sec` | float | 槍引き開始〜リリース時間（秒） |
| `approach_duration_sec` | float | 助走フェーズ時間（秒） |
| `cross_step_duration_sec` | float | クロスステップ時間（秒） |
| `withdrawal_duration_sec` | float | 槍引きフェーズ時間（秒） |
| `release_duration_sec` | float | リリースフェーズ時間（秒） |

> **注**: 値が計算できない場合は `null`（JSON）または空（CSV）になります。

---

## JSONL 形式の例

1 行 = 1 ジョブ。改行区切り JSON。

```jsonl
{"job_id":"20260508_054525_147f","dominant_arm":"right","fps":30.0,"release_wrist_height_normalized":1.12,...}
{"job_id":"20260508_054854_fffe","dominant_arm":"right","fps":60.0,"release_wrist_height_normalized":null,...}
```

### 重複除去ルール

JSONL ファイルへの追記時、同じ `job_id` が存在する場合は古いレコードを削除して新しいものに置き換えます。

---

## バッチエクスポート

```python
from src.analysis.advanced_metrics_exporter import export_all_advanced_metrics
from pathlib import Path

export_all_advanced_metrics(Path("jobs/"))
# → exports/metrics/advanced_metrics.json
# → exports/metrics/advanced_metrics.csv
# → exports/metrics/advanced_metrics.jsonl
```

## 単ジョブエクスポート

```python
from src.analysis.advanced_metrics_exporter import export_advanced_metrics_for_job
from pathlib import Path

export_advanced_metrics_for_job(Path("jobs/20260508_054525_147f/"))
# → exports/metrics/advanced_metrics.jsonl に追記
```

---

## 注意事項

- CSV は Excel で開くために **UTF-8-sig**（BOM付き）で出力されます
- エクスポートされるデータに **個人情報（氏名・メール・電話番号等）は含まれません**
- `job_id` のみが識別子として含まれます
- 指標値はすべて 2D 動画座標から算出した参考値です
