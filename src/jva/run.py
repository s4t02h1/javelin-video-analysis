#!/usr/bin/env python3
"""
jva.run - javelin-video-analysis メインエントリーポイント（パッケージ版）
"""

import argparse
import os
import sys
import logging
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional

# リポジトリルートを推定して src を import パスへ
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "src"))

import cv2  # type: ignore
import numpy as np  # type: ignore

from src.pipelines.pose_analysis import PoseAnalyzer
from src.data_exporter import export_pose_landmarks_csv
from src.frame_extractor import extract_representative_frames, extract_smart_frames
from src.valid_segment_detector import detect_valid_pose_segment, save_valid_segment
from src.graph_generator import generate_graphs_for_job
from src.pdf_report_generator import generate_pdf_report_for_job
from src.analysis_summary import generate_analysis_summary_for_job

try:
    from jva_visuals.registry import VisualPipeline, VisualPassRegistry
    from jva_visuals.adapters import adapt_state  # noqa: F401
    VISUALS_AVAILABLE = True
except Exception as e:
    print(f"Warning: Visual enhancements not available: {e}")
    VISUALS_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    default_config = {
        "height_m": None,
        "visuals": {},
        "output": {"export_landmarks": False},
        "blender": {"enabled": False},
        "debug": {"profile_performance": False}
    }
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f) or {}
            cfg = {**default_config}
            cfg.update(file_config)
            logger.info(f"Loaded config from: {config_path}")
            return cfg
        except Exception as e:
            logger.error(f"Failed to load config file {config_path}: {e}")
    return default_config


def override_config_with_args(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    if args.height_m:
        config["height_m"] = args.height_m
    visuals = config.get("visuals", {})
    if args.vectors:
        visuals["vectors"] = True
    if args.heatmap:
        visuals["heatmap"] = True
    if args.hud:
        visuals["hud"] = True
    if args.stickman:
        visuals["stickman"] = True
    if args.analysis:
        visuals["analysis"] = True
    if args.wrist_trail:
        visuals["wrist_trail"] = True
    if args.glow_trail:
        visuals["glow_trail"] = True
    output = config.get("output", {})
    if args.export_landmarks:
        output["export_landmarks"] = True
        output["landmarks_filename"] = args.export_landmarks
    blender = config.get("blender", {})
    if args.blender_overlay:
        blender["enabled"] = True
        blender["render_overlay"] = True
    config["visuals"] = visuals
    config["output"] = output
    config["blender"] = blender
    return config


def export_landmarks_json(landmarks_data: list, output_path: str):
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "format": "mediapipe_pose_landmarks",
                "version": "1.0",
                "frame_count": len(landmarks_data),
                "landmarks": landmarks_data
            }, f, indent=2)
        logger.info(f"Exported landmarks to: {output_path}")
    except Exception as e:
        logger.error(f"Failed to export landmarks: {e}")


def print_blender_commands(video_path: str, landmarks_path: str, output_path: str):
    blender_script = repo_root / "blender_bridge" / "scripts" / "setup_scene.py"
    commands = [
        "# Blender連携コマンド例:",
        f"blender --background --python {blender_script} -- \\",
        f"  --video {video_path} \\",
        f"  --landmarks {landmarks_path} \\", 
        f"  --output {output_path}",
        "",
        "# または既存のBlenderファイルに適用:",
        f"blender your_scene.blend --python {blender_script} -- \\",
        f"  --video {video_path} \\",
        f"  --landmarks {landmarks_path} \\",
        f"  --output {output_path}"
    ]
    print("\n" + "\n".join(commands) + "\n")


