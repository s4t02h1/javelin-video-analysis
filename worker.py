#!/usr/bin/env python3
"""
worker.py — Javelin Video Analysis: バックグラウンドジョブワーカー (Phase 7)

pending キューからジョブを取得し、解析パイプラインを順番に実行する。

使用方法:
    python worker.py                # 連続ポーリングモード
    python worker.py --once         # 1件だけ処理して終了
    python worker.py --poll-interval 10   # ポーリング間隔を10秒に設定
    python worker.py --max-jobs 5   # 最大5件処理して終了

ロックファイル:
    data/queue/worker.lock  — 複数ワーカーの同時起動を防ぐ

環境変数:
    JVA_WORKER_POLL_INTERVAL_SECONDS  ポーリング間隔（デフォルト: 5秒）
    JVA_WORKER_MAX_RETRIES            ジョブのデフォルト最大リトライ回数（デフォルト: 1）
    JVA_QUEUE_DIR                     キューディレクトリ（デフォルト: data/queue）

注意:
    src/types/__init__.py が stdlib types をシャドウイングするため
    sys.path.insert(0, 'src') は使わず、REPO_ROOT を sys.path に追加する。
"""
from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from subprocess import run as subprocess_run
from typing import Any, Dict, List, Optional

# ── パス設定 ─────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ── ロギング設定 ──────────────────────────────────────────────────────────────
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)
logger = logging.getLogger("jva.worker")

# ── 設定 ─────────────────────────────────────────────────────────────────────
_DEFAULT_POLL_INTERVAL = int(os.getenv("JVA_WORKER_POLL_INTERVAL_SECONDS", "5"))
_DEFAULT_MAX_RETRIES = int(os.getenv("JVA_WORKER_MAX_RETRIES", "1"))
_WORKER_LOCK_FILE: Optional[Path] = None   # claim 後に設定

PYTHON_BIN: str = sys.executable
RUN_PY: str = str(_REPO_ROOT / "run.py")


# ── モジュール遅延インポート（インポートエラーを許容） ────────────────────────

def _import_queue_manager():
    import src.queue_manager as qm
    return qm


def _import_job_manager():
    import job_manager as jm
    return jm


def _import_s3_storage():
    try:
        import src.storage.s3_storage as s3
        return s3
    except ImportError:
        return None


def _import_delivery_page():
    try:
        import src.delivery_page as dp
        return dp
    except ImportError:
        return None


def _import_deliverable_packager():
    try:
        import src.deliverable_packager as dp
        return dp
    except ImportError:
        return None


def _import_pdf_report_generator():
    try:
        import src.pdf_report_generator as pdf
        return pdf
    except ImportError:
        return None


def _import_intro_pdf_generator():
    try:
        import src.intro_pdf_generator as ipdf
        return ipdf
    except ImportError:
        return None


def _import_phase_detection():
    try:
        from src.analysis.phase_detection import detect_phases_for_job
        return detect_phases_for_job
    except ImportError:
        return None


def _import_video_quality():
    try:
        from src.analysis.video_quality import check_video_quality_for_job
        return check_video_quality_for_job
    except ImportError:
        return None


def _import_artifact_manifest():
    try:
        import src.artifact_manifest as am
        return am
    except ImportError:
        return None


# ── ワーカーロック ────────────────────────────────────────────────────────────

def _worker_lock_path() -> Path:
    qm = _import_queue_manager()
    return qm._queue_root() / "worker.lock"


def _acquire_worker_lock() -> bool:
    """ワーカーロックファイルを排他取得する。

    Returns
    -------
    bool
        True: 取得成功  False: 別ワーカーが実行中
    """
    lock = _worker_lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        # 既存ロックファイルの PID を確認して stale かどうかチェック
        try:
            pid_str = lock.read_text(encoding="utf-8").strip()
            pid = int(pid_str) if pid_str else 0
            if pid > 0:
                # プロセスが存在するか確認（存在しなければ stale ロック）
                try:
                    os.kill(pid, 0)
                    logger.warning("[worker] 別のワーカーが実行中 (PID=%d)", pid)
                    return False
                except OSError:
                    logger.warning("[worker] Stale ロックを削除: PID=%d", pid)
                    lock.unlink(missing_ok=True)
                    return _acquire_worker_lock()
        except Exception:
            pass
        return False


