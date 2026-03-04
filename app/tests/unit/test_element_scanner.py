import pytest

from app.services.element_scanner import ElementScannerService


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
    async def new_context(self, ignore_https_errors):
        self.ignore_https_errors = ignore_https_errors
        return FakeContext()

    async def close(self):
        return None


class FakeChromium:
    async def launch(self, headless):
        self.headless = headless
        return FakeBrowser()


class FakePlaywright:
    chromium = FakeChromium()


class FakePlaywrightManager:
    async def __aenter__(self):
        return FakePlaywright()

    async def __aexit__(self, exc_type, exc, tb):
        return False


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
