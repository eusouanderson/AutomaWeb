import pytest
import pytest_asyncio
import json
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tenacity import RetryError

from app.core.config import settings
from app.db.base import Base
from app.llm.groq_client import PayloadTooLargeError
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


class PayloadTooLargeFailingGroqClient:
    def generate_robot_test(self, prompt, context=None, page_structure=None):
        raise PayloadTooLargeError("too large")


class ChunkingGroqClient:
    def __init__(self):
        self.calls = []
        self._first = True

    def generate_robot_test(self, prompt, context=None, page_structure=None):
        self.calls.append({"prompt": prompt, "context": context, "page_structure": page_structure})
        if self._first:
            self._first = False
            raise PayloadTooLargeError("too large")
        return (
            "*** Settings ***\n"
            "Library    Browser\n\n"
            "*** Test Cases ***\n"
            "Caso Chunk\n"
            "    Log    OK\n"
        )


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


class HealthGroqClient:
    def check_api_health(self):
        return {"ok": True, "latency_ms": 10}


@pytest_asyncio.fixture()
async def session(tmp_path) -> AsyncSession: # type: ignore[arg-type]
    settings.STATIC_DIR = str(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_generate_test(session: AsyncSession) -> None:
    project = Project(name="Projeto Teste", description="Desc")
    session.add(project)
    await session.commit()
    await session.refresh(project)

    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
        test_repository=DummyTestRepository(), # type: ignore[arg-type]
        project_repository=DummyProjectRepository(None), # type: ignore[arg-type]
        groq_client=DummyGroqClient(), # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="Project not found"):
        await service.generate_test(session=None, project_id=999, prompt="Gerar teste") # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_generate_test_raises_scan_unavailable_when_scan_fails(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url="https://example.com")
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(project), # type: ignore[arg-type]
        groq_client=DummyGroqClient(), # type: ignore[arg-type]
        element_scanner=FailingScanService(), # type: ignore[arg-type]
    )

    with pytest.raises(ScanUnavailableError, match="scan is down"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste") # type: ignore[arg-type]

    assert test_repo.updated_statuses[-1] == "failed"


@pytest.mark.asyncio
async def test_generate_test_raises_llm_unavailable_on_retry_error(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url=None)
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(project), # type: ignore[arg-type]
        groq_client=RetryFailingGroqClient(), # type: ignore[arg-type]
        element_scanner=SuccessfulScanService(), # type: ignore[arg-type]
    )

    with pytest.raises(LLMServiceUnavailableError, match="LLM provider connection failed"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste") # type: ignore[arg-type]

    assert test_repo.updated_statuses[-1] == "failed"


@pytest.mark.asyncio
async def test_generate_test_raises_llm_unavailable_on_api_connection_error(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url=None)
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(project), # type: ignore[arg-type]
        groq_client=APIConnectionFailingGroqClient(), # type: ignore[arg-type]
        element_scanner=SuccessfulScanService(), # type: ignore[arg-type]
    )

    with pytest.raises(LLMServiceUnavailableError, match="LLM provider connection failed"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste") # type: ignore[arg-type]

    assert test_repo.updated_statuses[-1] == "failed"


@pytest.mark.asyncio
async def test_generate_test_raises_llm_unavailable_on_payload_too_large(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url=None)
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(project), # type: ignore[arg-type]
        groq_client=PayloadTooLargeFailingGroqClient(), # type: ignore[arg-type]
        element_scanner=SuccessfulScanService(), # type: ignore[arg-type]
    )

    with pytest.raises(LLMServiceUnavailableError, match="LLM request payload too large"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste") # type: ignore[arg-type]

    assert test_repo.updated_statuses[-1] == "failed"


@pytest.mark.asyncio
async def test_generate_test_uses_scanned_page_structure(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url="https://example.com")
    test_repo = DummyTestRepository()
    groq_client = CapturingGroqClient()
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(project), # type: ignore[arg-type]
        groq_client=groq_client, # type: ignore[arg-type]
        element_scanner=SuccessfulScanService(), # type: ignore[arg-type]
    )

    class _Session:
        async def flush(self): pass

    generated = await service.generate_test(session=_Session(), project_id=1, prompt="Gerar teste") # type: ignore[arg-type]

    assert generated.id == 99
    assert groq_client.captured_page_structure == {"title": "Page"}