def _release_worker_lock() -> None:
    lock = _worker_lock_path()
    try:
        lock.unlink(missing_ok=True)
    except Exception:
        pass


# ── パイプラインステップ ──────────────────────────────────────────────────────

def _step_validate_inputs(job_id: str, job_dir: Path) -> None:
    """入力ファイルの存在を確認する。"""
    input_file = job_dir / "input" / "original.mp4"
    if not input_file.exists():
        raise FileNotFoundError(
            f"入力動画が見つかりません: {input_file}\n"
            "管理画面から動画をアップロードしてから再実行してください。"
        )
    size = input_file.stat().st_size
    if size == 0:
        raise ValueError(f"入力動画のサイズが 0 バイトです: {input_file}")
    logger.info("[worker] validate_inputs: OK (size=%d bytes)", size)


def _step_run_analysis(job_id: str, job_dir: Path, job: dict) -> None:
    """run.py を subprocess で実行して動画解析を行う。"""
    input_file = job_dir / "input" / "original.mp4"
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    height_m = job.get("height_m")
    cmd = [
        PYTHON_BIN, RUN_PY,
        "--input",      str(input_file),
        "--output-dir", str(output_dir),
        "--all-variants",
    ]
    if height_m is not None:
        cmd += ["--height", str(height_m)]

    logger.info("[worker] run_analysis 開始: job_id=%s", job_id)
    logger.debug("[worker] コマンド: %s", " ".join(cmd))

    result = subprocess_run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        err_output = (result.stderr or result.stdout or "").strip()[:1000]
        raise RuntimeError(
            f"run.py が終了コード {result.returncode} で失敗しました。\n"
            f"エラー出力:\n{err_output}"
        )
    logger.info("[worker] run_analysis 完了: job_id=%s", job_id)


def _step_generate_artifacts(job_id: str, job_dir: Path) -> List[str]:
    """解析出力ファイルを収集して返す。"""
    output_dir = job_dir / "output"
    if not output_dir.exists():
        raise FileNotFoundError(f"output ディレクトリが存在しません: {output_dir}")

    files = [str(p) for p in output_dir.iterdir() if p.is_file()]
    if not files:
        raise ValueError("解析出力ファイルが生成されませんでした。")
    logger.info("[worker] generate_artifacts: %d ファイル確認", len(files))
    return files


def _step_check_video_quality(job_id: str, job_dir: Path) -> None:
    """動画品質チェックを実行して video_quality_report.json を生成する（非致命的）。

    Phase 10 追加ステップ。失敗しても通常の解析処理は継続する。
    """
    fn = _import_video_quality()
    if fn is None:
        logger.info("[worker] video_quality モジュール未使用: job_id=%s", job_id)
        return
    try:
        out = fn(job_dir)
        logger.info("[worker] check_video_quality 完了: %s", out.name)
    except Exception as e:
        logger.warning("[worker] check_video_quality 失敗（継続）: job_id=%s error=%s", job_id, e)


def _step_detect_phases(job_id: str, job_dir: Path) -> None:
    """自動フェーズ推定を実行して phase_detection_result.json を生成する（非致命的）。

    Phase 10 追加ステップ。失敗しても通常の解析処理は継続する。
    require_admin_review=true (デフォルト) のため、自動推定は手動フェーズ指定を上書きしない。
    """
    fn = _import_phase_detection()
    if fn is None:
        logger.info("[worker] phase_detection モジュール未使用: job_id=%s", job_id)
        return
    try:
        out = fn(job_dir)
        logger.info("[worker] detect_phases 完了: %s", out.name)
    except Exception as e:
        logger.warning("[worker] detect_phases 失敗（継続）: job_id=%s error=%s", job_id, e)


def _step_compute_advanced_metrics(job_id: str, job_dir: Path) -> None:
    """Phase 12: 高度解析指標を計算して保存する（非致命的）。

    姿勢推定 CSV とフェーズ・イベントフレームをもとに参考指標を計算します。
    失敗してもパイプライン処理は継続します。
    """
    try:
        from src.analysis.advanced_metrics import compute_advanced_metrics_for_job
        out = compute_advanced_metrics_for_job(job_dir)
        logger.info("[worker] advanced_metrics 生成完了: %s job_id=%s", out.name, job_id)
    except Exception as e:
        logger.warning("[worker] advanced_metrics 生成失敗（継続）: job_id=%s error=%s", job_id, e)


