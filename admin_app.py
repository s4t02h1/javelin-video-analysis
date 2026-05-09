#!/usr/bin/env python3
"""
admin_app.py — Javelin Video Analysis 管理画面 (Streamlit)

起動例:
    streamlit run admin_app.py --server.address 127.0.0.1 --server.port 8501

外出先からのアクセス:
    Tailscale Serve 経由で https://<PC名>.<tailnet名>.ts.net へアクセス。
    詳細は README の「Tailscale Serveで外出先から管理画面にアクセスする」を参照。
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

_REPO_ROOT = Path(__file__).resolve().parent

from job_manager import (
    JOBS_DIR,
    COMPARISONS_DIR,
    JOB_STATUSES,
    JOB_STATUS_LABELS,
    collect_output_files,
    create_comparison,
    create_job,
    get_comparison_dir,
    get_customer_info,
    get_delivery_checklist,
    get_intake_info,
    get_job_dir,
    get_phase_frames,
    list_comparisons,
    list_jobs,
    load_comparison,
    load_job,
    update_comparison,
    update_customer_info,
    update_delivery_checklist,
    update_intake_info,
    update_job,
    update_phase_frames,
    update_job_s3_delivery,
    get_job_s3_status,
)

# ── Phase 6: intake 管理 ──────────────────────────────────────────────────────
try:
    from src.intake_manager import (
        INTAKE_STATUSES,
        INTAKE_STATUS_LABELS,
        INTAKE_SOURCES,
        CONSENT_LABELS,
        check_all_consents,
        missing_consents,
        create_intake,
        load_intake,
        update_intake,
        list_intakes,
        set_intake_status,
        archive_intake,
        reject_intake,
        convert_intake_to_job,
        generate_intake_id,
    )
    import job_manager as _jm_module
    _INTAKE_AVAILABLE = True
except ImportError as _intake_ie:
    _INTAKE_AVAILABLE = False
    INTAKE_STATUSES = []
    INTAKE_STATUS_LABELS = {}
    INTAKE_SOURCES = []
    CONSENT_LABELS = {}

# ── Phase 7: キュー管理 ───────────────────────────────────────────────────────
try:
    from src.queue_manager import (
        QUEUE_STATUSES,
        QUEUE_STATUS_LABELS,
        JOB_TYPES,
        PIPELINE_STEPS,
        create_queue_job,
        load_queue_job,
        update_queue_job,
        list_queue_jobs,
        get_queue_counts,
        find_queue_job_for_job,
        find_active_queue_job_for_job,
        cancel_queue_job,
        retry_queue_job,
    )
    _QUEUE_AVAILABLE = True
except ImportError as _qm_ie:
    _QUEUE_AVAILABLE = False
    QUEUE_STATUSES = []
    QUEUE_STATUS_LABELS = {}
    JOB_TYPES = []
    PIPELINE_STEPS = []


# ── Phase 5: S3 / 納品ページ (try import — S3 未設定でもアプリは動く) ─────────
try:
    from src.storage.s3_storage import (
        is_s3_configured,
        get_s3_config,
        build_s3_key_for_job,
        upload_file_to_s3,
        generate_presigned_url,
        generate_presigned_urls_for_job,
        get_presigned_url_expires_at,
        append_upload_log,
    )
    from src.artifact_manifest import (
        build_artifact_manifest,
        build_comparison_artifact_manifest,
        save_artifact_manifest,
        load_artifact_manifest,
    )
    from src.delivery_page import generate_delivery_page, save_delivery_page
    _S3_MODULES_AVAILABLE = True
except ImportError:
    _S3_MODULES_AVAILABLE = False

    def is_s3_configured():  # type: ignore[misc]
        return False

_RUN_PY = _REPO_ROOT / "run.py"

# ── 定数 ──────────────────────────────────────────────────────────────────────

MODE_LABELS: dict = {
    "all_variants": "全バリエーション（6種同時）★おすすめ",
    "analysis":     "コーチング解析（フェーズ・角度・軌道・運動連鎖）→ 出力1ファイル",
    "basic":        "基本（骨格のみ）→ 出力1ファイル",
    "heatmap":      "ヒートマップ → 出力1ファイル",
    "vectors":      "ベクトル → 出力1ファイル",
    "hud":          "ゲーム風 HUD → 出力1ファイル",
    "stickman":     "スティックマン → 出力1ファイル",
}

STATUS_ICONS: dict = {
    "created":          "🆕",
    "uploaded":         "📤",
    "running":          "⏳",
    "completed":        "✅",
    "reviewing":        "🔍",
    "ready_to_deliver": "📦",
    "delivered":        "📨",
    "failed":           "❌",
    "archived":         "📂",
}

SNS_PERMISSION_LABELS: dict = {
    "unknown":   "⚠️ 未確認",
    "allowed":   "✅ 許可あり",
    "anonymous": "👤 匿名なら許可",
    "denied":    "🚫 不可",
    # 後方互換
    "yes":       "✅ 許可あり",
    "no":        "🚫 不可",
}

PLAN_LABELS: dict = {
    "free_preview": "🆓 無料プレビュー",
    "light":        "💡 ライト版",
    "data_sheet":   "📊 データシート版",
    "full_report":  "📦 フルレポート版",
    "comparison":   "🔀 2動画比較版",
}


# ── ヘルパー関数 ───────────────────────────────────────────────────────────────

def _gen_button(
    label: str,
    btn_key: str,
    mod_name: str,
    fn_name: str,
    job_dir: "Path",
    spinner_text: str = "生成中...",
) -> None:
    """共通生成ボタンヘルパー。

    session_state を使ってメッセージを st.rerun() をまたいで表示する。
    エラー時はスタックトレースも表示する。
    """
    import importlib
    import traceback

    _state_key = f"_gen_result_{btn_key}"

    # 前回の実行結果を表示（あれば、表示後に削除）
    if _state_key in st.session_state:
        _r = st.session_state.pop(_state_key)
        if _r["ok"]:
            st.success(_r["msg"])
        else:
            st.error(_r["msg"])
            if _r.get("tb"):
                with st.expander("エラー詳細", expanded=False):
                    st.code(_r["tb"], language="python")

    if st.button(f"🔄 {label}", key=btn_key):
        with st.spinner(spinner_text):
            try:
                _mod = importlib.import_module(mod_name)
                _fn  = getattr(_mod, fn_name)
                _result = _fn(job_dir)
                st.session_state[_state_key] = {
                    "ok": True,
                    "msg": f"✅ 生成完了: {_result.name}",
                }
            except Exception as _e:
                st.session_state[_state_key] = {
                    "ok": False,
                    "msg": f"生成エラー: {_e}",
                    "tb": traceback.format_exc(),
                }
        st.rerun()


def _build_cmd(job: dict) -> list:
    """job dict から run.py 実行コマンドリストを組み立てる。"""
    output_dir = str(get_job_dir(job["job_id"]) / "output")
    cmd = [
        sys.executable,
        str(_RUN_PY),
        "--input",      job["input_file"],
        "--output-dir", output_dir,
    ]
    if job.get("height_m"):
        cmd += ["--height-m", str(job["height_m"])]

    mode = job.get("mode", "basic")
    flag_map = {
        "all_variants": "--all-variants",
        "analysis":     "--analysis",
        "heatmap":      "--heatmap",
        "vectors":      "--vectors",
        "hud":          "--hud",
        "stickman":     "--stickman",
    }
    if mode in flag_map:
        cmd.append(flag_map[mode])

    return cmd


def _run_job(job_id: str) -> None:
    """解析をサブプロセスで同期実行し、job.json のステータスを更新する。

    ログ出力:
        jobs/<job_id>/logs/command.txt  — 実行コマンド
        jobs/<job_id>/logs/stdout.txt   — 標準出力
        jobs/<job_id>/logs/stderr.txt   — 標準エラー出力
    """
    job = update_job(job_id, status="running")
    cmd = _build_cmd(job)

    # logs/ ディレクトリを準備
    logs_dir: Path = get_job_dir(job_id) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "command.txt").write_text(
        " ".join(cmd), encoding="utf-8"
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(_REPO_ROOT),
        )
        # stdout / stderr をファイルに保存
        (logs_dir / "stdout.txt").write_text(
            result.stdout or "", encoding="utf-8"
        )
        (logs_dir / "stderr.txt").write_text(
            result.stderr or "", encoding="utf-8"
        )
        if result.returncode == 0:
            output_files = collect_output_files(job_id)
            update_job(
                job_id,
                status="completed",
                output_files=output_files,
                error=None,
                returncode=0,
            )
        else:
            err = (result.stderr or result.stdout or "Unknown error").strip()
            update_job(
                job_id,
                status="failed",
                error=err[:2000],
                returncode=result.returncode,
            )
    except Exception as exc:
        (logs_dir / "stderr.txt").write_text(str(exc), encoding="utf-8")
        update_job(job_id, status="failed", error=str(exc), returncode=-1)


def _read_video_bytes(path: Path) -> bytes | None:
    """動画ファイルをバイト列で読み込む。失敗時は None を返す。"""
    try:
        return path.read_bytes()
    except OSError:
        return None


@st.cache_data(max_entries=20, show_spinner=False)
def _read_file_cached(path_str: str, mtime_ns: int) -> bytes:
    """ファイルをキャッシュ付きで読み込む。

    mtime_ns を引数に含めることで、ファイル更新時に自動的にキャッシュが無効化される。
    """
    return Path(path_str).read_bytes()


# 無料プレビュー動画と判定するキーワード
_PREVIEW_KEYWORDS = {"skeleton", "trail", "heatmap", "hud", "stickman", "vectors", "gaming"}


def _classify_job_files(job_dir: Path, output_files: list) -> dict:
    """
    output_files リストをカテゴリ別に分類する。

    Returns dict with keys:
        preview_mp4s  : List[Path]  — 無料プレビュー用 MP4
        frame_files   : List[Path]  — 代表フレーム画像
        graph_files   : List[Path]  — 解析グラフ画像
        csv_files     : List[Path]  — CSV データシート
        pdf_path      : Path|None   — report.pdf
        admin_files   : List[Path]  — JSON / その他管理者ファイル
        other_files   : List[Path]  — 未分類ファイル
    """
    result: dict = {
        "preview_mp4s": [],
        "frame_files":  [],
        "graph_files":  [],
        "csv_files":    [],
        "pdf_path":     None,
        "instr_pdf_path": None,
        "athlete_pdf_path": None,
        "key_frame_pdf_path": None,
        "graph_pack_pdf_path": None,
        "coach_review_pdf_path": None,
        "admin_files":  [],
        "other_files":  [],
    }
    for f in output_files:
        p = Path(f)
        suffix     = p.suffix.lower()
        name_lower = p.name.lower()
        path_fwd   = str(p).replace("\\", "/")

        if suffix == ".mp4":
            if any(kw in name_lower for kw in _PREVIEW_KEYWORDS):
                result["preview_mp4s"].append(p)
            else:
                result["other_files"].append(p)
        elif suffix == ".csv":
            result["csv_files"].append(p)
        elif suffix in (".jpg", ".jpeg", ".png"):
            if "frames/" in path_fwd:
                result["frame_files"].append(p)
            elif "graphs/" in path_fwd:
                result["graph_files"].append(p)
            else:
                result["other_files"].append(p)
        elif suffix == ".pdf":
            if "report.pdf" in name_lower:
                result["pdf_path"] = p
            elif "video_instruction" in name_lower:
                result["instr_pdf_path"] = p
            elif "athlete_data_sheet" in name_lower:
                result["athlete_pdf_path"] = p
            elif "key_frame_sheet" in name_lower:
                result["key_frame_pdf_path"] = p
            elif "graph_pack" in name_lower:
                result["graph_pack_pdf_path"] = p
            elif "coach_review_sheet" in name_lower:
                result["coach_review_pdf_path"] = p
            else:
                result["other_files"].append(p)
        elif suffix == ".json":
            result["admin_files"].append(p)
        else:
            result["other_files"].append(p)

    # output_files にない場合でも report.pdf を直接確認
    if result["pdf_path"] is None:
        _pdf = job_dir / "report" / "report.pdf"
        if _pdf.exists():
            result["pdf_path"] = _pdf

    # output_files にない場合でも video_instruction.pdf を直接確認
    if result["instr_pdf_path"] is None:
        _instr = job_dir / "report" / "video_instruction.pdf"
        if _instr.exists():
            result["instr_pdf_path"] = _instr

    # report/ 配下の新 PDF を直接確認
    for _key, _fname in [
        ("athlete_pdf_path",      "athlete_data_sheet.pdf"),
        ("key_frame_pdf_path",    "key_frame_sheet.pdf"),
        ("graph_pack_pdf_path",   "graph_pack.pdf"),
        ("coach_review_pdf_path", "coach_review_sheet.pdf"),
    ]:
        if result[_key] is None:
            _p = job_dir / "report" / _fname
            if _p.exists():
                result[_key] = _p

    return result


# ── 納品メッセージ生成 ─────────────────────────────────────────────────────────

def build_delivery_message(
    job: dict,
    customer_info: dict,
    package_type: str,
    delivery_page_url: str = "",
) -> str:
    """納品メッセージ文テンプレートを生成する。

    Parameters
    ----------
    job : dict
        job.json の内容。
    customer_info : dict
        customer_info.json の内容（空 dict でも安全）。
    package_type : str
        'free_preview' | 'data_sheet' | 'full_report'
    delivery_page_url : str, optional
        S3 presigned 納品ページURL。指定するとメッセージに挿入される。

    Returns
    -------
    str
        コピペ用の納品メッセージ文。
    """
    name: str   = customer_info.get("customer_name") or customer_info.get("nickname") or ""
    event: str  = customer_info.get("event") or "やり投げ"
    paid: str   = customer_info.get("payment_status") or "unpaid"
    social: str = customer_info.get("permission_for_social_post") or "unknown"
    # 旧値正規化
    if social == "yes":
        social = "allowed"
    elif social == "no":
        social = "denied"

    greeting = f"{name}様、お待たせいたしました！" if name else "お待たせいたしました！"

    # SNS掲載許可の補足
    _social_note = ""
    if social == "allowed":
        _social_note = "\nなお、解析事例としてSNSに掲載させていただく場合がございます（ご確認済み）。"
    elif social == "anonymous":
        _social_note = "\nSNS掲載の際はお名前・所属等を匿名にして掲載させていただく場合がございます（ご確認済み）。"
    elif social == "denied":
        _social_note = "\nSNS等への掲載はいたしません。"

    _disclaimer = (
        "\n\n⚠️ 本解析は動きの可視化を目的とした参考資料です。"
        "医療診断・怪我の診断・専門的な競技指導を代替するものではありません。"
        "ご不明な点はお気軽にご連絡ください。"
    )

    # 納品ページ URL 差し込み
    _url_block = ""
    if delivery_page_url:
        _url_block = (
            "\n\n📱 解析結果はこちらからご確認ください。\n"
            f"納品URL：\n{delivery_page_url}"
        )

    if package_type == "free_preview":
        return (
            f"{greeting}\n"
            f"{event}の動画解析「無料プレビュー版」が完成しました。\n"
            "\n"
            "まず ZIP ファイルの中の「00_最初に読んでください.pdf」をご覧ください。"
            "ファイル構成・見方の説明が書いてあります。\n"
            "\n"
            "解析動画と代表フレーム画像が含まれています。動画は各アングルの動きをご確認いただけます。\n"
            "\n"
            "CSVやPDFレポート・グラフを含む詳細版（データシート版・フルレポート版）もご用意できます。"
            f"ご興味があればお気軽にお申し付けください。{_url_block}{_social_note}{_disclaimer}"
        )

    elif package_type == "data_sheet":
        _payment_note = ""
        if paid == "unpaid":
            _payment_note = "\n\n※ お支払いがまだの場合は、お支払い方法をご確認の上ご連絡ください。"
        elif paid == "paid":
            _payment_note = "\n\nお支払いの確認が取れております。ありがとうございます。"
        return (
            f"{greeting}\n"
            f"{event}の動画解析「有料データシート版」が完成しました。\n"
            "\n"
            "まず ZIP の「00_最初に読んでください.pdf」をご覧ください。\n"
            "\n"
            "今回の内容:\n"
            "・解析動画（全バリエーション）\n"
            "・選手向けサマリーPDF（主要指標・グラフ解説）\n"
            "・代表フレームシート\n"
            "・姿勢推定データ CSV（研究・開発用 — 通常は開かなくて大丈夫です）\n"
            "\n"
            "練習の振り返りや指導者との共有にお役立てください。\n"
            f"フルレポート版もご希望の場合はお申し付けください。{_url_block}{_payment_note}{_social_note}{_disclaimer}"
        )

    elif package_type == "full_report":
        _payment_note = ""
        if paid == "unpaid":
            _payment_note = "\n\n※ お支払いがまだの場合は、お支払い方法をご確認の上ご連絡ください。"
        elif paid == "paid":
            _payment_note = "\n\nお支払いの確認が取れております。ありがとうございます。"
        return (
            f"{greeting}\n"
            f"{event}の動画解析「有料フルレポート版」が完成しました。\n"
            "\n"
            "まず ZIP の「00_最初に読んでください.pdf」をご覧ください。\n"
            "\n"
            "今回の内容:\n"
            "・PDFレポート（詳細解析）\n"
            "・解析動画（全バリエーション）\n"
            "・選手向けサマリーPDF\n"
            "・コーチ向けレビューシート\n"
            "・グラフ解説PDF\n"
            "・代表フレームシート\n"
            "・CSV・JSON・グラフ画像（研究・開発用 — 通常は開かなくて大丈夫です）\n"
            "\n"
            f"今後の練習の振り返りにご活用いただけますと幸いです。{_url_block}{_payment_note}{_social_note}{_disclaimer}"
        )

    else:
        return f"package_type '{package_type}' は未定義です。"


def build_sns_permission_message(customer_info: dict) -> str:
    """SNS掲載許可確認用メッセージを生成する。"""
    name: str = customer_info.get("customer_name") or customer_info.get("nickname") or ""
    greeting = f"{name}様、" if name else ""

    return (
        f"{greeting}一点ご確認させてください。\n"
        "\n"
        "今回の解析結果・フォーム画像を、SNS（Instagram等）に"
        "「解析事例」として掲載させていただく場合があります。\n"
        "\n"
        "掲載にあたり、以下についてお聞かせください。\n"
        "\n"
        "① お名前・Instagram IDを出してもよいか\n"
        "② 学校名・所属チームを出してもよいか\n"
        "③ 顔が映っているフレームをそのまま使ってよいか\n"
        "④ ゼッケン番号等が写っている場合、そのまま使ってよいか\n"
        "⑤ 音声がある場合、使用してよいか\n"
        "\n"
        "上記すべて不可でも、「匿名加工（名前・顔・所属を隠す）」なら掲載可能でしょうか？\n"
        "\n"
        "どちらもご不安な場合は「掲載不可」で全く問題ありません。\n"
        "お答えいただいた内容がサービスのご利用に影響することはありません。\n"
        "\n"
        "また、一度許可をいただいた後でも、取り下げをご希望の場合はご連絡ください。\n"
        "よろしくお願いいたします。"
    )


# ── ページ設定 ─────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Javelin 管理画面",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 Javelin Video Analysis — 管理画面")


# ── 運用チェックリスト タブ関数 ───────────────────────────────────────────────

def render_operation_checklist_tab() -> None:
    """解析依頼の受付〜納品までの運用チェックリストを表示する。"""
    st.header("📋 運用チェックリスト")
    st.caption(
        "解析依頼を受けてから納品するまでの抜け漏れを防ぐためのチェックリストです。"
        "チェック状態はこのセッション内のみ保持されます。"
    )

    # ── 免責事項 ──────────────────────────────────────────────────────────────
    st.info(
        "⚠️ 本解析は、動画から身体の動きや軌跡を可視化し、練習の振り返りを補助するための参考資料です。"
        "競技指導・医療判断・怪我の診断を代替するものではありません。"
    )
    st.divider()

    # チェック項目定義: (セクション名, [(key, ラベル), ...])
    _sections: list[tuple[str, list[tuple[str, str]]]] = [
        (
            "📥 受付前",
            [
                ("pre_01", "顧客名またはInstagram IDを確認した"),
                ("pre_02", "種目（やり投げ等）を確認した"),
                ("pre_03", "利き腕（右 / 左）を確認した"),
                ("pre_04", "身長を確認した（または未計測を了承済み）"),
                ("pre_05", "撮影方向（側面 / 後方 / 正面 / 斜め）を確認した"),
                ("pre_06", "SNS・資料への掲載可否を確認した"),
                ("pre_07", "有料 / 無料プランを確定した"),
            ],
        ),
        (
            "📹 動画受領後",
            [
                ("recv_01", "動画ファイルを受け取った"),
                ("recv_02", "動画が再生できることを確認した（VLC等）"),
                ("recv_03", "動画形式が .mp4 であることを確認した"),
                ("recv_04", "動画に人物が映っていることを確認した"),
                ("recv_05", "撮影方向が適切か確認した（側面推奨）"),
            ],
        ),
        (
            "⚙️ 解析前",
            [
                ("pre_ana_01", "ジョブを新規作成した"),
                ("pre_ana_02", "顧客情報（customer_info.json）を入力した"),
                ("pre_ana_03", "解析モードを選択した（all_variants 推奨）"),
                ("pre_ana_04", "身長を設定した（任意）"),
                ("pre_ana_05", "解析を開始した"),
            ],
        ),
        (
            "✅ 解析後",
            [
                ("post_01", "解析が completed ステータスで完了していることを確認した"),
                ("post_02", "代表フレームが生成されていることを確認した"),
                ("post_03", "グラフ画像が生成されていることを確認した"),
                ("post_04", "解析サマリー (analysis_summary.json) を生成した"),
                ("post_05", "PDFレポートを確認・再生成した"),
                ("post_06", "コーチコメントをPDFに入力した"),
            ],
        ),
        (
            "🆓 無料プレビュー納品",
            [
                ("free_01", "free_preview.zip を生成した"),
                ("free_02", "ZIPの中身（動画・フレーム画像）を確認した"),
                ("free_03", "無料プレビュー納品文を作成した"),
                ("free_04", "顧客に納品した"),
                ("free_05", "有料版への案内メッセージを送った"),
            ],
        ),
        (
            "📊 有料データシート案内",
            [
                ("paid_ds_01", "data_sheet_package.zip を生成した"),
                ("paid_ds_02", "グラフ画像（3種）が含まれていることを確認した"),
                ("paid_ds_03", "pose_landmarks.csv が含まれていることを確認した"),
                ("paid_ds_04", "有料データシート納品文を作成・送付した"),
                ("paid_ds_05", "支払い状況を確認した"),
            ],
        ),
        (
            "📄 フルレポート納品",
            [
                ("full_01", "full_report_package.zip を生成した"),
                ("full_02", "PDFレポートを最終確認した"),
                ("full_03", "全解析動画が ZIP に含まれていることを確認した"),
                ("full_04", "フルレポート納品文を作成・送付した"),
                ("full_05", "delivery_status を 'delivered' に更新した"),
                ("full_06", "支払い完了を確認した"),
            ],
        ),
        (
            "📸 SNS掲載前確認",
            [
                ("sns_01", "顧客のSNS掲載許可を得ていることを確認した"),
                ("sns_02", "顧客名・IDの表示方法を確認した（匿名 / 実名）"),
                ("sns_03", "動画・画像に個人情報が映り込んでいないか確認した"),
                ("sns_04", "投稿文に免責事項（参考資料である旨）を含めた"),
            ],
        ),
    ]

    _total  = sum(len(items) for _, items in _sections)
    _checked = 0

    for _sec_title, _items in _sections:
        st.subheader(_sec_title)
        for _key, _label in _items:
            _full_key = f"checklist_{_key}"
            if st.checkbox(_label, key=_full_key):
                _checked += 1
        st.divider()

    # 進捗バー
    _pct = int(_checked / _total * 100) if _total > 0 else 0
    st.markdown(f"**進捗: {_checked} / {_total} 項目チェック済み ({_pct}%)**")
    st.progress(_pct / 100)

    if _checked == _total:
        st.success("🎉 全項目チェック完了！納品準備が整いました。")
    elif _checked >= _total * 0.8:
        st.info("もう少しです。残りの項目を確認してください。")


tab_new, tab_history, tab_compare, tab_checklist, tab_import, tab_intakes, tab_queue = st.tabs(
    ["▶ 新規ジョブ", "📋 ジョブ履歴", "⚖️ ジョブ比較", "✅ 運用チェックリスト", "📥 CSVインポート", "📨 受付一覧", "⚙️ キュー管理"]
)


# ─── Tab 1: 新規ジョブ ─────────────────────────────────────────────────────────

with tab_new:
    st.header("新しい解析ジョブを作成")

    uploaded = st.file_uploader(
        "解析する動画をアップロード（.mp4）",
        type=["mp4"],
        help="大容量動画の場合、アップロードに時間がかかることがあります。",
    )

    col1, col2 = st.columns(2)
    with col1:
        use_height = st.checkbox("身長を指定する", value=True)
        height_m = st.number_input(
            "被写体の身長（m）",
            min_value=0.5,
            max_value=2.5,
            value=1.75,
            step=0.01,
            disabled=not use_height,
        )
    with col2:
        mode = st.selectbox(
            "解析モード",
            options=list(MODE_LABELS.keys()),
            format_func=lambda k: MODE_LABELS[k],
            index=0,  # デフォルト: 全バリエーション
            help="全バリエーションを選ぶと 骨格・ヒートマップ・HUD・スティックマン の4ファイルを同時出力します",
        )

    st.markdown("---")
    st.markdown("#### 👤 顧客情報（任意）")
    _nj_col1, _nj_col2 = st.columns(2)
    with _nj_col1:
        customer_name = st.text_input("顧客名", placeholder="山田 太郎")
        instagram_id  = st.text_input("Instagram ID", placeholder="@username")
        event         = st.text_input("種目", value="javelin")
    with _nj_col2:
        dominant_hand = st.selectbox(
            "利き腕",
            options=["right", "left", "unknown"],
            format_func=lambda x: {"right": "右 (right)", "left": "左 (left)", "unknown": "不明 (unknown)"}[x],
        )
        camera_angle = st.selectbox(
            "撮影方向",
            options=["side", "back", "front", "diagonal", "unknown"],
            format_func=lambda x: {"side": "側面 (side)", "back": "後方 (back)", "front": "正面 (front)", "diagonal": "斜め (diagonal)", "unknown": "不明 (unknown)"}[x],
        )
        paid_status = st.selectbox(
            "有料ステータス",
            options=["unknown", "free", "data_sheet", "full_report"],
            format_func=lambda x: {"unknown": "未設定", "free": "無料", "data_sheet": "データシート", "full_report": "フルレポート"}[x],
        )
    request_note = st.text_area("相談内容メモ", placeholder="競技歴・フォームの悩みなど", height=80)

    run_btn = st.button(
        "▶ 解析を開始",
        type="primary",
        disabled=(uploaded is None),
    )

    if run_btn and uploaded is not None:
        h = height_m if use_height else None

        with st.spinner("ジョブを準備中..."):
            job = create_job(height_m=h, mode=mode)
            Path(job["input_file"]).write_bytes(uploaded.read())
            update_customer_info(
                job["job_id"],
                customer_name=customer_name,
                instagram_id=instagram_id,
                event=event,
                dominant_hand=dominant_hand,
                height_m=h,
                camera_angle=camera_angle,
                paid_status=paid_status,
                request_note=request_note,
            )

        st.info(f"ジョブID: `{job['job_id']}` — 解析を開始します...")

        with st.spinner("解析中... しばらくお待ちください（画面はそのままにしてください）"):
            _run_job(job["job_id"])

        final_job = next(
            (j for j in list_jobs() if j["job_id"] == job["job_id"]), None
        )

        if final_job and final_job["status"] == "completed":
            st.success(
                f"✅ 解析が完了しました！ "
                f"出力ファイル数: {len(final_job['output_files'])}"
            )
            st.info("「ジョブ履歴」タブから結果を確認できます。")
        else:
            err = (final_job or {}).get("error") or "不明なエラー"
            st.error(f"❌ 解析に失敗しました\n\n```\n{err}\n```")


# ─── Tab 2: ジョブ履歴 ────────────────────────────────────────────────────────

with tab_history:
    st.header("過去のジョブ一覧")

    _hist_refresh, _hist_filter_col = st.columns([1, 5])
    with _hist_refresh:
        if st.button("🔄 更新"):
            st.rerun()

    jobs = list_jobs()

    if not jobs:
        st.info("ジョブがまだありません。「新規ジョブ」タブから解析を開始してください。")
    else:
        # ── フィルタ ──────────────────────────────────────────────────────────
        with st.expander("🔍 フィルタ・絞り込み", expanded=False):
            _filt_col1, _filt_col2, _filt_col3 = st.columns(3)
            with _filt_col1:
                _filt_status = st.multiselect(
                    "ステータスで絞り込み",
                    options=JOB_STATUSES,
                    default=[],
                    format_func=lambda s: f"{STATUS_ICONS.get(s, '')} {JOB_STATUS_LABELS.get(s, s)}",
                )
            with _filt_col2:
                _filt_plan = st.multiselect(
                    "プランで絞り込み",
                    options=["free_preview", "data_sheet", "full_report"],
                    default=[],
                    format_func=lambda p: PLAN_LABELS.get(p, p),
                )
            with _filt_col3:
                _filt_undelivered = st.checkbox("未納品のみ表示", value=False)
                _filt_failed      = st.checkbox("エラーのみ表示", value=False)
                _filt_ready       = st.checkbox("納品準備完了のみ", value=False)

        # ── フィルタ適用 ──────────────────────────────────────────────────────
        def _apply_filters(all_jobs: list) -> list:
            result = all_jobs
            if _filt_failed:
                return [j for j in result if j.get("status") == "failed"]
            if _filt_ready:
                return [j for j in result if j.get("status") == "ready_to_deliver"]
            if _filt_undelivered:
                result = [j for j in result if j.get("status") not in ("delivered", "archived")]
            if _filt_status:
                result = [j for j in result if j.get("status") in _filt_status]
            if _filt_plan:
                _ci_cache: dict[str, dict] = {}
                filtered = []
                for j in result:
                    ci = _ci_cache.setdefault(j["job_id"], get_customer_info(j["job_id"]))
                    if ci.get("plan", "free_preview") in _filt_plan:
                        filtered.append(j)
                result = filtered
            return result

        _filtered_jobs = _apply_filters(jobs)

        if not _filtered_jobs:
            st.info("条件に一致するジョブがありません。フィルタを変更してください。")
        else:
            # ── 一覧テーブル ───────────────────────────────────────────────
            def _row_for_job(j: dict) -> dict:
                ci = get_customer_info(j["job_id"])
                _jdir = get_job_dir(j["job_id"])
                # 生成済み確認
                _has_pdf  = (_jdir / "report" / "report.pdf").exists()
                _has_zip  = (_jdir / "deliverables" / "free_preview.zip").exists() or \
                            (_jdir / "deliverables" / "data_sheet_package.zip").exists() or \
                            (_jdir / "deliverables" / "full_report_package.zip").exists()
                _has_mp4  = any((_jdir / "output").glob("*.mp4")) if (_jdir / "output").exists() else False
                _status   = j.get("status", "created")
                _social   = ci.get("permission_for_social_post", "unknown")
                return {
                    "ジョブID":      j["job_id"],
                    "選手名":        ci.get("customer_name") or ci.get("nickname") or "—",
                    "受付日":        (j.get("created_at") or "")[:10] or "—",
                    "プラン":        PLAN_LABELS.get(ci.get("plan", "free_preview"), ci.get("plan", "—")),
                    "ステータス":    STATUS_ICONS.get(_status, "?") + " " + JOB_STATUS_LABELS.get(_status, _status),
                    "PDF":          "✅" if _has_pdf else "—",
                    "ZIP":          "✅" if _has_zip else "—",
                    "解析動画":      "✅" if _has_mp4 else "—",
                    "納品済み":      "✅" if _status == "delivered" else "—",
                    "SNS許可":       SNS_PERMISSION_LABELS.get(_social, _social),
                    "最終更新":      (j.get("updated_at") or "")[:16] or "—",
                }

            _table_rows = [_row_for_job(j) for j in _filtered_jobs]
            st.dataframe(_table_rows, use_container_width=True, hide_index=True)
            st.caption(f"{len(_filtered_jobs)} 件 / 全 {len(jobs)} 件")

        # ── ジョブ選択（全ジョブから選択可能にする） ──────────────────────────
        selected_id = st.selectbox(
            "詳細を表示するジョブを選択",
            options=[j["job_id"] for j in jobs],
            format_func=lambda jid: next(
                (f"{j.get('created_at', '')[:10]}  {get_customer_info(jid).get('customer_name') or jid}  [{jid}]"
                 for j in jobs if j["job_id"] == jid), jid
            ),
        )

        if selected_id:
            job = next(j for j in jobs if j["job_id"] == selected_id)

            st.divider()
            st.subheader(f"ジョブ詳細: `{selected_id}`")

            _job_dir = get_job_dir(selected_id)
            _all_files = job.get("output_files") or collect_output_files(job["job_id"])
            _cls = _classify_job_files(_job_dir, _all_files)

            # ══════════════════════════════════════════════════════════════════
            # A. Job Summary + ステータス管理
            # ══════════════════════════════════════════════════════════════════
            st.markdown("#### 🗂️ A. Job Summary")

            _ci_for_summary = get_customer_info(selected_id)
            _current_status = job.get("status", "created")
            _inp_p = Path(job.get("input_file", ""))

            _sa1, _sa2 = st.columns([3, 2])
            with _sa1:
                _summary_pairs = [
                    ("Job ID",      job.get("job_id", "—")),
                    ("ステータス",  STATUS_ICONS.get(_current_status, "?") + " " + JOB_STATUS_LABELS.get(_current_status, _current_status)),
                    ("選手名",      _ci_for_summary.get("customer_name") or _ci_for_summary.get("nickname") or "—"),
                    ("プラン",      PLAN_LABELS.get(_ci_for_summary.get("plan", "free_preview"), _ci_for_summary.get("plan", "—"))),
                    ("受付日",      (job.get("created_at") or "")[:16] or "—"),
                    ("最終更新",    (job.get("updated_at") or "")[:16] or "—"),
                    ("身長 (m)",    str(job.get("height_m", "—"))),
                    ("モード",      job.get("mode", "—")),
                    ("入力動画",    _inp_p.name if _inp_p.name else "—"),
                ]
                for _k, _v in _summary_pairs:
                    st.markdown(f"**{_k}**: {_v}")

            with _sa2:
                st.markdown("**ステータス変更**")
                _new_status = st.selectbox(
                    "新しいステータス",
                    options=JOB_STATUSES,
                    index=JOB_STATUSES.index(_current_status) if _current_status in JOB_STATUSES else 0,
                    format_func=lambda s: f"{STATUS_ICONS.get(s, '')} {JOB_STATUS_LABELS.get(s, s)}",
                    key=f"status_select_{selected_id}",
                    label_visibility="collapsed",
                )
                _status_state_key = f"_status_change_{selected_id}"
                if _status_state_key in st.session_state:
                    _sr = st.session_state.pop(_status_state_key)
                    if _sr["ok"]:
                        st.success(_sr["msg"])
                    else:
                        st.error(_sr["msg"])
                if st.button("💾 ステータスを変更", key=f"btn_status_{selected_id}", use_container_width=True):
                    try:
                        from src.job_logger import log_status_change
                        _old = _current_status
                        update_job(selected_id, status=_new_status)
                        if _new_status == "delivered":
                            _delivered_now = datetime.now().isoformat(timespec="seconds")
                            update_customer_info(selected_id, delivered_at=_delivered_now)
                        log_status_change(selected_id, _old, _new_status)
                        st.session_state[_status_state_key] = {"ok": True, "msg": f"✅ {JOB_STATUS_LABELS.get(_new_status, _new_status)} に変更しました"}
                    except Exception as _se:
                        st.session_state[_status_state_key] = {"ok": False, "msg": f"変更エラー: {_se}"}
                    st.rerun()

                st.divider()
                st.markdown("**クイック操作**")
                _qbtn1, _qbtn2 = st.columns(2)
                with _qbtn1:
                    if st.button("📦 納品準備完了", key=f"btn_ready_{selected_id}", use_container_width=True):
                        update_job(selected_id, status="ready_to_deliver")
                        from src.job_logger import log_status_change
                        log_status_change(selected_id, _current_status, "ready_to_deliver")
                        st.rerun()
                with _qbtn2:
                    if st.button("📨 納品済みにする", key=f"btn_delivered_{selected_id}", use_container_width=True):
                        update_job(selected_id, status="delivered")
                        update_customer_info(selected_id, delivered_at=datetime.now().isoformat(timespec="seconds"))
                        from src.job_logger import log_status_change
                        log_status_change(selected_id, _current_status, "delivered")
                        st.rerun()
                _qbtn3, _qbtn4 = st.columns(2)
                with _qbtn3:
                    if st.button("🔄 エラーをリセット", key=f"btn_reset_err_{selected_id}", use_container_width=True):
                        update_job(selected_id, status="completed", error=None)
                        from src.job_logger import log_status_change
                        log_status_change(selected_id, _current_status, "completed")
                        st.rerun()
                with _qbtn4:
                    if st.button("📂 アーカイブ", key=f"btn_archive_{selected_id}", use_container_width=True):
                        update_job(selected_id, status="archived")
                        from src.job_logger import log_status_change
                        log_status_change(selected_id, _current_status, "archived")
                        st.rerun()

            if job.get("error"):
                st.error(f"❌ エラー:\n```\n{job['error']}\n```")

            with st.expander("📥 入力動画", expanded=False):
                if _inp_p.exists():
                    _vb = _read_video_bytes(_inp_p)
                    if _vb:
                        st.download_button(
                            label=f"⬇ {_inp_p.name}",
                            data=_vb, file_name=_inp_p.name,
                            mime="video/mp4", key=f"dl_input_{job['job_id']}",
                        )
                        st.video(_vb)
                else:
                    st.warning("入力ファイルが見つかりません。")

            # ══════════════════════════════════════════════════════════════════
            # N. 受付情報（intake_info.json）
            # ══════════════════════════════════════════════════════════════════
            with st.expander("📝 N. 受付情報", expanded=False):
                try:
                    _ii = get_intake_info(selected_id)
                except Exception as _ii_err:
                    st.warning(f"受付情報の読み込みに失敗しました: {_ii_err}")
                    _ii = {}

                with st.form(key=f"intake_form_{selected_id}"):
                    st.markdown("##### 基本情報")
                    _ni_c1, _ni_c2, _ni_c3 = st.columns(3)
                    with _ni_c1:
                        _ni_name = st.text_input(
                            "名前またはニックネーム ★",
                            value=_ii.get("name_or_nickname", ""),
                            placeholder="山田太郎 / タロウ",
                        )
                        _ni_contact = st.text_input(
                            "連絡先",
                            value=_ii.get("contact", ""),
                            placeholder="@instagram_id or LINE名",
                            help="個人情報のため慎重に扱ってください",
                        )
                        _ni_career = st.text_input(
                            "競技歴 ★",
                            value=_ii.get("athletic_career", ""),
                            placeholder="やり投げ3年目、陸上部",
                        )
                        _ni_pb = st.text_input(
                            "自己ベスト",
                            value=_ii.get("personal_best", ""),
                            placeholder="40m00",
                        )
                    with _ni_c2:
                        _age_opts = ["", "中学生", "高校生", "大学生", "社会人", "マスターズ", "その他"]
                        _ni_age_val = _ii.get("age_group", "")
                        _ni_age = st.selectbox(
                            "年齢区分",
                            options=_age_opts,
                            index=_age_opts.index(_ni_age_val) if _ni_age_val in _age_opts else 0,
                        )
                        _ni_gender = st.text_input(
                            "性別（任意）",
                            value=_ii.get("gender", ""),
                            placeholder="任意",
                        )
                        _aff_opts = ["", "中学", "高校", "大学", "社会人", "マスターズ", "その他"]
                        _ni_aff_val = _ii.get("affiliation_type", "")
                        _ni_aff = st.selectbox(
                            "所属区分",
                            options=_aff_opts,
                            index=_aff_opts.index(_ni_aff_val) if _ni_aff_val in _aff_opts else 0,
                        )
                        _arm_ii_opts = ["unknown", "right", "left"]
                        _arm_ii_labels = {"unknown": "不明", "right": "右", "left": "左"}
                        _ni_arm_val = _ii.get("dominant_arm", "unknown")
                        _ni_arm = st.selectbox(
                            "利き腕 ★",
                            options=_arm_ii_opts,
                            format_func=lambda x: _arm_ii_labels[x],
                            index=_arm_ii_opts.index(_ni_arm_val) if _ni_arm_val in _arm_ii_opts else 0,
                        )
                        _ni_height = st.number_input(
                            "身長 (m) ★",
                            min_value=0.0, max_value=2.5,
                            value=float(_ii.get("height_m") or 0.0),
                            step=0.01, format="%.2f",
                            help="0.00 は未設定扱いです",
                        )
                    with _ni_c3:
                        _ni_filming_date = st.text_input(
                            "撮影日",
                            value=_ii.get("filming_date", ""),
                            placeholder="2026-05-10",
                        )
                        _ctx_opts = ["", "大会", "練習", "その他"]
                        _ni_ctx_val = _ii.get("filming_context", "")
                        _ni_ctx = st.selectbox(
                            "撮影状況",
                            options=_ctx_opts,
                            index=_ctx_opts.index(_ni_ctx_val) if _ni_ctx_val in _ctx_opts else 0,
                        )
                        _angle_ii_opts = ["unknown", "side", "diagonal_back", "front", "other"]
                        _angle_ii_labels = {
                            "unknown": "不明", "side": "横（側面）",
                            "diagonal_back": "斜め後方", "front": "正面", "other": "その他",
                        }
                        _ni_angle_val = _ii.get("filming_angle", "unknown")
                        _ni_angle = st.selectbox(
                            "撮影角度 ★",
                            options=_angle_ii_opts,
                            format_func=lambda x: _angle_ii_labels[x],
                            index=_angle_ii_opts.index(_ni_angle_val) if _ni_angle_val in _angle_ii_opts else 0,
                        )
                        _vtype_opts = ["", "全助走", "投げのみ", "部分練習", "その他"]
                        _ni_vtype_val = _ii.get("video_type", "")
                        _ni_vtype = st.selectbox(
                            "動画種別 ★",
                            options=_vtype_opts,
                            index=_vtype_opts.index(_ni_vtype_val) if _ni_vtype_val in _vtype_opts else 0,
                        )
                        _ni_slow = st.checkbox(
                            "スロー動画",
                            value=bool(_ii.get("is_slow_motion", False)),
                        )
                        _ni_vcount = st.number_input(
                            "動画本数",
                            min_value=1, max_value=20,
                            value=int(_ii.get("video_count") or 1),
                        )

                    st.markdown("##### 相談内容")
                    _ni_focus_main = st.text_area(
                        "一番見てほしい点 ★",
                        value=_ii.get("focus_main", ""),
                        height=80,
                        placeholder="例: リリース時の肘の角度、助走のリズム など",
                    )
                    _ni_fc1, _ni_fc2, _ni_fc3 = st.columns(3)
                    with _ni_fc1:
                        _ni_f_approach  = st.checkbox("助走",     value=bool(_ii.get("focus_approach", False)),  key=f"ni_approach_{selected_id}")
                        _ni_f_crossstep = st.checkbox("クロスステップ", value=bool(_ii.get("focus_crossstep", False)), key=f"ni_cs_{selected_id}")
                    with _ni_fc2:
                        _ni_f_block   = st.checkbox("ブロック",   value=bool(_ii.get("focus_block", False)),   key=f"ni_block_{selected_id}")
                        _ni_f_release = st.checkbox("リリース",   value=bool(_ii.get("focus_release", False)), key=f"ni_release_{selected_id}")
                    with _ni_fc3:
                        _ni_f_upper = st.checkbox("上半身", value=bool(_ii.get("focus_upper_body", False)), key=f"ni_upper_{selected_id}")
                        _ni_f_lower = st.checkbox("下半身", value=bool(_ii.get("focus_lower_body", False)), key=f"ni_lower_{selected_id}")
                    _ni_focus_other = st.text_input(
                        "その他の相談内容",
                        value=_ii.get("focus_other", ""),
                        placeholder="自由記述",
                    )
                    _ni_prio = st.text_area(
                        "動画の優先順位・メモ",
                        value=_ii.get("video_priority_note", ""),
                        height=60,
                        placeholder="例: 1本目が一番いい試技、2本目はフォーム崩れ",
                    )
                    _ni_vmemo = st.text_area(
                        "動画に関するメモ",
                        value=_ii.get("video_memo", ""),
                        height=60,
                    )

                    st.markdown("##### 希望プラン")
                    try:
                        from src.plan_loader import load_plans as _load_plans_ii
                        _plans_ii = _load_plans_ii()
                    except Exception:
                        _plans_ii = {"free_preview": {"label": "無料プレビュー"}, "light": {"label": "ライト版"}, "data_sheet": {"label": "データシート版"}, "full_report": {"label": "フルレポート版"}, "comparison": {"label": "2動画比較版"}}
                    _plan_ii_opts = list(_plans_ii.keys()) + ["undecided"]
                    _plan_ii_labels = {k: v.get("label", k) for k, v in _plans_ii.items()}
                    _plan_ii_labels["undecided"] = "未定"
                    _ni_desired_plan_val = _ii.get("desired_plan", "free_preview")
                    _ni_desired_plan = st.selectbox(
                        "希望プラン ★",
                        options=_plan_ii_opts,
                        format_func=lambda x: _plan_ii_labels.get(x, x),
                        index=_plan_ii_opts.index(_ni_desired_plan_val) if _ni_desired_plan_val in _plan_ii_opts else 0,
                    )

                    st.markdown("##### 同意事項")
                    st.caption("以下の各項目にご同意いただいた場合はチェックをつけてください。")
                    _ni_con1 = st.checkbox(
                        "本解析は参考資料であり、絶対評価ではないことに同意します",
                        value=bool(_ii.get("consent_analysis_reference", False)),
                        key=f"con1_{selected_id}",
                    )
                    _ni_con2 = st.checkbox(
                        "本解析は医療診断・怪我の診断の代替ではないことに同意します",
                        value=bool(_ii.get("consent_not_medical", False)),
                        key=f"con2_{selected_id}",
                    )
                    _ni_con3 = st.checkbox(
                        "本解析は専門的な競技指導の代替ではないことに同意します",
                        value=bool(_ii.get("consent_not_coaching", False)),
                        key=f"con3_{selected_id}",
                    )
                    _ni_con4 = st.checkbox(
                        "動画の画質・撮影角度・服装・背景により解析精度が変わることに同意します",
                        value=bool(_ii.get("consent_accuracy_varies", False)),
                        key=f"con4_{selected_id}",
                    )
                    _ni_con5 = st.checkbox(
                        "解析・納品まで時間がかかる場合があることに同意します",
                        value=bool(_ii.get("consent_delivery_time", False)),
                        key=f"con5_{selected_id}",
                    )
                    _ni_con6 = st.checkbox(
                        "SNSへの掲載は別途許可制であることに同意します",
                        value=bool(_ii.get("consent_sns_separate", False)),
                        key=f"con6_{selected_id}",
                    )
                    _consent_count = sum([_ni_con1, _ni_con2, _ni_con3, _ni_con4, _ni_con5, _ni_con6])
                    if _consent_count < 6:
                        st.warning(f"⚠️ 同意事項: {_consent_count}/6 項目が未同意です。")
                    else:
                        st.success("✅ 全同意事項に同意済みです。")

                    _ni_save = st.form_submit_button("💾 受付情報を保存", type="primary")
                    if _ni_save:
                        update_intake_info(
                            selected_id,
                            name_or_nickname=_ni_name,
                            contact=_ni_contact,
                            age_group=_ni_age,
                            gender=_ni_gender,
                            athletic_career=_ni_career,
                            personal_best=_ni_pb,
                            dominant_arm=_ni_arm,
                            height_m=_ni_height if _ni_height > 0 else None,
                            affiliation_type=_ni_aff,
                            filming_date=_ni_filming_date,
                            filming_context=_ni_ctx,
                            filming_angle=_ni_angle,
                            video_type=_ni_vtype,
                            is_slow_motion=_ni_slow,
                            video_count=int(_ni_vcount),
                            video_priority_note=_ni_prio,
                            video_memo=_ni_vmemo,
                            focus_main=_ni_focus_main,
                            focus_approach=_ni_f_approach,
                            focus_crossstep=_ni_f_crossstep,
                            focus_block=_ni_f_block,
                            focus_release=_ni_f_release,
                            focus_upper_body=_ni_f_upper,
                            focus_lower_body=_ni_f_lower,
                            focus_other=_ni_focus_other,
                            desired_plan=_ni_desired_plan,
                            consent_analysis_reference=_ni_con1,
                            consent_not_medical=_ni_con2,
                            consent_not_coaching=_ni_con3,
                            consent_accuracy_varies=_ni_con4,
                            consent_delivery_time=_ni_con5,
                            consent_sns_separate=_ni_con6,
                        )
                        # 顧客情報との同期（利き腕・身長・競技歴）
                        update_customer_info(
                            selected_id,
                            dominant_arm=_ni_arm,
                            dominant_hand=_ni_arm,
                            height_m=_ni_height if _ni_height > 0 else None,
                            athletic_career=_ni_career,
                        )
                        st.success("✅ 受付情報を保存しました。")
                        st.rerun()
                st.caption(
                    f"updated_at: {_ii.get('updated_at', '—')}  ·  "
                    f"★ = 解析・納品に特に重要な項目"
                )

            # ══════════════════════════════════════════════════════════════════
            # I. 解析ログ（job_log.txt も含む）
            # ══════════════════════════════════════════════════════════════════
            _is_failed = job.get("status") == "failed"
            with st.expander(
                "🗒️ I. 解析ログ",
                expanded=_is_failed,   # 失敗時は自動展開
            ):
                _logs_dir = _job_dir / "logs"

                # ─ 操作ログ (job_log.txt) ────────────────────────────────────
                with st.expander("📋 操作ログ (job_log.txt)", expanded=False):
                    try:
                        from src.job_logger import read_job_log
                        _jlogs = read_job_log(selected_id)
                        if _jlogs:
                            import pandas as _pd_jl
                            st.dataframe(_pd_jl.DataFrame(_jlogs[::-1]), use_container_width=True, hide_index=True)
                        else:
                            st.caption("操作ログがまだありません。")
                    except Exception as _jle:
                        st.caption(f"操作ログの読み込みに失敗: {_jle}")

                if _is_failed:
                    st.error("❌ 解析に失敗しています。以下の点を確認してください。")
                    st.markdown("""