@pytest.mark.asyncio
async def test_generate_test_uses_chunked_generation_after_payload_too_large(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    settings.LLM_DOM_CHUNKING_ENABLED = True
    settings.LLM_DOM_CHUNK_TARGET_CHARS = 250
    settings.LLM_DOM_CHUNK_MAX_PARTS = 4

    big_items = [{"id": i, "text": "x" * 120} for i in range(12)]
    project = Project(
        id=1,
        name="Projeto",
        description="Desc",
        test_directory=str(tmp_path),
        url="https://example.com",
        scan_cache=json.dumps({"title": "Page", "items": big_items}),
    )
    test_repo = DummyTestRepository()
    groq_client = ChunkingGroqClient()
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(project), # type: ignore[arg-type]
        groq_client=groq_client, # type: ignore[arg-type]
        element_scanner=SuccessfulScanService(), # type: ignore[arg-type]
    )

    generated = await service.generate_test(session=None, project_id=1, prompt="Gerar teste", context="ctx") # type: ignore[arg-type]

    assert generated.id == 99
    assert "*** Test Cases ***" in generated.content
    assert len(groq_client.calls) > 1
    assert any("Where (onde):" in call["prompt"] and "CHUNK" in call["prompt"] for call in groq_client.calls[1:])


@pytest.mark.asyncio
async def test_generate_test_raises_when_chunked_generation_also_fails(tmp_path, monkeypatch) -> None:
    settings.STATIC_DIR = str(tmp_path)
    settings.LLM_DOM_CHUNKING_ENABLED = True

    project = Project(
        id=1,
        name="Projeto",
        description="Desc",
        test_directory=str(tmp_path),
        url="https://example.com",
        scan_cache=json.dumps({"title": "Page", "items": [{"id": 1}]}),
    )

    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(project), # type: ignore[arg-type]
        groq_client=PayloadTooLargeFailingGroqClient(), # type: ignore[arg-type]
        element_scanner=SuccessfulScanService(), # type: ignore[arg-type]
    )

    def _raise_chunked(*_args, **_kwargs):
        raise PayloadTooLargeError("still too large")

    monkeypatch.setattr(service, "_generate_robot_test_chunked", _raise_chunked)

    with pytest.raises(LLMServiceUnavailableError, match="LLM request payload too large"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste") # type: ignore[arg-type]

    assert test_repo.updated_statuses[-1] == "failed"


@pytest.mark.asyncio
async def test_generate_test_reraises_unexpected_llm_exception(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url=None)
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(project), # type: ignore[arg-type]
        groq_client=UnexpectedFailingGroqClient(), # type: ignore[arg-type]
        element_scanner=SuccessfulScanService(), # type: ignore[arg-type]
    )

    with pytest.raises(UnexpectedLLMError, match="unexpected"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste") # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_list_generated_tests_by_project_success() -> None:
    project = Project(id=1, name="Projeto", description="Desc")
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(project), # type: ignore[arg-type]
        groq_client=DummyGroqClient(),# type: ignore[arg-type]
    )

    items = await service.list_generated_tests_by_project(session=None, project_id=1) # type: ignore[arg-type]

    assert items == ["dummy"]


@pytest.mark.asyncio
async def test_get_generated_test_passthrough() -> None:
    generated = type("Generated", (), {"id": 7})()
    test_repo = DummyTestRepository()
    test_repo.generated_to_return = generated # type: ignore[arg-type]
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(None), # type: ignore[arg-type]
        groq_client=DummyGroqClient(), # type: ignore[arg-type]
    )

    found = await service.get_generated_test(session=None, test_id=7) # type: ignore[arg-type]

    assert found is generated


