from datetime import datetime
import json

import pytest

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import routes
from app.models.generated_test import GeneratedTest
from app.models.project import Project
from app.models.test_execution import TestExecution
from app.services.element_scanner import ElementScannerError
from app.services.test_service import LLMServiceUnavailableError, ScanUnavailableError


@pytest.mark.asyncio
async def test_create_project_route(monkeypatch) -> None:
    async def fake_create_project(
        self,
        session: AsyncSession,
        name: str,
        description: str | None = None,
        url: str | None = None,
        test_directory: str | None = None,
    ):
        return Project(
            id=1,
            name=name,
            description=description,
            url=url,
            test_directory=test_directory,
            created_at=datetime.utcnow(),
        )

    monkeypatch.setattr(routes.ProjectService, "create_project", fake_create_project)
    payload = routes.ProjectCreate(
        name="Test",
        description="Desc",
        url="https://example.com",
        test_directory="/tmp/tests",
    )
    result = await routes.create_project(payload, session=None)

    assert result.id == 1
    assert result.url == "https://example.com/"
    assert result.test_directory == "/tmp/tests"


@pytest.mark.asyncio
async def test_create_project_route_unique_error(monkeypatch) -> None:
    async def fake_create_project(
        self,
        session: AsyncSession,
        name: str,
        description: str | None = None,
        url: str | None = None,
        test_directory: str | None = None,
    ):
        raise Exception("UNIQUE constraint failed: projects.name")

    monkeypatch.setattr(routes.ProjectService, "create_project", fake_create_project)
    payload = routes.ProjectCreate(name="Teste", description="Desc", url="https://example.com", test_directory="/tmp/tests")

    with pytest.raises(HTTPException) as exc:
        await routes.create_project(payload, session=None)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_project_route_generic_error(monkeypatch) -> None:
    async def fake_create_project(
        self,
        session: AsyncSession,
        name: str,
        description: str | None = None,
        url: str | None = None,
        test_directory: str | None = None,
    ):
        raise Exception("Boom")

    monkeypatch.setattr(routes.ProjectService, "create_project", fake_create_project)
    payload = routes.ProjectCreate(name="Teste", description="Desc", url="https://example.com", test_directory="/tmp/tests")

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
                url="https://example.com",
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
    async def fake_generate_test(self, session: AsyncSession, project_id: int, prompt: str, context: str | None = None, ai_debug: bool = False, force_rescan: bool = False):
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
    async def fake_generate_test(self, session: AsyncSession, project_id: int, prompt: str, context: str | None = None, ai_debug: bool = False, force_rescan: bool = False):
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
async def test_delete_test_route_success(monkeypatch) -> None:
    async def fake_delete_generated_test(self, session: AsyncSession, test_id: int) -> bool:
        return True

    monkeypatch.setattr(routes.TestService, "delete_generated_test", fake_delete_generated_test)
    result = await routes.delete_test(1, session=None)

    assert result["message"] == "Teste deletado com sucesso"


@pytest.mark.asyncio
async def test_delete_test_route_not_found(monkeypatch) -> None:
    async def fake_delete_generated_test(self, session: AsyncSession, test_id: int) -> bool:
        return False

    monkeypatch.setattr(routes.TestService, "delete_generated_test", fake_delete_generated_test)

    with pytest.raises(HTTPException) as exc:
        await routes.delete_test(999, session=None)

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
    async def fake_execute_tests(self, session: AsyncSession, project_id: int, test_ids=None, ai_debug: bool = False, headless: bool = True):
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
    async def fake_execute_tests(self, session: AsyncSession, project_id: int, test_ids=None, ai_debug: bool = False, headless: bool = True):
        raise ValueError("Project not found")

    monkeypatch.setattr(routes.TestExecutionService, "execute_tests", fake_execute_tests)
    payload = routes.TestExecutionRequest(project_id=999, test_ids=[1])

    with pytest.raises(HTTPException) as exc:
        await routes.execute_tests(payload, session=None)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_project_tests_route_success(monkeypatch) -> None:
    generated = GeneratedTest(
        id=10,
        test_request_id=20,
        content="*** Test Cases ***",
        file_path="/tmp/path/generated_test_10.robot",
        created_at=datetime.utcnow(),
    )

    async def fake_list_generated_tests_by_project(self, session: AsyncSession, project_id: int):
        return [generated]

    monkeypatch.setattr(routes.TestService, "list_generated_tests_by_project", fake_list_generated_tests_by_project)

    result = await routes.list_project_tests(1, session=None)

    assert len(result) == 1
    assert result[0].id == 10
    assert result[0].file_path == "generated_test_10.robot"


