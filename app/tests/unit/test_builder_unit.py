import pytest

from app.builder.code_generator import PlaywrightCodeGenerator
from app.builder.service import BuilderService


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


@pytest.mark.asyncio
async def test_builder_service_ingests_and_generates_code() -> None:
    manager = DummyPlaywrightManager()
    service = BuilderService(playwright_manager=manager)  # type: ignore[arg-type]

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
    service = BuilderService(playwright_manager=manager)  # type: ignore[arg-type]
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
