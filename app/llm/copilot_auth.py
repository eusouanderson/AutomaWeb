"""Copilot Authentication Manager - OAuth Device Code Flow"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Models/Schemas
# ============================================================================


class OAuthDeviceCodeResponse(BaseModel):
    """Response from GitHub OAuth device code endpoint."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int = 5


class OAuthTokenResponse(BaseModel):
    """Response from GitHub OAuth token endpoint."""

    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    token_type: Optional[str] = None
    error: Optional[str] = None


class CopilotAuthRecord(BaseModel):
    """Stored authentication record."""

    access_token: str
    refresh_token: Optional[str] = None
    expires_at: int  # Unix timestamp in ms
    token_type: str = "bearer"
    enterprise_url: Optional[str] = None


class CopilotAPIToken(BaseModel):
    """Short-lived Copilot API token exchanged from the OAuth token."""

    token: str
    expires_at: int  # Unix timestamp (seconds) returned by GitHub
    expires_at_ms: int = 0  # computed Unix timestamp in ms


# ============================================================================
# Constants
# ============================================================================

DEFAULT_CLIENT_ID = "Iv1.b507a08c87ecfe98"
DEFAULT_SCOPE = "read:user"
EXPIRY_SKEW_MS = 30_000  # 30 second buffer before token expiry

COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"


# ============================================================================
# Utility Functions
# ============================================================================


def normalize_domain(value: str) -> str:
    """Normalize domain URL by removing scheme and trailing slash."""
    return value.replace("https://", "").replace("http://", "").rstrip("/")


def resolve_oauth_domain(enterprise_url: Optional[str] = None) -> str:
    """Resolve OAuth domain from enterprise URL or default to github.com."""
    if not enterprise_url:
        return "github.com"
    return normalize_domain(enterprise_url)


def resolve_oauth_endpoints(
    enterprise_url: Optional[str] = None,
) -> dict[str, str]:
    """Resolve OAuth endpoints based on GitHub instance."""
    domain = resolve_oauth_domain(enterprise_url)
    return {
        "device_code_url": f"https://{domain}/login/device/code",
        "token_url": f"https://{domain}/login/oauth/access_token",
    }


def is_token_expired(expires_at: int) -> bool:
    """Check if token is expired with safety skew."""
    now_ms = int(time.time() * 1000)
    return (now_ms + EXPIRY_SKEW_MS) >= expires_at


def get_static_copilot_token() -> Optional[str]:
    """Get Copilot token from environment if provided."""
    import os

    token = os.environ.get("COPILOT_TOKEN", "").strip()
    return token if token else None


# ============================================================================
# Authentication Manager
# ============================================================================


