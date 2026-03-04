from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from app.db.session import engine
from app.models import generated_test, log, project, test_execution, test_request, user  # noqa: F401


async def init_db(db_engine: AsyncEngine | None = None) -> None:
    """Initialize database tables."""

    target_engine = db_engine or engine
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_project_test_directory_column)


def _ensure_project_test_directory_column(sync_conn) -> None:
    inspector = inspect(sync_conn)
    columns = {col["name"] for col in inspector.get_columns("projects")}
    if "test_directory" in columns:
        return

    sync_conn.execute(
        text("ALTER TABLE projects ADD COLUMN test_directory VARCHAR(500)")
    )
