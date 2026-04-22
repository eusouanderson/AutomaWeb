from datetime import datetime
from pathlib import Path
import subprocess

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.project import Project
from app.models.test_execution import TestExecution
from app.services.test_execution_service import TestExecutionService
from app.services.test_service import TestService


class DummyProjectRepo:
    def __init__(self, project: Project | None):
        self._project = project

    async def get(self, session: AsyncSession, project_id: int):
        return self._project


class _DummyGeneratedTest:
    def __init__(self, file_path: str):
        self.file_path = file_path


class DummyTestRepo:
    async def get_generated_test(self, session: AsyncSession, test_id: int):
        return None

    async def list_generated_tests_by_ids_for_project(
        self, session: AsyncSession, project_id: int, test_ids: list[int]
    ):
        return [
            _DummyGeneratedTest(f"/tmp/generated_{test_id}.robot")
            for test_id in test_ids
        ]


def _prepare_project(tmp_path, name: str = "Projeto") -> Project:
    return Project(
        id=1,
        name=name,
        description="Desc",
        test_directory=str(tmp_path / "tests"),
        created_at=datetime.utcnow(),
    )


def _create_robot_file(project: Project) -> Path:
    safe_name = TestService()._safe_dir_name(project.name)
    project_dir = Path(project.test_directory) / safe_name  # type: ignore[arg-type]
    project_dir.mkdir(parents=True, exist_ok=True)
    robot_file = project_dir / "sample.robot"
    robot_file.write_text("*** Test Cases ***\nExample\n    Log    Hello")
    return project_dir


@pytest.mark.asyncio
async def test_execute_tests_happy_path(tmp_path, monkeypatch) -> None:
    settings.STATIC_DIR = str(tmp_path / "static")
    project = _prepare_project(tmp_path)

    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )

    _create_robot_file(project)

    def fake_run(*args, **kwargs):
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    async def fake_generate_mkdocs_report(project, output_dir, stats):
        return None

    monkeypatch.setattr(service, "_ensure_rfbrowser", lambda: None)
    monkeypatch.setattr(
        service,
        "_parse_robot_output",
        lambda *_: {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
    )
    monkeypatch.setattr(service, "_generate_mkdocs_report", fake_generate_mkdocs_report)
    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    execution = await service.execute_tests(session=None, project_id=1)  # type: ignore[arg-type]

    assert execution.status == "completed"
    assert execution.passed == 1
    assert execution.total_tests == 1


@pytest.mark.asyncio
async def test_execute_tests_runs_robot_non_interactive(tmp_path, monkeypatch) -> None:
    settings.STATIC_DIR = str(tmp_path / "static")
    project = _prepare_project(tmp_path)

    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )

    _create_robot_file(project)
    call_kwargs = {}

    def fake_run(*args, **kwargs):
        call_kwargs.update(kwargs)

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    async def fake_generate_mkdocs_report(project, output_dir, stats):
        return None

    monkeypatch.setattr(service, "_ensure_rfbrowser", lambda: None)
    monkeypatch.setattr(
        service,
        "_parse_robot_output",
        lambda *_: {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
    )
    monkeypatch.setattr(service, "_generate_mkdocs_report", fake_generate_mkdocs_report)
    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    await service.execute_tests(session=None, project_id=1)  # type: ignore[arg-type]

    assert call_kwargs.get("stdin") is subprocess.DEVNULL


@pytest.mark.asyncio
async def test_execute_tests_with_selected_test_ids(tmp_path, monkeypatch) -> None:
    settings.STATIC_DIR = str(tmp_path / "static")
    project = _prepare_project(tmp_path)
    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )

    def fake_run(*args, **kwargs):
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    async def fake_generate_mkdocs_report(project, output_dir, stats):
        return None

    monkeypatch.setattr(service, "_ensure_rfbrowser", lambda: None)
    monkeypatch.setattr(
        service,
        "_parse_robot_output",
        lambda *_: {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
    )
    monkeypatch.setattr(service, "_generate_mkdocs_report", fake_generate_mkdocs_report)
    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    execution = await service.execute_tests(session=None, project_id=1, test_ids=[10, 20])  # type: ignore[arg-type]

    assert execution.status == "completed"
    assert execution.total_tests == 2


@pytest.mark.asyncio
async def test_execute_tests_project_not_found() -> None:
    service = TestExecutionService(
        project_repository=DummyProjectRepo(None),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="Project not found"):
        await service.execute_tests(session=None, project_id=1)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_execute_tests_raises_when_project_is_already_running() -> None:
    service = TestExecutionService(
        project_repository=DummyProjectRepo(None),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )

    service.__class__._running_projects.add(1)
    try:
        with pytest.raises(ValueError, match="Tests are already running for project 1"):
            await service.execute_tests(session=None, project_id=1)  # type: ignore[arg-type]
    finally:
        service.__class__._running_projects.discard(1)


@pytest.mark.asyncio
async def test_execute_tests_raises_when_db_has_running_execution() -> None:
    service = TestExecutionService(
        project_repository=DummyProjectRepo(None),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )

    class _ScalarResult:
        def first(self):
            return object()

    class _ExecuteResult:
        def scalars(self):
            return _ScalarResult()

    class _SessionWithExecute:
        async def execute(self, _query):
            return _ExecuteResult()

    with pytest.raises(ValueError, match="already has a running execution"):
        await service.execute_tests(session=_SessionWithExecute(), project_id=1)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_execute_tests_missing_test_directory() -> None:
    project = Project(id=1, name="Projeto", description="Desc", test_directory=None)
    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="Project test directory not configured"):
        await service.execute_tests(session=None, project_id=1)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_execute_tests_no_test_files(tmp_path) -> None:
    project = _prepare_project(tmp_path)
    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="No test files found"):
        await service.execute_tests(session=None, project_id=1)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_execute_tests_failed_returncode_with_default_message(
    tmp_path, monkeypatch
) -> None:
    settings.STATIC_DIR = str(tmp_path / "static")
    project = _prepare_project(tmp_path)
    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )
    _create_robot_file(project)

    def fake_run(*args, **kwargs):
        class Result:
            returncode = 1
            stdout = ""
            stderr = ""

        return Result()

    async def fake_generate_mkdocs_report(project, output_dir, stats):
        return None

    monkeypatch.setattr(service, "_ensure_rfbrowser", lambda: None)
    monkeypatch.setattr(
        service,
        "_parse_robot_output",
        lambda *_: {"total": 1, "passed": 0, "failed": 1, "skipped": 0},
    )
    monkeypatch.setattr(service, "_generate_mkdocs_report", fake_generate_mkdocs_report)
    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    execution = await service.execute_tests(session=None, project_id=1)  # type: ignore[arg-type]

    assert execution.status == "failed"
    assert execution.error_output == "Test execution failed"


