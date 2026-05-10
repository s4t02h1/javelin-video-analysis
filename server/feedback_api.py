"""
server/feedback_api.py — Javelin Video Analysis: β版フィードバック API (Phase 15)

エンドポイント:
    POST /v1/public/feedback — フィードバック送信（β版）

⚠️ セキュリティ方針
    - dashboard_token を受け取り、job_id は内部解決のみ
    - job_id はレスポンスに含めない
    - 全フィールドはオプション（リクエストが不完全でも 200 を返す）
    - レート制限: 将来対応（TODO）
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("jva.feedback_api")

feedback_router = APIRouter(tags=["public-feedback"])


# ── リクエストモデル ───────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    """フィードバック送信リクエスト。

    全フィールドはオプション。β版クライアントが一部フィールドを送信しない場合でも
    サーバーがクラッシュしないようにするための設計。
    """
    dashboard_token: Optional[str] = ""
    beta_tester_id:  Optional[str] = ""
    feedback_type:   Optional[str] = "other"   # bug / confusing_ui / report_quality 等
    severity:        Optional[str] = "low"     # low / medium / high / critical
    title:           Optional[str] = ""
    body:            Optional[str] = ""
    device:          Optional[str] = ""        # スマホ / PC / タブレット 等
    os:              Optional[str] = ""        # iOS / Android / Windows 等
    browser:         Optional[str] = ""        # Chrome / Safari 等
    screenshot_note: Optional[str] = ""        # スクリーンショット説明


# ── エンドポイント ────────────────────────────────────────────────────────────

@feedback_router.post("/feedback", summary="β版フィードバック送信")
def submit_feedback(body: FeedbackRequest) -> JSONResponse:
    """β版利用者からのフィードバックを受け付ける。

    - dashboard_token から job_id を内部解決する（レスポンスには含めない）
    - 全フィールドはオプション — 空のリクエストでも 200 を返す
    - フィードバックは data/feedback/ に JSON として保存される

    TODO: レート制限（1 token につき 1 日 N 件まで）は将来対応
    """
    try:
        from src.feedback_manager import create_feedback

        feedback = create_feedback(
            feedback_type   = body.feedback_type or "other",
            severity        = body.severity or "low",
            title           = body.title or "",
            body            = body.body or "",
            dashboard_token = body.dashboard_token or "",
            beta_tester_id  = body.beta_tester_id or "",
            device          = body.device or "",
            os              = body.os or "",
            browser         = body.browser or "",
            screenshot_note = body.screenshot_note or "",
        )

        logger.info(
            "フィードバックを受け付けました: %s (type=%s, severity=%s)",
            feedback["feedback_id"],
            feedback["feedback_type"],
            feedback["severity"],
        )

        # job_id はレスポンスに含めない（セキュリティ方針）
        return JSONResponse(
            status_code=200,
            content={
                "ok":          True,
                "feedback_id": feedback["feedback_id"],
                "message":     "フィードバックを受け付けました。ご協力ありがとうございます。",
            },
        )

    except Exception as e:
        # β版のためクラッシュは避け、エラーをログに記録してから 500 を返す
        logger.error("フィードバック保存エラー: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "ok":     False,
                "error":  "フィードバックの保存に失敗しました。時間をおいて再度お試しください。",
            },
        )
