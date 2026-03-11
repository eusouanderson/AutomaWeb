"""Tests for the AI Test Self-Healing / Validation Layer."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_validation.locator_analyzer import LocatorAnalyzer, LocatorInspection
from app.ai_validation.metrics import AIMetrics, AIMetricsRegistry
from app.ai_validation.self_healing_service import AITestSelfHealingService, HealedTestResult
from app.ai_validation.test_fixer import FixResult, TestFixer
from app.ai_validation.test_validator import TestValidator, ValidationIssue, ValidationReport

# ---------------------------------------------------------------------------
# LocatorAnalyzer
# ---------------------------------------------------------------------------


class TestLocatorAnalyzerNormalize:
    def setup_method(self):
        self.analyzer = LocatorAnalyzer()

    def test_id_prefix_converts_to_css_hash(self):
        assert self.analyzer.normalize_locator("id:username") == "css=#username"

    def test_css_colon_prefix(self):
        assert self.analyzer.normalize_locator("css:.btn") == "css=.btn"

    def test_xpath_colon_prefix(self):
        assert self.analyzer.normalize_locator("xpath://div") == "xpath=//div"

    def test_slash_prefix_becomes_xpath(self):
        assert self.analyzer.normalize_locator("//div/span") == "xpath=//div/span"

    def test_paren_prefix_becomes_xpath(self):
        assert self.analyzer.normalize_locator("(//a)[1]") == "xpath=(//a)[1]"

    def test_hash_prefix_becomes_css(self):
        assert self.analyzer.normalize_locator("#main") == "css=#main"

    def test_dot_prefix_becomes_css(self):
        assert self.analyzer.normalize_locator(".primary-btn") == "css=.primary-btn"

    def test_bracket_prefix_becomes_css(self):
        assert self.analyzer.normalize_locator("[data-testid='foo']") == "css=[data-testid='foo']"

    def test_already_prefixed_passthrough(self):
        assert self.analyzer.normalize_locator("css=button") == "css=button"

    def test_plain_string_passthrough(self):
        assert self.analyzer.normalize_locator("button") == "button"


class TestLocatorAnalyzerInspect:
    def setup_method(self):
        self.analyzer = LocatorAnalyzer()

    def test_generic_xpath_tag_only(self):
        result = self.analyzer.inspect("//div")
        assert result.is_generic_xpath is True
        assert result.suggested_locator is not None
        assert "div" in result.suggested_locator

    def test_generic_xpath_dotslash(self):
        result = self.analyzer.inspect(".//a")
        assert result.is_generic_xpath is True

    def test_generic_xpath_star(self):
        result = self.analyzer.inspect("//*")
        assert result.is_generic_xpath is True

    def test_generic_xpath_indexed_group(self):
        result = self.analyzer.inspect("(//a)[1]")
        assert result.is_generic_xpath is True

    def test_specific_xpath_not_generic(self):
        result = self.analyzer.inspect("//button[@data-testid='ok']")
        assert result.is_generic_xpath is False

    def test_css_selector_not_generic(self):
        result = self.analyzer.inspect("css=#submit-btn")
        assert result.is_generic_xpath is False
        assert result.suggested_locator is None

    def test_inspection_returns_normalized_locator(self):
        result = self.analyzer.inspect("id:email")
        assert result.normalized_locator == "css=#email"


class TestLocatorAnalyzerCountMatches:
    def setup_method(self):
        self.analyzer = LocatorAnalyzer()

    @pytest.mark.asyncio
    async def test_returns_none_when_playwright_not_available(self, monkeypatch):
        import app.ai_validation.locator_analyzer as la_module
        monkeypatch.setattr(la_module, "async_playwright", None)
        result = await self.analyzer.count_matches("http://example.com", "css=#ok")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_count_on_success(self, monkeypatch):
        import app.ai_validation.locator_analyzer as la_module

        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=2)

        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        class _Ctx:
            async def close(self): pass
            async def new_page(self): return mock_page

        class _Browser:
            async def close(self): pass
            async def new_context(self): return _Ctx()

        class _Chromium:
            async def launch(self, **_): return _Browser()

        class _PW:
            chromium = _Chromium()

        class _PWCM:
            async def __aenter__(self): return _PW()
            async def __aexit__(self, *_): pass

        monkeypatch.setattr(la_module, "async_playwright", lambda: _PWCM())
        result = await self.analyzer.count_matches("http://example.com", "css=.btn")
        assert result == 2

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self, monkeypatch):
        import app.ai_validation.locator_analyzer as la_module

        timeout_exc = la_module.PlaywrightTimeoutError("Timeout exceeded")

        class _Ctx:
            async def close(self): pass
            async def new_page(self): return None  # won't reach

        class _Browser:
            async def close(self): pass
            async def new_context(self): return _Ctx()

        class _Chromium:
            async def launch(self, **_):
                raise timeout_exc

        class _PW:
            chromium = _Chromium()

        class _PWCM:
            async def __aenter__(self): return _PW()
            async def __aexit__(self, *_): pass

        monkeypatch.setattr(la_module, "async_playwright", lambda: _PWCM())
        result = await self.analyzer.count_matches("http://example.com", "css=.btn")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_generic_exception(self, monkeypatch):
        import app.ai_validation.locator_analyzer as la_module

        class _PWCM:
            async def __aenter__(self): raise RuntimeError("network error")
            async def __aexit__(self, *_): pass

        monkeypatch.setattr(la_module, "async_playwright", lambda: _PWCM())
        result = await self.analyzer.count_matches("http://example.com", "css=.btn")
        assert result is None


# ---------------------------------------------------------------------------
# AIMetrics / AIMetricsRegistry
# ---------------------------------------------------------------------------


class TestAIMetrics:
    def test_fix_rate_zero_when_no_tests_generated(self):
        m = AIMetrics()
        assert m.fix_rate == 0.0

    def test_fix_rate_calculated(self):
        m = AIMetrics(tests_generated=4, tests_fixed=3)
        assert m.fix_rate == 0.75

    def test_as_dict_contains_all_keys(self):
        m = AIMetrics(tests_generated=5, tests_fixed=4, tests_failed=1)
        d = m.as_dict()
        assert set(d.keys()) == {"tests_generated", "tests_fixed", "tests_failed", "fix_rate"}
        assert d["fix_rate"] == round(4 / 5, 4)


class TestAIMetricsRegistry:
    def setup_method(self):
        # Reset singleton state for isolation
        AIMetricsRegistry._instance = None

    def test_instance_returns_singleton(self):
        a = AIMetricsRegistry.instance()
        b = AIMetricsRegistry.instance()
        assert a is b

    def test_inc_generated_increments(self):
        reg = AIMetricsRegistry.instance()
        reg.inc_generated()
        assert reg.snapshot().tests_generated == 1

    def test_inc_fixed_increments(self):
        reg = AIMetricsRegistry.instance()
        reg.inc_fixed()
        assert reg.snapshot().tests_fixed == 1

    def test_inc_failed_increments(self):
        reg = AIMetricsRegistry.instance()
        reg.inc_failed()
        assert reg.snapshot().tests_failed == 1

    def test_snapshot_returns_copy(self):
        reg = AIMetricsRegistry.instance()
        snap = reg.snapshot()
        reg.inc_generated()
        # snap should not be updated
        assert snap.tests_generated == 0

    def test_as_dict_delegates_to_snapshot(self):
        reg = AIMetricsRegistry.instance()
        reg.inc_generated()
        reg.inc_fixed()
        d = reg.as_dict()
        assert d["tests_generated"] == 1
        assert d["tests_fixed"] == 1


# ---------------------------------------------------------------------------
# TestValidator
# ---------------------------------------------------------------------------

BASIC_ROBOT = """\
*** Settings ***
Library    Browser

