"""
src/annotation/manager.py — Phase 11 アノテーション管理

アノテーションデータの作成・読み込み・更新・一覧取得を担う。

保存先: data/annotations/{annotation_id}/annotation.json

⚠️  重要な方針
    - アノテーションデータは競技動作の参考分析用途のみに使用してください
    - 医療診断・怪我の診断・専門的な競技指導の代替ではありません
    - 動画の撮影角度・画質によりラベル精度が変わります
    - アノテーションは完全な正解ではなく、人間による判断記録です
    - 個人情報（氏名・学校名・連絡先）はエクスポートに含めないでください
    - SNS掲載許可と教師データ利用許可は別々に管理してください

Usage:
    from src.annotation.manager import create_annotation, load_annotation, list_annotations
    from pathlib import Path

    ann = create_annotation(job_id="20260508_070156_518a")
    saved = save_annotation(ann)
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jva.annotation")

_MODULE_DIR = Path(__file__).resolve().parent   # src/annotation/
_REPO_ROOT  = _MODULE_DIR.parent.parent          # project root


def _annotations_root() -> Path:
    """アノテーションデータルートを返す。JVA_ANNOTATIONS_DIR 環境変数で上書き可能。"""
    import os
    from src.config import cfg
    custom = os.getenv("JVA_ANNOTATIONS_DIR", "").strip()
    if custom:
        p = Path(custom)
        return p if p.is_absolute() else (_REPO_ROOT / p)
    return cfg.DATA_DIR / "annotations"


def _load_config() -> Dict[str, Any]:
    """configs/annotation.yaml を読み込む。"""
    cfg_path = _REPO_ROOT / "configs" / "annotation.yaml"
    try:
        import yaml  # type: ignore[import-not-found]
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("[annotation] 設定ファイル読み込み失敗: %s", e)
    return {}


# ── 定数 ──────────────────────────────────────────────────────────────────────

ANNOTATION_STATUSES: List[str] = [
    "draft",      # 下書き（自動生成後・確認前）
    "reviewing",  # 確認中
    "confirmed",  # 確定済み（教師データとして使用可能）
    "rejected",   # 除外
    "archived",   # アーカイブ
]

ANNOTATION_STATUS_LABELS: Dict[str, str] = {
    "draft":     "📝 下書き",
    "reviewing": "🔍 確認中",
    "confirmed": "✅ 確定済み",
    "rejected":  "❌ 除外",
    "archived":  "📂 アーカイブ",
}

CONSENT_FOR_TRAINING_DATA: List[str] = [
    "unknown",        # 未確認
    "allowed",        # 利用可
    "anonymous_only", # 匿名化すれば利用可
    "denied",         # 利用不可
]

CONSENT_TRAINING_LABELS: Dict[str, str] = {
    "unknown":        "⚠️ 未確認",
    "allowed":        "✅ 利用可",
    "anonymous_only": "👤 匿名化すれば利用可",
    "denied":         "🚫 利用不可",
}

SNS_PERMISSION_VALUES: List[str] = [
    "unknown",   # 未確認
    "allowed",   # 許可あり
    "anonymous", # 匿名なら許可
    "denied",    # 不可
]

SNS_PERMISSION_LABELS: Dict[str, str] = {
    "unknown":   "⚠️ 未確認",
    "allowed":   "✅ 許可あり",
    "anonymous": "👤 匿名なら許可",
    "denied":    "🚫 不可",
}

PRIVACY_FLAG_LABELS: Dict[str, str] = {
    "contains_face":             "顔が映っている",
    "contains_school_name":      "学校名が映っている",
    "contains_bib_number":       "ゼッケンが映っている",
    "contains_voice":            "音声が含まれる",
    "contains_third_party":      "第三者が映っている",
    "contains_background_info":  "背景に個人情報が映っている",
    "training_data_excluded":    "教師データ利用不可",
    "needs_anonymization":       "匿名化が必要",
    "csv_features_only":         "動画ファイルは使わずCSV特徴量のみ利用可",
}

LABEL_SOURCE_LABELS: Dict[str, str] = {
    "auto":           "🤖 自動推定",
    "manual":         "✏️ 手動",
    "auto_corrected": "🤖✏️ 自動推定→手動修正",
    "imported":       "📥 インポート",
    "unknown":        "❓ 不明",
}

# ── アノテーションID生成 ──────────────────────────────────────────────────────

def generate_annotation_id() -> str:
    """ann_YYYYMMDD_HHMMSS_xxxx 形式のユニークIDを生成する。"""
    now = datetime.now()
    suffix = "".join(random.choices("0123456789abcdef", k=4))
    return "ann_" + now.strftime("%Y%m%d_%H%M%S") + f"_{suffix}"


# ── アノテーションモデル ──────────────────────────────────────────────────────

def _empty_phase_label(is_range: bool = False) -> Dict[str, Any]:
    """空のフェーズラベルエントリを返す。"""
    base: Dict[str, Any] = {
        "source":     "unknown",
        "confidence": None,
        "reviewed":   False,
        "note":       "",
    }
    if is_range:
        base["start_frame"] = None
        base["end_frame"]   = None
    else:
        base["frame"] = None
    return base


def _empty_event_label() -> Dict[str, Any]:
    """空のイベントラベルエントリを返す。"""
    return {
        "frame":      None,
        "time_sec":   None,
        "source":     "unknown",
        "confidence": None,
        "reviewed":   False,
    }


def make_annotation(
    job_id: str,
    *,
    annotation_id: Optional[str] = None,
    comparison_id: Optional[str] = None,
    video_id: Optional[str] = None,
    source_video_path: Optional[str] = None,
    annotator: str = "system",
    dominant_arm: str = "right",
    fps: Optional[float] = None,
    total_frames: Optional[int] = None,
    duration_sec: Optional[float] = None,
    video_quality_level: str = "unknown",
    notes: str = "",
    consent_for_training_data: str = "unknown",
    sns_permission: str = "unknown",
    privacy_flags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    新しいアノテーション dict を返す（まだ保存しない）。

    Parameters
    ----------
    job_id : str
        対応するジョブID
    annotation_id : str, optional
        指定しない場合は自動生成
    comparison_id : str, optional
        比較ジョブ由来の場合の comparison_id
    video_id : str, optional
        動画ファイルの識別子（フルパスではなく匿名ID推奨）
    source_video_path : str, optional
        元動画パス（エクスポート時は除外される）
    annotator : str
        アノテーターの識別子
    dominant_arm : str
        投げ腕 ("right" | "left")
    fps : float, optional
        FPS
    total_frames : int, optional
        総フレーム数
    duration_sec : float, optional
        動画長（秒）
    video_quality_level : str
        動画品質 ("good" | "medium" | "low" | "unknown")
    notes : str
        管理者メモ
    consent_for_training_data : str
        教師データ利用許可
    sns_permission : str
        SNS掲載許可（教師データ利用許可とは別）
    privacy_flags : list, optional
        プライバシーフラグ

    Returns
    -------
    dict
        annotation.json の内容
    """
    now = datetime.now().isoformat(timespec="seconds")
    ann_id = annotation_id or generate_annotation_id()

    return {
        "schema_version":             "1.0",
        "annotation_id":              ann_id,
        "job_id":                     job_id,
        "comparison_id":              comparison_id,
        "video_id":                   video_id,
        # source_video_path は保存するが、エクスポート時は除外
        "source_video_path":          source_video_path,
        "created_at":                 now,
        "updated_at":                 now,
        "annotator":                  annotator,
        "annotation_status":          "draft",
        "dominant_arm":               dominant_arm,
        "fps":                        fps,
        "total_frames":               total_frames,
        "duration_sec":               duration_sec,
        "video_quality_level":        video_quality_level,
        # ── フェーズラベル ──────────────────────────────────────────────────
        "phase_labels": {
            "approach":       {**_empty_phase_label(is_range=True)},
            "cross_step":     {**_empty_phase_label(is_range=True)},
            "withdrawal":     {**_empty_phase_label(is_range=True)},
            "block":          {**_empty_phase_label(is_range=False)},
            "release":        {**_empty_phase_label(is_range=False)},
            "follow_through": {**_empty_phase_label(is_range=True)},
            "recovery":       {**_empty_phase_label(is_range=True)},
        },
        # ── イベントラベル ──────────────────────────────────────────────────
        "event_labels": {
            "release":              {**_empty_event_label()},
            "block_contact":        {**_empty_event_label()},
            # 将来拡張（存在しても構わない）
        },
        # ── 同意・プライバシー ──────────────────────────────────────────────
        "notes":                     notes,
        "consent_for_training_data": consent_for_training_data,
        "sns_permission":            sns_permission,
        "privacy_flags":             privacy_flags or [],
        # ── エクスポート管理 ────────────────────────────────────────────────
        "export_status":             "not_exported",
    }


