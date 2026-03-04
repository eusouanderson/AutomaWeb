from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any, Awaitable, Callable

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ModuleNotFoundError:  
    PlaywrightTimeoutError = TimeoutError  
    async_playwright = None 

from app.schemas.scan import ScanResult

ProgressCallback = Callable[[str], Awaitable[None]]


class ElementScannerError(Exception):
    """Raised when page scan fails."""


class ElementScannerService:
    """Fast UI element scanner using Playwright in headless mode."""

    _browser_lock = asyncio.Lock()
    _shared_browser = None
    _shared_playwright = None

    def __init__(self, timeout_ms: int = 10_000) -> None:
        self._timeout_ms = timeout_ms
        self._navigation_timeout_ms = min(timeout_ms, 4_000)
        self._network_idle_timeout_ms = min(timeout_ms, 1_200)

    @classmethod
    async def _get_shared_browser(cls):
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

    async def scan_url(self, url: str, progress_callback: ProgressCallback | None = None) -> ScanResult:
        await self._progress(progress_callback, "Launching browser...")

        if async_playwright is None:
            raise ElementScannerError(
                "Playwright is not installed. Install dependencies and run `playwright install chromium`."
            )

        try:
            browser = await self._get_shared_browser()
            context = await browser.new_context(ignore_https_errors=True, service_workers="block")
            try:
                await context.route("**/*", self._route_filter)

                page = await context.new_page()
                page.set_default_timeout(self._timeout_ms)

                await self._progress(progress_callback, "Loading page...")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=self._navigation_timeout_ms)
                except PlaywrightTimeoutError:
                    await self._progress(
                        progress_callback,
                        "Navigation timeout reached, continuing with partial page content...",
                    )

                await self._progress(progress_callback, "Waiting for network idle...")
                try:
                    await page.wait_for_load_state("networkidle", timeout=self._network_idle_timeout_ms)
                except PlaywrightTimeoutError:
                    await self._progress(progress_callback, "Network idle timeout reached, continuing scan...")

                await self._progress(progress_callback, "Extracting Robot-relevant elements...")
                raw_elements = await page.evaluate(self._scan_script())

                title = (await page.title()) or "Untitled"
                total_elements = len(raw_elements)
                summary = dict(Counter(item.get("type", "unknown") for item in raw_elements))

                await self._progress(progress_callback, f"Found {summary.get('input', 0)} inputs...")
                await self._progress(progress_callback, "Scan complete.")

                return ScanResult(
                    url=url,
                    title=title,
                    total_elements=total_elements,
                    summary=summary,
                    elements=raw_elements,
                )
            finally:
                await context.close()
        except Exception as exc:  # noqa: BLE001
            raise ElementScannerError(f"Scan failed: {exc}") from exc

    async def _progress(self, callback: ProgressCallback | None, message: str) -> None:
        if callback:
            await callback(message)

    async def _route_filter(self, route: Any) -> None:
        blocked = {"image", "font", "media", "manifest", "texttrack"}
        if route.request.resource_type in blocked:
            await route.abort()
            return
        await route.continue_()

    def _scan_script(self) -> str:
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

  const typeCap = {
    input: 35,
    button: 35,
    link: 25,
    select: 10,
    textarea: 10,
    label: 20,
  };
  const typeCount = {
    input: 0,
    button: 0,
    link: 0,
    select: 0,
    textarea: 0,
    label: 0,
  };

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