@pytest.mark.asyncio
async def test_execute_tests_timeout(tmp_path, monkeypatch) -> None:
    settings.STATIC_DIR = str(tmp_path / "static")
    project = _prepare_project(tmp_path)
    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )
    _create_robot_file(project)

    def fake_run(*args, **kwargs):
        from subprocess import TimeoutExpired

        raise TimeoutExpired(cmd="robot", timeout=1)

    monkeypatch.setattr(service, "_ensure_rfbrowser", lambda: None)
    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    execution = await service.execute_tests(session=None, project_id=1)  # type: ignore[arg-type]
    assert execution.status == "failed"
    assert execution.error_output == "Test execution timed out"


@pytest.mark.asyncio
async def test_execute_tests_handles_unexpected_exception(
    tmp_path, monkeypatch
) -> None:
    settings.STATIC_DIR = str(tmp_path / "static")
    project = _prepare_project(tmp_path)
    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )
    _create_robot_file(project)

    def fake_run(*args, **kwargs):
        raise RuntimeError("robot failed badly")

    monkeypatch.setattr(service, "_ensure_rfbrowser", lambda: None)
    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    execution = await service.execute_tests(session=None, project_id=1)  # type: ignore[arg-type]

    assert execution.status == "failed"
    assert execution.error_output == "robot failed badly"


def test_error_html() -> None:
    service = TestExecutionService()
    html = service._error_html("Robot Log", "Falhou")
    assert "Robot Log" in html
    assert "Falhou" in html


def test_ensure_report_files_creates_fallback(tmp_path) -> None:
    service = TestExecutionService()
    service._ensure_report_files(tmp_path, "Erro")

    assert (tmp_path / "output.xml").exists()
    assert (tmp_path / "log.html").exists()
    assert (tmp_path / "report.html").exists()


def test_sync_reports_for_static_replaces_existing_target(tmp_path) -> None:
    service = TestExecutionService()
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "log.html").write_text("log")
    (target / "old.txt").write_text("old")

    service._sync_reports_for_static(source, target)

    assert (target / "log.html").exists()
    assert not (target / "old.txt").exists()


def test_sync_reports_for_static_handles_copy_error(tmp_path, monkeypatch) -> None:
    service = TestExecutionService()
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    def fake_copytree(*args, **kwargs):
        raise OSError("cannot copy")

    monkeypatch.setattr(
        "app.services.test_execution_service.shutil.copytree", fake_copytree
    )

    service._sync_reports_for_static(source, target)


