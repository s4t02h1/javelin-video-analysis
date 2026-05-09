# アノテーションエクスポート形式（Phase 11）

## 出力ファイル一覧

| ファイル | 形式 | 内容 |
|---------|------|------|
| `phase_labels.jsonl` | JSON Lines | フェーズラベル（1行1アノテーション） |
| `phase_labels.csv` | CSV | フェーズラベル（フラット） |
| `event_labels.jsonl` | JSON Lines | イベントラベル（1行1イベント） |
| `export_log.json` | JSON | エクスポートログ |

デフォルト出力先: `exports/annotations/`（`configs/annotation.yaml` の `export.output_dir` で変更可）

---

## phase_labels.jsonl フィールド定義

```json
{
  "annotation_id": "ann_20260511_120000_abcd",
  "job_id": "20260508_070156_518a",
  "comparison_id": null,
  "video_id": null,
  "dominant_arm": "right",
  "fps": 30.0,
  "total_frames": 90,
  "duration_sec": 3.0,
  "video_quality_level": "good",
  "consent_for_training_data": "allowed",
  "privacy_flags": [],
  "export_allowed": true,

  // フェーズラベル（範囲型: start_frame / end_frame）
  "approach_start_frame": 0,
  "approach_end_frame": 15,
  "approach_source": "auto",
  "approach_confidence": 0.82,
  "approach_reviewed": false,

  "cross_step_start_frame": 16,
  "cross_step_end_frame": 30,
  ...

  // フェーズラベル（単点型: frame）
  "block_frame": 30,
  "block_source": "auto_corrected",
  "block_confidence": 0.91,
  "block_reviewed": true,

  "release_frame": 45,
  "release_source": "manual",
  "release_confidence": null,
  "release_reviewed": true,

  // イベントラベル（便利フラット化）
  "event_release_frame": 45,
  "event_release_time_sec": 1.5,
  "event_release_source": "manual",
  "event_release_reviewed": true,

  "event_block_contact_frame": 30,
  "event_block_contact_time_sec": 1.0,
  "event_block_contact_source": "auto",
  "event_block_contact_reviewed": false,

  // よく使うキー（重複）
  "release_frame": 45,
  "block_frame": 30,
  "cross_step_start_frame": 16,
  "cross_step_end_frame": 30
}
```

---

## event_labels.jsonl フィールド定義

1行が1イベントに対応します。

```json
{
  "annotation_id": "ann_20260511_120000_abcd",
  "job_id": "20260508_070156_518a",
  "event_name": "release",
  "frame": 45,
  "time_sec": 1.5,
  "source": "manual",
  "reviewed": true,
  "dominant_arm": "right",
  "fps": 30.0,
  "total_frames": 90
}
```

`event_name` の種類:
- `release`（リリース）
- `block_contact`（ブロック接地）

---

## source フィールドの値

| 値 | 意味 |
|----|------|
| `auto` | 自動推定のみ（人間による確認なし） |
| `manual` | 人間が手動で指定 |
| `auto_corrected` | 自動推定後に人間が修正 |
| `imported` | 外部インポート |
| `unknown` | 不明 |

---

## エクスポートフィルタ

以下のアノテーションは除外されます:

1. `annotation_status != "confirmed"`
2. `consent_for_training_data == "denied"`
3. `consent_for_training_data == "unknown"`（デフォルト、設定変更可）
4. `privacy_flags` に `training_data_excluded` が含まれる

---

## 除外されるフィールド

以下は保存されますが、エクスポートには含まれません:

- `source_video_path`（動画ファイルパス）
- `schema_version`（内部バージョン）
- 個人情報（氏名、学校名、連絡先など）

`consent_for_training_data == "anonymous_only"` の場合:
- `comparison_id`
- `video_id`

`anonymize_job_id == true`（設定）の場合:
- `job_id` が SHA-256 ハッシュの先頭12文字に置換されます

---

## Python での読み込み例

```python
import json
from pathlib import Path

# JSONL 読み込み
records = []
with open("exports/annotations/phase_labels.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        records.append(json.loads(line))

print(f"読み込み件数: {len(records)}")

# リリースフレームのあるレコードのみ
with_release = [r for r in records if r.get("release_frame") is not None]
print(f"リリースラベルあり: {len(with_release)} 件")
```

```python
import pandas as pd

# CSV 読み込み
df = pd.read_csv("exports/annotations/phase_labels.csv", encoding="utf-8-sig")
print(df.head())
```
