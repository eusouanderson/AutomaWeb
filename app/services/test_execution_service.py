"""Service for executing Robot Framework tests and generating reports"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_validation.self_healing_service import AITestSelfHealingService
from app.core.config import settings
from app.models.test_execution import TestExecution
from app.repositories.project_repository import ProjectRepository
from app.repositories.test_repository import TestRepository

logger = logging.getLogger(__name__)


class TestExecutionService:
    """Service for executing tests and generating reports."""

    _running_projects: set[int] = set()
    _rfbrowser_ready = False
    _rfbrowser_lock_file = Path(tempfile.gettempdir()) / "automaweb-rfbrowser-init.lock"

    def __init__(
        self,
        project_repository: ProjectRepository | None = None,
        test_repository: TestRepository | None = None,
    ) -> None:
        self._project_repository = project_repository or ProjectRepository()
        self._test_repository = test_repository or TestRepository()
        self._self_healing = AITestSelfHealingService()

    async def execute_tests(
        self,
        session: AsyncSession,
        project_id: int,
        test_ids: list[int] | None = None,
        ai_debug: bool = False,
        headless: bool = True,
        timeout_seconds: int = 300,
        speed_ms: int = 0,
        skip_heal: bool = False,
        parallel_workers: int = 4,
    ) -> TestExecution:
        """Execute Robot Framework tests for a project."""

        if project_id in self.__class__._running_projects:
            raise ValueError(f"Tests are already running for project {project_id}")

        # DB guard — works across restarts and multiple workers
        if session is not None and hasattr(session, "execute"):
            from sqlalchemy import select as _sa_select

            _existing = await session.execute(
                _sa_select(TestExecution).where(
                    TestExecution.project_id == project_id,
                    TestExecution.status == "running",
                )
            )
            if _existing.scalars().first():
                raise ValueError(
                    f"Project {project_id} already has a running execution. Wait for it to finish."
                )

        self.__class__._running_projects.add(project_id)
        temp_dir: Path | None = None
        try:
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
            base_dir = (
                Path(project.test_directory)
                if project.test_directory
                else Path(settings.STATIC_DIR) / "projects"
            )
            project_dir = base_dir / safe_name

            if test_ids:
                selected_tests = (
                    await self._test_repository.list_generated_tests_by_ids_for_project(
                        session=session,
                        project_id=project_id,
                        test_ids=test_ids,
                    )
                )
                test_files = [test.file_path for test in selected_tests]
            else:
                # Get all .robot files from project folder
                test_files = (
                    [str(path) for path in project_dir.glob("*.robot")]
                    if project_dir.exists()
                    else []
                )

            if not test_files:
                raise ValueError(f"No test files found in {project_dir}")

            if settings.AI_VALIDATION_ENABLED and not skip_heal:
                test_files = await self._apply_pre_execution_healing(
                    test_files=test_files,
                    page_url=str(project.url) if project.url else None,
                    ai_debug=ai_debug,
                )

            run_id = f"{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Store execution artifacts inside project folder
            project_reports_root = project_dir / "reports"
            output_dir = project_reports_root / run_id
            output_dir.mkdir(parents=True, exist_ok=True)

            # Public mirror for frontend access
            public_reports_root = Path(settings.STATIC_DIR) / "reports"
            public_output_dir = public_reports_root / run_id

            # URL paths for frontend access
            url_base = f"/static/reports/{run_id}"
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

            # Prepare temp copies with headless variable injected
            prepared_files, temp_dir = self._prepare_test_files(
                test_files, headless, speed_ms
            )
            headless_var = "True" if headless else "False"
            command = self._build_robot_command(
                output_dir=output_dir,
                headless_var=headless_var,
                speed_ms=speed_ms,
                prepared_files=prepared_files,
                parallel_workers=parallel_workers,
            )

            # Execute Robot Framework tests
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=int(timeout_seconds),
            )

            # One-time self-heal when Playwright executable is missing.
            if result.returncode != 0:
                robot_output = f"{result.stderr or ''}\n{result.stdout or ''}"
                if self._is_missing_playwright_executable_error(robot_output):
                    logger.warning(
                        "Robot failed due to missing Playwright executable; attempting one-time repair"
                    )
                    await asyncio.to_thread(self._ensure_rfbrowser)
                    result = await asyncio.to_thread(
                        subprocess.run,
                        command,
                        capture_output=True,
                        text=True,
                        stdin=subprocess.DEVNULL,
                        timeout=int(timeout_seconds),
                    )

            # Parse output.xml to get statistics
            stats = self._parse_robot_output(output_dir / "output.xml")
            execution.total_tests = stats["total"]
            execution.passed = stats["passed"]
            execution.failed = stats["failed"]
            execution.skipped = stats["skipped"]
            execution.test_cases = stats.get("test_cases", [])
            execution.status = "completed" if result.returncode == 0 else "failed"
            if result.returncode != 0:
                execution.error_output = (
                    result.stderr or result.stdout or ""
                ).strip() or "Test execution failed"
            execution.completed_at = datetime.utcnow()

            # Ensure report files exist even on failure
            self._ensure_report_files(output_dir, execution.error_output)

            # Generate MkDocs documentation in background — does not block execution result
            asyncio.create_task(self._generate_mkdocs_report(project, output_dir, stats))
            asyncio.create_task(asyncio.to_thread(self._sync_reports_for_static, output_dir, public_output_dir))
            execution.mkdocs_index = mkdocs_index_url

        except subprocess.TimeoutExpired:
            execution.status = "failed"
            execution.error_output = "Test execution timed out"
            execution.completed_at = datetime.utcnow()
            self._ensure_report_files(output_dir, execution.error_output)
            self._sync_reports_for_static(output_dir, public_output_dir)
            logger.error("Test execution timed out")
        except ValueError:
            raise
        except Exception as e:
            execution.status = "failed"
            execution.error_output = str(e)
            execution.completed_at = datetime.utcnow()
            self._ensure_report_files(output_dir, execution.error_output)
            self._sync_reports_for_static(output_dir, public_output_dir)
            logger.error(f"Test execution failed: {e}")
        finally:
            # Always release the project lock and clean up temp files
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
            self.__class__._running_projects.discard(project_id)

        # Persist execution record to database
        if session is not None:
            session.add(execution)
            await session.commit()
            await session.refresh(execution)
        print("Execution completed", execution)
        return execution

    async def list_executions_by_project(
        self,
        session: AsyncSession,
        project_id: int,
    ) -> list[TestExecution]:
        """Return all executions for a project, newest first."""
        from sqlalchemy import select

        result = await session.execute(
            select(TestExecution)
            .where(TestExecution.project_id == project_id)
            .order_by(TestExecution.created_at.desc())
        )
        return list(result.scalars().all())

    # Detects embedded HTTP Basic Auth credentials in URLs: https://user:pass@host
    _BASIC_AUTH_URL_RE = re.compile(r"https?://([^:/@\s]+):([^@/\s]+)@")

    def _inject_basic_auth_credentials(self, content: str) -> str:
        """If the robot file has URLs with embedded credentials (https://user:pass@host),
        inject httpCredentials into New Context so visible-mode runs don't trigger the
        native auth dialog that Playwright cannot dismiss."""
        match = self._BASIC_AUTH_URL_RE.search(content)
        if not match:
            return content

        username, password = match.group(1), match.group(2)

        # Skip if New Context already has httpCredentials
        if re.search(r"New Context\s+httpCredentials", content):
            return content

        # Variable block to add to the Variables section
        var_block = (
            f"${{__AW_HTTP_USER}}    {username}\n"
            f"${{__AW_HTTP_PASS}}    {password}\n"
            f"&{{__AW_HTTP_CREDS}}    username=$__AW_HTTP_USER    password=$__AW_HTTP_PASS\n"
        )

        if "*** Variables ***" in content:
            content = content.replace("*** Variables ***\n", f"*** Variables ***\n{var_block}", 1)
        else:
            content = content.replace(
                "*** Test Cases ***",
                f"*** Variables ***\n{var_block}\n*** Test Cases ***",
                1,
            )

        # Replace bare `New Context` (no existing httpCredentials) with injected version
        content = re.sub(
            r"([ \t]+New Context)(?!\s+http)(\s*\n)",
            r"\1    httpCredentials=${__AW_HTTP_CREDS}\2",
            content,
        )
        return content

    def _prepare_test_files(
        self, test_files: list[str], headless: bool, speed_ms: int
    ) -> tuple[list[str], Path]:
        """Copy test files to a temp dir, injecting headless=${HEADLESS} in every New Browser call.
        Also injects httpCredentials into New Context when URLs contain embedded credentials."""
        temp_dir = Path(tempfile.mkdtemp(prefix="robot_run_"))
        prepared: list[str] = []
        for fp in test_files:
            src = Path(fp)
            content = src.read_text(encoding="utf-8")
            # Add headless=${HEADLESS} and slowMo=${SPEED_MS}ms to New Browser when missing.
            content = re.sub(
                r"(New Browser\s+\S+)(?![^\n]*headless=)",
                r"\1    headless=${HEADLESS}",
                content,
            )
            content = re.sub(
                r"(New Browser\s+\S+)(?![^\n]*slowMo=)",
                r"\1    slowMo=${SPEED_MS}ms",
                content,
            )
            content = self._harden_runtime_locators(content)
            # Inject httpCredentials when URLs contain embedded user:pass@host
            content = self._inject_basic_auth_credentials(content)
            dst = temp_dir / src.name
            dst.write_text(content, encoding="utf-8")
            prepared.append(str(dst))
        return prepared, temp_dir

    def _harden_runtime_locators(self, content: str) -> str:
        """Apply lightweight deterministic hardening to reduce strict-mode flakes.

        This runs even when skip_heal=True and does not call any AI service.
        """
        selector_keywords = {
            "Click",
            "Click Element",
            "Wait For Elements State",
            "Wait Until Element Is Visible",
            "Wait Until Page Contains Element",
            "Get Element",
            "Get Elements",
            "Input Text",
            "Fill Text",
            "Type Text",
        }

        hardened: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("***"):
                hardened.append(line)
                continue

            indent = line[: len(line) - len(line.lstrip())]
            parts = re.split(r"\s{2,}", stripped)
            keyword = parts[0] if parts else ""

            if keyword in selector_keywords and len(parts) >= 2:
                selector = parts[1]
                if (
                    ">> nth=" not in selector
                    and not selector.startswith("text=")
                    and not selector.startswith("role=")
                    and (
                        selector.startswith("css=")
                        or selector.startswith("xpath=")
                        or selector.startswith("#")
                        or selector.startswith(".")
                        or selector.startswith("[")
                    )
                ):
                    if selector.startswith("#") or selector.startswith(".") or selector.startswith("["):
                        selector = f"css={selector}"
                    selector = f"{selector} >> nth=0"
                    parts[1] = selector

                # Cookie consent / GDPR banners are position:fixed but outside the
                # viewport in headless mode. Use JS click fallback instead of
                # actionability-dependent native click.
                if keyword == "Click" and re.search(
                    r"(cookie|consent|accept|hs-eu|onetrust|gdpr|lgpd|cookielaw|"
                    r"cc-accept|accept-all|cookie-btn|cookie-ok|cookie-agree)",
                    parts[1],
                    re.IGNORECASE,
                ):
                    css_query = parts[1]
                    if css_query.startswith("css="):
                        css_query = css_query[4:]
                    elif not css_query.startswith(("#", ".", "[")):
                        css_query = ""

                    if css_query:
                        hardened.append(
                            f'{indent}Evaluate JavaScript    ${{None}}    () => {{ const b = document.querySelector("{css_query}"); if (b) b.click(); }}'
                        )
                        continue

                hardened.append(f"{indent}{'    '.join(parts)}")
                continue

            if keyword == "New Page" and len(parts) >= 2 and not any(
                p.startswith("wait_until=") for p in parts[2:]
            ):
                parts.append("wait_until=domcontentloaded")
                hardened.append(f"{indent}{'    '.join(parts)}")
                continue

            hardened.append(line)

        return "\n".join(hardened) + "\n"

    async def _apply_pre_execution_healing(
        self,
        test_files: list[str],
        page_url: str | None,
        ai_debug: bool,
    ) -> list[str]:
        """Validate and heal generated .robot files before execution (parallel)."""
        existing = [Path(fp) for fp in test_files if Path(fp).exists()]
        if not existing:
            return []

        async def _heal_one(path: Path) -> str:
            content = path.read_text(encoding="utf-8")
            healed = await self._self_healing.heal_test(
                content=content,
                page_url=page_url,
                ai_debug=ai_debug,
            )
            if healed.final_content != content:
                path.write_text(healed.final_content, encoding="utf-8")
            return str(path)

        healed_files = await asyncio.gather(*(_heal_one(p) for p in existing))
        return list(healed_files)

    def _ensure_rfbrowser(self) -> None:
        """Install Browser dependencies if missing."""
        if self.__class__._rfbrowser_ready:
            self._ensure_playwright_package_compat()
            if self._has_chromium_headless_shell():
                return
            logger.warning("rfbrowser marked ready but chromium_headless_shell is missing; repairing")

        wrapper_root = self._browser_wrapper_root()
        rfbrowser_bin = Path(sys.prefix) / "bin" / "rfbrowser"
        rfbrowser_cmd = str(rfbrowser_bin) if rfbrowser_bin.exists() else "rfbrowser"

        # Fast path: if wrapper already has chromium_headless_shell, we're ready.
        if self._has_chromium_headless_shell():
            self.__class__._rfbrowser_ready = True
            self._ensure_playwright_package_compat()
            logger.info("Playwright wrapper already has chromium_headless_shell")
            return

        # Try to install missing shell directly in wrapper first.
        try:
            if wrapper_root.exists():
                logger.warning("Wrapper missing chromium_headless_shell; installing in wrapper")
                repair = subprocess.run(
                    ["npx", "playwright", "install", "chromium", "chromium-headless-shell"],
                    cwd=str(wrapper_root),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if repair.returncode == 0 and self._has_chromium_headless_shell():
                    self.__class__._rfbrowser_ready = True
                    self._ensure_playwright_package_compat()
                    logger.info("Installed chromium_headless_shell in Browser wrapper")
                    return
        except Exception:
            pass

        # In multi-worker mode (e.g. start.py workers=4), prevent concurrent init.
        lock_fd = None
        try:
            import fcntl

            lock_fd = os.open(str(self.__class__._rfbrowser_lock_file), os.O_CREAT | os.O_RDWR)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                logger.info("Another worker is warming rfbrowser; skipping duplicate init")
                return
        except Exception:
            # If lock is unavailable, continue best-effort init.
            lock_fd = None

        # Slow path: run full rfbrowser init (downloads browsers if needed)
        # Retry once on transient failure (e.g. npm network timeout)
        try:
            for attempt in range(2):
                try:
                    result = subprocess.run(
                        [rfbrowser_cmd, "init"], capture_output=True, text=True, timeout=180
                    )
                    if result.returncode == 0:
                        self.__class__._rfbrowser_ready = True
                        self._ensure_playwright_package_compat()
                        logger.info("rfbrowser init completed successfully")
                        return

                    stderr = (result.stderr or "").strip()
                    summary = stderr.splitlines()[-1] if stderr else "unknown error"
                    logger.warning(
                        "rfbrowser init attempt %s failed: %s",
                        attempt + 1,
                        summary,
                    )
                except Exception as exc:
                    logger.warning(f"rfbrowser init attempt {attempt + 1} exception: {exc}")
            logger.error("rfbrowser init failed after 2 attempts — robot tests may fail")
        finally:
            if lock_fd is not None:
                try:
                    import fcntl

                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except Exception:
                    pass
                os.close(lock_fd)

    def _ensure_playwright_package_compat(self) -> None:
        """Ensure playwright-core/lib/package.json exists for Browser wrapper runtime.

        Some wrapper distributions resolve "./../../../package.json" from
        lib/server/utils/userAgent.js, which points to lib/package.json.
        """
        try:
            wrapper_root = Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" / "Browser" / "wrapper"
            root_pkg = wrapper_root / "node_modules" / "playwright-core" / "package.json"
            lib_pkg = wrapper_root / "node_modules" / "playwright-core" / "lib" / "package.json"

            if lib_pkg.exists() or not root_pkg.exists():
                return

            data = json.loads(root_pkg.read_text(encoding="utf-8"))
            lib_pkg.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
            logger.info("Created playwright-core compatibility file at lib/package.json")
        except Exception as exc:
            logger.warning("Could not create playwright-core compatibility file: %s", exc)

    def _browser_wrapper_root(self) -> Path:
        return (
            Path(sys.prefix)
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages"
            / "Browser"
            / "wrapper"
        )

    def _has_chromium_headless_shell(self) -> bool:
        wrapper_root = self._browser_wrapper_root()
        base = wrapper_root / "node_modules" / "playwright-core" / ".local-browsers"
        if not base.exists():
            return False

        for shell_bin in base.glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"):
            if shell_bin.exists():
                return True
        return False

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

    def _sync_reports_for_static(self, source_dir: Path, target_dir: Path) -> None:
        """Mirror project report files to STATIC_DIR for browser access."""
        try:
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(source_dir, target_dir)
        except Exception as exc:
            logger.error("Failed to mirror reports to static dir: %s", exc)

    def _error_html(self, title: str, error_output: str | None) -> str:
        message = error_output or "No report generated."
        return (
            f"<html><head><title>{title}</title></head><body>"
            f"<h1>{title}</h1><pre>{message}</pre></body></html>"
        )

    def _is_missing_playwright_executable_error(self, output: str) -> bool:
        text = (output or "").lower()
        return "executable doesn't exist" in text and "playwright" in text

    def _resolve_pabot_command(self) -> str | None:
        pabot_bin = Path(sys.prefix) / "bin" / "pabot"
        if pabot_bin.exists():
            return str(pabot_bin)
        return shutil.which("pabot")

    def _build_robot_command(
        self,
        output_dir: Path,
        headless_var: str,
        speed_ms: int,
        prepared_files: list[str],
        parallel_workers: int,
    ) -> list[str]:
        base_args = [
            "--outputdir",
            str(output_dir),
            "--log",
            "log.html",
            "--report",
            "report.html",
            "--output",
            "output.xml",
            "--variable",
            f"HEADLESS:{headless_var}",
            "--variable",
            f"SPEED_MS:{int(speed_ms)}",
            *prepared_files,
        ]

        workers = max(1, int(parallel_workers or 1))
        if workers > 1 and len(prepared_files) > 1:
            pabot_cmd = self._resolve_pabot_command()
            if pabot_cmd:
                # No benefit in using more workers than files.
                workers = min(workers, len(prepared_files))
                return [pabot_cmd, "--processes", str(workers), "--testlevelsplit", *base_args]
            logger.warning("parallel_workers requested, but pabot is not installed; falling back to robot")

        return ["robot", *base_args]

    def _parse_robot_output(self, output_file: Path) -> dict:
        """Parse Robot Framework output.xml to extract statistics and per-test results."""
        import xml.etree.ElementTree as ET

        empty = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "test_cases": []}
        if not output_file.exists():
            return empty

        try:
            tree = ET.parse(output_file)
            root = tree.getroot()

            stats = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

            # Aggregate statistics from the toplevel stat element
            stats_elem = root.find(".//statistics/total/stat")
            if stats_elem is not None:
                stats["passed"] = int(stats_elem.get("pass", 0))
                stats["failed"] = int(stats_elem.get("fail", 0))
                stats["skipped"] = int(stats_elem.get("skip", 0))
                stats["total"] = stats["passed"] + stats["failed"] + stats["skipped"]

            # Extract individual test case results
            test_cases = []
            for test_elem in root.iter("test"):
                status_elem = test_elem.find("status")
                if status_elem is not None:
                    msg = (status_elem.text or "").strip() or None
                    test_cases.append(
                        {
                            "name": test_elem.get("name", "Unknown"),
                            "status": status_elem.get("status", "UNKNOWN"),
                            "message": msg,
                        }
                    )

            stats["test_cases"] = test_cases  # type: ignore
            return stats
        except Exception as e:
            logger.error(f"Failed to parse output.xml: {e}")

        return empty

    async def _generate_mkdocs_report(
        self, project, output_dir: Path, stats: dict
    ) -> None:
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
            await asyncio.to_thread(
                subprocess.run,
                ["mkdocs", "build"],
                cwd=str(docs_dir),
                capture_output=True,
                timeout=60,
            )
            logger.info(f"MkDocs documentation generated at {docs_dir / 'site'}")
        except Exception as e:
            logger.error(f"Failed to generate MkDocs documentation: {e}")