def _write_handout_html(output_dir: Path, base_name: str,
                        variants_results: list, config: Dict[str, Any],
                        input_path: str) -> None:
    """被験者向け説明書（A4 PDF）を出力する。"""
    import datetime, html as _html, io
    from xhtml2pdf import pisa
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    # ReportLab 内蔵 CJK CID フォントを使用（外部フォントファイル不要・日本語対応）
    _FONT_NORMAL = "HeiseiMin-W3"    # 明朝体（本文）
    _FONT_BOLD   = "HeiseiKakuGo-W5" # ゴシック体（見出し・太字）
    for _fn in (_FONT_NORMAL, _FONT_BOLD):
        if _fn not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(_fn))
    _font_face_css = ""  # CID フォントは @font-face 不要（pdfmetrics 登録済み）

    # 動画情報
    cap      = cv2.VideoCapture(input_path)
    fps_v    = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames_v = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w_v      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h_v      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    dur_s    = round(frames_v / fps_v, 1) if fps_v > 0 else 0
    cap.release()

    height_m  = config.get("height_m")
    generated = datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M")
    date_str  = datetime.datetime.now().strftime("%Y年%m月%d日")

    # 各バリアントの詳細説明
    VARIANT_DETAIL = {
        "骨格": {
            "subtitle": "骨格トレース＋手首軌跡",
            "desc": (
                "カメラで捉えた映像に、AIが推定した身体の骨格ライン（関節と骨の接続）を"
                "重ね合わせて表示しています。右手首の軌跡が細い線で記録されており、"
                "投擲フォームの全体的な流れを確認するのに適しています。"
            ),
            "points": [
                "青色の線と点が骨格ランドマーク",
                "手首の軌跡でリリース動作のパスを確認できる",
                "フォームの左右対称性・重心移動の把握に最適",
            ],
        },
        "ヒートマップ": {
            "subtitle": "速度ヒートマップ",
            "desc": (
                "各関節の動く速さを色で表現しています。"
                "赤・黄色に近いほど速く動いており、青に近いほどゆっくり動いています。"
                "どの関節がどのタイミングで加速しているかが視覚的に把握できます。"
            ),
            "points": [
                "赤＝高速、青＝低速（JETカラーマップ）",
                "リリース局面での手首・肘の加速を色で確認",
                "体の各部位の使い方の偏りを発見できる",
            ],
        },
        "ベクトル": {
            "subtitle": "速度・加速度ベクトル",
            "desc": (
                "各関節に矢印を重ねて、動きの方向と大きさを表現します。"
                "緑の矢印が速度（今どの向きに動いているか）、"
                "赤の矢印が加速度（速度がどう変化しているか）を示します。"
            ),
            "points": [
                "緑の矢印：速度ベクトル（向き＝移動方向、長さ＝速さ）",
                "赤の矢印：加速度ベクトル（同方向なら加速、逆なら減速）",
                "肩・肘・手首・腰の8関節を対象",
            ],
        },
        "スティックマン": {
            "subtitle": "スティックマン（黒背景シルエット）",
            "desc": (
                "背景を黒にして、身体をシンプルな線と点だけで表現したモードです。"
                "余計な情報を排除することで、フォームの輪郭・角度・タイミングが"
                "クリアに浮かび上がります。コーチとの振り返りに特に有効です。"
            ),
            "points": [
                "黒背景で骨格ラインが際立つ",
                "手首軌跡をリリース後に徐々にフェードアウト",
                "フォーム比較・コーチング資料として使いやすい",
            ],
        },
        "HUD": {
            "subtitle": "ゲーム風 HUD（数値ダッシュボード）",
            "desc": (
                "ゲームのヘッドアップディスプレイのように、リアルタイムの数値を"
                "画面上に重ねて表示します。右手首の現在速度・最大速度・円形ゲージで"
                "リリース瞬間の強さを定量的に把握できます。"
            ),
            "points": [
                "Speed：右手首のその瞬間の速度（km/h）",
                "Max Speed：動画全体での最大速度",
                "RELEASE フラッシュ：投擲リリース瞬間を自動検出",
            ],
        },
        "コーチング解析": {
            "subtitle": "コーチング解析（5種統合オーバーレイ）",
            "desc": (
                "最も情報量の多いモードです。以下の5つの解析が1本の動画に重ね合わされています。"
                "投擲のフェーズ・関節角度・リリース情報・軌道予測・運動連鎖を一覧できます。"
            ),
            "points": [
                "フェーズバー（下部）：アプローチ→デリバリー→リリース→フォロースルー",
                "関節角度アーク：肘・肩・股関節のリアルタイム角度",
                "リリーススナップショット：検出後3秒間、速度・角度・時刻を表示",
                "軌道予測アーク：リリース後の放物線シミュレーション",
                "Kinetic Chain（右側）：足首→膝→腰→肩→肘→手首の速度バー",
            ],
        },
    }

    # レポートファイルから速度情報を読み込む（存在すれば）
    max_kmh_str = "—"
    release_kmh_str = "—"
    detection_str = "—"
    for vr in variants_results:
        rp = output_dir / vr["filename"].replace(".mp4", "_report.json")
        if rp.exists():
            try:
                with open(rp, encoding="utf-8") as f:
                    rdata = json.load(f)
                a = rdata.get("analysis", {})
                if a.get("wrist_max_speed_kmh"):
                    max_kmh_str = f"{a['wrist_max_speed_kmh']:.1f} km/h"
                if a.get("release_speed_kmh"):
                    release_kmh_str = f"{a['release_speed_kmh']:.1f} km/h"
                if a.get("pose_detection_rate") is not None:
                    detection_str = f"{a['pose_detection_rate']*100:.0f}%"
            except Exception:
                pass
            break

    height_str = f"{height_m} m" if height_m else "未設定"

    # カードHTML（テーブルレイアウト）
    cards_html = ""
    for i, vr in enumerate(variants_results, 1):
        name  = vr["name"]
        fname = vr["filename"]
        ok    = vr["success"]
        d     = VARIANT_DETAIL.get(name, {})
        sub   = d.get("subtitle", name)
        desc  = d.get("desc", "")
        pts   = d.get("points", [])
        badge_cls = "badge-ok" if ok else "badge-ng"
        badge_txt = "出力済み" if ok else "処理失敗"
        pts_html  = "".join(f"<li>{_html.escape(p)}</li>" for p in pts)
        cards_html += f"""
        <div class="card">
          <table class="card-head-table"><tr>
            <td class="card-num">{i}</td>
            <td class="card-title-cell">
              <span class="card-title-main">{_html.escape(name)}</span><br/>
              <span class="card-subtitle">{_html.escape(sub)}</span>
            </td>
            <td class="card-badge-cell"><span class="{badge_cls}">{badge_txt}</span></td>
          </tr></table>
          <p class="card-desc">{_html.escape(desc)}</p>
          <ul class="card-points">{pts_html}</ul>
          <p class="card-fname">{_html.escape(fname)}</p>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>Javelin Video Analysis 解析動画説明書</title>
<style>
  @page {{ size: A4; margin: 15mm 12mm 12mm 12mm; }}
  body {{ font-family: {_FONT_NORMAL}; font-size: 10.5pt; color: #1a1a1a; word-break: break-all; -pdf-word-wrap: CJK; }}
  .page-header {{ border-bottom: 3pt solid #1a56db; padding-bottom: 5pt; margin-bottom: 8pt; }}
  .header-inner {{ width: 100%; }}
  .header-title {{ font-family: {_FONT_BOLD}; font-size: 16pt; color: #1a56db; }}
  .header-meta {{ font-size: 8pt; color: #555; text-align: right; }}
  .summary-table {{ width: 100%; border-collapse: collapse; margin-bottom: 8pt; }}
  .summary-table td {{ border: 1pt solid #d1d5db; padding: 5pt 4pt; background-color: #f9fafb; text-align: center; width: 20%; word-break: normal; }}
  .stat-val {{ font-family: {_FONT_BOLD}; font-size: 12pt; color: #1a56db; }}
  .stat-lbl {{ font-size: 7.5pt; color: #666; }}
  .intro {{ font-size: 9pt; color: #6b7280; margin-bottom: 8pt; word-break: break-all; }}
  .card {{ border: 1pt solid #e5e7eb; padding: 7pt 9pt; margin-bottom: 6pt; }}
  .card-head-table {{ width: 100%; border-collapse: collapse; margin-bottom: 3pt; }}
  .card-num {{ font-family: {_FONT_BOLD}; font-size: 9pt; color: #fff; background-color: #1a56db; text-align: center; width: 18pt; padding: 2pt; }}
  .card-title-cell {{ padding-left: 5pt; }}
  .card-title-main {{ font-family: {_FONT_BOLD}; font-size: 11pt; word-break: break-all; }}
  .card-subtitle {{ font-size: 8pt; color: #6b7280; }}
  .card-badge-cell {{ text-align: right; width: 50pt; }}
  .badge-ok {{ font-size: 7.5pt; color: #166534; background-color: #dcfce7; padding: 2pt 6pt; }}
  .badge-ng {{ font-size: 7.5pt; color: #991b1b; background-color: #fee2e2; padding: 2pt 6pt; }}
  .card-desc {{ font-size: 9pt; color: #374151; margin-bottom: 3pt; line-height: 1.5; word-break: break-all; }}
  .card-points {{ font-size: 8.5pt; color: #4b5563; padding-left: 12pt; line-height: 1.6; margin-bottom: 3pt; word-break: break-all; }}
  .card-fname {{ font-size: 7.5pt; color: #9ca3af; word-break: break-all; }}
  .page-footer {{ margin-top: 6pt; font-size: 7.5pt; color: #9ca3af; text-align: center; border-top: 1pt solid #e5e7eb; padding-top: 3pt; }}
</style>
</head>
<body>
<div class="page-header">
  <table class="header-inner"><tr>
    <td><span class="header-title">解析動画 説明書</span></td>
    <td class="header-meta">Javelin Video Analysis<br/>出力日：{generated}<br/>身長：{height_str}</td>
  </tr></table>
</div>

<table class="summary-table"><tr>
  <td><div class="stat-val">{dur_s} 秒</div><div class="stat-lbl">動画尺</div></td>
  <td><div class="stat-val">{w_v}x{h_v}</div><div class="stat-lbl">解像度</div></td>
  <td><div class="stat-val">{fps_v:.1f} fps</div><div class="stat-lbl">フレームレート</div></td>
  <td><div class="stat-val">{max_kmh_str}</div><div class="stat-lbl">手首最大速度</div></td>
  <td><div class="stat-val">{detection_str}</div><div class="stat-lbl">ポーズ検出率</div></td>
</tr></table>

<p class="intro">以下の 6 本の解析動画が同じフォルダに保存されています。それぞれ異なる視点から投擲フォームを分析したものです。動画は VLC メディアプレイヤー などで再生できます。</p>

{cards_html}

<p class="page-footer">本資料は Javelin Video Analysis により自動生成されました — {date_str}</p>
</body>
</html>"""

    out_path = output_dir / "説明書.pdf"
    buf = io.BytesIO()
    result = pisa.pisaDocument(io.BytesIO(html.encode("utf-8")), buf, encoding="utf-8")
    if result.err:
        logger.warning(f"PDF生成中に警告がありました (err={result.err})")
    with open(out_path, "wb") as f:
        f.write(buf.getvalue())
    logger.info(f"Handout PDF saved: {out_path}")
    w_v      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h_v      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    dur_s    = round(frames_v / fps_v, 1) if fps_v > 0 else 0
    cap.release()

    height_m  = config.get("height_m")
    generated = datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M")
    date_str  = datetime.datetime.now().strftime("%Y年%m月%d日")

    # 各バリアントの詳細説明
    VARIANT_DETAIL = {
        "骨格": {
            "icon": "🦴",
            "subtitle": "骨格トレース＋手首軌跡",
            "desc": (
                "カメラで捉えた映像に、AIが推定した身体の骨格ライン（関節と骨の接続）を"
                "重ね合わせて表示しています。右手首の軌跡が細い線で記録されており、"
                "投擲フォームの全体的な流れを確認するのに適しています。"
            ),
            "points": [
                "青色の線と点が骨格ランドマーク",
                "手首の軌跡でリリース動作のパスを確認できる",
                "フォームの左右対称性・重心移動の把握に最適",
            ],
        },
        "ヒートマップ": {
            "icon": "🌡️",
            "subtitle": "速度ヒートマップ",
            "desc": (
                "各関節の動く速さを色で表現しています。"
                "赤・黄色に近いほど速く動いており、青に近いほどゆっくり動いています。"
                "どの関節がどのタイミングで加速しているかが視覚的に把握できます。"
            ),
            "points": [
                "赤＝高速、青＝低速（JETカラーマップ）",
                "リリース局面での手首・肘の加速を色で確認",
                "体の各部位の使い方の偏りを発見できる",
            ],
        },
        "HUD": {
            "icon": "🎮",
            "subtitle": "ゲーム風 HUD（数値ダッシュボード）",
            "desc": (
                "ゲームのヘッドアップディスプレイのように、リアルタイムの数値を"
                "画面上に重ねて表示します。右手首の現在速度・最大速度・円形ゲージで"
                "リリース瞬間の強さを定量的に把握できます。"
            ),
            "points": [
                "Speed: 右手首のその瞬間の速度（km/h）",
                "Max Speed: 動画全体での最大速度",
                "RELEASE フラッシュ: 投擲リリース瞬間を自動検出",
            ],
        },
        "スティックマン": {
            "icon": "🕹️",
            "subtitle": "スティックマン（黒背景シルエット）",
            "desc": (
                "背景を黒にして、身体をシンプルな線と点だけで表現したモードです。"
                "余計な情報を排除することで、フォームの輪郭・角度・タイミングが"
                "クリアに浮かび上がります。コーチとの振り返りに特に有効です。"
            ),
            "points": [
                "黒背景で骨格ラインが際立つ",
                "手首軌跡をリリース後に徐々にフェードアウト",
                "フォーム比較・コーチング資料として使いやすい",
            ],
        },
        "コーチング解析": {
            "icon": "📊",
            "subtitle": "コーチング解析（5種統合オーバーレイ）",
            "desc": (
                "最も情報量の多いモードです。以下の5つの解析が1本の動画に重ね合わされています。"
                "投擲のフェーズ・関節角度・リリース情報・軌道予測・運動連鎖を一覧できます。"
            ),
            "points": [
                "① フェーズバー（下部）: アプローチ → デリバリー → リリース → フォロースルーの局面表示",
                "② 関節角度アーク: 肘・肩・股関節のリアルタイム角度（°）",
                "③ リリーススナップショット: 検出後3秒間、速度（km/h）・角度・時刻を表示",
                "④ 軌道予測アーク: リリース後の放物線シミュレーション",
                "⑤ Kinetic Chain（右側）: 足首→膝→腰→肩→肘→手首の速度バー",
            ],
        },
        "ベクトル": {
            "icon": "➡️",
            "subtitle": "速度・加速度ベクトル",
            "desc": (
                "各関節に矢印を重ねて、動きの方向と大きさを表現します。"
                "緑の矢印が速度（今どの向きに動いているか）、"
                "赤の矢印が加速度（速度がどう変化しているか）を示します。"
            ),
            "points": [
                "緑の矢印 → 速度ベクトル（向き＝移動方向、長さ＝速さ）",
                "赤の矢印 → 加速度ベクトル（同方向なら加速、逆なら減速）",
                "肩・肘・手首・腰の8関節を対象",
            ],
        },
    }

    # レポートファイルから速度情報を読み込む（存在すれば）
    max_kmh_str = "—"
    release_kmh_str = "—"
    detection_str = "—"
    for vr in variants_results:
        rp = output_dir / vr["filename"].replace(".mp4", "_report.json")
        if rp.exists():
            try:
                with open(rp, encoding="utf-8") as f:
                    rdata = json.load(f)
                a = rdata.get("analysis", {})
                if a.get("wrist_max_speed_kmh"):
                    max_kmh_str = f"{a['wrist_max_speed_kmh']:.1f} km/h"
                if a.get("release_speed_kmh"):
                    release_kmh_str = f"{a['release_speed_kmh']:.1f} km/h"
                if a.get("pose_detection_rate") is not None:
                    detection_str = f"{a['pose_detection_rate']*100:.0f}%"
            except Exception:
                pass
            break  # 1本分で十分

    height_row = f"<tr><td>身長設定</td><td>{height_m} m</td></tr>" if height_m else ""

    # HTML 各バリアントカード
    cards_html = ""
    for i, vr in enumerate(variants_results, 1):
        name = vr["name"]
        fname = vr["filename"]
        ok    = vr["success"]
        d     = VARIANT_DETAIL.get(name, {})
        icon  = d.get("icon", "▶")
        sub   = d.get("subtitle", name)
        desc  = d.get("desc", "")
        pts   = d.get("points", [])
        status_cls = "ok" if ok else "ng"
        status_txt = "出力済み" if ok else "処理失敗"
        pts_html = "".join(f"<li>{_html.escape(p)}</li>" for p in pts)
        cards_html += f"""
        <div class="card">
          <div class="card-header">
            <span class="num">{i}</span>
            <span class="icon">{icon}</span>
            <div class="card-title">
              <strong>{_html.escape(name)}</strong>
              <span class="subtitle">{_html.escape(sub)}</span>
            </div>
            <span class="badge {status_cls}">{status_txt}</span>
          </div>
          <p class="desc">{_html.escape(desc)}</p>
          <ul>{pts_html}</ul>
          <div class="fname">📄 {_html.escape(fname)}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>Javelin Video Analysis — 解析動画説明書</title>
<style>
  @page {{ size: A4; margin: 15mm 12mm 12mm 12mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Hiragino Kaku Gothic Pro","Yu Gothic","Meiryo",sans-serif;
         font-size: 10.5pt; color: #1a1a1a; background: #fff; }}
  header {{ border-bottom: 3px solid #1a56db; padding-bottom: 6px; margin-bottom: 10px; display:flex; justify-content:space-between; align-items:flex-end; }}
  header h1 {{ font-size: 16pt; color: #1a56db; }}
  header .meta {{ font-size: 8pt; color: #555; text-align:right; line-height:1.6; }}
  .summary {{ display: flex; gap: 8px; margin-bottom: 10px; }}
  .stat {{ flex: 1; border: 1px solid #d1d5db; border-radius: 6px; padding: 6px 10px; background: #f9fafb; }}
  .stat .val {{ font-size: 13pt; font-weight: bold; color: #1a56db; }}
  .stat .lbl {{ font-size: 7.5pt; color: #666; }}
  table.info {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; font-size: 9pt; }}
  table.info td {{ border: 1px solid #e5e7eb; padding: 3px 8px; }}
  table.info td:first-child {{ background: #f3f4f6; font-weight: bold; width: 30%; }}
  .card {{ border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px 10px; margin-bottom: 7px; page-break-inside: avoid; }}
  .card-header {{ display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }}
  .num {{ background: #1a56db; color: #fff; border-radius: 50%; width: 20px; height: 20px;
          display:inline-flex; align-items:center; justify-content:center; font-size:9pt; font-weight:bold; flex-shrink:0; }}
  .icon {{ font-size: 14pt; flex-shrink:0; }}
  .card-title {{ flex: 1; }}
  .card-title strong {{ font-size: 11pt; }}
  .subtitle {{ display: block; font-size: 8pt; color: #6b7280; }}
  .badge {{ font-size: 7.5pt; padding: 2px 7px; border-radius: 10px; font-weight: bold; flex-shrink:0; }}
  .badge.ok {{ background: #dcfce7; color: #166534; }}
  .badge.ng {{ background: #fee2e2; color: #991b1b; }}
  .desc {{ font-size: 9pt; color: #374151; margin-bottom: 4px; line-height: 1.55; }}
  ul {{ padding-left: 16px; font-size: 8.5pt; color: #4b5563; line-height: 1.6; }}
  .fname {{ font-size: 7.5pt; color: #9ca3af; margin-top: 4px; font-family: monospace; }}
  footer {{ margin-top: 8px; font-size: 7.5pt; color: #9ca3af; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 4px; }}
</style>
</head>
<body>
<header>
  <h1>解析動画 説明書</h1>
  <div class="meta">
    Javelin Video Analysis<br>
    出力日：{generated}<br>
    身長：{f"{height_m} m" if height_m else "未設定"}
  </div>
</header>

<div class="summary">
  <div class="stat"><div class="val">{dur_s} 秒</div><div class="lbl">動画尺</div></div>
  <div class="stat"><div class="val">{w_v}×{h_v}</div><div class="lbl">解像度</div></div>
  <div class="stat"><div class="val">{fps_v:.1f} fps</div><div class="lbl">フレームレート</div></div>
  <div class="stat"><div class="val">{max_kmh_str}</div><div class="lbl">手首最大速度</div></div>
  <div class="stat"><div class="val">{detection_str}</div><div class="lbl">ポーズ検出率</div></div>
</div>

<p style="font-size:9pt;color:#6b7280;margin-bottom:8px;">
  以下の 6 本の解析動画が同じフォルダに保存されています。
  それぞれ異なる視点から投擲フォームを分析したものです。
  動画は <strong>VLC メディアプレイヤー</strong> などで再生できます。
</p>

{cards_html}

<footer>
  本資料は Javelin Video Analysis により自動生成されました — {date_str}
</footer>
</body>
</html>"""

