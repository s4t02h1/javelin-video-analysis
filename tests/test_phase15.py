"""
tests/test_phase15.py — Phase 15: β版リリース機能テスト

テスト対象:
1. test_beta_config_loads                — YAML 読み込み
2. test_create_beta_tester               — βテスター作成・保存
3. test_tester_from_intake               — intake からβテスター作成
4. test_create_feedback                  — フィードバック作成・保存
5. test_feedback_api_empty_body          — POST /feedback 空リクエスト → 200
6. test_feedback_from_token_not_found    — 無効トークン → job_id = ""
7. test_improvement_from_feedback        — 改善ログ作成
8. test_beta_flags_dont_break_job        — betaフラグなしのjob.json を安全に読み込む
9. test_beta_delivery_message            — β版納品メッセージの内容確認
10. test_list_beta_testers_empty         — テスターゼロでリスト可能
11. test_list_feedback_empty             — フィードバックゼロでリスト可能
12. test_list_improvements_empty         — 改善ログゼロでリスト可能
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# ── β設定 ───────────────────────────────────────────────────────────────────

def test_beta_config_loads():
    """configs/beta_release_config.yaml が正常にロードできる。"""
    import yaml

    config_path = Path(__file__).resolve().parent.parent / "configs" / "beta_release_config.yaml"
    assert config_path.exists(), "configs/beta_release_config.yaml が見つかりません"

    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    assert "beta" in cfg
    assert cfg["beta"]["enabled"] is True
    assert "max_testers" in cfg["beta"]
    assert "beta_plans" in cfg
    assert "beta_full_report" in cfg["beta_plans"]


# ── βテスター ────────────────────────────────────────────────────────────────

def test_create_beta_tester(tmp_path):
    """βテスターを作成して JSON に保存できる。"""
    from src.beta_tester import create_beta_tester, load_beta_tester, BETA_TESTERS_DIR

    # tmp_path に BETA_TESTERS_DIR を向ける
    tester_dir = tmp_path / "beta_testers"
    with patch("src.beta_tester.BETA_TESTERS_DIR", tester_dir):
        tester = create_beta_tester(
            name_or_nickname="テスト太郎",
            contact="line_xxxxx",
            assigned_plan="beta_full_report",
        )

    assert tester["beta_tester_id"].startswith("bt_")
    assert tester["name_or_nickname"] == "テスト太郎"
    assert tester["assigned_plan"] == "beta_full_report"
    assert tester["is_beta"] is True

    # JSON が保存されている
    json_path = tester_dir / tester["beta_tester_id"] / "beta_tester.json"
    assert json_path.exists()
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    assert raw["beta_tester_id"] == tester["beta_tester_id"]


def test_tester_from_intake(tmp_path):
    """intake データからβテスターを作成できる（直接ロジックを検証）。"""
    from src.beta_tester import create_beta_tester

    tester_dir = tmp_path / "beta_testers"
    with patch("src.beta_tester.BETA_TESTERS_DIR", tester_dir):
        tester = create_beta_tester(
            name_or_nickname="テストさん",
            contact="dm_test",
            dominant_arm="right",
            athlete_category="高校生",
            related_intake_ids=["intake_test_001"],
        )

    assert tester["beta_tester_id"].startswith("bt_")
    assert tester["related_intake_ids"] == ["intake_test_001"]
    assert tester["athlete_category"] == "高校生"


# ── フィードバック ────────────────────────────────────────────────────────────

def test_create_feedback(tmp_path):
    """フィードバックを作成して JSON に保存できる。"""
    from src.feedback_manager import create_feedback, FEEDBACK_DIR

    fb_dir = tmp_path / "feedback"
    with (
        patch("src.feedback_manager.FEEDBACK_DIR", fb_dir),
        patch("src.feedback_manager._resolve_job_id_from_token", return_value="job_test_001"),
    ):
        fb = create_feedback(
            feedback_type="bug",
            severity="high",
            title="テストバグ",
            body="テスト本文",
            dashboard_token="dash_test_token",
        )

    assert fb["feedback_id"].startswith("fb_")
    assert fb["feedback_type"] == "bug"
    assert fb["severity"] == "high"
    assert fb["job_id"] == "job_test_001"

    # job_id は JSON に保存されるが API レスポンスには含めない（server 側で制御）
    json_path = fb_dir / fb["feedback_id"] / "feedback.json"
    assert json_path.exists()


def test_feedback_from_token_not_found(tmp_path):
    """無効なトークンの場合 job_id は空文字になる。"""
    from src.feedback_manager import create_feedback, FEEDBACK_DIR

    fb_dir = tmp_path / "feedback"
    with patch("src.feedback_manager.FEEDBACK_DIR", fb_dir):
        fb = create_feedback(
            feedback_type="other",
            dashboard_token="invalid_token_xyz",
        )

    # トークンが無効な場合でもフィードバックは作成される
    assert fb["feedback_id"].startswith("fb_")
    assert fb["job_id"] == ""


def test_feedback_api_empty_body():
    """POST /v1/public/feedback に空のボディを送っても 200 が返る。"""
    from fastapi.testclient import TestClient

    # 最小限の FastAPI app
    from fastapi import FastAPI
    from server.feedback_api import feedback_router

    app = FastAPI()
    app.include_router(feedback_router, prefix="/v1/public")

    client = TestClient(app)

    with patch("src.feedback_manager.FEEDBACK_DIR", Path(tempfile.mkdtemp()) / "feedback"):
        response = client.post(
            "/v1/public/feedback",
            json={},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "feedback_id" in data


# ── 改善ログ ─────────────────────────────────────────────────────────────────

def test_improvement_from_feedback(tmp_path):
    """フィードバックから改善ログを作成できる。"""
    from src.feedback_manager import create_feedback, FEEDBACK_DIR
    from src.improvement_log import create_improvement, IMPROVEMENT_DIR

    fb_dir  = tmp_path / "feedback"
    imp_dir = tmp_path / "improvement_logs"

    # フィードバックを先に作成
    with (
        patch("src.feedback_manager.FEEDBACK_DIR", fb_dir),
        patch("src.feedback_manager._resolve_job_id_from_token", return_value=""),
    ):
        fb = create_feedback(
            feedback_type="bug",
            severity="critical",
            title="表示崩れ",
            body="ダッシュボードが壊れる",
        )

    # 改善ログを作成（from_feedback ヘルパーではなく直接作成で検証）
    with patch("src.improvement_log.IMPROVEMENT_DIR", imp_dir):
        imp = create_improvement(
            title="表示崩れ修正",
            category="bug",
            priority="critical",
            source_feedback_id=fb["feedback_id"],
            description=fb["body"],
        )

    assert imp["improvement_id"].startswith("imp_")
    assert imp["source_feedback_id"] == fb["feedback_id"]
    assert imp["priority"] == "critical"
    assert imp["category"] == "bug"


# ── 既存 job との互換性 ───────────────────────────────────────────────────────

def test_beta_flags_dont_break_job(tmp_path):
    """β版フラグを持たない既存 job.json を安全に読み込める。"""
    from job_manager import JOBS_DIR, load_job

    # β版フラグなしの最小限の job.json を作成
    job_id = "20991231_235959_test"
    job_dir = tmp_path / "jobs" / job_id
    job_dir.mkdir(parents=True)
    job_data = {
        "job_id": job_id,
        "status": "completed",
        "mode": "basic",
    }
    (job_dir / "job.json").write_text(json.dumps(job_data), encoding="utf-8")

    with patch("job_manager.JOBS_DIR", tmp_path / "jobs"):
        job = load_job(job_id)

    # β版フラグがなくてもエラーにならない
    assert job["job_id"] == job_id
    # is_beta は存在しないか False と同等
    assert not job.get("is_beta")


# ── β版納品メッセージ ─────────────────────────────────────────────────────────

def test_beta_delivery_message():
    """β版納品メッセージに dashboard_url と免責事項が含まれる。"""
    from src.message_templates import generate_beta_delivery_message

    url = "https://example.com/dashboard/dash_testtoken"
    msg = generate_beta_delivery_message(
        dashboard_url=url,
        customer_label="テスト選手",
        feedback_form_url="https://forms.example.com/feedback",
    )

    assert url in msg
    assert "β版" in msg
    assert "参考" in msg
    assert "医療診断" in msg
    assert "フィードバック" in msg
    assert "テスト選手" in msg


# ── 空リスト ─────────────────────────────────────────────────────────────────

def test_list_beta_testers_empty(tmp_path):
    """βテスターが 0 件の場合、空リストを返す。"""
    from src.beta_tester import list_beta_testers

    with patch("src.beta_tester.BETA_TESTERS_DIR", tmp_path / "beta_testers"):
        result = list_beta_testers()

    assert result == []


def test_list_feedback_empty(tmp_path):
    """フィードバックが 0 件の場合、空リストを返す。"""
    from src.feedback_manager import list_feedback

    with patch("src.feedback_manager.FEEDBACK_DIR", tmp_path / "feedback"):
        result = list_feedback()

    assert result == []


def test_list_improvements_empty(tmp_path):
    """改善ログが 0 件の場合、空リストを返す。"""
    from src.improvement_log import list_improvements

    with patch("src.improvement_log.IMPROVEMENT_DIR", tmp_path / "improvements"):
        result = list_improvements()

    assert result == []
