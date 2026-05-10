# Public リポジトリ 公開前チェックリスト

> 本ドキュメントは Private リポジトリから Public デモ版を切り出す際の作業手順書です。  
> **このファイル自体は Private リポジトリにのみ保存し、Public リポジトリには含めないでください。**

---

## 1. ファイル分類表

### ✅ Public に含める（デモ・技術紹介に必要）

#### コア解析ライブラリ
| ファイル/ディレクトリ | 理由 |
|---|---|
| `src/pipelines/pose_analysis.py` | MediaPipe ポーズ解析（技術デモの核心） |
| `src/pipelines/speed_visualization.py` | 速度可視化パイプライン |
| `src/pipelines/acceleration_heatmap.py` | 加速度ヒートマップ |
| `src/pipelines/tip_tracking.py` | やり先端トラッキング |
| `src/pipelines/pose_visualization.py` | ポーズ可視化 |
| `src/tracking/marker_based.py` | マーカーベーストラッキング |
| `src/tracking/object_tracking.py` | オブジェクトトラッキング |
| `src/io/video_reader.py` | 動画読み込み |
| `src/io/video_writer.py` | 動画書き出し |
| `src/utils/geometry.py` | 幾何計算ユーティリティ |
| `src/utils/filters.py` | データフィルタ |
| `src/utils/color_maps.py` | カラーマッピング |
| `src/utils/visualization.py` | 描画ユーティリティ |
| `src/utils/mediapipe_fix.py` | MediaPipe 互換フィックス |
| `src/utils/mock_mediapipe.py` | テスト用モック |
| `src/utils/opencv_pose.py` | OpenCV ポーズ推定 |
| `src/types/__init__.py` | 型定義 |
| `src/app.py` | 基本エントリーポイント |

#### 可視化プラグインシステム
| ファイル/ディレクトリ | 理由 |
|---|---|
| `jva_visuals/__init__.py` | プラグインシステム |
| `jva_visuals/vectors.py` | ベクトル描画 |
| `jva_visuals/heatmap.py` | ヒートマップ |
| `jva_visuals/hud.py` | ゲーム風HUD |
| `jva_visuals/trails.py` | 軌跡エフェクト |
| `jva_visuals/stickman.py` | スティックマン描画 |
| `jva_visuals/kinematics.py` | 運動学計算 |
| `jva_visuals/adapters.py` | アダプター層 |
| `jva_visuals/analysis.py` | 解析ヘルパー |
| `jva_visuals/registry.py` | プラグインレジストリ |

#### Blender 連携
| ファイル/ディレクトリ | 理由 |
|---|---|
| `blender_bridge/` (全体) | 3D連携デモ |

#### 設定ファイル（機密情報なし）
| ファイル | 理由 |
|---|---|
| `configs/default.yaml` | 基本設定 |
| `configs/color_ranges.yaml` | 色範囲定義 |
| `configs/tracking.yaml` | トラッキング設定 |
| `configs/visuals.example.yaml` | 可視化設定サンプル |

#### スクリプト・ツール
| ファイル | 理由 |
|---|---|
| `scripts/run_pipeline.py` | パイプライン実行スクリプト |
| `scripts/export_metrics.py` | メトリクス出力 |
| `create_test_video.py` | テスト動画生成 |
| `run.py` | ⚠️ **要修正** — venv パスのハードコードを削除してから含める |

#### テスト（基本機能のみ）
| ファイル | 理由 |
|---|---|
| `tests/test_tip_tracking.py` | 先端トラッキングテスト |
| `tests/test_speed_visualization.py` | 速度可視化テスト |
| `tests/test_acceleration_heatmap.py` | 加速度ヒートマップテスト |
| `tests/test_trails.py` | 軌跡テスト |
| `tests/test_pipeline_visuals.py` | パイプライン可視化テスト |
| `tests/test_kinematics.py` | 運動学テスト |

