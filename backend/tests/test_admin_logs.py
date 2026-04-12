"""Tests for Admin Audit Logs API.

Validates: Requirements 5.1, 5.2, 5.3
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.app.core.auth import verify_cognito_token
from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models.moderation_logs import ModerationLog

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_CLAIMS = {"sub": "user-123", "username": "admin"}
NOW = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)


def _make_log(**overrides) -> MagicMock:
    """Build a mock ModerationLog object."""
    defaults = dict(
        id=uuid.uuid4(),
        task_id=str(uuid.uuid4()),
        status="completed",
        input_text="这是一条测试评论",
        input_image_url=None,
        business_type="商品评论",
        final_prompt="请审核以下内容...",
        model_response='{"result": "pass"}',
        result="pass",
        confidence=0.95,
        matched_rules=[],
        processing_time_ms=1200,
        degraded=False,
        model_id="anthropic.claude-3-sonnet",
        created_at=NOW,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=ModerationLog)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _patch_auth():
    """Bypass Cognito auth — return fake claims."""
    app.dependency_overrides[verify_cognito_token] = lambda: FAKE_CLAIMS
    yield
    app.dependency_overrides.pop(verify_cognito_token, None)


@pytest.fixture()
def mock_db():
    """Provide a mock DB session."""
    session = MagicMock()
    app.dependency_overrides[get_db] = lambda: session
    yield session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(_patch_auth, mock_db):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests — GET /api/admin/logs (Requirement 5.1)
# ---------------------------------------------------------------------------


class TestListLogs:
    """Validates: Requirement 5.1 — list logs with filtering and pagination."""

    def test_list_logs_returns_200(self, client: TestClient, mock_db):
        log = _make_log()
        # count query
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        # data query
        mock_data = MagicMock()
        mock_data.scalars.return_value.all.return_value = [log]

        mock_db.execute.side_effect = [mock_count, mock_data]

        resp = client.get("/api/admin/logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["page_size"] == 20
        assert len(body["items"]) == 1
        assert body["items"][0]["task_id"] == log.task_id
        assert body["items"][0]["status"] == "completed"

    def test_list_logs_empty(self, client: TestClient, mock_db):
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_data = MagicMock()
        mock_data.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_count, mock_data]

        resp = client.get("/api/admin/logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_list_logs_with_filters(self, client: TestClient, mock_db):
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_data = MagicMock()
        mock_data.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_count, mock_data]

        resp = client.get(
            "/api/admin/logs",
            params={
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-12-31T23:59:59Z",
                "result": "reject",
                "business_type": "商品评论",
            },
        )
        assert resp.status_code == 200

    def test_list_logs_pagination(self, client: TestClient, mock_db):
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 50
        mock_data = MagicMock()
        mock_data.scalars.return_value.all.return_value = [_make_log() for _ in range(10)]

        mock_db.execute.side_effect = [mock_count, mock_data]

        resp = client.get("/api/admin/logs?page=2&page_size=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 50
        assert body["page"] == 2
        assert body["page_size"] == 10

    def test_list_logs_invalid_page_returns_422(self, client: TestClient, mock_db):
        resp = client.get("/api/admin/logs?page=0")
        assert resp.status_code in (400, 422)

    def test_list_logs_page_size_too_large_returns_422(self, client: TestClient, mock_db):
        resp = client.get("/api/admin/logs?page_size=200")
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Tests — GET /api/admin/logs/{log_id} (Requirement 5.2)
# ---------------------------------------------------------------------------


class TestGetLogDetail:
    """Validates: Requirement 5.2 — log detail with full content."""

    def test_get_log_detail_returns_200(self, client: TestClient, mock_db):
        log_id = uuid.uuid4()
        log = _make_log(id=log_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = log
        mock_db.execute.return_value = mock_result

        resp = client.get(f"/api/admin/logs/{log_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(log_id)
        assert body["input_text"] == "这是一条测试评论"
        assert body["final_prompt"] == "请审核以下内容..."
        assert body["model_response"] == '{"result": "pass"}'
        assert body["matched_rules"] == []
        assert body["degraded"] is False

    def test_get_log_detail_not_found(self, client: TestClient, mock_db):
        log_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.get(f"/api/admin/logs/{log_id}")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_log_detail_invalid_uuid(self, client: TestClient, mock_db):
        resp = client.get("/api/admin/logs/not-a-uuid")
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Tests — POST /api/admin/logs/export (Requirement 5.3)
# ---------------------------------------------------------------------------


class TestExportLogs:
    """Validates: Requirement 5.3 — export filtered logs."""

    def test_export_logs_returns_200(self, client: TestClient, mock_db):
        logs = [_make_log(), _make_log()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = logs
        mock_db.execute.return_value = mock_result

        resp = client.post("/api/admin/logs/export")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_export_logs_with_filters(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = client.post(
            "/api/admin/logs/export",
            params={
                "result": "pass",
                "business_type": "商品评论",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_export_logs_includes_full_detail(self, client: TestClient, mock_db):
        log = _make_log()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [log]
        mock_db.execute.return_value = mock_result

        resp = client.post("/api/admin/logs/export")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        # Export should include full detail fields
        assert "input_text" in item
        assert "final_prompt" in item
        assert "model_response" in item
        assert "matched_rules" in item


# ---------------------------------------------------------------------------
# Tests — Auth (Requirement 10.2)
# ---------------------------------------------------------------------------


class TestAdminLogsAuth:
    """Validates: Requirement 10.2 — Cognito auth required for all log endpoints."""

    def test_list_logs_without_auth_returns_401(self, mock_db):
        from unittest.mock import patch

        app.dependency_overrides.pop(verify_cognito_token, None)
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.get("/api/admin/logs")
            assert resp.status_code == 401

    def test_get_log_detail_without_auth_returns_401(self, mock_db):
        from unittest.mock import patch

        app.dependency_overrides.pop(verify_cognito_token, None)
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.get(f"/api/admin/logs/{uuid.uuid4()}")
            assert resp.status_code == 401

    def test_export_logs_without_auth_returns_401(self, mock_db):
        from unittest.mock import patch

        app.dependency_overrides.pop(verify_cognito_token, None)
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.post("/api/admin/logs/export")
            assert resp.status_code == 401