@pytest.mark.asyncio
async def test_list_generated_tests_by_project_raises_when_project_not_found() -> None:
    service = TestService(
        test_repository=DummyTestRepository(), # type: ignore[arg-type]
        project_repository=DummyProjectRepository(None), # type: ignore[arg-type]
        groq_client=DummyGroqClient(), # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="Project not found"):
        await service.list_generated_tests_by_project(session=None, project_id=1) # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_delete_generated_test_returns_false_when_not_found() -> None:
    test_repo = DummyTestRepository()
    service = TestService(test_repository=test_repo, project_repository=DummyProjectRepository(None), groq_client=DummyGroqClient()) # type: ignore[arg-type]

    deleted = await service.delete_generated_test(session=None, test_id=1) # type: ignore[arg-type]

    assert deleted is False


@pytest.mark.asyncio
async def test_delete_generated_test_handles_unlink_error(tmp_path, monkeypatch) -> None:
    file_path = tmp_path / "generated_test_1.robot"
    file_path.write_text("*** Test Cases ***\nExample")
    generated = type("Generated", (), {"file_path": str(file_path)})()

    test_repo = DummyTestRepository()
    test_repo.generated_to_return = generated # type: ignore[arg-type]
    service = TestService(test_repository=test_repo, project_repository=DummyProjectRepository(None), groq_client=DummyGroqClient()) # type: ignore[arg-type]

    def failing_unlink(self):
        raise OSError("cannot unlink")

    monkeypatch.setattr("pathlib.Path.unlink", failing_unlink)

    deleted = await service.delete_generated_test(session=None, test_id=1) # type: ignore[arg-type]

    assert deleted is True
    assert test_repo.deleted_item is generated


def test_sanitize_robot_output_filters_noise_and_normalizes_library() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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


def test_split_page_structure_chunks_large_payload() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    settings.LLM_DOM_CHUNK_TARGET_CHARS = 200
    page_structure = {
        "title": "Page",
        "elements": [{"selector": f"#id-{i}", "text": "x" * 80} for i in range(10)],
    }

    chunks = service._split_page_structure(page_structure)

    assert len(chunks) > 1
    assert all("title" in c for c in chunks)


def test_check_llm_health_passthrough() -> None:
    service = TestService(groq_client=HealthGroqClient()) # type: ignore[arg-type]

    health = service.check_llm_health()

    assert health["ok"] is True
    assert health["latency_ms"] == 10


def test_generate_robot_test_chunked_raises_when_not_splittable() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]

    with pytest.raises(PayloadTooLargeError, match="cannot be split"):
        service._generate_robot_test_chunked(
            prompt="p",
            context=None,
            page_structure={"title": "small"},
        )


def test_generate_robot_test_chunked_raises_when_no_partial_output(monkeypatch) -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]

    class _NoIterationChunks:
        def __len__(self):
            return 2

        def __getitem__(self, item):
            if isinstance(item, slice):
                return []
            raise IndexError

    monkeypatch.setattr(service, "_split_page_structure", lambda _ps, target_chars=None: _NoIterationChunks())

    with pytest.raises(PayloadTooLargeError, match="produced no output"):
        service._generate_robot_test_chunked(prompt="p", context=None, page_structure={"k": "v"})


def test_split_page_structure_returns_original_when_within_target() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    settings.LLM_DOM_CHUNK_TARGET_CHARS = 1000
    page_structure = {"title": "tiny", "elements": []}

    chunks = service._split_page_structure(page_structure)

    assert chunks == [page_structure]


