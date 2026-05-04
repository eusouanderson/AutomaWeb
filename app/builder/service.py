from __future__ import annotations

from typing import Any

from app.builder.code_generator import PlaywrightCodeGenerator
from app.builder.event_store import InMemoryEventStore
from app.builder.playwright_manager import PlaywrightManager

_ALLOWED_ACTIONS = {"click", "input"}


class BuilderService:
    def __init__(
        self,
        *,
        event_store: InMemoryEventStore | None = None,
        playwright_manager: PlaywrightManager | None = None,
        code_generator: PlaywrightCodeGenerator | None = None,
    ) -> None:
        self._event_store = event_store or InMemoryEventStore()
        self._playwright_manager = playwright_manager or PlaywrightManager()
        self._code_generator = code_generator or PlaywrightCodeGenerator()

    async def start_builder(self, url: str, backend_base_url: str) -> str:
        session = await self._event_store.create_session(url)
        backend_event_url = f"{backend_base_url.rstrip('/')}/builder/event"

        async def _record_from_browser(payload: dict[str, Any]) -> None:
            await self.record_event(session.session_id, payload)

        try:
            await self._playwright_manager.start_session(
                session_id=session.session_id,
                url=url,
                backend_event_url=backend_event_url,
                event_handler=_record_from_browser,
            )
        except TypeError as exc:
            if "event_handler" not in str(exc):
                raise
            # Backward-compatible fallback for older test doubles.
            await self._playwright_manager.start_session(
                session_id=session.session_id,
                url=url,
                backend_event_url=backend_event_url,
            )
        return session.session_id

    async def start_builder_for_project(
        self, url: str, backend_base_url: str, project_id: int | None = None
    ) -> str:
        session = await self._event_store.create_session(url, project_id=project_id)
        backend_event_url = f"{backend_base_url.rstrip('/')}/builder/event"

        async def _record_from_browser(payload: dict[str, Any]) -> None:
            await self.record_event(session.session_id, payload)

        try:
            await self._playwright_manager.start_session(
                session_id=session.session_id,
                url=url,
                backend_event_url=backend_event_url,
                event_handler=_record_from_browser,
            )
        except TypeError as exc:
            if "event_handler" not in str(exc):
                raise
            await self._playwright_manager.start_session(
                session_id=session.session_id,
                url=url,
                backend_event_url=backend_event_url,
            )
        return session.session_id

    async def record_event(
        self, session_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        normalized = self._normalize_event(payload)
        return await self._event_store.add_event(session_id, normalized)

    async def ingest_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id", "")).strip()
        if not session_id:
            session = await self._event_store.get_session()
            if not session:
                raise ValueError("No active builder session found")
            session_id = session.session_id

        return await self.record_event(session_id, payload)

    async def list_steps(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return await self._event_store.get_steps(session_id)

    async def update_step(
        self,
        step_id: int,
        *,
        step_name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if step_name is not None:
            updates["step_name"] = step_name
        if description is not None:
            updates["description"] = description
        if not updates:
            raise ValueError("No builder step updates provided")
        return await self._event_store.update_step(step_id, updates)

    async def generate_code(self, session_id: str | None = None) -> dict[str, Any]:
        return await self.generate_code_with_prompt(session_id=session_id, prompt=None)

    async def generate_code_with_prompt(
        self, session_id: str | None = None, prompt: str | None = None
    ) -> dict[str, Any]:
        session = await self._event_store.get_session(session_id)
        if not session:
            raise ValueError("No builder session found")

        steps = await self._event_store.get_steps(session.session_id)
        code = self._code_generator.generate(
            steps=steps,
            start_url=session.url,
            prompt=prompt,
        )
        return {
            "session_id": session.session_id,
            "steps_count": len(steps),
            "code": code,
        }

    async def shutdown(self) -> None:
        await self._playwright_manager.shutdown()

    def _normalize_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_action = payload.get("action")
        raw_type = payload.get("type")

        action = str(raw_action or raw_type or "").strip().lower()
        if action not in _ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported action: '{action}'")

        selector = str(payload.get("selector", "")).strip()
        if not selector:
            raise ValueError(f"Action '{action}' requires a selector")

        normalized: dict[str, Any] = {
            "action": action,
            "selector": selector,
            "value": None,
            "description": str(payload.get("description", "")).strip(),
            "step_name": str(payload.get("step_name", "")).strip(),
            "page_url": str(payload.get("page_url", "")).strip(),
            "page_title": str(payload.get("page_title", "")).strip(),
            "element_tag": str(payload.get("element_tag", "")).strip(),
            "element_text": str(payload.get("element_text", "")).strip(),
            "input_type": str(payload.get("input_type", "")).strip(),
            "href": str(payload.get("href", "")).strip(),
        }

        if action == "input":
            normalized["value"] = str(payload.get("value", ""))

        # Keep legacy shape available for old consumers.
        normalized["type"] = normalized["action"]

        legacy_text = str(payload.get("text", "")).strip()
        if legacy_text and not normalized["description"]:
            normalized["description"] = legacy_text

        if not normalized["step_name"]:
            normalized["step_name"] = normalized["description"]

        if not normalized["step_name"]:
            if action == "input":
                normalized["step_name"] = "Preencher campo"
            else:
                normalized["step_name"] = "Interagir com elemento"

        return normalized


_builder_service = BuilderService()


def get_builder_service() -> BuilderService:
    return _builder_service
