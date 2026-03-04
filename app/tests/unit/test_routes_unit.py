from datetime import datetime

import pytest

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import routes
from app.models.generated_test import GeneratedTest
from app.models.project import Project
from app.models.test_execution import TestExecution


@pytest.mark.asyncio
async def test_create_project_route(monkeypatch) -> None:
    async def fake_create_project(self, session: AsyncSession, name: str, description: str | None = None, test_directory: str | None = None):
        return Project(
            id=1,
            name=name,
            description=description,
            test_directory=test_directory,
            created_at=datetime.utcnow(),
        )

    monkeypatch.setattr(routes.ProjectService, "create_project", fake_create_project)
    payload = routes.ProjectCreate(name="Test", description="Desc", test_directory="/tmp/tests")
    result = await routes.create_project(payload, session=None)

    assert result.id == 1
    assert result.test_directory == "/tmp/tests"


@pytest.mark.asyncio
async def test_create_project_route_unique_error(monkeypatch) -> None:
    async def fake_create_project(self, session: AsyncSession, name: str, description: str | None = None, test_directory: str | None = None):
        raise Exception("UNIQUE constraint failed: projects.name")

    monkeypatch.setattr(routes.ProjectService, "create_project", fake_create_project)
    payload = routes.ProjectCreate(name="Teste", description="Desc", test_directory="/tmp/tests")

    with pytest.raises(HTTPException) as exc:
        await routes.create_project(payload, session=None)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_project_route_generic_error(monkeypatch) -> None:
    async def fake_create_project(self, session: AsyncSession, name: str, description: str | None = None, test_directory: str | None = None):
        raise Exception("Boom")

    monkeypatch.setattr(routes.ProjectService, "create_project", fake_create_project)
    payload = routes.ProjectCreate(name="Teste", description="Desc", test_directory="/tmp/tests")

    with pytest.raises(HTTPException) as exc:
        await routes.create_project(payload, session=None)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_list_projects_route(monkeypatch) -> None:
    async def fake_list_projects(self, session: AsyncSession):
        return [
            Project(
                id=1,
                name="P1",
                description=None,
                test_directory=None,
                created_at=datetime.utcnow(),
            )
        ]

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
            created_at=datetime.utcnow(),
        )

    monkeypatch.setattr(routes.TestService, "generate_test", fake_generate_test)
    payload = routes.TestGenerateRequest(project_id=1, prompt="Teste ok", context="CTX")
    result = await routes.generate_test(payload, session=None)

    assert result.id == 1
    assert result.content == "Test"


@pytest.mark.asyncio
async def test_generate_test_route_error(monkeypatch) -> None:
    async def fake_generate_test(self, session: AsyncSession, project_id: int, prompt: str, context: str | None = None):
        raise ValueError("Project not found")

    monkeypatch.setattr(routes.TestService, "generate_test", fake_generate_test)
    payload = routes.TestGenerateRequest(project_id=999, prompt="Teste ok")

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
            created_at=datetime.utcnow(),
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
            created_at=datetime.utcnow(),
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


@pytest.mark.asyncio
async def test_delete_project_route_success(monkeypatch) -> None:
    async def fake_delete_project(self, session: AsyncSession, project_id: int) -> bool:
        return True

    monkeypatch.setattr(routes.ProjectService, "delete_project", fake_delete_project)
    result = await routes.delete_project(1, session=None)

    assert result["message"] == "Projeto deletado com sucesso"


@pytest.mark.asyncio
async def test_delete_project_route_not_found(monkeypatch) -> None:
    async def fake_delete_project(self, session: AsyncSession, project_id: int) -> bool:
        return False

    monkeypatch.setattr(routes.ProjectService, "delete_project", fake_delete_project)

    with pytest.raises(HTTPException) as exc:
        await routes.delete_project(999, session=None)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_execute_tests_route_success(monkeypatch) -> None:
    async def fake_execute_tests(self, session: AsyncSession, project_id: int, test_ids=None):
        return TestExecution(
            id=1,
            project_id=project_id,
            total_tests=2,
            passed=2,
            failed=0,
            skipped=0,
            log_file="/static/reports/1/log.html",
            report_file="/static/reports/1/report.html",
            output_file="/static/reports/1/output.xml",
            status="completed",
            created_at=datetime.utcnow(),
        )

    monkeypatch.setattr(routes.TestExecutionService, "execute_tests", fake_execute_tests)
    payload = routes.TestExecutionRequest(project_id=1, test_ids=[1])
    result = await routes.execute_tests(payload, session=None)

    assert result.status == "completed"
    assert result.passed == 2


@pytest.mark.asyncio
async def test_execute_tests_route_error(monkeypatch) -> None:
    async def fake_execute_tests(self, session: AsyncSession, project_id: int, test_ids=None):
        raise ValueError("Project not found")

    monkeypatch.setattr(routes.TestExecutionService, "execute_tests", fake_execute_tests)
    payload = routes.TestExecutionRequest(project_id=999, test_ids=[1])

    with pytest.raises(HTTPException) as exc:
        await routes.execute_tests(payload, session=None)

    assert exc.value.status_code == 404
