import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.init_db import init_db
from app.db.session import get_async_session


@pytest_asyncio.fixture()
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    yield engine
    await engine.dispose()


async def test_init_db(test_engine) -> None:
    await init_db(test_engine)

    # Verify tables were created
    async with test_engine.begin() as conn:
        result = await conn.run_sync(
            lambda sync_conn: sync_conn.dialect.has_table(sync_conn, "users")
        )
        assert result is True


async def test_get_async_session() -> None:
    gen = get_async_session()
    session = await gen.__anext__()
    assert isinstance(session, AsyncSession)

    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass
