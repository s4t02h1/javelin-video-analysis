# Phase 12: 高度解析指標 — 設計ドキュメント

## 概要

Phase 12 では、MediaPipe 等で取得した姿勢推定データ（`pose_landmarks.csv`）と
Phase 10/11 で整備したフェーズ・イベントラベルを用いて、やり投げ動作を
競技的に理解しやすい参考指標として算出・提供します。

> **重要**: 本指標はすべて **参考値** です。  
> 2D 動画座標から算出した推定値であり、実際の距離・速度・角度とは異なる場合があります。  
> 医療診断・専門的競技指導の代替として使用しないでください。

---

## ファイル構成

```
src/analysis/
    advanced_metrics.py             # 指標計算メインモジュール
    advanced_metrics_report.py      # PDF レポート生成
    advanced_metrics_exporter.py    # CSV/JSON/JSONL エクスポート
    comparison_advanced_metrics.py  # 2ジョブ比較指標
    comparison_advanced_report.py   # 比較 PDF レポート生成

configs/
    advanced_metrics.yaml           # 挙動設定
    metric_labels.yaml              # 日本語ラベル・説明・注意文

docs/
    advanced_metrics_design.md      # 本ファイル
    metrics_interpretation_guide.md # 各指標の読み方
    metrics_reliability.md          # 信頼度スコアの説明
    advanced_metrics_export_format.md # エクスポート形式仕様
```

---

## アーキテクチャ

```
pose_landmarks.csv
phase_frames.json / annotation / quality_report.json
customer_info.json
        │
        ▼
compute_advanced_metrics()          ← src/analysis/advanced_metrics.py
        │
        ├─ _resolve_phase_frames()  ← annotation > phase_frames > detection
        ├─ _compute_release_metrics()
        ├─ _compute_block_metrics()
        ├─ _compute_trunk_metrics()
        ├─ _compute_arm_metrics()
        ├─ _compute_trajectory_metrics()
        ├─ _compute_phase_metrics()
        └─ _comparison_ready_metrics()
                │
                ▼
        advanced_metrics.json       ← report/advanced_metrics.json
                │
        ┌───────┴────────┐
        ▼                ▼
  PDF レポート       CSV エクスポート
  (advanced_metrics_report.pdf)  (exports/metrics/)
```

---

## フェーズフレーム解決の優先順位

`_resolve_phase_frames()` が次の順番でデータを探します:

1. **annotation** — 人間が確認・確定したアノテーション（最優先）
2. **phase_frames.json** — Phase 10 自動推定結果
3. **corrections** — detection_result 内の手動補正
4. **detection** — detection_result 内の自動推定

データが見つからない場合、対応する指標は `available: false` となります。

---

## 指標カテゴリ

### リリース関連指標 (`release_metrics`)

リリースフレーム時点のスナップショット指標。

| キー | 説明 | 正規化 |
|------|------|--------|
| `release_wrist_height_normalized` | リリース時の手首高さ | 体スケール正規化（1 = 肩幅相当） |
| `release_wrist_velocity_normalized` | リリース時の手首速度 | 体スケール正規化 |
| `release_arm_extension_ratio` | 腕の伸展率（0-1） | なし（比率） |
| `release_trunk_angle_estimate` | 体幹前傾角度（2D推定）| 度 |
| `release_shoulder_line_tilt` | 肩ラインの傾き（2D）| 度 |

### ブロック関連指標 (`block_metrics`)

ブロックフレーム前後の動作分析。

| キー | 説明 |
|------|------|
| `block_to_release_time_sec` | ブロック〜リリース間の時間（秒） |
| `hip_deceleration_ratio` | ブロック時の腰減速率 |
| `shoulder_rotation_change_around_block` | ブロック前後の肩ライン角変化 |
| `hip_rotation_change_around_block` | ブロック前後の腰ライン角変化 |

### 体幹・肩腰分離指標 (`trunk_metrics`)

肩・腰の相対的な動きを2Dで推定する指標。

> **注意**: 3次元回旋角の正確な測定ではありません。2D投影された推定値です。

| キー | 説明 |
|------|------|
| `shoulder_hip_separation_angle_estimate_at_block` | ブロック時の肩腰分離角（2D推定） |
| `shoulder_hip_separation_angle_estimate_at_release` | リリース時の肩腰分離角（2D推定） |
| `trunk_tilt_estimate_at_block` | ブロック時の体幹傾き（2D推定） |
| `trunk_tilt_estimate_at_release` | リリース時の体幹傾き（2D推定） |
| `max_shoulder_hip_separation_estimate` | 全動作中の肩腰分離角最大値（推定） |

### 投げ腕指標 (`arm_metrics`)

投擲腕の軌跡・速度・角度の参考指標。

| キー | 説明 |
|------|------|
| `throwing_wrist_peak_velocity` | 手首最大速度（正規化相対値） |
| `elbow_angle_estimate_at_release` | リリース時の肘角度（2D推定） |
| `shoulder_elbow_wrist_alignment_score` | 肩-肘-手首の整列スコア（0-1） |
| `arm_pullback_distance_estimate` | 槍引き距離の推定（正規化） |
| `arm_path_length_normalized` | 手首の軌跡長（正規化） |

---

## 信頼度スコア

各指標に `reliability` フィールドが付きます:

- **`high`** (🟢): 姿勢検出率 ≥ 85%、十分なデータ
- **`medium`** (🟡): 姿勢検出率 ≥ 65%、または推定精度に限界あり
- **`low`** (🔴): 姿勢検出率 < 65%、または重大な制限あり
- **`unknown`** (⚪): データ不足で判断不能

詳細: [metrics_reliability.md](metrics_reliability.md)

---

## 設計上の制約と免責事項

1. **2D 座標のみ使用** — 奥行き情報なし。カメラアングルにより値が大きく変わる
2. **ピクセル座標正規化** — 「体スケール正規化」は肩幅と肩腰間距離の平均で行うが、
   実際の身長・体格とは対応しない
3. **速度推定の精度** — フレームレートと座標ノイズに依存。ノイズ除去に移動平均を適用
4. **角度推定の精度** — 2D 投影のため、正面・側面以外の撮影角では誤差が大きい
5. **フェーズ境界の不確実性** — phase_frames.json の精度に依存
