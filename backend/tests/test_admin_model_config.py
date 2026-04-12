"""Tests for Admin Model Config API.

Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models.model_config import ModelConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_CLAIMS = {"sub": "user-123", "username": "admin"}
NOW = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_config(**overrides) -> MagicMock:
    """Build a mock ModelConfig object."""
    defaults = dict(
        id=uuid.uuid4(),
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        model_name="Claude 3 Sonnet",
        temperature=0.0,
        max_tokens=1024,
        is_primary=True,
        is_fallback=False,
        fallback_result=None,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        updated_at=NOW,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=ModelConfig)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _patch_auth():
    """Bypass Cognito auth — return fake claims."""
    from backend.app.core.auth import verify_cognito_token

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
# Tests — GET /api/admin/model-config (Requirements 7.1, 7.5)
# ---------------------------------------------------------------------------

class TestListModelConfigs:
    """Validates: Requirements 7.1, 7.5 — list model configs with cost info."""

    def test_list_configs_returns_200(self, client: TestClient, mock_db):
        cfg = _make_config()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [cfg]
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/model-config")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["model_name"] == "Claude 3 Sonnet"
        assert data[0]["is_primary"] is True
        assert data[0]["cost_per_1k_input"] == 0.003

    def test_list_configs_empty(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/model-config")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_configs_multiple(self, client: TestClient, mock_db):
        cfg1 = _make_config(model_name="Claude 3 Sonnet", is_primary=True)
        cfg2 = _make_config(model_name="Claude 3 Haiku", is_primary=False, is_fallback=True)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [cfg1, cfg2]
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/model-config")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


# ---------------------------------------------------------------------------
# Tests — PUT /api/admin/model-config/{config_id} (Requirements 7.2, 7.3, 7.4)
# ---------------------------------------------------------------------------

class TestUpdateModelConfig:
    """Validates: Requirements 7.2, 7.3, 7.4 — update model config."""

    def test_update_config_returns_200(self, client: TestClient, mock_db):
        config_id = uuid.uuid4()
        cfg = _make_config(id=config_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = cfg
        mock_db.execute.return_value = mock_result
        mock_db.refresh = MagicMock()

        resp = client.put(
            f"/api/admin/model-config/{config_id}",
            json={"temperature": 0.5},
        )
        assert resp.status_code == 200
        mock_db.commit.assert_called_once()

    def test_update_config_applies_fields(self, client: TestClient, mock_db):
        config_id = uuid.uuid4()
        cfg = _make_config(id=config_id, temperature=0.0, max_tokens=1024)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = cfg
        mock_db.execute.return_value = mock_result
        mock_db.refresh = MagicMock()

        resp = client.put(
            f"/api/admin/model-config/{config_id}",
            json={"temperature": 0.7, "max_tokens": 2048},
        )
        assert resp.status_code == 200
        assert cfg.temperature == 0.7
        assert cfg.max_tokens == 2048

    def test_update_primary_and_fallback(self, client: TestClient, mock_db):
        """Validates: Requirement 7.3 — configure primary/fallback models."""
        config_id = uuid.uuid4()
        cfg = _make_config(id=config_id, is_primary=False, is_fallback=False)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = cfg
        mock_db.execute.return_value = mock_result
        mock_db.refresh = MagicMock()

        resp = client.put(
            f"/api/admin/model-config/{config_id}",
            json={"is_primary": True, "fallback_result": "review"},
        )
        assert resp.status_code == 200
        assert cfg.is_primary is True
        assert cfg.fallback_result == "review"

    def test_update_nonexistent_config_returns_404(self, client: TestClient, mock_db):
        config_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.put(
            f"/api/admin/model-config/{config_id}",
            json={"temperature": 0.5},
        )
        assert resp.status_code == 404

    def test_update_config_invalid_temperature_returns_422(self, client: TestClient, mock_db):
        """Temperature must be between 0.0 and 2.0."""
        config_id = uuid.uuid4()
        resp = client.put(
            f"/api/admin/model-config/{config_id}",
            json={"temperature": 5.0},
        )
        # FastAPI validation error — 400 (via exception handler) or 422
        assert resp.status_code in (400, 422)

    def test_update_config_invalid_max_tokens_returns_422(self, client: TestClient, mock_db):
        """max_tokens must be >= 1."""
        config_id = uuid.uuid4()
        resp = client.put(
            f"/api/admin/model-config/{config_id}",
            json={"max_tokens": 0},
        )
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Tests — Auth (Requirement 10.2)
# ---------------------------------------------------------------------------

class TestModelConfigAuth:
    """Validates: Requirement 10.2 — Cognito auth required."""

    def test_missing_auth_returns_401(self, mock_db):
        """Without Cognito token override, endpoints should return 401."""
        app.dependency_overrides.pop(
            __import__(
                "backend.app.core.auth", fromlist=["verify_cognito_token"]
            ).verify_cognito_token,
            None,
        )
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.get("/api/admin/model-config")
            assert resp.status_code == 401
