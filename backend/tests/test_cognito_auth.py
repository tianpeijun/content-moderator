"""Tests for Cognito JWT authentication middleware.

Validates: Requirements 10.2, 10.3
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from backend.app.core.auth import verify_cognito_token

# ---------------------------------------------------------------------------
# Helpers — RSA key pair for signing test JWTs
# ---------------------------------------------------------------------------

# We use python-jose to generate a minimal RSA key pair at module level so
# tests can create properly signed tokens without hitting real Cognito.
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

_private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend(),
)
_private_pem = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_public_key = _private_key.public_key()
_public_numbers = _public_key.public_numbers()

TEST_KID = "test-kid-001"
TEST_REGION = "us-east-1"
TEST_POOL_ID = "us-east-1_TestPool"
TEST_CLIENT_ID = "test-client-id"
TEST_ISSUER = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_POOL_ID}"


def _int_to_base64url(n: int) -> str:
    """Convert a large integer to a base64url-encoded string (JWK format)."""
    import base64
    byte_length = (n.bit_length() + 7) // 8
    raw = n.to_bytes(byte_length, byteorder="big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


FAKE_JWKS: dict[str, Any] = {
    "keys": [
        {
            "kty": "RSA",
            "kid": TEST_KID,
            "use": "sig",
            "alg": "RS256",
            "n": _int_to_base64url(_public_numbers.n),
            "e": _int_to_base64url(_public_numbers.e),
        }
    ]
}


def _make_token(
    claims: dict[str, Any] | None = None,
    kid: str = TEST_KID,
    expired: bool = False,
) -> str:
    """Create a signed JWT with the test RSA key."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": "user-123",
        "iss": TEST_ISSUER,
        "aud": TEST_CLIENT_ID,
        "iat": now,
        "exp": now - 10 if expired else now + 3600,
        "token_use": "id",
    }
    if claims:
        payload.update(claims)
    return jwt.encode(payload, _private_pem, algorithm="RS256", headers={"kid": kid})


# ---------------------------------------------------------------------------
# Test app & fixtures
# ---------------------------------------------------------------------------

app = FastAPI()


@app.get("/admin")
async def admin_route(claims: dict = pytest.importorskip("fastapi").Depends(verify_cognito_token)):
    return {"sub": claims.get("sub")}


@pytest.fixture(autouse=True)
def _reset_jwks_cache():
    """Clear the module-level JWKS cache before each test."""
    import backend.app.core.auth as auth_mod
    auth_mod._jwks_cache = None
    yield
    auth_mod._jwks_cache = None


@pytest.fixture()
def client():
    """TestClient with patched Cognito settings and JWKS fetch."""
    with (
        patch("backend.app.core.auth.settings") as mock_settings,
        patch("backend.app.core.auth._fetch_jwks", return_value=FAKE_JWKS),
    ):
        mock_settings.cognito_region = TEST_REGION
        mock_settings.cognito_user_pool_id = TEST_POOL_ID
        mock_settings.cognito_app_client_id = TEST_CLIENT_ID
        yield TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCognitoAuth:
    """Validates: Requirements 10.2, 10.3"""

    def test_missing_authorization_header_returns_401(self, client: TestClient):
        """No Authorization header → 401."""
        resp = client.get("/admin")
        assert resp.status_code == 401
        assert "Missing Authorization header" in resp.json()["detail"]

    def test_invalid_token_format_returns_401(self, client: TestClient):
        """Garbage token string → 401."""
        resp = client.get("/admin", headers={"Authorization": "Bearer not-a-real-jwt"})
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, client: TestClient):
        """Properly signed but expired token → 401."""
        token = _make_token(expired=True)
        resp = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "Invalid or expired token" in resp.json()["detail"]

    def test_wrong_audience_returns_401(self, client: TestClient):
        """Token with wrong audience claim → 401."""
        token = _make_token(claims={"aud": "wrong-client-id"})
        resp = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_wrong_kid_returns_401(self, client: TestClient):
        """Token signed with unknown kid → 401."""
        token = _make_token(kid="unknown-kid")
        resp = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "signing key not found" in resp.json()["detail"]

    def test_valid_token_returns_claims(self, client: TestClient):
        """Properly signed, non-expired token → 200 with claims."""
        token = _make_token()
        resp = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["sub"] == "user-123"

    def test_valid_token_with_custom_claims(self, client: TestClient):
        """Token with extra claims → all claims accessible."""
        token = _make_token(claims={"email": "test@example.com", "sub": "user-456"})
        resp = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["sub"] == "user-456"
