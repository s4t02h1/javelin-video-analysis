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
    get_job_dir,
    list_jobs,
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
    """解析をサブプロセスで同期実行し、job.json のステータスを更新する。"""
    job = update_job(job_id, status="running")
    cmd = _build_cmd(job)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(_REPO_ROOT),
        )
        if result.returncode == 0:
            output_files = collect_output_files(job_id)
            update_job(job_id, status="completed", output_files=output_files, error=None)
        else:
            err = (result.stderr or result.stdout or "Unknown error").strip()
            update_job(job_id, status="failed", error=err[:2000])
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))


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

    return result


# ── ページ設定 ─────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Javelin 管理画面",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 Javelin Video Analysis — 管理画面")

tab_new, tab_history = st.tabs(["▶ 新規ジョブ", "📋 ジョブ履歴"])


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
                        st.markdown("**📄 CSVデータシート**")
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
            # F. 納品用ZIPパッケージ
            # ══════════════════════════════════════════════════════════════════
            with st.expander("📦 F. 納品用ZIPパッケージ", expanded=False):
                st.caption("3種類の納品用ZIPを生成・ダウンロードできます。")
                _deliv_dir = _job_dir / "deliverables"
                _zip_specs = [
                    (
                        "free_preview.zip",
                        "🆓 Free Preview",
                        "解析動画 + 代表フレーム先頭3枚",
                    ),
                    (
                        "data_sheet_package.zip",
                        "📊 Data Sheet Package",
                        "pose_landmarks.csv + グラフ画像 + 全代表フレーム",
                    ),
                    (
                        "full_report_package.zip",
                        "📦 Full Report Package",
                        "report.pdf + CSV + グラフ + フレーム + 全解析動画",
                    ),
                ]

                _gz_col, _ = st.columns([2, 3])
                with _gz_col:
                    if st.button("🗜️ ZIPを全て生成", key=f"gen_zip_{job['job_id']}"):
                        with st.spinner("ZIP を生成中..."):
                            try:
                                from src.deliverable_packager import (
                                    create_deliverable_packages_for_job,
                                )
                                _zips = create_deliverable_packages_for_job(_job_dir)
                                st.success(f"生成完了: {len(_zips)} 件")
                                st.rerun()
                            except Exception as _ze:
                                st.error(f"ZIP 生成エラー: {_ze}")

                st.markdown("---")
                for _zname, _zlabel, _zdesc in _zip_specs:
                    _zp = _deliv_dir / _zname
                    _zc1, _zc2 = st.columns([3, 2])
                    with _zc1:
                        st.markdown(f"**{_zlabel}**  —  `{_zname}`")
                        st.caption(_zdesc)
                        if _zp.exists():
                            _zk = _zp.stat().st_size // 1024
                            _zm = datetime.fromtimestamp(
                                _zp.stat().st_mtime
                            ).strftime("%Y-%m-%d %H:%M")
                            st.caption(f"{_zk:,} KB  /  生成: {_zm}")
                        else:
                            st.caption("Not generated yet.")
                    with _zc2:
                        if _zp.exists():
                            try:
                                st.download_button(
                                    label=f"⬇ {_zname}",
                                    data=_zp.read_bytes(),
                                    file_name=_zname,
                                    mime="application/zip",
                                    key=f"dl_zip_{_zname}_{job['job_id']}",
                                )
                            except OSError:
                                st.warning("ZIPファイルを読み込めませんでした。")
