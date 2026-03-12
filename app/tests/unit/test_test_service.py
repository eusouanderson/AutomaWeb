import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tenacity import RetryError

from app.core.config import settings
from app.db.base import Base
from app.models.project import Project
from app.models.test_execution import TestExecution  # noqa: F401 — registers mapper
from app.services.element_scanner import ElementScannerError
from app.services.test_service import LLMServiceUnavailableError, ScanUnavailableError, TestService


class DummyGroqClient:
    def generate_robot_test(
        self,
        prompt: str,
        context: str | None = None,
        page_structure: dict | None = None,
    ) -> str:
        return "*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nExample\n    Log    Hello"


class FailingScanService:
    async def scan_url(self, _url: str):
        raise ElementScannerError("scan is down")


class ScanResultMock:
    def model_dump(self):
        return {"title": "Page"}


class SuccessfulScanService:
    async def scan_url(self, _url: str):
        return ScanResultMock()


class DummyProjectRepository:
    def __init__(self, project):
        self.project = project

    async def get(self, session, project_id):
        return self.project


class DummyTestRepository:
    def __init__(self):
        self.updated_statuses = []
        self.generated_to_return = None
        self.deleted_item = None

    async def create_test_request(self, session, test_request):
        test_request.id = 42
        return test_request

    async def update_test_request(self, session, test_request):
        self.updated_statuses.append(test_request.status)
        return test_request

    async def create_generated_test(self, session, generated_test):
        generated_test.id = 99
        return generated_test

    async def get_generated_test(self, session, test_id):
        return self.generated_to_return

    async def get_test_request(self, session, test_request_id):
        from app.models.test_request import TestRequest
        tr = TestRequest(id=test_request_id, project_id=1, prompt="p", status="completed")
        tr.id = test_request_id
        return tr

    async def delete_generated_test(self, session, generated):
        self.deleted_item = generated

    async def list_generated_tests_by_project(self, session, project_id):
        return ["dummy"]


class DummyRetryError(RetryError):
    def __init__(self):
        Exception.__init__(self, "retry exhausted")


class RetryFailingGroqClient:
    def generate_robot_test(self, prompt, context=None, page_structure=None):
        raise DummyRetryError()


class APIConnectionError(Exception):
    pass


class APIConnectionFailingGroqClient:
    def generate_robot_test(self, prompt, context=None, page_structure=None):
        raise APIConnectionError("network")


class UnexpectedLLMError(Exception):
    pass


class UnexpectedFailingGroqClient:
    def generate_robot_test(self, prompt, context=None, page_structure=None):
        raise UnexpectedLLMError("unexpected")


class CapturingGroqClient:
    def __init__(self):
        self.captured_page_structure = None

    def generate_robot_test(self, prompt, context=None, page_structure=None):
        self.captured_page_structure = page_structure
        return "*** Test Cases ***\nExample\n    Log    OK"


