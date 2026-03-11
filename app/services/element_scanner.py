from __future__ import annotations

import asyncio
import functools
import logging
from collections import Counter
from typing import Any, Awaitable, Callable

import requests
from lxml import html

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ModuleNotFoundError:
    PlaywrightTimeoutError = TimeoutError  # type: ignore[misc,assignment]
    async_playwright = None
    _PLAYWRIGHT_AVAILABLE = False

from app.schemas.scan import ScanResult

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], Awaitable[None]]

_ELEMENT_CAP = 120
_MAX_TEXT_LEN = 120
_MAX_XPATH = 80

# If lxml returns fewer elements than this, the page is likely a SPA
# and a Playwright browser-based scan will be attempted automatically.
_SPA_THRESHOLD = 30

_TYPE_CAPS: dict[str, int] = {
    "input": 35,
    "button": 35,
    "link": 25,
    "select": 10,
    "textarea": 10,
    "label": 20,
}

# XPath queries in priority traversal order
_XPATH_QUERIES: dict[str, str] = {
    "input": "//input",
    "button": "//button",
    "link": "//a[@href]",
    "select": "//select",
    "textarea": "//textarea",
    "label": "//label",
}


class ElementScannerError(Exception):
    """Raised when page scan fails."""


# ---------------------------------------------------------------------------
# Pure helper functions (no I/O, easily unit-tested)
# ---------------------------------------------------------------------------

def _normalize(value: str | None, max_len: int = _MAX_TEXT_LEN) -> str | None:
    if not value:
        return None
    text = " ".join(value.split())
    if not text:
        return None
    return text[:max_len] + "…" if len(text) > max_len else text


def _css_selector(el: html.HtmlElement) -> str:
    """Build a CSS selector with priority: id > data-testid > name > tag+class."""
    el_id = el.get("id")
    if el_id:
        return f"#{el_id}"

    data_testid = el.get("data-testid")
    if data_testid:
        return f'[data-testid="{data_testid}"]'

    name = el.get("name")
    if name:
        return f'{el.tag}[name="{name}"]'

    first_class = (el.get("class") or "").split()
    if first_class:
        return f"{el.tag}.{first_class[0]}"

    return el.tag


def _xpath_for(el: html.HtmlElement) -> str | None:
    """Build an absolute XPath for the element via ancestor traversal."""
    el_id = el.get("id")
    if el_id:
        return f'//*[@id="{el_id}"]'

    parts: list[str] = []
    current = el
    while current is not None:
        tag = current.tag
        if not isinstance(tag, str):  # skip Comment / PI nodes
            break
        parent = current.getparent()
        if parent is None:
            parts.append(tag)
            break
        siblings = [s for s in parent if s.tag == tag]
        index = siblings.index(current) + 1
        parts.append(f"{tag}[{index}]")
        current = parent

    if not parts:
        return None
    parts.reverse()
    return "/" + "/".join(parts)


def _element_type(el: html.HtmlElement) -> str | None:
    tag = el.tag
    if tag == "input":
        input_type = (el.get("type") or "text").lower()
        if input_type in ("hidden", "file"):
            return None
        if input_type in ("submit", "button", "reset"):
            return "button"
        return "input"
    mapping = {"button": "button", "a": "link", "select": "select", "textarea": "textarea", "label": "label"}
    return mapping.get(tag)


def _element_meta(el: html.HtmlElement, el_type: str, include_xpath: bool) -> dict:
    return {
        "type": el_type,
        "selector": _css_selector(el),
        "xpath": _xpath_for(el) if include_xpath else None,
        "text": _normalize(el.text_content()),
        "name": _normalize(el.get("name")),
        "id": _normalize(el.get("id")),
        "placeholder": _normalize(el.get("placeholder")),
        "required": True if el.get("required") is not None else None,
        "classes": _normalize(el.get("class")),
        "href": _normalize(el.get("href")),
        "aria_label": _normalize(el.get("aria-label")),
        "aria_role": _normalize(el.get("role")),
        "data_testid": _normalize(el.get("data-testid")),
    }


