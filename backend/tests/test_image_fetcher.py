"""Tests for ImageFetcher URL routing and fetch behaviour."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.image_fetcher import ImageFetcher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_s3_client():
    """Return a mock boto3 S3 client that returns dummy image bytes."""
    client = MagicMock()
    body = MagicMock()
    body.read.return_value = b"fake-s3-image-bytes"
    client.get_object.return_value = {"Body": body}
    return client


@pytest.fixture
def fetcher(mock_s3_client):
    """ImageFetcher wired with a mock S3 client."""
    return ImageFetcher(s3_client=mock_s3_client)


# ---------------------------------------------------------------------------
# S3 routing
# ---------------------------------------------------------------------------

class TestS3Fetch:
    async def test_s3_url_routes_to_s3_client(self, fetcher, mock_s3_client):
        result = await fetcher.fetch("s3://my-bucket/images/photo.jpg")
        assert result == b"fake-s3-image-bytes"
        mock_s3_client.get_object.assert_called_once_with(
            Bucket="my-bucket", Key="images/photo.jpg"
        )

    async def test_s3_url_nested_key(self, fetcher, mock_s3_client):
        await fetcher.fetch("s3://bucket/a/b/c/d.png")
        mock_s3_client.get_object.assert_called_once_with(
            Bucket="bucket", Key="a/b/c/d.png"
        )

    async def test_s3_url_missing_key_raises(self, fetcher):
        with pytest.raises(ValueError, match="Invalid S3 URL"):
            await fetcher.fetch("s3://bucket-only/")

    async def test_s3_url_missing_bucket_raises(self, fetcher):
        with pytest.raises(ValueError, match="Invalid S3 URL"):
            await fetcher.fetch("s3:///key-only")


# ---------------------------------------------------------------------------
# HTTP routing
# ---------------------------------------------------------------------------

class TestHttpFetch:
    async def test_http_url_routes_to_http_client(self, fetcher):
        with patch("backend.app.services.image_fetcher.httpx.AsyncClient") as mock_cls:
            mock_response = MagicMock()
            mock_response.content = b"http-image-bytes"
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await fetcher.fetch("http://example.com/image.jpg")
            assert result == b"http-image-bytes"
            mock_client.get.assert_called_once_with("http://example.com/image.jpg")

    async def test_https_url_routes_to_http_client(self, fetcher):
        with patch("backend.app.services.image_fetcher.httpx.AsyncClient") as mock_cls:
            mock_response = MagicMock()
            mock_response.content = b"https-image-bytes"
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await fetcher.fetch("https://cdn.example.com/pic.png")
            assert result == b"https-image-bytes"


# ---------------------------------------------------------------------------
# Invalid schemes
# ---------------------------------------------------------------------------

class TestInvalidScheme:
    async def test_ftp_raises_value_error(self, fetcher):
        with pytest.raises(ValueError, match="Unsupported image URL scheme"):
            await fetcher.fetch("ftp://server/file.jpg")

    async def test_empty_string_raises_value_error(self, fetcher):
        with pytest.raises(ValueError, match="Unsupported image URL scheme"):
            await fetcher.fetch("")

    async def test_random_string_raises_value_error(self, fetcher):
        with pytest.raises(ValueError, match="Unsupported image URL scheme"):
            await fetcher.fetch("not-a-url")

    async def test_data_uri_raises_value_error(self, fetcher):
        with pytest.raises(ValueError, match="Unsupported image URL scheme"):
            await fetcher.fetch("data:image/png;base64,abc")


# ---------------------------------------------------------------------------
# Error mapping: 4xx → client error, 5xx/timeout → server error
# ---------------------------------------------------------------------------

class TestErrorMapping:
    """Verify that HTTP/network failures are mapped to the correct exception
    subclass so the API layer can choose 400 vs 502 / 500 appropriately."""

    async def test_http_404_raises_client_error(self, fetcher):
        from backend.app.services.image_fetcher import ImageFetchClientError

        with patch("backend.app.services.image_fetcher.httpx.AsyncClient") as mock_cls:
            mock_response = MagicMock()
            mock_response.status_code = 404

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(ImageFetchClientError, match="HTTP 404"):
                await fetcher.fetch("https://example.com/missing.jpg")

    async def test_http_429_raises_client_error(self, fetcher):
        """429 (rate-limited) is a client-side category (bad request from caller)."""
        from backend.app.services.image_fetcher import ImageFetchClientError

        with patch("backend.app.services.image_fetcher.httpx.AsyncClient") as mock_cls:
            mock_response = MagicMock()
            mock_response.status_code = 429

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(ImageFetchClientError, match="HTTP 429"):
                await fetcher.fetch("https://example.com/limited.jpg")

    async def test_http_500_raises_server_error(self, fetcher):
        from backend.app.services.image_fetcher import ImageFetchServerError

        with patch("backend.app.services.image_fetcher.httpx.AsyncClient") as mock_cls:
            mock_response = MagicMock()
            mock_response.status_code = 503

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(ImageFetchServerError, match="HTTP 503"):
                await fetcher.fetch("https://example.com/down.jpg")

    async def test_http_timeout_raises_server_error(self, fetcher):
        import httpx
        from backend.app.services.image_fetcher import ImageFetchServerError

        with patch("backend.app.services.image_fetcher.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(ImageFetchServerError, match="timed out"):
                await fetcher.fetch("https://example.com/slow.jpg")

    async def test_http_connection_error_raises_server_error(self, fetcher):
        import httpx
        from backend.app.services.image_fetcher import ImageFetchServerError

        with patch("backend.app.services.image_fetcher.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(ImageFetchServerError, match="network error"):
                await fetcher.fetch("https://example.com/unreachable.jpg")

    async def test_s3_missing_key_raises_client_error(self, fetcher, mock_s3_client):
        from botocore.exceptions import ClientError
        from backend.app.services.image_fetcher import ImageFetchClientError

        mock_s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "The key does not exist"}},
            "GetObject",
        )
        with pytest.raises(ImageFetchClientError, match="not found"):
            await fetcher.fetch("s3://bucket/missing.jpg")