@pytest_asyncio.fixture()
async def session(tmp_path) -> AsyncSession:
    settings.STATIC_DIR = str(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.mark.asyncio
async def test_generate_test(session: AsyncSession) -> None:
    project = Project(name="Projeto Teste", description="Desc")
    session.add(project)
    await session.commit()
    await session.refresh(project)

    service = TestService(groq_client=DummyGroqClient())
    generated = await service.generate_test(
        session=session,
        project_id=project.id,
        prompt="Gerar teste",
        context="Contexto",
    )

    assert generated.id is not None
    assert "*** Test Cases ***" in generated.content


@pytest.mark.asyncio
async def test_generate_test_raises_when_project_not_found() -> None:
    service = TestService(
        test_repository=DummyTestRepository(),
        project_repository=DummyProjectRepository(None),
        groq_client=DummyGroqClient(),
    )

    with pytest.raises(ValueError, match="Project not found"):
        await service.generate_test(session=None, project_id=999, prompt="Gerar teste")


@pytest.mark.asyncio
async def test_generate_test_raises_scan_unavailable_when_scan_fails(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url="https://example.com")
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(project),
        groq_client=DummyGroqClient(),
        element_scanner=FailingScanService(),
    )

    with pytest.raises(ScanUnavailableError, match="scan is down"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste")

    assert test_repo.updated_statuses[-1] == "failed"


@pytest.mark.asyncio
async def test_generate_test_raises_llm_unavailable_on_retry_error(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url=None)
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(project),
        groq_client=RetryFailingGroqClient(),
        element_scanner=SuccessfulScanService(),
    )

    with pytest.raises(LLMServiceUnavailableError, match="LLM provider connection failed"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste")

    assert test_repo.updated_statuses[-1] == "failed"


@pytest.mark.asyncio
async def test_generate_test_raises_llm_unavailable_on_api_connection_error(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url=None)
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(project),
        groq_client=APIConnectionFailingGroqClient(),
        element_scanner=SuccessfulScanService(),
    )

    with pytest.raises(LLMServiceUnavailableError, match="LLM provider connection failed"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste")

    assert test_repo.updated_statuses[-1] == "failed"


@pytest.mark.asyncio
async def test_generate_test_uses_scanned_page_structure(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url="https://example.com")
    test_repo = DummyTestRepository()
    groq_client = CapturingGroqClient()
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(project),
        groq_client=groq_client,
        element_scanner=SuccessfulScanService(),
    )

    class _Session:
        async def flush(self): pass

    generated = await service.generate_test(session=_Session(), project_id=1, prompt="Gerar teste")

    assert generated.id == 99
    assert groq_client.captured_page_structure == {"title": "Page"}


@pytest.mark.asyncio
async def test_generate_test_reraises_unexpected_llm_exception(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url=None)
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(project),
        groq_client=UnexpectedFailingGroqClient(),
        element_scanner=SuccessfulScanService(),
    )

    with pytest.raises(UnexpectedLLMError, match="unexpected"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste")


@pytest.mark.asyncio
async def test_list_generated_tests_by_project_success() -> None:
    project = Project(id=1, name="Projeto", description="Desc")
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(project),
        groq_client=DummyGroqClient(),
    )

    items = await service.list_generated_tests_by_project(session=None, project_id=1)

    assert items == ["dummy"]


@pytest.mark.asyncio
async def test_get_generated_test_passthrough() -> None:
    generated = type("Generated", (), {"id": 7})()
    test_repo = DummyTestRepository()
    test_repo.generated_to_return = generated
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(None),
        groq_client=DummyGroqClient(),
    )

    found = await service.get_generated_test(session=None, test_id=7)

    assert found is generated


@pytest.mark.asyncio
async def test_list_generated_tests_by_project_raises_when_project_not_found() -> None:
    service = TestService(
        test_repository=DummyTestRepository(),
        project_repository=DummyProjectRepository(None),
        groq_client=DummyGroqClient(),
    )

    with pytest.raises(ValueError, match="Project not found"):
        await service.list_generated_tests_by_project(session=None, project_id=1)


@pytest.mark.asyncio
async def test_delete_generated_test_returns_false_when_not_found() -> None:
    test_repo = DummyTestRepository()
    service = TestService(test_repository=test_repo, project_repository=DummyProjectRepository(None), groq_client=DummyGroqClient())

    deleted = await service.delete_generated_test(session=None, test_id=1)

    assert deleted is False


@pytest.mark.asyncio
async def test_delete_generated_test_handles_unlink_error(tmp_path, monkeypatch) -> None:
    file_path = tmp_path / "generated_test_1.robot"
    file_path.write_text("*** Test Cases ***\nExample")
    generated = type("Generated", (), {"file_path": str(file_path)})()

    test_repo = DummyTestRepository()
    test_repo.generated_to_return = generated
    service = TestService(test_repository=test_repo, project_repository=DummyProjectRepository(None), groq_client=DummyGroqClient())

    def failing_unlink(self):
        raise OSError("cannot unlink")

    monkeypatch.setattr("pathlib.Path.unlink", failing_unlink)

    deleted = await service.delete_generated_test(session=None, test_id=1)

    assert deleted is True
    assert test_repo.deleted_item is generated