@pytest.mark.asyncio
async def test_list_project_tests_route_not_found(monkeypatch) -> None:
    async def fake_list_generated_tests_by_project(self, session: AsyncSession, project_id: int):
        raise ValueError("Project not found")

    monkeypatch.setattr(routes.TestService, "list_generated_tests_by_project", fake_list_generated_tests_by_project)

    with pytest.raises(HTTPException) as exc:
        await routes.list_project_tests(999, session=None)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Project not found"


@pytest.mark.asyncio
async def test_generate_test_route_llm_unavailable(monkeypatch) -> None:
    async def fake_generate_test(self, session: AsyncSession, project_id: int, prompt: str, context: str | None = None, ai_debug: bool = False, force_rescan: bool = False):
        raise LLMServiceUnavailableError("upstream unavailable")

    monkeypatch.setattr(routes.TestService, "generate_test", fake_generate_test)
    payload = routes.TestGenerateRequest(project_id=1, prompt="Teste")

    with pytest.raises(HTTPException) as exc:
        await routes.generate_test(payload, session=None)

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_generate_test_route_scan_unavailable(monkeypatch) -> None:
    async def fake_generate_test(self, session: AsyncSession, project_id: int, prompt: str, context: str | None = None, ai_debug: bool = False, force_rescan: bool = False):
        raise ScanUnavailableError("scan failed")

    monkeypatch.setattr(routes.TestService, "generate_test", fake_generate_test)
    payload = routes.TestGenerateRequest(project_id=1, prompt="Teste")

    with pytest.raises(HTTPException) as exc:
        await routes.generate_test(payload, session=None)

    assert exc.value.status_code == 502
    assert "scan failed" in exc.value.detail


@pytest.mark.asyncio
async def test_scan_page_stream_success(monkeypatch) -> None:
    class DummyScanResult:
        def model_dump(self):
            return {"title": "Home", "total_elements": 1}

    class DummyScanner:
        async def scan_url(self, _url: str, progress_callback=None):
            await progress_callback("step-1")
            return DummyScanResult()

    monkeypatch.setattr(routes, "ElementScannerService", lambda: DummyScanner())

    response = await routes.scan_page(routes.ScanRequest(url="https://example.com"))
    body_iter = response.body_iterator

    first = await anext(body_iter)
    second = await anext(body_iter)

    progress = json.loads(first.removeprefix("data: ").strip())
    result = json.loads(second.removeprefix("data: ").strip())

    assert progress["type"] == "progress"
    assert progress["message"] == "step-1"
    assert result["type"] == "result"
    assert result["data"]["title"] == "Home"

    with pytest.raises(StopAsyncIteration):
        await anext(body_iter)


@pytest.mark.asyncio
async def test_scan_page_stream_error(monkeypatch) -> None:
    class DummyScanner:
        async def scan_url(self, _url: str, progress_callback=None):
            raise ElementScannerError("scan boom")

    monkeypatch.setattr(routes, "ElementScannerService", lambda: DummyScanner())

    response = await routes.scan_page(routes.ScanRequest(url="https://example.com"), session=None)
    body_iter = response.body_iterator
    event = await anext(body_iter)
    payload = json.loads(event.removeprefix("data: ").strip())

    assert payload["type"] == "error"
    assert payload["message"] == "scan boom"

    with pytest.raises(StopAsyncIteration):
        await anext(body_iter)


