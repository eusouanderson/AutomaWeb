import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.api.deps import get_db
from app.main import app
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


@pytest.fixture(autouse=True)
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


@pytest.mark.asyncio
async def test_generate_endpoint(session: AsyncSession) -> None:
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
