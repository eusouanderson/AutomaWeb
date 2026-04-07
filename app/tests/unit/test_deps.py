import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.db.base import Base


@pytest_asyncio.fixture()
async def test_session() -> AsyncSession:  # type: ignore[arg-type]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session  # type: ignore[arg-type]


async def test_get_db_dependency() -> None:
    gen = get_db()
    session = await gen.__anext__()
    assert isinstance(session, AsyncSession)
    
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass
