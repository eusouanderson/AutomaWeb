import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.generated_test import GeneratedTest
from app.models.project import Project
from app.models.test_request import TestRequest
from app.repositories.test_repository import TestRepository


@pytest_asyncio.fixture()
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session


async def test_create_test_request(session: AsyncSession) -> None:
    project = Project(name="Test Project")
    session.add(project)
    await session.commit()
    await session.refresh(project)
    
    repo = TestRepository()
    test_request = TestRequest(project_id=project.id, prompt="Test prompt", status="pending")
    created = await repo.create_test_request(session, test_request)
    
    assert created.id is not None
    assert created.prompt == "Test prompt"
    assert created.status == "pending"


async def test_update_test_request(session: AsyncSession) -> None:
    project = Project(name="Test Project")
    session.add(project)
    await session.commit()
    await session.refresh(project)
    
    repo = TestRepository()
    test_request = TestRequest(project_id=project.id, prompt="Test", status="pending")
    created = await repo.create_test_request(session, test_request)
    
    created.status = "completed"
    updated = await repo.update_test_request(session, created)
    assert updated.status == "completed"


async def test_create_generated_test(session: AsyncSession) -> None:
    project = Project(name="Test Project")
    session.add(project)
    await session.commit()
    await session.refresh(project)
    
    test_request = TestRequest(project_id=project.id, prompt="Test")
    session.add(test_request)
    await session.commit()
    await session.refresh(test_request)
    
    repo = TestRepository()
    generated = GeneratedTest(
        test_request_id=test_request.id,
        content="*** Test Cases ***",
        file_path="/tmp/test.robot"
    )
    created = await repo.create_generated_test(session, generated)
    
    assert created.id is not None
    assert created.content == "*** Test Cases ***"


async def test_get_generated_test(session: AsyncSession) -> None:
    project = Project(name="Test Project")
    session.add(project)
    await session.commit()
    await session.refresh(project)
    
    test_request = TestRequest(project_id=project.id, prompt="Test")
    session.add(test_request)
    await session.commit()
    await session.refresh(test_request)
    
    repo = TestRepository()
    generated = GeneratedTest(
        test_request_id=test_request.id,
        content="*** Test Cases ***",
        file_path="/tmp/test.robot"
    )
    created = await repo.create_generated_test(session, generated)
    
    found = await repo.get_generated_test(session, created.id)
    assert found is not None
    assert found.id == created.id


async def test_get_nonexistent_generated_test(session: AsyncSession) -> None:
    repo = TestRepository()
    found = await repo.get_generated_test(session, 9999)
    assert found is None
