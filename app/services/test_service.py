import logging
import os
import re
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import RetryError

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

    async def generate_test(
        self,
        session: AsyncSession,
        project_id: int,
        prompt: str,
        context: str | None = None,
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

        try:
            content = self._groq_client.generate_robot_test(
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
                hardened.append(f"{indent}New Browser    chromium")
                hardened.append(f"{indent}New Context")
                hardened.append(f"{indent}New Page    {page_url}")
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

        return hardened

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
        if selector.startswith("."):
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
        return selector
