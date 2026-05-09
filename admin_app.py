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
    collect_output_files,
    create_job,
    get_customer_info,
    get_job_dir,
    list_jobs,
    update_customer_info,
    update_job,
)

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
    "created":   "🆕",
    "running":   "⏳",
    "completed": "✅",
    "failed":    "❌",
}


# ── ヘルパー関数 ───────────────────────────────────────────────────────────────

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

    Returns
    -------
    str
        コピペ用の納品メッセージ文。
    """
    name: str   = customer_info.get("customer_name") or ""
    event: str  = customer_info.get("event") or "javelin"
    plan: str   = customer_info.get("plan") or "free_preview"
    paid: str   = customer_info.get("payment_status") or "unpaid"
    social: str = customer_info.get("permission_for_social_post") or "unknown"
    arm: str    = customer_info.get("dominant_arm") or customer_info.get("dominant_hand") or "unknown"
    angle: str  = customer_info.get("filming_angle") or customer_info.get("camera_angle") or "unknown"

    greeting = f"{name}様、お待たせいたしました！" if name else "お待たせいたしました！"

    # SNS掲載許可の補足
    _social_note = ""
    if social == "yes":
        _social_note = "\nなお、解析結果をSNSの参考資料として掲載させていただく場合がございます。"
    elif social == "no":
        _social_note = "\nSNS等への掲載はいたしません。"

    if package_type == "free_preview":
        return (
            f"{greeting}\n"
            f"{event}の動画解析の無料プレビュー版が完成しました。\n"
            "\n"
            "今回の解析はフォームの良し悪しを断定するものではなく、"
            "動きの軌跡やタイミングを見返しやすくするための可視化資料です。\n"
            "\n"
            "必要であれば、CSVデータ・グラフ・PDFレポートを含む詳細版も作成できます。"
            f"お気軽にお申し付けください。{_social_note}"
        )

    elif package_type == "data_sheet":
        _payment_note = ""
        if paid == "unpaid":
            _payment_note = "\n\n※ お支払いがまだの場合は、お支払い方法をご確認の上ご連絡ください。"
        elif paid == "paid":
            _payment_note = "\n\nお支払いの確認が取れております。ありがとうございます。"
        return (
            f"{greeting}\n"
            f"{event}の右手首の高さ変化、腕の軌道、代表フレーム、"
            "CSVデータをまとめた「有料データシート版」が完成しました。\n"
            "\n"
            "練習の振り返りや指導者との共有に使いやすい内容です。\n"
            "\n"
            f"フルレポート（PDF＋全動画）もご希望の場合はお申し付けください。{_payment_note}{_social_note}"
        )

    elif package_type == "full_report":
        _payment_note = ""
        if paid == "unpaid":
            _payment_note = "\n\n※ お支払いがまだの場合は、お支払い方法をご確認の上ご連絡ください。"
        elif paid == "paid":
            _payment_note = "\n\nお支払いの確認が取れております。ありがとうございます。"
        return (
            f"{greeting}\n"
            f"{event}の「有料フルレポート版」が完成しました。\n"
            "\n"
            "PDFレポート、解析動画、CSV、グラフ、代表フレームをまとめたフルセットです。\n"
            "\n"
            f"あくまで参考資料として、今後の練習の振り返りにご活用ください。{_payment_note}{_social_note}"
        )

    else:
        return f"package_type '{package_type}' は未定義です。"


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


tab_new, tab_history, tab_compare, tab_checklist = st.tabs(
    ["▶ 新規ジョブ", "📋 ジョブ履歴", "⚖️ ジョブ比較", "✅ 運用チェックリスト"]
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

    if st.button("🔄 更新"):
        st.rerun()

    jobs = list_jobs()

    if not jobs:
        st.info("ジョブがまだありません。「新規ジョブ」タブから解析を開始してください。")
    else:
        # サマリーテーブル
        rows = [
            {
                "ジョブID":  j["job_id"],
                "状態":      STATUS_ICONS.get(j["status"], "?") + " " + j["status"],
                "モード":    MODE_LABELS.get(j.get("mode", ""), j.get("mode", "")),
                "身長(m)":   str(j["height_m"]) if j.get("height_m") else "—",
                "作成日時":  j.get("created_at", ""),
                "出力数":    len(j.get("output_files", [])),
            }
            for j in jobs
        ]
        st.dataframe(rows, width="stretch", hide_index=True)

        # ジョブ選択
        selected_id = st.selectbox(
            "詳細を表示するジョブを選択",
            options=[j["job_id"] for j in jobs],
        )

        if selected_id:
            job = next(j for j in jobs if j["job_id"] == selected_id)

            st.divider()
            st.subheader(f"ジョブ詳細: `{selected_id}`")

            _job_dir = get_job_dir(selected_id)
            _all_files = job.get("output_files") or collect_output_files(job["job_id"])
            _cls = _classify_job_files(_job_dir, _all_files)

            # ══════════════════════════════════════════════════════════════════
            # A. Job Summary
            # ══════════════════════════════════════════════════════════════════
            st.markdown("#### 🗂️ A. Job Summary")
            _inp_p = Path(job.get("input_file", ""))
            _summary_pairs = [
                ("Job ID",      job.get("job_id", "—")),
                ("Status",      STATUS_ICONS.get(job["status"], "") + " " + job.get("status", "—")),
                ("Created at",  job.get("created_at", "—")),
                ("Updated at",  job.get("updated_at", "—")),
                ("Height (m)",  str(job.get("height_m", "—"))),
                ("Mode",        job.get("mode", "—")),
                ("Input video", _inp_p.name if _inp_p.name else "—"),
            ]
            _sa_col, _sb_col = st.columns([1, 2])
            with _sa_col:
                for _k, _ in _summary_pairs:
                    st.markdown(f"**{_k}**")
            with _sb_col:
                for _, _v in _summary_pairs:
                    st.markdown(_v)

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

            # ══════════════════════════════════════════════════════════════════            # I. 解析ログ
            # ══════════════════════════════════════════════════════════════
            _is_failed = job.get("status") == "failed"
            with st.expander(
                "🗒️ I. 解析ログ",
                expanded=_is_failed,   # 失敗時は自動展開
            ):
                _logs_dir = _job_dir / "logs"

                # ─ 失敗時の簡易チェックリスト ───────────────────────────────────────────────
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

            # ══════════════════════════════════════════════════════════════            # G. Customer Info（顧客情報）
            # ══════════════════════════════════════════════════════════════════
            with st.expander("👤 G. 顧客情報 / Customer Info", expanded=True):
                try:
                    _ci = get_customer_info(selected_id)
                except Exception as _ci_err:
                    st.warning(f"⚠️ customer_info.json の読み込みに失敗しました: {_ci_err}")
                    _ci = {}
                with st.form(key=f"ci_form_{selected_id}"):
                    # ── 行1: 基本情報 ──
                    _ci_c1, _ci_c2, _ci_c3 = st.columns(3)
                    with _ci_c1:
                        _ci_name = st.text_input(
                            "顧客名", value=_ci.get("customer_name", "")
                        )
                        _ci_ig = st.text_input(
                            "Instagram ID", value=_ci.get("instagram_id", "")
                        )
                        _ci_event = st.text_input(
                            "種目", value=_ci.get("event", "javelin")
                        )
                    with _ci_c2:
                        _arm_opts = ["right", "left", "unknown"]
                        _arm_labels = {"right": "右 (right)", "left": "左 (left)", "unknown": "不明 (unknown)"}
                        _ci_arm_val = _ci.get("dominant_arm") or _ci.get("dominant_hand", "unknown")
                        _ci_arm = st.selectbox(
                            "利き腕 (dominant_arm)",
                            options=_arm_opts,
                            format_func=lambda x: _arm_labels[x],
                            index=_arm_opts.index(_ci_arm_val if _ci_arm_val in _arm_opts else "unknown"),
                        )
                        _ci_height = st.number_input(
                            "身長 (m)",
                            min_value=0.0,
                            max_value=2.5,
                            value=float(_ci.get("height_m") or 0.0),
                            step=0.01,
                            format="%.2f",
                            help="0.00 は未設定扱いです",
                        )
                        _angle_opts = ["side", "back", "front", "diagonal", "unknown"]
                        _angle_labels = {
                            "side": "側面 (side)", "back": "後方 (back)",
                            "front": "正面 (front)", "diagonal": "斜め (diagonal)",
                            "unknown": "不明 (unknown)",
                        }
                        _ci_angle_val = _ci.get("filming_angle") or _ci.get("camera_angle", "unknown")
                        _ci_angle = st.selectbox(
                            "撮影方向 (filming_angle)",
                            options=_angle_opts,
                            format_func=lambda x: _angle_labels[x],
                            index=_angle_opts.index(_ci_angle_val if _ci_angle_val in _angle_opts else "unknown"),
                        )
                    with _ci_c3:
                        _social_opts = ["yes", "no", "unknown"]
                        _social_labels = {"yes": "許可 (yes)", "no": "不許可 (no)", "unknown": "未確認 (unknown)"}
                        _ci_social_val = _ci.get("permission_for_social_post", "unknown")
                        _ci_social = st.selectbox(
                            "SNS掲載許可",
                            options=_social_opts,
                            format_func=lambda x: _social_labels[x],
                            index=_social_opts.index(_ci_social_val if _ci_social_val in _social_opts else "unknown"),
                        )
                        _plan_opts = ["free_preview", "data_sheet", "full_report"]
                        _plan_labels = {
                            "free_preview": "無料プレビュー",
                            "data_sheet":   "データシート",
                            "full_report":  "フルレポート",
                        }
                        _ci_plan_val = _ci.get("plan", "free_preview")
                        _ci_plan = st.selectbox(
                            "プラン (plan)",
                            options=_plan_opts,
                            format_func=lambda x: _plan_labels[x],
                            index=_plan_opts.index(_ci_plan_val if _ci_plan_val in _plan_opts else "free_preview"),
                        )
                        _pstatus_opts = ["unpaid", "paid", "free"]
                        _pstatus_labels = {"unpaid": "未払い (unpaid)", "paid": "支払済み (paid)", "free": "無料 (free)"}
                        _ci_pstatus_val = _ci.get("payment_status", "unpaid")
                        _ci_pstatus = st.selectbox(
                            "支払いステータス (payment_status)",
                            options=_pstatus_opts,
                            format_func=lambda x: _pstatus_labels[x],
                            index=_pstatus_opts.index(_ci_pstatus_val if _ci_pstatus_val in _pstatus_opts else "unpaid"),
                        )
                    # ── 行2: 納品ステータス ──
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
                    # ── 行3: メモ ──
                    _note_c1, _note_c2 = st.columns(2)
                    with _note_c1:
                        _ci_notes = st.text_area(
                            "メモ (notes)",
                            value=_ci.get("notes", "") or _ci.get("request_note", ""),
                            height=100,
                            help="相談内容・要望など自由記述",
                        )
                    with _note_c2:
                        _ci_coach = st.text_area(
                            "💬 コーチコメント (PDFに掲載)",
                            value=_ci.get("coach_comment", ""),
                            height=100,
                            help="英数字・記号はPDFにそのまま表示されます。日本語は現在 '?' に置換されます（フォント対応中）。",
                        )
                    _ci_save = st.form_submit_button("💾 顧客情報を保存", type="primary")
                    if _ci_save:
                        update_customer_info(
                            selected_id,
                            customer_name=_ci_name,
                            instagram_id=_ci_ig,
                            event=_ci_event,
                            dominant_arm=_ci_arm,
                            dominant_hand=_ci_arm,   # 旧フィールドも同期
                            height_m=_ci_height if _ci_height > 0 else None,
                            filming_angle=_ci_angle,
                            camera_angle=_ci_angle,  # 旧フィールドも同期
                            permission_for_social_post=_ci_social,
                            plan=_ci_plan,
                            payment_status=_ci_pstatus,
                            delivery_status=_ci_dstatus,
                            notes=_ci_notes,
                            request_note=_ci_notes,  # 旧フィールドも同期
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
                                        data=_fp.read_bytes(),
                                        file_name=_fp.name, mime="image/jpeg",
                                        key=f"dl_fr_{_fp.name}_{job['job_id']}",
                                    )
                                except OSError:
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
                                    data=_cp.read_bytes(), file_name=_cp.name,
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
                                        data=_gp.read_bytes(),
                                        file_name=_gp.name, mime="image/png",
                                        key=f"dl_gr_{_gp.name}_{job['job_id']}",
                                    )
                                except OSError:
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
                                data=_pdf_p.read_bytes(),
                                file_name="report.pdf",
                                mime="application/pdf",
                                key=f"dl_pdf_{job['job_id']}",
                            )
                            st.caption(f"生成日時: {_mtime}  /  {_size_kb} KB")
                        except OSError:
                            st.warning("PDF ファイルを読み込めませんでした。")
                    else:
                        st.info("Not generated yet.")
                with _dc2:
                    if st.button("🔄 PDF を再生成", key=f"gen_pdf_{job['job_id']}"):
                        with st.spinner("PDF を生成中..."):
                            try:
                                from src.pdf_report_generator import generate_pdf_report_for_job
                                _new_pdf = generate_pdf_report_for_job(_job_dir)
                                st.success(f"生成完了: {_new_pdf.name}")
                                st.rerun()
                            except Exception as _pe:
                                st.error(f"PDF 生成エラー: {_pe}")

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
                                data=_instr_p.read_bytes(),
                                file_name="video_instruction.pdf",
                                mime="application/pdf",
                                key=f"dl_instr_pdf_{job['job_id']}",
                            )
                            st.caption(f"生成日時: {_instr_mtime}  /  {_instr_kb} KB")
                        except OSError:
                            st.warning("説明書PDFファイルを読み込めませんでした。")
                    else:
                        st.info("Not generated yet.")
                with _d2c2:
                    if st.button("🔄 説明書PDFを生成・再生成", key=f"gen_instr_pdf_{job['job_id']}"):
                        with st.spinner("説明書PDF を生成中..."):
                            try:
                                from src.video_instruction_pdf_generator import (
                                    generate_video_instruction_pdf_for_job,
                                )
                                _new_instr = generate_video_instruction_pdf_for_job(_job_dir)
                                st.success(f"生成完了: {_new_instr.name}")
                                st.rerun()
                            except Exception as _ipe:
                                st.error(f"説明書PDF 生成エラー: {_ipe}")

            # ══════════════════════════════════════════════════════════════════
            # K. User-friendly Reports（アスリート向け成果物）
            # ══════════════════════════════════════════════════════════════════
            with st.expander("📋 K. User-friendly Reports（アスリート向け）", expanded=True):
                st.caption("選手・コーチが直接使える PDF 成果物です。")

                _ufr_items = [
                    (
                        "athlete_pdf_path",
                        "athlete_data_sheet.pdf",
                        "🏃 アスリートデータシート",
                        "主要指標をまとめた選手向けサマリーPDF",
                        "gen_athlete_pdf",
                        "src.athlete_data_sheet_generator",
                        "generate_athlete_data_sheet_for_job",
                    ),
                    (
                        "key_frame_pdf_path",
                        "key_frame_sheet.pdf",
                        "🖼 キーフレームシート",
                        "フェーズ別代表フレーム一覧PDF",
                        "gen_key_frame_pdf",
                        "src.key_frame_sheet_generator",
                        "generate_key_frame_sheet_for_job",
                    ),
                    (
                        "graph_pack_pdf_path",
                        "graph_pack.pdf",
                        "📈 グラフパック",
                        "解析グラフを解説付きでまとめたPDF",
                        "gen_graph_pack_pdf",
                        "src.graph_pack_generator",
                        "generate_graph_pack_for_job",
                    ),
                    (
                        "coach_review_pdf_path",
                        "coach_review_sheet.pdf",
                        "📝 コーチレビューシート",
                        "フェーズ別チェックリスト＆記入欄PDF",
                        "gen_coach_review_pdf",
                        "src.coach_review_sheet_generator",
                        "generate_coach_review_sheet_for_job",
                    ),
                ]

                for (_cls_key, _fname, _label, _caption, _btn_key,
                     _mod_name, _fn_name) in _ufr_items:
                    st.markdown(f"**{_label}**")
                    st.caption(_caption)
                    _ufr_p = _cls.get(_cls_key)
                    _k1, _k2 = st.columns([3, 2])
                    with _k1:
                        if _ufr_p and _ufr_p.exists():
                            try:
                                _ufr_mt = datetime.fromtimestamp(
                                    _ufr_p.stat().st_mtime
                                ).strftime("%Y-%m-%d %H:%M:%S")
                                _ufr_kb = _ufr_p.stat().st_size // 1024
                                st.download_button(
                                    label=f"⬇ {_fname} をダウンロード",
                                    data=_ufr_p.read_bytes(),
                                    file_name=_fname,
                                    mime="application/pdf",
                                    key=f"dl_{_btn_key}_{job['job_id']}",
                                )
                                st.caption(f"生成日時: {_ufr_mt}  /  {_ufr_kb} KB")
                            except OSError:
                                st.warning(f"{_fname} を読み込めませんでした。")
                        else:
                            st.info("未生成 / Not generated yet.")
                    with _k2:
                        if st.button(
                            f"🔄 生成・再生成",
                            key=f"btn_{_btn_key}_{job['job_id']}",
                        ):
                            with st.spinner(f"{_fname} を生成中..."):
                                try:
                                    import importlib
                                    _mod = importlib.import_module(_mod_name)
                                    _fn  = getattr(_mod, _fn_name)
                                    _new = _fn(_job_dir)
                                    st.success(f"生成完了: {_new.name}")
                                    st.rerun()
                                except Exception as _ke:
                                    st.error(f"生成エラー: {_ke}")
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
                            label=f"⬇ {_fp.name}", data=_fp.read_bytes(),
                            file_name=_fp.name,
                            key=f"dl_adm_{_fp.name}_{job['job_id']}",
                        )
                    except OSError:
                        pass

                # 未分類ファイル
                if _cls["other_files"]:
                    st.markdown("**その他のファイル**")
                    for _fp in _cls["other_files"]:
                        if not _fp.exists():
                            continue
                        try:
                            st.download_button(
                                label=f"⬇ {_fp.name}", data=_fp.read_bytes(),
                                file_name=_fp.name,
                                key=f"dl_oth_{_fp.name}_{job['job_id']}",
                            )
                        except OSError:
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
                            try:
                                from src.analysis_summary import generate_analysis_summary_for_job
                                _sp = generate_analysis_summary_for_job(_job_dir)
                                st.success(f"✅ 生成完了: {_sp.name}")
                                st.rerun()
                            except Exception as _se:
                                st.error(f"生成エラー: {_se}")
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
                        if st.button(
                            "🔄 サマリーを再生成",
                            key=f"regen_summary_{job['job_id']}",
                            use_container_width=True,
                        ):
                            with st.spinner("再計算中..."):
                                try:
                                    from src.analysis_summary import generate_analysis_summary_for_job
                                    generate_analysis_summary_for_job(_job_dir)
                                    st.success("✅ 再生成完了")
                                    st.rerun()
                                except Exception as _se:
                                    st.error(f"エラー: {_se}")
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
                    if st.button("🗜️ ZIPを全て生成・更新", key=f"gen_zip_{job['job_id']}",
                                 use_container_width=True):
                        with st.spinner("ZIP を生成中..."):
                            try:
                                from src.deliverable_packager import (
                                    create_deliverable_packages_for_job,
                                )
                                _zips = create_deliverable_packages_for_job(_job_dir)
                                st.success(f"✅ 生成完了: {len(_zips)} 件")
                                st.rerun()
                            except Exception as _ze:
                                st.error(f"ZIP 生成エラー: {_ze}")
                with _fz_right:
                    st.caption(
                        "解析完了後に上記ボタンを押すと3種類のZIPが一括生成されます。"
                        "生成済みのZIPは各カードのダウンロードボタンから取得できます。"
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
                            "📹 解析動画（骨格・トレイル等）",
                            "🖼️ 代表フレーム画像（先頭3枚）",
                            "📖 解析動画 説明書 (video_instruction.pdf)",
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
                            "📄 pose_landmarks.csv（全フレーム座標）",
                            "📈 解析グラフ画像（3種）",
                            "🖼️ 代表フレーム画像（全枚）",
                            "📖 解析動画 説明書 (video_instruction.pdf)",
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
                            "📝 report.pdf（A4レポート）",
                            "📖 解析動画 説明書 (video_instruction.pdf)",
                            "📄 pose_landmarks.csv",
                            "📈 解析グラフ画像",
                            "🖼️ 代表フレーム画像（全枚）",
                            "📹 全解析動画",
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
                                _zk  = _zp.stat().st_size // 1024
                                _zm  = datetime.fromtimestamp(
                                    _zp.stat().st_mtime
                                ).strftime("%Y-%m-%d %H:%M")
                                st.success("✅ 生成済み")
                                st.caption(f"`{_card['filename']}`")
                                st.caption(f"{_zk:,} KB  ·  生成: {_zm}")
                                st.download_button(
                                    label=f"⬇ ダウンロード",
                                    data=_zp.read_bytes(),
                                    file_name=_card["filename"],
                                    mime="application/zip",
                                    key=f"dl_zip_{_card['filename']}_{job['job_id']}",
                                    use_container_width=True,
                                )
                            except OSError:
                                st.warning("⚠️ ファイル読み込みエラー")
                        else:
                            st.info("⏳ 未生成")
                            st.caption(f"`{_card['filename']}`")
                            st.caption("「ZIPを全て生成」で作成できます。")

            # ══════════════════════════════════════════════════════════════
            # H. 納品メッセージ
            # ══════════════════════════════════════════════════════════════
            with st.expander("✉️ H. 納品メッセージ", expanded=False):
                st.caption(
                    "Instagram DM・公式LINE・メールにそのままコピペできる納品文を自動生成します。"
                )
                _hci = get_customer_info(selected_id)

                _msg_specs = [
                    (
                        "free_preview",
                        "🇦️ 無料プレビュー納品文",
                        "free_preview_msg",
                    ),
                    (
                        "data_sheet",
                        "📊 有料データシート案内文",
                        "data_sheet_msg",
                    ),
                    (
                        "full_report",
                        "📦 有料フルレポート納品文",
                        "full_report_msg",
                    ),
                ]

                for _pkg_type, _pkg_label, _ta_key in _msg_specs:
                    st.markdown(f"**{_pkg_label}**")
                    try:
                        _msg_text = build_delivery_message(
                            job=job,
                            customer_info=_hci,
                            package_type=_pkg_type,
                        )
                    except Exception as _me:
                        _msg_text = f"(メッセージ生成エラー: {_me})"
                    st.text_area(
                        label=_pkg_label,
                        value=_msg_text,
                        height=160,
                        key=f"{_ta_key}_{selected_id}",
                        label_visibility="collapsed",
                    )
                    st.divider()


# ─── Tab 3: ジョブ比較 ────────────────────────────────────────────────────────

with tab_compare:
    st.header("⚖️ ジョブ比較")
    st.caption(
        "完了済みの2つのジョブを選択し、analysis_summary.json の差分を比較します。"
        "比較前に各ジョブの「📊 J. 解析サマリー」が生成されている必要があります。"
    )

    # ── 完了済みジョブ一覧を取得 ──────────────────────────────────────────────
    _all_jobs = list_jobs()
    _done_jobs = [j for j in _all_jobs if j.get("status") == "completed"]

    if len(_done_jobs) < 2:
        st.warning(
            "比較には完了済みジョブが2つ以上必要です。"
            "先に「新規ジョブ」タブで解析を実行してください。"
        )
    else:
        # job_id → 表示ラベルのマッピング
        def _job_label(j: dict) -> str:
            ci = get_customer_info(j["job_id"])
            name = ci.get("customer_name") or ""
            ts   = j.get("created_at", j["job_id"])[:16] if j.get("created_at") else j["job_id"]
            return f"{ts}  {name}  [{j['job_id']}]" if name else f"{ts}  [{j['job_id']}]"

        _job_options   = [j["job_id"] for j in _done_jobs]
        _job_labels    = {j["job_id"]: _job_label(j) for j in _done_jobs}
        _label_to_id   = {v: k for k, v in _job_labels.items()}
        _display_opts  = [_job_labels[jid] for jid in _job_options]

        _cmp_col1, _cmp_col2 = st.columns(2)
        with _cmp_col1:
            st.markdown("**Job A（比較元）**")
            _sel_a_label = st.selectbox(
                "Job A", options=_display_opts,
                index=0,
                key="cmp_job_a",
                label_visibility="collapsed",
            )
        with _cmp_col2:
            st.markdown("**Job B（比較先）**")
            _sel_b_label = st.selectbox(
                "Job B", options=_display_opts,
                index=min(1, len(_display_opts) - 1),
                key="cmp_job_b",
                label_visibility="collapsed",
            )

        _sel_a_id = _label_to_id[_sel_a_label]
        _sel_b_id = _label_to_id[_sel_b_label]

        if _sel_a_id == _sel_b_id:
            st.warning("同じジョブが選択されています。異なるジョブを選択してください。")
        else:
            # ── 比較サマリー存在チェック ──────────────────────────────────
            _dir_a = get_job_dir(_sel_a_id)
            _dir_b = get_job_dir(_sel_b_id)
            _sum_a_exists = (_dir_a / "report" / "analysis_summary.json").exists()
            _sum_b_exists = (_dir_b / "report" / "analysis_summary.json").exists()

            if not _sum_a_exists or not _sum_b_exists:
                _missing = []
                if not _sum_a_exists:
                    _missing.append(f"Job A ({_sel_a_id})")
                if not _sum_b_exists:
                    _missing.append(f"Job B ({_sel_b_id})")
                st.warning(
                    f"以下のジョブの analysis_summary.json がありません: "
                    f"{', '.join(_missing)}  \n"
                    f"ジョブ詳細の「📊 J. 解析サマリー」から先に生成してください。"
                )

            # ── 比較実行ボタン ────────────────────────────────────────────
            if st.button(
                "⚖️ 比較を実行",
                key="run_compare",
                use_container_width=False,
                disabled=(not _sum_a_exists or not _sum_b_exists),
            ):
                with st.spinner("比較中..."):
                    try:
                        import sys as _sys
                        _sys.path.insert(0, str(_REPO_ROOT / "src"))
                        from src.compare_jobs import compare_two_jobs, save_comparison
                        _cmp_result = compare_two_jobs(_dir_a, _dir_b)
                        if _cmp_result.get("status") == "error":
                            st.error(f"比較エラー: {_cmp_result.get('error')}")
                        else:
                            _saved_path = save_comparison(
                                _cmp_result,
                                comparisons_root=JOBS_DIR / "comparisons",
                            )
                            st.session_state["last_comparison"] = _cmp_result
                            st.session_state["last_comparison_path"] = str(_saved_path)
                            st.success(f"✅ 比較完了  →  保存先: `{_saved_path}`")
                            st.rerun()
                    except Exception as _ce:
                        st.error(f"比較処理エラー: {_ce}")

        # ── 比較結果の表示 ────────────────────────────────────────────────────
        _cmp_data: dict | None = st.session_state.get("last_comparison")
        if _cmp_data and _cmp_data.get("status") == "ok":
            st.divider()
            st.subheader("比較結果")

            # ジョブ基本情報
            _ja = _cmp_data.get("job_a", {})
            _jb = _cmp_data.get("job_b", {})
            _info_cols = st.columns(2)
            with _info_cols[0]:
                st.markdown(
                    f"**Job A** — `{_ja.get('job_id', '—')}`  \n"
                    f"利き腕: {str(_ja.get('dominant_hand', '—')).capitalize()}  |  "
                    f"フレーム数: {_ja.get('total_frames', '—')}"
                )
            with _info_cols[1]:
                st.markdown(
                    f"**Job B** — `{_jb.get('job_id', '—')}`  \n"
                    f"利き腕: {str(_jb.get('dominant_hand', '—')).capitalize()}  |  "
                    f"フレーム数: {_jb.get('total_frames', '—')}"
                )

            # 差分テーブル
            _fields = _cmp_data.get("fields", {})
            _table_rows = []
            for _fkey, _fval in _fields.items():
                _diff_v = _fval.get("diff")
                if _diff_v is not None:
                    _diff_str = f"+{_diff_v}" if _diff_v > 0 else str(_diff_v)
                else:
                    _diff_str = "—"
                _table_rows.append({
                    "指標":           _fval.get("label", _fkey),
                    "Job A":          _fval.get("a") if _fval.get("a") is not None else "—",
                    "Job B":          _fval.get("b") if _fval.get("b") is not None else "—",
                    "差分 (B − A)":   _diff_str,
                })

            _df_cmp = pd.DataFrame(_table_rows)
            st.dataframe(_df_cmp, use_container_width=True, hide_index=True)

            # 保存先
            _saved_str = st.session_state.get("last_comparison_path")
            if _saved_str:
                st.caption(f"比較結果保存先: `{_saved_str}`")

            # Raw JSON
            with st.expander("🗂️ Raw JSON", expanded=False):
                st.json(_cmp_data)

    # ── 過去の比較履歴 ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("比較履歴")
    _comp_root = JOBS_DIR / "comparisons"
    if not _comp_root.exists() or not any(_comp_root.iterdir()):
        st.info("比較履歴はまだありません。")
    else:
        try:
            import sys as _sys2
            _sys2.path.insert(0, str(_REPO_ROOT / "src"))
            from src.compare_jobs import list_comparisons
            _history = list_comparisons(_comp_root)
        except Exception:
            _history = []

        if not _history:
            st.info("比較履歴の読み込みに失敗しました。")
        else:
            for _h in _history:
                _cid  = _h.get("comparison_id", "—")
                _hja  = _h.get("job_a", {})
                _hjb  = _h.get("job_b", {})
                _hgen = _h.get("generated_at", "—")
                with st.expander(
                    f"🕓 {_cid}  |  {_hja.get('job_id','?')}  vs  {_hjb.get('job_id','?')}",
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