def test_parse_robot_output_missing_file(tmp_path) -> None:
    service = TestExecutionService()
    stats = service._parse_robot_output(tmp_path / "output.xml")
    assert stats == {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "test_cases": [],
    }


def test_parse_robot_output_success(tmp_path) -> None:
    service = TestExecutionService()
    xml = """
<robot>
  <statistics>
    <total>
      <stat pass="2" fail="1" skip="0"/>
    </total>
  </statistics>
</robot>
"""
    output = tmp_path / "output.xml"
    output.write_text(xml)

    stats = service._parse_robot_output(output)

    assert stats["total"] == 3
    assert stats["passed"] == 2
    assert stats["failed"] == 1
    assert stats["skipped"] == 0


def test_parse_robot_output_without_stat_returns_zeros(tmp_path) -> None:
    service = TestExecutionService()
    xml = "<robot><statistics><total></total></statistics></robot>"
    output = tmp_path / "output.xml"
    output.write_text(xml)

    stats = service._parse_robot_output(output)

    assert stats == {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "test_cases": [],
    }


def test_parse_robot_output_invalid_xml(tmp_path) -> None:
    service = TestExecutionService()
    output = tmp_path / "output.xml"
    output.write_text("<robot><statistics><total><stat pass='1' fail='0'></total>")

    stats = service._parse_robot_output(output)

    assert stats == {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "test_cases": [],
    }


def test_ensure_rfbrowser_handles_exception(monkeypatch) -> None:
    service = TestExecutionService()
    TestExecutionService._rfbrowser_ready = False

    def fake_run(*args, **kwargs):
        raise RuntimeError("rfbrowser missing")

    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    service._ensure_rfbrowser()


def test_ensure_rfbrowser_handles_wrapper_path_resolution_error(monkeypatch) -> None:
    service = TestExecutionService()
    TestExecutionService._rfbrowser_ready = False
    calls = []

    def fake_resolve(self):
        raise RuntimeError("resolve failed")

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(
        "app.services.test_execution_service.Path.resolve", fake_resolve
    )
    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    service._ensure_rfbrowser()

    assert len(calls) == 1


def test_ensure_rfbrowser_runs_only_once_when_ready(monkeypatch) -> None:
    service = TestExecutionService()
    TestExecutionService._rfbrowser_ready = False
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    service._ensure_rfbrowser()
    service._ensure_rfbrowser()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_generate_mkdocs_report_creates_files(tmp_path, monkeypatch) -> None:
    service = TestExecutionService()
    project = Project(name="Projeto", description="Desc", test_directory=str(tmp_path))
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def fake_run(*args, **kwargs):
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    stats = {"total": 2, "passed": 2, "failed": 0, "skipped": 0}
    await service._generate_mkdocs_report(project, output_dir, stats)

    assert (output_dir / "mkdocs" / "docs" / "index.md").exists()
    assert (output_dir / "mkdocs" / "mkdocs.yml").exists()


@pytest.mark.asyncio
async def test_generate_mkdocs_report_handles_error(tmp_path, monkeypatch) -> None:
    service = TestExecutionService()
    project = Project(name="Projeto", description="Desc", test_directory=str(tmp_path))
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def fake_run(*args, **kwargs):
        raise RuntimeError("mkdocs failed")

    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    stats = {"total": 1, "passed": 1, "failed": 0, "skipped": 0}
    await service._generate_mkdocs_report(project, output_dir, stats)

    assert (output_dir / "mkdocs" / "docs" / "index.md").exists()


# ---------------------------------------------------------------------------
# _apply_pre_execution_healing – line 215
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_pre_execution_healing_writes_when_content_changed(
    tmp_path,
) -> None:
    """Line 215: path.write_text is called when healed content differs from original."""
    from unittest.mock import AsyncMock, MagicMock
    from app.ai_validation.self_healing_service import HealedTestResult

    robot_file = tmp_path / "test.robot"
    original = "*** Test Cases ***\nFoo\n    Click    //a\n"
    robot_file.write_text(original, encoding="utf-8")

    healed_result = HealedTestResult(
        original_content=original,
        final_content="*** Test Cases ***\nFoo\n    Click    css=a\n",
        issues_found=[],
        fixes_applied=["L3: locator refinado"],
    )

    mock_healing = MagicMock()
    mock_healing.heal_test = AsyncMock(return_value=healed_result)

    service = TestExecutionService()
    service._self_healing = mock_healing

    result = await service._apply_pre_execution_healing(
        [str(robot_file)], page_url=None, ai_debug=False
    )

    assert result == [str(robot_file)]
    assert robot_file.read_text(encoding="utf-8") == healed_result.final_content


