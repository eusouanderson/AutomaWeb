import json
import logging
import os
import re
import asyncio
from datetime import datetime
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Robot Framework syntax-correction constants
# ---------------------------------------------------------------------------

# LLM frequently emits wrong names for RF built-in variables.
_ROBOT_VAR_CORRECTIONS: dict[str, str] = {
    "${OUTPUT}": "${OUTPUT_DIR}",
    "${LOG}": "${LOG_FILE}",
    "${REPORT}": "${REPORT_FILE}",
    "${DEBUG}": "${DEBUG_FILE}",
}

# Assertion keywords that REQUIRE at least 2 positional arguments.
_ASSERTIONS_MIN_2_ARGS: frozenset[str] = frozenset(
    {
        "Should Be Equal",
        "Should Be Equal As Numbers",
        "Should Be Equal As Integers",
        "Should Be Equal As Strings",
        "Should Contain",
        "Should Not Contain",
        "Should Match",
        "Should Match Regexp",
        "Should Not Match Regexp",
        "Should Not Be Equal",
        "Should Not Be Equal As Integers",
        "Should Not Be Equal As Numbers",
    }
)

# Keyword "metadata" settings lines — a keyword with ONLY these is empty.
_KW_METADATA_TAGS: frozenset[str] = frozenset(
    {
        "[documentation]",
        "[arguments]",
        "[tags]",
        "[return]",
        "[timeout]",
        "[setup]",
        "[teardown]",
        "[template]",
    }
)

from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import RetryError

from app.ai_validation.self_healing_service import AITestSelfHealingService
from app.core.config import settings
from app.llm.copilot_adapter import CopilotServiceAdapter, PayloadTooLargeError
from app.models.generated_test import GeneratedTest
from app.models.test_request import TestRequest
from app.repositories.project_repository import ProjectRepository
from app.repositories.test_repository import TestRepository
from app.services.element_scanner import ElementScannerError, ElementScannerService

logger = logging.getLogger(__name__)


class LLMServiceUnavailableError(Exception):
    """Raised when LLM provider is unavailable."""


class LLMInvalidRequestError(Exception):
    """Raised when LLM provider rejects request payload/model/options."""


class ScanUnavailableError(Exception):
    """Raised when element scan fails during test generation."""


