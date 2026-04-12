"""Tests for Admin Statistics API.

Validates: Requirements 8.1, 8.2, 8.3
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.core.auth import verify_cognito_token
from backend.app.core.database import get_db
from backend.app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_CLAIMS = {"sub": "user-123", "username": "admin"}


def _row(**kwargs):
    """Create a mock row object with named attributes."""
    m = MagicMock()
    for k, v in kwargs.items():
        setattr(m, k, v)
    # Support tuple-style access used by SQLAlchemy Row
    m.__iter__ = lambda self: iter(kwargs.values())
    return m


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _patch_auth():
    app.dependency_overrides[verify_cognito_token] = lambda: FAKE_CLAIMS
    yield
    app.dependency_overrides.pop(verify_cognito_token, None)


@pytest.fixture()
def mock_db():
    session = MagicMock()
    app.dependency_overrides[get_db] = lambda: session
    yield session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(_patch_auth, mock_db):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests — GET /api/admin/stats/volume (Requirement 8.1)
# ---------------------------------------------------------------------------


class TestVolumeStats:
    """Validates: Requirement 8.1 — audit volume trend statistics."""

    def test_volume_returns_200_with_data(self, client: TestClient, mock_db):
        row = _row(
            period="2024-06-15",
            total=10,
            pass_count=5,
            reject_count=3,
            review_count=1,
            flag_count=1,
        )
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_db.execute.return_value = mock_result

        resp = client.get(
            "/api/admin/stats/volume",
            params={"granularity": "day", "start_date": "2024-06-01", "end_date": "2024-06-30"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["granularity"] == "day"
        assert len(body["data"]) == 1
        dp = body["data"][0]
        assert dp["period"] == "2024-06-15"
        assert dp["total"] == 10
        assert dp["pass_count"] == 5
        assert dp["reject_count"] == 3
        assert dp["review_count"] == 1
        assert dp["flag_count"] == 1

    def test_volume_empty_data(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/stats/volume")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []

    def test_volume_default_granularity_is_day(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/stats/volume")
        assert resp.status_code == 200
        assert resp.json()["granularity"] == "day"

    def test_volume_week_granularity(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/stats/volume", params={"granularity": "week"})
        assert resp.status_code == 200
        assert resp.json()["granularity"] == "week"

    def test_volume_month_granularity(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/stats/volume", params={"granularity": "month"})
        assert resp.status_code == 200
        assert resp.json()["granularity"] == "month"

    def test_volume_invalid_granularity_returns_422(self, client: TestClient, mock_db):
        resp = client.get("/api/admin/stats/volume", params={"granularity": "year"})
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Tests — GET /api/admin/stats/rule-hits (Requirement 8.2)
# ---------------------------------------------------------------------------


class TestRuleHitsStats:
    """Validates: Requirement 8.2 — rule hit rate statistics."""

    def test_rule_hits_returns_200_with_data(self, client: TestClient, mock_db):
        rule_id = str(uuid.uuid4())

        # First call: total count
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 10

        # Second call: logs with matched_rules
        mock_logs = MagicMock()
        mock_logs.scalars.return_value.all.return_value = [
            [{"rule_id": rule_id, "rule_name": "违禁词检测", "action": "reject"}],
            [{"rule_id": rule_id, "rule_name": "违禁词检测", "action": "reject"}],
        ]

        # Third call: rule name lookup
        rule_row = _row(id=uuid.UUID(rule_id), name="违禁词检测")
        mock_rules = MagicMock()
        mock_rules.all.return_value = [rule_row]

        mock_db.execute.side_effect = [mock_count, mock_logs, mock_rules]

        resp = client.get(
            "/api/admin/stats/rule-hits",
            params={"start_date": "2024-06-01", "end_date": "2024-06-30"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_moderation_count"] == 10
        assert len(body["rules"]) == 1
        assert body["rules"][0]["rule_id"] == rule_id
        assert body["rules"][0]["hit_count"] == 2
        assert body["rules"][0]["hit_rate"] == 0.2

    def test_rule_hits_empty_when_no_logs(self, client: TestClient, mock_db):
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_db.execute.return_value = mock_count

        resp = client.get("/api/admin/stats/rule-hits")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_moderation_count"] == 0
        assert body["rules"] == []

    def test_rule_hits_handles_null_matched_rules(self, client: TestClient, mock_db):
        """Logs with None matched_rules should be skipped gracefully."""
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 5

        mock_logs = MagicMock()
        mock_logs.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_count, mock_logs]

        resp = client.get("/api/admin/stats/rule-hits")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_moderation_count"] == 5
        assert body["rules"] == []


# ---------------------------------------------------------------------------
# Tests — GET /api/admin/stats/cost (Requirement 8.3)
# ---------------------------------------------------------------------------


class TestCostStats:
    """Validates: Requirement 8.3 — model invocation cost statistics."""

    def test_cost_returns_200_with_data(self, client: TestClient, mock_db):
        row = _row(period="2024-06-15", model_id="anthropic.claude-3-sonnet", call_count=100)
        cfg_row = _row(
            model_id="anthropic.claude-3-sonnet",
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015,
        )

        # First call: aggregated rows
        mock_rows = MagicMock()
        mock_rows.all.return_value = [row]

        # Second call: model configs
        mock_configs = MagicMock()
        mock_configs.all.return_value = [cfg_row]

        mock_db.execute.side_effect = [mock_rows, mock_configs]

        resp = client.get(
            "/api/admin/stats/cost",
            params={"start_date": "2024-06-01", "end_date": "2024-06-30"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        dp = body["data"][0]
        assert dp["model_id"] == "anthropic.claude-3-sonnet"
        assert dp["call_count"] == 100
        assert dp["estimated_cost"] > 0
        assert body["total_cost"] > 0

    def test_cost_empty_when_no_data(self, client: TestClient, mock_db):
        mock_rows = MagicMock()
        mock_rows.all.return_value = []
        mock_configs = MagicMock()
        mock_configs.all.return_value = []

        mock_db.execute.side_effect = [mock_rows, mock_configs]

        resp = client.get("/api/admin/stats/cost")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["total_cost"] == 0.0

    def test_cost_unknown_model_uses_zero_cost(self, client: TestClient, mock_db):
        """If model_id is not in model_config, cost should be 0."""
        row = _row(period="2024-06-15", model_id="unknown-model", call_count=50)

        mock_rows = MagicMock()
        mock_rows.all.return_value = [row]
        mock_configs = MagicMock()
        mock_configs.all.return_value = []

        mock_db.execute.side_effect = [mock_rows, mock_configs]

        resp = client.get("/api/admin/stats/cost")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["estimated_cost"] == 0.0
        assert body["total_cost"] == 0.0


# ---------------------------------------------------------------------------
# Tests — Auth (Requirement 10.2)
# ---------------------------------------------------------------------------


class TestAdminStatsAuth:
    """Validates: Requirement 10.2 — Cognito auth required for all stats endpoints."""

    def test_volume_without_auth_returns_401(self, mock_db):
        app.dependency_overrides.pop(verify_cognito_token, None)
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.get("/api/admin/stats/volume")
            assert resp.status_code == 401

    def test_rule_hits_without_auth_returns_401(self, mock_db):
        app.dependency_overrides.pop(verify_cognito_token, None)
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.get("/api/admin/stats/rule-hits")
            assert resp.status_code == 401

    def test_cost_without_auth_returns_401(self, mock_db):
        app.dependency_overrides.pop(verify_cognito_token, None)
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.get("/api/admin/stats/cost")
            assert resp.status_code == 401