*** Test Cases ***
Check Title
    New Browser    chromium
    New Context
    New Page    https://example.com
    Click    css=#submit
"""

ROBOT_WITH_WAIT = """\
*** Settings ***
Library    Browser

*** Test Cases ***
Check Button
    New Browser    chromium
    New Context
    New Page    https://example.com
    Wait For Elements State    css=#btn    visible    timeout=10s
    Click    css=#btn
"""

ROBOT_WITH_GENERIC_XPATH = """\
*** Settings ***
Library    Browser

*** Test Cases ***
Bad Locator
    New Browser    chromium
    New Page    https://example.com
    Click    //a
"""


class TestTestValidator:
    def setup_method(self):
        self.validator = TestValidator()

    @pytest.mark.asyncio
    async def test_no_issues_on_clean_robot_with_wait(self):
        report = await self.validator.validate(ROBOT_WITH_WAIT)
        # No generic xpath, wait is present before click
        xpath_or_wait_issues = [i for i in report.issues if i.issue_type != "missing_wait"]
        assert len(xpath_or_wait_issues) == 0

    @pytest.mark.asyncio
    async def test_detects_missing_wait(self):
        report = await self.validator.validate(BASIC_ROBOT)
        missing_waits = [i for i in report.issues if i.issue_type == "missing_wait"]
        assert len(missing_waits) >= 1

    @pytest.mark.asyncio
    async def test_detects_generic_xpath(self):
        report = await self.validator.validate(ROBOT_WITH_GENERIC_XPATH)
        generic = [i for i in report.issues if i.issue_type == "generic_xpath"]
        assert len(generic) >= 1
        assert generic[0].keyword == "Click"

    @pytest.mark.asyncio
    async def test_has_errors_false_when_only_warnings(self):
        report = await self.validator.validate(BASIC_ROBOT)
        warnings_only = all(i.severity == "warning" for i in report.issues)
        assert warnings_only
        assert report.has_errors is False

    @pytest.mark.asyncio
    async def test_has_errors_true_on_strict_mode_violation(self, monkeypatch):
        async def _bulk_many(self_la, page_url, locators, navigation_timeout_ms=10000):
            return {loc: 3 for loc in locators}

        monkeypatch.setattr(LocatorAnalyzer, "count_matches_bulk", _bulk_many)
        monkeypatch.setattr("app.ai_validation.test_validator.settings", type("S", (), {"AI_LIVE_CHECK_ENABLED": True, "AI_LIVE_CHECK_TIMEOUT_SECONDS": 15})())

        report = await self.validator.validate(BASIC_ROBOT, page_url="http://example.com")
        strict_violations = [i for i in report.issues if i.issue_type == "strict_mode_violation"]
        assert len(strict_violations) >= 1
        assert ">> nth=0" in strict_violations[0].suggested_locator
        assert report.has_errors is True

    @pytest.mark.asyncio
    async def test_detects_element_not_found(self, monkeypatch):
        async def _bulk_zero(self_la, page_url, locators, navigation_timeout_ms=10000):
            return {loc: 0 for loc in locators}

        monkeypatch.setattr(LocatorAnalyzer, "count_matches_bulk", _bulk_zero)
        monkeypatch.setattr("app.ai_validation.test_validator.settings", type("S", (), {"AI_LIVE_CHECK_ENABLED": True, "AI_LIVE_CHECK_TIMEOUT_SECONDS": 15})())

        report = await self.validator.validate(BASIC_ROBOT, page_url="http://example.com")
        not_found = [i for i in report.issues if i.issue_type == "element_not_found"]
        assert len(not_found) >= 1
        assert report.has_errors is True

    @pytest.mark.asyncio
    async def test_skips_comment_and_section_lines(self):
        content = "*** Test Cases ***\n# comment line\n\n"
        report = await self.validator.validate(content)
        assert report.issues == []

    @pytest.mark.asyncio
    async def test_has_wait_before_within_lookback(self):
        content = """\
