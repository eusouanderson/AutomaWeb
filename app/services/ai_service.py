"""Copilot Integration Service - Orchestration Layer"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from app.core.config import settings
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
            model: Model ID (defaults to settings.COPILOT_MODEL)
            system_prompt: System message for context
            temperature: Sampling temperature
            max_tokens: Maximum output tokens

        Returns:
            Generated text
        """
        # Determine model
        selected_model = model or os.environ.get("COPILOT_MODEL") or settings.COPILOT_MODEL

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
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate Robot Framework test code.

        Args:
            prompt: Test generation prompt
            context: Additional context about the page/application
            page_structure: Page DOM structure as dict
            model: Model ID override
            system_prompt: Optional custom system prompt
            temperature: Optional temperature override
            max_tokens: Optional max tokens override

        Returns:
            Generated Robot Framework code
        """
        execution_contract = (
            "Você é um especialista em gerar testes automatizados com Robot "
            "Framework e Browser Library (Playwright). "
            "Gere APENAS código Robot Framework válido, sem explicações, sem markdown, sem blocos ```robot. "
            "Siga rigorosamente as regras abaixo:\n\n"
            "REGRAS DE BIBLIOTECA:\n"
            "1. Use SOMENTE Browser Library — NUNCA SeleniumLibrary\n"
            "2. Sempre use New Browser → New Context → Set Browser Timeout 30s → New Page\n"
            "3. Sempre adicione [Teardown]    Close Browser no test case\n\n"
            "REGRAS DE SELETORES:\n"
            "4. NUNCA use xpath absoluto (xpath=/html/body/...) — use SEMPRE xpath relativo (xpath=//...)\n"
            "5. Prefira css= com id estável, data-testid, role ou classe específica\n"
            "6. NUNCA use seletores genéricos como css=h3, css=button, css=a sem contexto\n"
            "7. Se a estrutura da página estiver disponível, use os seletores exatos fornecidos\n\n"
            "REGRAS DE KEYWORDS:\n"
            "8. NUNCA use Input Text — use Fill Text\n"
            "9. Sempre aguarde visibilidade antes de agir: Wait For Elements State    <sel>    visible\n"
            "10. Para URL, use Get Url (não Get Location nem Location Should Contain)\n"
            "11. Cada teste deve ser completamente independente\n"
            "12. Should Be Equal precisa EXATAMENTE 2 argumentos\n"
            "13. NUNCA use ${OUTPUT}, ${LOG} ou ${REPORT}\n"
            "14. Toda keyword customizada deve ter pelo menos 1 step executável\n"
            "15. Set Browser Timeout aceita apenas 1 argumento (ex: 30s)\n"
            "16. Para banners/botões de cookie consent (id ou classe contendo: cookie, accept, consent, hs-eu, onetrust, gdpr, lgpd), prefira clique via JavaScript para contornar elementos fora do viewport em headless:\n"
            "    Exemplo correto: Evaluate JavaScript    ${None}    () => { const b = document.querySelector(\"#hs-eu-confirmation-button\"); if (b) b.click(); }\n\n"
            "PADRAO OBRIGATORIO DE EXECUCAO (SEM VARIAR):\n"
            "- Fluxo base: New Browser -> New Context -> Set Browser Timeout 30s -> New Page\n"
            "- Exemplo mínimo:\n"
            "  *** Settings ***\n"
            "  Library    Browser\n"
            "  *** Test Cases ***\n"
            "  Caso\n"
            "      New Browser    chromium    headless=${HEADLESS}\n"
            "      New Context\n"
            "      Set Browser Timeout    30s\n"
            "      New Page    https://exemplo.com\n"
            "      [Teardown]    Close Browser\n\n"
        )

        if system_prompt and system_prompt.strip():
            resolved_system_prompt = (
                f"{execution_contract}"
                "INSTRUCOES ADICIONAIS DO USUARIO (sem violar o padrao obrigatorio acima):\n"
                f"{system_prompt.strip()}"
            )
        else:
            resolved_system_prompt = execution_contract

        if page_structure:
            import json
            structure_str = json.dumps(page_structure, ensure_ascii=False, indent=2)
            resolved_system_prompt += f"Estrutura da página:\n{structure_str}\n"

        full_prompt = prompt
        if context:
            full_prompt = f"{prompt}\n\nContexto:\n{context}"

        return await self.generate(
            prompt=full_prompt,
            model=model,
            system_prompt=resolved_system_prompt,
            temperature=0.0 if temperature is None else temperature,
            max_tokens=4096 if max_tokens is None else max_tokens,
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
