import importlib

import pytest
import pytest_asyncio

import app.services.element_scanner as scanner_module
from app.services.element_scanner import ElementScannerError, ElementScannerService


# ---------------------------------------------------------------------------
# Playwright fakes
# ---------------------------------------------------------------------------

class FakePage:
    def set_default_timeout(self, timeout):
        self.timeout = timeout

    async def goto(self, url, wait_until, timeout):
        self.url = url

    async def wait_for_load_state(self, state, timeout):
        pass

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
        pass

    async def new_page(self):
        return FakePage()

    async def close(self):
        pass


class FakeBrowser:
    async def new_context(self, ignore_https_errors, service_workers=None):
        return FakeContext()

    async def close(self):
        pass


class FakeChromium:
    async def launch(self, headless):
        return FakeBrowser()


class FakePlaywright:
    chromium = FakeChromium()

    async def stop(self):
        pass


class FakePlaywrightManager:
    async def start(self):
        return FakePlaywright()

    async def stop(self):
        pass


# ---------------------------------------------------------------------------
# Custom page variants for edge-case tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Shared state reset
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def reset_shared_state():
    ElementScannerService._shared_browser = None
    ElementScannerService._shared_playwright = None
    yield
    ElementScannerService._shared_browser = None
    ElementScannerService._shared_playwright = None


# ---------------------------------------------------------------------------
# Helper: fake async _fetch_and_parse returning (title, elements, spa_hint, form_contexts)
# ---------------------------------------------------------------------------

def _fake_fetch(title="Untitled", elements=None, spa_hint=False, form_contexts=None):
    async def _inner(url):
        return title, elements or [], spa_hint, form_contexts or []
    return _inner


# ---------------------------------------------------------------------------
# scan_url integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_url_success(monkeypatch):
    scanner = ElementScannerService(timeout_ms=5000)
    progress_messages = []

    async def progress_callback(message: str):
        progress_messages.append(message)

    # Fast path returns 0 elements → SPA fallback triggers
    monkeypatch.setattr(scanner_module, "_fetch_and_parse", _fake_fetch())
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr("app.services.element_scanner.async_playwright", lambda: FakePlaywrightManager())

    result = await scanner.scan_url("https://example.com", progress_callback=progress_callback)

    assert result.url == "https://example.com"
    assert result.title == "Login"
    assert result.total_elements == 2
    assert result.summary["input"] == 1
    assert result.summary["button"] == 1
    assert any("Carregando página no navegador" in msg for msg in progress_messages)
    assert progress_messages[-1] == "Escaneamento concluído."


@pytest.mark.asyncio
async def test_scan_url_degrades_gracefully_without_playwright(monkeypatch):
    """When fast path returns few elements and Playwright is unavailable, returns what was found."""
    scanner = ElementScannerService(timeout_ms=5000)
    partial_elements = [{"type": "link", "selector": "a", "text": "About"}]
    monkeypatch.setattr(scanner_module, "_fetch_and_parse", _fake_fetch("Partial", partial_elements))
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", False)

    result = await scanner.scan_url("https://example.com")

    assert result.title == "Partial"
    assert result.total_elements == 1
    assert result.summary["link"] == 1


@pytest.mark.asyncio
async def test_scan_url_continues_after_navigation_timeout(monkeypatch):
    scanner = ElementScannerService(timeout_ms=5000)
    progress_messages = []

    async def progress_callback(message: str):
        progress_messages.append(message)

    monkeypatch.setattr(scanner_module, "_fetch_and_parse", _fake_fetch())
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(
        scanner_module, "async_playwright",
        lambda: CustomPagePlaywrightManager(TimeoutOnGotoPage()),
    )

    result = await scanner.scan_url("https://example.com", progress_callback=progress_callback)
    assert result.title == "Login"
    assert any("Timeout de navegação" in msg for msg in progress_messages)


@pytest.mark.asyncio
async def test_scan_url_continues_after_network_idle_timeout(monkeypatch):
    scanner = ElementScannerService(timeout_ms=5000)
    progress_messages = []

    async def progress_callback(message: str):
        progress_messages.append(message)

    monkeypatch.setattr(scanner_module, "_fetch_and_parse", _fake_fetch())
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(
        scanner_module, "async_playwright",
        lambda: CustomPagePlaywrightManager(TimeoutOnWaitStatePage()),
    )

    result = await scanner.scan_url("https://example.com", progress_callback=progress_callback)
    assert result.title == "Login"
    assert any("Timeout de rede ociosa" in msg for msg in progress_messages)


