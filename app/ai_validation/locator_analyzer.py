from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover
    PlaywrightTimeoutError = TimeoutError
    async_playwright = None

logger = logging.getLogger(__name__)

GENERIC_XPATH_PATTERNS = [
    re.compile(r"^//[a-zA-Z0-9_-]+$"),
    re.compile(r"^\.//[a-zA-Z0-9_-]+$"),
    re.compile(r"^//\*$"),
    re.compile(r"^\(//[a-zA-Z0-9_-]+\)\[\d+\]$"),
]


@dataclass
class LocatorInspection:
    locator: str
    normalized_locator: str
    is_generic_xpath: bool
    suggested_locator: str | None = None


class LocatorAnalyzer:
    def normalize_locator(self, locator: str) -> str:
        value = locator.strip()
        if value.startswith("id:"):
            return f"css=#{value[3:]}"
        if value.startswith("css:"):
            return f"css={value[4:]}"
        if value.startswith("xpath:"):
            return f"xpath={value[6:]}"
        if value.startswith("/") or value.startswith("(") or value.startswith(".//"):
            return f"xpath={value}"
        if value.startswith("#") or value.startswith(".") or value.startswith("["):
            return f"css={value}"
        return value

    def inspect(self, locator: str) -> LocatorInspection:
        normalized = self.normalize_locator(locator)
        xpath_value = normalized[6:] if normalized.startswith("xpath=") else ""
        is_generic_xpath = bool(
            xpath_value and any(p.match(xpath_value) for p in GENERIC_XPATH_PATTERNS)
        )

        suggested = None
        if is_generic_xpath:
            tag = (
                xpath_value.replace("//", "")
                .replace(".//", "")
                .strip(" ()[]0123456789")
            )
            suggested = f"css={tag}[data-testid]" if tag else "css=[data-testid]"

        return LocatorInspection(
            locator=locator,
            normalized_locator=normalized,
            is_generic_xpath=is_generic_xpath,
            suggested_locator=suggested,
        )

    async def count_matches_bulk(
        self,
        page_url: str,
        locators: list[str],
        navigation_timeout_ms: int = 15_000,
    ) -> dict[str, int | None]:
        """Open the page once and count matches for all locators in a single browser session."""
        if async_playwright is None or not locators:
            return {loc: None for loc in locators}

        results: dict[str, int | None] = {loc: None for loc in locators}
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                try:
                    context = await browser.new_context()
                    page = await context.new_page()
                    try:
                        await page.goto(
                            page_url,
                            wait_until="domcontentloaded",
                            timeout=navigation_timeout_ms,
                        )
                        await page.wait_for_timeout(300)
                        for locator in locators:
                            normalized = self.normalize_locator(locator)
                            try:
                                results[locator] = int(
                                    await page.locator(normalized).count()
                                )
                            except Exception as exc:  # pragma: no cover
                                logger.debug(
                                    "count_matches_bulk: locator %r failed: %s",
                                    locator,
                                    exc,
                                )
                    finally:
                        await context.close()
                finally:
                    await browser.close()
        except PlaywrightTimeoutError:
            logger.debug("count_matches_bulk: navigation to %s timed out", page_url)
        except Exception as exc:
            logger.debug(
                "count_matches_bulk: unexpected error for %s: %s", page_url, exc
            )

        return results

    # kept for backwards-compat with tests that call it directly
    async def count_matches(
        self, page_url: str, locator: str, timeout_ms: int = 10_000
    ) -> int | None:
        results = await self.count_matches_bulk(
            page_url=page_url,
            locators=[locator],
            navigation_timeout_ms=timeout_ms,
        )
        return results[locator]