def test_sanitize_robot_output_filters_noise_and_normalizes_library() -> None:
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "texto fora\n"
        "*** Settings ***\n"
        "Library    PlaywrightLibrary\n"
        "** nota\n"
        "Observação: remover\n"
        "*** Test Cases ***\n"
        "Caso\n"
        "    Log    Playwright\n"
    )

    cleaned = service._sanitize_robot_output(content)

    assert "PlaywrightLibrary" not in cleaned
    assert "Library    Browser" in cleaned
    assert "Observação" not in cleaned
    assert "** nota" not in cleaned


def test_sanitize_robot_output_hardens_strict_mode_selector_from_context() -> None:
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "*** Settings ***\n"
        "Library    Browser\n"
        "*** Test Cases ***\n"
        "Caso\n"
        "    Wait For Elements State    css=.card-title    visible    10\n"
        "    Click    css=.card-title\n"
    )
    context = "strict mode violation: locator('.card-title') resolved to 9 elements"

    cleaned = service._sanitize_robot_output(content, context=context)

    assert "css=.card-title >> nth=0" in cleaned


def test_sanitize_robot_output_converts_open_browser_and_invalid_selector_prefixes() -> None:
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "*** Settings ***\n"
        "Library    Browser\n"
        "*** Test Cases ***\n"
        "Caso\n"
        "    Open Browser    https://example.com    browser=chrome\n"
        "    Click    id:login\n"
        "    Wait For Elements State    xpath://button[@type='submit']    visible    10\n"
    )

    cleaned = service._sanitize_robot_output(content)

    assert "New Browser    chromium" in cleaned
    assert "New Context" in cleaned
    assert "New Page    https://example.com" in cleaned
    assert "Click    css=#login" in cleaned
    assert "Wait For Elements State    xpath=//button[@type='submit']" in cleaned


def test_sanitize_robot_output_applies_strict_mode_on_non_class_selector() -> None:
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "*** Settings ***\n"
        "Library    Browser\n"
        "*** Test Cases ***\n"
        "Caso\n"
        "    Click    css=#login\n"
    )
    context = "strict mode violation: locator('#login') resolved to 2 elements"

    cleaned = service._sanitize_robot_output(content, context=context)

    assert "Click    css=#login >> nth=0" in cleaned


def test_sanitize_robot_output_applies_strict_mode_on_raw_id_selector() -> None:
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "*** Settings ***\n"
        "Library    Browser\n"
        "*** Test Cases ***\n"
        "Caso\n"
        "    Wait For Elements State    #logo    visible    10\n"
    )
    context = "strict mode violation: locator('#logo') resolved to 3 elements"

    cleaned = service._sanitize_robot_output(content, context=context)

    assert "Wait For Elements State    css=#logo >> nth=0    visible    10" in cleaned


def test_sanitize_robot_output_applies_strict_mode_on_raw_attribute_selector() -> None:
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "*** Settings ***\n"
        "Library    Browser\n"
        "*** Test Cases ***\n"
        "Caso\n"
        "    Click    [aria-label=\"Guia\"]\n"
    )
    context = "strict mode violation: locator('[aria-label=\"Guia\"]') resolved to 2 elements"

    cleaned = service._sanitize_robot_output(content, context=context)

    assert "Click    css=[aria-label=\"Guia\"] >> nth=0" in cleaned


def test_normalize_selector_covers_css_and_dot_prefixes() -> None:
    service = TestService(groq_client=DummyGroqClient())

    assert service._normalize_selector("css:.btn-primary") == "css=.btn-primary"
    assert service._normalize_selector(".card-title") == "css=.card-title"


def test_make_selector_unique_covers_already_unique_and_non_css() -> None:
    service = TestService(groq_client=DummyGroqClient())

    assert service._make_selector_unique("css=.card-title >> nth=0") == "css=.card-title >> nth=0"
    assert service._make_selector_unique("xpath=//button") == "xpath=//button"


def test_sanitize_injects_set_browser_timeout_after_new_context() -> None:
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "*** Settings ***\n"
        "Library    Browser\n"
        "*** Test Cases ***\n"
        "Caso\n"
        "    New Browser    chromium\n"
        "    New Context\n"
        "    New Page    https://example.com\n"
    )
    cleaned = service._sanitize_robot_output(content)
    lines = cleaned.splitlines()
    ctx_idx = next(i for i, l in enumerate(lines) if l.strip() == "New Context")
    assert "Set Browser Timeout    30s" in lines[ctx_idx + 1]


