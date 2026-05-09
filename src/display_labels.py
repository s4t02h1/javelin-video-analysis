"""
display_labels.py — 表示用日本語変換ユーティリティ

PDF・管理画面・レポートで使用する内部キー/値を
アスリート・コーチ向けの日本語表示に変換するヘルパー集。

Usage:
    from src.display_labels import ja_label, ja_value, fmt_metric, fmt_arm, fmt_angle
"""

from __future__ import annotations

from typing import Any, Optional

# ── キー名 → 日本語ラベル ────────────────────────────────────────────────────

_KEY_MAP: dict[str, str] = {
    # ジョブ・管理
    "job_id":                  "解析ID",
    "created_at":              "作成日時",
    "updated_at":              "更新日時",
    "generated_at":            "出力日時",
    "status":                  "処理状況",
    "mode":                    "解析モード",
    # 選手情報
    "customer_name":           "氏名",
    "event":                   "種目",
    "dominant_arm":            "利き腕",
    "dominant_hand":           "利き手",
    "height_m":                "身長",
    "height":                  "身長",
    "filming_angle":           "撮影方向",
    "camera_angle":            "撮影方向",
    "instagram_id":            "Instagram ID",
    "plan":                    "プラン",
    "coach_comment":           "コーチコメント",
    # 動画情報
    "duration_sec":            "動画時間 (秒)",
    "duration_s":              "動画時間 (秒)",
    "duration":                "動画時間",
    "frame_count":             "総フレーム数",
    "total_frames":            "総フレーム数",
    "fps":                     "フレームレート",
    "fps_estimated":           "推定フレームレート",
    "resolution":              "解像度",
    "width":                   "動画幅",
    "height_px":               "動画高さ",
    "input_video":             "入力動画",
    "output_video":            "解析動画",
    # 解析品質
    "pose_detected_frames":    "ポーズ検出フレーム数",
    "pose_detection_rate":     "ポーズ検出率",
    "right_wrist_missing_ratio": "右手首 未検出率",
    "calibrated":              "キャリブレーション済み",
    # 速度・メトリクス
    "wrist_max_speed_kmh":     "手首 最大速度 (km/h)",
    "wrist_mean_speed_kmh":    "手首 平均速度 (km/h)",
    "release_speed_kmh":       "リリース速度 (km/h)",
    "wrist_height_max":        "手首 最高到達高さ",
    "wrist_height_min":        "手首 最低高さ",
    "wrist_height_range":      "手首 高さ可動域",
    "wrist_height_peak_frame": "手首 最高点フレーム",
    "wrist_height_peak_time_sec": "手首 最高点時刻 (秒)",
    "shoulder_center_x_start": "肩中心X 開始 (norm)",
    "shoulder_center_x_end":   "肩中心X 終了 (norm)",
    "hip_center_x_start":      "腰中心X 開始 (norm)",
    "hip_center_x_end":        "腰中心X 終了 (norm)",
    # 有効区間
    "valid_start_time_sec":    "有効区間 開始 (秒)",
    "valid_end_time_sec":      "有効区間 終了 (秒)",
    "valid_ratio":             "有効区間 比率",
    # 成果物
    "report_pdf":              "フル解析レポート",
    "video_instruction":       "解析動画の説明書",
    "athlete_data_sheet":      "アスリート向けデータシート",
    "key_frame_sheet":         "重要フレームシート",
    "graph_pack":              "解析グラフ解説",
    "coach_review_sheet":      "コーチ記入用レビューシート",
    "pose_landmarks_csv":      "生データCSV（上級者・研究者向け）",
    "analysis_summary_json":   "解析サマリーJSON（内部データ）",
    "valid_segment_json":      "有効解析区間JSON（内部データ）",
    # グラフ
    "right_wrist_height":      "右手首の高さ変化",
    "right_arm_trajectory":    "右腕の軌跡",
    "torso_center_trajectory": "体幹中心の移動",
    "right_wrist_speed":       "右手首の速度変化",
    "arm_chain_speed":         "運動連鎖の速度変化",
    # その他
    "px2m_mean":               "ピクセル/メートル比 (平均)",
    "height_m_analysis":       "解析用身長 (m)",
    "enabled_passes":          "有効解析パス",
}


def ja_label(key: str) -> str:
    """内部キーを日本語ラベルに変換する。未登録キーはそのまま返す。"""
    return _KEY_MAP.get(key, key)


# ── 値 → 日本語表示 ──────────────────────────────────────────────────────────

_STATUS_MAP: dict[str, str] = {
    "completed": "完了",
    "running":   "処理中",
    "failed":    "失敗",
    "created":   "作成済み",
    "pending":   "待機中",
    "skipped":   "スキップ",
    "ok":        "正常",
    "error":     "エラー",
    "unknown":   "不明",
}

_ARM_MAP: dict[str, str] = {
    "right":   "右",
    "left":    "左",
    "unknown": "不明",
}

_ANGLE_MAP: dict[str, str] = {
    "side":     "側面",
    "front":    "正面",
    "back":     "背面",
    "diagonal": "斜め",
    "unknown":  "不明",
}

_PLAN_MAP: dict[str, str] = {
    "free_preview": "無料プレビュー",
    "data_sheet":   "データシート",
    "full_report":  "フルレポート",
}

_BOOL_MAP: dict[bool, str] = {
    True:  "はい",
    False: "いいえ",
}

# None/null などの表示
_NONE_DISPLAY = "未計算"