#### ドキュメント
| ファイル | 理由 |
|---|---|
| `docs/colab_snippet.md` | Colab デモ手順 |
| `docs/BLENDER_INTEGRATION.md` | Blender 連携ガイド |
| `docs/PLUGIN_DEVELOPMENT.md` | プラグイン開発ガイド |
| `docs/CONFIGURATION.md` | 設定ガイド |
| `MEDIAPIPE_INSTALL_GUIDE.md` | インストールガイド |
| `CODE_OF_CONDUCT.md` | 行動規範 |
| `CONTRIBUTING.md` | コントリビュートガイド |
| `LICENSE` | MIT ライセンス |
| `PR_TEMPLATE.md` | PR テンプレート |
| `README.md` | ⚠️ **公開デモ版に書き換え済み** |

#### パッケージ設定（要修正）
| ファイル | 理由 |
|---|---|
| `requirements.txt` | ⚠️ **要修正** — boto3, fastapi, streamlit, httpx を削除 |
| `pyproject.toml` | ⚠️ **要修正** — boto3, fastapi, uvicorn 等の依存を削除 |
| `.env.example` | ⚠️ **要修正** — S3, LINE, 管理画面設定を削除 |

---

### 🔴 Private のみ（絶対に Public に含めない）

#### 商用サービスロジック（コア）
| ファイル/ディレクトリ | 理由 |
|---|---|
| `admin_app.py` | Streamlit 管理画面（全機能） |
| `job_manager.py` | ジョブ管理ロジック |
| `src/analysis/` (全体) | 独自高度解析指標・フェーズ検出 |
| `src/analysis_summary.py` | 解析サマリー生成 |
| `src/analysis_summary_generator.py` | 解析サマリー生成器 |
| `src/artifact_manifest.py` | 成果物マニフェスト |
| `src/athlete_data_sheet_generator.py` | 選手データシートPDF |
| `src/coach_review_sheet_generator.py` | コーチレビューシートPDF |
| `src/compare_jobs.py` | ジョブ比較ロジック |
| `src/comparison_dashboard_generator.py` | 比較ダッシュボード |
| `src/comparison_report_pdf.py` | 比較レポートPDF |
| `src/comparison_zip.py` | 比較成果物パッケージ |
| `src/config.py` | 本番設定ローダー |
| `src/dashboard_generator.py` | Webダッシュボード生成 |
| `src/dashboard_manifest.py` | ダッシュボードマニフェスト・トークン管理 |
| `src/data_exporter.py` | データエクスポート |
| `src/deliverable_packager.py` | 納品物パッケージャー |
| `src/delivery_page.py` | 納品ページ生成 |
| `src/display_labels.py` | 表示ラベル定義（商用プラン含む） |
| `src/frame_extractor.py` | 代表フレーム抽出 |
| `src/graph_generator.py` | グラフ生成（商用） |
| `src/graph_pack_generator.py` | グラフパック生成 |
| `src/intro_pdf_generator.py` | はじめにPDF生成 |
| `src/jva/` (全体) | 商用エントリーポイント・FFmpeg連携 |
| `src/key_frame_sheet_generator.py` | キーフレームシートPDF |
| `src/logging_config.py` | 本番ログ設定 |
| `src/message_templates.py` | 支払い・納品メッセージ文面 |
| `src/order_manager.py` | 注文管理 |
| `src/pdf_report_generator.py` | PDFレポート生成（商用） |
| `src/pdf_styles.py` | PDFスタイル定義 |
| `src/phase_frames.py` | フェーズフレーム抽出 |
| `src/phase_loader.py` | フェーズデータローダー |
| `src/phase_summary_pdf.py` | フェーズサマリーPDF |
| `src/plan_loader.py` | プランローダー |
| `src/queue_manager.py` | ジョブキュー管理 |
| `src/storage/` (全体) | S3 連携ロジック |
| `src/valid_segment_detector.py` | 有効セグメント検出 |
| `src/video_instruction_pdf_generator.py` | 動画の見方PDF生成 |
| `src/annotation/` (全体) | アノテーション管理 |

#### β版・ユーザー管理
| ファイル | 理由 |
|---|---|
| `src/beta_tester.py` | βテスター管理（個人情報含む） |
| `src/feedback_manager.py` | フィードバック管理 |
| `src/improvement_log.py` | 改善ログ |
| `src/intake_manager.py` | 申込（intake）管理（個人情報含む） |

#### サーバー・API（商用エンドポイント）
| ファイル | 理由 |
|---|---|
| `server/app.py` | FastAPI 本番アプリ |
| `server/feedback_api.py` | フィードバック API |
| `server/intake_api.py` | 申込受付 API |
| `server/jobs_api.py` | ジョブ管理 API |
| `server/public_dashboard_api.py` | パブリックダッシュボード API |

