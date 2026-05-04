"""Copilot API Provider"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ============================================================================
# Models/Schemas
# ============================================================================


class ChatMessage(BaseModel):
    """Chat message."""

    role: str  # system, user, assistant
    content: str


class ChatCompletionRequest(BaseModel):
    """Chat completion request."""

    model: str
    messages: list[ChatMessage]
    temperature: float = 0.2
    max_tokens: Optional[int] = None


class ChatCompletionChoice(BaseModel):
    """Chat completion choice."""

    message: ChatMessage


class ChatCompletionResponse(BaseModel):
    """Chat completion response."""

    choices: list[ChatCompletionChoice]


class ResponsesChoice(BaseModel):
    """Responses API choice."""

    content: Optional[list[dict]] = None
    text: Optional[str] = None


class ResponsesApiResponse(BaseModel):
    """Responses API response (for advanced models)."""

    output_text: Optional[str] = None
    output: Optional[list[dict]] = None


# ============================================================================
# Constants
# ============================================================================

DEFAULT_BASE_URL = "https://api.githubcopilot.com"


# ============================================================================
# Provider
# ============================================================================


class CopilotProvider:
    """Copilot API Provider - handles requests to Copilot endpoints."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        http_client: Optional["CopilotHTTPClient"] = None,  # type: ignore
    ):
        """Initialize provider.

        Args:
            base_url: Base URL for Copilot API
            http_client: HTTP client with auth/retry
        """
        self.base_url = base_url
        self.http_client = http_client
        self._logger = logger

    def _extract_responses_text(self, data: dict) -> Optional[str]:
        """Extract text from responses API response."""
        # Try direct output_text first
        if data.get("output_text") and data["output_text"].strip():
            return data["output_text"].strip()

        # Try extracting from output array
        output_items = data.get("output", [])
        texts = []
        for item in output_items:
            content = item.get("content", [])
            for part in content:
                if part.get("type") in ("output_text", "text"):
                    if text := part.get("text", "").strip():
                        texts.append(text)

        if texts:
            return "\n".join(texts).strip()

        return None

    def _build_responses_payload(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: Optional[int],
        *,
        legacy: bool = False,
    ) -> dict:
        """Build payload for responses API.

        Uses modern format by default (``input`` / ``max_output_tokens``),
        with optional legacy format fallback (``messages`` / ``max_tokens``).
        """
        if legacy:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            return payload

        payload = {
            "model": model,
            "input": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_output_tokens"] = max_tokens
        return payload

    async def chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Call chat completions endpoint.

        Args:
            model: Model ID
            messages: Chat messages
            temperature: Sampling temperature
            max_tokens: Maximum output tokens

        Returns:
            Generated text
        """
        self._logger.info(
            f"📤 Calling chat.completions for model: {model}"
        )

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        response = await self.http_client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )

        if not response.is_success:
            self._logger.error(
                "❌ chat.completions %s — body: %s", response.status_code, response.text[:500]
            )
        response.raise_for_status()
        data = response.json()

        try:
            result = ChatCompletionResponse(**data)
            content = result.choices[0].message.content.strip()

            if not content:
                raise ValueError("Empty response from chat.completions")

            return content

        except (IndexError, AttributeError, ValueError) as e:
            self._logger.error(f"❌ Invalid response format: {e}")
            raise ValueError(
                f"Invalid response from chat.completions: {str(e)}"
            ) from e

    async def responses(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Call responses API endpoint (for advanced models).

        Args:
            model: Model ID
            messages: Chat messages
            temperature: Sampling temperature
            max_tokens: Maximum output tokens

        Returns:
            Generated text
        """
        self._logger.info(
            f"📤 Calling responses API for model: {model}"
        )

        endpoint = f"{self.base_url}/responses"
        response = await self.http_client.post(
            endpoint,
            json=self._build_responses_payload(
                model,
                messages,
                temperature,
                max_tokens,
                legacy=False,
            ),
        )

        if not response.is_success:
            self._logger.error(
                "❌ responses %s — body: %s",
                response.status_code,
                response.text[:500],
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else None
            if status_code != 400:
                raise

            self._logger.warning(
                "⚠️ responses API returned 400 for model %s. Retrying with legacy payload format.",
                model,
            )
            response = await self.http_client.post(
                endpoint,
                json=self._build_responses_payload(
                    model,
                    messages,
                    temperature,
                    max_tokens,
                    legacy=True,
                ),
            )
            if not response.is_success:
                self._logger.error(
                    "❌ responses legacy retry %s — body: %s",
                    response.status_code,
                    response.text[:500],
                )
            response.raise_for_status()

        data = response.json()

        try:
            text = self._extract_responses_text(data)

            if not text:
                raise ValueError("Empty response from responses API")

            return text

        except (ValueError, KeyError) as e:
            self._logger.error(f"❌ Invalid response format: {e}")
            raise ValueError(
                f"Invalid response from responses API: {str(e)}"
            ) from e

    async def run_model(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Run model with automatic endpoint selection.

        Uses 'responses' API for advanced models (gpt-5+),
        and 'chat' API for basic models (gpt-5-mini).

        Args:
            model: Model ID
            messages: Chat messages
            temperature: Sampling temperature
            max_tokens: Maximum output tokens

        Returns:
            Generated text
        """
        # Determine endpoint:
        # - responses API: OpenAI GPT-5+ advanced models only
        # - chat API: everything else, including Claude and GPT-5-mini
        if model.startswith("gpt-5") and model not in {"gpt-5-mini"}:
            endpoint = "responses"
        else:
            endpoint = "chat"

        self._logger.debug(
            f"🎯 Resolved {model} → {endpoint} endpoint"
        )

        if endpoint == "responses":
            return await self.responses(
                model,
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            return await self.chat(
                model,
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