def _step_generate_advanced_metrics_report(job_id: str, job_dir: Path) -> None:
    """Phase 12: 高度解析指標 PDF を生成する（非致命的）。

    advanced_metrics.json をもとに advanced_metrics_report.pdf を生成します。
    失敗してもパイプライン処理は継続します。
    """
    try:
        from src.analysis.advanced_metrics_report import generate_advanced_metrics_report_for_job
        out = generate_advanced_metrics_report_for_job(job_dir)
        if out is not None:
            logger.info("[worker] advanced_metrics_report PDF 生成完了: %s job_id=%s", out.name, job_id)
        else:
            logger.warning("[worker] advanced_metrics_report PDF 生成スキップ: job_id=%s", job_id)
    except Exception as e:
        logger.warning("[worker] advanced_metrics_report PDF 生成失敗（継続）: job_id=%s error=%s", job_id, e)


def _step_export_advanced_metrics(job_id: str, job_dir: Path) -> None:
    """Phase 12: 高度解析指標をエクスポート用ファイルに書き出す（非致命的）。"""
    try:
        from src.analysis.advanced_metrics_exporter import export_advanced_metrics_for_job
        out = export_advanced_metrics_for_job(job_dir)
        if out is not None:
            logger.info("[worker] advanced_metrics export 完了: %s job_id=%s", out.name, job_id)
    except Exception as e:
        logger.warning("[worker] advanced_metrics export 失敗（継続）: job_id=%s error=%s", job_id, e)


def _step_generate_user_dashboard(job_id: str, job_dir: Path) -> None:
    """Phase 13: ユーザー向けダッシュボードHTMLを生成する（非致命的）。

    advanced_metrics.json・フェーズ画像・グラフ等をもとに user_dashboard.html を生成します。
    S3 presigned URL は upload_to_s3 後に別ステップで付与するため、ここではローカル生成のみ。
    失敗しても通常のPDF・ZIP納品は続きます。
    """
    try:
        from src.dashboard_generator import generate_user_dashboard_for_job
        out = generate_user_dashboard_for_job(job_dir)
        if out is not None:
            logger.info("[worker] user_dashboard.html 生成完了: %s job_id=%s", out.name, job_id)
        else:
            logger.info("[worker] user_dashboard.html 生成スキップ（無効設定）: job_id=%s", job_id)
    except Exception as e:
        logger.warning("[worker] user_dashboard.html 生成失敗（継続）: job_id=%s error=%s", job_id, e)


def _step_generate_dashboard_manifest(job_id: str, job_dir: Path) -> None:
    """Phase 14: ダッシュボードマニフェスト JSON を生成する（非致命的）。

    dashboard_manifest.json は公開 API とフロントエンドが使用するデータ定義ファイルです。
    dashboard_token を割り当て、job.json に保存します。
    """
    try:
        from src.dashboard_manifest import save_dashboard_manifest
        out = save_dashboard_manifest(job_dir)
        if out is not None:
            logger.info("[worker] dashboard_manifest.json 生成完了: %s job_id=%s", out.name, job_id)
        else:
            logger.info("[worker] dashboard_manifest.json 生成スキップ: job_id=%s", job_id)
    except Exception as e:
        logger.warning("[worker] dashboard_manifest.json 生成失敗（継続）: job_id=%s error=%s", job_id, e)


def _step_upload_dashboard_to_s3(job_id: str, job_dir: Path) -> Optional[str]:
    """Phase 13: ダッシュボードHTML の presigned URL を返す（非致命的）。

    user_dashboard.html は upload_to_s3 ステップで report/ ディレクトリと
    一緒にアップロード済みのため、このステップでは presigned URL の生成のみ行う。
    S3 未設定の場合は None を返す。
    """
    s3 = _import_s3_storage()
    if s3 is None or not s3.is_s3_configured():
        logger.info("[worker] S3 未設定のためダッシュボードURL生成をスキップ: job_id=%s", job_id)
        return None

    try:
        dashboard_path = job_dir / "report" / "user_dashboard.html"
        if not dashboard_path.exists():
            logger.info("[worker] user_dashboard.html が存在しないためURL生成をスキップ: job_id=%s", job_id)
            return None

        s3_key = s3.build_s3_key_for_job(job_id, "report/user_dashboard.html")
        url = s3.generate_presigned_url(s3_key)
        logger.info("[worker] ダッシュボードpresigned URL 生成完了: job_id=%s", job_id)
        return url
    except Exception as e:
        logger.warning("[worker] ダッシュボードURL生成エラー: job_id=%s error=%s", job_id, e)
        return None