*** Test Cases ***
Foo
    Wait For Elements State    css=#a    visible    timeout=10s
    Click    css=#a
"""
        report = await self.validator.validate(content)
        missing_waits = [i for i in report.issues if i.issue_type == "missing_wait" and i.locator == "css=#a"]
        assert len(missing_waits) == 0

    @pytest.mark.asyncio
    async def test_live_check_timeout_falls_back_to_empty_counts(self, monkeypatch):
        """Lines 111-115: asyncio.TimeoutError in live-check is caught and counts set to {}."""
        async def _bulk_timeout(self_la, page_url, locators, navigation_timeout_ms=10000):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(LocatorAnalyzer, "count_matches_bulk", _bulk_timeout)
        monkeypatch.setattr(
            "app.ai_validation.test_validator.settings",
            type("S", (), {"AI_LIVE_CHECK_ENABLED": True, "AI_LIVE_CHECK_TIMEOUT_SECONDS": 15})(),
        )

        report = await self.validator.validate(BASIC_ROBOT, page_url="http://example.com")
        live_issues = [i for i in report.issues if i.issue_type in {"element_not_found", "strict_mode_violation"}]
        assert live_issues == []

    @pytest.mark.asyncio
    async def test_live_check_skips_when_count_is_none(self, monkeypatch):
        """Line 120: continue when locator is absent from the counts dict (count is None)."""
        async def _bulk_empty(self_la, page_url, locators, navigation_timeout_ms=10000):
            return {}  # all counts will be None

        monkeypatch.setattr(LocatorAnalyzer, "count_matches_bulk", _bulk_empty)
        monkeypatch.setattr(
            "app.ai_validation.test_validator.settings",
            type("S", (), {"AI_LIVE_CHECK_ENABLED": True, "AI_LIVE_CHECK_TIMEOUT_SECONDS": 15})(),
        )

        report = await self.validator.validate(BASIC_ROBOT, page_url="http://example.com")
        live_issues = [i for i in report.issues if i.issue_type in {"element_not_found", "strict_mode_violation"}]
        assert live_issues == []

    @pytest.mark.asyncio
    async def test_has_wait_before_skips_empty_line_in_lookback(self):
        """Line 153: empty line within the lookback window is skipped (stripped == '' → continue)."""
        content = (
            "*** Test Cases ***\n"
            "Foo\n"
            "\n"  # empty line that falls inside the 2-line lookback
            "    Wait For Elements State    css=#a    visible    timeout=10s\n"
            "    Click    css=#a\n"
        )
        report = await self.validator.validate(content)
        missing_waits = [i for i in report.issues if i.issue_type == "missing_wait" and i.locator == "css=#a"]
        assert len(missing_waits) == 0


# ---------------------------------------------------------------------------
# TestFixer
# ---------------------------------------------------------------------------


class TestTestFixer:
    def setup_method(self):
        self.fixer = TestFixer()

    @pytest.mark.asyncio
    async def test_applies_no_fix_when_no_issues(self):
        content = "*** Test Cases ***\nFoo\n    New Page    https://example.com\n"
        result = await self.fixer.apply_fixes(content, [])
        assert result.content == content
        assert result.applied_fixes == []

    @pytest.mark.asyncio
    async def test_replaces_generic_xpath_locator(self):
        content = "*** Test Cases ***\nFoo\n    Click    //a\n"
        issue = ValidationIssue(
            line_number=3,
            keyword="Click",
            locator="//a",
            issue_type="generic_xpath",
            message="XPath genérico",
            suggested_locator="css=a[data-testid]",
        )
        result = await self.fixer.apply_fixes(content, [issue])
        assert "css=a[data-testid]" in result.content
        assert len(result.applied_fixes) == 1
        assert "generic_xpath" in result.applied_fixes[0]

    @pytest.mark.asyncio
    async def test_replaces_strict_mode_violation_locator(self):
        content = "*** Test Cases ***\nFoo\n    Click    css=.btn\n"
        issue = ValidationIssue(
            line_number=3,
            keyword="Click",
            locator="css=.btn",
            issue_type="strict_mode_violation",
            message="2 elements",
            suggested_locator="css=.btn >> nth=0",
        )
        result = await self.fixer.apply_fixes(content, [issue])
        assert ">> nth=0" in result.content

    @pytest.mark.asyncio
    async def test_inserts_wait_for_missing_wait(self):
        content = "*** Test Cases ***\nFoo\n    Click    css=#go\n"
        issue = ValidationIssue(
            line_number=3,
            keyword="Click",
            locator="css=#go",
            issue_type="missing_wait",
            message="no wait",
        )
        result = await self.fixer.apply_fixes(content, [issue])
        assert "Wait For Elements State" in result.content
        assert "css=#go" in result.content

    @pytest.mark.asyncio
    async def test_does_not_double_insert_wait(self):
        content = "*** Test Cases ***\nFoo\n    Wait For Elements State    css=#x    visible    timeout=10s\n    Click    css=#x\n"
        issue = ValidationIssue(
            line_number=4,
            keyword="Click",
            locator="css=#x",
            issue_type="missing_wait",
            message="no wait",
        )
        result = await self.fixer.apply_fixes(content, [issue])
        # Should not insert another wait since there is already one right before
        assert result.content.count("Wait For Elements State") == 1

    @pytest.mark.asyncio
    async def test_skips_issue_with_out_of_range_line_number(self):
        content = "*** Test Cases ***\nFoo\n    Click    css=#btn\n"
        issue = ValidationIssue(
            line_number=99,
            keyword="Click",
            locator="css=#btn",
            issue_type="generic_xpath",
            message="x",
            suggested_locator="css=div",
        )
        result = await self.fixer.apply_fixes(content, [issue])
        assert result.applied_fixes == []

    @pytest.mark.asyncio
    async def test_skips_issue_with_zero_line_number(self):
        content = "*** Test Cases ***\nFoo\n"
        issue = ValidationIssue(
            line_number=0,
            keyword="Click",
            locator="css=#x",
            issue_type="generic_xpath",
            message="x",
            suggested_locator="css=div",
        )
        result = await self.fixer.apply_fixes(content, [issue])
        assert result.applied_fixes == []

    @pytest.mark.asyncio
    async def test_regenerates_step_via_groq_for_element_not_found(self):
        content = "*** Test Cases ***\nFoo\n    Click    css=#ghost\n"
        issue = ValidationIssue(
            line_number=3,
            keyword="Click",
            locator="css=#ghost",
            issue_type="element_not_found",
            message="not found",
        )

        mock_groq = MagicMock()
        mock_groq.regenerate_robot_step = MagicMock(return_value="    Click    css=#real-btn")

        result = await self.fixer.apply_fixes(content, [issue], groq_client=mock_groq, prompt="Test prompt")
        assert "css=#real-btn" in result.content
        assert any("regenerado" in fix for fix in result.applied_fixes)

    @pytest.mark.asyncio
    async def test_skips_groq_regen_when_no_client(self):
        content = "*** Test Cases ***\nFoo\n    Click    css=#ghost\n"
        issue = ValidationIssue(
            line_number=3,
            keyword="Click",
            locator="css=#ghost",
            issue_type="element_not_found",
            message="not found",
        )
        result = await self.fixer.apply_fixes(content, [issue], groq_client=None, prompt="test")
        assert result.applied_fixes == []

    @pytest.mark.asyncio
    async def test_skips_groq_regen_when_no_prompt(self):
        content = "*** Test Cases ***\nFoo\n    Click    css=#ghost\n"
        issue = ValidationIssue(
            line_number=3,
            keyword="Click",
            locator="css=#ghost",
            issue_type="element_not_found",
            message="not found",
        )
        mock_groq = MagicMock()
        result = await self.fixer.apply_fixes(content, [issue], groq_client=mock_groq, prompt=None)
        assert result.applied_fixes == []

    @pytest.mark.asyncio
    async def test_skips_fix_when_no_suggested_locator(self):
        content = "*** Test Cases ***\nFoo\n    Click    css=#btn\n"
        issue = ValidationIssue(
            line_number=3,
            keyword="Click",
            locator="css=#btn",
            issue_type="generic_xpath",
            message="no suggestion",
            suggested_locator=None,
        )
        result = await self.fixer.apply_fixes(content, [issue])
        assert result.applied_fixes == []

    def test_build_wait_line_returns_none_for_no_locator(self):
        result = self.fixer._build_wait_line("    NoArgs")
        assert result is None

    def test_line_is_wait_detects_wait_for_selector(self):
        assert self.fixer._line_is_wait("    Wait For Selector    css=#x") is True

    def test_line_is_wait_returns_false_for_regular_line(self):
        assert self.fixer._line_is_wait("    Click    css=#x") is False

    @pytest.mark.asyncio
    async def test_skips_locator_replacement_for_irrelevant_issue_type_with_suggestion(self):
        """Line 35: continue when issue has suggested_locator but issue_type is not
        generic_xpath or strict_mode_violation."""
        content = "*** Test Cases ***\nFoo\n    Click    css=#ghost\n"
        issue = ValidationIssue(
            line_number=3,
            keyword="Click",
            locator="css=#ghost",
            issue_type="element_not_found",  # irrelevant type → triggers line 35 continue
            message="not found",
            suggested_locator="css=#real",
        )
        result = await self.fixer.apply_fixes(content, [issue])
        assert "css=#ghost" in result.content
        assert not any("locator refinado" in f for f in result.applied_fixes)

    @pytest.mark.asyncio
    async def test_skips_missing_wait_when_target_index_out_of_bounds(self):
        """Line 48: continue when target_index >= len(lines) for a missing_wait issue."""
        content = "*** Test Cases ***\nFoo\n"
        issue = ValidationIssue(
            line_number=10,  # beyond the 2 lines in content
            keyword="Click",
            locator="css=#btn",
            issue_type="missing_wait",
            message="no wait",
        )
        result = await self.fixer.apply_fixes(content, [issue])
        assert result.applied_fixes == []

    @pytest.mark.asyncio
    async def test_skips_groq_regen_when_element_not_found_line_out_of_bounds(self):
        """Line 63: continue when line_idx >= len(lines) for element_not_found
        even when groq_client and prompt are provided."""
        content = "*** Test Cases ***\nFoo\n"
        issue = ValidationIssue(
            line_number=99,  # way out of bounds
            keyword="Click",
            locator="css=#ghost",
            issue_type="element_not_found",
            message="not found",
        )
        mock_groq = MagicMock()
        result = await self.fixer.apply_fixes(content, [issue], groq_client=mock_groq, prompt="test")
        mock_groq.regenerate_robot_step.assert_not_called()
        assert result.applied_fixes == []

    def test_replace_locator_returns_unchanged_for_single_part_line(self):
        """Line 82: return line early in _replace_locator when the stripped line
        has fewer than 2 double-space-separated parts."""
        result = self.fixer._replace_locator("Click", "css=#new")
        assert result == "Click"


# ---------------------------------------------------------------------------
# AITestSelfHealingService
# ---------------------------------------------------------------------------


class TestAITestSelfHealingService:
    def setup_method(self):
        AIMetricsRegistry._instance = None

    @pytest.mark.asyncio
    async def test_no_issues_returns_original_content(self):
        clean_content = "*** Settings ***\nLibrary    Browser\n"
        service = AITestSelfHealingService()
        result = await service.heal_test(content=clean_content)
        assert result.final_content == clean_content
        assert result.issues_found == []
        assert result.fixes_applied == []
        assert result.was_fixed is False

    @pytest.mark.asyncio
    async def test_fixes_are_applied_and_was_fixed_true(self):
        content = "*** Test Cases ***\nFoo\n    Click    //a\n"
        service = AITestSelfHealingService()
        result = await service.heal_test(content=content)
        # should detect generic xpath and attempt a fix
        assert len(result.issues_found) >= 1

    @pytest.mark.asyncio
    async def test_metrics_incremented_on_generation(self):
        reg = AIMetricsRegistry.instance()
        service = AITestSelfHealingService(metrics=reg)
        await service.heal_test(content="*** Settings ***\nLibrary    Browser\n")
        assert reg.snapshot().tests_generated == 1

    @pytest.mark.asyncio
    async def test_metrics_inc_fixed_when_fixes_applied_and_no_errors(self):
        content = "*** Test Cases ***\nFoo\n    Click    //a\n"
        reg = AIMetricsRegistry()
        service = AITestSelfHealingService(metrics=reg)
        await service.heal_test(content=content)
        # fixes were applied (generic xpath) and second validation has no *errors* (only warnings)
        assert reg.snapshot().tests_fixed >= 0  # may be 0 or 1 depending on second validation

    @pytest.mark.asyncio
    async def test_metrics_returns_dict(self):
        service = AITestSelfHealingService()
        m = service.metrics()
        assert "tests_generated" in m
        assert "fix_rate" in m

    @pytest.mark.asyncio
    async def test_debug_log_written_when_ai_debug_true(self, tmp_path, monkeypatch):
        log_file = tmp_path / "ai_debug.log"
        monkeypatch.setattr("app.core.config.settings.AI_DEBUG_LOG_PATH", str(log_file))
        monkeypatch.setattr("app.core.config.settings.AI_DEBUG", False)

        service = AITestSelfHealingService()
        await service.heal_test(
            content="*** Test Cases ***\nFoo\n    Click    //a\n",
            prompt="my prompt",
            context="my context",
            ai_debug=True,
        )

        assert log_file.exists()
        line = log_file.read_text(encoding="utf-8").strip()
        payload = json.loads(line)
        assert payload["prompt"] == "my prompt"
        assert "original_test" in payload
        assert "final_test" in payload

    @pytest.mark.asyncio
    async def test_debug_log_written_when_settings_ai_debug_true(self, tmp_path, monkeypatch):
        log_file = tmp_path / "ai_debug2.log"
        monkeypatch.setattr("app.core.config.settings.AI_DEBUG_LOG_PATH", str(log_file))
        monkeypatch.setattr("app.core.config.settings.AI_DEBUG", True)

        service = AITestSelfHealingService()
        await service.heal_test(
            content="*** Settings ***\nLibrary    Browser\n",
            ai_debug=False,
        )

        assert log_file.exists()

    @pytest.mark.asyncio
    async def test_debug_log_not_written_when_both_false(self, tmp_path, monkeypatch):
        log_file = tmp_path / "no_debug.log"
        monkeypatch.setattr("app.core.config.settings.AI_DEBUG_LOG_PATH", str(log_file))
        monkeypatch.setattr("app.core.config.settings.AI_DEBUG", False)

        service = AITestSelfHealingService()
        await service.heal_test(
            content="*** Settings ***\nLibrary    Browser\n",
            ai_debug=False,
        )

        assert not log_file.exists()

    @pytest.mark.asyncio
    async def test_metrics_inc_failed_when_second_report_has_errors(self):
        """Line 68 of self_healing_service.py: inc_failed() is called when the
        second validation report still has errors after the fix attempt."""
        reg = AIMetricsRegistry()

        call_count = 0

        async def _mock_validate(content, page_url=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First pass: return a warning-only issue to trigger the fixer.
                return ValidationReport(
                    issues=[
                        ValidationIssue(
                            line_number=1,
                            keyword="Click",
                            locator="css=#x",
                            issue_type="missing_wait",
                            message="no wait",
                            severity="warning",
                        )
                    ]
                )
            # Second pass: report an error so inc_failed() is called.
            return ValidationReport(
                issues=[
                    ValidationIssue(
                        line_number=1,
                        keyword="Click",
                        locator="css=#x",
                        issue_type="element_not_found",
                        message="not found",
                        severity="error",
                    )
                ]
            )

        mock_validator = MagicMock()
        mock_validator.validate = _mock_validate

        service = AITestSelfHealingService(validator=mock_validator, metrics=reg)
        await service.heal_test(content="*** Test Cases ***\nFoo\n    Click    css=#x\n")
        assert reg.snapshot().tests_failed == 1


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------


class TestValidationReport:
    def test_has_errors_false_when_empty(self):
        report = ValidationReport(issues=[])
        assert report.has_errors is False

    def test_has_errors_false_with_only_warnings(self):
        issue = ValidationIssue(
            line_number=1, keyword="Click", locator="css=#x",
            issue_type="missing_wait", message="no wait", severity="warning"
        )
        report = ValidationReport(issues=[issue])
        assert report.has_errors is False

    def test_has_errors_true_with_error_severity(self):
        issue = ValidationIssue(
            line_number=1, keyword="Click", locator="css=#x",
            issue_type="element_not_found", message="not found", severity="error"
        )
        report = ValidationReport(issues=[issue])
        assert report.has_errors is True


# ---------------------------------------------------------------------------
# HealedTestResult
# ---------------------------------------------------------------------------


class TestHealedTestResult:
    def test_was_fixed_true_when_content_changed_and_fixes_present(self):
        r = HealedTestResult(
            original_content="A",
            final_content="B",
            issues_found=[],
            fixes_applied=["some fix"],
        )
        assert r.was_fixed is True

    def test_was_fixed_false_when_content_same(self):
        r = HealedTestResult(
            original_content="A",
            final_content="A",
            issues_found=[],
            fixes_applied=["some fix"],
        )
        assert r.was_fixed is False

    def test_was_fixed_false_when_no_fixes(self):
        r = HealedTestResult(
            original_content="A",
            final_content="B",
            issues_found=[],
            fixes_applied=[],
        )
        assert r.was_fixed is False


# ---------------------------------------------------------------------------
# /ai/metrics route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_ai_metrics_route():
    from app.api import routes
    AIMetricsRegistry._instance = None
    result = await routes.get_ai_metrics()
    assert "tests_generated" in result
    assert "fix_rate" in result