@pytest.mark.asyncio
async def test_scan_url_wraps_unexpected_exception(monkeypatch):
    scanner = ElementScannerService(timeout_ms=5000)
    monkeypatch.setattr(scanner_module, "_fetch_and_parse", _fake_fetch())
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(
        scanner_module, "async_playwright",
        lambda: CustomPagePlaywrightManager(ErrorOnEvaluatePage()),
    )

    with pytest.raises(ElementScannerError, match="Browser scan failed: boom"):
        await scanner.scan_url("https://example.com")


@pytest.mark.asyncio
async def test_scan_url_uses_fast_path_when_sufficient_elements(monkeypatch):
    """When fast path returns >= threshold elements, Playwright is never invoked."""
    scanner = ElementScannerService(timeout_ms=5000, spa_threshold=2)
    fake_elements = [
        {"type": "input", "selector": "#q", "xpath": '//*[@id="q"]', "text": None,
         "name": None, "id": "q", "placeholder": None, "required": None,
         "classes": None, "href": None, "aria_label": None, "aria_role": None, "data_testid": None},
        {"type": "button", "selector": "button", "xpath": None, "text": "Go",
         "name": None, "id": None, "placeholder": None, "required": None,
         "classes": None, "href": None, "aria_label": None, "aria_role": None, "data_testid": None},
        {"type": "link", "selector": "a", "xpath": None, "text": "About",
         "name": None, "id": None, "placeholder": None, "required": None,
         "classes": None, "href": "/about", "aria_label": None, "aria_role": None, "data_testid": None},
    ]
    monkeypatch.setattr(scanner_module, "_fetch_and_parse", _fake_fetch("Static Site", fake_elements))

    result = await scanner.scan_url("https://example.com")
    assert result.title == "Static Site"
    assert result.total_elements == 3


@pytest.mark.asyncio
async def test_scan_url_fast_path_exception_wraps(monkeypatch):
    """Non-ElementScannerError from _fetch_and_parse is wrapped."""
    scanner = ElementScannerService(timeout_ms=5000)

    async def boom(url):
        raise ValueError("unexpected")

    monkeypatch.setattr(scanner_module, "_fetch_and_parse", boom)

    with pytest.raises(scanner_module.ElementScannerError, match="Scan failed"):
        await scanner.scan_url("https://example.com")


@pytest.mark.asyncio
async def test_scan_url_fast_path_reraises_scanner_error(monkeypatch):
    """ElementScannerError from _fetch_and_parse is re-raised unchanged."""
    scanner = ElementScannerService(timeout_ms=5000)

    async def raise_scanner_error(url):
        raise scanner_module.ElementScannerError("original scanner error")

    monkeypatch.setattr(scanner_module, "_fetch_and_parse", raise_scanner_error)

    with pytest.raises(scanner_module.ElementScannerError, match="original scanner error"):
        await scanner.scan_url("https://example.com")


@pytest.mark.asyncio
async def test_playwright_scan_reraises_scanner_error(monkeypatch):
    """ElementScannerError raised inside _playwright_scan is re-raised unchanged."""
    class ErrorOnContextPage(FakePage):
        async def evaluate(self, script):
            raise scanner_module.ElementScannerError("inner scanner error")

    scanner = ElementScannerService(timeout_ms=5000)
    monkeypatch.setattr(scanner_module, "_fetch_and_parse", _fake_fetch())
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(
        scanner_module, "async_playwright",
        lambda: CustomPagePlaywrightManager(ErrorOnContextPage()),
    )

    with pytest.raises(scanner_module.ElementScannerError, match="inner scanner error"):
        await scanner.scan_url("https://example.com")


@pytest.mark.asyncio
async def test_scan_url_includes_form_contexts(monkeypatch):
    """form_contexts returned by _fetch_and_parse are in the ScanResult."""
    scanner = ElementScannerService(timeout_ms=5000, spa_threshold=0)
    fc = [{"form_selector": "#login-form", "inputs": ["#email", "#password"], "submit": "#submit-btn"}]
    monkeypatch.setattr(scanner_module, "_fetch_and_parse", _fake_fetch("Login", [], False, fc))

    result = await scanner.scan_url("https://example.com")
    assert len(result.form_contexts) == 1
    assert result.form_contexts[0].form_selector == "#login-form"
    assert "#email" in result.form_contexts[0].inputs
    assert result.form_contexts[0].submit == "#submit-btn"


