"""
src/phase_loader.py — Javelin Video Analysis フェーズ定義ローダー

configs/phases.yaml を読み込んで dict を返す。
PyYAML 未インストール / ファイル不在の場合はフォールバックを返す。

Usage:
    from src.phase_loader import load_phases, get_phase, get_all_phase_keys
    phases = load_phases()          # 全フェーズ dict
    p = get_phase("block")          # 単一フェーズ dict
    keys = get_all_phase_keys()     # ["approach", "cross_step", ...]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_logger = logging.getLogger("javelin.phase_loader")

_PHASES_YAML_PATH = Path(__file__).resolve().parent.parent / "configs" / "phases.yaml"

# フォールバック: phases.yaml が読み込めない場合のデフォルト定義
# この定義は configs/phases.yaml の内容と常に一致させること
_FALLBACK_PHASES: dict[str, dict] = {
    "approach": {
        "label": "助走", "label_en": "Approach",
        "description": "投てきに向けてスピードとリズムを作る局面です。",
        "key_points": ["歩幅とリズムが一定か", "上体の前傾・やりの持ち方"],
        "is_range": True,
    },
    "cross_step": {
        "label": "クロスステップ", "label_en": "Cross Step",
        "description": "投げに向けて身体を横向きに移行する局面です。",
        "key_points": ["足のクロスと体の向き", "肩・腰のひねりが生まれているか"],
        "is_range": True,
    },
    "withdrawal": {
        "label": "槍を引く局面", "label_en": "Withdrawal",
        "description": "やりを後方に引き、投げの準備を作る局面です。",
        "key_points": ["やりが水平〜やや後傾を保てているか", "肩の高さと肘の向き"],
        "is_range": True,
    },
    "block": {
        "label": "ブロック", "label_en": "Block",
        "description": "前脚で身体を受け止め、助走の力を上半身へ伝える局面です。",
        "key_points": ["前脚がしっかり地面を捉えているか", "肘が下がっていないか"],
        "is_range": False,
    },
    "release": {
        "label": "リリース", "label_en": "Release",
        "description": "やりを手放す瞬間です。",
        "key_points": ["やりが指先から離れていく方向", "肘の高さとリリース角度"],
        "is_range": False,
    },
    "follow_through": {
        "label": "フォロースルー", "label_en": "Follow Through",
        "description": "リリース後に身体が前方へ流れる局面です。",
        "key_points": ["体の重心が前方に流れているか", "腕・肩のリラックス"],
        "is_range": True,
    },
    "recovery": {
        "label": "リカバリー", "label_en": "Recovery",
        "description": "投てき後に姿勢を保ち、ファールを防ぐ局面です。",
        "key_points": ["前方への勢いを制御できているか", "着地位置とバランス"],
        "is_range": True,
    },
}


def load_phases() -> dict[str, dict]:
    """configs/phases.yaml を読み込んで dict を返す。

    失敗した場合はフォールバック定義を返す（アプリを落とさない）。
    """
    try:
        import yaml  # type: ignore[import-untyped]
        with open(_PHASES_YAML_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and data:
            return data
        _logger.warning("[phase_loader] phases.yaml が空またはパース失敗 — フォールバックを使用")
    except ImportError:
        _logger.warning("[phase_loader] PyYAML が未インストール — フォールバックを使用")
    except FileNotFoundError:
        _logger.warning(
            "[phase_loader] phases.yaml が見つかりません (%s) — フォールバックを使用",
            _PHASES_YAML_PATH,
        )
    except Exception as _e:
        _logger.warning("[phase_loader] phases.yaml 読み込みエラー: %s — フォールバックを使用", _e)
    return dict(_FALLBACK_PHASES)


def get_phase(phase_key: str) -> dict[str, Any]:
    """指定フェーズの定義を返す。存在しない場合は空 dict を返す。"""
    return load_phases().get(phase_key, {})


def get_phase_label(phase_key: str) -> str:
    """フェーズの日本語ラベルを返す。未知のキーはそのまま返す。"""
    return get_phase(phase_key).get("label") or phase_key


def get_phase_description(phase_key: str) -> str:
    """フェーズの説明文を返す。"""
    return get_phase(phase_key).get("description") or ""


def get_phase_key_points(phase_key: str) -> list[str]:
    """フェーズの確認ポイントリストを返す。"""
    return list(get_phase(phase_key).get("key_points") or [])


def is_range_phase(phase_key: str) -> bool:
    """開始〜終了フレームで定義するフェーズの場合 True を返す。"""
    return bool(get_phase(phase_key).get("is_range", True))


def get_all_phase_keys() -> list[str]:
    """全フェーズキーを定義順で返す。"""
    return list(load_phases().keys())


def get_phase_labels_map() -> dict[str, str]:
    """フェーズキー → 日本語ラベル の dict を返す。"""
    phases = load_phases()
    return {k: v.get("label", k) for k, v in phases.items()}
