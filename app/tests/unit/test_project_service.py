import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.project import Project
from app.services.project_service import ProjectService


@pytest_asyncio.fixture()
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session


async def test_create_project(session: AsyncSession) -> None:
    service = ProjectService()
    project = await service.create_project(session, name="My Project", description="Description")
    
    assert project.id is not None
    assert project.name == "My Project"
    assert project.description == "Description"


async def test_list_projects(session: AsyncSession) -> None:
    service = ProjectService()
    await service.create_project(session, name="Project 1")
    await service.create_project(session, name="Project 2")
    
    projects = await service.list_projects(session)
    assert len(projects) == 2


async def test_get_project(session: AsyncSession) -> None:
    service = ProjectService()
    created = await service.create_project(session, name="Get Project")
    
    found = await service.get_project(session, created.id)
    assert found is not None
    assert found.id == created.id


async def test_get_nonexistent_project(session: AsyncSession) -> None:
    service = ProjectService()
    found = await service.get_project(session, 9999)
    assert found is None
