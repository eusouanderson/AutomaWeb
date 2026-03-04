from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.repositories.project_repository import ProjectRepository


class ProjectService:
    """Project business rules."""

    def __init__(self, repository: ProjectRepository | None = None) -> None:
        self._repository = repository or ProjectRepository()

    async def create_project(self, session: AsyncSession, name: str, description: str | None = None) -> Project:
        project = Project(name=name, description=description)
        return await self._repository.create(session, project)

    async def list_projects(self, session: AsyncSession) -> list[Project]:
        return await self._repository.list(session)

    async def get_project(self, session: AsyncSession, project_id: int) -> Project | None:
        return await self._repository.get(session, project_id)
