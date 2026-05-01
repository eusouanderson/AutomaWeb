"""Adapter/Wrapper to replace GroqClient with CopilotService"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class PayloadTooLargeError(Exception):
    """Raised when LLM request exceeds provider payload limits even after fallback."""


class CopilotServiceAdapter:
    """Adapter that wraps CopilotService to maintain compatibility with TestService.

    This replaces the GroqClient interface with CopilotService interface.
    """

    def __init__(self) -> None:
        # Lazy import to avoid circular imports
        from app.services.ai_service import get_copilot_service

        self._service = get_copilot_service()
        self._last_health_ok_at: float | None = None
        self._last_health_error: str | None = None

    def check_api_health(self) -> dict[str, str | bool | int | None]:
        """Check if the Copilot API is reachable."""
        import asyncio

        try:
            # Run async check in thread
            result = asyncio.run(self._service.check_connection())
            if result.get("ok"):
                self._last_health_ok_at = time.time()
                self._last_health_error = None
                return {
                    "ok": True,
                    "source": "live",
                    "model": "gpt-5-mini",
                    "checked_at_epoch": int(time.time()),
                    "last_success_epoch": int(time.time()),
                    "error": None,
                    "message": "Copilot API reachable.",
                }
            else:
                self._last_health_error = result.get("error", "Unknown error")
                return {
                    "ok": False,
                    "source": "live",
                    "model": "gpt-5-mini",
                    "checked_at_epoch": int(time.time()),
                    "last_success_epoch": (
                        int(self._last_health_ok_at)
                        if self._last_health_ok_at
                        else None
                    ),
                    "error": self._last_health_error,
                    "message": "Copilot API unreachable.",
                }
        except Exception as e:
            self._last_health_error = f"{e.__class__.__name__}: {e}"
            return {
                "ok": False,
                "source": "live",
                "model": "gpt-5-mini",
                "checked_at_epoch": int(time.time()),
                "last_success_epoch": (
                    int(self._last_health_ok_at) if self._last_health_ok_at else None
                ),
                "error": self._last_health_error,
                "message": "Copilot API unreachable.",
            }

    async def generate_robot_test(
        self,
        prompt_text: str,
        context_text: str | None = None,
        page_structure: dict | None = None,
    ) -> str:
        """Generate Robot Framework test code using Copilot.

        Args:
            prompt_text: Test generation prompt
            context_text: Additional context
            page_structure: Page DOM structure

        Returns:
            Generated Robot Framework code

        Raises:
            PayloadTooLargeError: If payload exceeds limits even after retry
        """
        try:
            content = await self._service.generate_robot_test(
                prompt=prompt_text or "Gerar teste Robot Framework conforme solicitação recebida.",
                context=context_text,
                page_structure=page_structure,
            )

            if not content:
                raise ValueError(
                    "Copilot returned empty response for test generation"
                )

            return content

        except Exception as e:
            logger.error(f"❌ Error generating Robot test: {e}")

            # Check if it's a payload size issue
            error_str = str(e).lower()
            if "413" in error_str or "payload" in error_str:
                raise PayloadTooLargeError(
                    "Request payload exceeds Copilot limits"
                ) from e

            raise

    async def regenerate_robot_step(
        self,
        original_prompt: str,
        failing_step: str,
        error_message: str,
        context: str | None = None,
    ) -> str:
        """Regenerate a single Robot Framework step.

        Args:
            original_prompt: Original test generation prompt
            failing_step: The failing step line
            error_message: Error message from the failing step
            context: Additional context

        Returns:
            Regenerated step line
        """
        system_prompt = (
            "Você corrige apenas UMA linha de step de Robot Framework usando Browser Library. "
            "Retorne apenas a linha corrigida, sem markdown, sem explicações. "
            "A linha precisa conter wait explícito ou locator estável, evitando estrito ambíguo."
        )

        prompt = (
            f"Regenerar somente a linha de step abaixo mantendo a intenção do prompt original.\n"
            f"Prompt original: {original_prompt}\n"
            f"Step com falha: {failing_step}\n"
            f"Erro: {error_message}"
        )

        try:
            content = await self._service.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.0,
                max_tokens=256,
            )

            # Extract first line only
            return content.splitlines()[0] if content else ""

        except Exception as e:
            logger.error(f"Error regenerating step: {e}")
            # Return original on error
            return failing_step
