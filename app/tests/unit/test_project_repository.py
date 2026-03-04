import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository


@pytest_asyncio.fixture()
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session


async def test_create_project(session: AsyncSession) -> None:
    repo = ProjectRepository()
    project = Project(name="Test Project", description="Test Description")
    created = await repo.create(session, project)
    assert created.id is not None
    assert created.name == "Test Project"
    assert created.description == "Test Description"


async def test_list_projects(session: AsyncSession) -> None:
    repo = ProjectRepository()
    project1 = Project(name="Project 1", description="Desc 1")
    project2 = Project(name="Project 2", description="Desc 2")
    await repo.create(session, project1)
    await repo.create(session, project2)
    
    projects = await repo.list(session)
    assert len(projects) == 2


async def test_get_project(session: AsyncSession) -> None:
    repo = ProjectRepository()
    project = Project(name="Get Test", description="Desc")
    created = await repo.create(session, project)
    
    found = await repo.get(session, created.id)
    assert found is not None
    assert found.id == created.id
    assert found.name == "Get Test"


async def test_get_nonexistent_project(session: AsyncSession) -> None:
    repo = ProjectRepository()
    found = await repo.get(session, 9999)
    assert found is None