class TestService:
    """Test generation business rules."""

    def __init__(
        self,
        test_repository: TestRepository | None = None,
        project_repository: ProjectRepository | None = None,
        copilot_client: CopilotServiceAdapter | None = None,
        element_scanner: ElementScannerService | None = None,
    ) -> None:
        self._test_repository = test_repository or TestRepository()
        self._project_repository = project_repository or ProjectRepository()
        self._copilot_client = copilot_client or CopilotServiceAdapter()
        self._element_scanner = element_scanner or ElementScannerService()
        self._self_healing = AITestSelfHealingService()
        self._last_generation_metadata: dict | None = None

    @property
    def last_generation_metadata(self) -> dict | None:
        return self._last_generation_metadata

    def check_llm_health(self) -> dict[str, str | bool | int | None]:
        return self._copilot_client.check_api_health()

    async def generate_test(
        self,
        session: AsyncSession,
        project_id: int,
        prompt: str,
        context: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        ai_debug: bool = False,
        force_rescan: bool = False,
    ) -> GeneratedTest:
        self._last_generation_metadata = None
        project = await self._project_repository.get(session, project_id)
        if not project:
            raise ValueError("Project not found")

        test_request = TestRequest(
            project_id=project_id, prompt=prompt, context=context, status="processing"
        )
        test_request = await self._test_repository.create_test_request(
            session, test_request
        )

        page_structure: dict | None = None
        if project.url:
            if project.scan_cache and not force_rescan:
                # Reuse cached scan — no need to hit the page again
                page_structure = json.loads(project.scan_cache)
                logger.info(
                    "Reusing cached scan for project %s (cached at %s)",
                    project_id,
                    project.scan_cached_at,
                )
            else:
                try:
                    scan_result = await self._element_scanner.scan_url(str(project.url))
                except ElementScannerError as exc:
                    test_request.status = "failed"
                    await self._test_repository.update_test_request(
                        session, test_request
                    )
                    logger.error(
                        "Failed to scan project URL before generating test: %s", exc
                    )
                    raise ScanUnavailableError(str(exc)) from exc
                page_structure = scan_result.model_dump()
                # Persist updated scan in project cache
                project.scan_cache = json.dumps(page_structure, ensure_ascii=False)
                project.scan_cached_at = datetime.utcnow()
                await session.flush()

        generation_context = self._build_generation_context(
            user_context=context,
            test_directory=project.test_directory,
        )

        try:
            generation_options: dict[str, object] = {}
            if model is not None:
                generation_options["model"] = model
            if system_prompt is not None:
                generation_options["system_prompt"] = system_prompt
            if temperature is not None:
                generation_options["temperature"] = temperature
            if max_tokens is not None:
                generation_options["max_tokens"] = max_tokens

            content = await self._copilot_client.generate_robot_test(
                prompt_text=prompt,
                context_text=generation_context,
                page_structure=page_structure,
                **generation_options,
            )
            self._last_generation_metadata = {
                "strategy": "single",
                "chunk_target_chars": settings.LLM_DOM_CHUNK_TARGET_CHARS,
                "chunk_count": 1,
                "chunk_parts": None,
            }
        except RetryError as exc:
            test_request.status = "failed"
            await self._test_repository.update_test_request(session, test_request)
            logger.error("Failed to generate test: LLM connection retries exhausted")
            raise LLMServiceUnavailableError("LLM provider connection failed") from exc
        except PayloadTooLargeError as exc:
            if page_structure and settings.LLM_DOM_CHUNKING_ENABLED:
                logger.warning(
                    "LLM payload too large. Trying DOM chunked generation for project %s",
                    project_id,
                )
                try:
                    content = await self._generate_robot_test_chunked(
                        prompt,
                        generation_context,
                        page_structure,
                    )
                except PayloadTooLargeError:
                    test_request.status = "failed"
                    await self._test_repository.update_test_request(
                        session, test_request
                    )
                    logger.error(
                        "Failed to generate test: LLM payload too large even after chunked generation"
                    )
                    raise LLMServiceUnavailableError(
                        "LLM request payload too large"
                    ) from exc
            else:
                test_request.status = "failed"
                await self._test_repository.update_test_request(session, test_request)
                logger.error(
                    "Failed to generate test: LLM payload too large even after fallback"
                )
                raise LLMServiceUnavailableError(
                    "LLM request payload too large"
                ) from exc
        except Exception as exc:
            classification = self._classify_llm_exception(exc)
            if classification == "invalid-request":
                test_request.status = "failed"
                await self._test_repository.update_test_request(session, test_request)
                status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) and exc.response else None
                logger.error(
                    "Failed to generate test due to LLM request rejection: HTTP %s",
                    status_code,
                )
                raise LLMInvalidRequestError(
                    f"LLM request rejected by provider (HTTP {status_code}). "
                    "Verifique modelo e parâmetros de geração."
                ) from exc
            if classification == "unavailable":
                test_request.status = "failed"
                await self._test_repository.update_test_request(session, test_request)
                logger.error(
                    "Failed to generate test due to LLM availability issue: %s",
                    exc.__class__.__name__,
                )
                raise LLMServiceUnavailableError(
                    self._build_llm_unavailable_message(exc)
                ) from exc
            raise

        content = self._sanitize_robot_output(content, context=context)

        if settings.AI_VALIDATION_ENABLED:
            healed = await self._self_healing.heal_test(
                content=content,
                page_url=str(project.url) if project.url else None,
                prompt=prompt,
                context=context,
                copilot_client=self._copilot_client,
                ai_debug=ai_debug,
            )
            content = healed.final_content

        test_request.status = "completed"
        await self._test_repository.update_test_request(session, test_request)

        file_path = self._write_robot_file(
            test_request.id, content, project.name, project.test_directory
        )
        generated_test = GeneratedTest(
            test_request_id=test_request.id,
            content=content,
            file_path=str(file_path),
        )
        return await self._test_repository.create_generated_test(
            session, generated_test
        )

    async def get_generated_test(
        self, session: AsyncSession, test_id: int
    ) -> GeneratedTest | None:
        return await self._test_repository.get_generated_test(session, test_id)

    async def list_generated_tests_by_project(
        self, session: AsyncSession, project_id: int
    ) -> list[GeneratedTest]:
        project = await self._project_repository.get(session, project_id)
        if not project:
            raise ValueError("Project not found")
        return await self._test_repository.list_generated_tests_by_project(
            session, project_id
        )

    async def delete_generated_test(self, session: AsyncSession, test_id: int) -> bool:
        generated = await self._test_repository.get_generated_test(session, test_id)
        if not generated:
            return False

        file_path = Path(generated.file_path)
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                logger.warning("Could not remove generated test file: %s", file_path)

        await self._test_repository.delete_generated_test(session, generated)
        return True

    async def improve_robot_test(
        self,
        session: AsyncSession,
        test_id: int,
        content: str,
        feedback: str | None = None,
    ) -> str | None:
        """Send Robot Framework content to the AI (with page scan context) and return improved version."""
        generated = await self._test_repository.get_generated_test(session, test_id)
        if not generated:
            return None

        # Resolve project to get scan context
        test_request = await self._test_repository.get_test_request(
            session, generated.test_request_id
        )
        project = (
            await self._project_repository.get(session, test_request.project_id)
            if test_request
            else None
        )

        page_structure: dict | None = None
        if project and project.url:
            page_structure = await self._get_or_refresh_scan(session, project)

        improvement_context = self._build_generation_context(
            user_context=feedback,
            test_directory=project.test_directory if project else None,
            exclude_file_path=generated.file_path,
        )

        improvement_prompt = (
            "Melhore o teste Robot Framework abaixo. "
            "Preserve a estrutura das seções (*** Settings ***, *** Variables ***, *** Test Cases ***, *** Keywords ***). "
            "Corrija problemas de sintaxe, melhore a legibilidade, otimize keywords, "
            "adicione waits onde necessário e sugira uma estrutura de teste melhor. "
            "Siga obrigatoriamente o padrão de execução Browser: New Browser -> New Context -> Set Browser Timeout 30s -> New Page. "
            "Se houver feedback da execução, trate-o como prioridade. "
            "Use os testes existentes do diretório como referência de estilo e mantenha os testes que já passam alinhados com esse padrão. "
            "Retorne APENAS código Robot Framework válido, sem explicações ou markdown.\n\n"
            f"{content}"
        )
        try:
            improved = await self._copilot_client.generate_robot_test(
                prompt_text=improvement_prompt,
                context_text=improvement_context,
                page_structure=page_structure,
            )
        except Exception as exc:
            if self._classify_llm_exception(exc) == "unavailable":
                raise LLMServiceUnavailableError(
                    self._build_llm_unavailable_message(exc)
                ) from exc
            raise
        return self._sanitize_robot_output(improved)

    def _classify_llm_exception(self, exc: Exception) -> str | None:
        """Classify provider exceptions into invalid-request vs temporary-unavailable."""
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code if exc.response else None
            if status_code is not None:
                if status_code in {408, 429} or status_code >= 500:
                    return "unavailable"
                if 400 <= status_code < 500:
                    return "invalid-request"

        error_name = exc.__class__.__name__
        connectivity_error_names = {
            "APIConnectionError",
            "APITimeoutError",
            "ReadTimeout",
            "ConnectTimeout",
            "ConnectError",
            "TimeoutException",
            "NetworkError",
            "RequestError",
            "RetryError",
        }
        if error_name in connectivity_error_names or isinstance(exc, httpx.RequestError):
            return "unavailable"
        return None

    def _build_llm_unavailable_message(self, exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code if exc.response else None
            if status_code == 429:
                response_text = (exc.response.text or "").lower() if exc.response else ""
                if "weekly rate limit" in response_text or "exceeded your weekly rate limit" in response_text:
                    return "LLM provider weekly rate limit exceeded"
                return "LLM provider rate limit exceeded"
            if status_code == 408:
                return "LLM provider request timed out"
            if status_code is not None and status_code >= 500:
                return f"LLM provider unavailable (HTTP {status_code})"
        return "LLM provider connection failed"

    async def _get_or_refresh_scan(self, session: AsyncSession, project) -> dict | None:
        """Return cached page scan if fresh, otherwise re-scan and update cache. Returns None on failure."""
        now = datetime.utcnow()
        ttl = settings.SCAN_CACHE_TTL_SECONDS

        if (
            project.scan_cache
            and project.scan_cached_at
            and (now - project.scan_cached_at).total_seconds() < ttl
        ):
            logger.info("Using cached page scan for project %s", project.id)
            return json.loads(project.scan_cache)

        try:
            scan_result = await self._element_scanner.scan_url(str(project.url))
        except ElementScannerError as exc:
            logger.warning("Could not scan project URL for AI improve: %s", exc)
            return None

        data = scan_result.model_dump()
        project.scan_cache = json.dumps(data, ensure_ascii=False)
        project.scan_cached_at = now
        await session.flush()
        return data

    async def save_robot_test_content(
        self, session: AsyncSession, test_id: int, content: str
    ) -> "GeneratedTest | None":
        """Persist new content for an existing generated test."""
        generated = await self._test_repository.get_generated_test(session, test_id)
        if not generated:
            return None
        # Keep editor content intact; save should not rewrite user-authored Robot syntax.
        normalized = content.replace("\r\n", "\n")
        file_path = Path(generated.file_path)
        file_path.write_text(normalized, encoding="utf-8")
        generated.content = normalized
        await session.flush()
        return generated

    def _write_robot_file(
        self,
        test_request_id: int,
        content: str,
        project_name: str,
        test_directory: str | None = None,
    ) -> Path:
        base_dir = (
            Path(test_directory)
            if test_directory
            else Path(settings.STATIC_DIR) / "projects"
        )
        safe_name = self._safe_dir_name(project_name)
        project_dir = base_dir / safe_name
        os.makedirs(project_dir, exist_ok=True)
        file_path = project_dir / f"generated_test_{test_request_id}.robot"
        file_path.write_text(content, encoding="utf-8")
        logger.info("Robot test saved at %s", file_path)
        return file_path

    def _safe_dir_name(self, name: str) -> str:
        safe = (
            "".join(c for c in name if c.isalnum() or c in ("-", "_", " "))
            .strip()
            .replace(" ", "_")
            or "project"
        )
        return f"🧪_{safe}"

    def _build_generation_context(
        self,
        user_context: str | None,
        test_directory: str | None,
        exclude_file_path: str | None = None,
    ) -> str | None:
        """Compose LLM context from user context + existing Robot tests on disk."""
        user_part = (user_context or "").strip()
        tests_part = self._collect_robot_tests_context(
            test_directory,
            exclude_file_path=exclude_file_path,
        )

        if user_part and tests_part:
            merged = (
                f"{user_part}\n\n"
                "Contexto adicional (testes existentes no diretório do projeto):\n"
                f"{tests_part}"
            )
        elif user_part:
            merged = user_part
        elif tests_part:
            merged = (
                "Contexto adicional (testes existentes no diretório do projeto):\n"
                f"{tests_part}"
            )
        else:
            return None

        max_chars = max(200, int(settings.LLM_MAX_CONTEXT_CHARS))
        if len(merged) <= max_chars:
            return merged

        # Keep explicit user input as priority, and use remaining space for file context.
        if user_part:
            if len(user_part) >= max_chars:
                return user_part[:max_chars]
            sep = "\n\nContexto adicional (parcial):\n"
            remaining = max_chars - len(user_part) - len(sep)
            if remaining > 0 and tests_part:
                return f"{user_part}{sep}{tests_part[:remaining]}"
            return user_part[:max_chars]

        return merged[:max_chars]

    def _collect_robot_tests_context(
        self,
        test_directory: str | None,
        exclude_file_path: str | None = None,
    ) -> str | None:
        """Read existing .robot tests from project directory for prompt grounding."""
        if not test_directory:
            return None

        base_dir = Path(test_directory)
        if not base_dir.exists() or not base_dir.is_dir():
            return None

        max_files = 4
        # Reserve part of context budget for disk-based examples.
        max_total_chars = max(400, int(settings.LLM_MAX_CONTEXT_CHARS // 2))
        remaining = max_total_chars
        excluded_path = Path(exclude_file_path).resolve() if exclude_file_path else None

        robot_files = sorted(
            base_dir.rglob("*.robot"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        snippets: list[str] = []
        for path in robot_files:
            if len(snippets) >= max_files or remaining <= 0:
                break
            try:
                resolved_path = path.resolve()
            except OSError:
                continue
            if excluded_path is not None and resolved_path == excluded_path:
                continue
            # Avoid huge generated outputs from logs/reports folders.
            if any(part.lower() in {"report", "reports", "log", "logs"} for part in path.parts):
                continue
            try:
                raw = path.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                continue
            if not raw:
                continue

            rel = path.relative_to(base_dir)
            header = f"\n### Arquivo: {rel.as_posix()}\n"
            budget_for_content = max(120, remaining - len(header) - 1)
            body = raw[:budget_for_content]
            if len(raw) > budget_for_content:
                body += "\n... [conteúdo truncado]"
            chunk = f"{header}{body}"
            snippets.append(chunk)
            remaining -= len(chunk)

        if not snippets:
            return None

        return "\n".join(snippets).strip()

    async def _generate_robot_test_chunked(
        self, prompt: str, context: str | None, page_structure: dict
    ) -> str:
        base_target = max(200, settings.LLM_DOM_CHUNK_TARGET_CHARS)
        target_candidates = [
            base_target,
            max(800, base_target // 2),
            max(400, base_target // 4),
        ]

        # Preserve order and avoid duplicate retries with the same target size.
        deduped_targets: list[int] = []
        for target in target_candidates:
            if target not in deduped_targets:
                deduped_targets.append(target)

        last_payload_error: PayloadTooLargeError | None = None
        structure_candidates = [
            page_structure,
            self._compact_page_structure(page_structure),
        ]

        for structure_idx, candidate_structure in enumerate(structure_candidates):
            for target_chars in deduped_targets:
                chunks = self._split_page_structure(
                    candidate_structure, target_chars=target_chars
                )
                if len(chunks) <= 1:
                    continue

                max_parts = max(1, settings.LLM_DOM_CHUNK_MAX_PARTS)
                chunks = chunks[:max_parts]

                try:
                    merged, chunk_parts_meta = await self._generate_from_chunks(
                        prompt=prompt,
                        context=context,
                        chunks=chunks,
                    )
                    self._last_generation_metadata = {
                        "strategy": "chunked",
                        "chunk_target_chars": target_chars,
                        "chunk_count": len(chunk_parts_meta),
                        "chunk_parts": chunk_parts_meta,
                        "scan_compacted": bool(structure_idx == 1),
                    }
                    return merged
                except PayloadTooLargeError as exc:
                    last_payload_error = exc
                    logger.warning(
                        "Chunked generation still too large. Retrying with smaller chunks (target=%s, compacted=%s)",
                        target_chars,
                        bool(structure_idx == 1),
                    )

        if last_payload_error:
            raise last_payload_error
        raise PayloadTooLargeError("Page structure cannot be split into smaller chunks")

    async def _generate_from_chunks(
        self, prompt: str, context: str | None, chunks: list[dict]
    ) -> tuple[str, list[dict]]:
        partial_outputs: list[str] = []
        chunk_parts_meta: list[dict] = []

        for idx, chunk in enumerate(chunks, start=1):
            chunk_prompt = (
                f"What (o quê):\n{prompt}\n\n"
                "Why (por que):\nGerar cobertura incremental por partes para evitar limite de payload e manter o cenário solicitado.\n\n"
                f"Where (onde):\nSubconjunto do DOM referente ao CHUNK {idx}/{len(chunks)}.\n\n"
                "How (como):\nGerar casos APENAS com base neste chunk, sem duplicar casos de chunks anteriores e com nomes descritivos."
            )
            part = await self._copilot_client.generate_robot_test(
                prompt_text=chunk_prompt,
                context_text=context,
                page_structure=chunk,
            )
            partial_outputs.append(self._sanitize_robot_output(part, context=context))
            chunk_parts_meta.append(
                {
                    "index": idx,
                    "approx_chars": len(
                        json.dumps(chunk, ensure_ascii=False, separators=(",", ":"))
                    ),
                    "keys": sorted(str(key) for key in chunk.keys()),
                }
            )

        if not partial_outputs:
            raise PayloadTooLargeError("Chunked generation produced no output")

        return self._merge_robot_parts(partial_outputs), chunk_parts_meta

    def _compact_page_structure(self, page_structure: dict) -> dict:
        """Reduce heavy scan payload while preserving the most relevant keys for test generation."""
        max_items_per_list = 30
        max_string_chars = 220

        def compact(value):
            if isinstance(value, str):
                return value[:max_string_chars]
            if isinstance(value, list):
                return [compact(item) for item in value[:max_items_per_list]]
            if isinstance(value, dict):
                compacted: dict = {}
                for key, item in value.items():
                    if isinstance(item, str):
                        compacted[key] = item[:max_string_chars]
                    elif isinstance(item, list):
                        compacted[key] = [
                            compact(entry) for entry in item[:max_items_per_list]
                        ]
                    elif isinstance(item, dict):
                        compacted[key] = compact(item)
                    else:
                        compacted[key] = item
                return compacted
            return value

        return compact(page_structure)  # type: ignore[arg-type]

    def _split_page_structure(
        self, page_structure: dict, target_chars: int | None = None
    ) -> list[dict]:
        target_chars = max(200, target_chars or settings.LLM_DOM_CHUNK_TARGET_CHARS)
        serialized = json.dumps(
            page_structure, ensure_ascii=False, separators=(",", ":")
        )
        if len(serialized) <= target_chars:
            return [page_structure]

        scalar_base: dict = {}
        sequence_items: list[tuple[str, object]] = []

        for key, value in page_structure.items():
            if isinstance(value, list):
                for item in value:
                    sequence_items.append((key, item))
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    sequence_items.append((f"{key}.{sub_key}", sub_value))
            else:
                scalar_base[key] = value

        # Fallback when nothing is splittable: chunk a minified string payload.
        if not sequence_items:
            text_chunks = [
                serialized[i : i + target_chars]
                for i in range(0, len(serialized), target_chars)
            ]
            return [
                {"chunk_text": t, "chunk_format": "json-minified"} for t in text_chunks
            ]

        chunks: list[dict] = []
        current: dict = dict(scalar_base)

        def append_entry(container: dict, dotted_key: str, entry_value: object) -> None:
            if "." not in dotted_key:
                container.setdefault(dotted_key, []).append(entry_value)
                return
            root, sub = dotted_key.split(".", 1)
            container.setdefault(root, {})
            root_value = container[root]
            if not isinstance(root_value, dict):
                container[root] = {}
                root_value = container[root]
            root_value.setdefault(sub, []).append(entry_value)

        for dotted_key, value in sequence_items:
            candidate = json.loads(json.dumps(current, ensure_ascii=False))
            append_entry(candidate, dotted_key, value)
            candidate_len = len(
                json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))
            )

            if candidate_len <= target_chars:
                current = candidate
                continue

            # If current already has data beyond base, flush and start new chunk with this item.
            if current != scalar_base:
                chunks.append(current)
                current = dict(scalar_base)
                append_entry(current, dotted_key, value)
                continue

            # Single entry is already too large: keep it as its own chunk to preserve data.
            chunks.append(candidate)
            current = dict(scalar_base)

        if current != scalar_base:
            chunks.append(current)

        return chunks or [page_structure]

    def _merge_robot_parts(self, parts: list[str]) -> str:
        section_order = [
            "*** Settings ***",
            "*** Variables ***",
            "*** Test Cases ***",
            "*** Keywords ***",
        ]
        merged: dict[str, list[str]] = {name: [] for name in section_order}

        for part in parts:
            sections = self._extract_robot_sections(part)
            for name in section_order:
                merged[name].extend(sections.get(name, []))

        output_lines: list[str] = []
        for name in section_order:
            lines = self._dedupe_preserve_order(merged[name])
            if not lines:
                continue
            output_lines.append(name)
            output_lines.extend(lines)
            output_lines.append("")

        return "\n".join(output_lines).strip() + "\n"

    def _extract_robot_sections(self, content: str) -> dict[str, list[str]]:
        section_order = {
            "*** Settings ***",
            "*** Variables ***",
            "*** Test Cases ***",
            "*** Keywords ***",
        }
        sections: dict[str, list[str]] = {name: [] for name in section_order}
        current: str | None = None
        for line in content.splitlines():
            stripped = line.strip()
            if stripped in section_order:
                current = stripped
                continue
            if current:
                sections[current].append(line)
        return sections

    def _dedupe_preserve_order(self, lines: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for line in lines:
            key = line.strip()
            if not key:
                if result and result[-1].strip() == "":
                    continue
                result.append("")
                continue
            if key in seen:
                continue
            seen.add(key)
            result.append(line)
        while result and result[-1].strip() == "":
            result.pop()
        return result

    def _sanitize_robot_output(self, content: str, context: str | None = None) -> str:
        """Remove qualquer texto fora das seções Robot e normaliza libs."""
        lines = [line.rstrip() for line in content.splitlines()]
        # Keep only from first valid section
        valid_headers = (
            "*** Settings ***",
            "*** Variables ***",
            "*** Test Cases ***",
            "*** Keywords ***",
            "*** Comments ***",
            "*** Tasks ***",
        )
        start_idx = 0
        for i, line in enumerate(lines):
            if line.strip() in valid_headers:
                start_idx = i
                break
        cleaned = lines[start_idx:]

        # Drop any leftover non-section note lines
        filtered = []
        for line in cleaned:
            stripped = line.strip()
            # LLM sometimes wraps output in markdown code fences (```robot ... ```),
            # which Robot interprets as extra/empty test names.
            if stripped.startswith("```"):
                continue
            if stripped.startswith("**") and not stripped.startswith("***"):
                continue
            if line.strip().lower().startswith("observação"):
                continue
            filtered.append(line)
        cleaned = filtered

        # Replace invalid libraries
        cleaned = [
            l.replace("PlaywrightLibrary", "Browser").replace("Playwright", "Browser")
            for l in cleaned
        ]
        cleaned = [
            l.replace("Library    SeleniumLibrary", "Library    Browser")
            for l in cleaned
        ]

        cleaned = self._harden_robot_lines(cleaned, context=context)

        result = "\n".join(cleaned).strip() + "\n"
        return self._fix_robot_syntax_errors(result)

    # ------------------------------------------------------------------
    # Syntax error fixing — runs AFTER _harden_robot_lines
    # ------------------------------------------------------------------

    def _fix_robot_syntax_errors(self, content: str) -> str:
        """
        Deterministic post-processing that catches three classes of LLM errors:

        1. Wrong built-in variable names  (${OUTPUT} → ${OUTPUT_DIR}, etc.)
        2. Assertion keywords with fewer than 2 positional args
           (e.g. ``Should Be Equal    ${title}`` missing the expected value)
        3. Keyword definitions that have no executable steps
           (only metadata lines like [Documentation]) → inject ``No Operation``
        """
        # Fix 1 — variable name corrections
        for wrong, correct in _ROBOT_VAR_CORRECTIONS.items():
            content = content.replace(wrong, correct)

        # Fix 2 — drop assertion calls with too few arguments
        lines: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("***"):
                lines.append(line)
                continue
            parts = re.split(r"  +", stripped)
            kw = parts[0]
            args = parts[1:]
            # Handle variable assignment prefix: ${var}=    Keyword    arg
            if re.match(r"^\$\{[^}]+\}=?$", kw) and len(parts) > 1:
                kw = parts[1]
                args = parts[2:]
            if kw in _ASSERTIONS_MIN_2_ARGS and len(args) < 2:
                logger.debug("Removed assertion with too few args: %s", stripped)
                continue
            lines.append(line)
        content = "\n".join(lines)

        # Fix 3 — empty keyword bodies
        return self._fix_empty_keywords(content)

    def _fix_empty_keywords(self, content: str) -> str:
        """Inject ``No Operation`` into keyword definitions that have no executable steps."""
        kw_match = re.search(
            r"(\*\*\* Keywords \*\*\*[ \t]*\n)(.*?)(\Z|(?=\n\*\*\*))",
            content,
            re.DOTALL,
        )
        if not kw_match:
            return content
        prefix = content[: kw_match.start(2)]
        body = kw_match.group(2)
        suffix = content[kw_match.end(2) :]
        return prefix + self._patch_keyword_bodies(body) + suffix

    def _patch_keyword_bodies(self, body: str) -> str:
        """Ensure each keyword block in a *** Keywords *** section has executable steps."""
        # Split at lines that start at column 0 (= keyword name lines)
        blocks = re.split(r"(?m)(?=^[^\s\n])", body)
        patched: list[str] = []
        for block in blocks:
            if not block.strip():
                patched.append(block)
                continue
            block_lines = block.splitlines(keepends=True)
            step_lines = block_lines[1:]  # everything after the keyword name
            has_executable = any(
                ln.strip()
                and not ln.strip().lower().startswith(tuple(_KW_METADATA_TAGS))
                for ln in step_lines
            )
            if not has_executable:
                indent = "    "
                for ln in step_lines:
                    if ln.strip():
                        indent = ln[: len(ln) - len(ln.lstrip())]
                        break
                # Append No Operation as the only real step
                patched.append("".join(block_lines) + f"{indent}No Operation\n")
            else:
                patched.append(block)
        return "".join(patched)

    def _harden_robot_lines(
        self, lines: list[str], context: str | None = None
    ) -> list[str]:
        strict_selectors = self._extract_strict_mode_selectors(context)
        selector_keywords = {
            "Click",
            "Click Element",
            "Wait For Elements State",
            "Wait Until Element Is Visible",
            "Wait Until Page Contains Element",
            "Get Element",
            "Get Elements",
            "Input Text",
            "Fill Text",
            "Type Text",
        }

        hardened: list[str] = []
        has_context_timeout = False
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("***"):
                hardened.append(line)
                continue

            indent = line[: len(line) - len(line.lstrip())]
            parts = re.split(r"\s{2,}", stripped)
            keyword = parts[0] if parts else ""

            keyword_aliases = {
                "Click Element": "Click",
                "Input Text": "Fill Text",
                "Type Text": "Fill Text",
            }
            if keyword in keyword_aliases:
                keyword = keyword_aliases[keyword]
                parts[0] = keyword

            if keyword == "Maximize Browser Window":
                # Browser library does not need this Selenium keyword and it often
                # causes execution errors when LLM mixes libraries.
                continue

            if keyword == "Wait Until Element Is Visible" and len(parts) >= 2:
                timeout_value = self._extract_timeout_value(parts[2:], default="10s")
                parts = ["Wait For Elements State", parts[1], "visible", timeout_value]
                keyword = parts[0]

            if keyword == "Wait Until Page Contains Element" and len(parts) >= 2:
                timeout_value = self._extract_timeout_value(parts[2:], default="10s")
                parts = ["Wait For Elements State", parts[1], "visible", timeout_value]
                keyword = parts[0]

            if keyword == "Wait Until Location Contains" and len(parts) >= 2:
                timeout_value = self._extract_timeout_value(parts[2:], default="10s")
                target_fragment = parts[1]
                hardened.append(
                    f"{indent}Wait For URL    **{target_fragment}*    timeout={timeout_value}"
                )
                continue

            if keyword == "Wait Until Page Contains" and len(parts) >= 2:
                timeout_value = self._extract_timeout_value(parts[2:], default="10s")
                expected_text = parts[1]
                hardened.append(
                    f"{indent}Wait For Elements State    text={expected_text}    visible    {timeout_value}"
                )
                continue

            if keyword == "Location Should Contain" and len(parts) >= 2:
                target_fragment = parts[1]
                hardened.append(f"{indent}${{__aw_current_url}}    Get Url")
                hardened.append(f"{indent}Should Contain    ${{__aw_current_url}}    {target_fragment}")
                continue

            if keyword == "Page Should Contain" and len(parts) >= 2:
                expected_text = parts[1]
                hardened.append(f"{indent}${{__aw_page_text}}    Get Text    css=body")
                hardened.append(f"{indent}Should Contain    ${{__aw_page_text}}    {expected_text}")
                continue

            if keyword == "Open Browser" and len(parts) >= 2:
                page_url = parts[1]
                hardened.append(
                    f"{indent}New Browser    chromium    headless=${{HEADLESS}}"
                )
                hardened.append(f"{indent}New Context")
                hardened.append(f"{indent}Set Browser Timeout    30s")
                hardened.append(f"{indent}New Page    {page_url}")
                continue

            if keyword == "New Context":
                hardened.append(line)
                # Inject a global 30s timeout right after New Context so every
                # Wait / interaction uses 30s by default instead of the 10s default.
                hardened.append(f"{indent}Set Browser Timeout    30s")
                has_context_timeout = True
                continue

            if keyword == "New Page" and not has_context_timeout:
                # Some generated tests use Suite Setup with only New Browser and then
                # call New Page in test cases. In this shape Browser library falls back
                # to its 10s default and page.goto can fail on slower sites.
                hardened.append(f"{indent}New Context")
                hardened.append(f"{indent}Set Browser Timeout    30s")
                hardened.append(line)
                has_context_timeout = True
                continue

            if keyword in selector_keywords and len(parts) >= 2:
                selector = self._normalize_selector(parts[1])

                # Class-only selectors often match many elements and break strict mode.
                if self._is_class_only_css_selector(selector):
                    selector = self._make_selector_unique(selector)

                # IDs are expected to be unique, but many modern apps duplicate
                # generic IDs (e.g. #button, #logo, #icon), which breaks Browser
                # Library strict mode. Harden those deterministic high-risk IDs.
                if self._is_potentially_ambiguous_id_selector(selector):
                    selector = self._make_selector_unique(selector)

                if (
                    selector in strict_selectors
                    or selector.replace("css=", "") in strict_selectors
                ):
                    selector = self._make_selector_unique(selector)

                parts[1] = selector
                hardened.append(f"{indent}{'    '.join(parts)}")
                continue

            hardened.append(line)

        # Pass 2: remove Wait For Elements State lines that are immediately
        # before a Get Title call – those waits are logically wrong because
        # Get Title reads document.title from <head>, not from a visible element.
        hardened = self._fix_title_check_waits(hardened)
        return hardened

    def _extract_timeout_value(self, args: list[str], default: str = "10s") -> str:
        for arg in args:
            if arg.startswith("timeout="):
                value = arg.split("=", 1)[1].strip()
                return value or default
        for arg in args:
            token = arg.strip()
            if token:
                return token
        return default

    def _fix_title_check_waits(self, lines: list[str]) -> list[str]:
        """Remove Wait For Elements State that appear just before Get Title."""
        result: list[str] = []
        skip_next_blank = False
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            parts = re.split(r"\s{2,}", stripped)
            keyword = parts[0] if parts else ""

            if keyword == "Wait For Elements State":
                # Look ahead (skip blanks) to find the next real keyword line
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    next_stripped = lines[j].strip()
                    # Matches both "Get Title" and "${var}    Get Title"
                    if "Get Title" in next_stripped or "Get Url" in next_stripped:
                        # Drop this Wait – it is unnecessary and often wrong
                        i += 1
                        continue

            result.append(lines[i])
            i += 1
        return result

    def _extract_strict_mode_selectors(self, context: str | None) -> set[str]:
        if not context:
            return set()
        selectors = set(re.findall(r"locator\('([^']+)'\)", context))

        # Visual Builder context format:
        # - step=1 | action=click | selector=#login
        for raw_selector in re.findall(r"(?:\||\s)selector=([^|\n]+)", context):
            cleaned = raw_selector.strip()
            if cleaned and cleaned != "N/A":
                selectors.add(cleaned)

        return selectors

    def _normalize_selector(self, selector: str) -> str:
        if selector.startswith("id:"):
            return f"css=#{selector[3:]}"
        if selector.startswith("css:"):
            return f"css={selector[4:]}"
        if selector.startswith("xpath:"):
            selector = f"xpath={selector[6:]}"
            return self._relativize_xpath(selector)
        if selector.startswith("#"):
            return f"css={selector}"
        if selector.startswith("["):
            return f"css={selector}"
        if selector.startswith("/") or selector.startswith("("):
            selector = f"xpath={selector}"
            return self._relativize_xpath(selector)
        if selector.startswith("xpath="):
            return self._relativize_xpath(selector)
        if selector.startswith("."):
            return f"css={selector}"
        if re.match(r"^[a-zA-Z][\w-]*(?:[\[\.:#].*)?$", selector):
            return f"css={selector}"
        return selector

    # ------------------------------------------------------------------
    # XPath helpers
    # ------------------------------------------------------------------

    # Matches rooted absolute xpaths like /html/... or /html[1]/...
    _ABS_XPATH_RE = re.compile(r"^xpath=/html(?:\[\d+\])?/", re.IGNORECASE)

    def _relativize_xpath(self, selector: str) -> str:
        """Convert an absolute xpath (xpath=/html/body/...) to a relative one (xpath=//...).

        Absolute xpaths generated by LLMs are extremely brittle: the path
        breaks whenever the page adds or removes a wrapper element.  A
        double-slash prefix keeps the semantic intent while tolerating normal
        DOM variation.

        Examples::

            xpath=/html/body/div[2]/div/h3  →  xpath=//div[2]/div/h3
            xpath=/html[1]/body[1]/a[3]     →  xpath=//a[3]
        """
        if not self._ABS_XPATH_RE.match(selector):
            return selector

        # Strip the xpath= prefix and the leading /html.../body... segments
        path = selector[len("xpath="):]
        # Remove leading /html[N] and /body[N] segments to get a relative path
        # that starts from the first "meaningful" element inside <body>
        path = re.sub(r"^/html(?:\[\d+\])?/body(?:\[\d+\])?/?", "", path, flags=re.IGNORECASE)
        if not path:
            # degenerate case — just points at body itself
            return "css=body"
        relative = f"xpath=//{path}"
        logger.debug("Relativized absolute xpath: %s → %s", selector, relative)
        return relative

    def _is_class_only_css_selector(self, selector: str) -> bool:
        if not selector.startswith("css=."):
            return False
        body = selector[4:]
        return all(token not in body for token in (" ", ">", "+", "~", "[", ":", ">>"))

    def _is_potentially_ambiguous_id_selector(self, selector: str) -> bool:
        if not selector.startswith("css=#"):
            return False

        body = selector[5:]
        # Compound selector (e.g. #container .btn) is not a plain ID hit.
        if any(token in body for token in (" ", ">", "+", "~", "[", ":", ".", ">>")):
            return False

        normalized = body.strip().lower()
        if not normalized:
            return False

        generic_ids = {
            "button",
            "btn",
            "icon",
            "logo",
            "link",
            "item",
            "card",
            "menu",
            "tab",
            "title",
            "label",
            "input",
            "field",
            "container",
            "content",
            "main",
            "root",
            "app",
            "header",
            "footer",
            "nav",
            "search",
            "dialog",
            "modal",
        }

        if normalized in generic_ids:
            return True

        # Very short ids are frequently reused (#x, #el, #btn1 etc.).
        return len(normalized) <= 4

    def _make_selector_unique(self, selector: str) -> str:
        if selector.endswith(" >> nth=0"):
            return selector
        if selector.startswith("css="):
            return f"{selector} >> nth=0"
        if (
            selector.startswith("#")
            or selector.startswith("[")
            or re.match(r"^[a-zA-Z][\w-]*(?:[\[\.:#].*)?$", selector)
        ):
            return f"css={selector} >> nth=0"
        return selector