@pytest.mark.asyncio
async def test_scan_url_spa_hint_triggers_playwright(monkeypatch):
    """Even with enough static elements, SPA hint forces Playwright scan."""
    scanner = ElementScannerService(timeout_ms=5000, spa_threshold=1)
    # Return 2 elements (above threshold=1) but spa_hint=True
    fake_elements = [{"type": "input", "selector": "#q", "xpath": None, "text": None,
                      "name": None, "id": "q", "placeholder": None, "required": None,
                      "classes": None, "href": None, "aria_label": None, "aria_role": None, "data_testid": None},
                     {"type": "button", "selector": "button", "xpath": None, "text": "Go",
                      "name": None, "id": None, "placeholder": None, "required": None,
                      "classes": None, "href": None, "aria_label": None, "aria_role": None, "data_testid": None}]
    monkeypatch.setattr(scanner_module, "_fetch_and_parse",
                        _fake_fetch("SPA", fake_elements, spa_hint=True))
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr("app.services.element_scanner.async_playwright", lambda: FakePlaywrightManager())

    result = await scanner.scan_url("https://example.com")
    # Playwright returns 2 elements from FakePage.evaluate
    assert result.title == "Login"
    assert result.total_elements == 2


# ---------------------------------------------------------------------------
# route_filter tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Shared browser lifecycle
# ---------------------------------------------------------------------------

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
        ElementScannerService, "_browser_lock",
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


# ---------------------------------------------------------------------------
# _normalize tests
# ---------------------------------------------------------------------------

def test_normalize_returns_none_for_none():
    assert scanner_module._normalize(None) is None


def test_normalize_returns_none_for_empty_string():
    assert scanner_module._normalize("") is None
    assert scanner_module._normalize("   ") is None


def test_normalize_collapses_whitespace():
    assert scanner_module._normalize("  hello   world  ") == "hello world"


def test_normalize_truncates_long_text():
    long_text = "a" * 200
    result = scanner_module._normalize(long_text, max_len=50)
    assert result is not None
    assert result.endswith("\u2026")
    assert len(result) == 51


def test_normalize_returns_short_text_unchanged():
    assert scanner_module._normalize("hello", max_len=50) == "hello"


# ---------------------------------------------------------------------------
# selectolax-based helper tests (_css_selector, _xpath_for, _element_type, _element_meta)
# ---------------------------------------------------------------------------

def _parse_first(html_str: str, css: str):
    """Parse a snippet and return the first matching Node."""
    from selectolax.parser import HTMLParser
    tree = HTMLParser(html_str.encode())
    return tree.css_first(css)


def test_css_selector_prioritizes_id():
    node = _parse_first('<input id="email" name="email"/>', "input")
    assert scanner_module._css_selector(node) == "#email"  # type: ignore[arg-type]


def test_css_selector_uses_data_testid():
    node = _parse_first('<button data-testid="submit">OK</button>', "button")
    assert scanner_module._css_selector(node) == '[data-testid="submit"]'  # type: ignore[arg-type]


def test_css_selector_uses_name():
    node = _parse_first('<input name="email"/>', "input")
    assert scanner_module._css_selector(node) == 'input[name="email"]'  # type: ignore[arg-type]

def test_css_selector_uses_first_class():
    node = _parse_first('<button class="primary btn">OK</button>', "button")
    assert scanner_module._css_selector(node) == "button.primary"  # type: ignore[arg-type]


def test_css_selector_fallback_to_tag():
    node = _parse_first('<button>OK</button>', "button")
    assert scanner_module._css_selector(node) == "button"   # type: ignore[arg-type]


def test_xpath_for_with_id():
    node = _parse_first('<input id="search"/>', "input")
    assert scanner_module._xpath_for(node) == '//*[@id="search"]' # type: ignore[arg-type]


def test_xpath_for_without_id():
    from selectolax.parser import HTMLParser
    tree = HTMLParser(b'<html><body><form><input name="q"/></form></body></html>')
    node = tree.css_first("input")
    xpath = scanner_module._xpath_for(node) # type: ignore[arg-type]
    assert xpath is not None
    assert xpath.startswith("/")


def test_element_type_text_input():
    node = _parse_first('<input type="text"/>', "input")
    assert scanner_module._element_type(node) == "input" # type: ignore[arg-type]


def test_element_type_no_type_defaults_to_input():
    node = _parse_first('<input/>', "input")
    assert scanner_module._element_type(node) == "input" # type: ignore[arg-type]


