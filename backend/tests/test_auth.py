"""Tests for API Key authentication middleware."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.auth import verify_api_key

# ---------------------------------------------------------------------------
# Build a tiny test app that uses the auth dependency
# ---------------------------------------------------------------------------
app = FastAPI()


@app.get("/protected")
async def protected_route(api_key: str = pytest.importorskip("fastapi").Depends(verify_api_key)):
    return {"key": api_key}


VALID_KEYS = ["test-key-1", "test-key-2"]


@pytest.fixture()
def client():
    """TestClient with a patched settings.api_keys list."""
    with patch("backend.app.core.auth.settings") as mock_settings:
        mock_settings.api_keys = VALID_KEYS
        yield TestClient(app)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestApiKeyAuth:
    """Validates: Requirements 10.1, 1.7"""

    def test_valid_key_returns_200(self, client: TestClient):
        resp = client.get("/protected", headers={"X-API-Key": "test-key-1"})
        assert resp.status_code == 200
        assert resp.json()["key"] == "test-key-1"

    def test_second_valid_key_returns_200(self, client: TestClient):
        resp = client.get("/protected", headers={"X-API-Key": "test-key-2"})
        assert resp.status_code == 200
        assert resp.json()["key"] == "test-key-2"

    def test_missing_key_returns_401(self, client: TestClient):
        resp = client.get("/protected")
        assert resp.status_code == 401
        assert "Missing API Key" in resp.json()["detail"]

    def test_invalid_key_returns_401(self, client: TestClient):
        resp = client.get("/protected", headers={"X-API-Key": "bad-key"})
        assert resp.status_code == 401
        assert "Invalid API Key" in resp.json()["detail"]

    def test_empty_string_key_returns_401(self, client: TestClient):
        resp = client.get("/protected", headers={"X-API-Key": ""})
        assert resp.status_code == 401
