# アノテーション設計ドキュメント（Phase 11）

## 概要

Phase 11 では、自動推定（Phase 10）と手動修正の差分を「教師データ候補」として記録・管理する
アノテーションシステムを構築します。

> ⚠️ **重要な方針**
> - アノテーションデータは競技動作の参考分析用途のみ
> - 医療診断・怪我の診断・専門的競技指導の代替ではない
> - モデル訓練は Phase 11 の範囲外（Phase 12 以降）
> - アノテーションは「完全な正解ラベル」ではなく「人間による判断記録」

---

## データモデル

### annotation.json スキーマ（schema_version: "1.0"）

```json
{
  "schema_version": "1.0",
  "annotation_id": "ann_YYYYMMDD_HHMMSS_xxxx",
  "job_id": "20260508_070156_518a",
  "comparison_id": null,
  "video_id": null,
  "source_video_path": "/path/to/video.mp4",  // ← エクスポート時は除外
  "created_at": "2026-05-11T10:00:00",
  "updated_at": "2026-05-11T10:00:00",
  "annotator": "system",
  "annotation_status": "draft",
  "dominant_arm": "right",
  "fps": 30.0,
  "total_frames": 90,
  "duration_sec": 3.0,
  "video_quality_level": "good",
  "phase_labels": { ... },
  "event_labels": { ... },
  "notes": "",
  "consent_for_training_data": "unknown",
  "sns_permission": "unknown",
  "privacy_flags": [],
  "export_status": "not_exported"
}
```

### フェーズラベル（phase_labels）

各フェーズは「範囲型」または「単点型」のラベルを持ちます。

**範囲型（start_frame / end_frame）**
- approach（助走）
- cross_step（クロスステップ）
- withdrawal（槍を引く）
- follow_through（フォロースルー）
- recovery（リカバリー）

**単点型（frame）**
- block（ブロック接地）
- release（リリース）

各ラベルのフィールド:
```json
{
  "frame": 45,         // または start_frame / end_frame
  "source": "auto",    // auto / manual / auto_corrected / imported / unknown
  "confidence": 0.85,  // 0.0〜1.0、null=不明
  "reviewed": true,    // 人間が確認済みかどうか
  "note": ""           // 任意メモ
}
```

### イベントラベル（event_labels）

特定のフレームイベントを記録します。

- `release`（リリース）
- `block_contact`（ブロック接地）

各ラベルのフィールド:
```json
{
  "frame": 45,
  "time_sec": 1.5,
  "source": "manual",
  "confidence": 0.92,
  "reviewed": true
}
```

---

## データ優先順位

同じフェーズに複数のデータソースがある場合の優先順位:

1. **phase_frames.json**（手動フレーム指定・最優先）
2. **phase_corrections.json**（管理者による手動修正）
3. **phase_detection_result.json**（自動推定結果・最低優先）

---

## ステータス遷移

```
draft → reviewing → confirmed
  ↓                    ↓
rejected             archived
```

- `draft`: 自動生成後の初期状態。人間による確認が必要
- `reviewing`: 確認中
- `confirmed`: 確定済み。教師データ候補として利用可能
- `rejected`: 除外（品質不良、同意なし等）
- `archived`: アーカイブ（長期保管）

---

## ストレージ構造

```
data/
└── annotations/
    └── ann_YYYYMMDD_HHMMSS_xxxx/
        ├── annotation.json          ← メインデータ
        └── annotation_review.pdf   ← 管理者確認PDF（生成時）
```

環境変数 `JVA_ANNOTATIONS_DIR` で保存先を上書き可能。

---

## ソースコード構成

```
src/annotation/
├── __init__.py
├── manager.py               ← CRUD・自動生成・統計
├── exporter.py              ← JSONL/CSVエクスポート
└── annotation_review_pdf.py ← 管理者確認PDF生成
configs/
└── annotation.yaml          ← 設定ファイル
```
