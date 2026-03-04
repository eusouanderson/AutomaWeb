from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


class ProjectRepository:
    """Project data access layer."""

    async def create(self, session: AsyncSession, project: Project) -> Project:
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project

    async def list(self, session: AsyncSession) -> list[Project]:
        result = await session.execute(select(Project))
        return list(result.scalars().all())

    async def get(self, session: AsyncSession, project_id: int) -> Project | None:
        result = await session.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()