# ---------------------------------------------------------------------------
# lxml fast path — single HTTP request, no browser
# ---------------------------------------------------------------------------

def _fetch_and_parse(url: str, timeout: float) -> tuple[str, list[dict]]:
    """Fetch *url* and extract UI elements via lxml. Returns (title, elements)."""
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "AutomaWeb-Scanner/1.0"},
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise ElementScannerError(f"HTTP request failed: {exc}") from exc

    tree = html.fromstring(response.content)

    title_nodes = tree.xpath("//title/text()")
    title = _normalize(title_nodes[0]) if title_nodes else "Untitled"

    type_counts: dict[str, int] = {t: 0 for t in _TYPE_CAPS}
    seen: set[tuple] = set()
    raw_elements: list[dict] = []
    xpath_count = 0

    for el_type, xpath_expr in _XPATH_QUERIES.items():
        if len(raw_elements) >= _ELEMENT_CAP:
            break
        cap = _TYPE_CAPS[el_type]

        for el in tree.xpath(xpath_expr):
            if len(raw_elements) >= _ELEMENT_CAP:
                break
            if type_counts[el_type] >= cap:
                break

            actual_type = _element_type(el)
            if actual_type is None:
                continue

            include_xpath = xpath_count < _MAX_XPATH
            meta = _element_meta(el, actual_type, include_xpath)
            if include_xpath:
                xpath_count += 1

            dedup_key = (actual_type, meta["selector"], meta["xpath"])
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            raw_elements.append(meta)
            type_counts[el_type] += 1

    return title or "Untitled", raw_elements


# ---------------------------------------------------------------------------
# Playwright JS scan script — used only for the SPA fallback path
# ---------------------------------------------------------------------------

