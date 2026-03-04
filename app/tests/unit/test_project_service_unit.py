import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.project_service import ProjectService


class DummyRepository:
    def __init__(self, result: bool):
        self._result = result

    async def delete(self, session: AsyncSession, project_id: int) -> bool:
        return self._result


@pytest.mark.asyncio
async def test_delete_project_service_returns_true() -> None:
    service = ProjectService(repository=DummyRepository(True))
    result = await service.delete_project(session=None, project_id=1)
    assert result is True


@pytest.mark.asyncio
async def test_delete_project_service_returns_false() -> None:
    service = ProjectService(repository=DummyRepository(False))
    result = await service.delete_project(session=None, project_id=999)
    assert result is False