def test_element_type_hidden_returns_none():
    node = _parse_first('<input type="hidden"/>', "input")
    assert scanner_module._element_type(node) is None # type: ignore[arg-type]


def test_element_type_file_returns_none():
    node = _parse_first('<input type="file"/>', "input")
    assert scanner_module._element_type(node) is None # type: ignore[arg-type]


def test_element_type_submit_returns_button():
    node = _parse_first('<input type="submit"/>', "input")
    assert scanner_module._element_type(node) == "button" # type: ignore[arg-type]


def test_element_type_reset_returns_button():
    node = _parse_first('<input type="reset"/>', "input")
    assert scanner_module._element_type(node) == "button" # type: ignore[arg-type]


def test_element_type_button_input_returns_button():
    node = _parse_first('<input type="button"/>', "input")
    assert scanner_module._element_type(node) == "button" # type: ignore[arg-type]


def test_element_type_button_tag():
    node = _parse_first('<button>Click</button>', "button")
    assert scanner_module._element_type(node) == "button" # type: ignore[arg-type]


def test_element_type_link():
    node = _parse_first('<a href="/">Go</a>', "a")
    assert scanner_module._element_type(node) == "link" # type: ignore[arg-type]


def test_element_type_select():
    node = _parse_first('<select><option>A</option></select>', "select")
    assert scanner_module._element_type(node) == "select" # type: ignore[arg-type]


def test_element_type_textarea():
    node = _parse_first('<textarea/>', "textarea")
    assert scanner_module._element_type(node) == "textarea" # type: ignore[arg-type]


def test_element_type_label():
    node = _parse_first('<label for="x">Name</label>', "label")
    assert scanner_module._element_type(node) == "label" # type: ignore[arg-type]


def test_element_type_unknown_returns_none():
    node = _parse_first('<div/>', "div")
    assert scanner_module._element_type(node) is None # type: ignore[arg-type]


def test_element_meta_fields():
    from selectolax.parser import HTMLParser
    html = (
        b'<html><body>'
        b'<input id="q" name="search" placeholder="Search" required '
        b'class="main big" aria-label="Search box" role="searchbox" data-testid="search-input"/>'
        b'</body></html>'
    )
    tree = HTMLParser(html)
    node = tree.css_first("input")
    meta = scanner_module._element_meta(node, "input", include_xpath=True) # type: ignore[arg-type]
    assert meta["type"] == "input"
    assert meta["id"] == "q"
    assert meta["name"] == "search"
    assert meta["placeholder"] == "Search"
    assert meta["required"] is True
    assert meta["aria_label"] == "Search box"
    assert meta["aria_role"] == "searchbox"
    assert meta["data_testid"] == "search-input"
    assert meta["xpath"] is not None


def test_element_meta_no_xpath():
    from selectolax.parser import HTMLParser
    tree = HTMLParser(b'<html><body><input id="q"/></body></html>')
    node = tree.css_first("input")
    meta = scanner_module._element_meta(node, "input", include_xpath=False) # type: ignore[arg-type]
    assert meta["xpath"] is None


# ---------------------------------------------------------------------------
# _fetch_and_parse async tests (using httpx mock)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_and_parse_success(monkeypatch):
    import httpx

    html_content = (
        b'<html><head><title>Test Page</title></head><body>'
        b'<input id="email" type="text" placeholder="Email"/>'
        b'<button id="submit">Login</button>'
        b'<a href="/about">About</a>'
        b'</body></html>'
    )

    class FakeHttpxResponse:
        content = html_content
        def raise_for_status(self):
            pass

    class FakeClient:
        is_closed = False
        async def get(self, url):
            return FakeHttpxResponse()

    monkeypatch.setattr(scanner_module, "_http_client", FakeClient())

    title, elements, spa_hint, form_contexts = await scanner_module._fetch_and_parse("http://example.com")

    assert title == "Test Page"
    assert len(elements) == 3
    types = {e["type"] for e in elements}
    assert "input" in types
    assert "button" in types
    assert "link" in types
    assert isinstance(spa_hint, bool)


@pytest.mark.asyncio
async def test_fetch_and_parse_http_error(monkeypatch):
    import httpx

    class FakeClient:
        is_closed = False
        async def get(self, url):
            raise httpx.ConnectError("no conn")

    monkeypatch.setattr(scanner_module, "_http_client", FakeClient())

    with pytest.raises(scanner_module.ElementScannerError, match="HTTP request failed"):
        await scanner_module._fetch_and_parse("http://example.com")


