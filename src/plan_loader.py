"""
src/plan_loader.py — Javelin Video Analysis プランローダー

configs/plans.yaml を読み込んで dict を返す。
PyYAML 未インストール / ファイル不在の場合はフォールバックを返す。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_logger = logging.getLogger("javelin.plan_loader")

_PLANS_YAML_PATH = Path(__file__).resolve().parent.parent / "configs" / "plans.yaml"

# フォールバック: plans.yaml が読み込めない場合のデフォルト定義
# ── この定義は configs/plans.yaml の内容と常に一致させること ────────────────
_FALLBACK_PLANS: dict[str, dict] = {
    "free_preview": {
        "label":       "無料プレビュー",
        "price_hint":  "無料",
        "description": "まず解析の雰囲気を確認したい方向け",
        "includes":    ["readme_pdf", "video_instruction_pdf",
                        "representative_frames", "preview_video"],
    },
    "light": {
        "label":       "ライト版",
        "price_hint":  "500〜1000円",
        "description": "選手本人がスマホで確認しやすい簡易版",
        "includes":    ["readme_pdf", "video_instruction_pdf",
                        "athlete_summary_pdf", "key_frame_sheet",
                        "graph_explanation_pdf"],
    },
    "data_sheet": {
        "label":       "データシート版",
        "price_hint":  "1500〜3000円",
        "description": "PDFとデータをまとめて受け取りたい方向け",
        "includes":    ["readme_pdf", "video_instruction_pdf",
                        "athlete_summary_pdf", "graph_explanation_pdf",
                        "key_frame_sheet", "all_videos", "all_frames",
                        "pose_landmarks_csv", "analysis_summary_json"],
    },
    "full_report": {
        "label":       "フルレポート版",
        "price_hint":  "3000〜5000円",
        "description": "詳細に振り返りたい選手・コーチ向け",
        "includes":    ["readme_pdf", "video_instruction_pdf",
                        "athlete_summary_pdf", "graph_explanation_pdf",
                        "key_frame_sheet", "coach_review_sheet",
                        "full_report_pdf", "all_videos", "all_frames",
                        "pose_landmarks_csv", "analysis_summary_json"],
    },
    "comparison": {
        "label":       "2動画比較版",
        "price_hint":  "3000円〜",
        "description": "試合前後・改善前後など2本の動画を比較したい方向け",
        "includes":    ["readme_pdf", "video_instruction_pdf",
                        "comparison_report_pdf", "comparison_graphs",
                        "key_frame_sheet", "selected_videos"],
    },
}


def load_plans() -> dict[str, dict]:
    """configs/plans.yaml を読み込んで dict を返す。

    失敗した場合はフォールバック定義を返す（アプリを落とさない）。
    """
    try:
        import yaml  # type: ignore[import-untyped]
        with open(_PLANS_YAML_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and data:
            return data
        _logger.warning("[plan_loader] plans.yaml が空またはパース失敗 — フォールバックを使用")
    except ImportError:
        _logger.warning("[plan_loader] PyYAML が未インストール — フォールバックを使用")
    except FileNotFoundError:
        _logger.warning(
            "[plan_loader] plans.yaml が見つかりません (%s) — フォールバックを使用",
            _PLANS_YAML_PATH,
        )
    except Exception as _e:
        _logger.warning("[plan_loader] plans.yaml 読み込みエラー: %s — フォールバックを使用", _e)
    return dict(_FALLBACK_PLANS)


def get_plan(plan_key: str) -> dict[str, Any]:
    """指定プランの定義を返す。存在しない場合は free_preview のフォールバックを返す。"""
    plans = load_plans()
    return plans.get(plan_key) or dict(_FALLBACK_PLANS.get("free_preview", {}))


def get_plan_label(plan_key: str) -> str:
    """プランの表示ラベルを返す。未知のキーはそのまま返す。"""
    return get_plan(plan_key).get("label") or plan_key


def get_plan_includes(plan_key: str) -> list[str]:
    """プランに含まれる成果物キーのリストを返す。"""
    return list(get_plan(plan_key).get("includes") or [])


def get_all_plan_keys() -> list[str]:
    """全プランキーを定義順で返す。"""
    return list(load_plans().keys())


def get_plan_labels_map() -> dict[str, str]:
    """プランキー → ラベル の dict を返す。"""
    plans = load_plans()
    return {k: v.get("label", k) for k, v in plans.items()}