def test_split_page_structure_collects_nested_dict_entries() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    settings.LLM_DOM_CHUNK_TARGET_CHARS = 60
    page_structure = {
        "title": "Page",
        "forms": {
            "login": [{"id": 1, "name": "email", "text": "x" * 50}],
            "signup": [{"id": 2, "name": "name", "text": "y" * 50}],
        },
    }

    chunks = service._split_page_structure(page_structure)

    assert len(chunks) >= 1
    assert any("forms" in c for c in chunks)


def test_split_page_structure_fallback_for_scalar_only_payload() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    settings.LLM_DOM_CHUNK_TARGET_CHARS = 200
    page_structure = {
        "title": "Page",
        "html": "x" * 900,
    }

    chunks = service._split_page_structure(page_structure)

    assert len(chunks) > 1
    assert all(c.get("chunk_format") == "json-minified" for c in chunks)


def test_split_page_structure_handles_non_dict_root_for_dotted_key() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    settings.LLM_DOM_CHUNK_TARGET_CHARS = 180
    page_structure = {
        "meta": [{"kind": "base"}],
        "meta.sub": [{"blob": "y" * 300}],
    }

    chunks = service._split_page_structure(page_structure)

    assert len(chunks) >= 1
    assert any("meta" in c for c in chunks)


def test_split_page_structure_keeps_oversized_single_entry_chunk() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    settings.LLM_DOM_CHUNK_TARGET_CHARS = 200
    page_structure = {
        "title": "Page",
        "items": [{"blob": "z" * 1200}],
    }

    chunks = service._split_page_structure(page_structure)

    assert len(chunks) >= 1
    assert any("items" in c for c in chunks)


def test_generate_robot_test_chunked_retries_with_smaller_targets(monkeypatch) -> None:
    class SizeSensitiveGroqClient:
        def __init__(self):
            self.chunk_sizes = []

        def generate_robot_test(self, prompt, context=None, page_structure=None):
            size = len(json.dumps(page_structure or {}, ensure_ascii=False, separators=(",", ":")))
            self.chunk_sizes.append(size)
            if size > 700:
                raise PayloadTooLargeError("too large chunk")
            return "*** Test Cases ***\nChunk\n    Log    OK"

    settings.LLM_DOM_CHUNK_TARGET_CHARS = 1200
    groq_client = SizeSensitiveGroqClient()
    service = TestService(groq_client=groq_client) # type: ignore[arg-type]

    def fake_split(_page_structure, target_chars=None):
        if (target_chars or 0) >= 1000:
            return [{"blob": "x" * 1100}, {"tiny": "ok"}]
        return [{"blob": "x" * 250}, {"blob": "y" * 260}]

    monkeypatch.setattr(service, "_split_page_structure", fake_split)

    merged = service._generate_robot_test_chunked(prompt="p", context=None, page_structure={"big": True})

    assert "*** Test Cases ***" in merged
    assert any(size > 700 for size in groq_client.chunk_sizes)
    assert any(size <= 700 for size in groq_client.chunk_sizes)
    assert service.last_generation_metadata is not None
    assert service.last_generation_metadata["strategy"] == "chunked"
    assert service.last_generation_metadata["chunk_target_chars"] < 1200


def test_compact_page_structure_limits_heavy_fields() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    page_structure = {
        "title": "T" * 500,
        "elements": [
            {"selector": f"#el-{i}", "text": "x" * 400, "attrs": {"aria": "y" * 400}}
            for i in range(60)
        ],
    }

    compacted = service._compact_page_structure(page_structure)

    assert len(compacted["title"]) <= 220
    assert len(compacted["elements"]) == 30
    assert len(compacted["elements"][0]["text"]) <= 220


def test_compact_page_structure_handles_top_level_string() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]

    compacted = service._compact_page_structure("x" * 500)  # type: ignore[arg-type]

    assert isinstance(compacted, str)
    assert len(compacted) == 220


def test_compact_page_structure_handles_top_level_list() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]

    compacted = service._compact_page_structure(list(range(50)))  # type: ignore[arg-type]

    assert isinstance(compacted, list)
    assert len(compacted) == 30
    assert compacted[-1] == 29