def _step_update_dashboard_url(job_id: str, dashboard_url: Optional[str], expires_at: str = "") -> None:
    """Phase 13: ジョブメタデータにダッシュボードURLを保存する（非致命的）。"""
    jm = _import_job_manager()
    try:
        from datetime import datetime as _dt
        now = _dt.now().isoformat(timespec="seconds")
        update_fields: dict = {
            "dashboard_generated_at": now,
            "dashboard_upload_status": "complete" if dashboard_url else "local_only",
        }
        if dashboard_url:
            update_fields["user_dashboard_url"] = dashboard_url
            s3 = _import_s3_storage()
            if s3:
                update_fields["user_dashboard_s3_key"] = s3.build_s3_key_for_job(
                    job_id, "report/user_dashboard.html"
                )
        if expires_at:
            update_fields["dashboard_url_expires_at"] = expires_at
        jm.update_job(job_id, **update_fields)
        logger.info("[worker] ダッシュボードURL更新: job_id=%s url_set=%s", job_id, bool(dashboard_url))
    except Exception as e:
        logger.warning("[worker] ダッシュボードURL更新失敗: job_id=%s error=%s", job_id, e)


def _step_create_annotation_draft(job_id: str, job_dir: Path) -> None:
    """Phase 10推定結果からアノテーションドラフトを作成する（非致命的）。

    Phase 11 追加ステップ。annotation_status は draft にする。
    人間が管理画面で confirmed にする必要がある。
    すでにアノテーションが存在する場合はスキップする。
    失敗しても通常の解析処理は継続する。
    """
    try:
        import yaml  # type: ignore[import-not-found]
        cfg_path = Path(__file__).resolve().parent / "configs" / "annotation.yaml"
        cfg: dict = {}
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as _f:
                _loaded = yaml.safe_load(_f)
            cfg = _loaded if isinstance(_loaded, dict) else {}

        if not cfg.get("enabled", True):
            logger.info("[worker] アノテーション機能が無効です: job_id=%s", job_id)
            return
        if not cfg.get("create_draft_after_phase_detection", True):
            logger.info("[worker] Phase推定後のドラフト自動生成が無効です: job_id=%s", job_id)
            return

        from src.annotation.manager import create_annotation_draft_for_job
        out = create_annotation_draft_for_job(job_dir)
        if out is not None:
            logger.info("[worker] annotation draft 作成完了: %s job_id=%s", out.name, job_id)
        else:
            logger.info("[worker] annotation draft 作成スキップ（無効または既存）: job_id=%s", job_id)
    except Exception as e:
        logger.warning("[worker] annotation draft 作成失敗（継続）: job_id=%s error=%s", job_id, e)


def _step_generate_reports(job_id: str, job_dir: Path) -> List[str]:
    """PDF レポートを生成する。失敗しても継続可能なステップのみ。"""
    generated: List[str] = []
    report_dir = job_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    # intro PDF
    ipdf = _import_intro_pdf_generator()
    if ipdf:
        try:
            p = ipdf.generate_intro_pdf_for_job(job_dir)
            generated.append(str(p))
            logger.info("[worker] intro PDF 生成完了: %s", p.name)
        except Exception as e:
            logger.warning("[worker] intro PDF 生成スキップ: %s", e)

    # analysis PDF
    pdf_mod = _import_pdf_report_generator()
    if pdf_mod:
        try:
            p = pdf_mod.generate_pdf_report_for_job(job_dir)
            generated.append(str(p))
            logger.info("[worker] analysis PDF 生成完了: %s", p.name)
        except Exception as e:
            logger.warning("[worker] analysis PDF 生成スキップ: %s", e)

    # Phase 10: video quality PDF
    try:
        from src.analysis.video_quality_pdf import generate_video_quality_pdf_for_job
        p_vq = generate_video_quality_pdf_for_job(job_dir)
        if p_vq is not None:
            generated.append(str(p_vq))
            logger.info("[worker] video_quality PDF 生成完了: %s", p_vq.name)
    except Exception as e:
        logger.warning("[worker] video_quality PDF 生成スキップ: %s", e)

    logger.info("[worker] generate_reports: %d ファイル生成", len(generated))
    return generated


