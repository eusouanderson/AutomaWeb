from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Coroutine, cast

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

@dataclass(slots=True)
class BuilderRuntimeSession:
    session_id: str
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page
    pending_event_tasks: set[asyncio.Task[Any]] = field(default_factory=set)


def _capture_script(session_id: str, backend_event_url: str) -> str:
    escaped_session = session_id.replace("\\", "\\\\").replace('"', '\\"')
    escaped_backend_event_url = backend_event_url.replace("\\", "\\\\").replace(
        '"', '\\"'
    )
    return f"""
(() => {{
  if (window.__automaVisualBuilderLoaded) return;
  window.__automaVisualBuilderLoaded = true;

  const INPUT_DEBOUNCE_MS = 450;
  const SESSION_ID = \"{escaped_session}\";
  const BACKEND_EVENT_URL = \"{escaped_backend_event_url}\";
  const TOOLTIP_ID = '__aw_builder_tooltip__';

  let tooltipEl = null;
  let hoveredEl = null;
  let inputTimer = null;

  const truncate = (value, max = 180) => {{
    const normalized = String(value || '').replace(/\\s+/g, ' ').trim();
    if (!normalized) return '';
    return normalized.length > max ? normalized.slice(0, max - 1) + '…' : normalized;
  }};

  const cssEsc = (value) =>
    window.CSS?.escape ? window.CSS.escape(value) : String(value).replace(/[^\\w-]/g, '\\\\$&');

  const fallbackPath = (el) => {{
    const parts = [];
    let node = el;

    while (node && node.nodeType === 1 && node !== document.body) {{
      let part = node.tagName.toLowerCase();
      const siblings = node.parentElement
        ? Array.from(node.parentElement.children).filter((child) => child.tagName === node.tagName)
        : [];

      if (siblings.length > 1) {{
        part += ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')';
      }}

      parts.unshift(part);
      node = node.parentElement;
    }}

    return parts.join(' > ');
  }};

  const actionableSelector =
    'button, a, input, textarea, select, [role="button"], [role="link"], [role="checkbox"], [role="radio"], [data-testid], [data-test], [data-qa], [aria-label], [onclick]';

  const stableClassNames = (el) =>
    Array.from(el.classList || [])
      .filter((cls) => cls && cls.length <= 32 && !/\\d{3,}/.test(cls))
      .slice(0, 2);

  const isUnique = (selector, el) => {{
    if (!selector) return false;
    try {{
      const nodes = document.querySelectorAll(selector);
      return nodes.length === 1 && nodes[0] === el;
    }} catch (_error) {{
      return false;
    }}
  }};

  const resolveActionTarget = (target) => {{
    if (!(target instanceof Element)) return null;
    return target.closest(actionableSelector) || target;
  }};

  const resolveLabelText = (el) => {{
    if (!(el instanceof Element)) return '';

    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) return truncate(ariaLabel, 120);

    const labels = 'labels' in el && Array.isArray(Array.from(el.labels || []))
      ? Array.from(el.labels || []).map((label) => truncate(label.textContent || '', 120)).filter(Boolean)
      : [];
    if (labels.length) return labels[0];

    const id = el.getAttribute('id');
    if (id) {{
      const label = document.querySelector('label[for="' + cssEsc(id) + '"]');
      if (label) return truncate(label.textContent || '', 120);
    }}

    const placeholder = el.getAttribute('placeholder');
    if (placeholder) return truncate(placeholder, 120);

    return truncate(el.textContent || '', 120);
  }};

  const inferStepName = (action, target) => {{
    const label = resolveLabelText(target);
    if (action === 'input') {{
      return label ? 'Preencher ' + label : 'Preencher campo';
    }}
    return label ? 'Clicar em ' + label : 'Clicar no elemento';
  }};

  const buildElementDetails = (target, action, selector, value = null, description = '') => {{
    const text = truncate(target?.textContent || '', 220);
    const href = target instanceof HTMLAnchorElement ? target.href : target?.getAttribute?.('href') || '';
    const inputType = target instanceof HTMLInputElement ? target.type || '' : '';
    return {{
      session_id: SESSION_ID,
      action,
      selector,
      value,
      description,
      step_name: inferStepName(action, target),
      page_url: window.location.href,
      page_title: truncate(document.title || '', 180),
      element_tag: target?.tagName?.toLowerCase?.() || '',
      element_text: text,
      input_type: inputType,
      href: href || '',
    }};
  }};

  const buildSelector = (el) => {{
    if (!el || !(el instanceof Element)) return '';

    const byDataAttrs = ['data-testid', 'data-test', 'data-qa', 'data-cy'];
    for (const attr of byDataAttrs) {{
      const value = el.getAttribute(attr);
      if (value) {{
        const selector = '[' + attr + '="' + cssEsc(value) + '"]';
        if (isUnique(selector, el)) return selector;
      }}
    }}

    if (el.id) {{
      const idSelector = '#' + cssEsc(el.id);
      if (isUnique(idSelector, el)) return idSelector;
    }}

    const name = el.getAttribute('name');
    if (name) {{
      const selector = el.tagName.toLowerCase() + '[name="' + cssEsc(name) + '"]';
      if (isUnique(selector, el)) return selector;
    }}

    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) {{
      const selector = el.tagName.toLowerCase() + '[aria-label="' + cssEsc(ariaLabel) + '"]';
      if (isUnique(selector, el)) return selector;
    }}

    const placeholder = el.getAttribute('placeholder');
    if (placeholder) {{
      const selector = el.tagName.toLowerCase() + '[placeholder="' + cssEsc(placeholder) + '"]';
      if (isUnique(selector, el)) return selector;
    }}

    const classes = stableClassNames(el);
    if (classes.length) {{
      const selector = el.tagName.toLowerCase() + classes.map((cls) => '.' + cssEsc(cls)).join('');
      if (isUnique(selector, el)) return selector;
    }}

    // Avoid returning non-unique IDs/names because they frequently trigger
    // strict mode violations in Browser Library execution.
    if (name) {{
      const selector = el.tagName.toLowerCase() + '[name="' + cssEsc(name) + '"]';
      if (isUnique(selector, el)) return selector;
    }}

    if (classes.length) {{
      const selector = el.tagName.toLowerCase() + classes.map((cls) => '.' + cssEsc(cls)).join('');
      if (isUnique(selector, el)) return selector;
    }}

    return fallbackPath(el);
  }};

  const clearHighlight = () => {{
    if (!(hoveredEl instanceof HTMLElement)) return;
    hoveredEl.style.outline = '';
    hoveredEl.style.boxShadow = '';
    hoveredEl = null;
  }};

  const highlight = (el) => {{
    if (!(el instanceof HTMLElement)) return;
    clearHighlight();
    el.style.outline = '2px solid #2563eb';
    el.style.boxShadow = '0 0 0 6px rgba(37, 99, 235, 0.15)';
    hoveredEl = el;
  }};

  const removeTooltip = () => {{
    if (tooltipEl && tooltipEl.parentNode) {{
      tooltipEl.parentNode.removeChild(tooltipEl);
    }}
    tooltipEl = null;
  }};

  const sendEvent = async (payload) => {{
    if (typeof window.__awRecordBuilderEvent === 'function') {{
      try {{
        await window.__awRecordBuilderEvent(payload);
        return;
      }} catch (_error) {{
        // Fallback to HTTP transport below.
      }}
    }}

    const body = JSON.stringify(payload);
    const options = {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body,
      keepalive: true,
    }};

    try {{
      const sameOriginResponse = await fetch('/builder/event', options);
      if (sameOriginResponse.ok) {{
        return;
      }}
    }} catch (_error) {{
      // Fallback for cross-origin pages.
    }}

    try {{
      const backendResponse = await fetch(BACKEND_EVENT_URL, options);
      if (backendResponse.ok) {{
        return;
      }}
    }} catch (_error) {{
      // Ignore backend failures while recording interactions.
    }}
  }};

  const createTooltip = (target, selector, initialDescription, initialStepName, onSave) => {{
    removeTooltip();
    tooltipEl = document.createElement('div');
    tooltipEl.id = TOOLTIP_ID;
    tooltipEl.style.position = 'fixed';
    tooltipEl.style.zIndex = '2147483647';
    tooltipEl.style.maxWidth = '320px';
    tooltipEl.style.background = '#111827';
    tooltipEl.style.color = '#f9fafb';
    tooltipEl.style.padding = '10px';
    tooltipEl.style.borderRadius = '8px';
    tooltipEl.style.boxShadow = '0 12px 28px rgba(17, 24, 39, 0.35)';
    tooltipEl.style.border = '1px solid rgba(59, 130, 246, 0.5)';
    tooltipEl.style.fontFamily = 'ui-sans-serif, system-ui, -apple-system, sans-serif';
    tooltipEl.style.fontSize = '12px';
    tooltipEl.style.display = 'grid';
    tooltipEl.style.gap = '8px';
    tooltipEl.innerHTML =
      '<div style="font-weight:600;color:#93c5fd">Visual Test Builder</div>' +
      '<div style="opacity:.85;word-break:break-all">' + selector + '</div>' +
      '<input id="__aw_name_input__" type="text" placeholder="Nome do step" ' +
      'style="width:100%;border-radius:6px;border:1px solid #1f2937;background:#0b1220;color:#f9fafb;padding:7px 8px" />' +
      '<input id="__aw_desc_input__" type="text" placeholder="Descreva o que validar" ' +
      'style="width:100%;border-radius:6px;border:1px solid #1f2937;background:#0b1220;color:#f9fafb;padding:7px 8px" />' +
      '<button id="__aw_desc_save__" style="cursor:pointer;border:none;background:#2563eb;color:white;border-radius:6px;padding:7px 8px;font-weight:600">Salvar Step</button>';

    document.documentElement.appendChild(tooltipEl);

    const rect = target.getBoundingClientRect();
    const left = Math.max(8, Math.min(window.innerWidth - 336, rect.left));
    const top = Math.max(8, Math.min(window.innerHeight - 180, rect.bottom + 8));
    tooltipEl.style.left = left + 'px';
    tooltipEl.style.top = top + 'px';

    const nameInput = tooltipEl.querySelector('#__aw_name_input__');
    const input = tooltipEl.querySelector('#__aw_desc_input__');
    const saveBtn = tooltipEl.querySelector('#__aw_desc_save__');

    if (nameInput) {{
      nameInput.value = initialStepName || '';
    }}

    if (input) {{
      input.value = initialDescription || '';
    }}

    if (nameInput) {{
      nameInput.focus();
    }} else if (input) {{
      input.focus();
    }}

    const submit = () => {{
      const stepName = nameInput ? String(nameInput.value || '').trim() : '';
      const description = input ? String(input.value || '').trim() : '';
      onSave(stepName, description);
      removeTooltip();
    }};

    if (saveBtn) {{
      saveBtn.addEventListener('click', submit);
    }}

    [nameInput, input].filter(Boolean).forEach((field) => {{
      field.addEventListener('keydown', (event) => {{
        if (event.key === 'Enter') {{
          event.preventDefault();
          submit();
        }}
      }});
    }});
  }};

  const isBuilderUi = (target) =>
    target instanceof Element && (target.closest('#' + TOOLTIP_ID) || target.closest('[data-aw-builder="ui"]'));

  document.addEventListener(
    'mouseover',
    (event) => {{
      const target = resolveActionTarget(event.target);
      if (!(target instanceof HTMLElement) || isBuilderUi(target)) return;
      highlight(target);
    }},
    true,
  );

  document.addEventListener(
    'mouseout',
    (event) => {{
      const target = resolveActionTarget(event.target);
      if (!(target instanceof HTMLElement) || isBuilderUi(target)) return;
      if (hoveredEl === target) clearHighlight();
    }},
    true,
  );

  document.addEventListener(
    'contextmenu',
    (event) => {{
      const target = resolveActionTarget(event.target);
      if (!(target instanceof HTMLElement) || isBuilderUi(target)) return;

      event.preventDefault();
      event.stopPropagation();

      const selector = buildSelector(target);
      if (!selector) return;

      highlight(target);

      const defaultDescription = truncate(target.textContent || '', 120);
      const defaultStepName = inferStepName('click', target);
      createTooltip(target, selector, defaultDescription, defaultStepName, (stepName, description) => {{
        void sendEvent({{
          ...buildElementDetails(target, 'click', selector, null, description),
          step_name: stepName || defaultStepName,
        }});
      }});
    }},
    true,
  );

  document.addEventListener(
    'input',
    (event) => {{
      const target = resolveActionTarget(event.target);
      if (
        !(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) ||
        isBuilderUi(target)
      ) {{
        return;
      }}

      const selector = buildSelector(target);
      if (!selector) return;

      if (inputTimer) {{
        clearTimeout(inputTimer);
      }}

      inputTimer = setTimeout(() => {{
        void sendEvent(buildElementDetails(target, 'input', selector, target.value, 'Valor preenchido no campo'));
      }}, INPUT_DEBOUNCE_MS);
    }},
    true,
  );

  document.addEventListener(
    'change',
    (event) => {{
      const target = resolveActionTarget(event.target);
      if (!(target instanceof HTMLSelectElement) || isBuilderUi(target)) return;

      const selector = buildSelector(target);
      if (!selector) return;

      void sendEvent(buildElementDetails(target, 'input', selector, target.value, 'Opcao selecionada no campo'));
    }},
    true,
  );
}})();
"""


