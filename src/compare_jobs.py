"""
src/compare_jobs.py — Javelin Video Analysis ジョブ比較モジュール

2つのジョブの analysis_summary.json を読み込んで差分を算出し、
jobs/comparisons/<comparison_id>/comparison_summary.json に保存する。

Usage:
    from src.compare_jobs import compare_two_jobs, save_comparison
    from pathlib import Path

    result = compare_two_jobs(Path("jobs/job_a"), Path("jobs/job_b"))
    saved  = save_comparison(result)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 比較対象フィールド（summary キー → 表示ラベル）
_COMPARE_FIELDS: dict[str, str] = {
    "duration_sec":               "動画尺 (秒)",
    "wrist_height_range":         "手首可動域",
    "wrist_height_peak_time_sec": "手首ピーク時刻 (秒)",
    "shoulder_center_x_start":   "肩中心 X (開始)",
    "shoulder_center_x_end":     "肩中心 X (終了)",
    "hip_center_x_start":        "腰中心 X (開始)",
    "hip_center_x_end":          "腰中心 X (終了)",
}


def _load_json(path: Path) -> Optional[dict]:
    """JSON ファイルを読み込む。失敗時は None を返す。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[compare_jobs] JSON 読み込み失敗: %s — %s", path, exc)
        return None


def _load_summary(job_dir: Path) -> tuple[Optional[dict], str]:
    """analysis_summary.json を読み込む。

    Returns
    -------
    (summary_dict_or_None, error_message)
    """
    summary_path = job_dir / "report" / "analysis_summary.json"
    if not summary_path.exists():
        return None, f"analysis_summary.json が見つかりません: {summary_path}"
    data = _load_json(summary_path)
    if data is None:
        return None, f"analysis_summary.json の読み込みに失敗しました: {summary_path}"
    if data.get("status") != "ok":
        reason = data.get("reason", "不明")
        return None, f"analysis_summary のステータスが ok ではありません (status={data.get('status')}, reason={reason})"
    return data, ""


def _diff(val_a: Any, val_b: Any) -> Optional[float]:
    """b - a の数値差分を返す。計算できない場合は None。"""
    try:
        return round(float(val_b) - float(val_a), 6)
    except (TypeError, ValueError):
        return None


def compare_two_jobs(job_dir_a: Path, job_dir_b: Path) -> dict:
    """
    2つのジョブを比較し、差分を含む dict を返す。

    Parameters
    ----------
    job_dir_a : Path
        比較元ジョブのルートディレクトリ（Job A = 旧 / 1投目など）
    job_dir_b : Path
        比較先ジョブのルートディレクトリ（Job B = 新 / 2投目など）

    Returns
    -------
    dict
        比較結果。キー:
        - "status": "ok" | "error"
        - "error": str（status=="error" 時のみ）
        - "job_a": {"job_id", "dominant_hand", ...}
        - "job_b": {"job_id", "dominant_hand", ...}
        - "fields": {field_key: {"label", "a", "b", "diff"}, ...}
        - "generated_at": ISO 8601 文字列
    """
    job_dir_a = Path(job_dir_a)
    job_dir_b = Path(job_dir_b)

    summary_a, err_a = _load_summary(job_dir_a)
    summary_b, err_b = _load_summary(job_dir_b)

    errors: list[str] = []
    if err_a:
        errors.append(f"Job A: {err_a}")
    if err_b:
        errors.append(f"Job B: {err_b}")
    if errors:
        return {
            "status":       "error",
            "error":        " / ".join(errors),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

    assert summary_a is not None
    assert summary_b is not None

    fields: dict[str, dict] = {}
    for key, label in _COMPARE_FIELDS.items():
        val_a = summary_a.get(key)
        val_b = summary_b.get(key)
        fields[key] = {
            "label": label,
            "a":     val_a,
            "b":     val_b,
            "diff":  _diff(val_a, val_b),
        }

    result: dict[str, Any] = {
        "status": "ok",
        "job_a": {
            "job_id":       job_dir_a.name,
            "job_dir":      str(job_dir_a),
            "dominant_hand": summary_a.get("dominant_hand"),
            "total_frames": summary_a.get("total_frames"),
            "duration_sec": summary_a.get("duration_sec"),
        },
        "job_b": {
            "job_id":       job_dir_b.name,
            "job_dir":      str(job_dir_b),
            "dominant_hand": summary_b.get("dominant_hand"),
            "total_frames": summary_b.get("total_frames"),
            "duration_sec": summary_b.get("duration_sec"),
        },
        "fields":       fields,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    logger.info(
        "[compare_jobs] 比較完了: %s vs %s",
        job_dir_a.name, job_dir_b.name,
    )
    return result


def _make_comparison_id() -> str:
    """YYYYMMDD_HHMMSS_xxxx 形式の comparison_id を生成する。"""
    now = datetime.now()
    suffix = uuid.uuid4().hex[:4]
    return now.strftime("%Y%m%d_%H%M%S") + f"_{suffix}"


def save_comparison(
    result: dict,
    comparisons_root: Optional[Path] = None,
) -> Path:
    """
    比較結果を comparisons/<comparison_id>/comparison_summary.json に保存する。

    Parameters
    ----------
    result : dict
        compare_two_jobs() の返り値
    comparisons_root : Path, optional
        保存先ルート。省略時は jobs/ と同じ階層の jobs/comparisons/ を使う。

    Returns
    -------
    Path
        保存した comparison_summary.json のパス
    """
    if comparisons_root is None:
        # jobs/ ディレクトリを基準に決定
        # job_dir が result に含まれている場合はそこから推定
        job_a_dir = result.get("job_a", {}).get("job_dir")
        if job_a_dir:
            comparisons_root = Path(job_a_dir).parent.parent / "comparisons"
        else:
            comparisons_root = Path("jobs") / "comparisons"

    comparison_id = _make_comparison_id()
    out_dir = comparisons_root / comparison_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # comparison_id を result に埋め込んで保存
    payload = {"comparison_id": comparison_id, **result}
    out_path = out_dir / "comparison_summary.json"
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("[compare_jobs] Saved: %s", out_path)
    return out_path


def list_comparisons(comparisons_root: Path) -> list[dict]:
    """
    comparisons_root 以下の comparison_summary.json を新しい順に読み込んで返す。

    Parameters
    ----------
    comparisons_root : Path
        jobs/comparisons/ などの比較結果ルートディレクトリ

    Returns
    -------
    list[dict]
        各 comparison_summary.json の内容リスト（読み込めたものだけ）
    """
    results: list[dict] = []
    if not comparisons_root.exists():
        return results
    for summary_path in sorted(
        comparisons_root.glob("*/comparison_summary.json"), reverse=True
    ):
        data = _load_json(summary_path)
        if data:
            results.append(data)
    return results
