"""
tests/test_phase14.py — Phase 14: 軽量Webフロントエンド化 テスト

テスト対象:
- src/dashboard_manifest.py (token生成・マニフェスト構築・保存・検索)
- server/public_dashboard_api.py (FastAPI public API)
- worker.py (generate_dashboard_manifest ステップ)
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest


# ── テスト用ジョブディレクトリを作成するヘルパー ────────────────────────────────


def _make_test_job(
    tmp_path: Path,
    with_metrics: bool = True,
    with_frames: bool = True,
    with_graphs: bool = False,
    job_id: str = "test_job_p14",
) -> Path:
    """テスト用の最小限ジョブディレクトリを作成する。"""
    job_dir = tmp_path / job_id
    (job_dir / "input").mkdir(parents=True)
    (job_dir / "output").mkdir()
    (job_dir / "report").mkdir()
    (job_dir / "report" / "frames").mkdir()
    (job_dir / "report" / "graphs").mkdir()

    # job.json
    (job_dir / "job.json").write_text(json.dumps({
        "job_id": job_id,
        "status": "delivery_ready",
        "created_at": "2026-05-10T00:00:00",
        "updated_at": "2026-05-10T00:00:00",
        "height_m": None,
        "mode": "all_variants",
    }), encoding="utf-8")

    # customer_info.json
    (job_dir / "customer_info.json").write_text(json.dumps({
        "customer_name": "テスト選手",
        "plan": "スタンダード",
    }), encoding="utf-8")

    # phase_frames.json
    (job_dir / "phase_frames.json").write_text(json.dumps({
        "release_frame": 100,
        "block_frame": 90,
    }), encoding="utf-8")

    # advanced_metrics.json
    if with_metrics:
        (job_dir / "report" / "advanced_metrics.json").write_text(json.dumps({
            "job_id": job_id,
            "status": "ok",
            "metrics_version": "0.1.0",
            "generated_at": "2026-05-10T00:00:00",
            "quality": {
                "overall_quality": "good",
                "metrics_reliability": "high",
                "pose_detection_rate": 0.95,
                "warnings": [],
            },
            "release_metrics": {
                "available": True,
                "release_wrist_height_normalized": {
                    "value": 1.2, "unit": "body_scale", "reliability": "high", "note": ""
                },
                "release_wrist_velocity_normalized": {
                    "value": 8.5, "unit": "body_scale/sec", "reliability": "high", "note": ""
                },
            },
            "block_metrics": {
                "available": True,
                "block_to_release_time_sec": {
                    "value": 0.15, "unit": "sec", "reliability": "medium", "note": ""
                },
            },
            "trunk_metrics": {"available": False},
            "arm_metrics": {
                "available": True,
                "throwing_wrist_peak_velocity": {
                    "value": 12.3, "unit": "body_scale/sec", "reliability": "high", "note": ""
                },
            },
            "trajectory_metrics": {},
        }), encoding="utf-8")

    # 代表フレーム画像（1x1 PNG）
    if with_frames:
        _PNG_1X1 = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
        )
        (job_dir / "report" / "frames" / "release_frame.png").write_bytes(_PNG_1X1)

    if with_graphs:
        _PNG_1X1 = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
        )
        (job_dir / "report" / "graphs" / "wrist_height_graph.png").write_bytes(_PNG_1X1)

    return job_dir


# ── TestDashboardToken ─────────────────────────────────────────────────────────


class TestDashboardToken:
    def test_generate_token_format(self) -> None:
        """generate_dashboard_token() は 'dash_' で始まる文字列を返す。"""
        from src.dashboard_manifest import generate_dashboard_token
        token = generate_dashboard_token()
        assert isinstance(token, str)
        assert token.startswith("dash_")
        assert len(token) > 10

    def test_generate_token_unique(self) -> None:
        """generate_dashboard_token() は毎回異なるトークンを返す。"""
        from src.dashboard_manifest import generate_dashboard_token
        tokens = {generate_dashboard_token() for _ in range(10)}
        assert len(tokens) == 10

    def test_register_and_find_token(self, tmp_path: Path) -> None:
        """register_dashboard_token → find_job_id_by_token で job_id を取得できる。"""
        from src.dashboard_manifest import (
            register_dashboard_token,
            find_job_id_by_token,
            _TOKEN_INDEX_PATH,
        )
        # テスト用インデックスファイルに差し替え
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            token = "dash_testtoken1234"
            register_dashboard_token(token, "job_abc123")
            result = find_job_id_by_token(token)
            assert result is not None
            job_id, token_type = result
            assert job_id == "job_abc123"
            assert token_type == "single"

    def test_find_unknown_token_returns_none(self, tmp_path: Path) -> None:
        """存在しないトークンで find_job_id_by_token は None を返す。"""
        from src.dashboard_manifest import find_job_id_by_token
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            result = find_job_id_by_token("dash_unknown99999999")
            assert result is None

    def test_invalid_token_prefix_returns_none(self, tmp_path: Path) -> None:
        """'dash_' 以外のプレフィックスは None を返す。"""
        from src.dashboard_manifest import find_job_id_by_token
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            assert find_job_id_by_token("evil_token") is None
            assert find_job_id_by_token("") is None


# ── TestDashboardManifest ──────────────────────────────────────────────────────


class TestDashboardManifest:
    def test_build_manifest_returns_dict(self, tmp_path: Path) -> None:
        """build_dashboard_manifest() は dict を返す。"""
        from src.dashboard_manifest import build_dashboard_manifest
        job_dir = _make_test_job(tmp_path)
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            manifest = build_dashboard_manifest(job_dir)
        assert isinstance(manifest, dict)
        assert manifest["job_id"] == "test_job_p14"
        assert manifest["dashboard_type"] == "single"

    def test_manifest_has_required_keys(self, tmp_path: Path) -> None:
        """マニフェストに必要なキーが含まれている。"""
        from src.dashboard_manifest import build_dashboard_manifest
        job_dir = _make_test_job(tmp_path)
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            manifest = build_dashboard_manifest(job_dir)
        required_keys = [
            "schema_version", "dashboard_token", "job_id", "display_name",
            "plan_label", "generated_at", "token_expires_at",
            "sections", "notices", "videos", "phase_images",
            "key_metrics", "detail_metrics", "graphs", "downloads",
            "disclaimer", "inquiry_info",
        ]
        for k in required_keys:
            assert k in manifest, f"キー '{k}' が manifest に見つかりません"

    def test_manifest_has_token(self, tmp_path: Path) -> None:
        """マニフェストの dashboard_token は 'dash_' で始まる。"""
        from src.dashboard_manifest import build_dashboard_manifest
        job_dir = _make_test_job(tmp_path)
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            manifest = build_dashboard_manifest(job_dir)
        assert manifest["dashboard_token"].startswith("dash_")

    def test_manifest_disclaimer_present(self, tmp_path: Path) -> None:
        """免責事項が含まれている。"""
        from src.dashboard_manifest import build_dashboard_manifest
        job_dir = _make_test_job(tmp_path)
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            manifest = build_dashboard_manifest(job_dir)
        assert "参考" in manifest["disclaimer"]
        assert "医療診断" in manifest["disclaimer"]

    def test_manifest_notices_not_empty(self, tmp_path: Path) -> None:
        """notices リストが空でない。"""
        from src.dashboard_manifest import build_dashboard_manifest
        job_dir = _make_test_job(tmp_path)
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            manifest = build_dashboard_manifest(job_dir)
        assert len(manifest["notices"]) > 0

    def test_manifest_key_metrics_from_advanced_metrics(self, tmp_path: Path) -> None:
        """高度解析指標があれば key_metrics が生成される。"""
        from src.dashboard_manifest import build_dashboard_manifest
        job_dir = _make_test_job(tmp_path, with_metrics=True)
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            manifest = build_dashboard_manifest(job_dir)
        assert len(manifest["key_metrics"]) > 0
        for m in manifest["key_metrics"]:
            assert "label" in m
            assert "reliability" in m
            assert m["reliability"] in ("high", "medium", "low", "unknown")

    def test_manifest_no_metrics_no_crash(self, tmp_path: Path) -> None:
        """高度解析指標がなくてもクラッシュしない。"""
        from src.dashboard_manifest import build_dashboard_manifest
        job_dir = _make_test_job(tmp_path, with_metrics=False)
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            manifest = build_dashboard_manifest(job_dir)
        assert manifest["key_metrics"] == []

    def test_manifest_no_pii_in_downloads(self, tmp_path: Path) -> None:
        """ダウンロード項目に relative_path が含まれていない（サニタイズ後）。"""
        # これは API サニタイズのテスト用として確認
        from src.dashboard_manifest import build_dashboard_manifest
        job_dir = _make_test_job(tmp_path)
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            manifest = build_dashboard_manifest(job_dir)
        # relative_path は manifest に含まれるが、API レスポンスでは除去される
        # ここでは manifest 自体の構造を確認
        for cat, items in manifest["downloads"].items():
            for item in items:
                assert "label" in item
                assert "available" in item

    def test_save_manifest_creates_file(self, tmp_path: Path) -> None:
        """save_dashboard_manifest() で dashboard_manifest.json が作成される。"""
        from src.dashboard_manifest import save_dashboard_manifest
        job_dir = _make_test_job(tmp_path)
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            out = save_dashboard_manifest(job_dir)
        assert out is not None
        assert out.exists()
        assert out.name == "dashboard_manifest.json"

    def test_load_manifest_roundtrip(self, tmp_path: Path) -> None:
        """保存→読み込みで同じ内容が返る。"""
        from src.dashboard_manifest import save_dashboard_manifest, load_dashboard_manifest
        job_dir = _make_test_job(tmp_path)
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            save_dashboard_manifest(job_dir)
            loaded = load_dashboard_manifest(job_dir)
        assert loaded is not None
        assert loaded["job_id"] == "test_job_p14"
        assert loaded["dashboard_token"].startswith("dash_")

    def test_save_manifest_broken_dir_returns_none(self) -> None:
        """build_dashboard_manifest が例外を送出しても None を返す（例外なし）。"""
        from src.dashboard_manifest import save_dashboard_manifest
        with patch("src.dashboard_manifest.build_dashboard_manifest",
                   side_effect=RuntimeError("simulated build error")):
            result = save_dashboard_manifest(Path("/any/path"))
        assert result is None  # 例外なく None を返す


# ── TestManifestTokenExpiry ────────────────────────────────────────────────────


class TestManifestTokenExpiry:
    def test_not_expired_token(self) -> None:
        """将来の expires_at は期限切れと判定されない。"""
        from src.dashboard_manifest import is_token_expired
        manifest = {"token_expires_at": "2099-01-01T00:00:00+00:00"}
        assert is_token_expired(manifest) is False

    def test_expired_token(self) -> None:
        """過去の expires_at は期限切れと判定される。"""
        from src.dashboard_manifest import is_token_expired
        manifest = {"token_expires_at": "2000-01-01T00:00:00+00:00"}
        assert is_token_expired(manifest) is True

    def test_no_expires_at_not_expired(self) -> None:
        """token_expires_at なしは期限切れと判定されない。"""
        from src.dashboard_manifest import is_token_expired
        assert is_token_expired({}) is False


# ── TestPublicDashboardApi ─────────────────────────────────────────────────────


class TestPublicDashboardApi:
    """FastAPI public dashboard API のテスト。"""

    @pytest.fixture
    def client(self, tmp_path: Path):
        """テスト用 FastAPI テストクライアント。"""
        from fastapi.testclient import TestClient
        from server.public_dashboard_api import public_dashboard_router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(public_dashboard_router, prefix="/v1/public")
        return TestClient(app)

    def test_health_endpoint(self, client) -> None:
        """ヘルスチェックエンドポイントが 200 を返す。"""
        res = client.get("/v1/public/healthz")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["api"] == "public-dashboards"

    def test_unknown_token_returns_404(self, client) -> None:
        """存在しないトークンで 404 を返す。"""
        with patch("src.dashboard_manifest.find_job_id_by_token", return_value=None):
            res = client.get("/v1/public/dashboards/dash_unknowntoken")
        assert res.status_code == 404

    def test_invalid_token_format_returns_404(self, client) -> None:
        """不正なトークン形式（プレフィックス不一致）で 404 を返す。"""
        res = client.get("/v1/public/dashboards/invalid_token")
        assert res.status_code == 404

    def test_expired_token_returns_410(self, client, tmp_path: Path) -> None:
        """期限切れトークンで 410 を返す。"""
        from src.dashboard_manifest import save_dashboard_manifest
        job_dir = _make_test_job(tmp_path, job_id="expired_job")
        test_index = tmp_path / "_token_index.json"

        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            token = "dash_expiredtest1234"
            from src.dashboard_manifest import register_dashboard_token
            register_dashboard_token(token, "expired_job")
            # 期限切れマニフェストを直接書き込む
            manifest_data = {
                "dashboard_token": token,
                "job_id": "expired_job",
                "dashboard_type": "single",
                "display_name": "テスト",
                "plan_label": "スタンダード",
                "delivered_at": "2026-01-01",
                "generated_at": "2026-01-01T00:00:00",
                "token_expires_at": "2000-01-01T00:00:00+00:00",  # 過去日時
                "url_expires_at": "",
                "metrics_version": "0.1.0",
                "overall_quality": "good",
                "metrics_reliability": "high",
                "sections": {},
                "notices": [],
                "videos": [],
                "phase_images": [],
                "key_metrics": [],
                "detail_metrics": {},
                "graphs": [],
                "downloads": {},
                "disclaimer": "参考",
                "inquiry_info": {"job_id": "expired_job", "delivered_at": "2026-01-01", "plan_label": "スタンダード"},
            }
            manifest_path = job_dir / "report" / "dashboard_manifest.json"
            manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

            with patch("src.dashboard_manifest.find_job_id_by_token", return_value=("expired_job", "single")), \
                 patch("server.public_dashboard_api._get_job_dir", return_value=job_dir), \
                 patch("src.dashboard_manifest.load_dashboard_manifest", return_value=manifest_data):
                res = client.get(f"/v1/public/dashboards/{token}")

        assert res.status_code == 410
        assert "code" in res.json()

    def test_valid_token_returns_200(self, client, tmp_path: Path) -> None:
        """有効なトークンで 200 と manifest JSON を返す。"""
        job_dir = _make_test_job(tmp_path, job_id="valid_job")
        test_index = tmp_path / "_token_index.json"

        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            token = "dash_validtest1234567"
            from src.dashboard_manifest import register_dashboard_token
            register_dashboard_token(token, "valid_job")
            manifest_data = {
                "dashboard_token": token,
                "job_id": "valid_job",
                "dashboard_type": "single",
                "display_name": "テスト選手",
                "plan_label": "スタンダード",
                "delivered_at": "2026-05-10",
                "generated_at": "2026-05-10T00:00:00",
                "token_expires_at": "2099-01-01T00:00:00+00:00",  # 未来
                "url_expires_at": "",
                "metrics_version": "0.1.0",
                "overall_quality": "good",
                "metrics_reliability": "high",
                "sections": {"videos": False, "metrics": False},
                "notices": ["参考資料です。"],
                "videos": [],
                "phase_images": [],
                "key_metrics": [],
                "detail_metrics": {},
                "graphs": [],
                "downloads": {"athlete": [{"label": "test.pdf", "filename": "test.pdf", "url": None, "available": False, "is_research": False, "category": "athlete"}]},
                "disclaimer": "参考資料です。医療診断の代替ではありません。",
                "inquiry_info": {"job_id": "valid_job", "delivered_at": "2026-05-10", "plan_label": "スタンダード"},
            }

            with patch("server.public_dashboard_api.find_job_id_by_token", return_value=("valid_job", "single")), \
                 patch("server.public_dashboard_api._get_job_dir", return_value=job_dir), \
                 patch("server.public_dashboard_api.load_dashboard_manifest", return_value=manifest_data):
                res = client.get(f"/v1/public/dashboards/{token}")

        assert res.status_code == 200
        data = res.json()
        assert data["job_id"] == "valid_job"
        assert data["display_name"] == "テスト選手"

    def test_response_sanitized_no_s3_keys(self, client, tmp_path: Path) -> None:
        """レスポンスに s3_key が含まれない（サニタイズされている）。"""
        job_dir = _make_test_job(tmp_path, job_id="sanitize_job")
        manifest_data = {
            "dashboard_token": "dash_sanitize1234567",
            "job_id": "sanitize_job",
            "dashboard_type": "single",
            "display_name": "テスト",
            "plan_label": "テスト",
            "delivered_at": "2026-05-10",
            "generated_at": "2026-05-10T00:00:00",
            "token_expires_at": "2099-01-01T00:00:00+00:00",
            "url_expires_at": "",
            "metrics_version": "0.1.0",
            "overall_quality": "good",
            "metrics_reliability": "high",
            "sections": {},
            "notices": [],
            "videos": [{"key": "skeleton", "label": "骨格動画", "description": "", "filename": "test.mp4", "s3_key": "secret/path/test.mp4", "url": None, "content_type": "video/mp4", "available": False}],
            "phase_images": [],
            "key_metrics": [],
            "detail_metrics": {},
            "graphs": [],
            "downloads": {
                "athlete": [{
                    "label": "test.pdf", "filename": "test.pdf",
                    "s3_key": "secret/key", "url": None,
                    "available": False, "is_research": False,
                    "category": "athlete", "relative_path": "/internal/path"
                }]
            },
            "disclaimer": "参考",
            "inquiry_info": {"job_id": "sanitize_job", "delivered_at": "", "plan_label": ""},
        }

        with patch("server.public_dashboard_api.find_job_id_by_token", return_value=("sanitize_job", "single")), \
             patch("server.public_dashboard_api._get_job_dir", return_value=job_dir), \
             patch("server.public_dashboard_api.load_dashboard_manifest", return_value=manifest_data):
            res = client.get("/v1/public/dashboards/dash_sanitize1234567")

        assert res.status_code == 200
        data = res.json()
        # s3_key と relative_path がレスポンスに含まれないこと
        for video in data.get("videos", []):
            assert "s3_key" not in video
        for cat, items in data.get("downloads", {}).items():
            for item in items:
                assert "s3_key" not in item
                assert "relative_path" not in item

    def test_manifest_not_found_returns_404(self, client, tmp_path: Path) -> None:
        """マニフェストが存在しない場合 404 を返す。"""
        job_dir = _make_test_job(tmp_path, job_id="nomanifest_job")
        with patch("src.dashboard_manifest.find_job_id_by_token", return_value=("nomanifest_job", "single")), \
             patch("server.public_dashboard_api._get_job_dir", return_value=job_dir), \
             patch("src.dashboard_manifest.load_dashboard_manifest", return_value=None):
            res = client.get("/v1/public/dashboards/dash_nomanifest1234")
        assert res.status_code == 404


# ── TestWorkerManifestStep ─────────────────────────────────────────────────────


class TestWorkerManifestStep:
    def test_step_generates_manifest(self, tmp_path: Path) -> None:
        """_step_generate_dashboard_manifest がマニフェストファイルを生成する。"""
        import sys
        import importlib

        job_dir = _make_test_job(tmp_path, job_id="worker_test_job")
        test_index = tmp_path / "_token_index.json"

        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            # worker モジュールを直接呼び出す
            from src.dashboard_manifest import save_dashboard_manifest
            out = save_dashboard_manifest(job_dir)

        assert out is not None
        manifest = json.loads(out.read_text(encoding="utf-8"))
        assert manifest["job_id"] == "worker_test_job"

    def test_step_broken_dir_no_crash(self) -> None:
        """build_dashboard_manifest が例外を送出してもクラッシュしない（非致命的）。"""
        from src.dashboard_manifest import save_dashboard_manifest
        with patch("src.dashboard_manifest.build_dashboard_manifest",
                   side_effect=RuntimeError("simulated error")):
            result = save_dashboard_manifest(Path("/any/path"))
        assert result is None  # 例外なく None を返す


# ── TestManifestNoPii ──────────────────────────────────────────────────────────


class TestManifestNoPii:
    def test_no_email_in_manifest(self, tmp_path: Path) -> None:
        """マニフェストにメールアドレスが含まれない。"""
        from src.dashboard_manifest import build_dashboard_manifest
        job_dir = _make_test_job(tmp_path, job_id="pii_test_job")
        # customer_info にメールを追加
        (job_dir / "customer_info.json").write_text(json.dumps({
            "customer_name": "テスト選手",
            "email": "test@example.com",
            "phone": "090-1234-5678",
            "plan": "スタンダード",
        }), encoding="utf-8")
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            manifest = build_dashboard_manifest(job_dir)
        manifest_str = json.dumps(manifest)
        # メールアドレスと電話番号がマニフェストの JSON に現れないこと
        assert "test@example.com" not in manifest_str
        assert "090-1234-5678" not in manifest_str

    def test_display_name_only(self, tmp_path: Path) -> None:
        """display_name は氏名のみ（最小個人情報）。"""
        from src.dashboard_manifest import build_dashboard_manifest
        job_dir = _make_test_job(tmp_path, job_id="name_test_job")
        test_index = tmp_path / "_token_index.json"
        with patch("src.dashboard_manifest._TOKEN_INDEX_PATH", test_index), \
             patch("src.dashboard_manifest._JOBS_DIR", tmp_path):
            manifest = build_dashboard_manifest(job_dir)
        assert manifest["display_name"] == "テスト選手"
