"""Image fetcher supporting S3 and HTTP(S) sources.

All fetch failures are wrapped in :class:`ImageFetchError` (with subclasses)
so the API layer can distinguish client-side errors (400) from server errors (500).
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import boto3
import httpx
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class ImageFetchError(Exception):
    """Base class for all image-fetch failures.

    Subclasses distinguish failure modes so the API layer can choose
    the right HTTP status code.
    """

    def __init__(self, message: str, *, url: str | None = None):
        super().__init__(message)
        self.url = url


class ImageFetchClientError(ImageFetchError, ValueError):
    """Client-side failure: invalid URL, 4xx response, unsupported scheme.

    The API layer should translate this to HTTP 400.

    Inherits from ``ValueError`` for backwards compatibility with existing
    callers that caught ``ValueError`` from invalid URLs.
    """


class ImageFetchServerError(ImageFetchError):
    """Server-side / network failure: timeout, connection error, 5xx response.

    The API layer should translate this to HTTP 502 (bad upstream).
    """


class ImageFetcher:
    """Fetch image bytes from S3 or HTTP(S) URLs.

    Routing logic:
    - ``s3://bucket/key`` → AWS SDK (boto3)
    - ``http://`` / ``https://`` → async HTTP request (httpx)
    - Any other prefix → :class:`ImageFetchClientError`
    """

    def __init__(self, s3_client=None, http_timeout: float = 30.0):
        self._s3_client = s3_client
        self._http_timeout = http_timeout

    @property
    def s3_client(self):
        """Lazily initialise the boto3 S3 client."""
        if self._s3_client is None:
            self._s3_client = boto3.client("s3")
        return self._s3_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch(self, image_url: str) -> bytes:
        """Fetch image binary content based on URL prefix.

        Raises:
            ImageFetchClientError: bad URL, 4xx response, unsupported scheme
            ImageFetchServerError: timeout, network failure, 5xx response

        **Validates: Requirements 1.4**
        """
        if image_url.startswith("s3://"):
            return await self._fetch_from_s3(image_url)
        if image_url.startswith("http://") or image_url.startswith("https://"):
            return await self._fetch_from_http(image_url)
        raise ImageFetchClientError(
            f"Unsupported image URL scheme: {image_url!r}. "
            "Only s3://, http://, and https:// are supported.",
            url=image_url,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_from_s3(self, url: str) -> bytes:
        """Download an object from S3."""
        parsed = urlparse(url)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise ImageFetchClientError(
                f"Invalid S3 URL {url!r}: must be s3://bucket/key",
                url=url,
            )
        logger.info("Fetching image from S3: bucket=%s key=%s", bucket, key)
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            # NoSuchKey / NoSuchBucket → client-side (bad URL)
            if code in ("NoSuchKey", "NoSuchBucket", "404", "NotFound"):
                raise ImageFetchClientError(
                    f"S3 object not found: {url}", url=url,
                ) from exc
            # AccessDenied / permission → server-side (our IAM issue)
            raise ImageFetchServerError(
                f"S3 fetch failed ({code}): {exc}", url=url,
            ) from exc

    async def _fetch_from_http(self, url: str) -> bytes:
        """Download an image via HTTP(S).

        Translates httpx errors:
        - 4xx status → :class:`ImageFetchClientError`
        - 5xx / timeout / connection error → :class:`ImageFetchServerError`
        """
        logger.info("Fetching image from HTTP: %s", url)
        try:
            async with httpx.AsyncClient(
                timeout=self._http_timeout,
                follow_redirects=True,
                headers={"User-Agent": "ContentModerationBot/1.0"},
            ) as client:
                response = await client.get(url)
        except httpx.TimeoutException as exc:
            raise ImageFetchServerError(
                f"Image fetch timed out after {self._http_timeout}s: {url}",
                url=url,
            ) from exc
        except httpx.RequestError as exc:
            # DNS failure, connection refused, SSL error, etc.
            raise ImageFetchServerError(
                f"Image fetch network error: {exc.__class__.__name__}: {exc}",
                url=url,
            ) from exc

        status = response.status_code
        if 400 <= status < 500:
            raise ImageFetchClientError(
                f"Image URL returned HTTP {status}: {url}",
                url=url,
            )
        if status >= 500:
            raise ImageFetchServerError(
                f"Image source returned HTTP {status}: {url}",
                url=url,
            )
        return response.content
