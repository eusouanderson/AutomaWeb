import pytest
import pytest_asyncio
import importlib

import app.services.element_scanner as scanner_module
from app.services.element_scanner import ElementScannerError, ElementScannerService


class FakePage:
    def set_default_timeout(self, timeout):
        self.timeout = timeout

    async def goto(self, url, wait_until, timeout):
        self.url = url
        self.wait_until = wait_until
        self.goto_timeout = timeout

    async def wait_for_load_state(self, state, timeout):
        self.state = state
        self.state_timeout = timeout

    async def evaluate(self, script):
        return [
            {
                "type": "input",
                "selector": "#email",
                "xpath": "//*[@id='email']",
                "name": "email",
                "id": "email",
                "placeholder": "Email",
                "required": True,
            },
            {
                "type": "button",
                "selector": "button:nth-of-type(1)",
                "xpath": "/html/body/button[1]",
                "text": "Entrar",
            },
        ]

    async def title(self):
        return "Login"


class FakeContext:
    async def route(self, pattern, handler):
        self.pattern = pattern
        self.handler = handler

    async def new_page(self):
        return FakePage()

    async def close(self):
        return None


class FakeBrowser:
    async def new_context(self, ignore_https_errors, service_workers=None):
        self.ignore_https_errors = ignore_https_errors
        self.service_workers = service_workers
        return FakeContext()

    async def close(self):
        return None


class FakeChromium:
    async def launch(self, headless):
        self.headless = headless
        return FakeBrowser()


class FakePlaywright:
    chromium = FakeChromium()

    async def stop(self):
        return None


class FakePlaywrightManager:
    async def start(self):
        return FakePlaywright()

    async def stop(self):
        return None


@pytest_asyncio.fixture(autouse=True)
async def reset_shared_state():
    ElementScannerService._shared_browser = None
    ElementScannerService._shared_playwright = None
    yield
    ElementScannerService._shared_browser = None
    ElementScannerService._shared_playwright = None


@pytest.mark.asyncio
async def test_scan_url_success(monkeypatch):
    scanner = ElementScannerService(timeout_ms=5000)
    progress_messages = []

    async def progress_callback(message: str):
        progress_messages.append(message)

    monkeypatch.setattr("app.services.element_scanner.async_playwright", lambda: FakePlaywrightManager())

    result = await scanner.scan_url("https://example.com", progress_callback=progress_callback)

    assert result.url == "https://example.com"
    assert result.title == "Login"
    assert result.total_elements == 2
    assert result.summary["input"] == 1
    assert result.summary["button"] == 1
    assert any("Loading page" in msg for msg in progress_messages)
    assert progress_messages[-1] == "Scan complete."


@pytest.mark.asyncio
async def test_scan_url_raises_when_playwright_not_installed(monkeypatch):
    scanner = ElementScannerService(timeout_ms=5000)
    monkeypatch.setattr(scanner_module, "async_playwright", None)

    with pytest.raises(ElementScannerError, match="Playwright is not installed"):
        await scanner.scan_url("https://example.com")


class TimeoutOnGotoPage(FakePage):
    async def goto(self, url, wait_until, timeout):
        raise scanner_module.PlaywrightTimeoutError("navigation timeout")


class TimeoutOnWaitStatePage(FakePage):
    async def wait_for_load_state(self, state, timeout):
        raise scanner_module.PlaywrightTimeoutError("network idle timeout")


class ErrorOnEvaluatePage(FakePage):
    async def evaluate(self, script):
        raise RuntimeError("boom")


class CustomPageContext(FakeContext):
    def __init__(self, page):
        self._page = page

    async def new_page(self):
        return self._page


class CustomPageBrowser(FakeBrowser):
    def __init__(self, page):
        self._page = page

    async def new_context(self, ignore_https_errors, service_workers=None):
        self.ignore_https_errors = ignore_https_errors
        self.service_workers = service_workers
        return CustomPageContext(self._page)


class CustomPagePlaywright(FakePlaywright):
    def __init__(self, page):
        self.chromium = self
        self._page = page

    async def launch(self, headless):
        return CustomPageBrowser(self._page)


class CustomPagePlaywrightManager(FakePlaywrightManager):
    def __init__(self, page):
        self._page = page

    async def start(self):
        return CustomPagePlaywright(self._page)


