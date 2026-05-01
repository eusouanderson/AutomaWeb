"""Copilot HTTP Client with Retry Logic"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# Types
# ============================================================================

HTTPFetcher = Callable[
    [str | httpx.URL, Optional[dict]],
    httpx.AsyncClient | httpx.Response,
]


# ============================================================================
# Retry Configuration
# ============================================================================

DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_DELAY_MS = 600
DEFAULT_RETRY_STATUS_CODES = [408, 425, 429, 500, 502, 503, 504]
DEFAULT_USER_AGENT = "mcp-frontend-copilot/1.0"


# ============================================================================
# Utility Functions
# ============================================================================


def is_network_error(error: Exception) -> bool:
    """Check if error is a network-related error."""
    return isinstance(error, (OSError, httpx.NetworkError))


async def delay_ms(milliseconds: int) -> None:
    """Async sleep for milliseconds."""
    await asyncio.sleep(milliseconds / 1000.0)


def should_retry_status(status: int, retry_status_codes: list[int]) -> bool:
    """Check if status code should trigger a retry."""
    return status in retry_status_codes


def can_retry_body(body: Optional[dict]) -> bool:
    """Check if request body can be replayed."""
    # Streaming bodies cannot be retried
    return not isinstance(body, (httpx.ByteStream,))


# ============================================================================
# HTTP Client Factory with Retry
# ============================================================================


class CopilotHTTPClient:
    """HTTP client for Copilot API with retry logic and token management."""

    def __init__(
        self,
        auth_manager: "CopilotAuthManager",  # type: ignore
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay_ms: int = DEFAULT_RETRY_DELAY_MS,
        retry_status_codes: Optional[list[int]] = None,
        user_agent: str = DEFAULT_USER_AGENT,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        """Initialize HTTP client.

        Args:
            auth_manager: Copilot authentication manager
            max_retries: Maximum number of retries
            retry_delay_ms: Base retry delay in milliseconds
            retry_status_codes: HTTP status codes that trigger retry
            user_agent: Custom User-Agent header
            http_client: Custom httpx.AsyncClient for testing
        """
        self.auth_manager = auth_manager
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        self.retry_status_codes = retry_status_codes or DEFAULT_RETRY_STATUS_CODES
        self.user_agent = user_agent
        self._http_client = http_client
        self._logger = logger

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client:
            return self._http_client
        return httpx.AsyncClient(timeout=30.0)

    async def _add_auth_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Add authorization headers."""
        token = await self.auth_manager.get_valid_access_token()
        headers["Authorization"] = f"Bearer {token}"
        headers["User-Agent"] = self.user_agent
        headers["Editor-Version"] = "vscode/1.90.0"
        headers["Editor-Plugin-Version"] = "copilot/1.0"
        headers["Openai-Intent"] = "conversation-edits"
        headers["Content-Type"] = "application/json"
        return headers

    async def request(
        self,
        method: str,
        url: str | httpx.URL,
        *,
        headers: Optional[dict[str, str]] = None,
        json: Optional[dict] = None,
        content: Optional[dict] = None,
    ) -> httpx.Response:
        """Make HTTP request with retry logic and token management.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            headers: Optional headers dict
            json: Optional JSON body
            content: Optional request content/body

        Returns:
            HTTP response
        """
        client = await self._get_http_client()
        headers = headers or {}
        replayable = content is None or can_retry_body(content)
        attempt = 0

        while True:
            try:
                # Add authorization
                auth_headers = await self._add_auth_headers(headers.copy())

                # Make request
                response = await client.request(
                    method,
                    url,
                    headers=auth_headers,
                    json=json,
                    content=content,
                )

                # Handle 401 (token expired)
                if response.status_code == 401:
                    self._logger.warning(
                        "🔄 Invalid/expired token (401). Attempting refresh..."
                    )
                    try:
                        # Force refresh
                        await self.auth_manager.get_valid_access_token()

                        # Retry with new token
                        auth_headers = await self._add_auth_headers(
                            headers.copy()
                        )
                        retry_response = await client.request(
                            method,
                            url,
                            headers=auth_headers,
                            json=json,
                            content=content,
                        )

                        if retry_response.status_code != 401:
                            return retry_response

                        # Still 401 after refresh
                        text = retry_response.text
                        raise httpx.HTTPStatusError(
                            f"Still unauthorized after refresh: {text[:300]}",
                            request=retry_response.request,
                            response=retry_response,
                        )
                    except Exception as e:
                        raise httpx.HTTPStatusError(
                            f"Copilot authentication failed: {str(e)[:300]}",
                            request=response.request,
                            response=response,
                        ) from e

                # Handle retryable status codes
                if (
                    attempt < self.max_retries
                    and replayable
                    and should_retry_status(response.status_code, self.retry_status_codes)
                ):
                    wait_ms = self.retry_delay_ms * (2 ** attempt)
                    self._logger.warning(
                        f"⚠️  HTTP {response.status_code}. Retry {attempt + 1}/"
                        f"{self.max_retries} in {wait_ms}ms"
                    )
                    attempt += 1
                    await delay_ms(wait_ms)
                    continue

                return response

            except httpx.NetworkError as e:
                if attempt < self.max_retries and replayable:
                    wait_ms = self.retry_delay_ms * (2 ** attempt)
                    self._logger.warning(
                        f"🔄 Network error. Retry {attempt + 1}/{self.max_retries} "
                        f"in {wait_ms}ms: {e}"
                    )
                    attempt += 1
                    await delay_ms(wait_ms)
                    continue

                raise

    async def get(
        self,
        url: str | httpx.URL,
        headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        """Make GET request."""
        return await self.request("GET", url, headers=headers)

    async def post(
        self,
        url: str | httpx.URL,
        *,
        headers: Optional[dict[str, str]] = None,
        json: Optional[dict] = None,
    ) -> httpx.Response:
        """Make POST request with JSON body."""
        return await self.request("POST", url, headers=headers, json=json)