#### 設定ファイル（商用・機密）
| ファイル | 理由 |
|---|---|
| `configs/advanced_metrics.yaml` | 独自解析指標定義 |
| `configs/annotation.yaml` | アノテーション設定 |
| `configs/beta_release_config.yaml` | β版設定・KPI目標 |
| `configs/dashboard.yaml` | ダッシュボード設定 |
| `configs/metric_labels.yaml` | 指標ラベル定義 |
| `configs/phases.yaml` | フェーズ定義 |
| `configs/phase_detection.yaml` | フェーズ検出設定 |
| `configs/plans.yaml` | 商用プラン定義 |
| `configs/pricing_plans.yaml` | 料金・価格情報 |

#### テスト（商用機能）
| ファイル | 理由 |
|---|---|
| `tests/test_phase3.py` 〜 `test_phase15.py` | 商用機能テスト |
| `tests/test_analysis_summary_generator.py` | 商用解析テスト |
| `tests/test_video_instruction_pdf_generator.py` | 商用PDFテスト |

#### ドキュメント（商用・運用・個人情報リスク）
| ファイル | 理由 |
|---|---|
| `docs/advanced_metrics_design.md` | 独自指標設計 |
| `docs/advanced_metrics_export_format.md` | 独自指標フォーマット |
| `docs/annotation_design.md` | アノテーション設計 |
| `docs/annotation_export_format.md` | アノテーションフォーマット |
| `docs/background_worker.md` | 本番ワーカー設計 |
| `docs/beta_*.md` (全て) | β版運用手順・個人情報 |
| `docs/consent_template.md` | 同意書テンプレート |
| `docs/deployment_guide.md` | 本番デプロイ手順 |
| `docs/google_form_integration.md` | フォーム連携設定 |
| `docs/google_form_template.md` | フォームテンプレート |
| `docs/legal/` (全て) | 利用規約・プライバシーポリシー草稿 |
| `docs/line_official_account_guide.md` | LINE 連携設定 |
| `docs/metrics_interpretation_guide.md` | 商用指標解説 |
| `docs/metrics_reliability.md` | 指標信頼性評価 |
| `docs/public_dashboard_api.md` | 商用 API 仕様 |
| `docs/s3_cors.json` | S3 CORS 設定 |
| `docs/s3_delivery_setup.md` | S3 配信設定 |
| `docs/security_checklist.md` | 本番セキュリティチェック |
| `docs/social/` (全て) | SNS 告知文（β版サービス） |
| `docs/training_data_policy.md` | 教師データ利用ポリシー |
| `docs/user_dashboard_design.md` | 商用ダッシュボード設計 |
| `docs/video_submission_guide.md` | ユーザー向け動画提出ガイド |
| `docs/public_release_checklist.md` | **このファイル自体** |

#### データ・成果物（絶対に含めない）
| パス | 理由 |
|---|---|
| `jobs/` (全体) | ユーザー解析ジョブデータ |
| `data/` (全体) | ユーザーデータ（beta_testers, feedback, intake 等） |
| `input/` | ユーザー動画 |
| `output/` | 解析成果物 |
| `uploads/` | アップロードファイル |
| `reports/` | 生成レポート |
| `*.pdf` (生成済み) | 生成PDFレポート |
| `.env` | 本番環境変数 |
| `*.log` | ログファイル |
| `logs/` | ログディレクトリ |

---

## 2. Public リポジトリ作成手順

### Step 1: 新リポジトリ作成
```bash
# GitHub で新しい Public リポジトリを作成
# 名前例: javelin-video-analysis-demo または javelin-pose-analysis
```