@pytest.mark.asyncio
async def test_scan_page_stream_cancels_running_task_on_close(monkeypatch) -> None:
    release_scan = routes.asyncio.Event()

    class DummyScanner:
        async def scan_url(self, _url: str, progress_callback=None):
            await progress_callback("starting")
            await release_scan.wait()
            return type("Result", (), {"model_dump": lambda self: {"ok": True}})()

    monkeypatch.setattr(routes, "ElementScannerService", lambda: DummyScanner())

    response = await routes.scan_page(routes.ScanRequest(url="https://example.com"), session=None)
    body_iter = response.body_iterator

    first = await anext(body_iter)
    payload = json.loads(first.removeprefix("data: ").strip())
    assert payload["type"] == "progress"

    await body_iter.aclose()
    release_scan.set()


@pytest.mark.asyncio
async def test_list_project_executions_route_returns_list(monkeypatch) -> None:
    execution = TestExecution(
        id=5,
        project_id=1,
        total_tests=3,
        passed=3,
        failed=0,
        skipped=0,
        log_file="/static/reports/1_20260101_120000/log.html",
        report_file="/static/reports/1_20260101_120000/report.html",
        output_file="/static/reports/1_20260101_120000/output.xml",
        status="completed",
        created_at=datetime.utcnow(),
    )

    async def fake_list_executions(self, session, project_id: int):
        return [execution]

    monkeypatch.setattr(routes.TestExecutionService, "list_executions_by_project", fake_list_executions)
    result = await routes.list_project_executions(1, session=None)

    assert len(result) == 1
    assert result[0].id == 5
    assert result[0].status == "completed"
    assert result[0].passed == 3


@pytest.mark.asyncio
async def test_list_project_executions_route_returns_empty(monkeypatch) -> None:
    async def fake_list_executions(self, session, project_id: int):
        return []

    monkeypatch.setattr(routes.TestExecutionService, "list_executions_by_project", fake_list_executions)
    result = await routes.list_project_executions(99, session=None)

    assert result == []


# ── improve_robot_test ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_improve_robot_test_route_success(monkeypatch) -> None:
    async def fake_improve_robot_test(self, session, test_id: int, content: str):
        return "*** Test Cases ***\nImproved Test\n    Log    improved"

    monkeypatch.setattr(routes.TestService, "improve_robot_test", fake_improve_robot_test)

    payload = routes.RobotImproveRequest(content="*** Test Cases ***\nOld Test")
    result = await routes.improve_robot_test(1, payload, session=None)

    assert result.content == "*** Test Cases ***\nImproved Test\n    Log    improved"


@pytest.mark.asyncio
async def test_improve_robot_test_route_not_found(monkeypatch) -> None:
    async def fake_improve_robot_test(self, session, test_id: int, content: str):
        return None

    monkeypatch.setattr(routes.TestService, "improve_robot_test", fake_improve_robot_test)

    payload = routes.RobotImproveRequest(content="*** Test Cases ***")
    with pytest.raises(HTTPException) as exc:
        await routes.improve_robot_test(999, payload, session=None)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Test not found"


# ── update_robot_test_content ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_robot_test_content_route_success(monkeypatch) -> None:
    updated = GeneratedTest(
        id=2,
        test_request_id=20,
        content="*** Test Cases ***\nEdited",
        file_path="/tmp/t2.robot",
        created_at=datetime.utcnow(),
    )

    async def fake_save_robot_test_content(self, session, test_id: int, content: str):
        return updated

    monkeypatch.setattr(routes.TestService, "save_robot_test_content", fake_save_robot_test_content)

    payload = routes.RobotImproveRequest(content="*** Test Cases ***\nEdited")
    result = await routes.update_robot_test_content(2, payload, session=None)

    assert result.id == 2
    assert result.content == "*** Test Cases ***\nEdited"


@pytest.mark.asyncio
async def test_update_robot_test_content_route_not_found(monkeypatch) -> None:
    async def fake_save_robot_test_content(self, session, test_id: int, content: str):
        return None

    monkeypatch.setattr(routes.TestService, "save_robot_test_content", fake_save_robot_test_content)

    payload = routes.RobotImproveRequest(content="*** Test Cases ***")
    with pytest.raises(HTTPException) as exc:
        await routes.update_robot_test_content(999, payload, session=None)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Test not found"
