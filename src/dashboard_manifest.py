"""
src/dashboard_manifest.py — Phase 14: ダッシュボードマニフェスト生成

dashboard_token を生成し、ジョブごとに dashboard_manifest.json を作成する。
dashboard_token は job_id を直接露出しないための URL-safe なランダム文字列。

⚠️ 方針
    - 個人情報（氏名・メール・電話番号）を必要最低限にする
    - presigned URL はマニフェストに保存せず、API 呼び出し時に生成する
    - 参考値であることを manifest 内で明示する

token_index の保存先:
    jobs/_token_index.json
    { "dash_xxx": {"job_id": "...", "type": "single", "created_at": "..."}, ... }

manifest の保存先:
    jobs/<job_id>/report/dashboard_manifest.json
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.dashboard_manifest")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_JOBS_DIR = _REPO_ROOT / "jobs"
_TOKEN_INDEX_PATH = _JOBS_DIR / "_token_index.json"

# 14日間がデフォルト（環境変数で上書き可能）
_DEFAULT_TOKEN_EXPIRES_DAYS = int(os.getenv("JVA_DASHBOARD_TOKEN_EXPIRES_DAYS", "14"))

# 信頼度 → ユーザー向け表示
_RELIABILITY_LABELS: Dict[str, Dict[str, str]] = {
    "high": {
        "label": "信頼度：高め",
        "description": "動画内の姿勢推定点が比較的安定している指標です。",
    },
    "medium": {
        "label": "信頼度：中程度",
        "description": "参考として確認できますが、撮影角度や推定誤差の影響を受ける可能性があります。",
    },
    "low": {
        "label": "信頼度：低め",
        "description": "参考候補として確認してください。断定的な判断には向きません。",
    },
    "unknown": {
        "label": "信頼度：未判定",
        "description": "十分な情報がないため、信頼度を判定できません。",
    },
}

_PHASE_LABELS: Dict[str, Dict[str, str]] = {
    "approach":      {"label": "🏃 助走",            "description": "助走フェーズ。",                "tip": "腰の移動方向の傾向を確認してください（参考値）。"},
    "crossstep":     {"label": "↗️ クロスステップ",  "description": "体幹切り替えフェーズ。",         "tip": "肩腰の向きの変化（2D推定・参考値）。"},
    "withdrawal":    {"label": "↩️ 槍引き",           "description": "槍引きフェーズ。",              "tip": "槍引き距離は動画上の相対値（参考）。"},
    "block":         {"label": "🛑 ブロック",          "description": "前足踏み込みフェーズ。",         "tip": "腰の減速比は動画座標から算出した参考値。"},
    "release":       {"label": "🎯 リリース",          "description": "投擲フェーズ。",                "tip": "手首高さ・速度は相対参考値です。"},
    "follow_through":{"label": "🌀 フォロースルー",  "description": "リリース後の動きのフェーズ。",    "tip": "フォロースルーの動きを確認してください。"},
    "recovery":      {"label": "🔄 リカバリー",       "description": "バランス回復フェーズ。",         "tip": "着地後の安定性を確認してください。"},
}

_KEY_METRIC_KEYS: List[tuple[str, str, str]] = [
    ("release_wrist_height_normalized",       "リリース時の手首高さ（相対）",     "動画上の座標から算出した参考指標です。"),
    ("release_wrist_velocity_normalized",      "リリース時の手首速度（相対）",     "動画上の座標から算出した参考指標です。"),
    ("block_to_release_time_sec",              "ブロック〜リリースの時間",          "ブロックフレームとリリースフレームの差から算出しています。"),
    ("shoulder_hip_separation_angle_estimate_at_release", "肩腰分離（2D推定・参考）", "2D動画上の見かけの角度推定です。3Dの正確な値ではありません。"),
    ("hip_deceleration_ratio",                 "ブロック前後の腰中心減速比",       "腰の動きから算出した参考値です。"),
    ("throwing_wrist_peak_velocity",           "投げ腕の手首最大速度（相対）",     "動画座標上の速度であり、実際の速度とは異なります。"),
]

_DISCLAIMER = (
    "本解析は動画から取得した姿勢推定データをもとにした参考資料です。"
    "実際の距離・速度・角度と完全に一致するわけではありません。"
    "姿勢推定は服装・背景・照明・撮影角度により精度が変わります。"
    "フェーズ推定・高度指標は自動推定であり、正解を保証するものではありません。"
    "本資料は医療診断、怪我の診断、専門的な競技指導を代替するものではありません。"
    "怪我や体の痛みがある場合は医療機関に、競技指導については専門コーチにご相談ください。"
)

_NOTICES = [
    "この解析結果は動画上の姿勢推定をもとにした参考資料です。",
    "動画の画質・撮影角度・服装・背景により精度が変わります。",
    "フェーズ推定・高度指標は自動推定であり、正解を保証するものではありません。",
    "医療診断・怪我の診断・専門的競技指導の代替ではありません。",
]

# ── トークン管理 ──────────────────────────────────────────────────────────────


def generate_dashboard_token() -> str:
    """URL-safe なダッシュボードトークンを生成する。"""
    return "dash_" + secrets.token_urlsafe(16)


def _load_token_index() -> Dict[str, Any]:
    """トークンインデックスを読み込む。"""
    if not _TOKEN_INDEX_PATH.exists():
        return {}
    try:
        return json.loads(_TOKEN_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_token_index(index: Dict[str, Any]) -> None:
    """トークンインデックスを保存する。"""
    _JOBS_DIR.mkdir(parents=True, exist_ok=True)
    _TOKEN_INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def register_dashboard_token(token: str, job_id: str, token_type: str = "single") -> None:
    """トークンをインデックスに登録する。"""
    index = _load_token_index()
    index[token] = {
        "job_id": job_id,
        "type": token_type,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_token_index(index)


def find_job_id_by_token(token: str) -> Optional[tuple[str, str]]:
    """トークンから (job_id, type) を返す。見つからない場合は None。"""
    if not token or not token.startswith("dash_") or len(token) > 80:
        return None
    index = _load_token_index()
    entry = index.get(token)
    if not entry:
        return None
    return entry.get("job_id"), entry.get("type", "single")


def get_or_create_dashboard_token(job_id: str) -> str:
    """job_id に紐づくトークンを返す（なければ生成して保存）。"""
    import job_manager as jm
    try:
        job = jm.load_job(job_id)
    except Exception:
        job = {}
    existing = job.get("dashboard_token")
    if existing and str(existing).startswith("dash_"):
        # インデックスにも登録されていなければ再登録
        index = _load_token_index()
        if existing not in index:
            register_dashboard_token(existing, job_id)
        return existing
    token = generate_dashboard_token()
    try:
        jm.update_job(job_id, dashboard_token=token)
    except Exception as e:
        logger.warning("[manifest] dashboard_token 保存失敗: %s", e)
    register_dashboard_token(token, job_id)
    return token


# ── マニフェスト構築 ──────────────────────────────────────────────────────────


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _fmt_val(v: Any) -> Any:
    if v is None:
        return None
    try:
        f = float(v)
        return round(f, 4)
    except (TypeError, ValueError):
        return v


def _build_videos_list(job_dir: Path) -> List[Dict[str, Any]]:
    """利用可能な動画の情報リストを返す（URL は含めない）。"""
    video_defs = [
        ("skeleton",   "骨格線つき動画",     "姿勢推定点を骨格線として重ねた動画です。関節位置は推定値です。"),
        ("heatmap",    "ヒートマップ動画",   "各部位の動きの軌跡を色で表した動画です（参考）。"),
        ("hud",        "HUDつき動画",       "速度・角度の参考情報をオーバーレイした動画です（参考値）。"),
        ("comparison", "比較動画",           "複数試技を並べた比較動画です（比較解析実施時のみ）。"),
    ]
    output_dir = job_dir / "output"
    items: List[Dict[str, Any]] = []
    for keyword, label, description in video_defs:
        mp4s = list(output_dir.glob(f"*{keyword}*.mp4")) if output_dir.exists() else []
        if mp4s:
            items.append({
                "key": keyword,
                "label": label,
                "description": description,
                "filename": mp4s[0].name,
                "s3_key": None,  # upload_to_s3 後に設定される（マニフェスト再生成で更新）
                "url": None,     # API 呼び出し時に生成
                "content_type": "video/mp4",
                "available": True,
            })
    return items


def _build_phase_images_list(job_dir: Path, phase_frames_data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """フェーズ別画像の情報リストを返す（URL は含めない）。"""
    frames_dir = job_dir / "report" / "frames"
    items: List[Dict[str, Any]] = []
    for phase_key, info in _PHASE_LABELS.items():
        img_path: Optional[Path] = None
        for ext in ["png", "jpg", "jpeg"]:
            candidates = list(frames_dir.glob(f"*{phase_key}*.{ext}")) if frames_dir.exists() else []
            if candidates:
                img_path = candidates[0]
                break
        frame_num = None
        frame_sec = None
        if phase_frames_data:
            frame_num = phase_frames_data.get(f"{phase_key}_frame") or phase_frames_data.get(phase_key)
            sec = phase_frames_data.get(f"{phase_key}_time_sec")
            if sec is not None:
                try:
                    frame_sec = float(sec)
                except Exception:
                    pass
        items.append({
            "phase_key": phase_key,
            "label": info["label"],
            "description": info["description"],
            "tip": info["tip"],
            "filename": img_path.name if img_path else None,
            "s3_key": None,
            "url": None,
            "frame_num": frame_num,
            "frame_time_sec": frame_sec,
            "available": img_path is not None,
        })
    return items


def _build_key_metrics_list(advanced_metrics: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """主要指標のリストを返す。"""
    if not advanced_metrics or advanced_metrics.get("status") == "failed":
        return []
    items: List[Dict[str, Any]] = []
    all_data: Dict[str, Any] = {}
    for section_key in ("release_metrics", "block_metrics", "arm_metrics", "trajectory_metrics"):
        section = advanced_metrics.get(section_key, {})
        if isinstance(section, dict) and section.get("available"):
            all_data.update(section)
    for key, label, caution in _KEY_METRIC_KEYS:
        metric = all_data.get(key)
        if not isinstance(metric, dict):
            continue
        rel = metric.get("reliability", "unknown")
        rel_info = _RELIABILITY_LABELS.get(rel, _RELIABILITY_LABELS["unknown"])
        items.append({
            "key": key,
            "label": label,
            "value": _fmt_val(metric.get("value")),
            "unit": metric.get("unit", ""),
            "reliability": rel,
            "reliability_label": rel_info["label"],
            "reliability_description": rel_info["description"],
            "caution": caution,
            "note": metric.get("note", ""),
        })
    return items


def _build_detail_metrics(advanced_metrics: Optional[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """詳細指標カテゴリ別リストを返す。"""
    if not advanced_metrics:
        return {}

    # キー名 → 日本語ラベル（未登録はキー名をそのまま使用）
    _METRIC_LABELS: Dict[str, str] = {
        "release_wrist_height_normalized":          "リリース時の手首高さ（相対）",
        "release_wrist_velocity_normalized":         "リリース時の手首速度（相対）",
        "release_elbow_angle_deg":                   "リリース時の肘角度（2D推定）",
        "release_shoulder_angle_deg":                "リリース時の肩角度（2D推定）",
        "block_to_release_time_sec":                 "ブロック〜リリースの時間",
        "block_knee_angle_deg":                      "ブロック時の膝角度（2D推定）",
        "block_hip_velocity_normalized":             "ブロック時の腰速度（相対）",
        "hip_deceleration_ratio":                    "ブロック前後の腰中心減速比",
        "shoulder_hip_separation_angle_estimate_at_release": "肩腰分離角（2D推定・参考）",
        "trunk_forward_lean_at_release_deg":         "リリース時の体幹前傾角（2D推定）",
        "trunk_angle_change_rate":                   "体幹角速度（参考値）",
        "throwing_wrist_peak_velocity":              "投げ腕の手首最大速度（相対）",
        "throwing_elbow_lead_frame_count":           "肘先行フレーム数（参考）",
        "non_throwing_arm_position_at_release":      "非投げ腕のポジション（参考）",
        "trajectory_release_angle_deg":              "投射角度推定（2D・参考）",
        "trajectory_flight_time_sec":                "飛行時間推定（参考）",
        "trajectory_peak_height_normalized":         "弧頂高さ推定（相対・参考）",
    }

    def _cat(section_key: str) -> List[Dict[str, Any]]:
        section = advanced_metrics.get(section_key, {})
        if not isinstance(section, dict) or not section.get("available"):
            return []
        rows: List[Dict[str, Any]] = []
        for k, v in section.items():
            if k in ("available", "reason") or not isinstance(v, dict):
                continue
            rel = v.get("reliability", "unknown")
            rel_info = _RELIABILITY_LABELS.get(rel, _RELIABILITY_LABELS["unknown"])
            rows.append({
                "key": k,
                "label": _METRIC_LABELS.get(k, k),
                "value": _fmt_val(v.get("value")),
                "unit": v.get("unit", ""),
                "reliability": rel,
                "reliability_label": rel_info["label"],
            })
        return rows

    return {
        "release": _cat("release_metrics"),
        "block": _cat("block_metrics"),
        "trunk": _cat("trunk_metrics"),
        "arm": _cat("arm_metrics"),
        "trajectory": _cat("trajectory_metrics"),
    }


def _build_graphs_list(job_dir: Path) -> List[Dict[str, Any]]:
    """グラフ画像の情報リストを返す。"""
    graphs_dir = job_dir / "report" / "graphs"
    if not graphs_dir.exists():
        return []
    graph_defs = [
        ("wrist_height",   "手首高さグラフ",    "フレームごとの投げ腕手首高さの変化（参考値）。"),
        ("wrist_velocity", "手首速度グラフ",    "フレームごとの手首速度の変化（参考値）。"),
        ("trunk_angle",    "体幹角度グラフ",    "フレームごとの体幹前傾角度の変化（2D推定・参考値）。"),
        ("phase",          "フェーズ別グラフ",  "フェーズ区切りと時間を示すグラフ。"),
        ("comparison",     "比較グラフ",        "複数試技の比較グラフ（比較解析実施時のみ）。"),
    ]
    items: List[Dict[str, Any]] = []
    for keyword, label, description in graph_defs:
        imgs = list(graphs_dir.glob(f"*{keyword}*.png")) + list(graphs_dir.glob(f"*{keyword}*.jpg"))
        if imgs:
            items.append({
                "key": keyword,
                "label": label,
                "description": description,
                "filename": imgs[0].name,
                "s3_key": None,
                "url": None,
                "available": True,
            })
    return items


def _build_downloads_list(job_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """ダウンロードファイルのカテゴリ別リストを返す。"""
    def _item(rel: str, label: str, category: str, is_research: bool = False) -> Dict[str, Any]:
        full = job_dir / rel
        return {
            "label": label,
            "relative_path": rel,
            "filename": Path(rel).name,
            "s3_key": None,
            "url": None,
            "available": full.exists(),
            "is_research": is_research,
            "category": category,
        }

    return {
        "intro": [
            _item("report/00_最初に読んでください.pdf", "00_最初に読んでください.pdf", "intro"),
            _item("report/video_instruction.pdf",       "解析動画の見方.pdf",          "intro"),
        ],
        "athlete": [
            _item("report/athlete_data_sheet.pdf", "選手データシート.pdf",       "athlete"),
            _item("report/athlete_summary.pdf",    "解析サマリー.pdf",           "athlete"),
            _item("report/phase_summary.pdf",      "フェーズ別サマリー.pdf",     "athlete"),
        ],
        "advanced": [
            _item("report/advanced_metrics_report.pdf", "高度解析指標レポート.pdf", "advanced"),
            _item("report/graph_explanation.pdf",        "グラフ解説.pdf",           "advanced"),
        ],
        "coach": [
            _item("report/coach_review_sheet.pdf",       "コーチ用レビューシート.pdf",   "coach"),
            _item("report/comparison_report.pdf",         "比較レポート.pdf",            "coach"),
            _item("report/comparison_advanced_report.pdf","比較高度指標レポート.pdf",    "coach"),
        ],
        "packages": [
            _item("deliverables/full_report_package.zip",  "全資料一括ダウンロード（ZIP）", "packages"),
            _item("deliverables/data_sheet_package.zip",   "データシートパッケージ（ZIP）", "packages"),
        ],
        "research": [
            _item("report/pose_landmarks.csv",           "姿勢推定データ CSV",       "research", is_research=True),
            _item("report/advanced_metrics.json",        "高度解析指標 JSON",        "research", is_research=True),
            _item("report/phase_detection_result.json",  "フェーズ推定結果 JSON",    "research", is_research=True),
        ],
    }


def build_dashboard_manifest(
    job_dir: Path,
    token_expires_at: Optional[str] = None,
) -> Dict[str, Any]:
    """ダッシュボードマニフェスト dict を構築して返す（保存はしない）。"""
    job_dir = Path(job_dir)

    job_data = _load_json(job_dir / "job.json") or {}
    customer_info = _load_json(job_dir / "customer_info.json") or {}
    phase_frames_data = _load_json(job_dir / "phase_frames.json") or {}
    advanced_metrics = _load_json(job_dir / "report" / "advanced_metrics.json")

    job_id = job_data.get("job_id", job_dir.name)
    token = job_data.get("dashboard_token") or get_or_create_dashboard_token(job_id)

    # 個人情報最小化: 氏名のみ（初期文字に変換も可）。メール・電話は含まない。
    display_name = (customer_info.get("customer_name") or customer_info.get("nickname") or "").strip()
    plan_label = customer_info.get("plan", job_data.get("mode", "スタンダード"))
    created_at = job_data.get("created_at", "")

    if not token_expires_at:
        token_expires_at = (
            datetime.now(timezone.utc) + timedelta(days=_DEFAULT_TOKEN_EXPIRES_DAYS)
        ).isoformat(timespec="seconds")

    generated_at = datetime.now().isoformat(timespec="seconds")

    # 各セクション
    videos = _build_videos_list(job_dir)
    phase_images = _build_phase_images_list(job_dir, phase_frames_data)
    key_metrics = _build_key_metrics_list(advanced_metrics)
    detail_metrics = _build_detail_metrics(advanced_metrics)
    graphs = _build_graphs_list(job_dir)
    downloads = _build_downloads_list(job_dir)

    quality = (advanced_metrics or {}).get("quality", {})
    metrics_version = (advanced_metrics or {}).get("metrics_version", "—") if advanced_metrics else "—"
    overall_quality = quality.get("overall_quality", "unknown")
    metrics_reliability = quality.get("metrics_reliability", "unknown")

    return {
        "schema_version": "1.0",
        "dashboard_token": token,
        "job_id": job_id,
        "dashboard_type": "single",
        "display_name": display_name,
        "plan_label": plan_label,
        "delivered_at": created_at[:10] if len(created_at) >= 10 else created_at,
        "generated_at": generated_at,
        "token_expires_at": token_expires_at,
        "url_expires_at": job_data.get("dashboard_url_expires_at", ""),
        "metrics_version": metrics_version,
        "overall_quality": overall_quality,
        "metrics_reliability": metrics_reliability,
        "sections": {
            "videos": bool(videos),
            "phase_images": True,
            "metrics": bool(key_metrics),
            "graphs": bool(graphs),
            "downloads": True,
            "research_data": True,
        },
        "notices": _NOTICES,
        "videos": videos,
        "phase_images": phase_images,
        "key_metrics": key_metrics,
        "detail_metrics": detail_metrics,
        "graphs": graphs,
        "downloads": downloads,
        "disclaimer": _DISCLAIMER,
        "inquiry_info": {
            "job_id": job_id,
            "delivered_at": created_at[:10] if len(created_at) >= 10 else created_at,
            "plan_label": plan_label,
        },
    }


def save_dashboard_manifest(
    job_dir: Path,
    token_expires_at: Optional[str] = None,
) -> Optional[Path]:
    """ダッシュボードマニフェストを生成・保存する。失敗時は None を返す（例外なし）。"""
    try:
        job_dir = Path(job_dir)
        manifest = build_dashboard_manifest(job_dir, token_expires_at)
        out_path = job_dir / "report" / "dashboard_manifest.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[manifest] dashboard_manifest.json 生成完了: %s", out_path)
        return out_path
    except Exception as e:
        logger.warning("[manifest] dashboard_manifest.json 生成失敗: %s", e)
        return None


def load_dashboard_manifest(job_dir: Path) -> Optional[Dict[str, Any]]:
    """保存済みのマニフェストを読み込む。"""
    path = Path(job_dir) / "report" / "dashboard_manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_token_expired(manifest: Dict[str, Any]) -> bool:
    """マニフェストの token_expires_at が過去かどうかを返す。"""
    expires = manifest.get("token_expires_at", "")
    if not expires:
        return False
    try:
        exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > exp_dt
    except Exception:
        return False


def refresh_manifest_urls(manifest: Dict[str, Any], job_id: str) -> Dict[str, Any]:
    """manifest 内の S3 URL を再生成する（S3 設定済みの場合）。"""
    try:
        import src.storage.s3_storage as s3
        if not s3.is_s3_configured():
            return manifest
    except ImportError:
        return manifest

    def _refresh_item(item: Dict[str, Any]) -> Dict[str, Any]:
        s3_key = item.get("s3_key")
        if s3_key:
            url = s3.generate_presigned_url(s3_key)
            return {**item, "url": url}
        # s3_key がなければ job_id + filename から再構成
        filename = item.get("filename")
        if filename:
            for subdir in ("output", "report", "report/frames", "report/graphs", "deliverables"):
                candidate_key = s3.build_s3_key_for_job(job_id, f"{subdir}/{filename}")
                url = s3.generate_presigned_url(candidate_key)
                if url:
                    return {**item, "url": url, "s3_key": candidate_key}
        return item

    import copy
    m = copy.deepcopy(manifest)
    m["videos"] = [_refresh_item(v) for v in m.get("videos", [])]
    m["phase_images"] = [_refresh_item(p) for p in m.get("phase_images", [])]
    m["graphs"] = [_refresh_item(g) for g in m.get("graphs", [])]
    for cat, items in m.get("downloads", {}).items():
        m["downloads"][cat] = [_refresh_item(d) for d in items]
    return m
