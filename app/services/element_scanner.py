from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, urlparse

import httpx
from selectolax.parser import HTMLParser, Node

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ModuleNotFoundError:
    PlaywrightTimeoutError = TimeoutError 
    async_playwright = None
    _PLAYWRIGHT_AVAILABLE = False

from app.schemas.scan import FormContext, ScanResult

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], Awaitable[None]]

_ELEMENT_CAP = 120
_MAX_TEXT_LEN = 120
_MAX_XPATH = 80

# If selectolax returns fewer elements than this, the page is likely a SPA
# and a Playwright browser-based scan will be attempted automatically.
_SPA_THRESHOLD = 30

# How long to wait (ms) for the user to complete login in the visible browser.
_AUTH_TIMEOUT_MS = 120_000

# Login domains that require opening an auth tab before scanning protected pages.
_DEFAULT_LOGIN_HOST_HINTS: tuple[str, ...] = (
    "login-hmg.comerc.com.br",
)

_TYPE_CAPS: dict[str, int] = {
    "input": 35,
    "button": 35,
    "link": 25,
    "select": 10,
    "textarea": 10,
    "label": 20,
}

# CSS selector used for a single-pass DOM traversal (replaces 6 separate XPath queries)
_CSS_QUERY = "input, button, a[href], select, textarea, label"

# Early SPA detection: presence of any of these attributes/tags strongly suggests
# the page is JavaScript-rendered and will need Playwright.
_SPA_INDICATORS = (
    'data-reactroot', 'data-reactid',  # React
    '__NEXT_DATA__',                    # Next.js (script tag id)
    'data-v-',                          # Vue single-file components
    'ng-version',                       # Angular
    'data-svelte',                      # Svelte
)

# Reusable async HTTP client (created once, shared across all scan_url calls)
_http_client: httpx.AsyncClient | None = None
_http_client_lock = asyncio.Lock()


class ElementScannerError(Exception):
    """Raised when page scan fails."""


# ---------------------------------------------------------------------------
# Reusable HTTP client
# ---------------------------------------------------------------------------

async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        return _http_client
    async with _http_client_lock:
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                headers={"User-Agent": "AutomaWeb-Scanner/2.0"},
                follow_redirects=True,
                verify=False,
            )
        return _http_client


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


def _css_selector(node: Node) -> str:
    """Build a CSS selector with priority: id > data-testid > name > tag+class."""
    el_id = node.attributes.get("id")
    if el_id:
        return f"#{el_id}"

    data_testid = node.attributes.get("data-testid")
    if data_testid:
        return f'[data-testid="{data_testid}"]'

    name = node.attributes.get("name")
    if name:
        return f'{node.tag}[name="{name}"]'

    first_class = (node.attributes.get("class") or "").split()
    if first_class:
        return f"{node.tag}.{first_class[0]}"

    return node.tag


def _xpath_for(node: Node) -> str | None:
    """Build an absolute XPath for the element via ancestor traversal."""
    el_id = node.attributes.get("id")
    if el_id:
        return f'//*[@id="{el_id}"]'

    parts: list[str] = []
    current: Node | None = node
    while current is not None:
        tag = current.tag
        if not tag or not isinstance(tag, str):
            break
        parent = current.parent
        if parent is None or not parent.tag:
            parts.append(tag)
            break
        # Count preceding siblings with the same tag
        index = 1
        sibling = current.prev
        while sibling is not None:
            if sibling.tag == tag:
                index += 1
            sibling = sibling.prev
        parts.append(f"{tag}[{index}]")
        current = parent

    if not parts:
        return None
    parts.reverse()
    return "/" + "/".join(parts)


def _element_type(node: Node) -> str | None:
    tag = node.tag
    if tag == "input":
        input_type = (node.attributes.get("type") or "text").lower()
        if input_type in ("hidden", "file"):
            return None
        if input_type in ("submit", "button", "reset"):
            return "button"
        return "input"
    mapping = {
        "button": "button",
        "a": "link",
        "select": "select",
        "textarea": "textarea",
        "label": "label",
    }
    return mapping.get(tag)


