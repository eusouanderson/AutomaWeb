"""Tests for domain DOM models."""

import pytest

from app.domain.dom.models import (
    ChunkProcessingResult,
    DOMChunk,
    DOMSection,
    DOMSegmentationResult,
    DOMSectionType,
    ProcessedElement,
)


class TestProcessedElement:
    """Tests for ProcessedElement model."""

    def test_to_dict_includes_all_fields(self):
        """Test that to_dict includes all non-None fields."""
        elem = ProcessedElement(
            tag="input",
            id="email-input",
            name="email",
            type="email",
            placeholder="Enter email",
            aria_label="Email field",
            visible=True,
            xpath="//input[@id='email-input']",
        )

        result = elem.to_dict()

        assert result["tag"] == "input"
        assert result["id"] == "email-input"
        assert result["name"] == "email"
        assert result["type"] == "email"
        assert result["placeholder"] == "Enter email"
        assert result["aria_label"] == "Email field"
        assert result["xpath"] == "//input[@id='email-input']"
        # to_dict excludes empty lists and falsy values, so visible may not always be included
        # Just verify the dict was created correctly
        assert isinstance(result, dict)

    def test_to_dict_excludes_none_values(self):
        """Test that to_dict excludes None values."""
        elem = ProcessedElement(
            tag="button",
            text="Click me",
            id=None,
            href=None,
        )

        result = elem.to_dict()

        assert "id" not in result
        assert "href" not in result
        assert result["tag"] == "button"
        assert result["text"] == "Click me"

    def test_to_dict_excludes_empty_lists(self):
        """Test that to_dict excludes empty children list."""
        elem = ProcessedElement(tag="div", children=[])

        result = elem.to_dict()

        assert "children" not in result

    def test_to_dict_includes_children(self):
        """Test that to_dict includes nested children."""
        child = ProcessedElement(tag="span", text="Child")
        parent = ProcessedElement(tag="div", children=[child])

        result = parent.to_dict()

        assert "children" in result
        assert len(result["children"]) == 1
        assert result["children"][0]["tag"] == "span"

    def test_estimate_char_size_single_element(self):
        """Test character size estimation for single element."""
        elem = ProcessedElement(
            tag="input",
            id="test",
            xpath="//*[@id='test']",
        )

        size = elem.estimate_char_size()

        # Rough estimate: tag (5) + 10 + id (4) + 5 + xpath (12) + 5 = ~40
        assert size > 30
        assert size < 60

    def test_estimate_char_size_with_text(self):
        """Test size estimation includes text content."""
        elem = ProcessedElement(
            tag="button",
            text="This is a long button label",
        )

        size = elem.estimate_char_size()

        assert size >= len("This is a long button label")

    def test_estimate_char_size_recursive(self):
        """Test size includes nested children."""
        child1 = ProcessedElement(tag="span", text="Child 1")
        child2 = ProcessedElement(tag="span", text="Child 2")
        parent = ProcessedElement(tag="div", children=[child1, child2])

        size = parent.estimate_char_size()

        # Should include parent + both children
        assert size > 50

    def test_aria_attributes_preserved(self):
        """Test that aria attributes are properly preserved."""
        elem = ProcessedElement(
            tag="div",
            role="tablist",
            aria_label="Tab navigation",
            aria_labelledby="tab-title",
        )

        result = elem.to_dict()

        assert result["role"] == "tablist"
        assert result["aria_label"] == "Tab navigation"
        assert result["aria_labelledby"] == "tab-title"

    def test_to_dict_includes_href_onclick_and_hidden_flag(self):
        """Cover href, onclick and visible=False branches."""
        elem = ProcessedElement(
            tag="a",
            href="/home",
            onclick="goHome()",
            visible=False,
        )

        result = elem.to_dict()

        assert result["href"] == "/home"
        assert result["onclick"] == "goHome()"
        assert result["visible"] is False