- ❑ **動画ファイルが壊れていないか** — VLC 等で再生確認してください
- ❑ **mp4形式か** — `.mp4` 以外の形式（mov, avi）は現状非対応です
- ❑ **MediaPipeがインストールされているか** — `pip install mediapipe` でインストール
- ❑ **Pythonバージョンが対応しているか** — Python 3.10—3.12 準拠
- ❑ **出力フォルダへの書き込み権限があるか** — `jobs/` フォルダのアクセス権を確認
""")
                    st.divider()

                # ─ returncode ────────────────────────────────────────────────────────────
                _rc = job.get("returncode")
                if _rc is not None:
                    _rc_color = "🟢" if _rc == 0 else "🔴"
                    st.caption(f"{_rc_color} returncode: `{_rc}`")

                if not _logs_dir.exists():
                    st.info("ログファイルがありません。このジョブはログ機能追加前に実行されたものです。")
                else:
                    # ─ command.txt ───────────────────────────────────────────────────────
                    _cmd_f = _logs_dir / "command.txt"
                    with st.expander("🖥️ 実行コマンド", expanded=False):
                        if _cmd_f.exists():
                            st.code(
                                _cmd_f.read_text(encoding="utf-8"),
                                language="bash",
                            )
                        else:
                            st.caption("command.txt がありません")

                    # ─ stderr.txt ──────────────────────────────────────────────────────
                    _err_f = _logs_dir / "stderr.txt"
                    with st.expander("🚨 stderr（エラー出力）", expanded=_is_failed):
                        if _err_f.exists():
                            _err_text = _err_f.read_text(encoding="utf-8", errors="replace")
                            if _err_text.strip():
                                st.code(_err_text, language="text")
                            else:
                                st.caption("（出力なし）")
                        else:
                            st.caption("stderr.txt がありません")

                    # ─ stdout.txt ────────────────────────────────═══════════════════
                    _out_f = _logs_dir / "stdout.txt"
                    with st.expander("📜 stdout（標準出力）", expanded=False):
                        if _out_f.exists():
                            _out_text = _out_f.read_text(encoding="utf-8", errors="replace")
                            if _out_text.strip():
                                st.code(_out_text, language="text")
                            else:
                                st.caption("（出力なし）")
                        else:
                            st.caption("stdout.txt がありません")

            # ══════════════════════════════════════════════════════════════════
            # G. Customer Info（顧客情報）
            # ══════════════════════════════════════════════════════════════════
            with st.expander("👤 G. 顧客情報 / Customer Info", expanded=True):
                try:
                    _ci = get_customer_info(selected_id)
                except Exception as _ci_err:
                    st.warning(f"⚠️ customer_info.json の読み込みに失敗しました: {_ci_err}")
                    _ci = {}
                with st.form(key=f"ci_form_{selected_id}"):
                    st.markdown("##### 基本情報")
                    _ci_c1, _ci_c2, _ci_c3 = st.columns(3)
                    with _ci_c1:
                        _ci_name = st.text_input("顧客名", value=_ci.get("customer_name", ""))
                        _ci_nick = st.text_input("ニックネーム", value=_ci.get("nickname", ""), help="SNS等で使う名前")
                        _ci_ig = st.text_input("Instagram ID", value=_ci.get("instagram_id", ""))
                        _ci_event = st.text_input("種目", value=_ci.get("event", "javelin"))
                    with _ci_c2:
                        _arm_opts = ["right", "left", "unknown"]
                        _arm_labels = {"right": "右 (right)", "left": "左 (left)", "unknown": "不明 (unknown)"}
                        _ci_arm_val = _ci.get("dominant_arm") or _ci.get("dominant_hand", "unknown")
                        _ci_arm = st.selectbox(
                            "利き腕",
                            options=_arm_opts,
                            format_func=lambda x: _arm_labels[x],
                            index=_arm_opts.index(_ci_arm_val if _ci_arm_val in _arm_opts else "unknown"),
                        )
                        _ci_height = st.number_input(
                            "身長 (m)",
                            min_value=0.0, max_value=2.5,
                            value=float(_ci.get("height_m") or 0.0),
                            step=0.01, format="%.2f",
                            help="0.00 は未設定扱いです",
                        )
                        _ci_career = st.text_input("競技歴", value=_ci.get("athletic_career", ""), placeholder="例: やり投げ3年目")
                        _angle_opts = ["side", "back", "front", "diagonal", "unknown"]
                        _angle_labels = {"side": "側面", "back": "後方", "front": "正面", "diagonal": "斜め", "unknown": "不明"}
                        _ci_angle_val = _ci.get("filming_angle") or _ci.get("camera_angle", "unknown")
                        _ci_angle = st.selectbox(
                            "撮影方向",
                            options=_angle_opts,
                            format_func=lambda x: _angle_labels[x],
                            index=_angle_opts.index(_ci_angle_val if _ci_angle_val in _angle_opts else "unknown"),
                        )
                    with _ci_c3:
                        _plan_opts = list(PLAN_LABELS.keys())
                        _ci_plan_val = _ci.get("plan", "free_preview")
                        _ci_plan = st.selectbox(
                            "プラン",
                            options=_plan_opts,
                            format_func=lambda x: PLAN_LABELS.get(x, x),
                            index=_plan_opts.index(_ci_plan_val if _ci_plan_val in _plan_opts else "free_preview"),
                        )
                        _pstatus_opts = ["unpaid", "paid", "free"]
                        _pstatus_labels = {"unpaid": "未払い", "paid": "支払済み", "free": "無料"}
                        _ci_pstatus_val = _ci.get("payment_status", "unpaid")
                        _ci_pstatus = st.selectbox(
                            "支払いステータス",
                            options=_pstatus_opts,
                            format_func=lambda x: _pstatus_labels[x],
                            index=_pstatus_opts.index(_ci_pstatus_val if _ci_pstatus_val in _pstatus_opts else "unpaid"),
                        )
                        _ci_received_at = st.text_input("受付日", value=_ci.get("received_at", ""), placeholder="2026-05-10")
                        _ci_delivery_sched = st.text_input("納品予定メモ", value=_ci.get("delivery_scheduled_note", ""), placeholder="例: 今週末")
                        _ci_delivered_at = st.text_input("納品済み日時", value=_ci.get("delivered_at", ""), placeholder="ISO8601 or 空欄")

                    st.markdown("##### SNS掲載許可")
                    _sns_col1, _sns_col2 = st.columns([2, 3])
                    with _sns_col1:
                        _sns_opts = ["unknown", "allowed", "anonymous", "denied"]
                        _sns_labels = {
                            "unknown":   "⚠️ 未確認",
                            "allowed":   "✅ 許可あり",
                            "anonymous": "👤 匿名なら許可",
                            "denied":    "🚫 不可",
                        }
                        _ci_social_val = _ci.get("permission_for_social_post", "unknown")
                        # 旧値の正規化
                        if _ci_social_val == "yes":
                            _ci_social_val = "allowed"
                        elif _ci_social_val == "no":
                            _ci_social_val = "denied"
                        _ci_social = st.radio(
                            "SNS掲載許可ステータス",
                            options=_sns_opts,
                            format_func=lambda x: _sns_labels[x],
                            index=_sns_opts.index(_ci_social_val if _ci_social_val in _sns_opts else "unknown"),
                            horizontal=True,
                        )
                    with _sns_col2:
                        _ci_anon_note = st.text_area(
                            "匿名化メモ",
                            value=_ci.get("anonymization_note", ""),
                            height=100,
                            placeholder="例: 名前を出さない / 学校名を出さない / 顔を隠す",
                            help="SNS掲載時の匿名化条件を記載してください",
                        )

                    st.markdown("##### 納品ステータス・メモ")
                    _dstatus_opts = ["not_started", "analyzed", "preview_delivered", "paid_delivered", "completed"]
                    _dstatus_labels = {
                        "not_started":       "未着手",
                        "analyzed":          "解析済み",
                        "preview_delivered": "プレビュー納品済み",
                        "paid_delivered":    "有料納品済み",
                        "completed":         "完了",
                    }
                    _ci_dstatus = st.selectbox(
                        "納品ステータス",
                        options=_dstatus_opts,
                        format_func=lambda x: _dstatus_labels[x],
                        index=_dstatus_opts.index(
                            _ci.get("delivery_status", "not_started")
                            if _ci.get("delivery_status") in _dstatus_opts else "not_started"
                        ),
                    )
                    _note_c1, _note_c2, _note_c3 = st.columns(3)
                    with _note_c1:
                        _ci_notes = st.text_area(
                            "相談内容メモ (notes)",
                            value=_ci.get("notes", "") or _ci.get("request_note", ""),
                            height=100,
                        )
                    with _note_c2:
                        _ci_admin_memo = st.text_area(
                            "管理者メモ (admin_memo)",
                            value=_ci.get("admin_memo", ""),
                            height=100,
                            help="運営内部のメモ（顧客には見えません）",
                        )
                    with _note_c3:
                        _ci_coach = st.text_area(
                            "💬 コーチコメント (PDFに掲載)",
                            value=_ci.get("coach_comment", ""),
                            height=100,
                        )
                    _ci_save = st.form_submit_button("💾 顧客情報を保存", type="primary")
                    if _ci_save:
                        update_customer_info(
                            selected_id,
                            customer_name=_ci_name,
                            nickname=_ci_nick,
                            instagram_id=_ci_ig,
                            event=_ci_event,
                            dominant_arm=_ci_arm,
                            dominant_hand=_ci_arm,
                            height_m=_ci_height if _ci_height > 0 else None,
                            athletic_career=_ci_career,
                            filming_angle=_ci_angle,
                            camera_angle=_ci_angle,
                            permission_for_social_post=_ci_social,
                            anonymization_note=_ci_anon_note,
                            plan=_ci_plan,
                            payment_status=_ci_pstatus,
                            received_at=_ci_received_at,
                            delivery_scheduled_note=_ci_delivery_sched,
                            delivered_at=_ci_delivered_at,
                            delivery_status=_ci_dstatus,
                            notes=_ci_notes,
                            request_note=_ci_notes,
                            admin_memo=_ci_admin_memo,
                            coach_comment=_ci_coach,
                        )
                        st.success("保存しました。")
                        st.rerun()
                st.caption(
                    f"created_at: {_ci.get('created_at', '—')}  ·  "
                    f"updated_at: {_ci.get('updated_at', '—')}"
                )

            # ══════════════════════════════════════════════════════════════════
            # B. Free Preview Outputs
            # ══════════════════════════════════════════════════════════════════
            with st.expander("🆓 B. Free Preview Outputs", expanded=True):
                st.caption("無料プレビュー用の解析動画・代表フレーム画像")
                _prev_mp4s  = sorted(_cls["preview_mp4s"], key=lambda p: p.name)
                _frame_imgs = sorted(_cls["frame_files"],  key=lambda p: p.name)

                if not _prev_mp4s and not _frame_imgs:
                    st.info("Not generated yet.")
                else:
                    if _prev_mp4s:
                        st.markdown("**🎬 解析動画**")
                        for _vp in _prev_mp4s:
                            if not _vp.exists() or _vp.stat().st_size == 0:
                                st.caption(f"⚠ {_vp.name} — Not found")
                                continue
                            st.markdown(f"**{_vp.name}**")
                            _vbytes = _read_video_bytes(_vp)
                            if _vbytes:
                                st.download_button(
                                    label=f"⬇ {_vp.name}", data=_vbytes,
                                    file_name=_vp.name, mime="video/mp4",
                                    key=f"dl_prev_{_vp.name}_{job['job_id']}",
                                )
                                st.video(_vbytes)

                    if _frame_imgs:
                        st.markdown("**🖼️ 代表フレーム画像**")
                        _fcols = st.columns(min(len(_frame_imgs), 5))
                        for _col, _fp in zip(_fcols, _frame_imgs):
                            if not _fp.exists():
                                continue
                            with _col:
                                st.image(str(_fp), caption=_fp.name,
                                         use_container_width=True)
                                try:
                                    st.download_button(
                                        label=f"⬇ {_fp.name}",
                                        data=_read_file_cached(str(_fp), _fp.stat().st_mtime_ns),
                                        file_name=_fp.name, mime="image/jpeg",
                                        key=f"dl_fr_{_fp.name}_{job['job_id']}",
                                    )
                                except Exception:
                                    pass

            # ══════════════════════════════════════════════════════════════════
            # C. Data Sheet Outputs
            # ══════════════════════════════════════════════════════════════════
            with st.expander("📊 C. Data Sheet Outputs", expanded=True):
                st.caption("CSVデータシート・解析グラフ画像")
                _csv_fps   = sorted(_cls["csv_files"],   key=lambda p: p.name)
                _graph_fps = sorted(_cls["graph_files"],  key=lambda p: p.name)

                if not _csv_fps and not _graph_fps:
                    st.info("Not generated yet.")
                else:
                    if _csv_fps:
                        st.markdown("**📄 CSVデータシート (Raw Data / 上級者・研究者向け)**")
                        st.caption("⚠ このCSVは生の姿勢推定データです。アスリート向けにはセクション K の athlete_data_sheet.pdf をご利用ください。")
                        for _cp in _csv_fps:
                            if not _cp.exists():
                                st.caption(f"⚠ {_cp.name} — Not found")
                                continue
                            st.markdown(f"**{_cp.name}**")
                            try:
                                _df = pd.read_csv(_cp, encoding="utf-8", nrows=5)
                                st.dataframe(_df, use_container_width=True)
                                st.download_button(
                                    label=f"⬇ {_cp.name}（全フレーム）",
                                    data=_read_file_cached(str(_cp), _cp.stat().st_mtime_ns),
                                    file_name=_cp.name,
                                    mime="text/csv",
                                    key=f"dl_csv_{_cp.name}_{job['job_id']}",
                                )
                            except Exception as _e:
                                st.warning(f"{_cp.name} のプレビューに失敗: {_e}")

                    if _graph_fps:
                        st.markdown("**📈 解析グラフ画像**")
                        _gcols = st.columns(min(len(_graph_fps), 3))
                        for _col, _gp in zip(_gcols, _graph_fps):
                            if not _gp.exists():
                                continue
                            with _col:
                                st.image(str(_gp),
                                         caption=_gp.stem.replace("_", " ").title(),
                                         use_container_width=True)
                                try:
                                    st.download_button(
                                        label=f"⬇ {_gp.name}",
                                        data=_read_file_cached(str(_gp), _gp.stat().st_mtime_ns),
                                        file_name=_gp.name, mime="image/png",
                                        key=f"dl_gr_{_gp.name}_{job['job_id']}",
                                    )
                                except Exception:
                                    pass

            # ══════════════════════════════════════════════════════════════════
            # D. PDF Report
            # ══════════════════════════════════════════════════════════════════
            with st.expander("📄 D. PDF Report", expanded=True):
                _pdf_p = _cls["pdf_path"]
                _dc1, _dc2 = st.columns([3, 2])
                with _dc1:
                    if _pdf_p and _pdf_p.exists():
                        try:
                            _mtime = datetime.fromtimestamp(
                                _pdf_p.stat().st_mtime
                            ).strftime("%Y-%m-%d %H:%M:%S")
                            _size_kb = _pdf_p.stat().st_size // 1024
                            st.download_button(
                                label="⬇ report.pdf をダウンロード",
                                data=_read_file_cached(str(_pdf_p), _pdf_p.stat().st_mtime_ns),
                                file_name="report.pdf",
                                mime="application/pdf",
                                key=f"dl_pdf_{job['job_id']}",
                            )
                            st.caption(f"生成日時: {_mtime}  /  {_size_kb} KB")
                        except Exception as _e:
                            st.warning(f"PDF ファイルを読み込めませんでした: {_e}")
                    else:
                        st.info("Not generated yet.")
                with _dc2:
                    _gen_button(
                        "PDF を再生成",
                        f"gen_pdf_{job['job_id']}",
                        "src.pdf_report_generator",
                        "generate_pdf_report_for_job",
                        _job_dir,
                        "PDF を生成中...",
                    )

            # ══════════════════════════════════════════════════════════════════
            # D2. 解析動画 説明書 PDF (video_instruction.pdf)
            # ══════════════════════════════════════════════════════════════════
            with st.expander("📖 D2. 解析動画 説明書 (video_instruction.pdf)", expanded=True):
                _instr_p = _cls.get("instr_pdf_path")
                _d2c1, _d2c2 = st.columns([3, 2])
                with _d2c1:
                    if _instr_p and _instr_p.exists():
                        try:
                            _instr_mtime = datetime.fromtimestamp(
                                _instr_p.stat().st_mtime
                            ).strftime("%Y-%m-%d %H:%M:%S")
                            _instr_kb = _instr_p.stat().st_size // 1024
                            st.download_button(
                                label="⬇ video_instruction.pdf をダウンロード",
                                data=_read_file_cached(str(_instr_p), _instr_p.stat().st_mtime_ns),
                                file_name="video_instruction.pdf",
                                mime="application/pdf",
                                key=f"dl_instr_pdf_{job['job_id']}",
                            )
                            st.caption(f"生成日時: {_instr_mtime}  /  {_instr_kb} KB")
                        except Exception as _e:
                            st.warning(f"説明書PDFファイルを読み込めませんでした: {_e}")
                    else:
                        st.info("Not generated yet.")
                with _d2c2:
                    _gen_button(
                        "説明書PDFを生成・再生成",
                        f"gen_instr_pdf_{job['job_id']}",
                        "src.video_instruction_pdf_generator",
                        "generate_video_instruction_pdf_for_job",
                        _job_dir,
                        "説明書PDF を生成中...",
                    )

            # ══════════════════════════════════════════════════════════════════
            # K. User-friendly Reports（アスリート向け成果物）
            # ══════════════════════════════════════════════════════════════════
            with st.expander("📋 K. User-friendly Reports（アスリート向け）", expanded=True):
                st.caption("選手・コーチが直接使える PDF 成果物です。")

                # ── PDFを一括再生成ボタン ──────────────────────────────────
                _bulk_pdf_state = f"_bulk_pdf_{selected_id}"
                if _bulk_pdf_state in st.session_state:
                    _bpr = st.session_state.pop(_bulk_pdf_state)
                    if _bpr["ok"]:
                        st.success(_bpr["msg"])
                    else:
                        st.error(_bpr["msg"])
                        if _bpr.get("tb"):
                            with st.expander("エラー詳細", expanded=False):
                                st.code(_bpr["tb"], language="python")
                if st.button("🔄 PDFを一括再生成（全5種）", key=f"bulk_pdf_{selected_id}", use_container_width=False):
                    import traceback as _tb_bulk
                    _bulk_ok = []
                    _bulk_err = []
                    _bulk_gens = [
                        ("src.intro_pdf_generator",       "generate_intro_pdf_for_job"),
                        ("src.athlete_data_sheet_generator", "generate_athlete_data_sheet_for_job"),
                        ("src.key_frame_sheet_generator", "generate_key_frame_sheet_for_job"),
                        ("src.graph_pack_generator",       "generate_graph_pack_for_job"),
                        ("src.coach_review_sheet_generator","generate_coach_review_sheet_for_job"),
                    ]
                    with st.spinner("全PDFを生成中..."):
                        for _bmod, _bfn in _bulk_gens:
                            try:
                                import importlib as _imp
                                _m = _imp.import_module(_bmod)
                                _r = getattr(_m, _bfn)(_job_dir)
                                _bulk_ok.append(_r.name)
                                from src.job_logger import log_pdf_generated
                                log_pdf_generated(selected_id, _r.name)
                            except Exception as _be:
                                _bulk_err.append(f"{_bfn}: {_be}")
                    if _bulk_err:
                        st.session_state[_bulk_pdf_state] = {
                            "ok": False,
                            "msg": f"❌ {len(_bulk_err)} 件失敗: " + " / ".join(_bulk_err),
                            "tb": "\n".join(_bulk_err),
                        }
                    else:
                        st.session_state[_bulk_pdf_state] = {
                            "ok": True,
                            "msg": f"✅ {len(_bulk_ok)} 件生成完了: " + ", ".join(_bulk_ok),
                        }
                    st.rerun()

                st.divider()

                _ufr_items = [
                    (
                        None,
                        "00_最初に読んでください.pdf",
                        "📋 はじめにお読みください",
                        "ZIPの先頭に入る案内PDF（ファイル構成・見る順番・説明）",
                        "gen_intro_pdf",
                        "src.intro_pdf_generator",
                        "generate_intro_pdf_for_job",
                    ),
                    (
                        "athlete_pdf_path",
                        "athlete_data_sheet.pdf",
                        "🏃 アスリートデータシート（選手向けサマリー）",
                        "主要指標をまとめた選手向けサマリーPDF",
                        "gen_athlete_pdf",
                        "src.athlete_data_sheet_generator",
                        "generate_athlete_data_sheet_for_job",
                    ),
                    (
                        "key_frame_pdf_path",
                        "key_frame_sheet.pdf",
                        "🖼 代表フレームシート",
                        "フェーズ別代表フレーム一覧PDF",
                        "gen_key_frame_pdf",
                        "src.key_frame_sheet_generator",
                        "generate_key_frame_sheet_for_job",
                    ),
                    (
                        "graph_pack_pdf_path",
                        "graph_pack.pdf",
                        "📈 グラフ解説PDF",
                        "解析グラフを解説付きでまとめたPDF",
                        "gen_graph_pack_pdf",
                        "src.graph_pack_generator",
                        "generate_graph_pack_for_job",
                    ),
                    (
                        "coach_review_pdf_path",
                        "coach_review_sheet.pdf",
                        "📝 コーチ向けレビューシート",
                        "フェーズ別チェックリスト＆記入欄PDF（指導者向け）",
                        "gen_coach_review_pdf",
                        "src.coach_review_sheet_generator",
                        "generate_coach_review_sheet_for_job",
                    ),
                ]

                for (_cls_key, _fname, _label, _caption, _btn_key,
                     _mod_name, _fn_name) in _ufr_items:
                    st.markdown(f"**{_label}**")
                    st.caption(_caption)
                    # cls_key が None の場合は直接 report/ 以下を参照
                    _ufr_p = (_job_dir / "report" / _fname) if _cls_key is None else _cls.get(_cls_key)
                    _k1, _k2 = st.columns([3, 2])
                    with _k1:
                        if _ufr_p and Path(_ufr_p).exists():
                            try:
                                _ufr_p = Path(_ufr_p)
                                _ufr_mt = datetime.fromtimestamp(
                                    _ufr_p.stat().st_mtime
                                ).strftime("%Y-%m-%d %H:%M:%S")
                                _ufr_kb = _ufr_p.stat().st_size // 1024
                                st.download_button(
                                    label=f"⬇ {_fname} をダウンロード",
                                    data=_read_file_cached(str(_ufr_p), _ufr_p.stat().st_mtime_ns),
                                    file_name=_fname,
                                    mime="application/pdf",
                                    key=f"dl_{_btn_key}_{job['job_id']}",
                                )
                                st.caption(f"生成日時: {_ufr_mt}  /  {_ufr_kb} KB")
                            except Exception as _e:
                                st.warning(f"{_fname} を読み込めませんでした: {_e}")
                        else:
                            st.info("未生成 / Not generated yet.")
                    with _k2:
                        _gen_button(
                            "生成・再生成",
                            f"btn_{_btn_key}_{job['job_id']}",
                            _mod_name,
                            _fn_name,
                            _job_dir,
                            f"{_fname} を生成中...",
                        )
                    st.divider()

            # ══════════════════════════════════════════════════════════════════
            # E. Admin / Internal Files（管理者内部用）
            # ══════════════════════════════════════════════════════════════════
            with st.expander("🔒 E. 管理者内部用 (Admin/Internal Files)", expanded=False):
                st.caption("⚠️ この情報は管理者のみが参照してください。")

                # job.json
                _job_json_p = _job_dir / "job.json"
                if _job_json_p.exists():
                    st.markdown("**job.json**")
                    st.json(job)

                # 最新の *_report.json
                _out_dir = _job_dir / "output"
                if _out_dir.exists():
                    _rep_jsons = sorted(_out_dir.glob("*_report.json"))
                    if _rep_jsons:
                        _rj = _rep_jsons[-1]
                        st.markdown(f"**{_rj.name}**")
                        try:
                            st.json(json.loads(_rj.read_text(encoding="utf-8")))
                        except Exception:
                            st.warning(f"{_rj.name} の読み込みに失敗しました。")

                # その他の admin_files（*_report.json 以外）
                for _fp in _cls["admin_files"]:
                    if not _fp.exists():
                        continue
                    if _fp.name == "job.json" or _fp.name.endswith("_report.json"):
                        continue
                    st.markdown(f"**{_fp.name}**")
                    try:
                        st.download_button(
                            label=f"⬇ {_fp.name}",
                            data=_read_file_cached(str(_fp), _fp.stat().st_mtime_ns),
                            file_name=_fp.name,
                            key=f"dl_adm_{_fp.name}_{job['job_id']}",
                        )
                    except Exception:
                        pass

                # 未分類ファイル
                if _cls["other_files"]:
                    st.markdown("**その他のファイル**")
                    for _fp in _cls["other_files"]:
                        if not _fp.exists():
                            continue
                        try:
                            st.download_button(
                                label=f"⬇ {_fp.name}",
                                data=_read_file_cached(str(_fp), _fp.stat().st_mtime_ns),
                                file_name=_fp.name,
                                key=f"dl_oth_{_fp.name}_{job['job_id']}",
                            )
                        except Exception:
                            pass

                st.markdown("**ジョブディレクトリ**")
                st.code(str(_job_dir), language=None)

            # ══════════════════════════════════════════════════════════════════
            # J. 解析サマリー (analysis_summary.json)
            # ══════════════════════════════════════════════════════════════════
            _summary_path = _job_dir / "report" / "analysis_summary.json"
            with st.expander("📊 J. 解析サマリー", expanded=False):
                if not _summary_path.exists():
                    st.info("analysis_summary.json がまだ生成されていません。")
                    st.caption(
                        "解析完了後に自動生成されます。"
                        "手動で生成する場合は以下のボタンを押してください。"
                    )
                    if st.button(
                        "📊 解析サマリーを生成", key=f"gen_summary_{job['job_id']}",
                        use_container_width=False,
                    ):
                        with st.spinner("計算中..."):
                            import traceback as _tb_mod
                            _j_state_key = f"_gen_result_gen_summary_{job['job_id']}"
                            try:
                                from src.analysis_summary import generate_analysis_summary_for_job
                                _sp = generate_analysis_summary_for_job(_job_dir)
                                st.session_state[_j_state_key] = {"ok": True, "msg": f"✅ 生成完了: {_sp.name}"}
                            except Exception as _se:
                                st.session_state[_j_state_key] = {"ok": False, "msg": f"生成エラー: {_se}", "tb": _tb_mod.format_exc()}
                        st.rerun()
                else:
                    try:
                        import json as _json_mod
                        _summary = _json_mod.loads(
                            _summary_path.read_text(encoding="utf-8")
                        )
                    except Exception as _re:
                        st.error(f"読み込みエラー: {_re}")
                        _summary = {}

                    _s_status = _summary.get("status", "unknown")
                    if _s_status == "skipped":
                        st.warning(
                            f"⚠️ スキップ: {_summary.get('reason', '不明な理由')}"
                        )
                    else:
                        # ── 新形式 (video / pose_quality / key_metrics) の判定 ──
                        _is_new_fmt = "video" in _summary and "key_metrics" in _summary

                        if _is_new_fmt:
                            # ── 新形式メトリクス表示 ──────────────────────────
                            _vid   = _summary.get("video", {})
                            _km    = _summary.get("key_metrics", {})
                            _pq    = _summary.get("pose_quality", {})
                            _warns = _summary.get("warnings") or []

                            # 行1: ビデオ基本情報
                            _nc1, _nc2 = st.columns(2)
                            _nc1.metric(
                                "総フレーム数",
                                f"{_vid.get('frame_count', '—'):,}"
                                if isinstance(_vid.get('frame_count'), int) else "—",
                            )
                            _dur = _vid.get("duration_sec")
                            _nc2.metric(
                                "動画尺",
                                f"{_dur:.3f} 秒" if isinstance(_dur, (int, float)) else "—",
                            )

                            st.markdown("**Key Metrics — 右手首**")
                            _kc1, _kc2 = st.columns(2)
                            _mht = _km.get("right_wrist_max_height_time_sec")
                            _mhn = _km.get("right_wrist_max_height_norm")
                            _kc1.metric(
                                "最高到達時刻",
                                f"{_mht:.3f} 秒" if isinstance(_mht, (int, float)) else "—",
                            )
                            _kc2.metric(
                                "最高到達高さ (norm)",
                                f"{_mhn:.4f}" if isinstance(_mhn, (int, float)) else "—",
                                help="MediaPipe 正規化座標で 1 - y（1 = 画面上端）",
                            )

                            _tc_s = _km.get("torso_center_x_start")
                            _tc_e = _km.get("torso_center_x_end")
                            if _tc_s is not None or _tc_e is not None:
                                st.caption(
                                    f"胴体中心 X: 開始 `{_tc_s}`  →  終了 `{_tc_e}`"
                                    + (
                                        f"  （移動: `{round(_tc_e - _tc_s, 4)}`）"
                                        if _tc_s is not None and _tc_e is not None
                                        else ""
                                    )
                                )

                            st.markdown("**Pose Quality**")
                            _mr = _pq.get("right_wrist_missing_ratio")
                            _mr_pct = (
                                f"{_mr * 100:.1f}%"
                                if isinstance(_mr, (int, float))
                                else "—"
                            )
                            st.write(f"右手首 欠損率: **{_mr_pct}**")

                            _avg_vis: dict = _pq.get("average_visibility") or {}
                            if _avg_vis:
                                _vis_cols = [
                                    "right_shoulder", "right_elbow", "right_wrist",
                                    "left_shoulder",  "left_elbow",  "left_wrist",
                                ]
                                _vis_data = {
                                    k: (f"{v:.3f}" if isinstance(v, (int, float)) else "—")
                                    for k, v in _avg_vis.items()
                                    if k in _vis_cols
                                }
                                if _vis_data:
                                    import pandas as _pd_tmp
                                    st.dataframe(
                                        _pd_tmp.DataFrame(
                                            [_vis_data],
                                            index=["avg visibility"],
                                        ),
                                        use_container_width=True,
                                    )

                            if _warns:
                                with st.expander(
                                    f"⚠️ Warnings ({len(_warns)} 件)", expanded=False
                                ):
                                    for _w in _warns:
                                        st.write(f"- {_w}")

                        else:
                            # ── 旧形式メトリクスカード ─────────────────────────
                            _sc1, _sc2, _sc3, _sc4 = st.columns(4)
                            _sc1.metric(
                                "総フレーム数",
                                f"{_summary.get('total_frames', '—'):,}" if _summary.get('total_frames') is not None else "—",
                            )
                            _sc2.metric(
                                "動画尺",
                                f"{_summary.get('duration_sec', '—')} 秒" if _summary.get('duration_sec') is not None else "—",
                            )
                            _sc3.metric(
                                "推定 FPS",
                                f"{_summary.get('fps_estimated', '—')}" if _summary.get('fps_estimated') is not None else "—",
                            )
                            _sc4.metric(
                                "利き腕",
                                str(_summary.get('dominant_hand', '—')).capitalize(),
                            )

                            st.markdown("**手首高さ（投げ腕）**")
                            _wc1, _wc2, _wc3 = st.columns(3)
                            _wc1.metric("最小", f"{_summary.get('wrist_height_min', '—')}")
                            _wc2.metric("最大", f"{_summary.get('wrist_height_max', '—')}")
                            _wc3.metric("可動域", f"{_summary.get('wrist_height_range', '—')}")

                            _wp_frame = _summary.get('wrist_height_peak_frame')
                            _wp_time  = _summary.get('wrist_height_peak_time_sec')
                            if _wp_frame is not None:
                                st.caption(
                                    f"ピーク: フレーム {_wp_frame}"
                                    + (f"  /  {_wp_time} 秒" if _wp_time is not None else "")
                                )

                            st.markdown("**重心移動（X 軸, 0=左端 / 1=右端）**")
                            _gc1, _gc2 = st.columns(2)
                            with _gc1:
                                st.caption("肩中心")
                                _sc_s = _summary.get('shoulder_center_x_start')
                                _sc_e = _summary.get('shoulder_center_x_end')
                                st.write(
                                    f"開始: `{_sc_s}`  →  終了: `{_sc_e}`"
                                    + (f"  （移動: `{round(_sc_e - _sc_s, 4)}`）"
                                       if _sc_s is not None and _sc_e is not None else "")
                                )
                            with _gc2:
                                st.caption("腰中心")
                                _hc_s = _summary.get('hip_center_x_start')
                                _hc_e = _summary.get('hip_center_x_end')
                                st.write(
                                    f"開始: `{_hc_s}`  →  終了: `{_hc_e}`"
                                    + (f"  （移動: `{round(_hc_e - _hc_s, 4)}`）"
                                       if _hc_s is not None and _hc_e is not None else "")
                                )

                    # ── 生成ボタン（再生成） ────────────────────────────────
                    st.divider()
                    _sj_left, _sj_right = st.columns([2, 5])
                    with _sj_left:
                        _sj_state_key = f"_gen_result_regen_summary_{job['job_id']}"
                        if _sj_state_key in st.session_state:
                            _sjr = st.session_state.pop(_sj_state_key)
                            if _sjr["ok"]:
                                st.success(_sjr["msg"])
                            else:
                                st.error(_sjr["msg"])
                                if _sjr.get("tb"):
                                    st.code(_sjr["tb"], language="python")
                        if st.button(
                            "🔄 サマリーを再生成",
                            key=f"regen_summary_{job['job_id']}",
                            use_container_width=True,
                        ):
                            with st.spinner("再計算中..."):
                                import traceback as _tb_mod
                                try:
                                    from src.analysis_summary import generate_analysis_summary_for_job
                                    generate_analysis_summary_for_job(_job_dir)
                                    st.session_state[_sj_state_key] = {"ok": True, "msg": "✅ 再生成完了"}
                                except Exception as _se:
                                    st.session_state[_sj_state_key] = {"ok": False, "msg": f"エラー: {_se}", "tb": _tb_mod.format_exc()}
                            st.rerun()
                    with _sj_right:
                        st.caption(f"生成日時: {_summary.get('generated_at', '—')}")

                    # ── 生の JSON 表示 ──────────────────────────────────────
                    with st.expander("🗂️ Raw JSON", expanded=False):
                        st.json(_summary)

            # ══════════════════════════════════════════════════════════════════
            # F. 納品用ZIPパッケージ
            # ══════════════════════════════════════════════════════════════════
            with st.expander("📦 F. 納品用ZIPパッケージ", expanded=False):
                _deliv_dir = _job_dir / "deliverables"

                # ── ZIP全生成ボタン ──────────────────────────────────────────
                _fz_left, _fz_right = st.columns([2, 5])
                with _fz_left:
                    _zip_state_key = f"_gen_result_gen_zip_{job['job_id']}"
                    if _zip_state_key in st.session_state:
                        _zr = st.session_state.pop(_zip_state_key)
                        if _zr["ok"]:
                            st.success(_zr["msg"])
                        else:
                            st.error(_zr["msg"])
                            if _zr.get("tb"):
                                with st.expander("エラー詳細", expanded=False):
                                    st.code(_zr["tb"], language="python")
                    if st.button("🗜️ 納品ZIPを一括再生成", key=f"gen_zip_{job['job_id']}",
                                 type="primary", use_container_width=True):
                        with st.spinner("ZIP を生成中..."):
                            import traceback as _tb_mod
                            try:
                                from src.deliverable_packager import (
                                    create_deliverable_packages_for_job,
                                )
                                _zips = create_deliverable_packages_for_job(_job_dir)
                                from src.job_logger import log_zip_generated
                                for _zp_generated in _zips:
                                    log_zip_generated(selected_id, Path(_zp_generated).name)
                                st.session_state[_zip_state_key] = {
                                    "ok": True,
                                    "msg": f"✅ 生成完了: {len(_zips)} 件",
                                }
                            except Exception as _ze:
                                st.session_state[_zip_state_key] = {
                                    "ok": False,
                                    "msg": f"ZIP 生成エラー: {_ze}",
                                    "tb": _tb_mod.format_exc(),
                                }
                        st.rerun()
                with _fz_right:
                    st.caption(
                        "解析完了後に上記ボタンを押すと3種類のZIPが一括生成されます。"
                        "生成済みのZIPは各カードのダウンロードボタンから取得できます。"
                    )
                    st.caption(
                        "**ZIPフォルダ構成:** `00_最初に読んでください.pdf` → "
                        "`01_解析動画/` → `02_選手向けサマリー/` → `03_コーチ向け/` → "
                        "`04_代表フレーム画像/` → `05_研究・開発用データ/` → `99_注意事項/`"
                    )

                st.markdown("---")

                # ── カード定義 ──────────────────────────────────────────────
                _zip_cards = [
                    {
                        "filename":  "free_preview.zip",
                        "icon":      "🆓",
                        "tier":      "無料プレビュー",
                        "subtitle":  "Free Preview Package",
                        "purpose":   "SNSでシェアする前の確認・無料体験として納品",
                        "contents":  [
                            "📋 00_最初に読んでください.pdf",
                            "📹 01_解析動画/（プレビュー動画）",
                            "📖 解析動画の見方.pdf",
                            "🖼️ 02_代表フレーム画像/（先頭3枚）",
                            "⚠️ 99_注意事項/注意事項.txt",
                        ],
                        "badge_color": "#2E7D32",   # 緑
                        "badge_text":  "FREE",
                    },
                    {
                        "filename":  "data_sheet_package.zip",
                        "icon":      "📊",
                        "tier":      "有料データシート",
                        "subtitle":  "Paid Data Sheet Package",
                        "purpose":   "数値データ・グラフを活用したい競技者・コーチ向け",
                        "contents":  [
                            "📋 00_最初に読んでください.pdf",
                            "📹 01_解析動画/（全動画）",
                            "📖 解析動画の見方.pdf",
                            "🏃 02_選手向けサマリー/選手向けサマリー.pdf",
                            "🖼️ 02_選手向けサマリー/代表フレームシート.pdf",
                            "📈 02_選手向けサマリー/グラフ解説.pdf",
                            "🖼️ 03_代表フレーム画像/（全枚）",
                            "📄 04_研究・開発用データ/pose_landmarks.csv",
                            "⚠️ 99_注意事項/注意事項.txt",
                        ],
                        "badge_color": "#1565C0",   # 青
                        "badge_text":  "PAID",
                    },
                    {
                        "filename":  "full_report_package.zip",
                        "icon":      "📦",
                        "tier":      "有料フルレポート",
                        "subtitle":  "Paid Full Report Package",
                        "purpose":   "PDF・動画・データを完全セットで納品したい場合",
                        "contents":  [
                            "📋 00_最初に読んでください.pdf",
                            "📝 report.pdf（詳細解析レポート）",
                            "📹 01_解析動画/（全動画）",
                            "📖 解析動画の見方.pdf",
                            "🏃 02_選手向けサマリー/選手向けサマリー.pdf",
                            "🖼️ 02_選手向けサマリー/代表フレームシート.pdf",
                            "📈 02_選手向けサマリー/グラフ解説.pdf",
                            "📝 03_コーチ向け/コーチ向けレビューシート.pdf",
                            "🖼️ 04_代表フレーム画像/（全枚）",
                            "📄 05_研究・開発用データ/（CSV・JSON・グラフ画像）",
                            "⚠️ 99_注意事項/注意事項.txt",
                        ],
                        "badge_color": "#E65100",   # オレンジ
                        "badge_text":  "PAID",
                    },
                ]

                _card_cols = st.columns(3, gap="medium")
                for _card, _col in zip(_zip_cards, _card_cols):
                    _zp = _deliv_dir / _card["filename"]
                    with _col:
                        # ヘッダー行
                        st.markdown(
                            f"<span style='background:{_card['badge_color']};"
                            f"color:white;padding:2px 8px;border-radius:4px;"
                            f"font-size:11px;font-weight:bold'>{_card['badge_text']}</span>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f"#### {_card['icon']} {_card['tier']}"
                        )
                        st.caption(_card["subtitle"])
                        st.divider()

                        # 推奨用途
                        st.markdown("**📌 推奨用途**")
                        st.caption(_card["purpose"])

                        # 含まれる成果物
                        st.markdown("**📂 含まれる成果物**")
                        for _item in _card["contents"]:
                            st.caption(_item)

                        st.divider()

                        # ステータス & ダウンロード
                        if _zp.exists():
                            try:
                                _zstat = _zp.stat()
                                _zk    = _zstat.st_size // 1024
                                _zm    = datetime.fromtimestamp(
                                    _zstat.st_mtime
                                ).strftime("%Y-%m-%d %H:%M")
                                st.success("✅ 生成済み")
                                st.caption(f"`{_card['filename']}`")
                                st.caption(f"{_zk:,} KB  ·  生成: {_zm}")
                                # 大容量 ZIP は open() で渡す（キャッシュを介さない）
                                st.download_button(
                                    label="⬇ ダウンロード",
                                    data=open(str(_zp), "rb"),
                                    file_name=_card["filename"],
                                    mime="application/zip",
                                    key=f"dl_zip_{_card['filename']}_{job['job_id']}",
                                    use_container_width=True,
                                )
                                # ファイルパスをコピー用に表示
                                with st.expander("📋 ファイルパス（コピー用）", expanded=False):
                                    st.code(str(_zp.resolve()), language=None)
                            except Exception as _ze:
                                st.warning(f"⚠️ 読み込みエラー: {_ze}")
                        else:
                            st.info("⏳ 未生成")
                            st.caption(f"`{_card['filename']}`")
                            st.caption("「ZIPを全て生成」で作成できます。")

            # ══════════════════════════════════════════════════════════════
            # H. 納品メッセージ & SNS掲載許可メッセージ
            # ══════════════════════════════════════════════════════════════
            with st.expander("✉️ H. 納品メッセージ / SNS掲載許可メッセージ", expanded=False):
                st.caption(
                    "Instagram DM・公式LINE・メールにそのままコピペできる文章を自動生成します。"
                    "顧客情報を保存後に再生成してください。"
                )
                _hci = get_customer_info(selected_id)

                _h_tab1, _h_tab2 = st.tabs(["📦 納品メッセージ", "📸 SNS掲載許可確認"])

                with _h_tab1:
                    _msg_specs = [
                        ("free_preview", "🆓 無料プレビュー納品文", "free_preview_msg"),
                        ("data_sheet",   "📊 有料データシート納品文", "data_sheet_msg"),
                        ("full_report",  "📦 有料フルレポート納品文", "full_report_msg"),
                    ]
                    for _pkg_type, _pkg_label, _ta_key in _msg_specs:
                        st.markdown(f"**{_pkg_label}**")
                        try:
                            _delivery_url = get_job_s3_status(job).get("delivery_page_url") or ""
                            _msg_text = build_delivery_message(
                                job=job,
                                customer_info=_hci,
                                package_type=_pkg_type,
                                delivery_page_url=_delivery_url,
                            )
                        except Exception as _me:
                            _msg_text = f"(メッセージ生成エラー: {_me})"
                        st.text_area(
                            label=_pkg_label,
                            value=_msg_text,
                            height=200,
                            key=f"{_ta_key}_{selected_id}",
                            label_visibility="collapsed",
                        )
                        st.divider()

                with _h_tab2:
                    st.markdown("**📸 SNS掲載許可確認メッセージ**")
                    st.caption("SNS（Instagram等）への解析事例掲載について、顧客に確認するメッセージです。")
                    _sns_current = SNS_PERMISSION_LABELS.get(_hci.get("permission_for_social_post", "unknown"), "⚠️ 未確認")
                    st.info(f"現在の許可ステータス: **{_sns_current}**")
                    try:
                        _sns_msg = build_sns_permission_message(_hci)
                    except Exception as _sme:
                        _sns_msg = f"(メッセージ生成エラー: {_sme})"
                    st.text_area(
                        label="SNS掲載許可確認文",
                        value=_sns_msg,
                        height=280,
                        key=f"sns_perm_msg_{selected_id}",
                        label_visibility="collapsed",
                    )
                    st.caption("返答後は「G. 顧客情報」欄の「SNS掲載許可ステータス」を更新してください。")

            # ══════════════════════════════════════════════════════════════════
            # L. 納品前チェックリスト
            # ══════════════════════════════════════════════════════════════════
            with st.expander("✅ L. 納品前チェックリスト", expanded=False):
                try:
                    _cl = get_delivery_checklist(selected_id)
                except Exception as _cl_err:
                    st.warning(f"チェックリストの読み込みに失敗しました: {_cl_err}")
                    _cl = {}

                _cl_items = {
                    "chk_intake_confirmed":         "📝 受付情報が入力・確認されている",
                    "chk_dominant_arm":             "💪 利き腕が設定されている（右/左）",
                    "chk_height":                   "📏 身長が設定されている（0m以外）",
                    "chk_filming_angle":            "🎥 撮影角度が確認されている",
                    "chk_pdf_generated":            "📄 PDFが生成されている",
                    "chk_analysis_video":           "🎬 解析動画が生成されている",
                    "chk_zip_generated":            "🗜️ 納品ZIPが生成されている",
                    "chk_readme_in_zip":            "📋 ZIP内に「00_最初に読んでください.pdf」がある",
                    "chk_instruction_pdf":          "📖 ZIP内に解析動画の見方PDFがある",
                    "chk_disclaimer_in_zip":        "⚖️ ZIP内に免責事項ファイルがある",
                    "chk_plan_matches_deliverables":"🎯 希望プランと納品物の内容が一致している",
                    "chk_sns_permission":           "📸 SNS掲載許可ステータスが確認されている",
                    "chk_delivery_message_ready":   "✉️ 納品メッセージが生成されている",
                }
                _checked_vals = {k: bool(_cl.get(k, False)) for k in _cl_items}
                _checked_count = sum(_checked_vals.values())
                _total_count   = len(_cl_items)
                st.progress(
                    _checked_count / _total_count if _total_count > 0 else 0.0,
                    text=f"進捗: {_checked_count} / {_total_count}",
                )
                if _checked_count < _total_count:
                    st.warning(f"⚠️ {_total_count - _checked_count} 項目が未チェックです。")
                else:
                    st.success("🎉 全項目チェック済み！納品準備完了です。")

                _new_cl: dict = {}
                _cl_col1, _cl_col2 = st.columns(2)
                _cl_keys  = list(_cl_items.keys())
                _cl_half  = (_total_count + 1) // 2
                for _i, (_k, _label) in enumerate(_cl_items.items()):
                    _col_target = _cl_col1 if _i < _cl_half else _cl_col2
                    with _col_target:
                        _new_cl[_k] = st.checkbox(
                            _label,
                            value=_checked_vals[_k],
                            key=f"cl_{_k}_{selected_id}",
                        )
                if st.button("💾 チェックリストを保存", key=f"cl_save_{selected_id}"):
                    update_delivery_checklist(selected_id, **_new_cl)
                    st.success("✅ チェックリストを保存しました。")
                    st.rerun()
                st.caption(f"updated_at: {_cl.get('updated_at', '—')}")

            # ── O. フェーズ指定 ─────────────────────────────────────────────────
            with st.expander("🎬 O. フェーズ指定", expanded=False):
                try:
                    from src.phase_loader import load_phases, get_all_phase_keys, is_range_phase
                    _phases_def = load_phases()
                    _phase_keys = get_all_phase_keys()
                except Exception as _phe:
                    st.error(f"フェーズ定義の読み込みに失敗しました: {_phe}")
                    _phases_def = {}
                    _phase_keys = []

                _pf = get_phase_frames(selected_id)

                # 動画 FPS / 総フレーム数
                _pf_col1, _pf_col2, _pf_col3 = st.columns(3)
                with _pf_col1:
                    _fps_val = _pf.get("fps") or 0.0
                    _fps_new = st.number_input(
                        "FPS", min_value=0.0, max_value=240.0,
                        value=float(_fps_val), step=0.001, format="%.3f",
                        key=f"pf_fps_{selected_id}",
                    )
                with _pf_col2:
                    _total_frames_val = _pf.get("total_frames") or 0
                    _total_frames_new = st.number_input(
                        "総フレーム数", min_value=0, max_value=1_000_000,
                        value=int(_total_frames_val), step=1,
                        key=f"pf_total_{selected_id}",
                    )
                with _pf_col3:
                    _dur = (_total_frames_new / _fps_new) if _fps_new > 0 else 0.0
                    st.metric("動画尺（秒）", f"{_dur:.2f} 秒")

                st.divider()

                _pf_new: dict = {}
                for _phase_key in _phase_keys:
                    _phase_def = _phases_def.get(_phase_key, {})
                    _phase_label = _phase_def.get("label", _phase_key)
                    _is_range = is_range_phase(_phase_key)
                    st.markdown(f"**{_phase_label}**")
                    if _is_range:
                        _c1, _c2 = st.columns(2)
                        with _c1:
                            _sf_key = f"{_phase_key}_start_frame"
                            _sf_val = _pf.get(_sf_key)
                            _sf_new = st.number_input(
                                "開始フレーム",
                                min_value=0, max_value=1_000_000,
                                value=int(_sf_val) if _sf_val is not None else 0,
                                step=1,
                                key=f"pf_{_sf_key}_{selected_id}",
                            )
                            _sf_sec = (_sf_new / _fps_new) if _fps_new > 0 else 0.0
                            st.caption(f"= {_sf_sec:.2f} 秒")
                            _pf_new[_sf_key] = _sf_new if _sf_new > 0 else None
                        with _c2:
                            _ef_key = f"{_phase_key}_end_frame"
                            _ef_val = _pf.get(_ef_key)
                            _ef_new = st.number_input(
                                "終了フレーム",
                                min_value=0, max_value=1_000_000,
                                value=int(_ef_val) if _ef_val is not None else 0,
                                step=1,
                                key=f"pf_{_ef_key}_{selected_id}",
                            )
                            _ef_sec = (_ef_new / _fps_new) if _fps_new > 0 else 0.0
                            st.caption(f"= {_ef_sec:.2f} 秒")
                            _pf_new[_ef_key] = _ef_new if _ef_new > 0 else None
                    else:
                        _ff_key = f"{_phase_key}_frame"
                        _ff_val = _pf.get(_ff_key)
                        _ff_new = st.number_input(
                            "フレーム番号",
                            min_value=0, max_value=1_000_000,
                            value=int(_ff_val) if _ff_val is not None else 0,
                            step=1,
                            key=f"pf_{_ff_key}_{selected_id}",
                        )
                        _ff_sec = (_ff_new / _fps_new) if _fps_new > 0 else 0.0
                        st.caption(f"= {_ff_sec:.2f} 秒")
                        _pf_new[_ff_key] = _ff_new if _ff_new > 0 else None

                st.divider()
                _pf_btn_col1, _pf_btn_col2, _pf_btn_col3 = st.columns(3)

                with _pf_btn_col1:
                    if st.button("💾 フェーズ情報を保存", key=f"pf_save_{selected_id}"):
                        update_phase_frames(
                            selected_id,
                            fps=_fps_new if _fps_new > 0 else None,
                            total_frames=_total_frames_new if _total_frames_new > 0 else None,
                            **_pf_new,
                        )
                        st.success("✅ フェーズ情報を保存しました。")
                        st.rerun()

                with _pf_btn_col2:
                    if st.button("🖼️ フェーズ代表フレーム生成", key=f"pf_extract_{selected_id}"):
                        with st.spinner("フレーム抽出中..."):
                            try:
                                from src.phase_frames import extract_phase_frames_for_job
                                _pf_result = extract_phase_frames_for_job(get_job_dir(selected_id))
                                if _pf_result:
                                    st.success(f"✅ {len(_pf_result)} 件のフレームを抽出しました。")
                                else:
                                    st.warning("抽出対象がありませんでした。フェーズ情報を保存してから再実行してください。")
                            except Exception as _pfe:
                                st.error(f"フレーム抽出エラー: {_pfe}")

                with _pf_btn_col3:
                    if st.button("📄 フェーズ別サマリーPDF生成", key=f"pf_pdf_{selected_id}"):
                        with st.spinner("PDF生成中..."):
                            try:
                                from src.phase_summary_pdf import generate_phase_summary_pdf
                                _ps_pdf = generate_phase_summary_pdf(get_job_dir(selected_id))
                                st.success(f"✅ PDF生成: `{_ps_pdf.name}`")
                            except Exception as _pse:
                                st.error(f"PDF生成エラー: {_pse}")

                # フェーズ代表フレーム画像プレビュー
                _phase_img_dir_preview = get_job_dir(selected_id) / "report" / "phase_frames"
                if _phase_img_dir_preview.exists():
                    _preview_imgs = sorted(_phase_img_dir_preview.glob("phase_*.jpg"))
                    if _preview_imgs:
                        st.caption(f"生成済みフレーム画像: {len(_preview_imgs)} 件")
                        _prev_cols = st.columns(min(4, len(_preview_imgs)))
                        for _pi, _pimg in enumerate(_preview_imgs):
                            with _prev_cols[_pi % 4]:
                                st.image(str(_pimg), caption=_pimg.stem, use_container_width=True)

                st.caption(f"updated_at: {_pf.get('updated_at', '—')}")

            # ── P. S3納品 / 納品URL発行 ─────────────────────────────────────────
            with st.expander("☁️ P. S3納品 / 納品URL発行", expanded=False):
                _s3_modules_ok = _S3_MODULES_AVAILABLE
                _s3_ok = is_s3_configured()
                if not _s3_modules_ok:
                    st.warning(
                        "S3モジュールが読み込めません。`pip install boto3` でインストールしてください。"
                    )
                elif not _s3_ok:
                    st.warning(
                        "S3が未設定です。`.env` に `JVA_BUCKET` を設定してください。  \n"
                        "設定方法: `docs/s3_delivery_setup.md` を参照。"
                    )

                if not _s3_modules_ok:
                    # S3モジュール自体が読み込めない場合はここで終了
                    pass
                else:
                    if _s3_ok:
                        _s3_cfg = get_s3_config()
                        st.caption(
                            f"S3バケット: `{_s3_cfg['bucket']}` / リージョン: `{_s3_cfg['region']}` / "
                            f"プレフィックス: `{_s3_cfg['prefix']}` / URL有効期限: {_s3_cfg['expires_seconds']//86400}日"
                        )

                    # 現在の S3 ステータス表示
                    _s3_status = get_job_s3_status(_job)
                    _upload_status_label = {
                        "none": "未アップロード",
                        "partial": "一部アップロード済",
                        "complete": "アップロード完了",
                    }.get(_s3_status["upload_status"], "—")
                    st.write(f"**アップロード状況:** {_upload_status_label}")
                    if _s3_status["last_uploaded_at"]:
                        st.caption(f"最終アップロード: {_s3_status['last_uploaded_at']}")
                    if _s3_status["delivery_url_expires_at"]:
                        st.caption(f"URL有効期限: {_s3_status['delivery_url_expires_at']}")

                    # 成果物マニフェスト
                    st.markdown("---")
                    st.markdown("**① 成果物マニフェスト確認**")
                    if st.button("📋 マニフェスト生成 / 更新", key=f"manifest_gen_{_job_id}"):
                        with st.spinner("マニフェスト生成中..."):
                            _manifest = build_artifact_manifest(
                                job_dir=_job_dir,
                                job_id=_job_id,
                            )
                            save_artifact_manifest(_job_dir, _manifest)
                            st.success(f"✅ {_manifest['total_count']} 件を検出しました（存在: {_manifest['exists_count']} / 未生成: {_manifest['missing_count']}）")
                            st.session_state[f"manifest_{_job_id}"] = _manifest

                    _cached_manifest = st.session_state.get(f"manifest_{_job_id}") or load_artifact_manifest(_job_dir)
                    if _cached_manifest:
                        with st.expander("成果物一覧を表示", expanded=False):
                            for _art in _cached_manifest.get("artifacts", []):
                                _icon = "✅" if _art["exists"] else "❌"
                                st.caption(f"{_icon} [{_art['category']}] {_art['label']} — `{_art['local_path']}`")

                    # S3 アップロード
                    st.markdown("---")
                    st.markdown("**② S3 アップロード**")
                    _upload_btn_disabled = not _s3_ok
                    if st.button(
                        "☁️ 成果物を S3 にアップロード",
                        key=f"s3_upload_{_job_id}",
                        disabled=_upload_btn_disabled,
                    ):
                        _manifest = _cached_manifest or build_artifact_manifest(_job_dir, _job_id)
                        _uploaded_list: list[dict] = []
                        _failed_list: list[dict] = []
                        _arts = [a for a in _manifest.get("artifacts", []) if a["exists"]]
                        with st.spinner(f"S3 アップロード中... ({len(_arts)} 件)"):
                            for _art in _arts:
                                _lpath = _job_dir / _art["local_path"]
                                _res = upload_file_to_s3(
                                    _lpath,
                                    _art["s3_key"],
                                    content_type=_art.get("content_type"),
                                )
                                if _res["ok"]:
                                    _uploaded_list.append(_res)
                                else:
                                    _failed_list.append(_res)
                        # ログ保存
                        _expires_at_log = get_presigned_url_expires_at()
                        _log_path = _REPO_ROOT / "logs" / "s3_upload.log"
                        append_upload_log(_log_path, _job_id, _uploaded_list, _failed_list, _expires_at_log)
                        # ジョブメタ更新
                        _total_uploaded = len(_uploaded_list)
                        _new_status = "complete" if not _failed_list else ("partial" if _uploaded_list else "none")
                        update_job_s3_delivery(
                            _job_id,
                            delivery_page_s3_key="",
                            delivery_page_url=_s3_status.get("delivery_page_url") or "",
                            delivery_url_expires_at=_expires_at_log,
                            uploaded_artifacts_count=_total_uploaded,
                            upload_status=_new_status,
                        )
                        if _failed_list:
                            st.warning(f"⚠️ {len(_failed_list)} 件失敗: " + ", ".join(f["s3_key"].split("/")[-1] for f in _failed_list[:5]))
                        st.success(f"✅ {_total_uploaded} 件アップロード完了 (失敗: {len(_failed_list)} 件)")
                        st.rerun()

                    # 納品ページ HTML 生成 & URL 発行
                    st.markdown("---")
                    st.markdown("**③ 納品ページ生成 & URL 発行**")
                    if st.button(
                        "🌐 納品ページHTMLを生成して S3 にアップロード",
                        key=f"delivery_html_{_job_id}",
                        disabled=_upload_btn_disabled,
                    ):
                        _manifest = _cached_manifest or build_artifact_manifest(_job_dir, _job_id)
                        with st.spinner("presigned URL 生成中..."):
                            _presigned = generate_presigned_urls_for_job(_job_id, _manifest.get("artifacts", []))
                        _expires_at_str = get_presigned_url_expires_at()
                        _ci = get_customer_info(_job_id)
                        with st.spinner("納品ページ HTML 生成中..."):
                            _html = generate_delivery_page(
                                manifest=_manifest,
                                customer_info=_ci,
                                job_id=_job_id,
                                presigned_urls=_presigned,
                                expires_at=_expires_at_str,
                                job_label=_job_id[:16],
                            )
                            _html_path = save_delivery_page(_job_dir / "report", _html)
                        # S3 アップロード
                        _html_s3_key = build_s3_key_for_job(_job_id, "delivery/delivery_page.html")
                        _html_result = upload_file_to_s3(_html_path, _html_s3_key, content_type="text/html")
                        if _html_result["ok"]:
                            _page_url = generate_presigned_url(_html_s3_key) or ""
                            update_job_s3_delivery(
                                _job_id,
                                delivery_page_s3_key=_html_s3_key,
                                delivery_page_url=_page_url,
                                delivery_url_expires_at=_expires_at_str,
                                uploaded_artifacts_count=_s3_status.get("uploaded_artifacts_count") or 0,
                                upload_status=_s3_status.get("upload_status") or "partial",
                            )
                            st.success("✅ 納品ページをアップロードしました。")
                            st.rerun()
                        else:
                            st.error(f"❌ アップロード失敗: {_html_result.get('error')}")

                    # 発行済み URL 表示
                    _cur_s3 = get_job_s3_status(load_job(_job_id) if _s3_ok else _job)
                    if _cur_s3.get("delivery_page_url"):
                        st.markdown("**📱 納品URL（LINEで送付）:**")
                        st.text_area(
                            label="納品URL",
                            value=_cur_s3["delivery_page_url"],
                            height=80,
                            key=f"delivery_url_display_{_job_id}",
                            label_visibility="collapsed",
                        )
                        st.caption(f"有効期限: {_cur_s3.get('delivery_url_expires_at', '—')}")


# ─── Tab 3: ジョブ比較 ────────────────────────────────────────────────────────


with tab_compare:
    st.header("⚖️ ジョブ比較")

    _cmp_tab_a, _cmp_tab_b = st.tabs(["➕ 比較ジョブ作成", "📂 比較ジョブ一覧"])

    # ─── 比較ジョブ作成 ────────────────────────────────────────────────────────
    with _cmp_tab_a:
        st.subheader("新しい比較ジョブを作成")
        st.caption(
            "完了済みの2つのジョブを選択し、比較ジョブとして登録します。"
            "登録後に「比較ジョブ一覧」タブから比較レポートや ZIP を生成できます。"
        )

        _all_jobs_c = list_jobs()
        _done_jobs_c = [j for j in _all_jobs_c if j.get("status") == "completed"]

        if len(_done_jobs_c) < 2:
            st.warning(
                "比較には完了済みジョブが2つ以上必要です。"
                "先に「新規ジョブ」タブで解析を実行してください。"
            )
        else:
            def _job_label_c(j: dict) -> str:
                ci = get_customer_info(j["job_id"])
                name = ci.get("customer_name") or ""
                ts = j.get("created_at", j["job_id"])[:16] if j.get("created_at") else j["job_id"]
                return f"{ts}  {name}  [{j['job_id']}]" if name else f"{ts}  [{j['job_id']}]"

            _job_opts_c   = [j["job_id"] for j in _done_jobs_c]
            _job_lbls_c   = {j["job_id"]: _job_label_c(j) for j in _done_jobs_c}
            _lbl_to_id_c  = {v: k for k, v in _job_lbls_c.items()}
            _disp_opts_c  = [_job_lbls_c[jid] for jid in _job_opts_c]

            _cc1, _cc2 = st.columns(2)
            with _cc1:
                st.markdown("**Job A（比較元 / 旧 / 1本目）**")
                _sel_a_c_lbl = st.selectbox(
                    "Job A", options=_disp_opts_c, index=0,
                    key="new_cmp_job_a", label_visibility="collapsed",
                )
                _label_a_new = st.text_input(
                    "動画A の表示名", value="動画A",
                    key="new_cmp_label_a",
                    help="例: 改善前 / 試合1本目 / 成功投てき",
                )
            with _cc2:
                st.markdown("**Job B（比較先 / 新 / 2本目）**")
                _sel_b_c_lbl = st.selectbox(
                    "Job B", options=_disp_opts_c,
                    index=min(1, len(_disp_opts_c) - 1),
                    key="new_cmp_job_b", label_visibility="collapsed",
                )
                _label_b_new = st.text_input(
                    "動画B の表示名", value="動画B",
                    key="new_cmp_label_b",
                    help="例: 改善後 / 試合2本目 / 失敗投てき",
                )

            _sel_a_c_id = _lbl_to_id_c[_sel_a_c_lbl]
            _sel_b_c_id = _lbl_to_id_c[_sel_b_c_lbl]

            _purpose_new = st.text_area(
                "比較目的（任意）", value="",
                key="new_cmp_purpose",
                placeholder="例: 助走フォームの改善前後を確認する",
                height=80,
            )
            _memo_new = st.text_area(
                "管理者メモ（任意）", value="",
                key="new_cmp_memo",
                height=60,
            )

            _same_id_warn = _sel_a_c_id == _sel_b_c_id
            if _same_id_warn:
                st.warning("同じジョブが選択されています。異なるジョブを選択してください。")

            if st.button(
                "➕ 比較ジョブを作成",
                key="btn_create_comparison",
                disabled=_same_id_warn,
            ):
                _new_comp = create_comparison(
                    job_a_id=_sel_a_c_id,
                    job_b_id=_sel_b_c_id,
                    label_a=_label_a_new or "動画A",
                    label_b=_label_b_new or "動画B",
                    purpose=_purpose_new,
                    admin_memo=_memo_new,
                )
                st.success(f"✅ 比較ジョブを作成しました: `{_new_comp['comparison_id']}`")
                st.rerun()

    # ─── 比較ジョブ一覧 ────────────────────────────────────────────────────────
    with _cmp_tab_b:
        st.subheader("比較ジョブ一覧")

        _cmp_list = list_comparisons()

        if not _cmp_list:
            st.info("比較ジョブはまだありません。「比較ジョブ作成」タブから作成してください。")
        else:
            for _comp in _cmp_list:
                _cid      = _comp.get("comparison_id", "—")
                _cla      = _comp.get("label_a", "動画A")
                _clb      = _comp.get("label_b", "動画B")
                _cja      = _comp.get("job_a_id", "—")
                _cjb      = _comp.get("job_b_id", "—")
                _cstat    = _comp.get("status", "created")
                _cpurpose = _comp.get("purpose", "")
                _ccreated = _comp.get("created_at", "—")[:16] if _comp.get("created_at") else "—"

                with st.expander(
                    f"📊 {_ccreated}  |  {_cla} vs {_clb}  [{_cid}]  ({_cstat})",
                    expanded=False,
                ):
                    _ci_col1, _ci_col2 = st.columns(2)
                    with _ci_col1:
                        st.markdown(f"**{_cla}**  `{_cja}`")
                    with _ci_col2:
                        st.markdown(f"**{_clb}**  `{_cjb}`")
                    if _cpurpose:
                        st.caption(f"比較目的: {_cpurpose}")

                    # ステータス変更
                    _status_opts = ["created", "report_generated", "delivered"]
                    _status_labels = {
                        "created": "作成済み",
                        "report_generated": "レポート生成済み",
                        "delivered": "納品済み",
                    }
                    _cur_status_idx = _status_opts.index(_cstat) if _cstat in _status_opts else 0
                    _new_status_label = st.selectbox(
                        "ステータス",
                        options=[_status_labels[s] for s in _status_opts],
                        index=_cur_status_idx,
                        key=f"cmp_status_{_cid}",
                    )
                    _new_status = _status_opts[[_status_labels[s] for s in _status_opts].index(_new_status_label)]
                    if _new_status != _cstat:
                        if st.button("💾 ステータス保存", key=f"cmp_stat_save_{_cid}"):
                            update_comparison(_cid, status=_new_status)
                            st.success("ステータスを更新しました。")
                            st.rerun()

                    st.divider()

                    # 生成ボタン群
                    _cmp_dir_path = get_comparison_dir(_cid)
                    _dir_a_path   = get_job_dir(_cja)
                    _dir_b_path   = get_job_dir(_cjb)

                    _cbtn1, _cbtn2, _cbtn3, _cbtn4 = st.columns(4)

                    with _cbtn1:
                        if st.button("📊 差分比較実行", key=f"cmp_run_{_cid}"):
                            with st.spinner("比較中..."):
                                try:
                                    from src.compare_jobs import compare_two_jobs, save_comparison
                                    _cr = compare_two_jobs(_dir_a_path, _dir_b_path)
                                    if _cr.get("status") == "error":
                                        st.error(f"比較エラー: {_cr.get('error')}")
                                    else:
                                        save_comparison(
                                            _cr,
                                            comparisons_root=_cmp_dir_path.parent,
                                            comparison_id=_cid,
                                        )
                                        update_comparison(_cid, status="report_generated")
                                        st.success("✅ 差分比較完了")
                                        st.rerun()
                                except Exception as _cre:
                                    st.error(f"比較エラー: {_cre}")

                    with _cbtn2:
                        if st.button("📄 比較レポートPDF", key=f"cmp_pdf_{_cid}"):
                            with st.spinner("PDF生成中..."):
                                try:
                                    from src.comparison_report_pdf import generate_comparison_report_pdf
                                    _rp = generate_comparison_report_pdf(
                                        comparison_dir=_cmp_dir_path,
                                        job_dir_a=_dir_a_path,
                                        job_dir_b=_dir_b_path,
                                        label_a=_cla,
                                        label_b=_clb,
                                        purpose=_cpurpose,
                                    )
                                    update_comparison(_cid, status="report_generated")
                                    st.success(f"✅ PDF生成: `{_rp.name}`")
                                    st.rerun()
                                except Exception as _re:
                                    st.error(f"PDF生成エラー: {_re}")

                    with _cbtn3:
                        if st.button("📦 比較ZIP生成", key=f"cmp_zip_{_cid}"):
                            with st.spinner("ZIP生成中..."):
                                try:
                                    from src.comparison_zip import create_comparison_zip
                                    _zp = create_comparison_zip(
                                        comparison_dir=_cmp_dir_path,
                                        job_dir_a=_dir_a_path,
                                        job_dir_b=_dir_b_path,
                                        label_a=_cla,
                                        label_b=_clb,
                                    )
                                    st.success(f"✅ ZIP生成: `{_zp.name}`")
                                    st.rerun()
                                except Exception as _ze:
                                    st.error(f"ZIP生成エラー: {_ze}")

                    with _cbtn4:
                        # ZIP ダウンロード
                        _zip_path = _cmp_dir_path / "comparison_package.zip"
                        if _zip_path.exists():
                            with open(_zip_path, "rb") as _zf:
                                st.download_button(
                                    "⬇️ ZIP DL",
                                    data=_zf.read(),
                                    file_name=f"comparison_{_cid}.zip",
                                    mime="application/zip",
                                    key=f"cmp_dl_{_cid}",
                                )
                        else:
                            st.button("⬇️ ZIP DL", disabled=True, key=f"cmp_dl_na_{_cid}")

                    # 生成済みファイル一覧
                    if _cmp_dir_path.exists():
                        _cmp_files = [f for f in _cmp_dir_path.iterdir() if f.is_file()]
                        if _cmp_files:
                            with st.expander("📁 生成済みファイル", expanded=False):
                                for _cf in sorted(_cmp_files):
                                    size_kb = _cf.stat().st_size // 1024
                                    st.caption(f"`{_cf.name}` ({size_kb} KB)")

                    # 比較サマリー表示
                    _csummary_path = _cmp_dir_path / "comparison_summary.json"
                    if _csummary_path.exists():
                        try:
                            import json as _json_c
                            _cs = _json_c.loads(_csummary_path.read_text(encoding="utf-8"))
                            _csfields = _cs.get("fields", {})
                            if _csfields:
                                _csrows = []
                                for _fk, _fv in _csfields.items():
                                    _dv = _fv.get("diff")
                                    _csrows.append({
                                        "指標":         _fv.get("label", _fk),
                                        _cla:           _fv.get("a") if _fv.get("a") is not None else "—",
                                        _clb:           _fv.get("b") if _fv.get("b") is not None else "—",
                                        "差分 (B−A)": f"+{_dv:.3f}" if (_dv is not None and _dv > 0) else (f"{_dv:.3f}" if _dv is not None else "—"),
                                    })
                                st.dataframe(pd.DataFrame(_csrows), use_container_width=True, hide_index=True)
                        except Exception:
                            pass

                    # ── S3納品 / 納品URL発行（比較ジョブ） ────────────────────
                    if _S3_MODULES_AVAILABLE:
                        st.divider()
                        with st.expander("☁️ S3納品 / 納品URL発行（比較ジョブ）", expanded=False):
                            _cmp_s3_ok = is_s3_configured()
                            if not _cmp_s3_ok:
                                st.warning(
                                    "S3が未設定です。`.env` に `JVA_BUCKET` を設定してください。"
                                )
                            else:
                                _cmp_s3_btn_disabled = False

                                if st.button("📋 マニフェスト生成", key=f"cmp_manifest_{_cid}"):
                                    with st.spinner("マニフェスト生成中..."):
                                        _cmp_manifest = build_comparison_artifact_manifest(
                                            comparison_dir=_cmp_dir_path,
                                            comparison_id=_cid,
                                            job_dir_a=_dir_a_path,
                                            job_dir_b=_dir_b_path,
                                            label_a=_cla,
                                            label_b=_clb,
                                        )
                                        save_artifact_manifest(_cmp_dir_path, _cmp_manifest)
                                        st.success(
                                            f"✅ {_cmp_manifest['total_count']} 件を検出しました"
                                            f"（存在: {_cmp_manifest['exists_count']} / 未生成: {_cmp_manifest['missing_count']}）"
                                        )
                                        st.session_state[f"cmp_manifest_{_cid}"] = _cmp_manifest

                                _cmp_cached = st.session_state.get(f"cmp_manifest_{_cid}") or load_artifact_manifest(_cmp_dir_path)

                                if st.button(
                                    "☁️ S3 アップロード",
                                    key=f"cmp_s3_upload_{_cid}",
                                    disabled=_cmp_s3_btn_disabled,
                                ):
                                    _cmp_manifest = _cmp_cached or build_comparison_artifact_manifest(
                                        comparison_dir=_cmp_dir_path,
                                        comparison_id=_cid,
                                        job_dir_a=_dir_a_path,
                                        job_dir_b=_dir_b_path,
                                        label_a=_cla,
                                        label_b=_clb,
                                    )
                                    _cmp_arts = [a for a in _cmp_manifest.get("artifacts", []) if a["exists"]]
                                    _cmp_uploaded: list[dict] = []
                                    _cmp_failed: list[dict] = []
                                    with st.spinner(f"S3 アップロード中... ({len(_cmp_arts)} 件)"):
                                        for _ca in _cmp_arts:
                                            _clpath = (_cmp_dir_path / _ca["local_path"]) if not (_cmp_dir_path / _ca["local_path"]).is_absolute() else Path(_ca["local_path"])
                                            _cres = upload_file_to_s3(
                                                _clpath,
                                                _ca["s3_key"],
                                                content_type=_ca.get("content_type"),
                                            )
                                            if _cres["ok"]:
                                                _cmp_uploaded.append(_cres)
                                            else:
                                                _cmp_failed.append(_cres)
                                    if _cmp_failed:
                                        st.warning(f"⚠️ {len(_cmp_failed)} 件失敗")
                                    st.success(f"✅ {len(_cmp_uploaded)} 件アップロード完了")
                                    st.rerun()

        # 既存の比較サマリー（compare_jobs.py 出力の旧形式）を参照
        st.divider()
        st.subheader("旧形式の比較履歴（jobs/comparisons/）")
        _old_comp_root = JOBS_DIR / "comparisons"
        if not _old_comp_root.exists() or not any(_old_comp_root.iterdir()):
            st.info("旧形式の比較履歴はありません。")
        else:
            try:
                from src.compare_jobs import list_comparisons as _list_old_cmp
                _old_history = _list_old_cmp(_old_comp_root)
            except Exception:
                _old_history = []

            if not _old_history:
                st.info("旧形式の比較履歴の読み込みに失敗しました。")
            else:
                for _h in _old_history:
                    _cid_h  = _h.get("comparison_id", "—")
                    _hja    = _h.get("job_a", {})
                    _hjb    = _h.get("job_b", {})
                    _hgen   = _h.get("generated_at", "—")
                    with st.expander(
                        f"🕓 {_cid_h}  |  {_hja.get('job_id','?')}  vs  {_hjb.get('job_id','?')}",
                        expanded=False,
                    ):
                        if _h.get("status") == "error":
                            st.error(_h.get("error"))
                        else:
                            _hfields = _h.get("fields", {})
                            _hrows = []
                            for _fk, _fv in _hfields.items():
                                _dv = _fv.get("diff")
                                _hrows.append({
                                    "指標":         _fv.get("label", _fk),
                                    "Job A":        _fv.get("a") if _fv.get("a") is not None else "—",
                                    "Job B":        _fv.get("b") if _fv.get("b") is not None else "—",
                                    "差分 (B − A)": f"+{_dv}" if (_dv is not None and _dv > 0) else (str(_dv) if _dv is not None else "—"),
                                })
                            st.dataframe(
                                pd.DataFrame(_hrows),
                                use_container_width=True,
                                hide_index=True,
                            )
                            st.caption(f"生成日時: {_hgen}")




# ─── Tab 4: 運用チェックリスト ────────────────────────────────────────────────

with tab_checklist:
    render_operation_checklist_tab()


# ─── Tab 5: GoogleフォームCSVインポート ───────────────────────────────────────

with tab_import:
    st.header("📥 GoogleフォームCSVインポート")
    st.caption(
        "GoogleフォームのCSVエクスポートをアップロードし、受付情報として取り込みます。"
        "新規ジョブを作成して intake_info.json に保存します。"
        "Googleフォームの列名は柔軟にマッピングできます。"
    )

    _csv_file = st.file_uploader("CSVファイルをアップロード", type=["csv"])

    if _csv_file is not None:
        try:
            import io as _io
            _df = pd.read_csv(_io.BytesIO(_csv_file.read()))
            st.success(f"✅ {len(_df)} 行、{len(_df.columns)} 列のデータを読み込みました。")
        except Exception as _csv_err:
            st.error(f"CSVの読み込みに失敗しました: {_csv_err}")
            _df = None

        if _df is not None and len(_df) > 0:
            st.markdown("#### 列マッピング")
            st.caption("CSVの列名を受付情報のフィールドへマッピングしてください（不要な列は「（スキップ）」を選択）。")

            _intake_field_labels = {
                "(skip)":            "（スキップ）",
                "name_or_nickname":  "名前またはニックネーム",
                "contact":           "連絡先",
                "age_group":         "年齢区分",
                "gender":            "性別",
                "athletic_career":   "競技歴",
                "personal_best":     "自己ベスト",
                "dominant_arm":      "利き腕",
                "height_m":          "身長(m)",
                "affiliation_type":  "所属区分",
                "filming_date":      "撮影日",
                "filming_context":   "撮影状況",
                "filming_angle":     "撮影角度",
                "video_type":        "動画種別",
                "video_count":       "動画本数",
                "video_priority_note": "動画優先順位メモ",
                "video_memo":        "動画メモ",
                "focus_main":        "一番見てほしい点",
                "focus_other":       "その他相談内容",
                "desired_plan":      "希望プラン",
            }
            _skip_label  = "(skip)"
            _field_opts  = list(_intake_field_labels.keys())

            # 自動推測: 列名から近い候補を選ぶ
            def _guess_field(col: str) -> str:
                _col_lower = col.lower()
                _hints = {
                    "name_or_nickname": ["名前", "ニックネーム", "name", "nickname"],
                    "contact":          ["連絡先", "contact", "sns", "instagram", "line"],
                    "age_group":        ["年齢区分", "年齢", "age"],
                    "gender":           ["性別", "gender", "sex"],
                    "athletic_career":  ["競技歴", "キャリア", "career"],
                    "personal_best":    ["自己ベスト", "pb", "best"],
                    "dominant_arm":     ["利き腕", "dominant", "arm"],
                    "height_m":         ["身長", "height"],
                    "affiliation_type": ["所属", "affiliation"],
                    "filming_date":     ["撮影日", "filming_date", "date"],
                    "filming_context":  ["撮影状況", "大会", "練習", "context"],
                    "video_type":       ["動画種別", "全助走", "video_type"],
                    "video_count":      ["動画本数", "本数", "video_count", "count"],
                    "focus_main":       ["見てほしい", "相談", "focus", "request"],
                    "desired_plan":     ["希望プラン", "plan"],
                }
                for _fk, _kws in _hints.items():
                    for _kw in _kws:
                        if _kw.lower() in _col_lower:
                            return _fk
                return _skip_label

            _mapping: dict[str, str] = {}
            _map_cols = st.columns(3)
            for _ci2, _col_name in enumerate(_df.columns):
                _default_field = _guess_field(_col_name)
                _default_idx   = _field_opts.index(_default_field)
                with _map_cols[_ci2 % 3]:
                    _chosen = st.selectbox(
                        f"`{_col_name}`",
                        options=_field_opts,
                        format_func=lambda x: _intake_field_labels[x],
                        index=_default_idx,
                        key=f"csv_map_{_ci2}",
                    )
                    _mapping[_col_name] = _chosen

            st.markdown("#### 取り込む行を選択")
            _row_labels = [f"行 {_ri + 1}: {_df.iloc[_ri].values[:3].tolist()}" for _ri in range(len(_df))]
            _selected_rows = st.multiselect(
                "取り込む行",
                options=list(range(len(_df))),
                format_func=lambda i: _row_labels[i],
                default=list(range(min(len(_df), 5))),
            )

            if st.button("🚀 選択行を新規ジョブとして取り込む", type="primary", key="csv_import_btn"):
                if not _selected_rows:
                    st.warning("取り込む行が選択されていません。")
                else:
                    _import_errors: list[str] = []
                    _import_success = 0
                    for _ri in _selected_rows:
                        try:
                            _row = _df.iloc[_ri]
                            _new_job  = create_job(height_m=None, mode="basic")
                            _new_jid  = _new_job["job_id"]
                            _intake_kwargs: dict = {}
                            for _col_n, _field_k in _mapping.items():
                                if _field_k == _skip_label:
                                    continue
                                _raw_val = _row.get(_col_n)
                                if pd.isna(_raw_val):
                                    continue
                                if _field_k == "height_m":
                                    try:
                                        _intake_kwargs[_field_k] = float(str(_raw_val).replace("cm", "").replace("m", "").strip())
                                        # cmで入力されている場合は自動変換
                                        if _intake_kwargs[_field_k] > 10:
                                            _intake_kwargs[_field_k] = round(_intake_kwargs[_field_k] / 100.0, 2)
                                    except (ValueError, TypeError):
                                        pass
                                elif _field_k == "video_count":
                                    try:
                                        _intake_kwargs[_field_k] = int(_raw_val)
                                    except (ValueError, TypeError):
                                        pass
                                else:
                                    _intake_kwargs[_field_k] = str(_raw_val).strip()
                            update_intake_info(_new_jid, **_intake_kwargs)
                            _import_success += 1
                        except Exception as _row_err:
                            _import_errors.append(f"行 {_ri + 1}: {_row_err}")
                    if _import_success:
                        st.success(f"✅ {_import_success} 件のジョブを作成しました。")
                    if _import_errors:
                        for _em in _import_errors:
                            st.error(f"❌ エラー: {_em}")
                    if _import_success:
                        st.info("「📋 ジョブ履歴」タブで確認してください。")
    else:
        st.info("CSVファイルをアップロードしてください。")
        with st.expander("📋 Googleフォームの列名ガイド（推奨）", expanded=False):
            st.markdown("""