### Step 2: Public 版ファイルの準備（Local）
```powershell
# 作業ディレクトリを作成
mkdir C:\work\javelin-public-prep
cd C:\work\javelin-public-prep
git init

# Private リポジトリから必要ファイルのみコピー
$SRC = "C:\Users\Owner\javelin\javelin-video-analysis\javelin-video-analysis"
$DST = "C:\work\javelin-public-prep"

# --- コピー対象ディレクトリ ---
Copy-Item "$SRC\src\pipelines" "$DST\src\pipelines" -Recurse
Copy-Item "$SRC\src\tracking"  "$DST\src\tracking"  -Recurse
Copy-Item "$SRC\src\io"        "$DST\src\io"        -Recurse
Copy-Item "$SRC\src\utils"     "$DST\src\utils"     -Recurse
Copy-Item "$SRC\src\types"     "$DST\src\types"     -Recurse
Copy-Item "$SRC\src\app.py"    "$DST\src\app.py"
Copy-Item "$SRC\jva_visuals"   "$DST\jva_visuals"   -Recurse
Copy-Item "$SRC\blender_bridge" "$DST\blender_bridge" -Recurse
Copy-Item "$SRC\scripts"       "$DST\scripts"       -Recurse
Copy-Item "$SRC\configs\default.yaml"        "$DST\configs\"
Copy-Item "$SRC\configs\color_ranges.yaml"   "$DST\configs\"
Copy-Item "$SRC\configs\tracking.yaml"       "$DST\configs\"
Copy-Item "$SRC\configs\visuals.example.yaml" "$DST\configs\"

# --- コピー対象テスト ---
Copy-Item "$SRC\tests\test_tip_tracking.py"        "$DST\tests\"
Copy-Item "$SRC\tests\test_speed_visualization.py" "$DST\tests\"
Copy-Item "$SRC\tests\test_acceleration_heatmap.py" "$DST\tests\"
Copy-Item "$SRC\tests\test_trails.py"              "$DST\tests\"
Copy-Item "$SRC\tests\test_pipeline_visuals.py"    "$DST\tests\"
Copy-Item "$SRC\tests\test_kinematics.py"          "$DST\tests\"

# --- コピー対象ドキュメント ---
Copy-Item "$SRC\docs\colab_snippet.md"          "$DST\docs\"
Copy-Item "$SRC\docs\BLENDER_INTEGRATION.md"    "$DST\docs\"
Copy-Item "$SRC\docs\PLUGIN_DEVELOPMENT.md"     "$DST\docs\"
Copy-Item "$SRC\docs\CONFIGURATION.md"          "$DST\docs\"
Copy-Item "$SRC\MEDIAPIPE_INSTALL_GUIDE.md"     "$DST\"
Copy-Item "$SRC\CODE_OF_CONDUCT.md"             "$DST\"
Copy-Item "$SRC\CONTRIBUTING.md"                "$DST\"
Copy-Item "$SRC\LICENSE"                        "$DST\"
Copy-Item "$SRC\PR_TEMPLATE.md"                 "$DST\"
Copy-Item "$SRC\README.md"                      "$DST\"
Copy-Item "$SRC\create_test_video.py"           "$DST\"
```

### Step 3: 要修正ファイルの処理
```powershell
# run.py — venv ハードコードを削除してからコピー
# (編集後にコピー)

# requirements.txt — public 版を新規作成
# (下記内容を参照)

# pyproject.toml — dependencies を削減
# (下記内容を参照)

# .env.example — S3/LINE/管理画面設定を削除
# (下記内容を参照)
```

### Step 4: 機密情報の確認
```bash
# grep でコード内に機密情報が残っていないか確認
grep -r "JVA_BUCKET\|LINE_CHANNEL\|AWS_SECRET\|stripe\|pricing_plan" ./src/
grep -r "boto3\|s3_storage\|order_manager\|intake_manager\|job_manager" ./src/
grep -r "admin_password\|JVA_API_KEY\|dashboard_token" .
```

### Step 5: git secret / pre-commit の設定
```bash
# gitleaks でシークレットスキャン
pip install gitleaks  # またはバイナリを使用
gitleaks detect --source .

# または trufflehog
pip install truffleHog3
trufflehog3 .
```

### Step 6: Public リポジトリへ push
```bash
git remote add origin https://github.com/YOUR_USERNAME/javelin-video-analysis-demo
git add .
git commit -m "Initial public release: javelin pose analysis demo"
git push -u origin main
```

---

## 3. Public 版 requirements.txt（参考）

```
# Core
opencv-python>=4.5.0
numpy>=1.21.0
PyYAML>=5.4.1

# Pose estimation
mediapipe>=0.8.6

# Analysis
scipy>=1.7.0
pandas
matplotlib
seaborn

# Testing
pytest>=6.0
pytest-cov
```

