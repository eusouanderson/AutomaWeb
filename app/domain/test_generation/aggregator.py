"""Test aggregation and merging logic."""

import logging
import re
from typing import Optional

from app.domain.dom.models import ChunkProcessingResult

logger = logging.getLogger(__name__)


class TestAggregator:
    """Aggregates and merges Robot Framework tests from multiple chunks."""

    def __init__(self):
        """Initialize aggregator."""
        self._section_tests: dict[str, str] = {}

    def aggregate_results(
        self, results: list[ChunkProcessingResult]
    ) -> tuple[str, dict]:
        """Aggregate chunk results into single Robot Framework test suite.

        Args:
            results: List of ChunkProcessingResult from all chunks

        Returns:
            Tuple of (merged_test_content, metadata)
        """
        self._section_tests = {}

        # Group results by section type
        by_section = {}
        for result in results:
            if not result.generated_test:
                logger.warning("Skipping empty result from chunk: %s", result.chunk_id)
                continue

            section_key = result.section_type.value
            if section_key not in by_section:
                by_section[section_key] = []
            by_section[section_key].append(result)

        # Merge tests per section
        section_tests = {}
        for section_type, section_results in by_section.items():
            merged = self._merge_section_tests(section_type, section_results)
            if merged:
                section_tests[section_type] = merged

        # Combine all sections into single suite
        final_suite = self._combine_sections(section_tests)

        metadata = {
            "sections_processed": len(section_tests),
            "chunks_processed": len(results),
            "chunks_successful": len([r for r in results if r.generated_test]),
        }

        logger.info(
            "Aggregated %d sections from %d results", len(section_tests), len(results)
        )

        return final_suite, metadata

    def _merge_section_tests(
        self, section_type: str, results: list[ChunkProcessingResult]
    ) -> str:
        """Merge multiple test results from same section.

        Args:
            section_type: Section type identifier
            results: Chunk results from same section

        Returns:
            Merged Robot Framework test code
        """
        if not results:
            return ""

        if len(results) == 1:
            return results[0].generated_test

        logger.info("Merging %d results from section: %s", len(results), section_type)

        # Extract test cases and keywords from each result
        all_test_cases = []
        all_keywords = []
        settings = None
        variables = None

        for result in results:
            test_content = result.generated_test

            tc = self._extract_test_cases(test_content)
            all_test_cases.extend(tc)

            kw = self._extract_keywords(test_content)
            all_keywords.extend(kw)

            if not settings:
                settings = self._extract_section(test_content, "Settings")
            if not variables:
                variables = self._extract_section(test_content, "Variables")

        # Remove duplicate test cases
        all_test_cases = self._deduplicate_tests(all_test_cases)

        # Remove duplicate keywords
        all_keywords = self._deduplicate_keywords(all_keywords)

        # Reconstruct merged test file
        merged = self._reconstruct_test(
            settings, variables, all_test_cases, all_keywords
        )
        return merged

    def _combine_sections(self, section_tests: dict[str, str]) -> str:
        """Combine all section tests into a single suite.

        Args:
            section_tests: Dict of section_type -> test_content

        Returns:
            Combined Robot Framework test content
        """
        all_test_cases = []
        all_keywords = []
        settings = None
        variables = None

        # Process each section in order
        section_order = [
            "header",
            "navigation",
            "main_content",
            "forms",
            "sidebar",
            "footer",
            "modal",
            "unknown",
        ]

        for section_type in section_order:
            if section_type not in section_tests:
                continue

            test_content = section_tests[section_type]

            # Extract components
            tc = self._extract_test_cases(test_content)
            # Prefix test names with section for clarity
            tc = [
                (
                    f"Test {section_type.title()} - {name.strip()}"
                    if not name.startswith(f"Test {section_type.title()}")
                    else name
                )
                for name in tc
            ]
            all_test_cases.extend(tc)

            kw = self._extract_keywords(test_content)
            all_keywords.extend(kw)

            if not settings:
                settings = self._extract_section(test_content, "Settings")
            if not variables:
                variables = self._extract_section(test_content, "Variables")

        # Deduplicate
        all_test_cases = self._deduplicate_tests(all_test_cases)
        all_keywords = self._deduplicate_keywords(all_keywords)

        # Use combined settings with browser setup
        if not settings:
            settings = self._default_settings()

        return self._reconstruct_test(settings, variables, all_test_cases, all_keywords)

    def _extract_test_cases(self, content: str) -> list[str]:
        """Extract test case blocks from Robot Framework content."""
        match = re.search(
            r"^\*\*\* Test Cases \*\*\*\s*\n(.*?)(?=\n\*\*\*|$)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        if not match:
            return []

        test_block = match.group(1)
        # Split by test case names (starting at line beginning)
        tests = re.split(r"\n(?=[A-Z])", test_block)
        return [t.strip() for t in tests if t.strip()]

    def _extract_keywords(self, content: str) -> list[str]:
        """Extract keyword definitions from Robot Framework content."""
        match = re.search(
            r"^\*\*\* Keywords \*\*\*\s*\n(.*?)(?=\n\*\*\*|$)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        if not match:
            return []

        keyword_block = match.group(1)
        # Split by keyword names (starting at line beginning)
        keywords = re.split(r"\n(?=[A-Z])", keyword_block)
        return [k.strip() for k in keywords if k.strip()]

    def _extract_section(self, content: str, section_name: str) -> str | None:
        """Extract a Robot Framework section (Settings, Variables, etc.)."""
        pattern = f"^\\*\\*\\* {section_name} \\*\\*\\*\\s*\n(.*?)(?=\n\\*\\*\\*|$)"
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
        if match:
            return f"*** {section_name} ***\n{match.group(1).rstrip()}"
        return None

    def _deduplicate_tests(self, tests: list[str]) -> list[str]:
        """Remove duplicate test cases."""
        seen = set()
        unique = []
        for test in tests:
            # Use first line (test name) as key
            key = test.split("\n")[0] if test else ""
            if key and key not in seen:
                seen.add(key)
                unique.append(test)
        return unique

    def _deduplicate_keywords(self, keywords: list[str]) -> list[str]:
        """Remove duplicate keywords."""
        seen = set()
        unique = []
        for keyword in keywords:
            # Use first line (keyword name) as key
            key = keyword.split("\n")[0] if keyword else ""
            if key and key not in seen:
                seen.add(key)
                unique.append(keyword)
        return unique

    def _reconstruct_test(
        self,
        settings: str | None,
        variables: str | None,
        test_cases: list[str],
        keywords: list[str],
    ) -> str:
        """Reconstruct Robot Framework test file from components."""
        parts = []

        if settings:
            parts.append(settings)

        if variables:
            parts.append(variables)

        if test_cases:
            parts.append("*** Test Cases ***")
            parts.extend(test_cases)

        if keywords:
            parts.append("*** Keywords ***")
            parts.extend(keywords)

        return "\n\n".join(parts)

    def _default_settings(self) -> str:
        """Return default Robot Framework settings for browser testing."""
        return """*** Settings ***
Library    Browser
Suite Teardown    Close Browser"""
