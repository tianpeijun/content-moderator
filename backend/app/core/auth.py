"""Authentication dependencies for FastAPI (API Key + Cognito JWT)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API Key authentication
# ---------------------------------------------------------------------------

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
) -> str:
    """Validate the API Key from the X-API-Key request header.

    Returns the validated key on success so downstream handlers can
    identify the caller if needed.

    Raises:
        HTTPException 401 when the key is missing or not in the
        configured allow-list.
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key: X-API-Key header is required",
        )

    if api_key not in settings.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    return api_key


# ---------------------------------------------------------------------------
# Cognito JWT authentication
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=False)

# Module-level JWKS cache to avoid fetching on every request.
_jwks_cache: dict[str, Any] | None = None


def _get_jwks_url() -> str:
    """Build the Cognito JWKS URL from settings."""
    region = settings.cognito_region
    pool_id = settings.cognito_user_pool_id
    return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json"


def _get_issuer() -> str:
    """Build the expected token issuer URL."""
    region = settings.cognito_region
    pool_id = settings.cognito_user_pool_id
    return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"


def _fetch_jwks() -> dict[str, Any]:
    """Fetch JWKS from Cognito, using a module-level cache."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    url = _get_jwks_url()
    try:
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        _jwks_cache = response.json()
        return _jwks_cache
    except Exception:
        logger.exception("Failed to fetch Cognito JWKS from %s", url)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to verify token: JWKS unavailable",
        )


def _find_signing_key(token: str, jwks: dict[str, Any]) -> dict[str, Any]:
    """Find the JWK that matches the token's kid header."""
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: unable to decode header",
        )

    kid = unverified_header.get("kid")
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token: signing key not found",
    )


async def verify_cognito_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict[str, Any]:
    """Validate a Cognito JWT Bearer token.

    Extracts the Bearer token from the Authorization header, verifies
    signature, expiration, audience and issuer against the Cognito
    User Pool JWKS.

    Returns the decoded token claims on success.

    Raises:
        HTTPException 401 when the token is missing, malformed,
        expired or otherwise invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    token = credentials.credentials
    jwks = _fetch_jwks()
    signing_key = _find_signing_key(token, jwks)

    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.cognito_app_client_id,
            issuer=_get_issuer(),
        )
    except JWTError as exc:
        logger.warning("Cognito token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return claims