def _playwright_scan_script() -> str:
    return r"""
() => {
  const normalize = (value, max = 120) => {
    if (!value) return null;
    const text = String(value).replace(/\s+/g, ' ').trim();
    if (!text) return null;
    return text.length > max ? `${text.slice(0, max)}…` : text;
  };

  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  const cssEscape = (value) => {
    if (!value) return '';
    if (window.CSS && window.CSS.escape) return window.CSS.escape(value);
    return value.replace(/([ #;?%&,.+*~\\':\"!^$\[\]()=>|/@])/g, '\\\\$1');
  };

  const getSelector = (el) => {
    if (el.id) return `#${cssEscape(el.id)}`;
    const dataTestId = el.getAttribute('data-testid');
    if (dataTestId) return `[data-testid="${dataTestId}"]`;
    const name = el.getAttribute('name');
    if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;

    const parts = [];
    let current = el;
    let depth = 0;
    while (current && current.nodeType === Node.ELEMENT_NODE && depth < 4) {
      let selector = current.tagName.toLowerCase();
      const className = normalize(current.className);
      if (className) {
        const firstClass = className.split(/\s+/)[0];
        if (firstClass) selector += `.${cssEscape(firstClass)}`;
      }
      let sibling = current;
      let nth = 1;
      while ((sibling = sibling.previousElementSibling)) {
        if (sibling.tagName === current.tagName) nth += 1;
      }
      selector += `:nth-of-type(${nth})`;
      parts.unshift(selector);
      current = current.parentElement;
      depth += 1;
    }
    return parts.join(' > ');
  };

  const getXPath = (el) => {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return null;
    if (el.id) return `//*[@id="${el.id}"]`;
    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE) {
      let index = 1;
      let sibling = current.previousElementSibling;
      while (sibling) {
        if (sibling.tagName === current.tagName) index += 1;
        sibling = sibling.previousElementSibling;
      }
      parts.unshift(`${current.tagName.toLowerCase()}[${index}]`);
      current = current.parentElement;
    }
    return '/' + parts.join('/');
  };

  const typeFromElement = (el) => {
    const tag = el.tagName.toLowerCase();
    if (tag === 'input') {
      const inputType = (el.getAttribute('type') || 'text').toLowerCase();
      if (['hidden', 'file'].includes(inputType)) return null;
      if (['submit', 'button', 'reset'].includes(inputType)) return 'button';
      return 'input';
    }
    if (tag === 'button') return 'button';
    if (tag === 'a') return 'link';
    if (tag === 'select') return 'select';
    if (tag === 'textarea') return 'textarea';
    if (tag === 'label') return 'label';
    return null;
  };

  let xpathCount = 0;
  const maxXpath = 80;

  const baseMeta = (el, type) => ({
    type,
    selector: getSelector(el),
    xpath: xpathCount < maxXpath ? (() => { xpathCount += 1; return getXPath(el); })() : null,
    text: normalize(el.innerText || el.textContent, 120),
    name: normalize(el.getAttribute('name')),
    id: normalize(el.id),
    placeholder: normalize(el.getAttribute('placeholder')),
    required: el.hasAttribute('required') || null,
    classes: normalize(el.className),
    href: normalize(el.getAttribute('href')),
    aria_label: normalize(el.getAttribute('aria-label')),
    aria_role: normalize(el.getAttribute('role')),
    data_testid: normalize(el.getAttribute('data-testid')),
  });

  const cap = 120;
  const all = [];
  const typeCap = { input: 35, button: 35, link: 25, select: 10, textarea: 10, label: 20 };
  const typeCount = { input: 0, button: 0, link: 0, select: 0, textarea: 0, label: 0 };

  const selectors = 'input, button, a[href], select, textarea, label[for], [aria-label], [data-testid]';
  const candidates = Array.from(document.querySelectorAll(selectors)).filter((el) => {
    if (!isVisible(el)) return false;
    if (el.hasAttribute('disabled')) return false;
    if (el.tagName.toLowerCase() === 'a' && !el.getAttribute('href')) return false;
    return true;
  });

  for (const el of candidates) {
    if (all.length >= cap) break;
    const type = typeFromElement(el);
    if (!type) continue;
    if (typeCount[type] >= (typeCap[type] || 0)) continue;
    all.push(baseMeta(el, type));
    typeCount[type] += 1;
  }

  const seen = new Set();
  return all.filter((item) => {
    const key = `${item.type}|${item.selector}|${item.xpath}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
    """


# ---------------------------------------------------------------------------
# Public service class — hybrid lxml + Playwright
# ---------------------------------------------------------------------------

