import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.models.project import Project
from app.services.test_service import TestService


class DummyGroqClient:
    def generate_robot_test(self, prompt: str, context: str | None = None) -> str:
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


@pytest.mark.asyncio
async def test_generate_test(session: AsyncSession) -> None:
    project = Project(name="Projeto Teste", description="Desc")
    session.add(project)
    await session.commit()
    await session.refresh(project)

    service = TestService(groq_client=DummyGroqClient())
    generated = await service.generate_test(
        session=session,
        project_id=project.id,
        prompt="Gerar teste",
        context="Contexto",
    )

    assert generated.id is not None
    assert "*** Test Cases ***" in generated.content
