import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.builder.event_store import InMemoryEventStore
from app.builder.code_generator import PlaywrightCodeGenerator
from app.db.init_db import init_db
from app.builder.service import BuilderService, get_builder_service


class DummyPlaywrightManager:
    def __init__(self) -> None:
        self.started: list[dict] = []
        self.shutdown_called = False

    async def start_session(self, *, session_id: str, url: str, backend_event_url: str):
        self.started.append(
            {
                "session_id": session_id,
                "url": url,
                "backend_event_url": backend_event_url,
            }
        )

    async def shutdown(self) -> None:
        self.shutdown_called = True


class DummyPlaywrightManagerWithHandler:
    def __init__(self) -> None:
        self.started: list[dict] = []

    async def start_session(
        self,
        *,
        session_id: str,
        url: str,
        backend_event_url: str,
        event_handler,
    ):
        self.started.append(
            {
                "session_id": session_id,
                "url": url,
                "backend_event_url": backend_event_url,
            }
        )
        await event_handler(
            {
                "action": "click",
                "selector": "#from-browser",
                "description": "browser callback",
            }
        )

    async def shutdown(self) -> None:
        return None


async def _make_service(manager) -> BuilderService:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool
    )
    await init_db(engine)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    store = InMemoryEventStore(session_factory=session_factory)
    return BuilderService(
        event_store=store,
        playwright_manager=manager,
    )


@pytest.mark.asyncio
async def test_builder_service_ingests_and_generates_code() -> None:
    manager = DummyPlaywrightManager()
    service = await _make_service(manager)  # type: ignore[arg-type]

    session_id = await service.start_builder(
        "https://example.com", "http://localhost:8000"
    )

    await service.ingest_event(
        {
            "session_id": session_id,
            "action": "click",
            "selector": "#login",
            "description": "Clicar no botao de login",
        }
    )
    await service.ingest_event(
        {
            "session_id": session_id,
            "action": "input",
            "selector": "#email",
            "value": "teste@email.com",
            "description": "Preencher e-mail",
        }
    )

    steps = await service.list_steps(session_id)
    assert len(steps) == 2
    assert steps[0]["action"] == "click"
    assert steps[1]["action"] == "input"

    generated = await service.generate_code(session_id)
    assert 'Click    css=#login >> nth=0' in generated["code"]
    assert 'Fill Text    css=#email >> nth=0    teste@email.com' in generated["code"]


@pytest.mark.asyncio
async def test_builder_service_rejects_unsupported_event() -> None:
    manager = DummyPlaywrightManager()
    service = await _make_service(manager)  # type: ignore[arg-type]
    session_id = await service.start_builder(
        "https://example.com", "http://localhost:8000"
    )

    with pytest.raises(ValueError):
        await service.ingest_event(
            {
                "session_id": session_id,
                "action": "hover",
                "selector": "#x",
            }
        )


@pytest.mark.asyncio
async def test_builder_service_requires_selector_for_valid_action() -> None:
    manager = DummyPlaywrightManager()
    service = await _make_service(manager)  # type: ignore[arg-type]
    session_id = await service.start_builder(
        "https://example.com", "http://localhost:8000"
    )

    with pytest.raises(ValueError, match="requires a selector"):
        await service.ingest_event(
            {
                "session_id": session_id,
                "action": "click",
            }
        )


@pytest.mark.asyncio
async def test_builder_service_uses_active_session_when_session_id_missing() -> None:
    manager = DummyPlaywrightManager()
    service = await _make_service(manager)  # type: ignore[arg-type]
    session_id = await service.start_builder(
        "https://example.com", "http://localhost:8000"
    )

    saved = await service.ingest_event(
        {
            "action": "click",
            "selector": "#implicit",
            "text": "legacy description",
        }
    )

    assert saved["session_id"] == session_id
    assert saved["description"] == "legacy description"


@pytest.mark.asyncio
async def test_builder_service_raises_when_no_active_session_for_implicit_event() -> None:
    manager = DummyPlaywrightManager()
    service = await _make_service(manager)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="No active builder session found"):
        await service.ingest_event(
            {
                "action": "click",
                "selector": "#x",
            }
        )


@pytest.mark.asyncio
async def test_builder_service_generate_code_with_prompt_raises_without_session() -> None:
    manager = DummyPlaywrightManager()
    service = await _make_service(manager)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="No builder session found"):
        await service.generate_code_with_prompt(session_id="missing", prompt="p")


@pytest.mark.asyncio
async def test_builder_service_records_event_from_browser_handler() -> None:
    manager = DummyPlaywrightManagerWithHandler()
    service = await _make_service(manager)  # type: ignore[arg-type]

    session_id = await service.start_builder(
        "https://example.com", "http://localhost:8000"
    )

    steps = await service.list_steps(session_id)
    assert len(steps) == 1
    assert steps[0]["selector"] == "#from-browser"
    assert steps[0]["action"] == "click"


@pytest.mark.asyncio
async def test_builder_service_shutdown_calls_manager() -> None:
    manager = DummyPlaywrightManager()
    service = await _make_service(manager)  # type: ignore[arg-type]

    await service.shutdown()
    assert manager.shutdown_called is True


@pytest.mark.asyncio
async def test_builder_service_updates_saved_step_name() -> None:
    manager = DummyPlaywrightManager()
    service = await _make_service(manager)  # type: ignore[arg-type]

    session_id = await service.start_builder_for_project(
        "https://example.com", "http://localhost:8000", project_id=9
    )
    saved = await service.ingest_event(
        {
            "session_id": session_id,
            "action": "click",
            "selector": "#save",
            "page_url": "https://example.com/form",
        }
    )

    updated = await service.update_step(saved["id"], step_name="Salvar formulário")

    assert updated["step_name"] == "Salvar formulário"
    assert updated["page_url"] == "https://example.com/form"


def test_get_builder_service_returns_singleton_instance() -> None:
    service = get_builder_service()
    assert isinstance(service, BuilderService)


@pytest.mark.asyncio
async def test_code_generator_handles_click_and_input() -> None:
    generator = PlaywrightCodeGenerator()
    code = generator.generate(
        [
            {"action": "click", "selector": "#login"},
            {"action": "input", "selector": "#country", "value": "BR"},
        ],
        start_url="https://example.com",
    )

    assert 'Library    Browser' in code
    assert 'New Page    https://example.com' in code
    assert 'Click    css=#login >> nth=0' in code
    assert 'Fill Text    css=#country >> nth=0    BR' in code