def test_sanitize_removes_useless_wait_before_get_title() -> None:
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "*** Settings ***\n"
        "Library    Browser\n"
        "*** Test Cases ***\n"
        "Testar Título\n"
        "    New Browser    chromium\n"
        "    New Context\n"
        "    New Page    https://example.com\n"
        "    Wait For Elements State    css=h1    visible    10\n"
        "    ${titulo_atual}    Get Title\n"
        "    Should Be Equal    ${titulo_atual}    Example Domain\n"
    )
    cleaned = service._sanitize_robot_output(content)
    assert "Wait For Elements State    css=h1" not in cleaned
    assert "Get Title" in cleaned
    assert "Should Be Equal" in cleaned


def test_sanitize_converts_open_browser_and_injects_timeout() -> None:
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "*** Settings ***\n"
        "Library    Browser\n"
        "*** Test Cases ***\n"
        "Caso\n"
        "    Open Browser    https://example.com    browser=chrome\n"
    )
    cleaned = service._sanitize_robot_output(content)
    assert "New Browser" in cleaned
    assert "New Context" in cleaned
    assert "Set Browser Timeout    30s" in cleaned
    assert "New Page    https://example.com" in cleaned
    assert "Open Browser" not in cleaned


# ---------------------------------------------------------------------------
# _sanitize_robot_output – line 276 (blank line between Wait and Get Title)
# ---------------------------------------------------------------------------


def test_sanitize_removes_wait_before_get_title_with_blank_line_between() -> None:
    """Line 276: j += 1 inside the blank-line-skip while loop."""
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "*** Settings ***\n"
        "Library    Browser\n"
        "*** Test Cases ***\n"
        "Testar Título\n"
        "    New Browser    chromium\n"
        "    New Context\n"
        "    New Page    https://example.com\n"
        "    Wait For Elements State    css=h1    visible    10\n"
        "\n"  # blank line between Wait and Get Title
        "    ${titulo}    Get Title\n"
        "    Should Be Equal    ${titulo}    Example Domain\n"
    )
    cleaned = service._sanitize_robot_output(content)
    assert "Wait For Elements State    css=h1" not in cleaned
    assert "Get Title" in cleaned


def test_sanitize_removes_wait_before_get_url_with_blank_line_between() -> None:
    """Line 276: same blank-line-skip, but for Get Url."""
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "*** Settings ***\n"
        "Library    Browser\n"
        "*** Test Cases ***\n"
        "Check URL\n"
        "    New Browser    chromium\n"
        "    New Context\n"
        "    New Page    https://example.com\n"
        "    Wait For Elements State    css=body    visible    10\n"
        "\n"
        "    ${url}    Get Url\n"
        "    Should Contain    ${url}    example\n"
    )
    cleaned = service._sanitize_robot_output(content)
    assert "Wait For Elements State    css=body" not in cleaned
    assert "Get Url" in cleaned


# ---------------------------------------------------------------------------
# _normalize_selector – lines 306/310 (xpath prefix, regex-css match)
# ---------------------------------------------------------------------------


def test_normalize_selector_slash_prefix_yields_xpath() -> None:
    """Line 306: selector starting with '/' → xpath=..."""
    service = TestService(groq_client=DummyGroqClient())
    assert service._normalize_selector("//div[@role='main']") == "xpath=//div[@role='main']"


def test_normalize_selector_paren_prefix_yields_xpath() -> None:
    """Line 306: selector starting with '(' → xpath=..."""
    service = TestService(groq_client=DummyGroqClient())
    assert service._normalize_selector("(//a)[1]") == "xpath=(//a)[1]"


def test_normalize_selector_plain_tag_yields_css() -> None:
    """Line 310: plain alphanumeric selector matched by regex → css=..."""
    service = TestService(groq_client=DummyGroqClient())
    assert service._normalize_selector("button") == "css=button"


def test_normalize_selector_plain_tag_with_attribute_yields_css() -> None:
    """Line 310: tag with attribute like input[type='text'] → css=..."""
    service = TestService(groq_client=DummyGroqClient())
    assert service._normalize_selector("input[type='text']") == "css=input[type='text']"


