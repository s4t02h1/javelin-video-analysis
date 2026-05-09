"""
src/annotation/exporter.py — Phase 11 アノテーションエクスポート

教師データとして利用可能なアノテーションを JSONL / CSV 形式でエクスポートする。

⚠️  安全フィルタ
    - consent_for_training_data=denied は除外
    - consent_for_training_data=unknown はデフォルト除外
    - anonymous_only は匿名化メタデータのみ出力
    - source_video_path, 個人情報はエクスポートに含めない
    - privacy_flags に training_data_excluded が付いている場合は除外
    - needs_anonymization が付いている場合は警告

出力先例:
    exports/annotations/phase_labels.jsonl
    exports/annotations/phase_labels.csv
    exports/annotations/event_labels.jsonl

Usage:
    from src.annotation.exporter import export_annotations
    from pathlib import Path

    result = export_annotations()
    print(result["exported"], result["excluded"])
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jva.annotation.exporter")

_MODULE_DIR = Path(__file__).resolve().parent   # src/annotation/
_REPO_ROOT  = _MODULE_DIR.parent.parent          # project root

# エクスポートから除外する個人情報フィールド
_EXCLUDED_FIELDS = {
    "source_video_path",
    "schema_version",
}

# anonymous_only の場合に除外するフィールド（追加で匿名化）
_ANON_ONLY_EXCLUDED = {
    "video_id",
    "comparison_id",
}


def _load_config() -> Dict[str, Any]:
    """configs/annotation.yaml のエクスポート設定を読み込む。"""
    cfg_path = _REPO_ROOT / "configs" / "annotation.yaml"
    try:
        import yaml  # type: ignore[import-not-found]
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return (data or {}).get("export", {})
    except Exception:
        pass
    return {}


def _export_dir() -> Path:
    """エクスポート出力先ディレクトリを返す。"""
    cfg = _load_config()
    rel = cfg.get("output_dir", "exports/annotations")
    return _REPO_ROOT / rel


def _should_export(ann: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[bool, str]:
    """
    エクスポート可否を判定する。

    Returns
    -------
    (bool, str)
        (True/False, 理由)
    """
    consent = ann.get("consent_for_training_data", "unknown")
    flags   = ann.get("privacy_flags", [])

    # 利用不可は無条件除外
    if consent == "denied":
        return False, "教師データ利用不可（denied）"

    # 未確認はデフォルト除外
    if consent == "unknown" and cfg.get("default_exclude_unknown_consent", True):
        return False, "教師データ利用許可未確認（unknown）"

    # 明示的に除外フラグが付いている
    if "training_data_excluded" in flags:
        return False, "教師データ利用除外フラグあり"

    # annotation_status が confirmed でないと除外
    status = ann.get("annotation_status", "draft")
    if status not in ("confirmed",):
        return False, f"ステータスが confirmed でない（{status}）"

    return True, ""


def _build_export_record(ann: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    エクスポート用レコードを構築する（個人情報・除外フィールドを除く）。
    """
    consent = ann.get("consent_for_training_data", "unknown")
    flags   = ann.get("privacy_flags", [])

    record: Dict[str, Any] = {}

    # ── 基本フィールド ────────────────────────────────────────────────────────
    record["annotation_id"] = ann["annotation_id"]

    # job_id: anonymize_job_id=True なら匿名ID
    job_id = ann.get("job_id", "")
    if cfg.get("anonymize_job_id", False):
        import hashlib
        record["job_id"] = "j_" + hashlib.sha256(job_id.encode()).hexdigest()[:12]
    else:
        record["job_id"] = job_id

    # anonymous_only は comparison_id / video_id も除外
    if consent != "anonymous_only":
        record["comparison_id"] = ann.get("comparison_id")
        record["video_id"]      = ann.get("video_id")

    record["dominant_arm"]              = ann.get("dominant_arm", "right")
    record["fps"]                       = ann.get("fps")
    record["total_frames"]              = ann.get("total_frames")
    record["duration_sec"]              = ann.get("duration_sec")
    record["video_quality_level"]       = ann.get("video_quality_level", "unknown")
    record["consent_for_training_data"] = consent

    # privacy_flags は概要として保持（詳細は除外）
    safe_flags = [f for f in flags if "personal" not in f.lower()]
    record["privacy_flags"]  = safe_flags
    record["export_allowed"] = True

    # ── フェーズラベルのフラット化 ────────────────────────────────────────────
    phase_labels = ann.get("phase_labels", {})

    for phase_name, pl in phase_labels.items():
        if "start_frame" in pl:
            record[f"{phase_name}_start_frame"] = pl.get("start_frame")
            record[f"{phase_name}_end_frame"]   = pl.get("end_frame")
        elif "frame" in pl:
            record[f"{phase_name}_frame"]       = pl.get("frame")
        record[f"{phase_name}_source"]          = pl.get("source", "unknown")
        record[f"{phase_name}_confidence"]      = pl.get("confidence")
        record[f"{phase_name}_reviewed"]        = pl.get("reviewed", False)

    # ── イベントラベルのフラット化 ────────────────────────────────────────────
    event_labels = ann.get("event_labels", {})

    for event_name, el in event_labels.items():
        record[f"event_{event_name}_frame"]    = el.get("frame")
        record[f"event_{event_name}_time_sec"] = el.get("time_sec")
        record[f"event_{event_name}_source"]   = el.get("source", "unknown")
        record[f"event_{event_name}_reviewed"] = el.get("reviewed", False)

    # ── 便利フラット化（よく使うキー） ───────────────────────────────────────
    record["release_frame"]         = phase_labels.get("release", {}).get("frame")
    record["block_frame"]           = phase_labels.get("block", {}).get("frame")
    record["cross_step_start_frame"] = phase_labels.get("cross_step", {}).get("start_frame")
    record["cross_step_end_frame"]   = phase_labels.get("cross_step", {}).get("end_frame")

    return record