class ElementScannerService:
    """
    Hybrid UI element scanner.

    Strategy:
    1. Fast path: fetch page with ``requests`` + parse with ``lxml`` (no browser, <500 ms).
    2. SPA fallback: if the fast path returns fewer than ``spa_threshold`` elements
       (the page is JavaScript-rendered), launch a Playwright browser, wait for the
       real DOM to settle, and extract elements via JavaScript evaluation.

    The Playwright browser instance is shared across calls and lives for the
    duration of the application process (managed via ``close_shared_browser``).
    """

    _browser_lock: asyncio.Lock = asyncio.Lock()
    _shared_browser: Any = None
    _shared_playwright: Any = None

    def __init__(self, timeout_ms: int = 10_000, spa_threshold: int = _SPA_THRESHOLD) -> None:
        self._timeout_s: float = timeout_ms / 1_000
        self._timeout_ms = timeout_ms
        self._navigation_timeout_ms = min(timeout_ms, 4_000)
        self._network_idle_timeout_ms = min(timeout_ms, 1_200)
        self._spa_threshold = spa_threshold

    # ------------------------------------------------------------------
    # Shared Playwright browser lifecycle
    # ------------------------------------------------------------------

    @classmethod
    async def _get_shared_browser(cls) -> Any:
        if cls._shared_browser is not None:
            return cls._shared_browser

        async with cls._browser_lock:
            if cls._shared_browser is not None:
                return cls._shared_browser

            cls._shared_playwright = await async_playwright().start()
            cls._shared_browser = await cls._shared_playwright.chromium.launch(headless=True)
            return cls._shared_browser

    @classmethod
    async def close_shared_browser(cls) -> None:
        async with cls._browser_lock:
            if cls._shared_browser is not None:
                await cls._shared_browser.close()
                cls._shared_browser = None
            if cls._shared_playwright is not None:
                await cls._shared_playwright.stop()
                cls._shared_playwright = None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def scan_url(
        self,
        url: str,
        progress_callback: ProgressCallback | None = None,
    ) -> ScanResult:
        # --- Fast path (lxml) ---
        await self._progress(progress_callback, "Buscando página (escaneamento rápido)...")
        try:
            loop = asyncio.get_running_loop()
            title, raw_elements = await loop.run_in_executor(
                None,
                functools.partial(_fetch_and_parse, url, self._timeout_s),
            )
        except ElementScannerError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ElementScannerError(f"Scan failed: {exc}") from exc

        # --- SPA fallback (Playwright) ---
        if len(raw_elements) < self._spa_threshold:
            if _PLAYWRIGHT_AVAILABLE:
                logger.info(
                    "lxml returned %d elements (< threshold %d) for %s — switching to Playwright browser scan.",
                    len(raw_elements),
                    self._spa_threshold,
                    url,
                )
                await self._progress(
                    progress_callback,
                    f"Página parece ser uma SPA ({len(raw_elements)} elementos estáticos). "
                    "Iniciando navegador para escaneamento completo do DOM...",
                )
                title, raw_elements = await self._playwright_scan(url, progress_callback, title)
            else:
                logger.warning(
                    "lxml returned only %d elements for %s but Playwright is not installed. "
                    "Install it for better SPA support.",
                    len(raw_elements),
                    url,
                )

        total_elements = len(raw_elements)
        summary = dict(Counter(item.get("type", "unknown") for item in raw_elements))

        await self._progress(progress_callback, f"Encontrados {summary.get('input', 0)} inputs...")
        await self._progress(progress_callback, "Escaneamento concluído.")

        return ScanResult(
            url=url,
            title=title,
            total_elements=total_elements,
            summary=summary,
            elements=raw_elements,
        )

    # ------------------------------------------------------------------
    # Playwright browser scan (SPA fallback)
    # ------------------------------------------------------------------

    async def _playwright_scan(
        self,
        url: str,
        progress_callback: ProgressCallback | None,
        fallback_title: str,
    ) -> tuple[str, list[dict]]:
        try:
            browser = await self._get_shared_browser()
            context = await browser.new_context(ignore_https_errors=True, service_workers="block")
            try:
                await context.route("**/*", self._route_filter)
                page = await context.new_page()
                page.set_default_timeout(self._timeout_ms)

                await self._progress(progress_callback, "Carregando página no navegador...")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=self._navigation_timeout_ms)
                except PlaywrightTimeoutError:
                    await self._progress(progress_callback, "Timeout de navegação — continuando com DOM parcial...")

                await self._progress(progress_callback, "Aguardando rede ociosa...")
                try:
                    await page.wait_for_load_state("networkidle", timeout=self._network_idle_timeout_ms)
                except PlaywrightTimeoutError:
                    await self._progress(progress_callback, "Timeout de rede ociosa — continuando escaneamento...")

                await self._progress(progress_callback, "Extraindo elementos do DOM ao vivo...")
                raw_elements: list[dict] = await page.evaluate(_playwright_scan_script())
                title = (await page.title()) or fallback_title
            finally:
                await context.close()
        except ElementScannerError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ElementScannerError(f"Browser scan failed: {exc}") from exc

        return title, raw_elements

    async def _route_filter(self, route: Any) -> None:
        blocked = {"image", "font", "media", "manifest", "texttrack"}
        if route.request.resource_type in blocked:
            await route.abort()
            return
        await route.continue_()

    async def _progress(self, callback: ProgressCallback | None, message: str) -> None:
        if callback:
            await callback(message)
