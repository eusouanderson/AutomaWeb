"""Service for executing Robot Framework tests and generating reports"""
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.test_execution import TestExecution
from app.repositories.project_repository import ProjectRepository
from app.repositories.test_repository import TestRepository

logger = logging.getLogger(__name__)


class TestExecutionService:
    """Service for executing tests and generating reports."""

    def __init__(
        self,
        project_repository: ProjectRepository | None = None,
        test_repository: TestRepository | None = None,
    ) -> None:
        self._project_repository = project_repository or ProjectRepository()
        self._test_repository = test_repository or TestRepository()

    async def execute_tests(
        self,
        session: AsyncSession,
        project_id: int,
        test_ids: list[int] | None = None,
    ) -> TestExecution:
        """Execute Robot Framework tests for a project."""
        project = await self._project_repository.get(session, project_id)
        if not project:
            raise ValueError("Project not found")

        if not project.test_directory:
            raise ValueError("Project test directory not configured")

        # Create test directory if it doesn't exist
        test_dir = Path(project.test_directory)
        test_dir.mkdir(parents=True, exist_ok=True)

        # Get test files - search in project folder
        from app.services.test_service import TestService
        safe_name = TestService()._safe_dir_name(project.name)
        base_dir = Path(project.test_directory) if project.test_directory else Path(settings.STATIC_DIR) / "projects"
        project_dir = base_dir / safe_name
        
        if test_ids:
            test_files = []
            for test_id in test_ids:
                generated = await self._test_repository.get_generated_test(session, test_id)
                if generated:
                    test_files.append(generated.file_path)
        else:
            # Get all .robot files from project folder
            test_files = list(project_dir.glob("*.robot")) if project_dir.exists() else []

        if not test_files:
            raise ValueError(f"No test files found in {project_dir}")

        # Robot will execute files directly from project folder
        test_dir = project_dir

        # Create output directory for reports under STATIC_DIR for browser access
        reports_root = Path(settings.STATIC_DIR) / "reports"
        output_dir = reports_root / datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir.mkdir(parents=True, exist_ok=True)

        # URL paths for frontend access
        url_base = f"/static/reports/{output_dir.name}"
        mkdocs_index_url = f"{url_base}/mkdocs/site/index.html"

        # Create execution record
        execution = TestExecution(
            project_id=project_id,
            log_file=f"{url_base}/log.html",
            report_file=f"{url_base}/report.html",
            output_file=f"{url_base}/output.xml",
            status="running",
            created_at=datetime.utcnow(),
        )

        # Ensure Browser deps installed
        self._ensure_rfbrowser()

        # Execute Robot Framework tests
        try:
            result = subprocess.run(
                [
                    "robot",
                    "--outputdir", str(output_dir),
                    "--log", "log.html",
                    "--report", "report.html",
                    "--output", "output.xml",
                    str(test_dir),
                ],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes timeout
            )

            # Parse output.xml to get statistics
            stats = self._parse_robot_output(output_dir / "output.xml")
            execution.total_tests = stats["total"]
            execution.passed = stats["passed"]
            execution.failed = stats["failed"]
            execution.skipped = stats["skipped"]
            execution.status = "completed" if result.returncode == 0 else "failed"
            if result.returncode != 0:
                execution.error_output = (result.stderr or result.stdout or "").strip() or "Test execution failed"
            execution.completed_at = datetime.utcnow()

            # Ensure report files exist even on failure
            self._ensure_report_files(output_dir, execution.error_output)

            # Generate MkDocs documentation
            await self._generate_mkdocs_report(project, output_dir, stats)
            execution.mkdocs_index = mkdocs_index_url

        except subprocess.TimeoutExpired:
            execution.status = "failed"
            execution.error_output = "Test execution timed out"
            execution.completed_at = datetime.utcnow()
            self._ensure_report_files(output_dir, execution.error_output)
            logger.error("Test execution timed out")
        except Exception as e:
            execution.status = "failed"
            execution.error_output = str(e)
            execution.completed_at = datetime.utcnow()
            self._ensure_report_files(output_dir, execution.error_output)
            logger.error(f"Test execution failed: {e}")

        # Save execution record to database (you'll need to create a repository for this)
        # For now, just return the execution object
        return execution

    def _ensure_rfbrowser(self) -> None:
        """Install Browser dependencies if missing."""
        try:
            wrapper_path = Path(__file__).resolve().parent.parent.parent / ".venv"
        except Exception:
            wrapper_path = None

        # If rfbrowser is available, run init to ensure deps
        try:
            subprocess.run(["rfbrowser", "init"], capture_output=True, text=True, timeout=120)
        except Exception as exc:
            logger.warning(f"rfbrowser init failed or not available: {exc}")

    def _ensure_report_files(self, output_dir: Path, error_output: str | None) -> None:
        """Create fallback report/log/output files if Robot didn't generate them."""
        log_file = output_dir / "log.html"
        report_file = output_dir / "report.html"
        output_file = output_dir / "output.xml"

        if not output_file.exists():
            output_file.write_text("<robot></robot>", encoding="utf-8")

        if not log_file.exists():
            log_file.write_text(
                self._error_html("Robot Log", error_output),
                encoding="utf-8",
            )

        if not report_file.exists():
            report_file.write_text(
                self._error_html("Robot Report", error_output),
                encoding="utf-8",
            )

    def _error_html(self, title: str, error_output: str | None) -> str:
        message = error_output or "No report generated."
        return (
            f"<html><head><title>{title}</title></head><body>"
            f"<h1>{title}</h1><pre>{message}</pre></body></html>"
        )

    def _parse_robot_output(self, output_file: Path) -> dict:
        """Parse Robot Framework output.xml to extract statistics."""
        import xml.etree.ElementTree as ET

        if not output_file.exists():
            return {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        try:
            tree = ET.parse(output_file)
            root = tree.getroot()
            
            # Find statistics element
            stats_elem = root.find(".//statistics/total/stat")
            if stats_elem is not None:
                return {
                    "total": int(stats_elem.get("pass", 0)) + int(stats_elem.get("fail", 0)),
                    "passed": int(stats_elem.get("pass", 0)),
                    "failed": int(stats_elem.get("fail", 0)),
                    "skipped": int(stats_elem.get("skip", 0)),
                }
        except Exception as e:
            logger.error(f"Failed to parse output.xml: {e}")

        return {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

    async def _generate_mkdocs_report(self, project, output_dir: Path, stats: dict) -> None:
        """Generate MkDocs documentation for test results."""
        docs_dir = output_dir / "mkdocs"
        docs_dir.mkdir(exist_ok=True)

        # Create docs/index.md
        docs_content_dir = docs_dir / "docs"
        docs_content_dir.mkdir(exist_ok=True)

        # Generate index.md
        index_content = f"""# Test Execution Report

## Project: {project.name}

{project.description or ''}

## Test Results

- **Total Tests**: {stats['total']}
- **Passed**: {stats['passed']} ✅
- **Failed**: {stats['failed']} ❌
- **Skipped**: {stats['skipped']} ⏭️

## Success Rate

{(stats['passed'] / stats['total'] * 100) if stats['total'] > 0 else 0:.2f}%

## Detailed Reports

- [HTML Report](../../report.html)
- [Log File](../../log.html)
- [XML Output](../../output.xml)

## Execution Time

Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        (docs_content_dir / "index.md").write_text(index_content)

        # Create mkdocs.yml
        mkdocs_config = f"""site_name: '{project.name} - Test Report'
theme:
  name: material
  palette:
    primary: indigo
    accent: indigo
  features:
    - navigation.instant
    - navigation.sections

docs_dir: docs
site_dir: site

nav:
  - Home: index.md
"""

        (docs_dir / "mkdocs.yml").write_text(mkdocs_config)

        # Build MkDocs site
        try:
            subprocess.run(
                ["mkdocs", "build"],
                cwd=str(docs_dir),
                capture_output=True,
                timeout=60,
            )
            logger.info(f"MkDocs documentation generated at {docs_dir / 'site'}")
        except Exception as e:
            logger.error(f"Failed to generate MkDocs documentation: {e}")
