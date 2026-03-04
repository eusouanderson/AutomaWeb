from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from app.db.session import engine
from app.models import generated_test, log, project, test_request, user  # noqa: F401


async def init_db(db_engine: AsyncEngine | None = None) -> None:
    """Initialize database tables."""

    target_engine = db_engine or engine
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
