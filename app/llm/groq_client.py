from __future__ import annotations

import logging
import time
import json
from dataclasses import dataclass

import httpx
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: str
    created_at: float


class SimpleCache:
    """Simple in-memory cache with TTL."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if not entry:
            return None
        if time.time() - entry.created_at > self._ttl_seconds:
            self._store.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: str) -> None:
        self._store[key] = CacheEntry(value=value, created_at=time.time())


class GroqClient:
    """Groq LLM client with retry, timeout and cache."""

    def __init__(self) -> None:
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not configured")

        verify: bool | str = True
        if settings.GROQ_INSECURE_SKIP_VERIFY:
            verify = False
            logger.warning("GROQ_INSECURE_SKIP_VERIFY is enabled. SSL certificate verification is disabled.")
        elif settings.GROQ_CA_BUNDLE:
            verify = settings.GROQ_CA_BUNDLE

        http_client = httpx.Client(verify=verify, timeout=settings.GROQ_TIMEOUT_SECONDS)
        self._client = Groq(
            api_key=settings.GROQ_API_KEY,
            timeout=settings.GROQ_TIMEOUT_SECONDS,
            http_client=http_client,
        )
        self._cache = SimpleCache(settings.CACHE_TTL_SECONDS)

    @retry(stop=stop_after_attempt(settings.GROQ_MAX_RETRIES), wait=wait_exponential(min=1, max=10))
    def generate_robot_test(
        self,
        prompt: str,
        context: str | None = None,
        page_structure: dict | None = None,
    ) -> str:
        page_structure_key = json.dumps(page_structure, ensure_ascii=False, sort_keys=True) if page_structure else ""
        cache_key = f"{settings.GROQ_MODEL}:{prompt}:{context or ''}:{page_structure_key}"
        cached = self._cache.get(cache_key)
        if cached:
            logger.info("Groq cache hit")
            return cached

        system_prompt = (
            "Você é um gerador de testes web em Robot Framework usando a biblioteca Browser. "
            "Responda SOMENTE com código Robot Framework válido. "
            "Não inclua explicações, observações, markdown, nem texto fora das seções do Robot. "
            "Use apenas as seções: *** Settings ***, *** Variables ***, *** Test Cases ***, *** Keywords ***. "
            "Use 'Library    Browser' e NÃO use Playwright/PlaywrightLibrary. "
            "Objetivo: gerar testes estáveis, executáveis e funcionais no Browser Library. "
            "Regras obrigatórias: "
            "1) NÃO use 'Open Browser'. Use sempre 'New Browser    chromium', 'New Context' e 'New Page'. "
            "2) Inclua fechamento com 'Close Browser' via teardown (preferencialmente Test Teardown ou Suite Teardown). "
            "3) Antes de qualquer ação, faça espera explícita com 'Wait For Elements State' (visible/attached) com timeout entre 10-15s. "
            "4) Use seletores válidos do Browser Library: 'css=#id', 'css=.class', 'css=[attr=\"v\"]', 'xpath=...'. "
            "5) NÃO use o formato inválido 'id:algo'. "
            "6) Prefira seletores estáveis: data-testid, role+name, aria-label, name. Use id somente se for único e estável. "
            "6.1) Evite id genérico/reutilizado (#button, #logo etc.) em sites com Web Components (ex.: YouTube). "
            "6.2) Quando houver risco de ambiguidade, use seletor mais específico (escopo + atributo), por exemplo: "
            "'css=ytd-masthead button[aria-label=\"Guia\"]' ou 'css=input[name=\"search_query\"]'. "
            "7) Para validação de título, use '${titulo}    Get Title' seguido de 'Should Be Equal'. "
            "8) Mantenha o cenário solicitado pelo usuário, sem inventar passos fora do fluxo principal. "
            "9) Gere comandos de navegação robustos (ex.: Go Back apenas após página de detalhe estar visível). "
            "10) Se houver múltiplos casos, mantenha cada caso independente e reprodutível."
        )
        if page_structure:
            system_prompt = (
                f"{system_prompt}\n\n"
                "You are generating Robot Framework tests. "
                "Here is the page structure in JSON format:\n"
                f"{json.dumps(page_structure, ensure_ascii=False)}"
            )
        user_content = prompt
        if context:
            user_content = f"Contexto:\n{context}\n\nPrompt:\n{prompt}"

        response = self._client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        content = response.choices[0].message.content
        self._cache.set(cache_key, content)
        return content