フォームの質問タイトルに以下のキーワードを含めると自動マッピングされます：

| 推奨質問タイトル | マッピング先 |
|---|---|
| 名前またはニックネーム | 名前またはニックネーム |
| 連絡先（SNS/LINE名） | 連絡先 |
| 年齢区分 | 年齢区分 |
| 競技歴 | 競技歴 |
| 自己ベスト | 自己ベスト |
| 利き腕 | 利き腕 |
| 身長（cm） | 身長（cmで入力した場合は自動でmに変換） |
| 所属区分 | 所属区分 |
| 撮影日 | 撮影日 |
| 一番見てほしい点 | 一番見てほしい点 |
| 希望プラン | 希望プラン |

詳細は `docs/video_submission_guide.md` と `docs/google_form_template.md` を参照してください。
""")


# ─── Tab 6: 受付一覧 (intake) ──────────────────────────────────────────────────

with tab_intakes:
    st.header("📨 受付一覧")

    if not _INTAKE_AVAILABLE:
        st.error("`src/intake_manager.py` が読み込めません。インストールを確認してください。")
        st.stop()

    # ── フィルタ ─────────────────────────────────────────────────────────────
    with st.expander("🔍 フィルタ", expanded=False):
        _f_col1, _f_col2, _f_col3 = st.columns(3)
        with _f_col1:
            _f_status = st.selectbox(
                "ステータス",
                options=["すべて"] + list(INTAKE_STATUS_LABELS.values()),
                key="intake_filter_status",
            )
        with _f_col2:
            _f_source_labels = {"すべて": None, "手動": "manual", "Googleフォーム": "google_form",
                                 "LINE": "line", "API": "api", "CSVインポート": "csv_import"}
            _f_source_label = st.selectbox(
                "受付ソース",
                options=list(_f_source_labels.keys()),
                key="intake_filter_source",
            )
        with _f_col3:
            _f_plan = st.selectbox(
                "希望プラン",
                options=["すべて", "free_preview", "data_sheet", "full_report", "comparison", "undecided"],
                key="intake_filter_plan",
            )
        _f_col4, _f_col5 = st.columns(2)
        with _f_col4:
            _f_consent_ng = st.checkbox("同意未完了のみ", key="intake_filter_consent")
        with _f_col5:
            _f_not_converted = st.checkbox("未ジョブ化のみ", key="intake_filter_converted")

    # ステータスラベル → 内部値
    _status_label_to_key = {v: k for k, v in INTAKE_STATUS_LABELS.items()}
    _filter_status_key = _status_label_to_key.get(_f_status)
    _filter_source_key = _f_source_labels.get(_f_source_label)

    _all_intakes = list_intakes(status=_filter_status_key, source=_filter_source_key)

    # 追加フィルタ
    if _f_plan != "すべて":
        _all_intakes = [i for i in _all_intakes if i.get("desired_plan") == _f_plan]
    if _f_consent_ng:
        _all_intakes = [i for i in _all_intakes if not check_all_consents(i)]
    if _f_not_converted:
        _all_intakes = [i for i in _all_intakes if not i.get("converted_job_id")]

    st.caption(f"**{len(_all_intakes)} 件**の受付が見つかりました。")

    # ── 新規受付登録ボタン ──────────────────────────────────────────────────
    if st.button("➕ 新規受付を手動登録", key="intake_manual_create"):
        _new_intake = create_intake(source="manual")
        st.success(f"✅ 受付を作成しました: `{_new_intake['intake_id']}`")
        st.rerun()

    st.divider()

    if not _all_intakes:
        st.info("受付データがありません。Googleフォームや公式LINE、または「新規受付を手動登録」から追加してください。")
    else:
        # ── 一覧テーブル ──────────────────────────────────────────────────────
        _intake_rows = []
        for _intake in _all_intakes:
            _all_ok = check_all_consents(_intake)
            _intake_rows.append({
                "intake_id":  _intake["intake_id"],
                "受付日時":    _intake.get("created_at", "")[:16] if _intake.get("created_at") else "—",
                "ソース":      _intake.get("source", "—"),
                "名前/ニックネーム": _intake.get("name_or_nickname", "—") or "—",
                "連絡先":      "****" if _intake.get("contact") else "—",
                "希望プラン":  _intake.get("desired_plan", "—"),
                "ステータス":  INTAKE_STATUS_LABELS.get(_intake.get("status", ""), _intake.get("status", "—")),
                "動画本数":    _intake.get("video_count", "—"),
                "同意完了":    "✅" if _all_ok else "❌",
                "ジョブ化済み": "✅" if _intake.get("converted_job_id") else "—",
            })
        st.dataframe(
            pd.DataFrame(_intake_rows).drop(columns=["intake_id"]),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.subheader("受付詳細")

        # ── 受付詳細エリア ────────────────────────────────────────────────────
        for _intake in _all_intakes:
            _iid = _intake["intake_id"]
            _istat = INTAKE_STATUS_LABELS.get(_intake.get("status", ""), _intake.get("status", "—"))
            _icreated = _intake.get("created_at", "")[:16] if _intake.get("created_at") else "—"
            _iname = _intake.get("name_or_nickname", "—") or "—"
            _isrc = _intake.get("source", "—")
            _all_ok = check_all_consents(_intake)
            _miss = missing_consents(_intake)

            with st.expander(
                f"{_icreated}  |  {_iname}  [{_iid}]  ({_istat})",
                expanded=False,
            ):
                _itab1, _itab2, _itab3, _itab4, _itab5 = st.tabs(
                    ["基本情報", "競技・動画", "同意事項", "管理操作", "生データ"]
                )

                # ── 基本情報タブ ──────────────────────────────────────────────
                with _itab1:
                    _ic1, _ic2 = st.columns(2)
                    with _ic1:
                        _new_name = st.text_input(
                            "名前またはニックネーム",
                            value=_intake.get("name_or_nickname", ""),
                            key=f"intake_name_{_iid}",
                        )
                        _new_contact = st.text_input(
                            "連絡先",
                            value=_intake.get("contact", ""),
                            key=f"intake_contact_{_iid}",
                        )
                        _new_instagram = st.text_input(
                            "Instagramアカウント",
                            value=_intake.get("instagram_account", ""),
                            key=f"intake_instagram_{_iid}",
                        )
                    with _ic2:
                        _new_source = st.selectbox(
                            "受付ソース",
                            options=INTAKE_SOURCES,
                            index=INTAKE_SOURCES.index(_intake.get("source", "unknown")) if _intake.get("source") in INTAKE_SOURCES else 0,
                            key=f"intake_source_{_iid}",
                        )
                        _new_desired_plan = st.selectbox(
                            "希望プラン",
                            options=["free_preview", "data_sheet", "full_report", "comparison", "undecided"],
                            index=["free_preview", "data_sheet", "full_report", "comparison", "undecided"].index(
                                _intake.get("desired_plan", "free_preview")
                            ) if _intake.get("desired_plan") in ["free_preview", "data_sheet", "full_report", "comparison", "undecided"] else 0,
                            key=f"intake_plan_{_iid}",
                        )
                        _sns_opts = ["unknown", "allowed", "anonymous", "denied"]
                        _sns_labels = {"unknown": "⚠️ 未確認", "allowed": "✅ 許可", "anonymous": "🙈 匿名のみ許可", "denied": "❌ 不可"}
                        _new_sns = st.selectbox(
                            "SNS掲載許可",
                            options=_sns_opts,
                            format_func=lambda x: _sns_labels[x],
                            index=_sns_opts.index(_intake.get("sns_permission_status", "unknown")) if _intake.get("sns_permission_status") in _sns_opts else 0,
                            key=f"intake_sns_{_iid}",
                        )
                    _new_main_req = st.text_area(
                        "主な相談内容",
                        value=_intake.get("main_request", ""),
                        height=100,
                        key=f"intake_main_req_{_iid}",
                    )
                    _new_admin_note = st.text_area(
                        "管理者メモ",
                        value=_intake.get("admin_note", ""),
                        height=80,
                        key=f"intake_admin_note_{_iid}",
                    )
                    if st.button("💾 基本情報を保存", key=f"intake_save_basic_{_iid}"):
                        update_intake(
                            _iid,
                            name_or_nickname=_new_name,
                            contact=_new_contact,
                            instagram_account=_new_instagram,
                            source=_new_source,
                            desired_plan=_new_desired_plan,
                            sns_permission_status=_new_sns,
                            main_request=_new_main_req,
                            admin_note=_new_admin_note,
                        )
                        st.success("保存しました。")
                        st.rerun()

                # ── 競技・動画タブ ────────────────────────────────────────────
                with _itab2:
                    _icc1, _icc2 = st.columns(2)
                    with _icc1:
                        _new_age_group = st.text_input(
                            "年齢区分",
                            value=_intake.get("age_group", ""),
                            key=f"intake_age_{_iid}",
                            placeholder="中学生 / 高校生 / 大学生 / 社会人 / マスターズ",
                        )
                        _new_dominant_arm = st.selectbox(
                            "利き腕",
                            options=["unknown", "right", "left"],
                            format_func=lambda x: {"unknown": "不明", "right": "右腕", "left": "左腕"}[x],
                            index=["unknown", "right", "left"].index(_intake.get("dominant_arm", "unknown")) if _intake.get("dominant_arm") in ["unknown", "right", "left"] else 0,
                            key=f"intake_arm_{_iid}",
                        )
                        _new_height_cm = st.number_input(
                            "身長 (cm)",
                            value=float(_intake.get("height_cm") or 0),
                            min_value=0.0,
                            max_value=250.0,
                            step=0.5,
                            key=f"intake_height_{_iid}",
                        )
                        _new_pb = st.text_input(
                            "自己ベスト",
                            value=_intake.get("personal_best", ""),
                            key=f"intake_pb_{_iid}",
                        )
                    with _icc2:
                        _new_video_count = st.number_input(
                            "動画本数",
                            value=int(_intake.get("video_count") or 1),
                            min_value=1,
                            max_value=20,
                            step=1,
                            key=f"intake_vcount_{_iid}",
                        )
                        _angle_opts = ["unknown", "side", "diagonal_back", "front", "other"]
                        _angle_labels = {"unknown": "不明", "side": "側面", "diagonal_back": "斜め後方", "front": "正面", "other": "その他"}
                        _new_angle = st.selectbox(
                            "撮影角度",
                            options=_angle_opts,
                            format_func=lambda x: _angle_labels[x],
                            index=_angle_opts.index(_intake.get("shooting_angle", "unknown")) if _intake.get("shooting_angle") in _angle_opts else 0,
                            key=f"intake_angle_{_iid}",
                        )
                        _new_is_slow = st.checkbox(
                            "スローモーション",
                            value=_intake.get("is_slow_motion", False),
                            key=f"intake_slow_{_iid}",
                        )
                    _new_video_type = st.text_input(
                        "動画種別",
                        value=_intake.get("video_type", ""),
                        key=f"intake_vtype_{_iid}",
                        placeholder="全助走 / 投げのみ / 部分練習 / その他",
                    )
                    if st.button("💾 競技・動画情報を保存", key=f"intake_save_sport_{_iid}"):
                        update_intake(
                            _iid,
                            age_group=_new_age_group,
                            dominant_arm=_new_dominant_arm,
                            height_cm=_new_height_cm if _new_height_cm > 0 else None,
                            personal_best=_new_pb,
                            video_count=_new_video_count,
                            shooting_angle=_new_angle,
                            is_slow_motion=_new_is_slow,
                            video_type=_new_video_type,
                        )
                        st.success("保存しました。")
                        st.rerun()

                # ── 同意事項タブ ──────────────────────────────────────────────
                with _itab3:
                    if _all_ok:
                        st.success("✅ すべての同意事項が確認済みです。")
                    else:
                        st.warning(f"⚠️ {len(_miss)} 件の同意事項が未確認です。")
                    _consent_vals: dict = {}
                    for _ckey, _clabel in CONSENT_LABELS.items():
                        _consent_vals[_ckey] = st.checkbox(
                            _clabel,
                            value=_intake.get(_ckey, False),
                            key=f"intake_{_ckey}_{_iid}",
                        )
                    if st.button("💾 同意事項を保存", key=f"intake_save_consent_{_iid}"):
                        update_intake(_iid, **_consent_vals)
                        st.success("保存しました。")
                        st.rerun()

                # ── 管理操作タブ ──────────────────────────────────────────────
                with _itab4:
                    # ステータス変更
                    _cur_status = _intake.get("status", "received")
                    _new_status_label = st.selectbox(
                        "ステータス",
                        options=[INTAKE_STATUS_LABELS.get(s, s) for s in INTAKE_STATUSES],
                        index=INTAKE_STATUSES.index(_cur_status) if _cur_status in INTAKE_STATUSES else 0,
                        key=f"intake_status_sel_{_iid}",
                    )
                    _new_status_key = {v: k for k, v in INTAKE_STATUS_LABELS.items()}.get(_new_status_label, _cur_status)
                    if st.button("💾 ステータスを更新", key=f"intake_status_save_{_iid}"):
                        set_intake_status(_iid, _new_status_key)
                        st.success("ステータスを更新しました。")
                        st.rerun()

                    st.divider()

                    # 納品URL送信文
                    _cur_job_for_delivery_url = ""
                    if _intake.get("converted_job_id"):
                        try:
                            _cj = load_job(_intake["converted_job_id"])
                            _cur_job_for_delivery_url = get_job_s3_status(_cj).get("delivery_page_url") or ""
                        except Exception:
                            pass
                    if _cur_job_for_delivery_url:
                        st.markdown("**📱 納品URL送信文:**")
                        _delivery_tmpl = (
                            f"このたびは動画解析サービスをご利用いただきありがとうございます。\n\n"
                            f"解析結果はこちらからご確認ください。\n\n"
                            f"{_cur_job_for_delivery_url}\n\n"
                            "まずは「最初に読んでください」を開いてから、解析動画とPDFをご確認ください。\n\n"
                            "URLには有効期限があります。\n"
                            "期限切れの場合は再発行しますのでご連絡ください。\n\n"
                            "本解析は、動画から取得した姿勢推定データをもとにした参考資料です。\n"
                            "競技指導、医療判断、怪我の診断を代替するものではありません。"
                        )
                        st.text_area(
                            "納品URL送信文",
                            value=_delivery_tmpl,
                            height=200,
                            key=f"intake_delivery_msg_{_iid}",
                            label_visibility="collapsed",
                        )

                    # 受付完了メッセージ
                    st.markdown("**📩 受付完了メッセージ:**")
                    _receipt_tmpl = (
                        "動画解析サービスへのお申し込みありがとうございます。\n\n"
                        "受付内容を確認後、順番に解析を進めます。\n"
                        "動画の画質・撮影角度・内容によっては、追加確認をお願いする場合があります。\n\n"
                        "本解析は参考資料であり、医療診断や専門的な競技指導を代替するものではありません。\n\n"
                        "納品まで少々お時間をいただく場合があります。\n"
                        "あらかじめご了承ください。"
                    )
                    st.text_area(
                        "受付完了メッセージ",
                        value=_receipt_tmpl,
                        height=160,
                        key=f"intake_receipt_msg_{_iid}",
                        label_visibility="collapsed",
                    )

                    st.divider()

                    # ジョブ化ボタン
                    if _intake.get("converted_job_id"):
                        st.info(f"✅ ジョブ化済み: `{_intake['converted_job_id']}`")
                        if st.button("⚠️ 再ジョブ化（強制）", key=f"intake_reconvert_{_iid}"):
                            try:
                                _conv_res = convert_intake_to_job(_iid, _jm_module, force=True)
                                st.success(f"✅ 新規ジョブを作成しました: `{_conv_res['job']['job_id']}`")
                                st.rerun()
                            except Exception as _ce:
                                st.error(f"❌ エラー: {_ce}")
                    else:
                        _consent_warn = not _all_ok
                        if _consent_warn:
                            st.warning(
                                f"⚠️ 同意未確認項目が {len(_miss)} 件あります: "
                                + "、".join(CONSENT_LABELS.get(k, k) for k in _miss[:3])
                                + ("..." if len(_miss) > 3 else "")
                            )
                        if st.button(
                            "🚀 ジョブを作成する" + ("（同意未完了）" if _consent_warn else ""),
                            key=f"intake_convert_{_iid}",
                            type="secondary" if _consent_warn else "primary",
                        ):
                            try:
                                _conv_res = convert_intake_to_job(_iid, _jm_module, force=False)
                                st.success(f"✅ ジョブを作成しました: `{_conv_res['job']['job_id']}`")
                                st.info("「📋 ジョブ履歴」タブでジョブを確認してください。")
                                st.rerun()
                            except ValueError as _ve:
                                st.error(f"❌ {_ve}")
                            except Exception as _ce:
                                st.error(f"❌ エラー: {_ce}")

                    st.divider()

                    _op_col1, _op_col2 = st.columns(2)
                    with _op_col1:
                        if st.button("📦 アーカイブ", key=f"intake_archive_{_iid}"):
                            archive_intake(_iid)
                            st.success("アーカイブしました。")
                            st.rerun()
                    with _op_col2:
                        if st.button("❌ 対応不可", key=f"intake_reject_{_iid}"):
                            reject_intake(_iid)
                            st.success("対応不可にしました。")
                            st.rerun()

                # ── 生データタブ ──────────────────────────────────────────────
                with _itab5:
                    _raw = _intake.get("raw_payload", {})
                    if _raw:
                        st.json(_raw)
                    else:
                        st.caption("raw_payload は空です。")
                    st.divider()
                    st.caption("intake.json 全体:")
                    # 個人情報フィールドをマスク表示
                    _masked = {
                        k: ("****" if k in ("name_or_nickname", "contact", "line_user_id", "email", "instagram_account") and v else v)
                        for k, v in _intake.items()
                    }
                    st.json(_masked)


# ─── Tab 7: キュー管理 ─────────────────────────────────────────────────────────

with tab_queue:
    st.header("⚙️ キュー管理")

    if not _QUEUE_AVAILABLE:
        st.error("`src/queue_manager.py` が読み込めません。Phase 7 モジュールが見つかりません。")
        st.stop()

    # ── 件数サマリー ────────────────────────────────────────────────────────────
    _counts = get_queue_counts()
    _cnt_cols = st.columns(5)
    for _ci, _cs in enumerate(["pending", "running", "completed", "failed", "cancelled"]):
        _cnt_cols[_ci].metric(QUEUE_STATUS_LABELS.get(_cs, _cs), _counts.get(_cs, 0))

    st.divider()

    # ── キュー投入フォーム ──────────────────────────────────────────────────────
    with st.expander("➕ ジョブをキューに投入"):
        _enq_job_id = st.text_input("ジョブID", key="queue_enqueue_job_id")
        _enq_type = st.selectbox("処理タイプ", JOB_TYPES, key="queue_enqueue_type")
        if st.button("🚀 キューに投入", key="queue_enqueue_btn"):
            if _enq_job_id:
                try:
                    _qjob = create_queue_job(_enq_job_id, job_type=_enq_type, source="manual")
                    st.success(f"✅ キューに投入しました: `{_qjob['queue_id']}`")
                    st.rerun()
                except Exception as _qe:
                    st.error(f"❌ エラー: {_qe}")
            else:
                st.warning("ジョブIDを入力してください。")

    # ── キュー一覧 ──────────────────────────────────────────────────────────────
    for _qs in ["running", "pending", "failed", "cancelled", "completed"]:
        _qjobs = list_queue_jobs(status=_qs)
        if not _qjobs:
            continue
        st.subheader(f"{QUEUE_STATUS_LABELS.get(_qs, _qs)} ({len(_qjobs)}件)")
        for _qjob in _qjobs[:20]:
            _qid = _qjob.get("queue_id", "?")
            _jid = _qjob.get("job_id", "?")
            _step = _qjob.get("current_step", "—")
            with st.expander(f"{_qid} | job: {_jid} | step: {_step}"):
                st.json({k: v for k, v in _qjob.items() if k != "steps"})
                if _qjob.get("status") in ("pending", "running"):
                    if st.button("❌ キャンセル", key=f"cancel_{_qid}"):
                        try:
                            cancel_queue_job(_qid)
                            st.success("キャンセルしました。")
                            st.rerun()
                        except Exception as _ce:
                            st.error(f"エラー: {_ce}")
                if _qjob.get("status") in ("failed", "cancelled"):
                    if st.button("🔄 リトライ", key=f"retry_{_qid}"):
                        try:
                            retry_queue_job(_qid)
                            st.success("リトライキューに追加しました。")
                            st.rerun()
                        except Exception as _re:
                            st.error(f"エラー: {_re}")
                if _qjob.get("steps"):
                    with st.expander("ステップ詳細"):
                        st.json(_qjob["steps"])

    st.divider()
    st.markdown("**ワーカー起動方法:**")
    st.code(
        "# 1件だけ処理（テスト用）\npython worker.py --once\n\n"
        "# 継続ポーリング（本番用）\npython worker.py --poll-interval 5\n\n"
        "# 最大5件処理して終了\npython worker.py --max-jobs 5",
        language="bash",
    )
