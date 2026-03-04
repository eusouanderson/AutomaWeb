import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository
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
async def session(tmp_path) -> AsyncSession:
    settings.STATIC_DIR = str(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
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
    
    app.dependency_overrides.clear()
    TestService.__init__ = original_init


async def test_create_project_with_description(session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/projects", json={"name": "Project 1", "description": "A description"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Project 1"
        assert data["description"] == "A description"


async def test_get_nonexistent_project(session: AsyncSession) -> None:
    from app.services.project_service import ProjectService
    service = ProjectService()
    project = await service.get_project(session, 9999)
    assert project is None


async def test_generate_with_context(session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project_resp = await client.post("/projects", json={"name": "P1"})
        project_id = project_resp.json()["id"]

        gen_resp = await client.post(
            "/tests/generate",
            json={"project_id": project_id, "prompt": "Test login", "context": "Use Chrome browser"},
        )
        assert gen_resp.status_code == 200
        assert gen_resp.json()["content"] is not None


async def test_generate_returns_503_when_llm_unavailable(session: AsyncSession) -> None:
    class FailingGroqClient:
        def generate_robot_test(
            self,
            prompt: str,
            context: str | None = None,
            page_structure: dict | None = None,
        ) -> str:
            api_error = type("APIConnectionError", (Exception,), {})
            raise api_error("connection failed")

    original_init = TestService.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["groq_client"] = FailingGroqClient()
        original_init(self, *args, **kwargs)

    TestService.__init__ = patched_init

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            project_resp = await client.post("/projects", json={"name": "P2"})
            project_id = project_resp.json()["id"]

            gen_resp = await client.post(
                "/tests/generate",
                json={"project_id": project_id, "prompt": "Test login", "context": "Use Chrome browser"},
            )
            assert gen_resp.status_code == 503
            assert "Groq" in gen_resp.json()["detail"]
    finally:
        TestService.__init__ = original_init
