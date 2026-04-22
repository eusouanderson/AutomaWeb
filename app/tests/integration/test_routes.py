import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.models.project import Project
from app.services.test_service import TestService


class DummyGroqClient:
    def generate_robot_test(
        self,
        prompt: str,
        context: str | None = None,
        page_structure: dict | None = None,
    ) -> str:
        return "*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nExample\n    Log    Hello"


@pytest_asyncio.fixture()
async def session(tmp_path) -> AsyncSession:  # type: ignore[arg-type]
    settings.STATIC_DIR = str(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session  # type: ignore[arg-type]


@pytest_asyncio.fixture(autouse=True)  # type: ignore[arg-type]
def override_dependencies(session: AsyncSession):
    async def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db

    original_init = TestService.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["groq_client"] = DummyGroqClient()
        original_init(self, *args, **kwargs)

    TestService.__init__ = patched_init
    yield
    TestService.__init__ = original_init
    app.dependency_overrides.clear()


async def test_create_project_endpoint(session: AsyncSession) -> None:
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/projects", json={"name": "API Project", "description": "API Desc"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "API Project"
        assert data["description"] == "API Desc"
        assert "id" in data


async def test_list_projects_endpoint(session: AsyncSession) -> None:
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/projects", json={"name": "P1"})
        await client.post("/projects", json={"name": "P2"})

        response = await client.get("/projects")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


async def test_generate_test_endpoint(session: AsyncSession) -> None:
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_resp = await client.post(
            "/projects", json={"name": "P1", "description": "Desc"}
        )
        assert project_resp.status_code == 200
        project_id = project_resp.json()["id"]

        resp = await client.post(
            "/tests/generate",
            json={"project_id": project_id, "prompt": "Gerar", "context": "Ctx"},
        )
        assert resp.status_code == 200
        assert "content" in resp.json()


async def test_generate_test_nonexistent_project(session: AsyncSession) -> None:
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/tests/generate",
            json={"project_id": 9999, "prompt": "Gerar"},
        )
        assert resp.status_code == 404


async def test_list_project_tests_endpoint(session: AsyncSession) -> None:
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_resp = await client.post(
            "/projects", json={"name": "ListTestsProject", "description": "Desc"}
        )
        assert project_resp.status_code == 200
        project_id = project_resp.json()["id"]

        gen_resp = await client.post(
            "/tests/generate",
            json={"project_id": project_id, "prompt": "Gerar", "context": "Ctx"},
        )
        assert gen_resp.status_code == 200

        list_resp = await client.get(f"/projects/{project_id}/tests")
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert len(data) >= 1
        assert "id" in data[0]
        assert "file_path" in data[0]


async def test_get_test_endpoint(session: AsyncSession) -> None:
    from httpx import ASGITransport

    # Create a test directly via repository
    from app.models.project import Project
    from app.models.test_request import TestRequest
    from app.models.generated_test import GeneratedTest
    from app.repositories.project_repository import ProjectRepository
    from app.repositories.test_repository import TestRepository

    project_repo = ProjectRepository()
    test_repo = TestRepository()

    project = await project_repo.create(session, Project(name="Test"))
    test_request = await test_repo.create_test_request(
        session, TestRequest(project_id=project.id, prompt="Test", status="completed")
    )
    generated = await test_repo.create_generated_test(
        session,
        GeneratedTest(
            test_request_id=test_request.id, content="Test", file_path="/tmp/test.robot"
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/tests/{generated.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == generated.id


async def test_get_nonexistent_test_endpoint(session: AsyncSession) -> None:
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/tests/9999")
        assert resp.status_code == 404


async def test_download_test_endpoint(session: AsyncSession, tmp_path) -> None:
    from httpx import ASGITransport
    from app.models.project import Project
    from app.models.test_request import TestRequest
    from app.models.generated_test import GeneratedTest
    from app.repositories.project_repository import ProjectRepository
    from app.repositories.test_repository import TestRepository
    from pathlib import Path

    # Create test file
    test_file = tmp_path / "test.robot"
    test_file.write_text("*** Settings ***\nLibrary    Browser")

    project_repo = ProjectRepository()
    test_repo = TestRepository()

    project = await project_repo.create(session, Project(name="Test"))
    test_request = await test_repo.create_test_request(
        session, TestRequest(project_id=project.id, prompt="Test", status="completed")
    )
    generated = await test_repo.create_generated_test(
        session,
        GeneratedTest(
            test_request_id=test_request.id, content="Test", file_path=str(test_file)
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/tests/{generated.id}/download")
        assert resp.status_code == 200
        assert "robot" in resp.headers.get("content-disposition", "")


async def test_download_nonexistent_test(session: AsyncSession) -> None:
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/tests/9999/download")
        assert resp.status_code == 404


async def test_delete_generated_test_endpoint(session: AsyncSession, tmp_path) -> None:
    from app.models.generated_test import GeneratedTest
    from app.models.test_request import TestRequest
    from app.repositories.project_repository import ProjectRepository
    from app.repositories.test_repository import TestRepository

    test_file = tmp_path / "test_delete.robot"
    test_file.write_text("*** Settings ***\nLibrary    Browser")

    project_repo = ProjectRepository()
    test_repo = TestRepository()

    project = await project_repo.create(session, Project(name="DeleteGeneratedProject"))
    test_request = await test_repo.create_test_request(
        session,
        TestRequest(project_id=project.id, prompt="Delete me", status="completed"),
    )
    generated = await test_repo.create_generated_test(
        session,
        GeneratedTest(
            test_request_id=test_request.id,
            content="*** Test Cases ***\nExample\n    Log    Hi",
            file_path=str(test_file),
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        delete_resp = await client.delete(f"/tests/{generated.id}")
        assert delete_resp.status_code == 200

        get_resp = await client.get(f"/tests/{generated.id}")
        assert get_resp.status_code == 404


async def test_delete_nonexistent_generated_test_endpoint(
    session: AsyncSession,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        delete_resp = await client.delete("/tests/9999")
        assert delete_resp.status_code == 404
