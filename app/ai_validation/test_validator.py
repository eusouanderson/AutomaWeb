from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from app.ai_validation.locator_analyzer import LocatorAnalyzer
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    line_number: int
    keyword: str
    locator: str
    issue_type: str
    message: str
    severity: str = "warning"
    suggested_locator: str | None = None


@dataclass
class ValidationReport:
    issues: list[ValidationIssue]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


class TestValidator:
    ACTION_KEYWORDS = {
        "Click",
        "Click With Options",
        "Fill Text",
        "Input Text",
        "Type Text",
        "Get Element",
        "Get Elements",
        "Wait For Elements State",
    }

    WAIT_KEYWORDS = {
        "Wait For Elements State",
        "Wait For Selector",
    }

    def __init__(self, locator_analyzer: LocatorAnalyzer | None = None) -> None:
        self._locator_analyzer = locator_analyzer or LocatorAnalyzer()

    async def validate(
        self, content: str, page_url: str | None = None
    ) -> ValidationReport:
        lines = content.splitlines()
        issues: list[ValidationIssue] = []

        # --- Pass 1: static analysis (no network, instant) ---
        action_lines: list[tuple[int, str, str, str]] = (
            []
        )  # (idx, keyword, locator, indent)
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("***") or stripped.startswith("#"):
                continue

            parts = re.split(r"\s{2,}", stripped)
            keyword = parts[0] if parts else ""
            locator = parts[1] if len(parts) > 1 else ""

            if keyword not in self.ACTION_KEYWORDS or not locator:
                continue

            action_lines.append((idx, keyword, locator, line))
            inspection = self._locator_analyzer.inspect(locator)

            if inspection.is_generic_xpath:
                issues.append(
                    ValidationIssue(
                        line_number=idx,
                        keyword=keyword,
                        locator=locator,
                        issue_type="generic_xpath",
                        message="XPath genérico detectado; pode causar flakiness e strict mode violation.",
                        suggested_locator=inspection.suggested_locator,
                    )
                )

            if keyword not in self.WAIT_KEYWORDS and not self._has_wait_before(
                lines, idx - 1
            ):
                issues.append(
                    ValidationIssue(
                        line_number=idx,
                        keyword=keyword,
                        locator=locator,
                        issue_type="missing_wait",
                        message="Ação sem espera explícita anterior para sincronização.",
                        severity="warning",
                    )
                )

        # --- Pass 2: live element check (ONE page load for all locators) ---
        if page_url and action_lines and settings.AI_LIVE_CHECK_ENABLED:
            unique_locators = list({loc for _, _, loc, _ in action_lines})
            try:
                counts = await asyncio.wait_for(
                    self._locator_analyzer.count_matches_bulk(
                        page_url=page_url,
                        locators=unique_locators,
                        navigation_timeout_ms=settings.AI_LIVE_CHECK_TIMEOUT_SECONDS
                        * 1000,
                    ),
                    timeout=settings.AI_LIVE_CHECK_TIMEOUT_SECONDS + 5,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "AI live-check timed out for %s; skipping element verification.",
                    page_url,
                )
                counts = {}

            for idx, keyword, locator, _ in action_lines:
                count = counts.get(locator)
                if count is None:
                    continue
                inspection = self._locator_analyzer.inspect(locator)
                if count == 0:
                    issues.append(
                        ValidationIssue(
                            line_number=idx,
                            keyword=keyword,
                            locator=locator,
                            issue_type="element_not_found",
                            message="Locator não encontrou elementos na página.",
                            severity="error",
                        )
                    )
                elif count > 1:
                    issues.append(
                        ValidationIssue(
                            line_number=idx,
                            keyword=keyword,
                            locator=locator,
                            issue_type="strict_mode_violation",
                            message=f"Locator corresponde a {count} elementos.",
                            severity="error",
                            suggested_locator=f"{inspection.normalized_locator} >> nth=0",
                        )
                    )

        return ValidationReport(issues=issues)

    def _has_wait_before(self, lines: list[str], line_index: int) -> bool:
        lookback = 2
        for i in range(max(0, line_index - lookback), line_index):
            stripped = lines[i].strip()
            if not stripped:
                continue
            parts = re.split(r"\s{2,}", stripped)
            if parts and parts[0] in self.WAIT_KEYWORDS:
                return True
        return False