def _step_generate_packages(job_id: str, job_dir: Path) -> Dict[str, str]:
    """納品用 ZIP パッケージを生成する。"""
    dp = _import_deliverable_packager()
    if dp is None:
        logger.warning("[worker] deliverable_packager が利用できません。ZIP 生成をスキップ。")
        return {}

    zips = dp.create_deliverable_packages_for_job(job_dir)
    result = {k: str(v) for k, v in zips.items()}
    logger.info("[worker] generate_packages: %d ZIPファイル生成", len(result))
    return result


def _step_upload_to_s3(job_id: str, job_dir: Path) -> Dict[str, Any]:
    """S3 が設定されていればアップロードする。未設定の場合はスキップ。"""
    s3 = _import_s3_storage()
    if s3 is None or not s3.is_s3_configured():
        logger.info("[worker] S3 未設定のためアップロードをスキップ: job_id=%s", job_id)
        return {"skipped": True, "reason": "S3 未設定"}

    try:
        uploaded, failed = s3.upload_directory_to_s3(
            job_dir / "output",
            job_id,
            sub_prefix="output",
        )
        # report ディレクトリもアップロード
        if (job_dir / "report").exists():
            u2, f2 = s3.upload_directory_to_s3(
                job_dir / "report",
                job_id,
                sub_prefix="report",
            )
            uploaded += u2
            failed += f2
        logger.info("[worker] S3 アップロード完了: job_id=%s uploaded=%d failed=%d",
                    job_id, len(uploaded), len(failed))
        return {"uploaded": len(uploaded), "failed": len(failed), "skipped": False}
    except Exception as e:
        logger.warning("[worker] S3 アップロードエラー: job_id=%s error=%s", job_id, e)
        return {"skipped": True, "reason": str(e)[:200]}


def _step_generate_delivery_page(job_id: str, job_dir: Path, job: dict) -> Optional[str]:
    """S3 が設定されていれば納品ページを生成する。"""
    s3 = _import_s3_storage()
    dp = _import_delivery_page()
    am = _import_artifact_manifest()

    if s3 is None or not s3.is_s3_configured():
        logger.info("[worker] S3 未設定のため納品ページ生成をスキップ: job_id=%s", job_id)
        return None

    if dp is None:
        logger.warning("[worker] delivery_page モジュールが利用できません。スキップ。")
        return None

    try:
        # マニフェスト取得
        manifest_data: List[dict] = []
        if am:
            try:
                manifest_data = am.load_artifact_manifest(job_dir)
            except Exception:
                pass

        # presigned URL を生成
        presigned_urls = s3.generate_presigned_urls_for_job(job_id, manifest_data)
        expires_at = s3.get_presigned_url_expires_at()

        # 顧客情報（PII はページに含めない）
        customer_info = {"job_id": job_id}

        html_content = dp.generate_delivery_page(
            manifest={"artifacts": manifest_data} if manifest_data else {},
            customer_info=customer_info,
            job_id=job_id,
            presigned_urls=presigned_urls,
            expires_at=expires_at,
            job_label=job_id[:16],
        )

        page_path = job_dir / "report" / "delivery_page.html"
        page_path.write_text(html_content, encoding="utf-8")

        # S3 にアップロード
        s3_key = s3.build_s3_key_for_job(job_id, "report/delivery_page.html")
        s3.upload_file_to_s3(page_path, s3_key)
        delivery_url = s3.generate_presigned_url(s3_key)

        logger.info("[worker] 納品ページ生成完了: job_id=%s", job_id)
        return delivery_url

    except Exception as e:
        logger.warning("[worker] 納品ページ生成エラー: job_id=%s error=%s", job_id, e)
        return None


