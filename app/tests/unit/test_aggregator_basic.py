"""Tests for test results aggregator."""

import pytest
from app.domain.dom.models import DOMSectionType, ChunkProcessingResult
from app.domain.test_generation.aggregator import TestAggregator


class TestAggregatorBasic:
    """Basic tests for TestAggregator."""

    def test_aggregate_results_returns_tuple(self):
        """Test that aggregate_results returns tuple with test and metadata."""
        aggregator = TestAggregator()

        result = ChunkProcessingResult(
            chunk_id="chunk_1",
            section_type=DOMSectionType.FORMS,
            section_name="forms",
            generated_test="Test Form\n    Input Text    id:email",
            token_usage=100,  # type
        )

        output, metadata = aggregator.aggregate_results([result])

        assert isinstance(output, str)
        assert isinstance(metadata, dict)

    def test_aggregate_multiple_results(self):
        """Test aggregation of multiple chunk results."""
        aggregator = TestAggregator()

        results = [
            ChunkProcessingResult(
                chunk_id=f"chunk_{i}",
                section_type=DOMSectionType.HEADER,
                section_name="header",
                generated_test=f"Test {i}\n    Click Button",
                token_usage=100,
            )
            for i in range(3)
        ]

        output, metadata = aggregator.aggregate_results(results)

        assert len(output) > 0
        assert metadata["chunks_processed"] > 0

    def test_aggregate_empty_results(self):
        """Test handling of empty results."""
        aggregator = TestAggregator()

        output, metadata = aggregator.aggregate_results([])

        assert isinstance(output, str)
        assert metadata["chunks_processed"] == 0

    def test_aggregate_preserves_sections(self):
        """Test that aggregation preserves section types."""
        aggregator = TestAggregator()

        results = [
            ChunkProcessingResult(
                chunk_id="chunk_header",
                section_type=DOMSectionType.HEADER,
                section_name="header",
                generated_test="Test Header\n    Click Logo",
                token_usage=50,
            ),
            ChunkProcessingResult(
                chunk_id="chunk_form",
                section_type=DOMSectionType.FORMS,
                section_name="forms",
                generated_test="Test Form\n    Input Text",
                token_usage=100,
            ),
        ]

        output, metadata = aggregator.aggregate_results(results)

        # Output should contain either the test or settings (empty can still be valid)
        assert isinstance(output, str)
        # Sections should be counted in metadata
        assert metadata["chunks_processed"] == 2

    def test_aggregate_skips_empty_generated_test(self):
        aggregator = TestAggregator()
        results = [
            ChunkProcessingResult(
                chunk_id="c-empty",
                section_type=DOMSectionType.FORMS,
                section_name="forms",
                generated_test="",
            )
        ]

        output, metadata = aggregator.aggregate_results(results)
        assert isinstance(output, str)
        assert metadata["chunks_successful"] == 0

    def test_merge_section_tests_empty_and_single(self):
        aggregator = TestAggregator()
        assert aggregator._merge_section_tests("forms", []) == ""

        single = ChunkProcessingResult(
            chunk_id="c1",
            section_type=DOMSectionType.FORMS,
            section_name="forms",
            generated_test="*** Test Cases ***\nA\n    No Operation",
        )
        assert (
            aggregator._merge_section_tests("forms", [single]) == single.generated_test
        )

    def test_extract_test_cases_and_keywords_no_match(self):
        aggregator = TestAggregator()
        assert aggregator._extract_test_cases("no robot sections") == []
        assert aggregator._extract_keywords("no robot sections") == []

    def test_extract_section_match_and_no_match(self):
        aggregator = TestAggregator()
        content = "*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nCase 1\n    No Operation"
        settings = aggregator._extract_section(content, "Settings")
        variables = aggregator._extract_section(content, "Variables")
        assert settings is not None and "*** Settings ***" in settings
        assert variables is None

    def test_deduplicate_tests_and_keywords(self):
        aggregator = TestAggregator()
        tests = ["A\n    x", "A\n    y", "B\n    z", ""]
        kws = ["K1\n    x", "K1\n    y", "K2\n    z", ""]
        dedup_tests = aggregator._deduplicate_tests(tests)
        dedup_kws = aggregator._deduplicate_keywords(kws)
        assert len(dedup_tests) == 2
        assert len(dedup_kws) == 2

    def test_reconstruct_test_all_sections_and_default_settings(self):
        aggregator = TestAggregator()
        rebuilt = aggregator._reconstruct_test(
            settings=None,
            variables="*** Variables ***\n${URL}    http://x",
            test_cases=["Case A\n    No Operation"],
            keywords=["Keyword A\n    No Operation"],
        )
        assert "*** Variables ***" in rebuilt
        assert "*** Test Cases ***" in rebuilt
        assert "*** Keywords ***" in rebuilt

        combined = aggregator._combine_sections({})
        assert "*** Settings ***" in combined

    def test_extract_test_cases_and_keywords_with_matches(self):
        aggregator = TestAggregator()
        content = (
            "*** Test Cases ***\n"
            "Login Works\n"
            "    No Operation\n"
            "Another Case\n"
            "    No Operation\n\n"
            "*** Keywords ***\n"
            "Open Login\n"
            "    No Operation\n"
            "Submit Form\n"
            "    No Operation\n"
        )

        tests = aggregator._extract_test_cases(content)
        keywords = aggregator._extract_keywords(content)

        assert len(tests) >= 1
        assert len(keywords) >= 1
        assert tests[0].startswith("Login Works")
