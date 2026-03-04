import pytest

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import routes
from app.models.generated_test import GeneratedTest
from app.models.project import Project


@pytest.mark.asyncio
async def test_create_project_route(monkeypatch) -> None:
    async def fake_create_project(self, session: AsyncSession, name: str, description: str | None = None, test_directory: str | None = None):
        return Project(id=1, name=name, description=description, test_directory=test_directory)

    monkeypatch.setattr(routes.ProjectService, "create_project", fake_create_project)
    payload = routes.ProjectCreate(name="Test", description="Desc", test_directory="/tmp/tests")
    result = await routes.create_project(payload, session=None)

    assert result.id == 1
    assert result.test_directory == "/tmp/tests"


@pytest.mark.asyncio
async def test_list_projects_route(monkeypatch) -> None:
    async def fake_list_projects(self, session: AsyncSession):
        return [Project(id=1, name="P1", description=None, test_directory=None)]

    monkeypatch.setattr(routes.ProjectService, "list_projects", fake_list_projects)
    result = await routes.list_projects(session=None)

    assert len(result) == 1
    assert result[0].name == "P1"


@pytest.mark.asyncio
async def test_generate_test_route_success(monkeypatch, tmp_path) -> None:
    async def fake_generate_test(self, session: AsyncSession, project_id: int, prompt: str, context: str | None = None):
        return GeneratedTest(
            id=1,
            test_request_id=1,
            content="Test",
            file_path=str(tmp_path / "test.robot"),
        )

    monkeypatch.setattr(routes.TestService, "generate_test", fake_generate_test)
    payload = routes.TestGenerateRequest(project_id=1, prompt="Test", context="CTX")
    result = await routes.generate_test(payload, session=None)

    assert result.id == 1
    assert result.content == "Test"


@pytest.mark.asyncio
async def test_generate_test_route_error(monkeypatch) -> None:
    async def fake_generate_test(self, session: AsyncSession, project_id: int, prompt: str, context: str | None = None):
        raise ValueError("Project not found")

    monkeypatch.setattr(routes.TestService, "generate_test", fake_generate_test)
    payload = routes.TestGenerateRequest(project_id=999, prompt="Test")

    with pytest.raises(HTTPException) as exc:
        await routes.generate_test(payload, session=None)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_test_route_success(monkeypatch, tmp_path) -> None:
    async def fake_get_generated_test(self, session: AsyncSession, test_id: int):
        return GeneratedTest(
            id=test_id,
            test_request_id=1,
            content="Test",
            file_path=str(tmp_path / "test.robot"),
        )

    monkeypatch.setattr(routes.TestService, "get_generated_test", fake_get_generated_test)
    result = await routes.get_test(1, session=None)

    assert result.id == 1


@pytest.mark.asyncio
async def test_get_test_route_not_found(monkeypatch) -> None:
    async def fake_get_generated_test(self, session: AsyncSession, test_id: int):
        return None

    monkeypatch.setattr(routes.TestService, "get_generated_test", fake_get_generated_test)

    with pytest.raises(HTTPException) as exc:
        await routes.get_test(999, session=None)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_download_test_route_success(monkeypatch, tmp_path) -> None:
    test_file = tmp_path / "test.robot"
    test_file.write_text("*** Settings ***")

    async def fake_get_generated_test(self, session: AsyncSession, test_id: int):
        return GeneratedTest(
            id=test_id,
            test_request_id=1,
            content="Test",
            file_path=str(test_file),
        )

    monkeypatch.setattr(routes.TestService, "get_generated_test", fake_get_generated_test)
    response = await routes.download_test(1, session=None)

    assert response.path == str(test_file)


@pytest.mark.asyncio
async def test_download_test_route_not_found(monkeypatch) -> None:
    async def fake_get_generated_test(self, session: AsyncSession, test_id: int):
        return None

    monkeypatch.setattr(routes.TestService, "get_generated_test", fake_get_generated_test)

    with pytest.raises(HTTPException) as exc:
        await routes.download_test(999, session=None)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_execution_report_not_implemented() -> None:
    with pytest.raises(HTTPException) as exc:
        await routes.get_execution_report(1)

    assert exc.value.status_code == 501