# ── 永続化 ────────────────────────────────────────────────────────────────────

def _annotation_dir(annotation_id: str) -> Path:
    return _annotations_root() / annotation_id


def save_annotation(annotation: Dict[str, Any]) -> Path:
    """
    annotation dict を data/annotations/{annotation_id}/annotation.json に保存する。

    Returns
    -------
    Path
        annotation.json のパス
    """
    ann_id = annotation["annotation_id"]
    ann_dir = _annotation_dir(ann_id)
    ann_dir.mkdir(parents=True, exist_ok=True)

    annotation["updated_at"] = datetime.now().isoformat(timespec="seconds")
    out_path = ann_dir / "annotation.json"
    out_path.write_text(
        json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("[annotation] 保存完了: %s job=%s status=%s",
                ann_id, annotation.get("job_id"), annotation.get("annotation_status"))
    return out_path


def load_annotation(annotation_id: str) -> Optional[Dict[str, Any]]:
    """annotation.json を読み込んで返す。存在しない場合は None。"""
    ann_path = _annotation_dir(annotation_id) / "annotation.json"
    if not ann_path.exists():
        return None
    try:
        return json.loads(ann_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[annotation] 読み込み失敗: %s — %s", annotation_id, e)
        return None


def list_annotations(
    status_filter: Optional[List[str]] = None,
    job_id_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    全アノテーションを作成日降順で返す。

    Parameters
    ----------
    status_filter : list, optional
        指定ステータスのみを返す
    job_id_filter : str, optional
        指定ジョブIDのみを返す

    Returns
    -------
    list[dict]
        annotation dict のリスト
    """
    root = _annotations_root()
    if not root.exists():
        return []

    results: List[Dict[str, Any]] = []
    for ann_path in sorted(root.glob("*/annotation.json"), reverse=True):
        try:
            ann = json.loads(ann_path.read_text(encoding="utf-8"))
            if status_filter and ann.get("annotation_status") not in status_filter:
                continue
            if job_id_filter and ann.get("job_id") != job_id_filter:
                continue
            results.append(ann)
        except Exception:
            continue

    return results


def find_annotation_for_job(job_id: str) -> Optional[Dict[str, Any]]:
    """ジョブIDに対応するアノテーションを返す（最初の1件）。"""
    anns = list_annotations(job_id_filter=job_id)
    return anns[0] if anns else None


def update_annotation(
    annotation_id: str,
    updates: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    既存のアノテーションを更新して保存する。

    Parameters
    ----------
    annotation_id : str
        更新対象の annotation_id
    updates : dict
        更新するキーと値のマッピング

    Returns
    -------
    dict or None
        更新後の annotation dict。存在しない場合は None。
    """
    ann = load_annotation(annotation_id)
    if ann is None:
        logger.warning("[annotation] 更新対象が見つかりません: %s", annotation_id)
        return None

    ann.update(updates)
    save_annotation(ann)
    return ann


def set_annotation_status(annotation_id: str, new_status: str) -> Optional[Dict[str, Any]]:
    """annotation_status を更新する。"""
    if new_status not in ANNOTATION_STATUSES:
        raise ValueError(f"無効なステータス: {new_status}. 有効値: {ANNOTATION_STATUSES}")
    return update_annotation(annotation_id, {"annotation_status": new_status})


def archive_annotation(annotation_id: str) -> Optional[Dict[str, Any]]:
    """アノテーションをアーカイブする。"""
    return set_annotation_status(annotation_id, "archived")


# ── Phase 10 推定結果からの自動生成 ──────────────────────────────────────────

def _phase_source(
    phase_key: str,
    corrections: Dict[str, Any],
    detection_phase: Optional[Dict[str, Any]],
) -> str:
    """フェーズのデータソース（auto / manual / auto_corrected）を判定する。"""
    corr = corrections.get(phase_key)
    if corr is not None:
        if corr.get("accepted_by_admin"):
            return "manual"
        if corr.get("manual_corrected_frame") is not None:
            auto_f = corr.get("auto_detected_frame")
            manual_f = corr.get("manual_corrected_frame")
            if auto_f == manual_f:
                return "manual"
            return "auto_corrected"
    if detection_phase is not None and detection_phase.get("frame") is not None:
        return "auto"
    return "unknown"


def _phase_confidence(
    phase_key: str,
    corrections: Dict[str, Any],
    detection_phase: Optional[Dict[str, Any]],
) -> Optional[float]:
    """フェーズの confidence を返す。"""
    corr = corrections.get(phase_key)
    if corr is not None and corr.get("confidence") is not None:
        return round(float(corr["confidence"]), 4)
    if detection_phase is not None:
        return detection_phase.get("confidence")
    return None


def _effective_frame(
    phase_key: str,
    corrections: Dict[str, Any],
    detection_phase: Optional[Dict[str, Any]],
) -> Optional[int]:
    """有効フレーム番号を返す（手動修正 > 自動推定）。"""
    corr = corrections.get(phase_key)
    if corr is not None:
        manual_f = corr.get("manual_corrected_frame")
        if manual_f is not None:
            return int(manual_f)
    if detection_phase is not None:
        f = detection_phase.get("frame")
        if f is not None:
            return int(f)
    return None


def generate_annotation_from_job(
    job_dir: Path,
    annotator: str = "system",
    annotation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    ジョブディレクトリの各 JSON ファイルから annotation dict を自動生成する。

    Phase 10の推定結果 (phase_detection_result.json, video_quality_report.json,
    phase_corrections.json) と受付情報を読み込み、annotation を構築する。

    手動修正済みの値があれば優先する。
    confidence が低い場合は reviewed=False にする。
    動画品質が低い場合は annotation_status=draft を維持する。

    Parameters
    ----------
    job_dir : Path
        ジョブのルートディレクトリ
    annotator : str
        アノテーターID（"system" = 自動生成）
    annotation_id : str, optional
        指定しない場合は自動生成

    Returns
    -------
    dict
        annotation dict（まだ保存されていない）
    """
    job_dir = Path(job_dir)
    cfg = _load_config()
    min_conf = float(cfg.get("quality", {}).get("auto_accept_min_confidence", 0.70))

    # ── 各種JSONの読み込み ────────────────────────────────────────────────────

    def _load_json(path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    job_data         = _load_json(job_dir / "job.json") or {}
    phase_frames_data = _load_json(job_dir / "phase_frames.json") or {}
    customer_info    = _load_json(job_dir / "customer_info.json") or {}
    detection_result = _load_json(job_dir / "report" / "phase_detection_result.json") or {}
    quality_report   = _load_json(job_dir / "report" / "video_quality_report.json") or {}
    corrections      = _load_json(job_dir / "report" / "phase_corrections.json") or {}

    # ── 基本情報 ──────────────────────────────────────────────────────────────
    job_id        = job_data.get("job_id") or job_dir.name
    dominant_arm  = (
        customer_info.get("dominant_arm")
        or customer_info.get("dominant_hand")
        or detection_result.get("dominant_arm")
        or "right"
    )
    fps           = phase_frames_data.get("fps") or quality_report.get("fps")
    total_frames  = phase_frames_data.get("total_frames") or quality_report.get("total_frames")
    duration_sec  = quality_report.get("duration_sec")

    # 動画品質レベル
    video_quality_level = quality_report.get("overall_quality", "unknown")

    # ── consent（SNSと教師データは分ける） ────────────────────────────────────
    default_consent = cfg.get("default_consent_for_training_data", "unknown")
    # customer_info.json の SNS 許可フィールド名は "permission_for_social_post"
    sns_perm = customer_info.get("permission_for_social_post", "unknown")
    # 教師データ利用許可は受付情報に training_data_consent キーがあれば使用
    training_consent = customer_info.get("training_data_consent", default_consent)

    # ── フェーズラベルの組み立て ──────────────────────────────────────────────
    detection_phases = (
        detection_result.get("phases", {})
        if detection_result.get("status") == "ok"
        else {}
    )

    def _build_range_label(key_start: str, key_end: str, phase_name: str) -> Dict[str, Any]:
        """範囲フェーズラベルを構築する。"""
        dp_start = detection_phases.get(key_start)
        dp_end   = detection_phases.get(key_end)

        start_frame = _effective_frame(key_start, corrections, dp_start)
        end_frame   = _effective_frame(key_end,   corrections, dp_end)

        # 手動フレームを優先 (phase_frames.json)
        pf_start = phase_frames_data.get(f"{phase_name}_start_frame")
        pf_end   = phase_frames_data.get(f"{phase_name}_end_frame")
        if pf_start is not None:
            start_frame = int(pf_start)
        if pf_end is not None:
            end_frame = int(pf_end)

        conf = max(
            _phase_confidence(key_start, corrections, dp_start) or 0.0,
            _phase_confidence(key_end,   corrections, dp_end)   or 0.0,
        ) or None

        source = _phase_source(key_start, corrections, dp_start)
        reviewed = bool(
            pf_start is not None
            or (conf is not None and conf >= min_conf and source in ("manual", "auto_corrected"))
        )

        return {
            "start_frame": start_frame,
            "end_frame":   end_frame,
            "source":      source,
            "confidence":  conf,
            "reviewed":    reviewed,
            "note":        "",
        }

    def _build_point_label(key: str, pf_key: str) -> Dict[str, Any]:
        """単点フェーズラベルを構築する。"""
        dp = detection_phases.get(key)
        frame = _effective_frame(key, corrections, dp)

        pf_frame = phase_frames_data.get(pf_key)
        if pf_frame is not None:
            frame = int(pf_frame)

        conf   = _phase_confidence(key, corrections, dp)
        source = _phase_source(key, corrections, dp)
        reviewed = bool(
            pf_frame is not None
            or (conf is not None and conf >= min_conf and source in ("manual", "auto_corrected"))
        )

        return {
            "frame":      frame,
            "source":     source,
            "confidence": conf,
            "reviewed":   reviewed,
            "note":       "",
        }

    phase_labels = {
        "approach":       _build_range_label("approach_start", "approach_end", "approach"),
        "cross_step":     _build_range_label("cross_step_start", "cross_step_end", "cross_step"),
        "withdrawal":     _build_range_label("withdrawal_start", "withdrawal_end", "withdrawal"),
        "block":          _build_point_label("block", "block_frame"),
        "release":        _build_point_label("release", "release_frame"),
        "follow_through": _build_range_label("follow_through_start", "follow_through_end", "follow_through"),
        "recovery":       _build_range_label("recovery_start", "recovery_end", "recovery"),
    }

    # ── イベントラベルの組み立て ──────────────────────────────────────────────
    def _build_event(key: str, pf_key: str) -> Dict[str, Any]:
        dp = detection_phases.get(key)
        frame    = _effective_frame(key, corrections, dp)
        pf_frame = phase_frames_data.get(pf_key)
        if pf_frame is not None:
            frame = int(pf_frame)

        time_sec = None
        if dp is not None:
            time_sec = dp.get("time_sec")

        conf   = _phase_confidence(key, corrections, dp)
        source = _phase_source(key, corrections, dp)
        reviewed = bool(
            pf_frame is not None
            or (conf is not None and conf >= min_conf and source in ("manual", "auto_corrected"))
        )
        return {
            "frame":      frame,
            "time_sec":   time_sec,
            "source":     source,
            "confidence": conf,
            "reviewed":   reviewed,
        }

    event_labels = {
        "release":       _build_event("release", "release_frame"),
        "block_contact": _build_event("block",   "block_frame"),
    }

    # ── 動画品質が低い場合は draft を維持 ────────────────────────────────────
    annotation_status = "draft"

    # ── プライバシーフラグの初期化 ────────────────────────────────────────────
    privacy_flags: List[str] = []

    # source_video_path は保存するがエクスポート時は除外
    source_video_path = job_data.get("input_file")

    ann = make_annotation(
        job_id=job_id,
        annotation_id=annotation_id,
        source_video_path=source_video_path,
        annotator=annotator,
        dominant_arm=dominant_arm,
        fps=fps,
        total_frames=total_frames,
        duration_sec=duration_sec,
        video_quality_level=video_quality_level,
        consent_for_training_data=training_consent,
        sns_permission=sns_perm,
        privacy_flags=privacy_flags,
    )

    ann["annotation_status"] = annotation_status
    ann["phase_labels"]      = phase_labels
    ann["event_labels"]      = event_labels

    return ann


def create_annotation_draft_for_job(job_dir: Path) -> Optional[Path]:
    """
    ジョブディレクトリから annotation draft を作成して保存し、パスを返す。

    すでにそのジョブの annotation が存在する場合は上書きせずスキップして
    既存の annotation.json パスを返す。
    機能が無効またはエラーの場合は None を返す（例外は外に出さない）。

    Parameters
    ----------
    job_dir : Path
        ジョブのルートディレクトリ

    Returns
    -------
    Path or None
        annotation.json のパス。無効化またはエラーの場合は None。
    """
    job_dir = Path(job_dir)

    try:
        # 設定確認
        cfg = _load_config()
        if not cfg.get("enabled", True):
            logger.info("[annotation] 設定で無効化されています: %s", job_dir.name)
            return None

        job_id = job_dir.name

        # 既存 annotation の確認（既にあればスキップ）
        existing = find_annotation_for_job(job_id)
        if existing is not None:
            logger.info("[annotation] 既存アノテーションが存在するためスキップ: %s", job_id)
            return _annotation_dir(existing["annotation_id"]) / "annotation.json"

        ann = generate_annotation_from_job(job_dir, annotator="system")
        out_path = save_annotation(ann)
        logger.info("[annotation] ドラフト作成完了: %s ann_id=%s",
                    job_id, ann["annotation_id"])
        return out_path

    except Exception as e:
        logger.error("[annotation] ドラフト作成エラー: %s — %s", job_dir.name, e)
        return None


# ── データセット統計 ──────────────────────────────────────────────────────────

def compute_dataset_stats() -> Dict[str, Any]:
    """
    全アノテーションのデータセット統計を計算して返す。

    Returns
    -------
    dict
        統計情報
    """
    all_anns = list_annotations()

    total   = len(all_anns)
    status_counts: Dict[str, int] = {s: 0 for s in ANNOTATION_STATUSES}
    consent_counts: Dict[str, int] = {c: 0 for c in CONSENT_FOR_TRAINING_DATA}
    arm_counts: Dict[str, int] = {"right": 0, "left": 0, "unknown": 0}
    quality_counts: Dict[str, int] = {"good": 0, "medium": 0, "low": 0, "unknown": 0}
    has_release   = 0
    has_block     = 0
    from_comparison = 0
    needs_anon    = 0
    export_allowed = 0

    for ann in all_anns:
        status = ann.get("annotation_status", "draft")
        status_counts[status] = status_counts.get(status, 0) + 1

        consent = ann.get("consent_for_training_data", "unknown")
        consent_counts[consent] = consent_counts.get(consent, 0) + 1

        arm = ann.get("dominant_arm", "unknown")
        if arm in arm_counts:
            arm_counts[arm] += 1
        else:
            arm_counts["unknown"] += 1

        quality = ann.get("video_quality_level", "unknown")
        quality_counts[quality] = quality_counts.get(quality, 0) + 1

        # release ラベルあり
        release = ann.get("event_labels", {}).get("release", {})
        if release.get("frame") is not None:
            has_release += 1

        # block ラベルあり
        block = ann.get("event_labels", {}).get("block_contact", {})
        if block.get("frame") is not None:
            has_block += 1

        # 比較由来
        if ann.get("comparison_id"):
            from_comparison += 1

        # 匿名化要
        flags = ann.get("privacy_flags", [])
        if "needs_anonymization" in flags:
            needs_anon += 1

        # エクスポート可能（consent allowed or anonymous_only, ステータス confirmed）
        if (
            consent in ("allowed", "anonymous_only")
            and status == "confirmed"
            and "training_data_excluded" not in flags
        ):
            export_allowed += 1

    return {
        "total":                   total,
        "by_status":               status_counts,
        "by_consent":              consent_counts,
        "by_arm":                  arm_counts,
        "by_quality":              quality_counts,
        "confirmed":               status_counts.get("confirmed", 0),
        "draft":                   status_counts.get("draft", 0),
        "training_data_allowed":   consent_counts.get("allowed", 0) + consent_counts.get("anonymous_only", 0),
        "has_release_label":       has_release,
        "has_block_label":         has_block,
        "from_comparison":         from_comparison,
        "needs_anonymization":     needs_anon,
        "export_allowed":          export_allowed,
    }
