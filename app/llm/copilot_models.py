"""Copilot Models API Client"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ============================================================================
# Models/Schemas
# ============================================================================


class ModelCapabilities(BaseModel):
    """Model capabilities."""

    reasoning: bool = False
    vision: bool = False
    streaming: bool = False
    tool_calls: bool = False
    structured_outputs: bool = False


class ModelLimits(BaseModel):
    """Model token limits."""

    context_tokens: int
    output_tokens: int
    prompt_tokens: int


class CopilotModelInfo(BaseModel):
    """Information about a Copilot model."""

    id: str
    name: str
    family: str
    endpoints: list[str] = []
    limits: ModelLimits
    capabilities: ModelCapabilities


class CacheEntry(BaseModel):
    """Cache entry with TTL."""

    value: list[CopilotModelInfo]
    expires_at: int


# ============================================================================
# Constants
# ============================================================================

CACHE_TTL_MS = 5 * 60 * 1000  # 5 minutes


# ============================================================================
# Models API Client
# ============================================================================


class CopilotModelsClient:
    """Client for Copilot Models API."""

    def __init__(
        self,
        http_client: "CopilotHTTPClient",  # type: ignore
    ):
        """Initialize models client.

        Args:
            http_client: Copilot HTTP client with auth/retry
        """
        self.http_client = http_client
        self._cache: dict[str, CacheEntry] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._logger = logger

    async def fetch_models(
        self,
        base_url: str,
        force_refresh: bool = False,
    ) -> list[CopilotModelInfo]:
        """Fetch available models from Copilot API.

        Args:
            base_url: Base URL for Copilot API
            force_refresh: Force refresh cache

        Returns:
            List of available CopilotModelInfo
        """
        import asyncio

        now_ms = int(time.time() * 1000)

        # Check cache
        if not force_refresh and base_url in self._cache:
            cached = self._cache[base_url]
            if cached.expires_at > now_ms:
                self._logger.debug(f"✅ Using cached models for {base_url}")
                return cached.value

        # Check if fetch is already in progress
        if base_url in self._inflight:
            self._logger.debug(
                f"⏳ Models fetch already in progress for {base_url}"
            )
            return await self._inflight[base_url]

        # Start new fetch
        future: asyncio.Future = asyncio.Future()
        self._inflight[base_url] = future

        try:
            models = await self._do_fetch_models(base_url)

            # Update cache
            self._cache[base_url] = CacheEntry(
                value=models,
                expires_at=int(time.time() * 1000) + CACHE_TTL_MS,
            )

            future.set_result(models)
            return models

        except Exception as e:
            future.set_exception(e)
            raise

        finally:
            self._inflight.pop(base_url, None)

    async def _do_fetch_models(self, base_url: str) -> list[CopilotModelInfo]:
        """Actually fetch models from API."""
        self._logger.info(f"🔍 Fetching models from {base_url}/models")

        response = await self.http_client.get(
            f"{base_url}/models",
            headers={"Accept": "application/json"},
        )

        response.raise_for_status()
        data = response.json()

        if not isinstance(data.get("data"), list):
            raise ValueError("Invalid response format: missing 'data' array")

        # Parse and filter models
        models = []
        for item in data["data"]:
            try:
                model_info = self._parse_model_item(item)
                # Only include enabled models
                if item.get("model_picker_enabled") and item.get("policy", {}).get("state") != "disabled":
                    models.append(model_info)
            except Exception as e:
                self._logger.warning(
                    f"⚠️  Failed to parse model {item.get('id')}: {e}"
                )
                continue

        self._logger.info(f"✅ Found {len(models)} available models")
        return models

    def _parse_model_item(self, item: dict) -> CopilotModelInfo:
        """Parse a model item from API response."""
        capabilities = item.get("capabilities", {})
        limits = capabilities.get("limits", {})
        supports = capabilities.get("supports", {})

        # Determine if model has reasoning capabilities
        has_reasoning = bool(
            supports.get("adaptive_thinking")
            or (
                isinstance(supports.get("reasoning_effort"), list)
                and len(supports["reasoning_effort"]) > 0
            )
            or isinstance(supports.get("max_thinking_budget"), int)
            or isinstance(supports.get("min_thinking_budget"), int)
        )

        return CopilotModelInfo(
            id=item["id"],
            name=item.get("name", item["id"]),
            family=capabilities.get("family", "unknown"),
            endpoints=item.get("supported_endpoints", []),
            limits=ModelLimits(
                context_tokens=limits.get("max_context_window_tokens", 4096),
                output_tokens=limits.get("max_output_tokens", 2048),
                prompt_tokens=limits.get("max_prompt_tokens", 2048),
            ),
            capabilities=ModelCapabilities(
                reasoning=has_reasoning,
                vision=bool(supports.get("vision")),
                streaming=bool(supports.get("streaming")),
                tool_calls=bool(supports.get("tool_calls")),
                structured_outputs=bool(supports.get("structured_outputs")),
            ),
        )