def export_annotations(
    output_dir: Optional[Path] = None,
    include_unknown_consent: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    全アノテーションをフィルタリングして JSONL / CSV エクスポートする。

    Parameters
    ----------
    output_dir : Path, optional
        出力先ディレクトリ。None の場合は configs/annotation.yaml の設定を使用。
    include_unknown_consent : bool
        True の場合、consent=unknown もエクスポート対象に含める（デフォルト: False）
    dry_run : bool
        True の場合、ファイルを書き出さず集計結果のみ返す。

    Returns
    -------
    dict
        exported: エクスポートされた件数
        excluded: 除外された件数
        excluded_reasons: {理由: 件数}
        warnings: 警告リスト
        output_dir: 出力先パス
        jsonl_path: フラットJSONLパス (phase_labels.jsonl)
        csv_path: CSVパス
        event_jsonl_path: イベントJSONLパス (event_labels.jsonl)
    """
    from src.annotation.manager import list_annotations

    cfg = _load_config()
    if include_unknown_consent:
        cfg = dict(cfg)
        cfg["default_exclude_unknown_consent"] = False

    out_dir = output_dir or _export_dir()
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    all_anns = list_annotations()

    exported_records: List[Dict[str, Any]] = []
    excluded_count   = 0
    excluded_reasons: Dict[str, int] = {}
    warnings: List[str] = []

    for ann in all_anns:
        ok, reason = _should_export(ann, cfg)
        if not ok:
            excluded_count += 1
            excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
            continue

        # 匿名化警告
        flags = ann.get("privacy_flags", [])
        warn_flags = [f for f in flags if f in (
            "needs_anonymization", "contains_face", "contains_school_name",
            "contains_bib_number",
        )]
        if warn_flags:
            warnings.append(
                f"⚠️ {ann['annotation_id']} ({ann.get('job_id', '')}) に "
                f"プライバシーフラグがあります: {', '.join(warn_flags)}"
            )

        record = _build_export_record(ann, cfg)
        exported_records.append(record)

    generated_at = datetime.now().isoformat(timespec="seconds")
    result: Dict[str, Any] = {
        "exported":        len(exported_records),
        "excluded":        excluded_count,
        "excluded_reasons": excluded_reasons,
        "warnings":        warnings,
        "output_dir":      str(out_dir),
        "generated_at":    generated_at,
        "jsonl_path":      None,
        "csv_path":        None,
        "event_jsonl_path": None,
    }

    if dry_run or not exported_records:
        return result

    # ── JSONL エクスポート（phase_labels.jsonl）────────────────────────────
    jsonl_path = out_dir / "phase_labels.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as jf:
        for rec in exported_records:
            jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
    result["jsonl_path"] = str(jsonl_path)
    logger.info("[exporter] JSONL エクスポート: %d件 → %s", len(exported_records), jsonl_path)

    # ── CSV エクスポート ───────────────────────────────────────────────────
    if exported_records:
        csv_path = out_dir / "phase_labels.csv"
        all_keys: List[str] = []
        for rec in exported_records:
            for k in rec:
                if k not in all_keys:
                    all_keys.append(k)

        with csv_path.open("w", newline="", encoding="utf-8-sig") as cf:
            writer = csv.DictWriter(cf, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            for rec in exported_records:
                row = {k: rec.get(k, "") for k in all_keys}
                # list フィールドを文字列化
                if isinstance(row.get("privacy_flags"), list):
                    row["privacy_flags"] = "|".join(row["privacy_flags"])
                writer.writerow(row)
        result["csv_path"] = str(csv_path)
        logger.info("[exporter] CSV エクスポート: %d件 → %s", len(exported_records), csv_path)

    # ── イベントラベル JSONL ──────────────────────────────────────────────
    event_records: List[Dict[str, Any]] = []
    for rec in exported_records:
        for event_name in ("release", "block_contact"):
            frame = rec.get(f"event_{event_name}_frame")
            if frame is not None:
                event_records.append({
                    "annotation_id": rec["annotation_id"],
                    "job_id":        rec["job_id"],
                    "event_name":    event_name,
                    "frame":         frame,
                    "time_sec":      rec.get(f"event_{event_name}_time_sec"),
                    "source":        rec.get(f"event_{event_name}_source", "unknown"),
                    "reviewed":      rec.get(f"event_{event_name}_reviewed", False),
                    "dominant_arm":  rec.get("dominant_arm", "right"),
                    "fps":           rec.get("fps"),
                    "total_frames":  rec.get("total_frames"),
                })

    if event_records:
        event_jsonl_path = out_dir / "event_labels.jsonl"
        with event_jsonl_path.open("w", encoding="utf-8") as ef:
            for er in event_records:
                ef.write(json.dumps(er, ensure_ascii=False) + "\n")
        result["event_jsonl_path"] = str(event_jsonl_path)
        logger.info("[exporter] イベントJSONL エクスポート: %d件 → %s",
                    len(event_records), event_jsonl_path)

    # ── エクスポートログ ───────────────────────────────────────────────────
    log_path = out_dir / "export_log.json"
    log_payload = {
        "generated_at":    generated_at,
        "exported":        result["exported"],
        "excluded":        result["excluded"],
        "excluded_reasons": excluded_reasons,
        "warnings":        warnings,
        "files": {
            "phase_labels_jsonl": result["jsonl_path"],
            "phase_labels_csv":   result["csv_path"],
            "event_labels_jsonl": result["event_jsonl_path"],
        },
    }
    log_path.write_text(json.dumps(log_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return result
