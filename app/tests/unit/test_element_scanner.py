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

    # Fast path returns < threshold so Playwright SPA fallback is triggered
    monkeypatch.setattr(scanner_module, "_fetch_and_parse", lambda url, timeout: ("Untitled", []))
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
    """When lxml returns few elements and Playwright is unavailable, returns what lxml found."""
    scanner = ElementScannerService(timeout_ms=5000)
    partial_elements = [{"type": "link", "selector": "a", "text": "About"}]
    monkeypatch.setattr(scanner_module, "_fetch_and_parse", lambda url, timeout: ("Partial", partial_elements))
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", False)

    result = await scanner.scan_url("https://example.com")

    assert result.title == "Partial"
    assert result.total_elements == 1
    assert result.summary["link"] == 1


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

    monkeypatch.setattr(scanner_module, "_fetch_and_parse", lambda url, timeout: ("Untitled", []))
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(
        scanner_module,
        "async_playwright",
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

    monkeypatch.setattr(scanner_module, "_fetch_and_parse", lambda url, timeout: ("Untitled", []))
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(
        scanner_module,
        "async_playwright",
        lambda: CustomPagePlaywrightManager(TimeoutOnWaitStatePage()),
    )

    result = await scanner.scan_url("https://example.com", progress_callback=progress_callback)
    assert result.title == "Login"
    assert any("Timeout de rede ociosa" in msg for msg in progress_messages)


@pytest.mark.asyncio
async def test_scan_url_wraps_unexpected_exception(monkeypatch):
    scanner = ElementScannerService(timeout_ms=5000)
    monkeypatch.setattr(scanner_module, "_fetch_and_parse", lambda url, timeout: ("Untitled", []))
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(
        scanner_module,
        "async_playwright",
        lambda: CustomPagePlaywrightManager(ErrorOnEvaluatePage()),
    )

    with pytest.raises(ElementScannerError, match="Browser scan failed: boom"):
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


# ---------------------------------------------------------------------------
# Tests for lxml helper functions
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


def _make_el(html_str):
    from lxml import html
    return html.fragment_fromstring(html_str)


def test_css_selector_prioritizes_id():
    el = _make_el('<input id="email" name="email"/>')
    assert scanner_module._css_selector(el) == "#email"


def test_css_selector_uses_data_testid():
    el = _make_el('<button data-testid="submit">OK</button>')
    assert scanner_module._css_selector(el) == '[data-testid="submit"]'


def test_css_selector_uses_name():
    el = _make_el('<input name="email"/>')
    assert scanner_module._css_selector(el) == 'input[name="email"]'


def test_css_selector_uses_first_class():
    el = _make_el('<button class="primary btn">OK</button>')
    assert scanner_module._css_selector(el) == "button.primary"


def test_css_selector_fallback_to_tag():
    el = _make_el('<button>OK</button>')
    assert scanner_module._css_selector(el) == "button"


def test_xpath_for_with_id():
    el = _make_el('<input id="search"/>')
    assert scanner_module._xpath_for(el) == '//*[@id="search"]'


def test_xpath_for_without_id():
    from lxml import html as lhtml
    tree = lhtml.fromstring('<html><body><form><input name="q"/></form></body></html>')
    el = tree.xpath("//input")[0]
    xpath = scanner_module._xpath_for(el)
    assert xpath is not None
    assert xpath.startswith("/")


def test_element_type_text_input():
    el = _make_el('<input type="text"/>')
    assert scanner_module._element_type(el) == "input"


def test_element_type_no_type_defaults_to_input():
    el = _make_el('<input/>')
    assert scanner_module._element_type(el) == "input"


def test_element_type_hidden_returns_none():
    el = _make_el('<input type="hidden"/>')
    assert scanner_module._element_type(el) is None


def test_element_type_file_returns_none():
    el = _make_el('<input type="file"/>')
    assert scanner_module._element_type(el) is None


def test_element_type_submit_returns_button():
    el = _make_el('<input type="submit"/>')
    assert scanner_module._element_type(el) == "button"


def test_element_type_reset_returns_button():
    el = _make_el('<input type="reset"/>')
    assert scanner_module._element_type(el) == "button"


def test_element_type_button_input_returns_button():
    el = _make_el('<input type="button"/>')
    assert scanner_module._element_type(el) == "button"


def test_element_type_button_tag():
    el = _make_el('<button>Click</button>')
    assert scanner_module._element_type(el) == "button"


def test_element_type_link():
    el = _make_el('<a href="/">Go</a>')
    assert scanner_module._element_type(el) == "link"


def test_element_type_select():
    el = _make_el('<select><option>A</option></select>')
    assert scanner_module._element_type(el) == "select"


def test_element_type_textarea():
    el = _make_el('<textarea/>')
    assert scanner_module._element_type(el) == "textarea"


def test_element_type_label():
    el = _make_el('<label for="x">Name</label>')
    assert scanner_module._element_type(el) == "label"


def test_element_type_unknown_returns_none():
    el = _make_el('<div/>')
    assert scanner_module._element_type(el) is None


def test_element_meta_fields(monkeypatch):
    from lxml import html as lhtml
    tree = lhtml.fromstring(
        '<html><body>'
        '<input id="q" name="search" placeholder="Search" required '
        'class="main big" aria-label="Search box" role="searchbox" data-testid="search-input"/>'
        '</body></html>'
    )
    el = tree.xpath("//input")[0]
    meta = scanner_module._element_meta(el, "input", include_xpath=True)
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
    from lxml import html as lhtml
    tree = lhtml.fromstring('<html><body><input id="q"/></body></html>')
    el = tree.xpath("//input")[0]
    meta = scanner_module._element_meta(el, "input", include_xpath=False)
    assert meta["xpath"] is None


def test_fetch_and_parse_success(monkeypatch):
    from unittest.mock import MagicMock
    fake_response = MagicMock()
    fake_response.content = (
        b'<html><head><title>Test Page</title></head><body>'
        b'<input id="email" type="text" placeholder="Email"/>'
        b'<button id="submit">Login</button>'
        b'<a href="/about">About</a>'
        b'</body></html>'
    )
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr("requests.get", lambda *a, **kw: fake_response)

    title, elements = scanner_module._fetch_and_parse("http://example.com", 5.0)

    assert title == "Test Page"
    assert len(elements) == 3
    types = {e["type"] for e in elements}
    assert "input" in types
    assert "button" in types
    assert "link" in types


def test_fetch_and_parse_http_error(monkeypatch):
    import requests as req

    def _raise(*a, **kw):
        raise req.exceptions.ConnectionError("no conn")

    monkeypatch.setattr("requests.get", _raise)

    with pytest.raises(scanner_module.ElementScannerError, match="HTTP request failed"):
        scanner_module._fetch_and_parse("http://example.com", 5.0)


def test_fetch_and_parse_no_title(monkeypatch):
    from unittest.mock import MagicMock
    fake_response = MagicMock()
    fake_response.content = b'<html><body><input id="q"/></body></html>'
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr("requests.get", lambda *a, **kw: fake_response)

    title, _ = scanner_module._fetch_and_parse("http://example.com", 5.0)
    assert title == "Untitled"


@pytest.mark.asyncio
async def test_scan_url_uses_lxml_fast_path_when_sufficient_elements(monkeypatch):
    """When lxml returns >= threshold elements, Playwright is never invoked."""
    scanner = ElementScannerService(timeout_ms=5000, spa_threshold=2)
    fake_elements = [
        {"type": "input", "selector": "#q", "xpath": None, "text": None, "name": None,
         "id": "q", "placeholder": None, "required": None, "classes": None,
         "href": None, "aria_label": None, "aria_role": None, "data_testid": None},
        {"type": "button", "selector": "button", "xpath": None, "text": "Go", "name": None,
         "id": None, "placeholder": None, "required": None, "classes": None,
         "href": None, "aria_label": None, "aria_role": None, "data_testid": None},
        {"type": "link", "selector": "a", "xpath": None, "text": "About", "name": None,
         "id": None, "placeholder": None, "required": None, "classes": None,
         "href": "/about", "aria_label": None, "aria_role": None, "data_testid": None},
    ]
    monkeypatch.setattr(
        scanner_module, "_fetch_and_parse", lambda url, timeout: ("Static Site", fake_elements)
    )
    # Playwright should never be called — confirm by not patching it
    result = await scanner.scan_url("https://example.com")
    assert result.title == "Static Site"
    assert result.total_elements == 3


@pytest.mark.asyncio
async def test_scan_url_fast_path_exception_wraps(monkeypatch):
    """Non-ElementScannerError from _fetch_and_parse is wrapped."""
    scanner = ElementScannerService(timeout_ms=5000)

    def boom(url, timeout):
        raise ValueError("unexpected")

    monkeypatch.setattr(scanner_module, "_fetch_and_parse", boom)

    with pytest.raises(scanner_module.ElementScannerError, match="Scan failed"):
        await scanner.scan_url("https://example.com")


@pytest.mark.asyncio
async def test_scan_url_fast_path_reraises_scanner_error(monkeypatch):
    """ElementScannerError raised by _fetch_and_parse is re-raised unchanged (line 426)."""
    scanner = ElementScannerService(timeout_ms=5000)

    def raise_scanner_error(url, timeout):
        raise scanner_module.ElementScannerError("original scanner error")

    monkeypatch.setattr(scanner_module, "_fetch_and_parse", raise_scanner_error)

    with pytest.raises(scanner_module.ElementScannerError, match="original scanner error"):
        await scanner.scan_url("https://example.com")


@pytest.mark.asyncio
async def test_playwright_scan_reraises_scanner_error(monkeypatch):
    """ElementScannerError raised inside _playwright_scan is re-raised unchanged (line 503)."""
    class ErrorOnContextPage(FakePage):
        async def evaluate(self, script):
            raise scanner_module.ElementScannerError("inner scanner error")

    scanner = ElementScannerService(timeout_ms=5000)
    monkeypatch.setattr(scanner_module, "_fetch_and_parse", lambda url, timeout: ("Untitled", []))
    monkeypatch.setattr(scanner_module, "_PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(
        scanner_module,
        "async_playwright",
        lambda: CustomPagePlaywrightManager(ErrorOnContextPage()),
    )

    with pytest.raises(scanner_module.ElementScannerError, match="inner scanner error"):
        await scanner.scan_url("https://example.com")


def test_xpath_for_non_string_tag_returns_none():
    """_xpath_for returns None when an ancestor has a non-string tag (lines 104, 115)."""
    from unittest.mock import MagicMock
    from lxml import etree

    # Build a real element whose tag is a callable (Comment node simulation via mock)
    el = MagicMock()
    el.get.return_value = None        # no id attribute
    el.tag = etree.Comment            # callable — not a str, triggers the branch
    el.getparent.return_value = None

    result = scanner_module._xpath_for(el)
    assert result is None


def _fake_response_with_html(html_bytes):
    from unittest.mock import MagicMock
    r = MagicMock()
    r.content = html_bytes
    r.raise_for_status.return_value = None
    return r


def test_fetch_and_parse_skips_hidden_and_file_inputs(monkeypatch):
    """hidden/file inputs are skipped (line 190: actual_type is None → continue)."""
    html = (
        b"<html><head><title>T</title></head><body>"
        b'<input type="hidden" name="csrf"/>'
        b'<input type="file" name="upload"/>'
        b'<input type="text" id="visible"/>'
        b"</body></html>"
    )
    monkeypatch.setattr("requests.get", lambda *a, **kw: _fake_response_with_html(html))
    _, elements = scanner_module._fetch_and_parse("http://example.com", 5.0)
    types = [e["type"] for e in elements]
    assert "input" in types
    assert len(elements) == 1  # only the visible text input


def test_fetch_and_parse_deduplicates_elements(monkeypatch):
    """Duplicate selector+xpath combos are skipped (line 199: dedup_key in seen → continue)."""
    # Two inputs with the same id produce the same selector and xpath → deduplicated
    html = (
        b"<html><head><title>T</title></head><body>"
        b'<input id="dup" type="text"/>'
        b'<input id="dup" type="text"/>'
        b"</body></html>"
    )
    monkeypatch.setattr("requests.get", lambda *a, **kw: _fake_response_with_html(html))
    _, elements = scanner_module._fetch_and_parse("http://example.com", 5.0)
    selectors = [e["selector"] for e in elements]
    assert selectors.count("#dup") == 1


def test_fetch_and_parse_respects_type_cap(monkeypatch):
    """Elements beyond the per-type cap are ignored (line 186: type_counts >= cap → break)."""
    # input cap is 35 — generate 40 unique inputs
    inputs = b"".join(
        f'<input type="text" id="inp{i}"/>'.encode() for i in range(40)
    )
    html = b"<html><head><title>T</title></head><body>" + inputs + b"</body></html>"
    monkeypatch.setattr("requests.get", lambda *a, **kw: _fake_response_with_html(html))
    _, elements = scanner_module._fetch_and_parse("http://example.com", 5.0)
    inputs_found = [e for e in elements if e["type"] == "input"]
    assert len(inputs_found) == 35  # capped at _TYPE_CAPS["input"]


def test_fetch_and_parse_respects_global_element_cap(monkeypatch):
    """Global cap of 120 elements is respected (lines 179 and 184).

    We lower _ELEMENT_CAP to 3 so that:
    - Line 184 fires: while adding inputs, after 3 the inner loop breaks.
    - Line 179 fires: when the outer loop starts the 'button' type, total >= 3.
    """
    monkeypatch.setattr(scanner_module, "_ELEMENT_CAP", 3)

    inputs = b"".join(f'<input type="text" id="i{i}"/>'.encode() for i in range(10))
    buttons = b"".join(f'<button id="b{i}">B</button>'.encode() for i in range(10))
    html = b"<html><head><title>T</title></head><body>" + inputs + buttons + b"</body></html>"
    monkeypatch.setattr("requests.get", lambda *a, **kw: _fake_response_with_html(html))
    _, elements = scanner_module._fetch_and_parse("http://example.com", 5.0)
    assert len(elements) <= 3
