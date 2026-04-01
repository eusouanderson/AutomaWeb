from __future__ import annotations

import logging
import time
import json
from dataclasses import dataclass
from typing import Any

import httpx
from groq import Groq
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)


class PayloadTooLargeError(Exception):
    """Raised when LLM request exceeds provider payload limits even after fallback."""


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
        self._last_health_ok_at: float | None = None
        self._last_health_error: str | None = None

    def check_api_health(self) -> dict[str, str | bool | int | None]:
        """Check if the upstream LLM is reachable, with recent-success fallback."""
        now = time.time()
        try:
            response = self._client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a health-check assistant."},
                    {"role": "user", "content": "Reply only with: ok"},
                ],
                max_tokens=4,
                temperature=0,
            )
            _ = (response.choices[0].message.content or "").strip()
            self._last_health_ok_at = now
            self._last_health_error = None
            return {
                "ok": True,
                "source": "live",
                "model": settings.GROQ_MODEL,
                "checked_at_epoch": int(now),
                "last_success_epoch": int(now),
                "error": None,
                "message": "LLM API reachable.",
            }
        except Exception as exc:
            self._last_health_error = f"{exc.__class__.__name__}: {exc}"
            fallback_window = settings.LLM_HEALTH_FALLBACK_WINDOW_SECONDS
            if self._last_health_ok_at and now - self._last_health_ok_at <= fallback_window:
                return {
                    "ok": True,
                    "source": "fallback_cache",
                    "model": settings.GROQ_MODEL,
                    "checked_at_epoch": int(now),
                    "last_success_epoch": int(self._last_health_ok_at),
                    "error": self._last_health_error,
                    "message": "Live check failed, using recent successful health check fallback.",
                }
            return {
                "ok": False,
                "source": "live",
                "model": settings.GROQ_MODEL,
                "checked_at_epoch": int(now),
                "last_success_epoch": int(self._last_health_ok_at) if self._last_health_ok_at else None,
                "error": self._last_health_error,
                "message": "LLM API unreachable.",
            }

    @retry(
        stop=stop_after_attempt(settings.GROQ_MAX_RETRIES),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_not_exception_type(PayloadTooLargeError),
    )
    def generate_robot_test(
        self,
        prompt: str,
        context: str | None = None,
        page_structure: dict | None = None,
    ) -> str:
        prompt_text = self._truncate_text(prompt, settings.LLM_MAX_PROMPT_CHARS)
        context_text = self._truncate_text(context, settings.LLM_MAX_CONTEXT_CHARS)
        page_structure_text = self._serialize_page_structure(page_structure, settings.LLM_MAX_PAGE_STRUCTURE_CHARS)

        page_structure_key = page_structure_text
        cache_key = f"{settings.GROQ_MODEL}:{prompt_text}:{context_text or ''}:{page_structure_key}"
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
            "2) Após 'New Context', adicione SEMPRE: 'Set Browser Timeout    30s' para definir timeout global. "
            "3) Inclua fechamento com 'Close Browser' via teardown (preferencialmente Test Teardown ou Suite Teardown). "
            "4) Antes de interações com elementos DOM (Click, Fill Text, Input Text), use 'Wait For Elements State    <selector>    visible    30s'. "
            "   EXCEÇÃO IMPORTANTE: NÃO use 'Wait For Elements State' antes de 'Get Title' ou 'Get Url'. "
            "   Para verificar título da página, use EXATAMENTE este padrão: "
            "   New Page → (Wait For Load State    load  OU  aguarde algum elemento da página) → Get Title → Should Be Equal. "
            "   O 'Get Title' lê o <title> do HTML head; não há nenhum elemento DOM a esperar. "
            "5) Use seletores válidos do Browser Library: 'css=#id', 'css=.class', 'css=[attr=\"v\"]', 'xpath=...'. "
            "6) NÃO use o formato inválido 'id:algo'. "
            "7) Prefira seletores estáveis: data-testid, role+name, aria-label, name. Use id somente se for único e estável. "
            "7.1) Evite id genérico/reutilizado (#button, #logo etc.) em sites com Web Components (ex.: YouTube). "
            "7.2) Quando houver risco de ambiguidade, use seletor mais específico (escopo + atributo), por exemplo: "
            "'css=ytd-masthead button[aria-label=\"Guia\"]' ou 'css=input[name=\"search_query\"]'. "
            "8) Para validação de título, use '${titulo}    Get Title' seguido de 'Should Be Equal'. "
            "9) Mantenha o cenário solicitado pelo usuário, sem inventar passos fora do fluxo principal. "
            "10) Gere comandos de navegação robustos (ex.: Go Back apenas após página de detalhe estar visível). "
            "11) Se houver múltiplos casos, mantenha cada caso independente e reprodutível. "
            "12) Nunca use XPath genérico como '//div', '//a', '//*[@id=...]' sem escopo estável. "
            "13) Prefira seletores com 'getByRole/getByLabel' representados em Browser selector engine como "
            "'role=button[name=\"...\"]' quando possível. "
            "14) Evite estritamente seletores ambíguos; se houver múltiplas correspondências, "
            "use escopo estável ou '>> nth=0' explicitamente. "
            "15) NÃO invente seletores como 'css=h1' para verificar o título — o título vem de Get Title, não de um h1 visível. "
            "    Somente use 'Wait For Elements State    css=h1' se o h1 for um elemento que o usuário precisa interagir ou verificar como texto visível."
        )
        if page_structure_text:
            system_prompt = (
                f"{system_prompt}\n\n"
                "You are generating Robot Framework tests. "
                "Here is the page structure in JSON format:\n"
                f"{page_structure_text}"
            )
        user_content = prompt_text
        if context_text:
            user_content = f"Contexto:\n{context_text}\n\nPrompt:\n{prompt_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        try:
            content = self._chat_completion(messages)
        except Exception as exc:
            if not self._is_payload_too_large(exc):
                raise

            logger.warning("LLM returned 413 payload too large. Retrying once with compact fallback payload.")
            fallback_prompt = self._truncate_text(prompt_text, max(800, settings.LLM_MAX_PROMPT_CHARS // 3)) or ""
            fallback_context = self._truncate_text(context_text, max(1200, settings.LLM_MAX_CONTEXT_CHARS // 3))
            fallback_structure = self._serialize_page_structure(
                page_structure,
                max(2000, settings.LLM_MAX_PAGE_STRUCTURE_CHARS // 4),
            )

            compact_system_prompt = system_prompt
            if fallback_structure:
                compact_system_prompt = (
                    "O contexto da página foi reduzido automaticamente para caber no limite de payload. "
                    f"{compact_system_prompt}"
                )

            compact_user_content = fallback_prompt
            if fallback_context:
                compact_user_content = (
                    "Contexto reduzido automaticamente por limite de payload:\n"
                    f"{fallback_context}\n\nPrompt:\n{fallback_prompt}"
                )

            compact_messages = [
                {"role": "system", "content": compact_system_prompt},
                {"role": "user", "content": compact_user_content},
            ]
            try:
                content = self._chat_completion(compact_messages)
            except Exception as compact_exc:
                if self._is_payload_too_large(compact_exc):
                    raise PayloadTooLargeError(
                        "LLM payload exceeds provider limits even after automatic fallback reduction"
                    ) from compact_exc
                raise

        self._cache.set(cache_key, content)
        return content

    def _chat_completion(self, messages: list[dict[str, Any]]) -> str:
        response = self._client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,  # type: ignore[arg-type]
        )
        return response.choices[0].message.content or ""

    def _truncate_text(self, value: str | None, limit: int) -> str | None:
        if value is None:
            return None
        if len(value) <= limit:
            return value
        return value[:limit] + "\n...[TRUNCATED]"

    def _serialize_page_structure(self, page_structure: dict | None, max_chars: int) -> str:
        if not page_structure:
            return ""
        as_text = json.dumps(page_structure, ensure_ascii=False)
        if len(as_text) <= max_chars:
            return as_text
        return as_text[:max_chars] + "\n...[TRUNCATED]"

    def _is_payload_too_large(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code == 413:
            return True
        response = getattr(exc, "response", None)
        return getattr(response, "status_code", None) == 413

    def regenerate_robot_step(
        self,
        original_prompt: str,
        failing_step: str,
        error_message: str,
        context: str | None = None,
    ) -> str:
        """Regenerate only one Robot step for a failing locator/action."""
        system_prompt = (
            "Você corrige apenas UMA linha de step de Robot Framework usando Browser Library. "
            "Retorne apenas a linha corrigida, sem markdown, sem explicações. "
            "A linha precisa conter wait explícito ou locator estável, evitando estrito ambíguo."
        )

        user_content = (
            f"Prompt original:\n{original_prompt}\n\n"
            f"Contexto adicional:\n{context or 'N/A'}\n\n"
            f"Step com falha:\n{failing_step}\n\n"
            f"Erro:\n{error_message}\n\n"
            "Gere a linha substituta equivalente e robusta."
        )

        response = self._client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        return content.splitlines()[0] if content else ""