# ---------------------------------------------------------------------------
# _make_selector_unique – line 327 (#, [, plain CSS match)
# ---------------------------------------------------------------------------


def test_make_selector_unique_hash_prefix() -> None:
    """Line 327: selector starting with '#' → css=# >> nth=0."""
    service = TestService(groq_client=DummyGroqClient())
    assert service._make_selector_unique("#submit-btn") == "css=#submit-btn >> nth=0"


def test_make_selector_unique_bracket_prefix() -> None:
    """Line 327: selector starting with '[' → css=[...] >> nth=0."""
    service = TestService(groq_client=DummyGroqClient())
    assert service._make_selector_unique("[data-testid='ok']") == "css=[data-testid='ok'] >> nth=0"


def test_make_selector_unique_plain_tag() -> None:
    """Line 327: plain alphanumeric selector matched by regex → css=... >> nth=0."""
    service = TestService(groq_client=DummyGroqClient())
    assert service._make_selector_unique("button") == "css=button >> nth=0"


# ---------------------------------------------------------------------------
# improve_robot_test – new signature: (session, test_id, content)
# ---------------------------------------------------------------------------

class _FakeSession:
    """Minimal async session stub for improve_robot_test unit tests."""
    async def flush(self):
        pass


def _make_improve_service(groq_client, project=None, generated=None):
    """Build a TestService with a fake generated test and project for improve tests."""
    from app.models.generated_test import GeneratedTest as GT
    from app.models.project import Project
    from datetime import datetime as dt

    fake_gen = GT(
        id=1,
        test_request_id=10,
        content="*** Test Cases ***",
        file_path="/tmp/t.robot",
        created_at=dt.utcnow(),
    )
    if generated is not None:
        fake_gen = generated

    fake_project = Project(
        id=1,
        name="Proj",
        url=None,
        created_at=dt.utcnow(),
    )
    if project is not None:
        fake_project = project

    class _Repo(DummyTestRepository):
        def __init__(self):
            super().__init__()
            self.generated_to_return = fake_gen

    return TestService(
        test_repository=_Repo(),
        project_repository=DummyProjectRepository(fake_project),
        groq_client=groq_client,
        element_scanner=SuccessfulScanService(),
    )


@pytest.mark.asyncio
async def test_improve_robot_test_returns_sanitized_output() -> None:
    """improve_robot_test calls the LLM and returns sanitized content."""

    class ImprovingGroqClient:
        def generate_robot_test(self, prompt, context=None, page_structure=None):
            return "*** Test Cases ***\nImproved\n    Log    better"

    service = _make_improve_service(ImprovingGroqClient())
    result = await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nOld\n    Log    old")
    assert result is not None
    assert "*** Test Cases ***" in result
    assert "Improved" in result


@pytest.mark.asyncio
async def test_improve_robot_test_returns_none_when_test_not_found() -> None:
    """improve_robot_test returns None when the generated test does not exist."""

    class AnyGroqClient:
        def generate_robot_test(self, prompt, context=None, page_structure=None):
            return "*** Test Cases ***"

    service = _make_improve_service(AnyGroqClient(), generated=None)
    service._test_repository.generated_to_return = None
    result = await service.improve_robot_test(_FakeSession(), test_id=999, content="x")
    assert result is None


@pytest.mark.asyncio
async def test_improve_robot_test_raises_llm_unavailable_on_connection_error() -> None:
    """improve_robot_test wraps APIConnectionError into LLMServiceUnavailableError."""

    class APIConnectionError(Exception):
        pass

    class ConnFailingGroqClient:
        def generate_robot_test(self, prompt, context=None, page_structure=None):
            raise APIConnectionError("down")

    service = _make_improve_service(ConnFailingGroqClient())
    with pytest.raises(LLMServiceUnavailableError):
        await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nX")


@pytest.mark.asyncio
async def test_improve_robot_test_raises_llm_unavailable_on_timeout_error() -> None:
    """improve_robot_test wraps APITimeoutError into LLMServiceUnavailableError."""

    class APITimeoutError(Exception):
        pass

    class TimeoutGroqClient:
        def generate_robot_test(self, prompt, context=None, page_structure=None):
            raise APITimeoutError("timeout")

    service = _make_improve_service(TimeoutGroqClient())
    with pytest.raises(LLMServiceUnavailableError):
        await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nX")