def _step_update_delivery_url(job_id: str, delivery_url: Optional[str]) -> None:
    """ジョブに納品 URL を記録する。"""
    jm = _import_job_manager()
    try:
        s3 = _import_s3_storage()
        expires_at = s3.get_presigned_url_expires_at() if s3 else ""
        jm.update_job(
            job_id,
            delivery_page_url=delivery_url,
            delivery_url_expires_at=expires_at,
            upload_status="complete" if delivery_url else "partial",
        )
        logger.info("[worker] 納品URL更新: job_id=%s url_set=%s", job_id, bool(delivery_url))
    except Exception as e:
        logger.warning("[worker] 納品URL更新エラー: job_id=%s error=%s", job_id, e)


def _step_mark_ready(job_id: str) -> None:
    """ジョブのステータスを delivery_ready に更新する。"""
    jm = _import_job_manager()
    try:
        jm.update_job(job_id, status="delivery_ready")
        logger.info("[worker] ジョブステータスを delivery_ready に更新: job_id=%s", job_id)
    except Exception as e:
        logger.warning("[worker] ステータス更新エラー: job_id=%s error=%s", job_id, e)


# ── パイプライン実行 ──────────────────────────────────────────────────────────

def _run_pipeline(queue_id: str, job_id: str, job_type: str) -> bool:
    """ジョブのパイプラインを実行する。

    Returns
    -------
    bool
        True: 成功  False: 失敗
    """
    qm = _import_queue_manager()
    jm = _import_job_manager()

    try:
        job = jm.load_job(job_id)
    except FileNotFoundError:
        qm.fail_queue_job(queue_id, f"job.json が見つかりません: job_id={job_id}",
                          failed_step="validate_inputs")
        return False

    job_dir = Path(jm.JOBS_DIR) / job_id
    steps: List[Dict[str, Any]] = []

    def record(step: str, success: bool, error: str = "") -> None:
        started_at = datetime.now().isoformat(timespec="seconds")
        steps.append({
            "step":        step,
            "success":     success,
            "started_at":  started_at,
            "finished_at": started_at,
            "error":       error[:500] if error else "",
        })
        # キャンセル確認
        if qm.is_cancel_requested(queue_id):
            raise InterruptedError("キャンセル要求を受け取りました。")

    # ─ ステップ定義（致命的: validate_inputs / run_analysis / generate_artifacts）─
    pipeline_steps = {
        "validate_inputs":     lambda: _step_validate_inputs(job_id, job_dir),
        "run_analysis":        lambda: _step_run_analysis(job_id, job_dir, job),
        "generate_artifacts":  lambda: _step_generate_artifacts(job_id, job_dir),
        # Phase 10: 非致命的ステップ（失敗しても処理継続）
        "check_video_quality": lambda: _step_check_video_quality(job_id, job_dir),
        "detect_phases":       lambda: _step_detect_phases(job_id, job_dir),
        # Phase 11: アノテーションドラフト作成（非致命的）
        "create_annotation_draft": lambda: _step_create_annotation_draft(job_id, job_dir),
        # Phase 12: 高度解析指標（非致命的）
        "compute_advanced_metrics":          lambda: _step_compute_advanced_metrics(job_id, job_dir),
        "generate_advanced_metrics_report":  lambda: _step_generate_advanced_metrics_report(job_id, job_dir),
        "export_advanced_metrics":           lambda: _step_export_advanced_metrics(job_id, job_dir),
        "generate_reports":    lambda: _step_generate_reports(job_id, job_dir),
        "generate_packages":   lambda: _step_generate_packages(job_id, job_dir),
        # Phase 13: ユーザー向けダッシュボード（非致命的）
        "generate_user_dashboard": lambda: _step_generate_user_dashboard(job_id, job_dir),
        # Phase 14: ダッシュボードマニフェスト（非致命的）
        "generate_dashboard_manifest": lambda: _step_generate_dashboard_manifest(job_id, job_dir),
        "upload_to_s3":        lambda: _step_upload_to_s3(job_id, job_dir),
    }
    fatal_steps = {"validate_inputs", "run_analysis", "generate_artifacts"}
    # check_video_quality / detect_phases は fatal_steps に含まれない

    # ─ ステップ実行 ────────────────────────────────────────────────────────
    # ジョブステータスを running に更新
    try:
        jm.update_job(job_id, status="running")
    except Exception:
        pass

    for step_name, step_fn in pipeline_steps.items():
        # 管理画面のリアルタイム表示のため current_step を更新
        try:
            qm.update_queue_job(queue_id, current_step=step_name)
        except Exception:
            pass

        try:
            step_fn()
            record(step_name, True)
            logger.info("[worker] ステップ完了: %s (queue_id=%s)", step_name, queue_id)
        except InterruptedError as e:
            logger.info("[worker] キャンセル: queue_id=%s step=%s", queue_id, step_name)
            qm.fail_queue_job(queue_id, str(e), "cancelled", steps)
            try:
                jm.update_job(job_id, status="cancelled")
            except Exception:
                pass
            return False
        except Exception as e:
            logger.error("[worker] ステップ失敗: %s (queue_id=%s) error=%s",
                         step_name, queue_id, e)
            record(step_name, False, str(e))

            if step_name in fatal_steps:
                qm.fail_queue_job(queue_id, str(e), step_name, steps)
                try:
                    jm.update_job(job_id, status="failed", error=str(e)[:500])
                except Exception:
                    pass
                return False
            # 非致命的ステップはログだけで継続

    # ─ 後処理ステップ（generate_delivery_page → update_delivery_url → mark_ready）──
    # delivery_url の戻り値を次ステップに渡す必要があるため、ループ外で順に実行する

    # キャンセル確認
    if qm.is_cancel_requested(queue_id):
        qm.fail_queue_job(queue_id, "キャンセル要求を受け取りました。", "cancelled", steps)
        try:
            jm.update_job(job_id, status="cancelled")
        except Exception:
            pass
        return False

    # generate_delivery_page（非致命的）
    try:
        qm.update_queue_job(queue_id, current_step="generate_delivery_page")
    except Exception:
        pass
    delivery_url: Optional[str] = None
    try:
        delivery_url = _step_generate_delivery_page(job_id, job_dir, job)
        record("generate_delivery_page", True)
        logger.info("[worker] ステップ完了: generate_delivery_page (queue_id=%s)", queue_id)
    except InterruptedError as e:
        qm.fail_queue_job(queue_id, str(e), "cancelled", steps)
        try:
            jm.update_job(job_id, status="cancelled")
        except Exception:
            pass
        return False
    except Exception as e:
        logger.warning("[worker] generate_delivery_page スキップ (非致命的): %s", e)
        record("generate_delivery_page", False, str(e))

    # Phase 13: upload_user_dashboard（非致命的）
    try:
        qm.update_queue_job(queue_id, current_step="upload_user_dashboard")
    except Exception:
        pass
    dashboard_url: Optional[str] = None
    expires_at_str: str = ""
    try:
        dashboard_url = _step_upload_dashboard_to_s3(job_id, job_dir)
        s3_mod = _import_s3_storage()
        if s3_mod:
            expires_at_str = s3_mod.get_presigned_url_expires_at()
        record("upload_user_dashboard", True)
        logger.info("[worker] ステップ完了: upload_user_dashboard (queue_id=%s)", queue_id)
    except Exception as e:
        logger.warning("[worker] upload_user_dashboard スキップ (非致命的): %s", e)
        record("upload_user_dashboard", False, str(e))

    # Phase 13: update_dashboard_url（非致命的）
    try:
        qm.update_queue_job(queue_id, current_step="update_dashboard_url")
    except Exception:
        pass
    try:
        _step_update_dashboard_url(job_id, dashboard_url, expires_at_str)
        record("update_dashboard_url", True)
    except Exception as e:
        record("update_dashboard_url", False, str(e))

    # Phase 14: refresh_dashboard_manifest（非致命的）- S3 URL 反映後にマニフェストを再生成
    try:
        qm.update_queue_job(queue_id, current_step="refresh_dashboard_manifest")
    except Exception:
        pass
    try:
        _step_generate_dashboard_manifest(job_id, job_dir)
        record("refresh_dashboard_manifest", True)
        logger.info("[worker] ステップ完了: refresh_dashboard_manifest (queue_id=%s)", queue_id)
    except Exception as e:
        logger.warning("[worker] refresh_dashboard_manifest スキップ (非致命的): %s", e)
        record("refresh_dashboard_manifest", False, str(e))

    # update_delivery_url（非致命的）
    try:
        qm.update_queue_job(queue_id, current_step="update_delivery_url")
    except Exception:
        pass
    try:
        _step_update_delivery_url(job_id, delivery_url)
        record("update_delivery_url", True)
        logger.info("[worker] ステップ完了: update_delivery_url (queue_id=%s)", queue_id)
    except Exception as e:
        record("update_delivery_url", False, str(e))

    # mark_ready（非致命的）
    try:
        qm.update_queue_job(queue_id, current_step="mark_ready")
    except Exception:
        pass
    try:
        _step_mark_ready(job_id)
        record("mark_ready", True)
        logger.info("[worker] ステップ完了: mark_ready (queue_id=%s)", queue_id)
    except Exception as e:
        record("mark_ready", False, str(e))

    # 完了
    qm.complete_queue_job(queue_id, steps)

    logger.info("[worker] パイプライン完了: queue_id=%s job_id=%s", queue_id, job_id)
    return True