@pytest.mark.asyncio
async def test_scan_url_continues_after_navigation_timeout(monkeypatch):
    scanner = ElementScannerService(timeout_ms=5000)
    progress_messages = []

    async def progress_callback(message: str):
        progress_messages.append(message)

    monkeypatch.setattr(
        scanner_module,
        "async_playwright",
        lambda: CustomPagePlaywrightManager(TimeoutOnGotoPage()),
    )

    result = await scanner.scan_url("https://example.com", progress_callback=progress_callback)
    assert result.title == "Login"
    assert any("Navigation timeout reached" in msg for msg in progress_messages)


@pytest.mark.asyncio
async def test_scan_url_continues_after_network_idle_timeout(monkeypatch):
    scanner = ElementScannerService(timeout_ms=5000)
    progress_messages = []

    async def progress_callback(message: str):
        progress_messages.append(message)

    monkeypatch.setattr(
        scanner_module,
        "async_playwright",
        lambda: CustomPagePlaywrightManager(TimeoutOnWaitStatePage()),
    )

    result = await scanner.scan_url("https://example.com", progress_callback=progress_callback)
    assert result.title == "Login"
    assert any("Network idle timeout reached" in msg for msg in progress_messages)


@pytest.mark.asyncio
async def test_scan_url_wraps_unexpected_exception(monkeypatch):
    scanner = ElementScannerService(timeout_ms=5000)
    monkeypatch.setattr(
        scanner_module,
        "async_playwright",
        lambda: CustomPagePlaywrightManager(ErrorOnEvaluatePage()),
    )

    with pytest.raises(ElementScannerError, match="Scan failed: boom"):
        await scanner.scan_url("https://example.com")


class FakeRequest:
    def __init__(self, resource_type: str):
        self.resource_type = resource_type


class FakeRoute:
    def __init__(self, resource_type: str):
        self.request = FakeRequest(resource_type)
        self.aborted = False
        self.continued = False

    async def abort(self):
        self.aborted = True

    async def continue_(self):
        self.continued = True


@pytest.mark.asyncio
async def test_route_filter_blocks_binary_assets():
    scanner = ElementScannerService()
    route = FakeRoute("image")

    await scanner._route_filter(route)

    assert route.aborted is True
    assert route.continued is False


@pytest.mark.asyncio
async def test_route_filter_continues_other_assets():
    scanner = ElementScannerService()
    route = FakeRoute("document")

    await scanner._route_filter(route)

    assert route.aborted is False
    assert route.continued is True


class DummyAsyncLock:
    def __init__(self, on_enter=None):
        self._on_enter = on_enter

    async def __aenter__(self):
        if self._on_enter:
            self._on_enter()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_get_shared_browser_returns_existing_instance():
    sentinel_browser = object()
    ElementScannerService._shared_browser = sentinel_browser

    browser = await ElementScannerService._get_shared_browser()

    assert browser is sentinel_browser


@pytest.mark.asyncio
async def test_get_shared_browser_returns_instance_set_inside_lock(monkeypatch):
    sentinel_browser = object()

    def set_shared_browser_inside_lock():
        ElementScannerService._shared_browser = sentinel_browser

    monkeypatch.setattr(
        ElementScannerService,
        "_browser_lock",
        DummyAsyncLock(on_enter=set_shared_browser_inside_lock),
    )

    browser = await ElementScannerService._get_shared_browser()

    assert browser is sentinel_browser


class ClosableBrowser:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class StoppablePlaywright:
    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


@pytest.mark.asyncio
async def test_close_shared_browser_closes_and_stops(monkeypatch):
    browser = ClosableBrowser()
    playwright = StoppablePlaywright()
    ElementScannerService._shared_browser = browser
    ElementScannerService._shared_playwright = playwright
    monkeypatch.setattr(ElementScannerService, "_browser_lock", DummyAsyncLock())

    await ElementScannerService.close_shared_browser()

    assert browser.closed is True
    assert playwright.stopped is True
    assert ElementScannerService._shared_browser is None
    assert ElementScannerService._shared_playwright is None


def test_import_fallback_without_playwright(monkeypatch):
    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "playwright.async_api":
            raise ModuleNotFoundError("playwright missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    reloaded = importlib.reload(scanner_module)

    assert reloaded.async_playwright is None
    assert reloaded.PlaywrightTimeoutError is TimeoutError

    monkeypatch.setattr("builtins.__import__", original_import)
    importlib.reload(scanner_module)
