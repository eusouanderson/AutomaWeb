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
        test_request.status = "completed"
        await self._test_repository.update_test_request(session, test_request)

        file_path = self._write_robot_file(test_request.id, content)
        generated_test = GeneratedTest(
            test_request_id=test_request.id,
            content=content,
            file_path=str(file_path),
        )
        return await self._test_repository.create_generated_test(session, generated_test)

    async def get_generated_test(self, session: AsyncSession, test_id: int) -> GeneratedTest | None:
        return await self._test_repository.get_generated_test(session, test_id)

    def _write_robot_file(self, test_request_id: int, content: str) -> Path:
        static_dir = Path(settings.STATIC_DIR)
        os.makedirs(static_dir, exist_ok=True)
        file_path = static_dir / f"generated_test_{test_request_id}.robot"
        file_path.write_text(content, encoding="utf-8")
        logger.info("Robot test saved at %s", file_path)
        return file_path
