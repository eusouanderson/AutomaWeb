import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.generated_test import GeneratedTest
from app.models.project import Project
from app.models.test_request import TestRequest
from app.repositories.test_repository import TestRepository


@pytest_asyncio.fixture()
async def session() -> AsyncSession:  # type: ignore[arg-type]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session  # type: ignore[arg-type]


async def test_create_test_request(session: AsyncSession) -> None:
    project = Project(name="Test Project")
    session.add(project)
    await session.commit()
    await session.refresh(project)

    repo = TestRepository()
    test_request = TestRequest(
        project_id=project.id, prompt="Test prompt", status="pending"
    )
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
        file_path="/tmp/test.robot",
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
        file_path="/tmp/test.robot",
    )
    created = await repo.create_generated_test(session, generated)

    found = await repo.get_generated_test(session, created.id)
    assert found is not None
    assert found.id == created.id


async def test_get_nonexistent_generated_test(session: AsyncSession) -> None:
    repo = TestRepository()
    found = await repo.get_generated_test(session, 9999)
    assert found is None


async def test_delete_generated_test(session: AsyncSession) -> None:
    project = Project(name="Projeto Delete")
    session.add(project)
    await session.commit()
    await session.refresh(project)

    test_request = TestRequest(project_id=project.id, prompt="Delete me")
    session.add(test_request)
    await session.commit()
    await session.refresh(test_request)

    repo = TestRepository()
    generated = GeneratedTest(
        test_request_id=test_request.id,
        content="*** Test Cases ***",
        file_path="/tmp/delete.robot",
    )
    created = await repo.create_generated_test(session, generated)

    await repo.delete_generated_test(session, created)

    found = await repo.get_generated_test(session, created.id)
    assert found is None


async def test_list_generated_tests_by_project(session: AsyncSession) -> None:
    project_a = Project(name="Projeto A")
    project_b = Project(name="Projeto B")
    session.add_all([project_a, project_b])
    await session.commit()
    await session.refresh(project_a)
    await session.refresh(project_b)

    req_a = TestRequest(project_id=project_a.id, prompt="A")
    req_b = TestRequest(project_id=project_b.id, prompt="B")
    session.add_all([req_a, req_b])
    await session.commit()
    await session.refresh(req_a)
    await session.refresh(req_b)

    session.add_all(
        [
            GeneratedTest(
                test_request_id=req_a.id, content="A1", file_path="/tmp/a1.robot"
            ),
            GeneratedTest(
                test_request_id=req_a.id, content="A2", file_path="/tmp/a2.robot"
            ),
            GeneratedTest(
                test_request_id=req_b.id, content="B1", file_path="/tmp/b1.robot"
            ),
        ]
    )
    await session.commit()

    repo = TestRepository()
    tests = await repo.list_generated_tests_by_project(session, project_a.id)

    assert len(tests) == 2
    assert {test.content for test in tests} == {"A1", "A2"}


async def test_list_generated_tests_by_ids_for_project_filters_ids(
    session: AsyncSession,
) -> None:
    project_a = Project(name="Projeto A")
    project_b = Project(name="Projeto B")
    session.add_all([project_a, project_b])
    await session.commit()
    await session.refresh(project_a)
    await session.refresh(project_b)

    req_a = TestRequest(project_id=project_a.id, prompt="A")
    req_b = TestRequest(project_id=project_b.id, prompt="B")
    session.add_all([req_a, req_b])
    await session.commit()
    await session.refresh(req_a)
    await session.refresh(req_b)

    test_a1 = GeneratedTest(
        test_request_id=req_a.id, content="A1", file_path="/tmp/a1.robot"
    )
    test_a2 = GeneratedTest(
        test_request_id=req_a.id, content="A2", file_path="/tmp/a2.robot"
    )
    test_b1 = GeneratedTest(
        test_request_id=req_b.id, content="B1", file_path="/tmp/b1.robot"
    )
    session.add_all([test_a1, test_a2, test_b1])
    await session.commit()
    await session.refresh(test_a1)
    await session.refresh(test_a2)
    await session.refresh(test_b1)

    repo = TestRepository()
    selected = await repo.list_generated_tests_by_ids_for_project(
        session, project_a.id, [test_a2.id, test_b1.id]
    )

    assert len(selected) == 1
    assert selected[0].id == test_a2.id


async def test_list_generated_tests_by_ids_for_project_returns_empty_on_empty_ids(
    session: AsyncSession,
) -> None:
    repo = TestRepository()

    selected = await repo.list_generated_tests_by_ids_for_project(
        session, project_id=1, test_ids=[]
    )

    assert selected == []


async def test_get_test_request_found(session: AsyncSession) -> None:
    project = Project(name="Projeto GetReq")
    session.add(project)
    await session.commit()
    await session.refresh(project)

    repo = TestRepository()
    test_request = TestRequest(
        project_id=project.id, prompt="Find me", status="pending"
    )
    created = await repo.create_test_request(session, test_request)

    found = await repo.get_test_request(session, created.id)
    assert found is not None
    assert found.id == created.id
    assert found.prompt == "Find me"


async def test_get_test_request_not_found(session: AsyncSession) -> None:
    repo = TestRepository()
    found = await repo.get_test_request(session, 99999)
    assert found is None