def process_video_all_variants(input_path: str, base_output_path: str, config: Dict[str, Any]) -> bool:
    logger.info("6つの可視化バリエーションを同時出力します...")
    base_name = Path(base_output_path).stem
    output_dir = Path(base_output_path).parent
    variants = [
        {
            "name": "骨格",
            "filename": f"{base_name}_skeleton.mp4",
            "config_override": {
                "visuals": {
                    "heatmap":     True,
                    "wrist_trail": False,
                    "vectors":     False,
                    "hud":         False,
                    "stickman":    False,
                    "analysis":    False,
                }
            }
        },
        {
            "name": "ベクトル",
            "filename": f"{base_name}_vectors.mp4",
            "config_override": {
                "visuals": {
                    "vectors":     True,
                    "wrist_trail": False,
                    "heatmap":     False,
                    "hud":         False,
                    "stickman":    False,
                    "analysis":    False,
                }
            }
        },
        {
            "name": "スティックマン",
            "filename": f"{base_name}_stickman.mp4",
            "config_override": {
                "visuals": {
                    "stickman":    True,
                    "wrist_trail": False,
                    "vectors":     False,
                    "heatmap":     False,
                    "hud":         False,
                    "analysis":    False,
                }
            }
        },
        {
            "name": "HUD",
            "filename": f"{base_name}_hud.mp4",
            "config_override": {
                "visuals": {
                    "hud":         True,
                    "wrist_trail": False,
                    "vectors":     False,
                    "heatmap":     False,
                    "stickman":    False,
                    "analysis":    False,
                }
            }
        },
        {
            "name": "コーチング解析",
            "filename": f"{base_name}_analysis.mp4",
            "config_override": {
                "visuals": {
                    "analysis":    True,
                    "wrist_trail": False,
                    "vectors":     False,
                    "heatmap":     False,
                    "hud":         False,
                    "stickman":    False,
                }
            }
        },
    ]
    success_count = 0
    total_variants = len(variants)
    variants_results = []
    for i, variant in enumerate(variants, 1):
        print(f"\n[{i}/{total_variants}] {variant['name']}を処理中...")
        variant_config = config.copy()
        variant_config.update(variant["config_override"])
        output_path = output_dir / variant["filename"]
        ok = process_video(input_path, str(output_path), variant_config)
        if ok:
            success_count += 1
            logger.info(f"{variant['name']}: {output_path}")
        else:
            logger.error(f"{variant['name']}の処理に失敗")
        variants_results.append({"name": variant["name"], "filename": variant["filename"], "success": ok})

    print(f"\n完了: {success_count}/{total_variants} バリエーションを出力しました")

    # 説明書 HTML を生成
    try:
        _write_handout_html(output_dir, base_name, variants_results, config, input_path)
    except Exception as e:
        logger.warning(f"説明書の生成に失敗しました: {e}")

    return success_count == total_variants


