import asyncio
from typing import Any, Awaitable, Callable

import pytest

from app.builder.playwright_manager import PlaywrightManager, _capture_script


class FakePage:
    def __init__(self) -> None:
        self.goto_urls: list[str] = []
        self.goto_kwargs: list[dict[str, Any]] = []
        self.default_timeout_values: list[float] = []
        self.default_navigation_timeout_values: list[float] = []

    def set_default_timeout(self, timeout: float) -> None:
        self.default_timeout_values.append(timeout)

    def set_default_navigation_timeout(self, timeout: float) -> None:
        self.default_navigation_timeout_values.append(timeout)

    async def goto(self, url: str, **kwargs: Any) -> None:
        self.goto_urls.append(url)
        self.goto_kwargs.append(kwargs)


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.bound: list[
            tuple[str, Callable[[Any, Any], Awaitable[None]]]
        ] = []
        self.scripts: list[str] = []
        self.closed = False
        self.default_timeout_values: list[float] = []
        self.default_navigation_timeout_values: list[float] = []

    def set_default_timeout(self, timeout: float) -> None:
        self.default_timeout_values.append(timeout)

    def set_default_navigation_timeout(self, timeout: float) -> None:
        self.default_navigation_timeout_values.append(timeout)

    async def expose_binding(self, name: str, callback) -> None:
        self.bound.append((name, callback))

    async def add_init_script(self, script: str) -> None:
        self.scripts.append(script)

    async def new_page(self) -> FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.closed = False

    async def new_context(self):
        return self.context

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.headless_args: list[bool] = []

    async def launch(self, headless: bool = False) -> FakeBrowser:
        self.headless_args.append(headless)
        return self.browser


class FakePlaywright:
    def __init__(self, chromium: FakeChromium) -> None:
        self.chromium = chromium
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class FakeStarter:
    def __init__(self, playwright: FakePlaywright) -> None:
        self.playwright = playwright
        self.started = False

    async def start(self) -> FakePlaywright:
        self.started = True
        return self.playwright


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    PlaywrightManager._instance = None


def test_playwright_manager_is_singleton_and_skips_reinitialization() -> None:
    first = PlaywrightManager()
    original_lock = first._lock

    second = PlaywrightManager()

    assert second is first
    assert second._lock is original_lock


def test_capture_script_embeds_bridge_and_contextmenu_trigger() -> None:
    script = _capture_script('session"1', 'https://api.example.com/builder/event')

    assert '__awRecordBuilderEvent' in script
    assert 'contextmenu' in script
    assert 'Salvar Step' in script
    assert 'https://api.example.com/builder/event' in script
    assert 'SESSION_ID = "session\\"1"' in script


@pytest.mark.asyncio
async def test_start_session_registers_binding_and_runtime(monkeypatch) -> None:
    manager = PlaywrightManager()
    page = FakePage()
    context = FakeContext(page)
    browser = FakeBrowser(context)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)
    starter = FakeStarter(playwright)
    captured_payloads: list[dict] = []

    monkeypatch.setattr(
        'app.builder.playwright_manager.async_playwright', lambda: starter
    )

    async def _handler(payload: dict) -> None:
        captured_payloads.append(payload)

    await manager.start_session(
        session_id='session-1',
        url='https://example.com',
        backend_event_url='https://backend.example.com/builder/event',
        event_handler=_handler,
    )

    assert starter.started is True
    assert chromium.headless_args == [False]
    assert page.goto_urls == ['https://example.com']
    assert page.goto_kwargs == [{'wait_until': 'domcontentloaded', 'timeout': 0}]
    assert context.default_timeout_values == [0]
    assert context.default_navigation_timeout_values == [0]
    assert page.default_timeout_values == [0]
    assert page.default_navigation_timeout_values == [0]
    assert len(context.scripts) == 1
    assert 'https://backend.example.com/builder/event' in context.scripts[0]
    assert context.bound[0][0] == '__awRecordBuilderEvent'
    assert 'session-1' in manager._sessions

    await context.bound[0][1](None, {'selector': '#login'})
    await asyncio.sleep(0)
    assert captured_payloads == [{'selector': '#login'}]


@pytest.mark.asyncio
async def test_start_session_rejects_duplicate_session(monkeypatch) -> None:
    manager = PlaywrightManager()
    page = FakePage()
    context = FakeContext(page)
    browser = FakeBrowser(context)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)
    starter = FakeStarter(playwright)

    monkeypatch.setattr(
        'app.builder.playwright_manager.async_playwright', lambda: starter
    )

    await manager.start_session(
        session_id='session-1',
        url='https://example.com',
        backend_event_url='https://backend.example.com/builder/event',
    )

    with pytest.raises(ValueError, match="already started"):
        await manager.start_session(
            session_id='session-1',
            url='https://example.com',
            backend_event_url='https://backend.example.com/builder/event',
        )


@pytest.mark.asyncio
async def test_stop_session_closes_resources_and_missing_session_is_noop(monkeypatch) -> None:
    manager = PlaywrightManager()
    page = FakePage()
    context = FakeContext(page)
    browser = FakeBrowser(context)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)
    starter = FakeStarter(playwright)

    monkeypatch.setattr(
        'app.builder.playwright_manager.async_playwright', lambda: starter
    )

    await manager.start_session(
        session_id='session-1',
        url='https://example.com',
        backend_event_url='https://backend.example.com/builder/event',
    )

    await manager.stop_session('session-1')

    assert context.closed is True
    assert browser.closed is True
    assert playwright.stopped is True
    assert 'session-1' not in manager._sessions

    await manager.stop_session('missing-session')


@pytest.mark.asyncio
async def test_shutdown_stops_all_sessions(monkeypatch) -> None:
    manager = PlaywrightManager()
    first_page = FakePage()
    first_context = FakeContext(first_page)
    first_browser = FakeBrowser(first_context)
    first_playwright = FakePlaywright(FakeChromium(first_browser))

    second_page = FakePage()
    second_context = FakeContext(second_page)
    second_browser = FakeBrowser(second_context)
    second_playwright = FakePlaywright(FakeChromium(second_browser))

    starters = [FakeStarter(first_playwright), FakeStarter(second_playwright)]

    def _starter_factory():
        return starters.pop(0)

    monkeypatch.setattr(
        'app.builder.playwright_manager.async_playwright', _starter_factory
    )

    await manager.start_session(
        session_id='session-1',
        url='https://example.com/1',
        backend_event_url='https://backend.example.com/builder/event',
    )
    await manager.start_session(
        session_id='session-2',
        url='https://example.com/2',
        backend_event_url='https://backend.example.com/builder/event',
    )

    await manager.shutdown()

    assert manager._sessions == {}
    assert first_context.closed is True
    assert second_context.closed is True
    assert first_browser.closed is True
    assert second_browser.closed is True
    assert first_playwright.stopped is True
    assert second_playwright.stopped is True