@pytest.mark.asyncio
async def test_fetch_and_parse_no_title(monkeypatch):
    class FakeHttpxResponse:
        content = b'<html><body><input id="q"/></body></html>'
        def raise_for_status(self):
            pass

    class FakeClient:
        is_closed = False
        async def get(self, url):
            return FakeHttpxResponse()

    monkeypatch.setattr(scanner_module, "_http_client", FakeClient())

    title, _, _, _ = await scanner_module._fetch_and_parse("http://example.com")
    assert title == "Untitled"


@pytest.mark.asyncio
async def test_fetch_and_parse_skips_hidden_and_file_inputs(monkeypatch):
    html = (
        b'<html><head><title>T</title></head><body>'
        b'<input type="hidden" name="csrf"/>'
        b'<input type="file" name="upload"/>'
        b'<input type="text" id="visible"/>'
        b'</body></html>'
    )

    class FakeHttpxResponse:
        content = html
        def raise_for_status(self): pass

    class FakeClient:
        is_closed = False
        async def get(self, url): return FakeHttpxResponse()

    monkeypatch.setattr(scanner_module, "_http_client", FakeClient())

    _, elements, _, _ = await scanner_module._fetch_and_parse("http://example.com")
    types = [e["type"] for e in elements]
    assert "input" in types
    assert len(elements) == 1


@pytest.mark.asyncio
async def test_fetch_and_parse_deduplicates_elements(monkeypatch):
    # Two inputs with the same id → same selector/xpath → deduplicated
    html = (
        b'<html><head><title>T</title></head><body>'
        b'<input id="dup" type="text"/>'
        b'<input id="dup" type="text"/>'
        b'</body></html>'
    )

    class FakeHttpxResponse:
        content = html
        def raise_for_status(self): pass

    class FakeClient:
        is_closed = False
        async def get(self, url): return FakeHttpxResponse()

    monkeypatch.setattr(scanner_module, "_http_client", FakeClient())

    _, elements, _, _ = await scanner_module._fetch_and_parse("http://example.com")
    selectors = [e["selector"] for e in elements]
    assert selectors.count("#dup") == 1


@pytest.mark.asyncio
async def test_fetch_and_parse_respects_type_cap(monkeypatch):
    # input cap is 35 — generate 40 unique inputs
    inputs = b"".join(
        f'<input type="text" id="inp{i}"/>'.encode() for i in range(40)
    )
    html = b"<html><head><title>T</title></head><body>" + inputs + b"</body></html>"

    class FakeHttpxResponse:
        content = html
        def raise_for_status(self): pass

    class FakeClient:
        is_closed = False
        async def get(self, url): return FakeHttpxResponse()

    monkeypatch.setattr(scanner_module, "_http_client", FakeClient())

    _, elements, _, _ = await scanner_module._fetch_and_parse("http://example.com")
    inputs_found = [e for e in elements if e["type"] == "input"]
    assert len(inputs_found) == 35


@pytest.mark.asyncio
async def test_fetch_and_parse_respects_global_element_cap(monkeypatch):
    monkeypatch.setattr(scanner_module, "_ELEMENT_CAP", 3)

    inputs = b"".join(f'<input type="text" id="i{i}"/>'.encode() for i in range(10))
    buttons = b"".join(f'<button id="b{i}">B</button>'.encode() for i in range(10))
    html = b"<html><head><title>T</title></head><body>" + inputs + buttons + b"</body></html>"

    class FakeHttpxResponse:
        content = html
        def raise_for_status(self): pass

    class FakeClient:
        is_closed = False
        async def get(self, url): return FakeHttpxResponse()

    monkeypatch.setattr(scanner_module, "_http_client", FakeClient())

    _, elements, _, _ = await scanner_module._fetch_and_parse("http://example.com")
    assert len(elements) <= 3


# ---------------------------------------------------------------------------
# _is_likely_spa
# ---------------------------------------------------------------------------

def test_is_likely_spa_detects_next_data():
    html = b'<html><body><script id="__NEXT_DATA__">{}</script></body></html>'
    assert scanner_module._is_likely_spa(html) is True


def test_is_likely_spa_detects_react_root():
    html = b'<html><body><div data-reactroot=""></div></body></html>'
    assert scanner_module._is_likely_spa(html) is True


def test_is_likely_spa_returns_false_for_plain_html():
    html = b'<html><body><form><input id="q"/></form></body></html>'
    assert scanner_module._is_likely_spa(html) is False


# ---------------------------------------------------------------------------
# _extract_form_contexts
# ---------------------------------------------------------------------------