def test_compact_page_structure_handles_top_level_scalar() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]

    compacted = service._compact_page_structure(123)  # type: ignore[arg-type]

    assert compacted == 123


def test_merge_robot_parts_keeps_sections() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    parts = [
        "*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nCaso A\n    Log    A\n",
        "*** Test Cases ***\nCaso B\n    Log    B\n\n*** Keywords ***\nKW\n    Log    K\n",
    ]

    merged = service._merge_robot_parts(parts)

    assert "*** Settings ***" in merged
    assert "*** Test Cases ***" in merged
    assert "Caso A" in merged
    assert "Caso B" in merged
    assert "*** Keywords ***" in merged


def test_sanitize_robot_output_hardens_strict_mode_selector_from_context() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]

    assert service._normalize_selector("css:.btn-primary") == "css=.btn-primary"
    assert service._normalize_selector(".card-title") == "css=.card-title"


def test_make_selector_unique_covers_already_unique_and_non_css() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]

    assert service._make_selector_unique("css=.card-title >> nth=0") == "css=.card-title >> nth=0"
    assert service._make_selector_unique("xpath=//button") == "xpath=//button"


def test_sanitize_injects_set_browser_timeout_after_new_context() -> None:
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    assert service._normalize_selector("//div[@role='main']") == "xpath=//div[@role='main']"


def test_normalize_selector_paren_prefix_yields_xpath() -> None:
    """Line 306: selector starting with '(' → xpath=..."""
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    assert service._normalize_selector("(//a)[1]") == "xpath=(//a)[1]"


def test_normalize_selector_plain_tag_yields_css() -> None:
    """Line 310: plain alphanumeric selector matched by regex → css=..."""
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    assert service._normalize_selector("button") == "css=button"


def test_normalize_selector_plain_tag_with_attribute_yields_css() -> None:
    """Line 310: tag with attribute like input[type='text'] → css=..."""
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type] 
    assert service._normalize_selector("input[type='text']") == "css=input[type='text']"


# ---------------------------------------------------------------------------
# _make_selector_unique – line 327 (#, [, plain CSS match)
# ---------------------------------------------------------------------------


def test_make_selector_unique_hash_prefix() -> None:
    """Line 327: selector starting with '#' → css=# >> nth=0."""
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    assert service._make_selector_unique("#submit-btn") == "css=#submit-btn >> nth=0"


def test_make_selector_unique_bracket_prefix() -> None:
    """Line 327: selector starting with '[' → css=[...] >> nth=0."""
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
    assert service._make_selector_unique("[data-testid='ok']") == "css=[data-testid='ok'] >> nth=0"


def test_make_selector_unique_plain_tag() -> None:
    """Line 327: plain alphanumeric selector matched by regex → css=... >> nth=0."""
    service = TestService(groq_client=DummyGroqClient()) # type: ignore[arg-type]
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
        test_repository=_Repo(), # type: ignore[arg-type]
        project_repository=DummyProjectRepository(fake_project), # type: ignore[arg-type]
        groq_client=groq_client, # type: ignore[arg-type]
        element_scanner=SuccessfulScanService(), # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_improve_robot_test_returns_sanitized_output() -> None:
    """improve_robot_test calls the LLM and returns sanitized content."""

    class ImprovingGroqClient:
        def generate_robot_test(self, prompt, context=None, page_structure=None):
            return "*** Test Cases ***\nImproved\n    Log    better"

    service = _make_improve_service(ImprovingGroqClient())
    result = await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nOld\n    Log    old") # type: ignore[arg-type]
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
    service._test_repository.generated_to_return = None # type: ignore[arg-type]
    result = await service.improve_robot_test(_FakeSession(), test_id=999, content="x") # type: ignore[arg-type]
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
        await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nX") # type: ignore[arg-type]


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
        await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nX") # type: ignore[arg-type]


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
        await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nX") # type: ignore[arg-type]


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

    result = await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nOld") # type: ignore[arg-type]
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
    service._element_scanner = NeverScanService() # type: ignore[arg-type]
    result = await service.improve_robot_test(_FakeSession(), test_id=1, content="*** Test Cases ***\nX") # type: ignore[arg-type]
    assert result is not None
    assert received_structures[0]["title"] == "Cached"


