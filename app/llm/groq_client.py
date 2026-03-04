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
            "Use 'Library    Browser' e NÃO use Playwright/PlaywrightLibrary."
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
