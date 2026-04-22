import pytest

from app.builder import router as builder_routes


class DummyBuilderService:
    def __init__(self) -> None:
        self.started = False

    async def start_builder(self, url: str, backend_base_url: str) -> str:
        self.started = True
        return "session-1"

    async def ingest_event(self, payload: dict):
        return {"step": 1, "session_id": "session-1", **payload}

    async def list_steps(self, session_id: str | None = None):
        return [
            {
                "step": 1,
                "session_id": session_id or "session-1",
                "action": "click",
                "selector": "#btn",
            }
        ]

    async def generate_code_with_prompt(
        self, session_id: str | None = None, prompt: str | None = None
    ):
        return {
            "session_id": session_id or "session-1",
            "steps_count": 1,
            "code": "Click    css=#btn >> nth=0",
        }


@pytest.mark.asyncio
async def test_capture_builder_event_route(monkeypatch) -> None:
    service = DummyBuilderService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    payload = builder_routes.BuilderEventRequest(
        session_id="session-1",
        action="click",
        selector="#btn",
        description="Clicar no botao",
    )
    result = await builder_routes.capture_builder_event(payload, service=service)  # type: ignore[arg-type]

    assert result.step == 1
    assert result.session_id == "session-1"


@pytest.mark.asyncio
async def test_generate_builder_code_route(monkeypatch) -> None:
    service = DummyBuilderService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    payload = builder_routes.BuilderGenerateRequest(session_id="session-1")
    result = await builder_routes.generate_builder_code(payload, service=service)  # type: ignore[arg-type]

    assert result.steps_count == 1
    assert "Click" in result.code