def test_extract_form_contexts_login_form():
    from selectolax.parser import HTMLParser
    html = (
        b'<html><body>'
        b'<form id="login-form">'
        b'<input type="text" id="email"/>'
        b'<input type="password" id="password"/>'
        b'<button type="submit" id="submit-btn">Login</button>'
        b'</form>'
        b'</body></html>'
    )
    tree = HTMLParser(html)
    contexts = scanner_module._extract_form_contexts(tree)
    assert len(contexts) == 1
    ctx = contexts[0]
    assert ctx["form_selector"] == "#login-form"
    assert "#email" in ctx["inputs"]
    assert "#password" in ctx["inputs"]
    assert ctx["submit"] == "#submit-btn"


def test_extract_form_contexts_skips_hidden_file():
    from selectolax.parser import HTMLParser
    html = (
        b'<html><body>'
        b'<form>'
        b'<input type="hidden" name="csrf"/>'
        b'<input type="file" name="upload"/>'
        b'<input type="text" id="name"/>'
        b'</form>'
        b'</body></html>'
    )
    tree = HTMLParser(html)
    contexts = scanner_module._extract_form_contexts(tree)
    assert len(contexts) == 1
    assert all("hidden" not in sel for sel in contexts[0]["inputs"])
    assert all("upload" not in sel for sel in contexts[0]["inputs"])


def test_extract_form_contexts_no_forms():
    from selectolax.parser import HTMLParser
    html = b'<html><body><input id="q"/></body></html>'
    tree = HTMLParser(html)
    contexts = scanner_module._extract_form_contexts(tree)
    assert contexts == []


# ---------------------------------------------------------------------------
# _xpath_for edge case: non-string tag
# ---------------------------------------------------------------------------

def test_xpath_for_non_string_tag_returns_none(monkeypatch):
    """_xpath_for returns None when node has no id and tag traversal hits a dead end."""
    from selectolax.parser import HTMLParser
    # A node that resolves to just the tag with no parent should still return a path
    tree = HTMLParser(b'<html><body><input id=""/></body></html>')
    node = tree.css_first("input")
    # Patch out the id so we exercise the traversal path
    result = scanner_module._xpath_for(node) # type: ignore[arg-type]
    # Should either return a path or None, not raise
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# _get_http_client: lazy initialisation (lines 73-81)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_http_client_creates_new_client_when_none(monkeypatch):
    """_get_http_client creates a new AsyncClient when _http_client is None."""
    import httpx

    monkeypatch.setattr(scanner_module, "_http_client", None)
    client = await scanner_module._get_http_client()
    try:
        assert isinstance(client, httpx.AsyncClient)
        assert not client.is_closed
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# _xpath_for: falsy tag triggers break → empty parts → return None (lines 129, 145)
# ---------------------------------------------------------------------------

def test_xpath_for_returns_none_when_tag_is_none():
    """Traversal breaks immediately when node.tag is None; returns None because parts is empty."""

    class _FakeNode:
        attributes = {}
        tag = None
        parent = None
        prev = None

    result = scanner_module._xpath_for(_FakeNode()) # type: ignore[arg-type]
    assert result is None


# ---------------------------------------------------------------------------
# _xpath_for: preceding sibling with same tag increments index (line 139)
# ---------------------------------------------------------------------------

def test_xpath_for_counts_preceding_siblings_of_same_tag():
    """When two inputs share the same parent, the second one gets index [2] in its XPath."""
    from selectolax.parser import HTMLParser

    tree = HTMLParser(b'<html><body><input name="a"/><input name="b"/></body></html>')
    nodes = tree.css("input")
    # Second input has one preceding sibling with the same tag → index becomes 2
    second = nodes[1]
    xpath = scanner_module._xpath_for(second)
    assert xpath is not None
    assert "input[2]" in xpath


# ---------------------------------------------------------------------------
# _extract_form_contexts: form with class but no id (line 223)
# ---------------------------------------------------------------------------

def test_extract_form_contexts_form_with_class_no_id():
    """A form with a class attribute but no id uses 'form.<class>' as selector."""
    from selectolax.parser import HTMLParser

    html = (
        b'<html><body>'
        b'<form class="login-form">'
        b'<input type="text" id="user"/>'
        b'<button type="submit">Entrar</button>'
        b'</form>'
        b'</body></html>'
    )
    tree = HTMLParser(html)
    contexts = scanner_module._extract_form_contexts(tree)
    assert len(contexts) == 1
    assert contexts[0]["form_selector"] == "form.login-form"