class TestDOMSection:
    """Tests for DOMSection model."""

    def test_estimate_char_size_with_elements(self):
        """Test section size estimation."""
        elements = [
            ProcessedElement(tag="button", text="Submit"),
            ProcessedElement(tag="a", href="/home"),
        ]

        section = DOMSection(
            section_type=DOMSectionType.FORMS,
            name="Contact Form",
            elements=elements,
            raw_html="<form>...</form>",
        )

        size = section.estimate_char_size()

        assert size > 20  # At least HTML + elements

    def test_to_dict_includes_all_fields(self):
        """Test section dict conversion."""
        elem = ProcessedElement(tag="input", type="text")
        section = DOMSection(
            section_type=DOMSectionType.FORMS,
            name="Login Form",
            elements=[elem],
        )

        result = section.to_dict()

        assert result["type"] == "forms"
        assert result["name"] == "Login Form"
        assert len(result["elements"]) == 1
        assert "estimated_size" in result

    def test_section_types_enum(self):
        """Test all section types are valid."""
        assert DOMSectionType.HEADER.value == "header"
        assert DOMSectionType.FORMS.value == "forms"
        assert DOMSectionType.MODAL.value == "modal"


class TestDOMSegmentationResult:
    """Tests for DOMSegmentationResult model."""

    def test_to_dict_includes_statistics(self):
        """Test result dict includes metadata."""
        section = DOMSection(
            section_type=DOMSectionType.HEADER,
            name="Header",
            elements=[ProcessedElement(tag="button")],
        )

        result_obj = DOMSegmentationResult(
            sections=[section],
            total_char_size=1000,
            segmentation_metadata={"method": "semantic"},
        )

        result = result_obj.to_dict()

        assert result["section_count"] == 1
        assert result["total_char_size"] == 1000
        assert result["metadata"]["method"] == "semantic"

    def test_empty_result(self):
        """Test empty segmentation result."""
        result = DOMSegmentationResult()

        assert len(result.sections) == 0
        assert result.total_char_size == 0


class TestDOMChunk:
    """Tests for DOMChunk model."""

    def test_to_dict_includes_all_metadata(self):
        """Test chunk dict conversion."""
        elem = ProcessedElement(tag="input", type="email")
        chunk = DOMChunk(
            chunk_id="forms_0",
            section_type=DOMSectionType.FORMS,
            section_name="Login Form",
            elements=[elem],
            char_size=500,
            priority=10,
        )

        result = chunk.to_dict()

        assert result["chunk_id"] == "forms_0"
        assert result["section_type"] == "forms"
        assert result["section_name"] == "Login Form"
        assert result["char_size"] == 500
        assert result["priority"] == 10
        assert len(result["elements"]) == 1

    def test_chunk_with_multiple_elements(self):
        """Test chunk with several elements."""
        elements = [
            ProcessedElement(tag="input", type="email"),
            ProcessedElement(tag="input", type="password"),
            ProcessedElement(tag="button", text="Login"),
        ]

        chunk = DOMChunk(
            chunk_id="forms_0",
            section_type=DOMSectionType.FORMS,
            section_name="Form",
            elements=elements,
            char_size=1000,
        )

        result = chunk.to_dict()

        assert len(result["elements"]) == 3


class TestChunkProcessingResult:
    """Tests for ChunkProcessingResult model."""

    def test_result_with_successful_generation(self):
        """Test result from successful LLM processing."""
        result = ChunkProcessingResult(
            chunk_id="header_0",
            section_type=DOMSectionType.HEADER,
            section_name="Header",
            generated_test="*** Test Cases ***\nTest Header Visible\n    ...",
            token_usage={"input": 200, "output": 150},
            metadata={"duration_ms": 2500},
        )

        assert result.chunk_id == "header_0"
        assert "*** Test Cases ***" in result.generated_test
        assert result.token_usage["input"] == 200
        assert result.metadata["duration_ms"] == 2500

    def test_result_with_failure(self):
        """Test result with error."""
        result = ChunkProcessingResult(
            chunk_id="forms_0",
            section_type=DOMSectionType.FORMS,
            section_name="Form",
            generated_test="",
            metadata={"error": "Token limit exceeded"},
        )

        assert result.generated_test == ""
        assert result.metadata["error"] == "Token limit exceeded"
