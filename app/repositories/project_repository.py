from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Sequence

from app.models.generated_test import GeneratedTest
from app.models.project import Project
from app.models.test_request import TestRequest


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

    async def list_with_test_count(
        self, session: AsyncSession
    ) -> Sequence[tuple[Project, int]]:
        result = await session.execute(
            select(Project, func.count(GeneratedTest.id).label("test_count"))
            .outerjoin(TestRequest, TestRequest.project_id == Project.id)
            .outerjoin(GeneratedTest, GeneratedTest.test_request_id == TestRequest.id)
            .group_by(Project.id)
        )
        return [(project, int(test_count or 0)) for project, test_count in result.all()]

    async def get(self, session: AsyncSession, project_id: int) -> Project | None:
        result = await session.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()

    async def delete(self, session: AsyncSession, project_id: int) -> bool:
        project = await self.get(session, project_id)
        if not project:
            return False
        await session.delete(project)
        await session.commit()
        return True
