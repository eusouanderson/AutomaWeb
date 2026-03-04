import logging
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.groq_client import GroqClient
from app.models.generated_test import GeneratedTest
from app.models.test_request import TestRequest
from app.repositories.project_repository import ProjectRepository
from app.repositories.test_repository import TestRepository

logger = logging.getLogger(__name__)


class TestService:
    """Test generation business rules."""

    def __init__(
        self,
        test_repository: TestRepository | None = None,
        project_repository: ProjectRepository | None = None,
        groq_client: GroqClient | None = None,
    ) -> None:
        self._test_repository = test_repository or TestRepository()
        self._project_repository = project_repository or ProjectRepository()
        self._groq_client = groq_client or GroqClient()

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

        content = self._groq_client.generate_robot_test(prompt=prompt, context=context)
        content = self._sanitize_robot_output(content)
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

    def _sanitize_robot_output(self, content: str) -> str:
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
            if line.strip().startswith("**"):
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

        return "\n".join(cleaned).strip() + "\n"
