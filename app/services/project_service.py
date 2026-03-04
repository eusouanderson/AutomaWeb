import logging
import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository

logger = logging.getLogger(__name__)


class ProjectService:
    """Project business rules."""

    def __init__(self, repository: ProjectRepository | None = None) -> None:
        self._repository = repository or ProjectRepository()

    async def create_project(
        self,
        session: AsyncSession,
        name: str,
        description: str | None = None,
        url: str | None = None,
        test_directory: str | None = None,
    ) -> Project:
        project = Project(name=name, description=description, url=url, test_directory=test_directory)
        return await self._repository.create(session, project)

    async def list_projects(self, session: AsyncSession) -> list[Project]:
        return await self._repository.list(session)

    async def get_project(self, session: AsyncSession, project_id: int) -> Project | None:
        return await self._repository.get(session, project_id)

    async def delete_project(self, session: AsyncSession, project_id: int) -> bool:
        project = await self._repository.get(session, project_id)
        if not project:
            return False

        deleted = await self._repository.delete(session, project_id)
        if not deleted:
            return False

        self._cleanup_project_directories(project)
        self._cleanup_project_reports(project_id)
        return True

    def _cleanup_project_directories(self, project: Project) -> None:
        base_dir = Path(project.test_directory) if project.test_directory else Path(settings.STATIC_DIR) / "projects"
        project_dir = base_dir / self._safe_dir_name(project.name)

        if project_dir.exists():
            try:
                shutil.rmtree(project_dir)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to remove project directory %s: %s", project_dir, exc)

    def _cleanup_project_reports(self, project_id: int) -> None:
        reports_root = Path(settings.STATIC_DIR) / "reports"
        if not reports_root.exists():
            return

        for report_dir in reports_root.glob(f"{project_id}_*"):
            if report_dir.is_dir():
                try:
                    shutil.rmtree(report_dir)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to remove project report directory %s: %s", report_dir, exc)

    def _safe_dir_name(self, name: str) -> str:
        safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", " ")).strip().replace(" ", "_") or "project"
        return f"🧪_{safe}"