def _element_meta(node: Node, el_type: str, include_xpath: bool) -> dict:
    attrs = node.attributes
    return {
        "type": el_type,
        "selector": _css_selector(node),
        "xpath": _xpath_for(node) if include_xpath else None,
        "text": _normalize(node.text(deep=True)),
        "name": _normalize(attrs.get("name")),
        "id": _normalize(attrs.get("id")),
        "placeholder": _normalize(attrs.get("placeholder")),
        "required": True if "required" in attrs else None,
        "classes": _normalize(attrs.get("class")),
        "href": _normalize(attrs.get("href")),
        "aria_label": _normalize(attrs.get("aria-label")),
        "aria_role": _normalize(attrs.get("role")),
        "data_testid": _normalize(attrs.get("data-testid")),
    }


# ---------------------------------------------------------------------------
# Early SPA detection
# ---------------------------------------------------------------------------

def _is_likely_spa(html_bytes: bytes) -> bool:
    """
    Quick early-exit check: scan the raw HTML bytes for known SPA fingerprints
    before building a full DOM tree. This avoids the full parse cost for obvious
    SPA pages (Next.js, React, Vue, Angular, Svelte).
    """
    sample = html_bytes[:8_000]
    return any(indicator.encode() in sample for indicator in _SPA_INDICATORS)


# ---------------------------------------------------------------------------
# Form-context extraction — enriches output for better LLM test generation
# ---------------------------------------------------------------------------

def _extract_form_contexts(tree: HTMLParser) -> list[dict]:
    """
    Walk every <form> in the parsed tree and collect:
    - form_selector: the form's id/class/tag
    - inputs: selectors of interactive fields inside the form
    - submit: selector of the submit button, if present

    This structural grouping lets the LLM understand which inputs belong
    together and which button submits the form, enabling it to generate
    complete test flows (e.g. Fill Form → Click Submit → Assert Result).
    """
    contexts: list[dict] = []
    for form in tree.css("form"):
        form_attrs = form.attributes
        if form_attrs.get("id"):
            form_sel = f'#{form_attrs["id"]}'
        elif form_attrs.get("class"):
            form_sel = f'form.{form_attrs["class"].split()[0]}'  # type: ignore[arg-type]
        else:
            form_sel = "form"

        inputs: list[str] = []
        submit_sel: str | None = None

        for child in form.css("input, textarea, select, button"):
            child_attrs = child.attributes
            tag = child.tag
            input_type = (child_attrs.get("type") or "text").lower()

            # Skip hidden/file
            if tag == "input" and input_type in ("hidden", "file"):
                continue

            selector = _css_selector(child)

            # Identify submit button
            if tag == "button" or (tag == "input" and input_type in ("submit", "button", "reset")):
                if submit_sel is None:
                    submit_sel = selector
            else:
                inputs.append(selector)

        if inputs or submit_sel:
            contexts.append({
                "form_selector": form_sel,
                "inputs": inputs,
                "submit": submit_sel,
            })

    return contexts




