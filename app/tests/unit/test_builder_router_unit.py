import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.builder import router as builder_routes


class DummyBuilderService:
    def __init__(self) -> None:
        self.started = False
        self.project_id = None

    async def start_builder_for_project(
        self, url: str, backend_base_url: str, project_id: int | None = None
    ) -> str:
        self.started = True
        self.project_id = project_id
        return "session-1"

    async def ingest_event(self, payload: dict):
        return {"id": 11, "step": 1, "session_id": "session-1", **payload}

    async def list_steps(self, session_id: str | None = None):
        return [
            {
                "id": 11,
                "step": 1,
                "session_id": session_id or "session-1",
                "action": "click",
                "selector": "#btn",
                "step_name": "Clicar botão",
            }
        ]

    async def update_step(
        self, step_id: int, *, step_name: str | None = None, description: str | None = None
    ):
        return {"id": step_id, "step_name": step_name, "description": description}

    async def generate_code_with_prompt(
        self, session_id: str | None = None, prompt: str | None = None
    ):
        return {
            "session_id": session_id or "session-1",
            "steps_count": 1,
            "code": "Click    css=#btn >> nth=0",
        }


class FailingStartService(DummyBuilderService):
    async def start_builder_for_project(
        self, url: str, backend_base_url: str, project_id: int | None = None
    ) -> str:
        raise RuntimeError("boom")


class FailingEventService(DummyBuilderService):
    async def ingest_event(self, payload: dict):
        raise ValueError("invalid event")


class FailingGenerateService(DummyBuilderService):
    async def generate_code_with_prompt(
        self, session_id: str | None = None, prompt: str | None = None
    ):
        raise ValueError("missing session")


class FailingUpdateService(DummyBuilderService):
    async def update_step(
        self, step_id: int, *, step_name: str | None = None, description: str | None = None
    ):
        raise ValueError("missing step")


class EmptyStepsService(DummyBuilderService):
    async def list_steps(self, session_id: str | None = None):
        return []


def _request(base_url: str = "http://localhost:8000/") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/builder/start",
        "headers": [],
        "scheme": "http",
        "server": ("localhost", 8000),
        "client": ("testclient", 123),
        "root_path": "",
    }
    req = Request(scope)
    if base_url:
        # Keep Request semantics but allow custom assertion of computed backend URL.
        req._base_url = base_url  # type: ignore[attr-defined]
    return req


@pytest.mark.asyncio
async def test_start_builder_route_success(monkeypatch) -> None:
    service = DummyBuilderService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    payload = builder_routes.BuilderStartRequest(url="https://example.com")
    result = await builder_routes.start_builder(
        payload,
        request=_request(),
        service=service,  # type: ignore[arg-type]
    )

    assert result.session_id == "session-1"
    assert result.url == "https://example.com/"
    assert "started" in result.message.lower()
    assert service.project_id is None


@pytest.mark.asyncio
async def test_start_builder_route_forwards_project_id(monkeypatch) -> None:
    service = DummyBuilderService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    payload = builder_routes.BuilderStartRequest(url="https://example.com", project_id=5)
    await builder_routes.start_builder(
        payload,
        request=_request(),
        service=service,  # type: ignore[arg-type]
    )

    assert service.project_id == 5


@pytest.mark.asyncio
async def test_start_builder_route_returns_http_500(monkeypatch) -> None:
    service = FailingStartService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    payload = builder_routes.BuilderStartRequest(url="https://example.com")

    with pytest.raises(HTTPException) as exc:
        await builder_routes.start_builder(
            payload,
            request=_request(),
            service=service,  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 500
    assert "Failed to start builder" in str(exc.value.detail)


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
    assert result.step_id == 11
    assert result.session_id == "session-1"


@pytest.mark.asyncio
async def test_capture_builder_event_route_returns_http_400(monkeypatch) -> None:
    service = FailingEventService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    payload = builder_routes.BuilderEventRequest(
        session_id="session-1",
        action="click",
        selector="#btn",
    )

    with pytest.raises(HTTPException) as exc:
        await builder_routes.capture_builder_event(
            payload,
            service=service,  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid event"


@pytest.mark.asyncio
async def test_get_builder_steps_route_resolves_session_from_steps(monkeypatch) -> None:
    service = DummyBuilderService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    result = await builder_routes.get_builder_steps(service=service)  # type: ignore[arg-type]
    assert result.session_id == "session-1"
    assert len(result.steps) == 1


@pytest.mark.asyncio
async def test_get_builder_steps_route_handles_empty_steps(monkeypatch) -> None:
    service = EmptyStepsService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    result = await builder_routes.get_builder_steps(service=service)  # type: ignore[arg-type]
    assert result.session_id is None
    assert result.steps == []


@pytest.mark.asyncio
async def test_generate_builder_code_route(monkeypatch) -> None:
    service = DummyBuilderService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    payload = builder_routes.BuilderGenerateRequest(session_id="session-1")
    result = await builder_routes.generate_builder_code(payload, service=service)  # type: ignore[arg-type]

    assert result.steps_count == 1
    assert "Click" in result.code


@pytest.mark.asyncio
async def test_generate_builder_code_route_returns_http_400(monkeypatch) -> None:
    service = FailingGenerateService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    payload = builder_routes.BuilderGenerateRequest(session_id="session-1")

    with pytest.raises(HTTPException) as exc:
        await builder_routes.generate_builder_code(
            payload,
            service=service,  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "missing session"


@pytest.mark.asyncio
async def test_update_builder_step_route(monkeypatch) -> None:
    service = DummyBuilderService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    payload = builder_routes.BuilderStepUpdateRequest(step_name="Novo nome")
    result = await builder_routes.update_builder_step(
        11,
        payload,
        service=service,  # type: ignore[arg-type]
    )

    assert result["id"] == 11
    assert result["step_name"] == "Novo nome"


@pytest.mark.asyncio
async def test_update_builder_step_route_returns_http_400(monkeypatch) -> None:
    service = FailingUpdateService()
    monkeypatch.setattr(builder_routes, "get_builder_service", lambda: service)

    payload = builder_routes.BuilderStepUpdateRequest(step_name="Novo nome")

    with pytest.raises(HTTPException) as exc:
        await builder_routes.update_builder_step(
            11,
            payload,
            service=service,  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "missing step"
