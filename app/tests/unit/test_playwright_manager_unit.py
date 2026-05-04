from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.builder.playwright_manager import (
    BuilderRuntimeSession,
    PlaywrightManager,
    _capture_script,
)


def _fake_playwright_runtime():
    page = MagicMock()
    page.expose_binding = AsyncMock()
    page.add_init_script = AsyncMock()
    page.goto = AsyncMock()

    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()

    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()

    playwright_obj = MagicMock()
    playwright_obj.chromium.launch = AsyncMock(return_value=browser)
    playwright_obj.stop = AsyncMock()

    async_playwright_obj = MagicMock()
    async_playwright_obj.start = AsyncMock(return_value=playwright_obj)

    return async_playwright_obj, playwright_obj, browser, context, page


def test_capture_script_escapes_session_and_url() -> None:
    script = _capture_script('sess"\\id', 'http://api.local/ev"ent\\x')
    assert 'const SESSION_ID = "sess\\"\\\\id";' in script
    assert 'const BACKEND_EVENT_URL = "http://api.local/ev\\"ent\\\\x";' in script
    assert "Avoid returning non-unique IDs/names" in script
    assert '__aw_name_input__' in script
    assert 'page_url: window.location.href' in script


def test_playwright_manager_singleton_and_reinit_guard() -> None:
    first = PlaywrightManager()
    first._sessions = {"s": "placeholder"}  # type: ignore[assignment]

    second = PlaywrightManager()

    assert first is second
    assert second._sessions == {"s": "placeholder"}


@pytest.mark.asyncio
async def test_start_session_registers_runtime_and_binding_callback() -> None:
    manager = PlaywrightManager()
    manager._sessions = {}

    apw_obj, playwright_obj, browser, context, page = _fake_playwright_runtime()
    event_handler = AsyncMock()

    with patch("app.builder.playwright_manager.async_playwright", return_value=apw_obj):
        await manager.start_session(
            session_id="session-1",
            url="https://example.com",
            backend_event_url="http://localhost:8000/builder/event",
            event_handler=event_handler,
        )

    assert "session-1" in manager._sessions
    session = manager._sessions["session-1"]
    assert isinstance(session, BuilderRuntimeSession)
    assert session.playwright is playwright_obj
    assert session.browser is browser
    assert session.context is context
    assert session.page is page

    page.expose_binding.assert_awaited_once()
    bind_name, bind_callback = page.expose_binding.await_args.args
    assert bind_name == "__awRecordBuilderEvent"

    await bind_callback(None, {"action": "click"})
    event_handler.assert_awaited_once_with({"action": "click"})

    await bind_callback(None, "not-a-dict")
    event_handler.assert_awaited_once()

    page.add_init_script.assert_awaited_once()
    page.goto.assert_awaited_once_with("https://example.com")


@pytest.mark.asyncio
async def test_start_session_raises_for_duplicate_session_id() -> None:
    manager = PlaywrightManager()
    manager._sessions = {}

    apw_obj, *_ = _fake_playwright_runtime()
    with patch("app.builder.playwright_manager.async_playwright", return_value=apw_obj):
        await manager.start_session(
            session_id="dup-id",
            url="https://example.com",
            backend_event_url="http://localhost:8000/builder/event",
        )

    with pytest.raises(ValueError, match="already started"):
        await manager.start_session(
            session_id="dup-id",
            url="https://example.com",
            backend_event_url="http://localhost:8000/builder/event",
        )


@pytest.mark.asyncio
async def test_stop_session_noop_when_missing() -> None:
    manager = PlaywrightManager()
    manager._sessions = {}

    await manager.stop_session("missing")


@pytest.mark.asyncio
async def test_stop_session_closes_runtime_resources() -> None:
    manager = PlaywrightManager()
    manager._sessions = {}

    fake_session = BuilderRuntimeSession(
        session_id="s1",
        playwright=MagicMock(stop=AsyncMock()),
        browser=MagicMock(close=AsyncMock()),
        context=MagicMock(close=AsyncMock()),
        page=MagicMock(),
    )
    manager._sessions["s1"] = fake_session

    await manager.stop_session("s1")

    fake_session.context.close.assert_awaited_once()
    fake_session.browser.close.assert_awaited_once()
    fake_session.playwright.stop.assert_awaited_once()
    assert "s1" not in manager._sessions


@pytest.mark.asyncio
async def test_shutdown_stops_all_sessions() -> None:
    manager = PlaywrightManager()
    manager._sessions = {"a": MagicMock(), "b": MagicMock()}  # type: ignore[assignment]

    with patch.object(manager, "stop_session", new=AsyncMock()) as stop_mock:
        await manager.shutdown()

    assert stop_mock.await_count == 2
    stop_mock.assert_any_await("a")
    stop_mock.assert_any_await("b")
