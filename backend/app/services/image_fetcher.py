"""Image fetcher supporting S3 and HTTP(S) sources."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import boto3
import httpx

logger = logging.getLogger(__name__)


class ImageFetcher:
    """Fetch image bytes from S3 or HTTP(S) URLs.

    Routing logic:
    - ``s3://bucket/key`` → AWS SDK (boto3)
    - ``http://`` / ``https://`` → async HTTP request (httpx)
    - Any other prefix → ``ValueError``
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

        - ``s3://`` prefix → :meth:`_fetch_from_s3`
        - ``http://`` or ``https://`` prefix → :meth:`_fetch_from_http`
        - Other prefixes → raises ``ValueError``

        **Validates: Requirements 1.4**
        """
        if image_url.startswith("s3://"):
            return await self._fetch_from_s3(image_url)
        if image_url.startswith("http://") or image_url.startswith("https://"):
            return await self._fetch_from_http(image_url)
        raise ValueError(
            f"Unsupported image URL scheme: {image_url!r}. "
            "Only s3://, http://, and https:// are supported."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_from_s3(self, url: str) -> bytes:
        """Download an object from S3.

        Expected format: ``s3://bucket-name/path/to/object``
        """
        parsed = urlparse(url)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError(
                f"Invalid S3 URL {url!r}: must be s3://bucket/key"
            )
        logger.info("Fetching image from S3: bucket=%s key=%s", bucket, key)
        response = self.s3_client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    async def _fetch_from_http(self, url: str) -> bytes:
        """Download an image via HTTP(S)."""
        logger.info("Fetching image from HTTP: %s", url)
        async with httpx.AsyncClient(
            timeout=self._http_timeout,
            follow_redirects=True,
            headers={"User-Agent": "ContentModerationBot/1.0"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
