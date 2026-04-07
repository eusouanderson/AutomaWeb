import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.log import Log
from app.repositories.log_repository import LogRepository


@pytest_asyncio.fixture()
async def session() -> AsyncSession: # type: ignore[arg-type]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session # type: ignore[arg-type]


async def test_create_log(session: AsyncSession) -> None:
    repo = LogRepository()
    log = Log(level="INFO", message="Test log message", context="Test context")
    created = await repo.create(session, log)
    
    assert created.id is not None
    assert created.level == "INFO"
    assert created.message == "Test log message"
    assert created.context == "Test context"


async def test_create_log_without_context(session: AsyncSession) -> None:
    repo = LogRepository()
    log = Log(level="ERROR", message="Error message")
    created = await repo.create(session, log)
    
    assert created.id is not None
    assert created.level == "ERROR"
    assert created.message == "Error message"
    assert created.context is None