@pytest.mark.asyncio
async def test_improve_robot_test_reraises_unexpected_exceptions() -> None:
    """improve_robot_test re-raises exceptions that are not LLM connectivity errors."""

    class BoomError(Exception):
        pass

    class BoomGroqClient:
        def generate_robot_test(self, prompt, context=None, page_structure=None):
            raise BoomError("boom")

    service = _make_improve_service(BoomGroqClient())
    with pytest.raises(BoomError):
        await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nX")


@pytest.mark.asyncio
async def test_improve_robot_test_uses_page_scan_when_project_has_url() -> None:
    """improve_robot_test passes page_structure to LLM when project has a URL."""
    from app.models.project import Project
    from datetime import datetime as dt

    received_structures = []

    class CapturingGroqClient:
        def generate_robot_test(self, prompt, context=None, page_structure=None):
            received_structures.append(page_structure)
            return "*** Test Cases ***\nWith Scan\n    Log    ok"

    project_with_url = Project(id=1, name="P", url="http://example.com", created_at=dt.utcnow())
    service = _make_improve_service(CapturingGroqClient(), project=project_with_url)

    result = await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nOld")
    assert result is not None
    assert received_structures[0] is not None
    assert received_structures[0]["title"] == "Page"


@pytest.mark.asyncio
async def test_improve_robot_test_uses_cached_scan_when_fresh() -> None:
    """improve_robot_test uses cached scan_cache when it is within TTL."""
    import json
    from app.models.project import Project
    from datetime import datetime as dt

    received_structures = []

    class CapturingGroqClient:
        def generate_robot_test(self, prompt, context=None, page_structure=None):
            received_structures.append(page_structure)
            return "*** Test Cases ***\nCached\n    Log    ok"

    cached_data = {"title": "Cached", "elements": [], "total_elements": 0, "summary": {}, "url": "http://x.com"}
    project_with_cache = Project(
        id=1,
        name="P",
        url="http://x.com",
        scan_cache=json.dumps(cached_data),
        scan_cached_at=dt.utcnow(),
        created_at=dt.utcnow(),
    )

    class NeverScanService:
        async def scan_url(self, _url):
            raise AssertionError("Should not re-scan when cache is fresh")

    service = _make_improve_service(CapturingGroqClient(), project=project_with_cache)
    service._element_scanner = NeverScanService()
    result = await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nX")
    assert result is not None
    assert received_structures[0]["title"] == "Cached"


# ---------------------------------------------------------------------------
# save_robot_test_content – lines 166-178
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_robot_test_content_returns_none_when_not_found() -> None:
    """save_robot_test_content returns None when test does not exist."""
    test_repo = DummyTestRepository()
    test_repo.generated_to_return = None
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(None),
        groq_client=DummyGroqClient(),
    )
    result = await service.save_robot_test_content(session=None, test_id=999, content="*** Test Cases ***")
    assert result is None


@pytest.mark.asyncio
async def test_save_robot_test_content_writes_file_and_updates_content(tmp_path) -> None:
    """save_robot_test_content writes sanitized content to disk and updates the model."""
    from datetime import datetime

    robot_file = tmp_path / "generated_test_1.robot"
    robot_file.write_text("*** Test Cases ***\nOld\n    Log    old\n", encoding="utf-8")

    class FakeGenerated:
        id = 1
        test_request_id = 10
        content = "*** Test Cases ***\nOld\n    Log    old\n"
        file_path = str(robot_file)
        created_at = datetime.utcnow()

    generated = FakeGenerated()

    class FlushableSession:
        async def flush(self):
            pass

    test_repo = DummyTestRepository()
    test_repo.generated_to_return = generated
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(None),
        groq_client=DummyGroqClient(),
    )

    new_content = "*** Test Cases ***\nNew Test\n    Log    new\n"
    result = await service.save_robot_test_content(
        session=FlushableSession(), test_id=1, content=new_content
    )

    assert result is not None
    assert "New Test" in result.content
    assert "New Test" in robot_file.read_text(encoding="utf-8")
