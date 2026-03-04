from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.project import Project
from app.services.test_execution_service import TestExecutionService
from app.services.test_service import TestService


class DummyProjectRepo:
    def __init__(self, project: Project | None):
        self._project = project

    async def get(self, session: AsyncSession, project_id: int):
        return self._project


class DummyTestRepo:
    async def get_generated_test(self, session: AsyncSession, test_id: int):
        return None


@pytest.mark.asyncio
async def test_execute_tests_happy_path(tmp_path, monkeypatch) -> None:
    settings.STATIC_DIR = str(tmp_path / "static")
    project = Project(
        id=1,
        name="Projeto",
        description="Desc",
        test_directory=str(tmp_path / "tests"),
        created_at=datetime.utcnow(),
    )

    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),
        test_repository=DummyTestRepo(),
    )

    safe_name = TestService()._safe_dir_name(project.name)
    project_dir = Path(project.test_directory) / safe_name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sample.robot").write_text("*** Test Cases ***\nExample\n    Log    Hello")

    def fake_run(*args, **kwargs):
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    async def fake_generate_mkdocs_report(project, output_dir, stats):
        return None

    monkeypatch.setattr(service, "_ensure_rfbrowser", lambda: None)
    monkeypatch.setattr(service, "_parse_robot_output", lambda *_: {"total": 1, "passed": 1, "failed": 0, "skipped": 0})
    monkeypatch.setattr(service, "_generate_mkdocs_report", fake_generate_mkdocs_report)
    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    execution = await service.execute_tests(session=None, project_id=1)

    assert execution.status == "completed"
    assert execution.passed == 1
    assert execution.total_tests == 1


@pytest.mark.asyncio
async def test_execute_tests_project_not_found(monkeypatch) -> None:
    service = TestExecutionService(
        project_repository=DummyProjectRepo(None),
        test_repository=DummyTestRepo(),
    )

    with pytest.raises(ValueError):
        await service.execute_tests(session=None, project_id=1)


@pytest.mark.asyncio
async def test_execute_tests_missing_test_directory(monkeypatch) -> None:
    project = Project(id=1, name="Projeto", description="Desc", test_directory=None)
    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),
        test_repository=DummyTestRepo(),
    )

    with pytest.raises(ValueError):
        await service.execute_tests(session=None, project_id=1)


@pytest.mark.asyncio
async def test_execute_tests_no_test_files(tmp_path) -> None:
    project = Project(
        id=1,
        name="Projeto",
        description="Desc",
        test_directory=str(tmp_path / "tests"),
    )
    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),
        test_repository=DummyTestRepo(),
    )

    with pytest.raises(ValueError):
        await service.execute_tests(session=None, project_id=1)


@pytest.mark.asyncio
async def test_execute_tests_failed_returncode(tmp_path, monkeypatch) -> None:
    settings.STATIC_DIR = str(tmp_path / "static")
    project = Project(
        id=1,
        name="Projeto",
        description="Desc",
        test_directory=str(tmp_path / "tests"),
    )

    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),
        test_repository=DummyTestRepo(),
    )

    safe_name = TestService()._safe_dir_name(project.name)
    project_dir = Path(project.test_directory) / safe_name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sample.robot").write_text("*** Test Cases ***\nExample\n    Log    Hello")

    def fake_run(*args, **kwargs):
        class Result:
            returncode = 1
            stdout = ""
            stderr = "Erro"

        return Result()

    async def fake_generate_mkdocs_report(project, output_dir, stats):
        return None

    monkeypatch.setattr(service, "_ensure_rfbrowser", lambda: None)
    monkeypatch.setattr(service, "_parse_robot_output", lambda *_: {"total": 1, "passed": 0, "failed": 1, "skipped": 0})
    monkeypatch.setattr(service, "_generate_mkdocs_report", fake_generate_mkdocs_report)
    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    execution = await service.execute_tests(session=None, project_id=1)
    assert execution.status == "failed"
    assert execution.error_output == "Erro"


@pytest.mark.asyncio
async def test_execute_tests_timeout(tmp_path, monkeypatch) -> None:
    settings.STATIC_DIR = str(tmp_path / "static")
    project = Project(
        id=1,
        name="Projeto",
        description="Desc",
        test_directory=str(tmp_path / "tests"),
    )

    service = TestExecutionService(
        project_repository=DummyProjectRepo(project),
        test_repository=DummyTestRepo(),
    )

    safe_name = TestService()._safe_dir_name(project.name)
    project_dir = Path(project.test_directory) / safe_name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sample.robot").write_text("*** Test Cases ***\nExample\n    Log    Hello")

    def fake_run(*args, **kwargs):
        from subprocess import TimeoutExpired

        raise TimeoutExpired(cmd="robot", timeout=1)

    monkeypatch.setattr(service, "_ensure_rfbrowser", lambda: None)
    monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)

    execution = await service.execute_tests(session=None, project_id=1)
    assert execution.status == "failed"
    assert execution.error_output == "Test execution timed out"


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


def test_parse_robot_output_missing_file(tmp_path) -> None:
    service = TestExecutionService()
    stats = service._parse_robot_output(tmp_path / "output.xml")
    assert stats == {"total": 0, "passed": 0, "failed": 0, "skipped": 0}


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
    def test_parse_robot_output_invalid_xml(tmp_path) -> None:
        service = TestExecutionService()
        output = tmp_path / "output.xml"
        output.write_text("<robot><statistics><total><stat pass='1' fail='0'></total>")

        stats = service._parse_robot_output(output)
        assert stats == {"total": 0, "passed": 0, "failed": 0, "skipped": 0}


    def test_ensure_rfbrowser_handles_exception(monkeypatch) -> None:
        service = TestExecutionService()

        def fake_run(*args, **kwargs):
            raise RuntimeError("rfbrowser missing")

        monkeypatch.setattr("app.services.test_execution_service.subprocess.run", fake_run)
        service._ensure_rfbrowser()

    assert stats["passed"] == 2
    assert stats["failed"] == 1
    assert stats["skipped"] == 0


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