class PlaywrightManager:
    """Singleton manager for browser/page runtime used by Visual Test Builder."""

    _instance: PlaywrightManager | None = None
    _instance_guard = asyncio.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> PlaywrightManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._sessions: dict[str, BuilderRuntimeSession] = {}
        self._lock = asyncio.Lock()
        self._initialized = True

    async def start_session(
        self,
        *,
        session_id: str,
        url: str,
        backend_event_url: str,
        event_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        async with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"Session '{session_id}' already started")

            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            # Builder startup must not fail due to client-side timeout budgets.
            context.set_default_timeout(0)
            context.set_default_navigation_timeout(0)
            page.set_default_timeout(0)
            page.set_default_navigation_timeout(0)
            pending_event_tasks: set[asyncio.Task[Any]] = set()

            if event_handler is not None:
                async def _aw_record_event(_source: Any, payload: Any) -> None:
                    if isinstance(payload, dict):
                        # Avoid blocking page-side bridge calls and browser interactions
                        # on transient DB/network slowness while still persisting events.
                        coroutine = cast(
                          Coroutine[Any, Any, None],
                          event_handler(payload),
                        )
                        task = asyncio.create_task(coroutine)
                        pending_event_tasks.add(task)

                        def _cleanup(done_task: asyncio.Task[Any]) -> None:
                            pending_event_tasks.discard(done_task)
                            try:
                                done_task.result()
                            except Exception:
                                # Capture errors should never break browser-side flow.
                                return

                        task.add_done_callback(_cleanup)

                await context.expose_binding("__awRecordBuilderEvent", _aw_record_event)

            # Install capture bootstrap at context level so it applies to every
            # navigation/frame created inside this builder session.
            await context.add_init_script(_capture_script(session_id, backend_event_url))
            await page.goto(url, wait_until="domcontentloaded", timeout=0)

            self._sessions[session_id] = BuilderRuntimeSession(
                session_id=session_id,
                playwright=playwright,
                browser=browser,
                context=context,
                page=page,
                pending_event_tasks=pending_event_tasks,
            )

    async def stop_session(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)

        if not session:
            return

        if session.pending_event_tasks:
          await asyncio.gather(*session.pending_event_tasks, return_exceptions=True)

        await session.context.close()
        await session.browser.close()
        await session.playwright.stop()

    async def shutdown(self) -> None:
        async with self._lock:
            session_ids = list(self._sessions.keys())

        for session_id in session_ids:
            await self.stop_session(session_id)