def process_video(input_path: str, output_path: str, config: Dict[str, Any]) -> bool:
    logger.info(f"Processing video: {input_path}")
    if not os.path.exists(input_path):
        logger.error(f"Input video not found: {input_path}")
        return False
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        logger.error(f"Failed to open video: {input_path}")
        return False
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    logger.info(f"Video: {width}x{height}, {fps} fps, {total_frames} frames")
    # avc1 (H.264) はブラウザ再生可能。失敗時は mp4v にフォールバック
    for fourcc_str in ('avc1', 'mp4v'):
        fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        if out.isOpened():
            logger.info(f"VideoWriter codec: {fourcc_str}")
            break
        out.release()
    if not out.isOpened():
        logger.error(f"Failed to create output video: {output_path}")
        cap.release()
        return False
    pose_analyzer = PoseAnalyzer()
    if config.get("height_m"):
        pose_analyzer.set_scale_from_reference(height * 0.8, config["height_m"] * 0.8)
    visual_pipeline = None
    if VISUALS_AVAILABLE and config.get("visuals"):
        visual_passes = VisualPassRegistry.build_from_config(
            config["visuals"], fps, config.get("height_m")
        )
        if visual_passes:
            visual_pipeline = VisualPipeline(visual_passes)
            logger.info(f"Initialized {len(visual_passes)} visual passes")
    landmarks_data = []
    export_landmarks = config.get("output", {}).get("export_landmarks", False)
    frame_count = 0

    # report.json 用の集計変数
    _pose_detected_frames = 0
    _wrist_speeds_ms: list = []   # キャリブ済みフレームの右手首速度 (m/s)
    _px2m_samples:   list = []   # 有効な px2m サンプル
    _landmarks_rows: list = []   # CSV出力用ランドマーク行
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1
            if frame_count % 30 == 0:
                progress = (frame_count / total_frames) * 100 if total_frames > 0 else 0
                elapsed_time = (frame_count / fps) if fps > 0 else 0
                logger.info(f"Processing frame {frame_count}/{total_frames} ({progress:.1f}%) - Elapsed: {elapsed_time:.1f}s")
            state = pose_analyzer.process(frame, fps)
            result = pose_analyzer.render_basic(frame, state)

            # CSV用ランドマーク行を収集（全バリアント共通: 1回目フレームのみ記録）
            _landmarks_rows.append({
                "frame":         frame_count,
                "time_sec":      (frame_count / fps) if fps > 0 else None,
                "raw_landmarks": state.get("raw_landmarks"),
            })

            # report.json 用データ収集
            points = state.get("points", [])
            if points and any(p is not None for p in points):
                _pose_detected_frames += 1
                # adapters.py と同ロジックで px2m を計算
                _px2m = None
                if config.get("height_m") and len(points) > 28:
                    sh  = points[11] or points[12]
                    ank = [p for p in (points[27], points[28]) if p is not None]
                    if sh is not None and ank:
                        sh_y  = sh[1]
                        ank_y = max(p[1] for p in ank)
                        h_px  = abs(ank_y - sh_y)
                        if h_px > 20:
                            _px2m = (config["height_m"] * 0.8) / h_px
                if _px2m and _px2m < 0.5:
                    _px2m_samples.append(_px2m)
                    # 右手首 (idx=16) 速度: 前フレームとの差分
                    p16 = points[16] if len(points) > 16 else None
                    if p16 is not None and hasattr(process_video, "_prev_wrist") and process_video._prev_wrist is not None:
                        prev = process_video._prev_wrist
                        dx = (p16[0] - prev[0]) * _px2m * fps
                        dy = (p16[1] - prev[1]) * _px2m * fps
                        spd_ms = float(np.hypot(dx, dy))
                        if spd_ms < 35.0:
                            _wrist_speeds_ms.append(spd_ms)
                    process_video._prev_wrist = points[16] if len(points) > 16 else None
                else:
                    if not hasattr(process_video, "_prev_wrist"):
                        process_video._prev_wrist = None
            if visual_pipeline:
                try:
                    result = visual_pipeline.apply_all(
                        result, state, fps, config.get("height_m")
                    )
                except Exception as e:
                    logger.error(f"Visual pipeline error at frame {frame_count}: {e}")
            if export_landmarks and state.get("points"):
                frame_landmarks = []
                for i, point in enumerate(state["points"]):
                    if point is not None:
                        frame_landmarks.append({
                            "id": i,
                            "x": float(point[0]) / width,
                            "y": float(point[1]) / height,
                            "visibility": 1.0
                        })
                    else:
                        frame_landmarks.append({
                            "id": i,
                            "x": 0.0,
                            "y": 0.0,
                            "visibility": 0.0
                        })
                landmarks_data.append({
                    "frame": frame_count,
                    "timestamp": frame_count / fps,
                    "landmarks": frame_landmarks
                })
            out.write(result)
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        return False
    finally:
        cap.release()
        out.release()
        pose_analyzer.close()
    processing_time = frame_count / fps if fps > 0 else 0
    logger.info(f"Video processing completed: {output_path}")
    logger.info(f"Processed {frame_count} frames in {processing_time:.2f}s of video content")

    # ── report.json 出力 ──────────────────────────────────────────────────────
    try:
        import datetime
        px2m_mean = float(np.mean(_px2m_samples)) if _px2m_samples else None
        spd_arr   = np.array(_wrist_speeds_ms) if _wrist_speeds_ms else np.array([])
        max_spd_ms   = float(np.max(spd_arr))  if len(spd_arr) else None
        mean_spd_ms  = float(np.mean(spd_arr)) if len(spd_arr) else None

        # リリース瞬間: 20 m/s を超えた最初のフレーム群のピーク
        release_kmh = None
        if len(spd_arr) > 0:
            cand = spd_arr[spd_arr > 20.0]
            if len(cand):
                release_kmh = round(float(np.max(cand)) * 3.6, 1)

        report = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "input_video": input_path,
            "output_video": output_path,
            "video_info": {
                "width": width,
                "height": height,
                "fps": round(fps, 3),
                "total_frames": total_frames,
                "duration_s": round(total_frames / fps, 2) if fps > 0 else None,
            },
            "analysis": {
                "height_m": config.get("height_m"),
                "px2m_mean": round(px2m_mean, 6) if px2m_mean else None,
                "calibrated": px2m_mean is not None,
                "pose_detected_frames": _pose_detected_frames,
                "pose_detection_rate": round(_pose_detected_frames / frame_count, 3) if frame_count else 0,
                "wrist_max_speed_kmh":  round(max_spd_ms  * 3.6, 1) if max_spd_ms  else None,
                "wrist_mean_speed_kmh": round(mean_spd_ms * 3.6, 1) if mean_spd_ms else None,
                "release_speed_kmh": release_kmh,
            },
            "enabled_passes": [k for k, v in config.get("visuals", {}).items() if v is True],
        }

        # ── CSV 出力（report/ フォルダがあればそこに、なければ output/ に出力）──
        csv_rel_path = None
        try:
            _out_p = Path(output_path)
            _report_dir = _out_p.parent.parent / "report"
            if _report_dir.exists():
                _csv_path = _report_dir / "pose_landmarks.csv"
                csv_rel_path = "report/pose_landmarks.csv"
            else:
                _csv_path = _out_p.parent / "pose_landmarks.csv"
                csv_rel_path = "pose_landmarks.csv"
            # all_variants 等で複数回呼ばれる場合は既存ファイルを上書きしない
            if not _csv_path.exists():
                export_pose_landmarks_csv(_landmarks_rows, _csv_path)
        except Exception as csv_err:
            logger.warning(f"Failed to write pose_landmarks.csv: {csv_err}")
            csv_rel_path = None

        if csv_rel_path:
            report["data_files"] = {"pose_landmarks_csv": csv_rel_path}

        # ── 有効解析区間の検出・保存 ─────────────────────────────────────────────
        _valid_segment: Optional[dict] = None
        try:
            _vs_csv: Optional[Path] = None
            try:
                _vs_csv = _csv_path if (_csv_path is not None and Path(_csv_path).exists()) else None
            except Exception:
                pass
            if _vs_csv is not None:
                _valid_segment = detect_valid_pose_segment(_vs_csv)
                _vs_out = _vs_csv.parent / "valid_segment.json"
                save_valid_segment(_valid_segment, _vs_out)
                report.setdefault("data_files", {})["valid_segment"] = (
                    "report/valid_segment.json"
                    if _vs_csv.parent.name == "report"
                    else "valid_segment.json"
                )
        except Exception as _vs_err:
            logger.warning(f"Failed to detect valid segment: {_vs_err}")

        # ── 代表フレーム画像の切り出し ──────────────────────────────────────────
        try:
            _out_p = Path(output_path)
            _report_dir = _out_p.parent.parent / "report"
            if _report_dir.exists():
                _frames_dir = _report_dir / "frames"
                _frames_prefix = "report/frames"
            else:
                _frames_dir = _out_p.parent / "frames"
                _frames_prefix = "frames"
            # all_variants で複数回呼ばれる場合は既存ディレクトリがあればスキップ
            if not _frames_dir.exists():
                # CSV が存在すればスマートフレーム選択、なければ均等割合で抽出
                try:
                    _csv_for_frames = _csv_path if (_csv_path is not None and _csv_path.exists()) else None
                except Exception:
                    _csv_for_frames = None
                _frame_paths = extract_smart_frames(
                    input_path,
                    _frames_dir,
                    csv_path=_csv_for_frames,
                    valid_segment=_valid_segment,
                )
                if _frame_paths:
                    _rel_paths = [
                        f"{_frames_prefix}/{Path(p).name}" for p in _frame_paths
                    ]
                    report["visual_files"] = {"representative_frames": _rel_paths}
        except Exception as frame_err:
            logger.warning(f"Failed to extract representative frames: {frame_err}")

        report_path = output_path.replace(".mp4", "_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"Report saved: {report_path}")

        # ── グラフ画像生成（CSV 出力後に実行、all_variants では1回目のみ）──
        try:
            _job_dir = Path(output_path).parent.parent
            _graphs_dir = _job_dir / "report" / "graphs"
            if not _graphs_dir.exists():
                _graph_paths = generate_graphs_for_job(_job_dir)
                if _graph_paths:
                    _graph_rels = [f"report/graphs/{Path(p).name}" for p in _graph_paths]
                    # report.json を再読み込みして visual_files.graphs を追記
                    with open(report_path, "r", encoding="utf-8") as _f:
                        _rep = json.load(_f)
                    _vf = _rep.setdefault("visual_files", {})
                    _vf["graphs"] = _graph_rels
                    with open(report_path, "w", encoding="utf-8") as _f:
                        json.dump(_rep, _f, ensure_ascii=False, indent=2)
                    logger.info(f"Graph paths added to report.json: {_graph_rels}")
        except Exception as _graph_err:
            logger.warning(f"Failed to generate graphs: {_graph_err}")

        # ── PDFレポート生成（グラフ生成後に実行）────────────────────────────────
        try:
            _pdf_path = generate_pdf_report_for_job(_job_dir)
            # report.json に report_files.pdf を追記
            with open(report_path, "r", encoding="utf-8") as _f:
                _rep = json.load(_f)
            _rep.setdefault("report_files", {})["pdf"] = "report/report.pdf"
            with open(report_path, "w", encoding="utf-8") as _f:
                json.dump(_rep, _f, ensure_ascii=False, indent=2)
            logger.info(f"PDF report path added to report.json: report/report.pdf")
        except Exception as _pdf_err:
            logger.warning(f"Failed to generate PDF report: {_pdf_err}")

        # ── 解析サマリー JSON 生成（PDF 生成後に実行）────────────────────────────
        try:
            _summary_path = generate_analysis_summary_for_job(_job_dir)
            with open(report_path, "r", encoding="utf-8") as _f:
                _rep = json.load(_f)
            _rep.setdefault("report_files", {})["analysis_summary"] = "report/analysis_summary.json"
            with open(report_path, "w", encoding="utf-8") as _f:
                json.dump(_rep, _f, ensure_ascii=False, indent=2)
            logger.info(f"Analysis summary saved: {_summary_path}")
        except Exception as _summary_err:
            logger.warning(f"Failed to generate analysis summary: {_summary_err}")

    except Exception as e:
        logger.warning(f"Failed to write report.json: {e}")
    if export_landmarks and landmarks_data:
        landmarks_filename = config.get("output", {}).get("landmarks_filename", "landmarks.json")
        if os.path.isabs(landmarks_filename) or os.path.dirname(landmarks_filename):
            landmarks_path = landmarks_filename
        else:
            landmarks_path = os.path.join(output_dir, landmarks_filename) if output_dir else landmarks_filename
        export_landmarks_json(landmarks_data, landmarks_path)
        if config.get("blender", {}).get("enabled", False):
            blender_output = output_path.replace(".mp4", "_blender_overlay.mp4")
            print_blender_commands(output_path, landmarks_path, blender_output)
    return True


def main():
    # Windows cp932 コンソールで絵文字が UnicodeEncodeError になるのを防ぐ
    if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp932", "cp936", "cp949", "cp950", "mbcs"):
        sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, closefd=False)
        sys.stderr = open(sys.stderr.fileno(), mode="w", encoding="utf-8", buffering=1, closefd=False)

    parser = argparse.ArgumentParser(
        description="Javelin Video Analysis with Enhanced Visualizations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "\n使用例:\n"
            "  # 標準形式（推奨）\n"
            "  python run.py --input input/sample.mp4 --output-dir output --all-variants --height-m 1.80\n\n"
            "  # 入力ディレクトリを自動選択して4バリアント同時出力\n"
            "  python run.py --all-variants --height-m 1.80\n\n"
            "  # 可視化フラグを個別指定\n"
            "  python run.py --input input/sample.mp4 --output-dir output --vectors --heatmap --hud\n\n"
            "  # すべての可視化機能を有効化 + Blender連携\n"
            "  python run.py --input input/sample.mp4 --output-dir output --vectors --heatmap --hud\n"
            "              --glow-trail --height-m 1.80 --export-landmarks landmarks.json --blender-overlay\n\n"
            "  # 後方互換: --video / --output も引き続き使用可能\n"
            "  python run.py --video input/sample.mp4 --output output/analysis.mp4 --all-variants\n\n"
            "  # 設定ファイルを使用\n"
            "  python run.py --input input/sample.mp4 --output-dir output --config configs/visuals.yaml\n"
        )
    )
    # ── 入出力（標準形式） ────────────────────────────────────────────────────
    parser.add_argument(
        "--input",
        metavar="INPUT_MP4",
        help="入力動画ファイルのパス（例: input/sample.mp4）。省略時は input/ 内の最初の .mp4 を自動選択。",
    )
    parser.add_argument(
        "--output-dir",
        metavar="OUTPUT_DIR",
        help="出力先ディレクトリ（例: output）。指定すると解析結果をすべてこのフォルダに保存する。",
    )
    # ── 後方互換エイリアス ────────────────────────────────────────────────────
    parser.add_argument(
        "--video",
        metavar="VIDEO",
        help="（後方互換）入力動画ファイルのパス。--input が指定されている場合は --input が優先される。",
    )
    parser.add_argument(
        "--output",
        metavar="OUTPUT_MP4",
        help="（後方互換）出力動画ファイルのパス。--output-dir が指定されている場合は --output-dir が優先される。",
    )
    # ── 共通オプション ────────────────────────────────────────────────────────
    parser.add_argument("--config", metavar="CONFIG_YAML", help="設定ファイルのパス（YAML）")
    parser.add_argument("--height-m", type=float, metavar="HEIGHT", help="被写体の身長（メートル）。速度の物理単位換算に使用。")
    # ── 可視化フラグ ──────────────────────────────────────────────────────────
    parser.add_argument("--vectors",      action="store_true", help="速度・加速度ベクトルを表示")
    parser.add_argument("--heatmap",      action="store_true", help="速度ヒートマップを表示")
    parser.add_argument("--hud",          action="store_true", help="ゲーム風HUDを表示")
    parser.add_argument("--stickman",     action="store_true", help="スティックマン表示（黒背景+ライン骨格）")
    parser.add_argument("--analysis",     action="store_true", help="統合コーチング解析（フェーズ・関節角度・軌道予測・運動連鎖）")
    parser.add_argument("--wrist-trail",  action="store_true", help="右手首軌跡を表示")
    parser.add_argument("--glow-trail",   action="store_true", help="光軌跡エフェクトを表示")
    parser.add_argument("--all-variants", action="store_true", help="骨格・ヒートマップ・HUD・スティックマンの4種を同時出力（推奨）")
    # ── Blender / Landmarks ───────────────────────────────────────────────────
    parser.add_argument("--export-landmarks", metavar="LANDMARKS_JSON", help="ランドマークをJSONで出力（ファイルパスを指定）")
    parser.add_argument("--blender-overlay",  action="store_true",      help="Blender実行コマンドを表示（要 --export-landmarks）")
    # ── その他 ───────────────────────────────────────────────────────────────
    parser.add_argument("--verbose", action="store_true", help="詳細ログを出力")
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    # --input が指定されていれば --video より優先
    if args.input:
        args.video = args.input
    elif args.video:
        # --video のみ指定 → args.input にも反映（以降の処理で統一的に args.video を使う）
        pass
    if not args.video:
        input_dir = Path("input")
        if input_dir.exists():
            video_files = list(input_dir.glob("*.mp4"))
            if video_files:
                args.video = str(video_files[0])
                logger.info(f"自動選択された入力動画: {args.video}")
            else:
                logger.error("inputフォルダに.mp4ファイルが見つかりません")
                return False
        else:
            logger.error("inputフォルダが存在しません")
            return False
    # --output-dir が指定されている場合、そのディレクトリへ出力を設定
    if args.output_dir and not args.output:
        input_path_obj = Path(args.video).resolve()
        out_dir = Path(args.output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        args.output = str(out_dir / f"analysis_{input_path_obj.name}")
        logger.info(f"ジョブ出力パス: {args.output}")
    if not args.output:
        input_path = Path(args.video)
        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)
        args.output = str(out_dir / f"analysis_{input_path.name}")
        logger.info(f"自動設定された出力パス: {args.output}")
    # 入出力パスを絶対パスに統一（サブプロセス・cwd変化に備える）
    args.video = str(Path(args.video).resolve())
    args.output = str(Path(args.output).resolve())
    config = load_config(args.config)
    config = override_config_with_args(config, args)
    if not VISUALS_AVAILABLE and any([args.vectors, args.heatmap, args.hud, args.stickman, args.analysis, args.wrist_trail, args.glow_trail, args.all_variants]):
        logger.warning("可視化機能が利用できません。基本機能のみで実行します。")
    if args.all_variants:
        success = process_video_all_variants(args.video, args.output, config)
    else:
        success = process_video(args.video, args.output, config)
    if success:
        if args.all_variants:
            print(f"\n全バリエーション処理完了!")
            print(f"出力フォルダ: {Path(args.output).parent}")
        else:
            print(f"\n✅ 処理完了: {args.output}")
            enabled = []
            vis = config.get("visuals", {})
            if vis.get("vectors"): enabled.append("ベクトル")
            if vis.get("heatmap"): enabled.append("ヒートマップ")
            if vis.get("hud"): enabled.append("HUD")
            if vis.get("wrist_trail"): enabled.append("手首軌跡")
            if vis.get("glow_trail"): enabled.append("光軌跡")
            print(f"📊 有効な機能: {', '.join(enabled)}" if enabled else "📊 基本骨格表示のみ（後方互換モード）")
        if config.get("height_m"):
            print(f"📏 身長設定: {config['height_m']:.2f}m")
        sys.exit(0)
    else:
        print("❌ 処理中にエラーが発生しました。")
        sys.exit(1)


if __name__ == "__main__":
    main()
