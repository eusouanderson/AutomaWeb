import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository


@pytest_asyncio.fixture()
async def session() -> AsyncSession: # type: ignore[arg-type]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_delete_project_found(session: AsyncSession) -> None:
    repo = ProjectRepository()
    project = Project(name="Projeto", description="Desc", test_directory="/tmp")
    session.add(project)
    await session.commit()
    await session.refresh(project)

    deleted = await repo.delete(session, project.id)
    assert deleted is True

    fetched = await repo.get(session, project.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_project_not_found(session: AsyncSession) -> None:
    repo = ProjectRepository()
    deleted = await repo.delete(session, 999)
    assert deleted is False