async def _fetch_and_parse(url: str) -> tuple[str, list[dict], bool, list[dict]]:
    """
    Fetch *url* asynchronously with httpx and extract UI elements via a single
    CSS-selector pass using selectolax.
    Returns (title, elements, is_spa_hint, form_contexts).
    """
    try:
        client = await _get_http_client()
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ElementScannerError(f"HTTP request failed: {exc}") from exc

    content = response.content

    # Fast SPA fingerprint check before parsing
    spa_hint = _is_likely_spa(content)

    tree = HTMLParser(content)

    title_node = tree.css_first("title")
    title = _normalize(title_node.text()) if title_node else "Untitled"

    type_counts: dict[str, int] = {t: 0 for t in _TYPE_CAPS}
    seen: set[tuple] = set()
    raw_elements: list[dict] = []
    xpath_count = 0

    # Single-pass: one CSS query instead of 6 separate XPath traversals
    for node in tree.css(_CSS_QUERY):
        if len(raw_elements) >= _ELEMENT_CAP:
            break

        el_type = _element_type(node)
        if el_type is None:
            continue

        cap = _TYPE_CAPS.get(el_type, 0)
        if type_counts.get(el_type, 0) >= cap:
            continue

        include_xpath = xpath_count < _MAX_XPATH
        meta = _element_meta(node, el_type, include_xpath)
        if include_xpath:
            xpath_count += 1

        dedup_key = (el_type, meta["selector"], meta["xpath"])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        raw_elements.append(meta)
        type_counts[el_type] = type_counts.get(el_type, 0) + 1

    form_contexts = _extract_form_contexts(tree)
    return title or "Untitled", raw_elements, spa_hint, form_contexts


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
# Public service class — hybrid selectolax + Playwright
# ---------------------------------------------------------------------------

