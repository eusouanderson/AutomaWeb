from __future__ import annotations

import logging
import time
import json
from dataclasses import dataclass
from typing import Any

import httpx
from groq import Groq
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

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
            logger.warning(
                "GROQ_INSECURE_SKIP_VERIFY is enabled. SSL certificate verification is disabled."
            )
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
            if (
                self._last_health_ok_at
                and now - self._last_health_ok_at <= fallback_window
            ):
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
                "last_success_epoch": (
                    int(self._last_health_ok_at) if self._last_health_ok_at else None
                ),
                "error": self._last_health_error,
                "message": "LLM API unreachable.",
            }

    def _build_wwwh_prompt(
        self,
        *,
        what: str,
        why: str,
        where: str,
        how: str,
        extra: str | None = None,
    ) -> str:
        parts = [
            f"What (o quê):\n{what.strip() or 'N/A'}",
            f"Why (por que):\n{why.strip() or 'N/A'}",
            f"Where (onde):\n{where.strip() or 'N/A'}",
            f"How (como):\n{how.strip() or 'N/A'}",
        ]
        if extra and extra.strip():
            parts.append(extra.strip())
        return "\n\n".join(parts)

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
        page_structure_text = self._serialize_page_structure(
            page_structure, settings.LLM_MAX_PAGE_STRUCTURE_CHARS
        )

        page_structure_key = page_structure_text
        cache_key = f"{settings.GROQ_MODEL}:{prompt_text}:{context_text or ''}:{page_structure_key}"
        cached = self._cache.get(cache_key)
        if cached:
            logger.info("Groq cache hit")
            return cached

        system_prompt = """Você é um especialista em automação web com Robot Framework usando a Browser Library.

OBJETIVO:
Gerar testes estáveis, executáveis e consistentes.

FORMATO DE RESPOSTA (OBRIGATÓRIO):
- Responda SOMENTE com código Robot Framework válido
- NÃO escreva explicações
- Use apenas:
    *** Settings ***
    *** Variables ***
    *** Test Cases ***
    *** Keywords ***

BIBLIOTECA:
Library    Browser

---

FLUXO PADRÃO (SEMPRE SIGA):
1. New Browser    chromium
2. New Context
3. Set Browser Timeout    30s
4. New Page
5. Wait For Load State    load (ou elemento estável)
6. Interações
7. Validações
8. Close Browser (via teardown)

---

REGRAS CRÍTICAS (NUNCA VIOLAR):

- NÃO use Open Browser
- SEMPRE usar New Browser / Context / Page
- SEMPRE usar teardown com Close Browser
- SEMPRE esperar elemento antes de interagir:
    Wait For Elements State    <selector>    visible    30s

EXCEÇÃO IMPORTANTE:
- NÃO usar Wait For Elements State antes de:
    - Get Title
    - Get Url

VARIÁVEIS BUILT-IN (CRÍTICO):
- NUNCA usar ${OUTPUT}   → use ${OUTPUT_DIR} ou ${OUTPUT_FILE}
- NUNCA usar ${LOG}      → use ${LOG_FILE}
- NUNCA usar ${REPORT}   → use ${REPORT_FILE}

ASSERTIONS (OBRIGATÓRIO — ERROS FATAIS SE VIOLADO):
- Should Be Equal SEMPRE requer 2 argumentos: actual E expected
  CORRETO:  Should Be Equal    ${title}    Título Esperado
  ERRADO:   Should Be Equal    ${title}
- Mesma regra para: Should Contain, Should Match, Should Not Be Equal, etc.

KEYWORDS NUNCA PUEDEN SER VAZIAS:
- Toda keyword definida em *** Keywords *** DEVE ter ao menos 1 step executável
  ERRADO:
    My Keyword
        [Documentation]    Descrição
  CORRETO:
    My Keyword
        [Documentation]    Descrição
        No Operation

VALIDAÇÃO DE TÍTULO (PADRÃO FIXO):
${title}=    Get Title
Should Be Equal    ${title}    Título Esperado

---

SELETORES (MUITO IMPORTANTE):

PRIORIDADE:
1. data-testid
2. role + name
3. aria-label
4. name
5. id (somente se estável)

NUNCA USAR:
- id:algo
- xpath genérico (//div, //a, //*...)
- css=h1 para título

SEMPRE:
- usar css= ou xpath=
- evitar ambiguidade
- usar nth=0 se necessário

---

REGRAS DE ESTABILIDADE:

- Sempre aguardar carregamento antes de ação
- Nunca clicar sem wait
- Nunca usar seletor genérico
- Cada teste deve ser independente
- Não inventar passos fora do fluxo solicitado

---

AUTO-VALIDAÇÃO (ANTES DE RESPONDER):

Revise mentalmente:
- Usei New Browser correto?
- Tem Set Browser Timeout?
- Todos os cliques têm wait antes?
- Não usei seletores inválidos?
- Tem teardown com Close Browser?
- Should Be Equal tem EXATAMENTE 2 argumentos (actual e expected)?
- Não usei ${OUTPUT} nem ${LOG} nem ${REPORT}?
- Todas as keywords definidas têm pelo menos 1 step executável (não apenas [Documentation])?

Se algo estiver errado, CORRIJA antes de responder.

---

EXEMPLO CORRETO:

Wait For Elements State    css=input[name="q"]    visible    30s
Fill Text    css=input[name="q"]    teste

EXEMPLO ERRADO (NUNCA FAZER):

Input Text    id:search    teste
Click    //button

---

Agora gere o teste solicitado seguindo TODAS as regras."""
        if page_structure_text:
            system_prompt = (
                f"{system_prompt}\n\n"
                "You are generating Robot Framework tests. "
                "Here is the page structure in JSON format:\n"
                f"{page_structure_text}"
            )
        user_content = self._build_wwwh_prompt(
            what=prompt_text
            or "Gerar teste Robot Framework conforme solicitação recebida.",
            why="Gerar um teste automatizado estável e executável para validar o fluxo solicitado.",
            where=context_text or "Sem contexto adicional informado.",
            how="Responder apenas com código Robot Framework válido, seguindo as regras do system prompt.",
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        try:
            content = self._chat_completion(messages)
        except Exception as exc:
            if not self._is_payload_too_large(exc):
                raise

            logger.warning(
                "LLM returned 413 payload too large. Retrying once with compact fallback payload."
            )
            fallback_prompt = (
                self._truncate_text(
                    prompt_text, max(800, settings.LLM_MAX_PROMPT_CHARS // 3)
                )
                or ""
            )
            fallback_context = self._truncate_text(
                context_text, max(1200, settings.LLM_MAX_CONTEXT_CHARS // 3)
            )
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

            compact_user_content = self._build_wwwh_prompt(
                what=fallback_prompt
                or "Gerar teste Robot Framework conforme solicitação recebida.",
                why="Gerar um teste automatizado estável mesmo após redução de payload.",
                where=(
                    "Contexto reduzido automaticamente por limite de payload:\n"
                    f"{fallback_context}"
                    if fallback_context
                    else "Sem contexto adicional informado."
                ),
                how="Responder apenas com código Robot Framework válido, mantendo o cenário solicitado.",
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

    def _serialize_page_structure(
        self, page_structure: dict | None, max_chars: int
    ) -> str:
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

        user_content = self._build_wwwh_prompt(
            what=(
                "Regenerar somente a linha de step abaixo mantendo a intenção do prompt original.\n"
                f"Prompt original: {original_prompt}\n"
                f"Step com falha: {failing_step}"
            ),
            why=f"Corrigir o erro atual do step sem alterar o restante do teste. Erro: {error_message}",
            where=context or "N/A",
            how="Retornar apenas uma linha de Robot Framework equivalente e mais robusta.",
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