---

## 4. Public 版 .env.example（参考）

```
# Javelin Video Analysis — Demo .env.example
# Copy this file to .env and edit as needed.

# Debug mode
JVA_DEBUG=false

# Input/output paths
JVA_INPUT_DIR=input
JVA_OUTPUT_DIR=output
```

---

## 5. 公開前チェックリスト

### コード
- [ ] `run.py` から `C:/venvs/javelin312/Scripts/python.exe` のハードコードを削除した
- [ ] `pyproject.toml` から boto3, fastapi, uvicorn, streamlit 等の依存を削除した
- [ ] `requirements.txt` を公開デモ版用に整理した
- [ ] `.env.example` から S3, LINE, 管理画面, APIキー 設定を削除した
- [ ] 全ファイルに URLリテラルとして本番 S3 バケット名が含まれていないことを確認した
- [ ] 全ファイルに本番 API キーや署名 URL が含まれていないことを確認した
- [ ] コメント欄に実サービスの内部処理に関するヒントが含まれていないことを確認した

### データ・成果物
- [ ] `jobs/` ディレクトリが含まれていないことを確認した
- [ ] `data/` ディレクトリが含まれていないことを確認した（特に `beta_testers/`, `feedback/`, `intake/`）
- [ ] `input/` に実ユーザーの動画が含まれていないことを確認した
- [ ] `output/` に実ユーザーの解析結果が含まれていないことを確認した
- [ ] PDF レポート（`*.pdf`）が含まれていないことを確認した
- [ ] ログファイル（`*.log`）が含まれていないことを確認した
- [ ] `.env` ファイルが含まれていないことを確認した

### 個人情報
- [ ] 実ユーザーの名前・連絡先・メールが含まれていないことを確認した
- [ ] 実ユーザーの動画・画像が含まれていないことを確認した
- [ ] intake データ（申込情報）が含まれていないことを確認した
- [ ] フィードバックデータが含まれていないことを確認した

### 商用情報
- [ ] 料金・価格情報（`pricing_plans.yaml`）が含まれていないことを確認した
- [ ] 商用プラン定義（`plans.yaml`）が含まれていないことを確認した
- [ ] 独自解析指標の詳細定義（`advanced_metrics.yaml`）が含まれていないことを確認した
- [ ] β版運用手順・告知文が含まれていないことを確認した
- [ ] 法務ドキュメント草稿（`docs/legal/`）が含まれていないことを確認した

### GitHub 設定
- [ ] リポジトリを Public に設定した
- [ ] `LICENSE` ファイルが MIT ライセンスで正しく設定されていることを確認した
- [ ] `.gitignore` に適切な除外設定があることを確認した
- [ ] リポジトリの Description と Topics を設定した
- [ ] GitHub Actions のシークレット設定は不要（公開デモ版は CI 任意）

### README
- [ ] README が「公開デモ版」として記述されていることを確認した
- [ ] Private リポジトリへの言及が適切であることを確認した
- [ ] β版サービスの申込 URL・フォーム URL が含まれていないことを確認した
- [ ] 管理画面・S3 設定手順が含まれていないことを確認した
- [ ] `run.py` のデモ実行コマンドが機能することを手元で確認した

### テスト
- [ ] `python -m pytest tests/ -q` が PASS することを確認した
- [ ] 商用機能テスト（`test_phase3.py` 等）が含まれていないことを確認した

---

## 6. リポジトリ説明文（GitHub の About）

**Description:**
```
🎯 Javelin throw pose analysis and visualization toolkit using MediaPipe. Includes heatmaps, vector overlays, and Blender 3D integration.
```

**Topics（おすすめ）:**
```
javelin, pose-estimation, mediapipe, opencv, sports-analysis, visualization, python, athletics
```

---

## 7. Private / Public リポジトリの関係管理

- Private リポジトリは **git subtree** や **git submodule** では連携しないこと（意図しない情報漏洩のリスク）
- Public リポジトリは独立した別リポジトリとして管理する
- Public 版に変更を反映する場合は、手動でファイルをコピーして commit する
- Private リポジトリの commit 履歴を Public に移行しないこと（過去 commit に機密情報が含まれる可能性がある）
