import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from app.services.project_service import ProjectService


class DummyRepository:
    def __init__(self, project, delete_result: bool):
        self._project = project
        self._delete_result = delete_result

    async def get(self, session: AsyncSession, project_id: int):
        return self._project

    async def delete(self, session: AsyncSession, project_id: int) -> bool:
        return self._delete_result


def _fake_project(name: str = "Projeto", test_directory: str | None = "/tmp"):
    return type("FakeProject", (), {"id": 1, "name": name, "test_directory": test_directory})()


@pytest.mark.asyncio
async def test_delete_project_service_returns_true() -> None:
    service = ProjectService(repository=DummyRepository(_fake_project(), True))
    result = await service.delete_project(session=None, project_id=1)
    assert result is True


@pytest.mark.asyncio
async def test_delete_project_service_returns_false() -> None:
    service = ProjectService(repository=DummyRepository(None, False))
    result = await service.delete_project(session=None, project_id=999)
    assert result is False


@pytest.mark.asyncio
async def test_delete_project_service_returns_false_when_delete_fails() -> None:
    service = ProjectService(repository=DummyRepository(_fake_project(), False))

    result = await service.delete_project(session=None, project_id=1)

    assert result is False


def test_cleanup_project_reports_handles_remove_error(tmp_path, monkeypatch) -> None:
    settings.STATIC_DIR = str(tmp_path)
    reports_root = tmp_path / "reports"
    report_dir = reports_root / "1_20260305_100000"
    report_dir.mkdir(parents=True, exist_ok=True)

    service = ProjectService()

    def fake_rmtree(path):
        raise OSError("cannot remove")

    monkeypatch.setattr("app.services.project_service.shutil.rmtree", fake_rmtree)

    service._cleanup_project_reports(1)


def test_cleanup_project_reports_noop_when_reports_root_missing(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    service = ProjectService()

    service._cleanup_project_reports(1)


def test_cleanup_project_directories_uses_default_projects_dir(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    service = ProjectService()
    project = _fake_project(name="Projeto Base", test_directory=None)
    project_dir = tmp_path / "projects" / service._safe_dir_name(project.name)
    project_dir.mkdir(parents=True, exist_ok=True)

    service._cleanup_project_directories(project)

    assert not project_dir.exists()


def test_cleanup_project_directories_handles_remove_error(tmp_path, monkeypatch) -> None:
    service = ProjectService()
    project = _fake_project(name="Projeto Erro", test_directory=str(tmp_path))
    project_dir = tmp_path / service._safe_dir_name(project.name)
    project_dir.mkdir(parents=True, exist_ok=True)

    warning_calls = []

    def fake_rmtree(path):
        raise OSError("cannot remove project dir")

    def fake_warning(*args, **kwargs):
        warning_calls.append(args)

    monkeypatch.setattr("app.services.project_service.shutil.rmtree", fake_rmtree)
    monkeypatch.setattr("app.services.project_service.logger.warning", fake_warning)

    service._cleanup_project_directories(project)

    assert len(warning_calls) == 1


def test_safe_dir_name_falls_back_to_project() -> None:
    service = ProjectService()

    assert service._safe_dir_name("!!!") == "🧪_project"
