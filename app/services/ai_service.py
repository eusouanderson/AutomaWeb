"""Copilot Integration Service - Orchestration Layer"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from app.llm.copilot_auth import CopilotAuthManager
from app.llm.copilot_http import CopilotHTTPClient
from app.llm.copilot_models import CopilotModelsClient, CopilotModelInfo
from app.llm.copilot_provider import CopilotProvider

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

DEFAULT_BASE_URL = "https://api.githubcopilot.com"


# ============================================================================
# Copilot Service
# ============================================================================


class CopilotService:
    """Main Copilot integration service.

    Provides:
    - OAuth authentication and token management
    - HTTP client with retry logic
    - Model discovery and selection
    - Chat completions and responses API calls
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        auth_file_path: Optional[str] = None,
        client_id: Optional[str] = None,
        enterprise_url: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        """Initialize Copilot service.

        Args:
            base_url: Base URL for Copilot API
            auth_file_path: Path to store auth.json
            client_id: OAuth client ID
            enterprise_url: GitHub Enterprise URL (optional)
            http_client: Custom httpx.AsyncClient for testing
        """
        self.base_url = base_url or DEFAULT_BASE_URL
        self._logger = logger

        # Initialize auth manager
        self.auth_manager = CopilotAuthManager(
            auth_file_path=auth_file_path,
            client_id=client_id,
            enterprise_url=enterprise_url,
            http_client=http_client,
        )

        # Initialize HTTP client
        self.http_client = CopilotHTTPClient(
            auth_manager=self.auth_manager,
            http_client=http_client,
        )

        # Initialize provider
        self.provider = CopilotProvider(
            base_url=self.base_url,
            http_client=self.http_client,
        )

        # Initialize models client
        self.models_client = CopilotModelsClient(
            http_client=self.http_client,
        )

    async def get_valid_token(self) -> str:
        """Get a valid Copilot access token.

        Handles OAuth authorization, token refresh, and caching.

        Returns:
            Valid access token
        """
        return await self.auth_manager.get_valid_access_token()

    async def fetch_models(
        self,
        force_refresh: bool = False,
    ) -> list[CopilotModelInfo]:
        """Fetch available Copilot models.

        Args:
            force_refresh: Force refresh from API

        Returns:
            List of available models
        """
        return await self.models_client.fetch_models(
            self.base_url,
            force_refresh=force_refresh,
        )

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate content using Copilot.

        Args:
            prompt: User prompt/request
            model: Model ID (defaults to env COPILOT_MODEL or gpt-5-mini)
            system_prompt: System message for context
            temperature: Sampling temperature
            max_tokens: Maximum output tokens

        Returns:
            Generated text
        """
        # Determine model
        selected_model = model or os.environ.get("COPILOT_MODEL", "gpt-5-mini")

        self._logger.info(
            f"🚀 Generating content using model: {selected_model}"
        )

        # Build messages
        messages = []

        if system_prompt:
            messages.append(
                {"role": "system", "content": system_prompt}
            )

        messages.append(
            {"role": "user", "content": prompt}
        )

        # Call provider
        return await self.provider.run_model(
            selected_model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def generate_robot_test(
        self,
        prompt: str,
        context: Optional[str] = None,
        page_structure: Optional[dict] = None,
        model: Optional[str] = None,
    ) -> str:
        """Generate Robot Framework test code.

        Args:
            prompt: Test generation prompt
            context: Additional context about the page/application
            page_structure: Page DOM structure as dict
            model: Model ID override

        Returns:
            Generated Robot Framework code
        """
        system_prompt = (
            "Você é um especialista em gerar testes automatizados com Robot "
            "Framework e Playwright. "
            "Gere apenas código Robot Framework válido, sem explicações ou markdown. "
            "Siga as melhores práticas de automação:\n\n"
            "REGRAS:\n"
            "1. Use Browser Library do Playwright\n"
            "2. Sempre use New Browser antes de New Context\n"
            "3. Sempre use Set Browser Timeout\n"
            "4. NUNCA use Input Text - use Fill Text\n"
            "5. NUNCA use Click - use click da página com wait\n"
            "6. Sempre aguarde elemento antes de ação (Wait For Elements State)\n"
            "7. Use data-testid ou role + name para seletores\n"
            "8. NUNCA use //div, //a ou seletores genéricos\n"
            "9. Use css= ou xpath= para localizadores\n"
            "10. Cada teste deve ser independente\n"
            "11. Sempre feche browser no teardown\n"
            "12. Should Be Equal precisa EXATAMENTE 2 argumentos\n"
            "13. NUNCA use ${OUTPUT}, ${LOG} ou ${REPORT}\n"
            "14. Toda keyword deve ter pelo menos 1 step executável\n\n"
        )

        if page_structure:
            import json
            structure_str = json.dumps(page_structure, ensure_ascii=False, indent=2)
            system_prompt += f"Estrutura da página:\n{structure_str}\n"

        full_prompt = prompt
        if context:
            full_prompt = f"{prompt}\n\nContexto:\n{context}"

        return await self.generate(
            prompt=full_prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=0.0,  # Deterministic for test generation
            max_tokens=4096,
        )

    async def check_connection(self) -> dict:
        """Check if Copilot is reachable and authenticated.

        Returns:
            Connection status info
        """
        try:
            token = await self.get_valid_token()
            self._logger.info("✅ Copilot connection successful")
            return {
                "ok": True,
                "message": "Copilot authenticated successfully",
                "has_token": bool(token),
            }
        except Exception as e:
            self._logger.error(f"❌ Copilot connection failed: {e}")
            return {
                "ok": False,
                "error": str(e),
                "message": "Failed to connect to Copilot",
            }


# ============================================================================
# Global Service Instance
# ============================================================================

_copilot_service: Optional[CopilotService] = None


def get_copilot_service() -> CopilotService:
    """Get or create global Copilot service instance."""
    global _copilot_service

    if _copilot_service is None:
        enterprise_url = os.environ.get("COPILOT_ENTERPRISE_URL")
        _copilot_service = CopilotService(
            enterprise_url=enterprise_url,
        )

    return _copilot_service


async def initialize_copilot(
    base_url: Optional[str] = None,
    auth_file_path: Optional[str] = None,
    client_id: Optional[str] = None,
    enterprise_url: Optional[str] = None,
) -> CopilotService:
    """Initialize Copilot service with custom parameters.

    Args:
        base_url: Base URL for Copilot API
        auth_file_path: Path to store auth.json
        client_id: OAuth client ID
        enterprise_url: GitHub Enterprise URL

    Returns:
        Configured CopilotService instance
    """
    global _copilot_service

    _copilot_service = CopilotService(
        base_url=base_url or DEFAULT_BASE_URL,
        auth_file_path=auth_file_path,
        client_id=client_id,
        enterprise_url=enterprise_url,
    )

    return _copilot_service