@pytest.mark.asyncio
async def test_generate_test_uses_cached_scan_without_rescan(tmp_path) -> None:
    """generate_test reuses project.scan_cache when force_rescan=False (covers lines 68-69)."""
    import json
    from datetime import datetime as dt

    settings.STATIC_DIR = str(tmp_path)
    cached_data = {"title": "Cached", "elements": [], "total_elements": 0, "summary": {}, "url": "https://example.com"}
    project = Project(
        id=1,
        name="Proj",
        description="Desc",
        test_directory=str(tmp_path),
        url="https://example.com",
        scan_cache=json.dumps(cached_data),
        scan_cached_at=dt.utcnow(),
    )

    class NeverScanService:
        async def scan_url(self, _url):
            raise AssertionError("Scanner should not be called when cache is available")

    groq_client = CapturingGroqClient()
    service = TestService(
        test_repository=DummyTestRepository(), # type: ignore[arg-type]
        project_repository=DummyProjectRepository(project), # type: ignore[arg-type]
        groq_client=groq_client, # type: ignore[arg-type]
        element_scanner=NeverScanService(), # type: ignore[arg-type]
    )

    class _Session:
        async def flush(self): pass

    generated = await service.generate_test(
        session=_Session(), project_id=1, prompt="Gerar teste", force_rescan=False # type: ignore[arg-type]
    )
    assert generated.id == 99
    assert groq_client.captured_page_structure == cached_data


@pytest.mark.asyncio
async def test_get_or_refresh_scan_returns_none_on_scanner_error() -> None:
    """_get_or_refresh_scan catches ElementScannerError and returns None (covers lines 209-211)."""
    from datetime import datetime as dt
    from datetime import timedelta

    project_stale = Project(
        id=1,
        name="P",
        url="http://x.com",
        scan_cache=None,
        scan_cached_at=None,
        created_at=dt.utcnow(),
    )

    service = _make_improve_service(DummyGroqClient(), project=project_stale)
    service._element_scanner = FailingScanService() # type: ignore[arg-type]

    result = await service._get_or_refresh_scan(_FakeSession(), project_stale) # type: ignore[arg-type]
    assert result is None



@pytest.mark.asyncio
async def test_save_robot_test_content_returns_none_when_not_found() -> None:
    """save_robot_test_content returns None when test does not exist."""
    test_repo = DummyTestRepository()
    test_repo.generated_to_return = None
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(None), # type: ignore[arg-type]
        groq_client=DummyGroqClient(), # type: ignore[arg-type]
    )
    result = await service.save_robot_test_content(session=None, test_id=999, content="*** Test Cases ***") # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_save_robot_test_content_writes_file_and_updates_content(tmp_path) -> None:
    """save_robot_test_content writes exact editor content to disk and updates the model."""
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
    test_repo.generated_to_return = generated # type: ignore[arg-type]
    service = TestService(
        test_repository=test_repo, # type: ignore[arg-type]
        project_repository=DummyProjectRepository(None), # type: ignore[arg-type]
        groq_client=DummyGroqClient(), # type: ignore[arg-type]
    )

    new_content = "*** Test Cases ***\nNew Test\n    Log    new\n"
    result = await service.save_robot_test_content(
        session=FlushableSession(), test_id=1, content=new_content # type: ignore[arg-type]
    )

    assert result is not None
    assert result.content == new_content
    assert robot_file.read_text(encoding="utf-8") == new_content
