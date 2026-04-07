"""Tests to cover HTTPException raises and error paths"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.services.test_service import TestService


@pytest_asyncio.fixture()
async def error_session(tmp_path) -> AsyncSession:  # type: ignore[arg-type]
    settings.STATIC_DIR = str(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session  # type: ignore[arg-type]


async def test_generate_test_project_not_found(error_session: AsyncSession) -> None:
    """Test ValueError raised when project not found - line 39 of test_service.py"""
    service = TestService()
    
    with pytest.raises(ValueError, match="Project not found"):
        await service.generate_test(
            session=error_session,
            project_id=9999,
            prompt="Test",
        )


async def test_get_test_not_found(error_session: AsyncSession) -> None:
    """Test None returned when test not found"""
    service = TestService()
    result = await service.get_generated_test(error_session, 9999)
    assert result is None