class ElementScannerService:
    """
    Hybrid UI element scanner.

    Strategy:
    1. Fast path: fetch page async with ``httpx`` + parse with ``selectolax``
       via a single CSS-selector pass (no blocking I/O, no run_in_executor).
    2. Early SPA detection: raw-byte fingerprint check for React/Next/Vue/Angular/
       Svelte markers before the full DOM parse.
    3. SPA fallback: if the fast path returns fewer than ``spa_threshold`` elements
       OR the early SPA hint fires, launch a Playwright browser, wait for the
       real DOM to settle, and extract elements via JavaScript evaluation.

    The Playwright browser instance is shared across calls and lives for the
    duration of the application process (managed via ``close_shared_browser``).
    """

    _browser_lock: asyncio.Lock = asyncio.Lock()
    _shared_browser: Any = None
    _shared_playwright: Any = None

    def __init__(self, timeout_ms: int = 10_000, spa_threshold: int = _SPA_THRESHOLD) -> None:
        self._timeout_ms = timeout_ms
        self._navigation_timeout_ms = min(timeout_ms, 4_000)
        self._network_idle_timeout_ms = min(timeout_ms, 1_200)
        self._spa_threshold = spa_threshold
        self._login_host_hints = _DEFAULT_LOGIN_HOST_HINTS

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
 
            cls._shared_playwright = await async_playwright().start()  # type: ignore[arg-type]
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
        # --- Fast path (httpx + selectolax, fully async) ---
        await self._progress(progress_callback, "Buscando página...")
        try:
            title, raw_elements, spa_hint, form_contexts = await _fetch_and_parse(url)
        except ElementScannerError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ElementScannerError(f"Scan failed: {exc}") from exc

        # --- SPA fallback (Playwright) —--
        # Form contexts are only available from the static fast path;
        # Playwright scan returns a flat element list without form structure.
        needs_browser = spa_hint or len(raw_elements) < self._spa_threshold
        if needs_browser:
            if _PLAYWRIGHT_AVAILABLE:
                reason = "SPA fingerprint detected" if spa_hint else f"only {len(raw_elements)} static elements"
                logger.info(
                    "%s for %s — switching to Playwright browser scan.",
                    reason,
                    url,
                )
                await self._progress(
                    progress_callback,
                    f"Página dinâmica detectada ({len(raw_elements)} elementos estáticos). "
                    "Iniciando navegador para escaneamento completo do DOM...",
                )
                title, raw_elements = await self._playwright_scan(url, progress_callback, title)
                form_contexts = []  # not available from JS scan
            else:
                logger.warning(
                    "selectolax returned only %d elements for %s but Playwright is not installed. "
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
            elements=raw_elements,  # type: ignore[arg-type]
            form_contexts=[FormContext(**fc) for fc in form_contexts],
        )

    # ------------------------------------------------------------------
    # Playwright browser scan (SPA fallback)
    # ------------------------------------------------------------------

    def _is_login_url(self, candidate_url: str) -> bool:
        host = urlparse(candidate_url).netloc.lower()
        return any(hint in host for hint in self._login_host_hints)

    def _extract_redirect_target(self, login_url: str) -> str | None:
        query = parse_qs(urlparse(login_url).query)
        redirect_values = query.get("redirect_uri")
        if not redirect_values:
            return None
        return redirect_values[0]

    async def _handle_login_flow(
        self,
        context: Any,
        login_url: str,
        original_url: str,
        progress_callback: ProgressCallback | None,
    ) -> None:
        """
        Opens a **visible** (non-headless) browser so the user can complete the
        corporate Cognito login, then transfers the resulting session cookies to
        *context* (the headless scanning browser context).

        Degrades gracefully when no display is available (Docker / CI).
        """
        redirect_target = self._extract_redirect_target(login_url)
        redirect_netloc = urlparse(redirect_target).netloc if redirect_target else None

        await self._progress(
            progress_callback,
            "Login corporativo detectado. Abrindo janela de autenticação — "
            "faça login e aguarde...",
        )

        auth_pw = await async_playwright().start()  # type: ignore[misc]
        try:
            try:
                auth_browser = await auth_pw.chromium.launch(headless=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cannot open non-headless browser for login: %s", exc)
                await self._progress(
                    progress_callback,
                    "Não foi possível abrir janela de login (ambiente sem display). "
                    "Faça login manualmente e tente novamente.",
                )
                return

            try:
                auth_ctx = await auth_browser.new_context(ignore_https_errors=True)
                try:
                    auth_page = await auth_ctx.new_page()
                    auth_page.set_default_timeout(_AUTH_TIMEOUT_MS)
                    try:
                        await auth_page.goto(
                            login_url,
                            wait_until="domcontentloaded",
                            timeout=15_000,
                        )
                    except PlaywrightTimeoutError:
                        pass

                    wait_pattern = (
                        f"https://{redirect_netloc}/**" if redirect_netloc else "**"
                    )
                    try:
                        await self._progress(
                            progress_callback,
                            "Aguardando autenticação do usuário (máx. 2 min)...",
                        )
                        await auth_page.wait_for_url(wait_pattern, timeout=_AUTH_TIMEOUT_MS)
                        try:
                            await auth_page.wait_for_load_state("networkidle", timeout=5_000)
                        except PlaywrightTimeoutError:
                            pass

                        cookies = await auth_ctx.cookies()
                        if cookies:
                            await context.add_cookies(cookies)
                            await self._progress(
                                progress_callback,
                                f"Autenticação concluída. Sessão transferida "
                                f"({len(cookies)} cookie(s)).",
                            )
                    except PlaywrightTimeoutError:
                        await self._progress(
                            progress_callback,
                            "Timeout de autenticação (2 min). Continuando sem sessão autenticada.",
                        )
                    finally:
                        await auth_page.close()
                finally:
                    await auth_ctx.close()
            finally:
                await auth_browser.close()
        finally:
            await auth_pw.stop()

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

                current_url = page.url
                if self._is_login_url(current_url):
                    await self._handle_login_flow(context, current_url, url, progress_callback)
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=self._navigation_timeout_ms)
                    except PlaywrightTimeoutError:
                        await self._progress(progress_callback, "Timeout ao recarregar página após login...")

                await self._progress(progress_callback, "Aguardando rede ociosa...")
                try:
                    await page.wait_for_load_state("networkidle", timeout=self._network_idle_timeout_ms)
                except PlaywrightTimeoutError:
                    await self._progress(progress_callback, "Timeout de rede ociosa — continuando escaneamento...")

                await self._progress(progress_callback, "Extraindo elementos do DOM...")
                raw_elements: list[dict] = await page.evaluate(_playwright_scan_script())
                title = (await page.title()) or fallback_title
            finally:
                await context.close()
        except ElementScannerError:
            raise
        except Exception as exc:
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