# ── ワーカーメインループ ──────────────────────────────────────────────────────

def run_worker(
    once: bool = False,
    poll_interval: int = _DEFAULT_POLL_INTERVAL,
    max_jobs: Optional[int] = None,
) -> int:
    """ワーカーのメインループを実行する。

    Parameters
    ----------
    once : bool
        True の場合、1件だけ処理して終了（--once フラグ）
    poll_interval : int
        pending キューをチェックする間隔（秒）
    max_jobs : int, optional
        最大処理件数。超えると終了

    Returns
    -------
    int
        処理したジョブ件数
    """
    qm = _import_queue_manager()
    processed = 0

    logger.info("[worker] 起動: once=%s poll_interval=%ds max_jobs=%s",
                once, poll_interval, max_jobs)

    while True:
        qjob = qm.claim_next_pending()

        if qjob is None:
            if once:
                logger.info("[worker] pending キューが空です。終了します。")
                break
            logger.debug("[worker] pending キューが空。%d 秒後に再確認...", poll_interval)
            time.sleep(poll_interval)
            continue

        queue_id = qjob["queue_id"]
        job_id   = qjob["job_id"]
        job_type = qjob.get("job_type", "full_pipeline")

        logger.info("[worker] ジョブ処理開始: queue_id=%s job_id=%s type=%s",
                    queue_id, job_id, job_type)

        try:
            success = _run_pipeline(queue_id, job_id, job_type)
        except Exception as exc:
            logger.exception("[worker] 予期しないエラー: queue_id=%s error=%s",
                             queue_id, exc)
            try:
                qm.fail_queue_job(queue_id, f"予期しないエラー: {exc}", "unknown")
            except Exception:
                pass
            success = False

        processed += 1
        logger.info("[worker] ジョブ処理終了: queue_id=%s success=%s", queue_id, success)

        if once or (max_jobs is not None and processed >= max_jobs):
            break

        time.sleep(1)  # 連続処理の場合は少し待機

    logger.info("[worker] 終了: processed=%d", processed)
    return processed


# ── エントリポイント ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Javelin Video Analysis バックグラウンドワーカー"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="1件だけ処理して終了する",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=_DEFAULT_POLL_INTERVAL,
        metavar="SECONDS",
        help=f"pending キューのポーリング間隔（秒, デフォルト: {_DEFAULT_POLL_INTERVAL}）",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        metavar="N",
        help="最大処理件数（未指定の場合は無制限）",
    )
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="ワーカーロックを取得しない（テスト用）",
    )
    args = parser.parse_args()

    if not args.no_lock:
        if not _acquire_worker_lock():
            logger.error("[worker] ワーカーロックの取得に失敗しました。"
                         "別のワーカーが実行中か、stale ロックが残っています。")
            sys.exit(1)

    try:
        processed = run_worker(
            once=args.once,
            poll_interval=args.poll_interval,
            max_jobs=args.max_jobs,
        )
    except KeyboardInterrupt:
        logger.info("[worker] Ctrl+C で中断されました。")
        processed = -1
    finally:
        if not args.no_lock:
            _release_worker_lock()

    sys.exit(0 if processed >= 0 else 1)


if __name__ == "__main__":
    main()
