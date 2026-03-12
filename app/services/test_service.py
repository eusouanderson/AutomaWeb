import json
import logging
import os
import re
import asyncio
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import RetryError

from app.ai_validation.self_healing_service import AITestSelfHealingService
from app.core.config import settings
from app.llm.groq_client import GroqClient
from app.models.generated_test import GeneratedTest
from app.models.test_request import TestRequest
from app.repositories.project_repository import ProjectRepository
from app.repositories.test_repository import TestRepository
from app.services.element_scanner import ElementScannerError, ElementScannerService

logger = logging.getLogger(__name__)


class LLMServiceUnavailableError(Exception):
    """Raised when LLM provider is unavailable."""


class ScanUnavailableError(Exception):
    """Raised when element scan fails during test generation."""


class TestService:
    """Test generation business rules."""

    def __init__(
        self,
        test_repository: TestRepository | None = None,
        project_repository: ProjectRepository | None = None,
        groq_client: GroqClient | None = None,
        element_scanner: ElementScannerService | None = None,
    ) -> None:
        self._test_repository = test_repository or TestRepository()
        self._project_repository = project_repository or ProjectRepository()
        self._groq_client = groq_client or GroqClient()
        self._element_scanner = element_scanner or ElementScannerService()
        self._self_healing = AITestSelfHealingService()

    async def generate_test(
        self,
        session: AsyncSession,
        project_id: int,
        prompt: str,
        context: str | None = None,
        ai_debug: bool = False,
    ) -> GeneratedTest:
        project = await self._project_repository.get(session, project_id)
        if not project:
            raise ValueError("Project not found")

        test_request = TestRequest(project_id=project_id, prompt=prompt, context=context, status="processing")
        test_request = await self._test_repository.create_test_request(session, test_request)

        page_structure: dict | None = None
        if project.url:
            try:
                scan_result = await self._element_scanner.scan_url(str(project.url))
            except ElementScannerError as exc:
                test_request.status = "failed"
                await self._test_repository.update_test_request(session, test_request)
                logger.error("Failed to scan project URL before generating test: %s", exc)
                raise ScanUnavailableError(str(exc)) from exc
            page_structure = scan_result.model_dump()
            # Persist scan in project cache
            project.scan_cache = json.dumps(page_structure, ensure_ascii=False)
            project.scan_cached_at = datetime.utcnow()
            await session.flush()

        try:
            content = await asyncio.to_thread(
                self._groq_client.generate_robot_test,
                prompt=prompt,
                context=context,
                page_structure=page_structure,
            )
        except RetryError as exc:
            test_request.status = "failed"
            await self._test_repository.update_test_request(session, test_request)
            logger.error("Failed to generate test: LLM connection retries exhausted")
            raise LLMServiceUnavailableError("LLM provider connection failed") from exc
        except Exception as exc:
            error_name = exc.__class__.__name__
            if "APIConnectionError" in error_name or "APITimeoutError" in error_name:
                test_request.status = "failed"
                await self._test_repository.update_test_request(session, test_request)
                logger.error("Failed to generate test due to LLM connectivity issue: %s", error_name)
                raise LLMServiceUnavailableError("LLM provider connection failed") from exc
            raise

        content = self._sanitize_robot_output(content, context=context)

        if settings.AI_VALIDATION_ENABLED:
            healed = await self._self_healing.heal_test(
                content=content,
                page_url=str(project.url) if project.url else None,
                prompt=prompt,
                context=context,
                groq_client=self._groq_client,
                ai_debug=ai_debug,
            )
            content = healed.final_content

        test_request.status = "completed"
        await self._test_repository.update_test_request(session, test_request)

        file_path = self._write_robot_file(test_request.id, content, project.name, project.test_directory)
        generated_test = GeneratedTest(
            test_request_id=test_request.id,
            content=content,
            file_path=str(file_path),
        )
        return await self._test_repository.create_generated_test(session, generated_test)


    async def get_generated_test(self, session: AsyncSession, test_id: int) -> GeneratedTest | None:
        return await self._test_repository.get_generated_test(session, test_id)

    async def list_generated_tests_by_project(self, session: AsyncSession, project_id: int) -> list[GeneratedTest]:
        project = await self._project_repository.get(session, project_id)
        if not project:
            raise ValueError("Project not found")
        return await self._test_repository.list_generated_tests_by_project(session, project_id)

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

    async def improve_robot_test(self, session: AsyncSession, test_id: int, content: str) -> str | None:
        """Send Robot Framework content to the AI (with page scan context) and return improved version."""
        generated = await self._test_repository.get_generated_test(session, test_id)
        if not generated:
            return None

        # Resolve project to get scan context
        test_request = await self._test_repository.get_test_request(session, generated.test_request_id)
        project = await self._project_repository.get(session, test_request.project_id) if test_request else None

        page_structure: dict | None = None
        if project and project.url:
            page_structure = await self._get_or_refresh_scan(session, project)

        improvement_prompt = (
            "Melhore o teste Robot Framework abaixo. "
            "Preserve a estrutura das seções (*** Settings ***, *** Variables ***, *** Test Cases ***, *** Keywords ***). "
            "Corrija problemas de sintaxe, melhore a legibilidade, otimize keywords, "
            "adicione waits onde necessário e sugira uma estrutura de teste melhor. "
            "Retorne APENAS código Robot Framework válido, sem explicações ou markdown.\n\n"
            f"{content}"
        )
        try:
            improved = await asyncio.to_thread(
                self._groq_client.generate_robot_test,
                prompt=improvement_prompt,
                context=None,
                page_structure=page_structure,
            )
        except Exception as exc:
            error_name = exc.__class__.__name__
            if "APIConnectionError" in error_name or "APITimeoutError" in error_name or "RetryError" in error_name:
                raise LLMServiceUnavailableError("LLM provider connection failed") from exc
            raise
        return self._sanitize_robot_output(improved)

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
        sanitized = self._sanitize_robot_output(content)
        file_path = Path(generated.file_path)
        file_path.write_text(sanitized, encoding="utf-8")
        generated.content = sanitized
        await session.flush()
        return generated

    def _write_robot_file(
        self,
        test_request_id: int,
        content: str,
        project_name: str,
        test_directory: str | None = None,
    ) -> Path:
        base_dir = Path(test_directory) if test_directory else Path(settings.STATIC_DIR) / "projects"
        safe_name = self._safe_dir_name(project_name)
        project_dir = base_dir / safe_name
        os.makedirs(project_dir, exist_ok=True)
        file_path = project_dir / f"generated_test_{test_request_id}.robot"
        file_path.write_text(content, encoding="utf-8")
        logger.info("Robot test saved at %s", file_path)
        return file_path

    def _safe_dir_name(self, name: str) -> str:
        safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", " ")).strip().replace(" ", "_") or "project"
        return f"🧪_{safe}"

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

        cleaned = self._harden_robot_lines(cleaned, context=context)

        return "\n".join(cleaned).strip() + "\n"

    def _harden_robot_lines(self, lines: list[str], context: str | None = None) -> list[str]:
        strict_selectors = self._extract_strict_mode_selectors(context)
        selector_keywords = {
            "Click",
            "Wait For Elements State",
            "Get Element",
            "Get Elements",
            "Input Text",
            "Fill Text",
            "Type Text",
        }

        hardened: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("***"):
                hardened.append(line)
                continue

            indent = line[: len(line) - len(line.lstrip())]
            parts = re.split(r"\s{2,}", stripped)
            keyword = parts[0] if parts else ""

            if keyword == "Open Browser" and len(parts) >= 2:
                page_url = parts[1]
                hardened.append(f"{indent}New Browser    chromium    headless=${{HEADLESS}}")
                hardened.append(f"{indent}New Context")
                hardened.append(f"{indent}Set Browser Timeout    30s")
                hardened.append(f"{indent}New Page    {page_url}")
                continue

            if keyword == "New Context":
                hardened.append(line)
                # Inject a global 30s timeout right after New Context so every
                # Wait / interaction uses 30s by default instead of the 10s default.
                hardened.append(f"{indent}Set Browser Timeout    30s")
                continue

            if keyword in selector_keywords and len(parts) >= 2:
                selector = self._normalize_selector(parts[1])

                # Class-only selectors often match many elements and break strict mode.
                if self._is_class_only_css_selector(selector):
                    selector = self._make_selector_unique(selector)

                if selector in strict_selectors or selector.replace("css=", "") in strict_selectors:
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
        return set(re.findall(r"locator\('([^']+)'\)", context))

    def _normalize_selector(self, selector: str) -> str:
        if selector.startswith("id:"):
            return f"css=#{selector[3:]}"
        if selector.startswith("css:"):
            return f"css={selector[4:]}"
        if selector.startswith("xpath:"):
            return f"xpath={selector[6:]}"
        if selector.startswith("#"):
            return f"css={selector}"
        if selector.startswith("["):
            return f"css={selector}"
        if selector.startswith("/") or selector.startswith("("):
            return f"xpath={selector}"
        if selector.startswith("."):
            return f"css={selector}"
        if re.match(r"^[a-zA-Z][\w-]*(?:[\[\.:#].*)?$", selector):
            return f"css={selector}"
        return selector

    def _is_class_only_css_selector(self, selector: str) -> bool:
        if not selector.startswith("css=."):
            return False
        body = selector[4:]
        return all(token not in body for token in (" ", ">", "+", "~", "[", ":", ">>"))

    def _make_selector_unique(self, selector: str) -> str:
        if selector.endswith(" >> nth=0"):
            return selector
        if selector.startswith("css="):
            return f"{selector} >> nth=0"
        if selector.startswith("#") or selector.startswith("[") or re.match(
            r"^[a-zA-Z][\w-]*(?:[\[\.:#].*)?$", selector
        ):
            return f"css={selector} >> nth=0"
        return selector
