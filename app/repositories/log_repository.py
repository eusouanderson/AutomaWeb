from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import Log


class LogRepository:
    """Log data access layer."""

    async def create(self, session: AsyncSession, log: Log) -> Log:
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log