# ---------------------------------------------------------------------------
# _parse_robot_output – lines 301-304 (test elements with status children)
# ---------------------------------------------------------------------------


def test_parse_robot_output_with_test_elements(tmp_path) -> None:
    """Lines 301-304: covers the for-loop body when <test> elements have <status> children."""
    service = TestExecutionService()
    xml = """\
<robot>
  <statistics>
    <total>
      <stat pass="1" fail="1" skip="0"/>
    </total>
  </statistics>
  <suite>
    <test name="Login Test">
      <status status="PASS">All steps OK</status>
    </test>
    <test name="Logout Test">
      <status status="FAIL">Element not found</status>
    </test>
  </suite>
</robot>
"""
    output = tmp_path / "output.xml"
    output.write_text(xml)

    stats = service._parse_robot_output(output)

    assert stats["total"] == 2
    assert stats["passed"] == 1
    assert stats["failed"] == 1
    assert len(stats["test_cases"]) == 2
    names = [tc["name"] for tc in stats["test_cases"]]
    assert "Login Test" in names
    assert "Logout Test" in names
    statuses = {tc["name"]: tc["status"] for tc in stats["test_cases"]}
    assert statuses["Login Test"] == "PASS"
    assert statuses["Logout Test"] == "FAIL"


def test_parse_robot_output_with_test_element_empty_message(tmp_path) -> None:
    """msg is None when status element has no text."""
    service = TestExecutionService()
    xml = """\
<robot>
  <statistics><total><stat pass="1" fail="0" skip="0"/></total></statistics>
  <suite>
    <test name="Silent Test">
      <status status="PASS"></status>
    </test>
  </suite>
</robot>
"""
    output = tmp_path / "output.xml"
    output.write_text(xml)

    stats = service._parse_robot_output(output)

    assert stats["test_cases"][0]["message"] is None


# ---------------------------------------------------------------------------
# execute_tests – DB persist branch (lines 175-177)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tests_persists_to_db_when_session_provided(
    tmp_path, monkeypatch
) -> None:
    """Lines 175-177: session.add / commit / refresh are called when session is not None."""
    settings.STATIC_DIR = str(tmp_path / "static")
    project = _prepare_project(tmp_path)
    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),  # type: ignore[arg-type]
        test_repository=DummyTestRepo(),  # type: ignore[arg-type]
    )
    _create_robot_file(project)

    def fake_run(*args, **kwargs):
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    async def fake_generate_mkdocs_report(project, output_dir, stats):
        return None

    monkeypatch.setattr(service, "_ensure_rfbrowser", lambda: None)
    monkeypatch.setattr(
        service,
        "_parse_robot_output",
        lambda *_: {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
    )
    monkeypatch.setattr(service, "_generate_mkdocs_report", fake_generate_mkdocs_report)
    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    calls = []

    class FakeSession:
        def add(self, obj):
            calls.append(("add", obj))

        async def commit(self):
            calls.append(("commit",))

        async def refresh(self, obj):
            calls.append(("refresh", obj))

    execution = await service.execute_tests(session=FakeSession(), project_id=1)  # type: ignore[arg-type]

    assert execution.status == "completed"
    assert any(c[0] == "add" for c in calls)
    assert any(c[0] == "commit" for c in calls)
    assert any(c[0] == "refresh" for c in calls)


# ---------------------------------------------------------------------------
# list_executions_by_project (lines 187-193)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_executions_by_project_returns_results() -> None:
    """Lines 187-193: list_executions_by_project queries the DB and returns executions."""
    from datetime import datetime
    from unittest.mock import AsyncMock, MagicMock

    service = TestExecutionService()

    expected = [
        TestExecution(
            id=1,
            project_id=42,
            total_tests=2,
            passed=2,
            failed=0,
            skipped=0,
            log_file="/static/reports/42_run/log.html",
            report_file="/static/reports/42_run/report.html",
            output_file="/static/reports/42_run/output.xml",
            status="completed",
            created_at=datetime.utcnow(),
        )
    ]

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = expected

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    session = MagicMock()
    session.execute = AsyncMock(return_value=result_mock)

    results = await service.list_executions_by_project(session, project_id=42)

    assert results == expected
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_executions_by_project_returns_empty_list() -> None:
    """list_executions_by_project returns [] when no executions exist."""
    from unittest.mock import AsyncMock, MagicMock

    service = TestExecutionService()

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    session = MagicMock()
    session.execute = AsyncMock(return_value=result_mock)

    results = await service.list_executions_by_project(session, project_id=99)

    assert results == []