def fmt_status(value: str) -> str:
    """処理状況値を日本語に変換する。"""
    if value is None:
        return "不明"
    return _STATUS_MAP.get(str(value).lower(), str(value))


def fmt_arm(value: str) -> str:
    """利き腕 (right/left) を日本語に変換する。"""
    if value is None:
        return "—"
    return _ARM_MAP.get(str(value).lower(), str(value))


def fmt_angle(value: str) -> str:
    """撮影方向 (side/front/back/diagonal) を日本語に変換する。"""
    if value is None:
        return "—"
    return _ANGLE_MAP.get(str(value).lower(), str(value))


def fmt_plan(value: str) -> str:
    """プラン (free_preview/data_sheet/full_report) を日本語に変換する。"""
    if value is None:
        return "—"
    return _PLAN_MAP.get(str(value).lower(), str(value))


def ja_value(value: Any) -> str:
    """任意の値を表示用日本語文字列に変換する。

    - None / 空文字 / "None" / "null" → "未計算"
    - bool → はい/いいえ
    - right/left/side/... → 対応する日本語
    - それ以外 → str(value)
    """
    if value is None:
        return _NONE_DISPLAY
    if isinstance(value, bool):
        return _BOOL_MAP[value]
    s = str(value).strip()
    if s in ("", "None", "null", "none", "NULL"):
        return _NONE_DISPLAY
    low = s.lower()
    if low in _STATUS_MAP:
        return _STATUS_MAP[low]
    if low in _ARM_MAP:
        return _ARM_MAP[low]
    if low in _ANGLE_MAP:
        return _ANGLE_MAP[low]
    if low in _PLAN_MAP:
        return _PLAN_MAP[low]
    return s


def fmt_metric(
    value: Any,
    unit: str = "",
    digits: int = 2,
    note: str = "",
    fallback: str = _NONE_DISPLAY,
) -> str:
    """数値メトリクスを「値 単位 ※注記」形式にフォーマットする。

    Parameters
    ----------
    value   : 数値 or None
    unit    : 付加する単位文字列 (例: " km/h", " 秒")
    digits  : 小数点以下桁数
    note    : 値の末尾に付加するメモ (例: "※推定値")
    fallback: None / 変換失敗時に返す文字列
    """
    if value is None:
        return fallback
    s = str(value).strip()
    if s in ("", "None", "null", "none"):
        return fallback
    try:
        f = float(s)
        result = f"{f:.{digits}f}{unit}"
        if note:
            result += f"  {note}"
        return result
    except (TypeError, ValueError):
        return s + unit if s else fallback


def fmt_pct(value: Any, fallback: str = _NONE_DISPLAY) -> str:
    """0.0〜1.0 の数値をパーセント表示に変換する。"""
    if value is None:
        return fallback
    try:
        return f"{float(value) * 100:.1f} %"
    except (TypeError, ValueError):
        return fallback


def safe_str(value: Any, fallback: str = "—") -> str:
    """値が None / 空の場合は fallback を返す。"""
    if value is None:
        return fallback
    s = str(value).strip()
    return s if s and s not in ("None", "null") else fallback


# ── グラフ説明文 ─────────────────────────────────────────────────────────────

GRAPH_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "right_wrist_height": (
        "右手首の高さ変化",
        "時間ごとの右手首の高さを示したグラフです。"
        "リリースに向かって手首がどのように上がるか、"
        "途中で大きく下がっていないかを確認する目安になります。"
        "縦軸は正規化高さ（0=画面下端 / 1=画面上端）で、"
        "数値は2D動画からの参考推定値です。",
    ),
    "right_arm_trajectory": (
        "右腕の軌跡",
        "肩・肘・手首の位置変化を2D上に表示したグラフです。"
        "投げ腕がどのような通り道を通っているか、"
        "手首の移動経路が大きく乱れていないかを確認するための参考資料です。"
        "撮影角度やポーズ検出精度によって見え方は変わります。",
    ),
    "torso_center_trajectory": (
        "体幹中心の移動",
        "肩中心・腰中心の移動を表示したグラフです。"
        "助走から投げに入る局面で、体幹がどの方向へ移動しているかを"
        "確認する参考資料です。"
        "カメラ方向や画角の影響を受けるため、振り返り用として扱ってください。",
    ),
    "right_wrist_speed": (
        "右手首の速度変化",
        "各フレームにおける右手首の推定速度変化を示しています。"
        "速度ピーク付近がリリース動作の候補です。"
        "数値は撮影条件・姿勢推定精度の影響を受ける参考推定値です。",
    ),
    "arm_chain_speed": (
        "運動連鎖の速度変化",
        "肩・肘・手首などの速度変化を比較するグラフです。"
        "末端である手首に向かって速度がどのように伝わっているか"
        "（運動連鎖）を確認する参考資料です。",
    ),
}

GRAPH_COMMON_NOTE = (
    "【注意】本グラフは2D動画からの姿勢推定データをもとにした参考可視化です。"
    "競技指導・医療判断・怪我の診断を代替するものではありません。"
)


def get_graph_info(stem: str) -> tuple[str, str]:
    """グラフファイルのステム名からタイトルと説明文を返す。"""
    stem_lower = stem.lower()
    for key, (title, desc) in GRAPH_DESCRIPTIONS.items():
        if key in stem_lower:
            return title, desc
    # fallback: ファイル名から生成
    title = stem.replace("_", " ").title()
    return title, "解析グラフです。参考可視化として活用してください。"