class CopilotAuthManager:
    """Manages OAuth Device Code Flow authentication for Copilot."""

    def __init__(
        self,
        auth_file_path: Optional[str] = None,
        client_id: Optional[str] = None,
        enterprise_url: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        """Initialize the authentication manager.

        Args:
            auth_file_path: Path to store auth.json (defaults to .copilot/auth.json)
            client_id: OAuth client ID (defaults to pre-configured)
            enterprise_url: GitHub Enterprise URL (optional)
            http_client: Custom httpx.AsyncClient for testing
        """
        self.auth_file_path = Path(
            auth_file_path or Path.cwd() / ".copilot" / "auth.json"
        )
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self.enterprise_url = enterprise_url
        self._http_client = http_client
        self._cache: Optional[CopilotAuthRecord] = None
        self._copilot_api_token: Optional[CopilotAPIToken] = None
        self._logger = logger

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client:
            return self._http_client

        # Create new client with reasonable timeouts
        return httpx.AsyncClient(timeout=10.0)

    async def _load_auth_record(self) -> Optional[CopilotAuthRecord]:
        """Load authentication record from file."""
        if self._cache:
            self._logger.debug(f"🔵 Returning cached auth record")
            return self._cache

        if not self.auth_file_path.exists():
            self._logger.debug(f"🔴 Auth file not found: {self.auth_file_path}")
            return None

        try:
            data = json.loads(self.auth_file_path.read_text())
            # Normalize camelCase keys (legacy format) to snake_case
            _camel_to_snake = {
                "accessToken": "access_token",
                "refreshToken": "refresh_token",
                "expiresAt": "expires_at",
                "tokenType": "token_type",
                "enterpriseUrl": "enterprise_url",
            }
            data = {_camel_to_snake.get(k, k): v for k, v in data.items()}
            record = CopilotAuthRecord(**data)
            self._cache = record
            self._logger.info(f"✅ Auth record loaded from file: {self.auth_file_path}")
            return record
        except (json.JSONDecodeError, ValueError) as e:
            self._logger.warning(f"Failed to load auth record: {e}")
            return None

    async def _save_auth_record(self, record: CopilotAuthRecord) -> None:
        """Save authentication record to file."""
        self.auth_file_path.parent.mkdir(parents=True, exist_ok=True)
        # Use model_dump() since CopilotAuthRecord is a Pydantic BaseModel
        self.auth_file_path.write_text(
            json.dumps(record.model_dump(), indent=2) + "\n"
        )
        self._cache = record
        self._logger.info(f"✅ Auth record saved to {self.auth_file_path}")
        self._logger.debug(f"   Token: {record.access_token[:30]}...")
        self._logger.debug(f"   Expires at: {record.expires_at}")

    async def _request_device_code(
        self, http_client: httpx.AsyncClient
    ) -> OAuthDeviceCodeResponse:
        """Request device code from OAuth endpoint."""
        endpoints = resolve_oauth_endpoints(self.enterprise_url)
        response = await http_client.post(
            endpoints["device_code_url"],
            json={
                "client_id": self.client_id,
                "scope": DEFAULT_SCOPE,
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return OAuthDeviceCodeResponse(**response.json())

    async def _request_token_by_device_code(
        self, device_code: str, http_client: httpx.AsyncClient
    ) -> OAuthTokenResponse:
        """Poll for token using device code."""
        endpoints = resolve_oauth_endpoints(self.enterprise_url)
        response = await http_client.post(
            endpoints["token_url"],
            json={
                "client_id": self.client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return OAuthTokenResponse(**response.json())

    async def _request_token_by_refresh_token(
        self, refresh_token: str, http_client: httpx.AsyncClient
    ) -> OAuthTokenResponse:
        """Request new token using refresh token."""
        endpoints = resolve_oauth_endpoints(self.enterprise_url)
        response = await http_client.post(
            endpoints["token_url"],
            json={
                "client_id": self.client_id,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return OAuthTokenResponse(**response.json())

    async def authorize_device_code_flow(
        self,
        enterprise_url: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> CopilotAuthRecord:
        """Perform OAuth Device Code Flow authorization.

        This method is typically called only for CLI/script usage.
        For web applications, use the /api/ai/authorize endpoints instead.

        Args:
            enterprise_url: Optional GitHub Enterprise URL override
            http_client: Optional custom HTTP client

        Returns:
            CopilotAuthRecord with tokens
        """
        client = http_client or await self._get_http_client()
        selected_enterprise = enterprise_url or self.enterprise_url

        # Request device code
        device_response = await self._request_device_code(client)

        # Display authorization instructions to terminal user
        print(
            f"\n🔐 Authorize Copilot:\n"
            f"   Visit: {device_response.verification_uri}\n"
            f"   Code:  {device_response.user_code}\n"
            f"   ⏳ Waiting for authorization (expires in {device_response.expires_in}s)...\n"
        )

        # Poll for token
        timeout_at = time.time() + device_response.expires_in
        interval_ms = max(1, device_response.interval) * 1000

        while time.time() < timeout_at:
            await asyncio.sleep(interval_ms / 1000)

            token_response = await self._request_token_by_device_code(
                device_response.device_code, client
            )

            if token_response.access_token:
                expires_in = token_response.expires_in or 3600
                record = CopilotAuthRecord(
                    access_token=token_response.access_token,
                    refresh_token=token_response.refresh_token,
                    expires_at=int(
                        (time.time() + max(60, expires_in)) * 1000
                    ),
                    token_type="bearer",
                    enterprise_url=selected_enterprise,
                )
                await self._save_auth_record(record)
                self._logger.info("✅ Copilot authenticated successfully")
                print("✅ Copilot authenticated successfully!\n")
                return record

            if token_response.error == "authorization_pending":
                continue

            if token_response.error == "slow_down":
                interval_ms += 5000
                continue

            raise ValueError(
                f"OAuth error: {token_response.error or 'unknown'}"
            )

        raise TimeoutError("Device code authorization timed out")

    async def _exchange_for_copilot_token(
        self,
        oauth_token: str,
        http_client: httpx.AsyncClient,
    ) -> str:
        """Exchange a GitHub OAuth token (gho_) for a short-lived Copilot API token.

        The Copilot API (api.githubcopilot.com) does NOT accept raw OAuth tokens.
        This call fetches the real bearer token used for completions.

        Args:
            oauth_token: GitHub OAuth access token (gho_...)
            http_client: HTTP client to use

        Returns:
            Short-lived Copilot bearer token
        """
        # Return cached Copilot token if still valid
        if self._copilot_api_token:
            now_ms = int(time.time() * 1000)
            if (self._copilot_api_token.expires_at_ms - EXPIRY_SKEW_MS) > now_ms:
                self._logger.debug("🔵 Using cached Copilot API token")
                return self._copilot_api_token.token

        self._logger.info("🔄 Exchanging OAuth token for Copilot API token...")
        response = await http_client.get(
            COPILOT_TOKEN_URL,
            headers={
                "Authorization": f"token {oauth_token}",
                "Accept": "application/json",
                "Editor-Version": "vscode/1.90.0",
                "Editor-Plugin-Version": "copilot/1.0",
                "User-Agent": "GithubCopilot/1.0",
            },
        )
        response.raise_for_status()
        data = response.json()

        # GitHub returns expires_at as a Unix timestamp integer (seconds)
        raw_expires = data.get("expires_at", 0)
        try:
            expires_at_ms = int(raw_expires) * 1000
        except (TypeError, ValueError):
            # Fallback: 25 minutes from now
            expires_at_ms = int((time.time() + 1500) * 1000)

        api_token = CopilotAPIToken(
            token=data["token"],
            expires_at=int(raw_expires) if raw_expires else 0,
            expires_at_ms=expires_at_ms,
        )
        self._copilot_api_token = api_token
        self._logger.info("✅ Copilot API token obtained (expires_at: %s)", raw_expires)
        return api_token.token

    async def get_valid_access_token(
        self, http_client: Optional[httpx.AsyncClient] = None
    ) -> str:
        """Get a valid access token, refreshing if necessary.

        Args:
            http_client: Optional custom HTTP client

        Returns:
            Valid access token

        Raises:
            RuntimeError: If no token exists and authorization is required
        """
        # Check for static token first
        static = get_static_copilot_token()
        if static:
            return static

        client = http_client or await self._get_http_client()

        # Try to load from cache
        record = await self._load_auth_record()

        if not record:
            # Need to authorize - raise exception instead of blocking
            raise RuntimeError(
                "Copilot authentication required. "
                "Please visit /api/ai/authorize endpoint to start the authorization flow."
            )

        # Check if token is expired
        if not is_token_expired(record.expires_at):
            return await self._exchange_for_copilot_token(record.access_token, client)

        # Token expired, try refresh
        self._logger.info("🔄 Refreshing Copilot token...")

        if not record.refresh_token:
            # Classic GitHub tokens (gho_) may still be valid despite our expiry marker.
            # Return the token optimistically — the caller will get a 401 if it really expired.
            self._logger.warning(
                "⚠️  Token expiry marker reached but no refresh_token. "
                "Returning existing token optimistically (classic token may still be valid)."
            )
            # Extend our local expiry by 28 days to avoid repeated re-auth prompts
            extended = CopilotAuthRecord(
                access_token=record.access_token,
                refresh_token=None,
                expires_at=int((time.time() + 86400 * 28) * 1000),
                token_type=record.token_type,
                enterprise_url=record.enterprise_url,
            )
            await self._save_auth_record(extended)
            return await self._exchange_for_copilot_token(extended.access_token, client)

        try:
            token_response = await self._request_token_by_refresh_token(
                record.refresh_token, client
            )

            if not token_response.access_token:
                raise ValueError("No access token in refresh response")

            expires_in = token_response.expires_in or 3600
            refreshed = CopilotAuthRecord(
                access_token=token_response.access_token,
                refresh_token=token_response.refresh_token
                or record.refresh_token,
                expires_at=int((time.time() + max(60, expires_in)) * 1000),
                token_type="bearer",
                enterprise_url=record.enterprise_url,
            )

            await self._save_auth_record(refreshed)
            self._logger.info("✅ Token refreshed successfully")
            return await self._exchange_for_copilot_token(refreshed.access_token, client)

        except Exception as e:
            self._logger.warning(f"Refresh failed: {e}, re-authorizing...")
            raise RuntimeError(
                "Copilot token refresh failed. "
                "Please visit /api/ai/authorize endpoint to re-authorize."
            )

    async def get_auth_record(self) -> Optional[CopilotAuthRecord]:
        """Get the current auth record if it exists."""
        return await self._load_auth_record()
