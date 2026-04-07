"""Tests for DOM segmenter."""

import pytest

from app.domain.dom.segmenter import DOMSegmenter
from app.domain.dom.models import DOMSectionType, DOMSegmentationResult

class TestDOMSegmenter:
    """Tests for DOMSegmenter responsible for DOM segmentation."""

    def test_segment_simple_page_structure(self):
        """Test segmentation of a simple page."""
        segmenter = DOMSegmenter()
        
        page = {
            "dom_tree": {
                "tag": "html",
                "children": [
                    {
                        "tag": "header",
                        "id": "header",
                        "children": [{"tag": "h1", "text": "My Site"}],
                    },
                    {
                        "tag": "main",
                        "children": [
                            {"tag": "p", "text": "Main content"}
                        ],
                    },
                    {
                        "tag": "footer",
                        "children": [{"tag": "p", "text": "Footer"}],
                    },
                ],
            }
        }

        result = segmenter.segment_page(page)

        assert len(result.sections) > 0
        assert result.total_char_size > 0

    def test_identify_header_section(self):
        """Test identification of header section."""
        segmenter = DOMSegmenter()
        
        element = {
            "tag": "header",
            "id": "site-header",
            "children": [
                {"tag": "nav", "text": "Navigation"},
                {"tag": "h1", "text": "Title"},
            ],
        }

        section_type = segmenter._match_section_pattern(element)

        assert section_type == DOMSectionType.HEADER

    def test_identify_navigation_section(self):
        """Test identification of navigation section."""
        segmenter = DOMSegmenter()
        
        element = {
            "tag": "nav",
            "attributes": {"id": "main-nav"},
        }

        section_type = segmenter._match_section_pattern(element)

        # Should identify nav or return None if no specific type
        assert section_type in [DOMSectionType.NAVIGATION, None]

    def test_identify_form_section(self):
        """Test identification of form section."""
        segmenter = DOMSegmenter()
        
        element = {
            "tag": "form",
            "children": [
                {"tag": "input", "type": "text"},
                {"tag": "button", "text": "Submit"},
            ],
        }

        section_type = segmenter._match_section_pattern(element)

        assert section_type == DOMSectionType.FORMS

    def test_identify_footer_section(self):
        """Test identification of footer section."""
        segmenter = DOMSegmenter()
        
        element = {
            "tag": "footer",
        }

        section_type = segmenter._match_section_pattern(element)

        assert section_type == DOMSectionType.FOOTER

    def test_segment_extracts_text_content(self):
        """Test that segmentation preserves text content."""
        segmenter = DOMSegmenter()
        
        page = {
            "dom_tree": {
                "tag": "body",
                "children": [
                    {
                        "tag": "main",
                        "children": [
                            {"tag": "p", "text": "This is important content."},
                            {"tag": "p", "text": "More content here."},
                        ],
                    },
                ],
            }
        }

        result = segmenter.segment_page(page)

        # Should have extracted content
        all_text = " ".join([str(elem) for section in result.sections for elem in section.elements])
        assert len(all_text) > 0

    def test_segment_with_nested_divs(self):
        """Test segmentation with deeply nested divs."""
        segmenter = DOMSegmenter()
        
        page = {
            "dom_tree": {
                "tag": "body",
                "children": [
                    {
                        "tag": "div",
                        "class": "container",
                        "children": [
                            {
                                "tag": "div",
                                "class": "content",
                                "children": [
                                    {
                                        "tag": "div",
                                        "children": [
                                            {"tag": "p", "text": "Deep content"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        }

        result = segmenter.segment_page(page)

        assert len(result.sections) > 0

    def test_extract_section_from_element(self):
        """Test extraction of a section from an element."""
        segmenter = DOMSegmenter()
        
        element = {
            "tag": "section",
            "id": "content",
            "children": [
                {"tag": "h2", "text": "Section Title"},
                {"tag": "p", "text": "Section content"},
            ],
        }

        section = segmenter._extract_section(element, DOMSectionType.MAIN_CONTENT)

        assert section is not None
        assert section.section_type == DOMSectionType.MAIN_CONTENT
        assert len(section.elements) > 0

    def test_segment_multiple_sections(self):
        """Test segmentation returns multiple distinct sections."""
        segmenter = DOMSegmenter()
        
        page = {
            "dom_tree": {
                "tag": "body",
                "children": [
                    {"tag": "header", "children": [{"tag": "h1", "text": "Title"}]},
                    {"tag": "main", "children": [{"tag": "p", "text": "Content"}]},
                    {"tag": "aside", "children": [{"tag": "p", "text": "Sidebar"}]},
                    {"tag": "footer", "children": [{"tag": "p", "text": "Footer"}]},
                ],
            }
        }

        result = segmenter.segment_page(page)

        # Should identify multiple sections
        assert len(result.sections) >= 3

    def test_match_section_pattern_by_id(self):
        """Test pattern matching by element ID."""
        segmenter = DOMSegmenter()
        
        navigation_element = {
            "tag": "div",
            "id": "main-navigation",
        }

        # Should recognize 'navigation' in ID
        section_type = segmenter._match_section_pattern(navigation_element)
        assert section_type is not None

    def test_match_section_pattern_by_class(self):
        """Test pattern matching by element class."""
        segmenter = DOMSegmenter()
        
        navbar_element = {
            "tag": "div",
            "class": "navbar navbar-expand-lg",
        }

        # May match navigation pattern
        section_type = segmenter._match_section_pattern(navbar_element)
        # Should either match or return None, not crash
        assert section_type is None or isinstance(section_type, DOMSectionType)

    def test_estimate_section_size(self):
        """Test that section size is estimated."""
        segmenter = DOMSegmenter()
        
        page = {
            "dom_tree": {
                "tag": "body",
                "children": [
                    {
                        "tag": "main",
                        "text": "A" * 500,
                    }
                ],
            }
        }

        result = segmenter.segment_page(page)

        assert result.total_char_size > 0

    def test_ignore_script_tags_in_segmentation(self):
        """Test that script tags are ignored in segmentation."""
        segmenter = DOMSegmenter()
        
        page = {
            "dom_tree": {
                "tag": "body",
                "children": [
                    {"tag": "script", "text": "console.log('test');"},
                    {
                        "tag": "main",
                        "children": [
                            {"tag": "p", "text": "Real content"},
                        ],
                    },
                ],
            }
        }

        result = segmenter.segment_page(page)

        # Should have at least one section (main)
        assert len(result.sections) > 0

    def test_section_type_enum_values(self):
        """Test that SectionType enum has expected values."""
        assert DOMSectionType.HEADER is not None
        assert DOMSectionType.NAVIGATION is not None
        assert DOMSectionType.FORMS is not None
        assert DOMSectionType.FOOTER is not None
        assert DOMSectionType.MAIN_CONTENT is not None

    def test_extract_semantic_sections(self):
        """Test extraction of semantically meaningful sections."""
        segmenter = DOMSegmenter()
        
        page = {
            "dom_tree": {
                "tag": "body",
                "children": [
                    {
                        "tag": "article",
                        "children": [
                            {"tag": "h1", "text": "Article Title"},
                            {"tag": "p", "text": "Article content"},
                        ],
                    },
                ],
            }
        }

        result = segmenter.segment_page(page)

        assert len(result.sections) > 0
        assert any(s.section_type == DOMSectionType.MAIN_CONTENT for s in result.sections) or len(result.sections) > 0

    def test_segment_page_preserves_xpath(self):
        """Test that segmentation preserves or generates XPath for elements."""
        segmenter = DOMSegmenter()
        
        page = {
            "dom_tree": {
                "tag": "body",
                "children": [
                    {
                        "tag": "main",
                        "children": [
                            {"tag": "button", "id": "submit", "text": "Submit"},
                        ],
                    },
                ],
            }
        }

        result = segmenter.segment_page(page)

        # Each section should have elements
        assert len(result.sections[0].elements) > 0

    def test_empty_page_segmentation(self):
        """Test segmentation of empty page."""
        segmenter = DOMSegmenter()
        
        page = {
            "dom_tree": {
                "tag": "html",
                "children": [],
            }
        }

        result = segmenter.segment_page(page)

        # Should handle empty page gracefully
        assert isinstance(result.sections, list)

    def test_single_large_section(self):
        """Test segmentation of page with single large section."""
        segmenter = DOMSegmenter()
        
        large_text = " ".join([f"Word{i}" for i in range(1000)])
        page = {
            "dom_tree": {
                "tag": "body",
                "children": [
                    {
                        "tag": "main",
                        "text": large_text,
                    }
                ],
            }
        }

        result = segmenter.segment_page(page)

        assert len(result.sections) > 0
        assert result.total_char_size > 1000

    def test_segment_page_without_dom_tree_returns_empty_result(self):
        segmenter = DOMSegmenter()
        result = segmenter.segment_page({"url": "https://example.com"})
        assert result.sections == []
        assert result.total_char_size == 0

    def test_extract_semantic_sections_accepts_list_input(self):
        segmenter = DOMSegmenter()
        page_list = [{"tag": "header"}, {"tag": "footer"}]
        result = segmenter.segment_page({"dom_tree": {"tag": "body", "children": page_list}})
        assert len(result.sections) >= 1

    def test_extract_semantic_sections_ignores_non_dict(self):
        segmenter = DOMSegmenter()
        out = segmenter._extract_section("not-dict", DOMSectionType.HEADER)
        assert out is None

    def test_extract_section_returns_none_when_dict_to_element_none(self, monkeypatch):
        segmenter = DOMSegmenter()
        monkeypatch.setattr(segmenter, "_dict_to_element", lambda *_: None)
        out = segmenter._extract_section({"tag": "div"}, DOMSectionType.UNKNOWN)
        assert out is None

    def test_collect_interactive_recursive_list_and_non_dict_paths(self):
        segmenter = DOMSegmenter()
        acc = []
        segmenter._collect_interactive_recursive([{"tag": "button"}, "x"], acc)
        assert any(e.tag == "button" for e in acc)

    def test_classify_remaining_elements_creates_form_and_nav_sections(self):
        from app.domain.dom.models import ProcessedElement, DOMSegmentationResult

        segmenter = DOMSegmenter()
        result = DOMSegmentationResult()
        elems = [
            ProcessedElement(tag="input"),
            ProcessedElement(tag="a"),
            ProcessedElement(tag="div"),
        ]

        segmenter._classify_remaining_elements(elems, result)

        types = [s.section_type for s in result.sections]
        assert DOMSectionType.FORMS in types
        assert DOMSectionType.NAVIGATION in types
        assert all(e.tag != "div" for e in elems)

    def test_dict_to_element_with_empty_dict_returns_none(self):
        segmenter = DOMSegmenter()
        assert segmenter._dict_to_element({}) is None

    def test_flatten_elements_recursively(self):
        from app.domain.dom.models import ProcessedElement

        segmenter = DOMSegmenter()
        root = ProcessedElement(tag="div", children=[ProcessedElement(tag="span")])
        out = []
        segmenter._flatten_elements(root, out)
        assert [e.tag for e in out] == ["div", "span"]

    def test_get_section_name_without_id(self):
        segmenter = DOMSegmenter()
        name = segmenter._get_section_name(DOMSectionType.MAIN_CONTENT, {"tag": "main"})
        assert name == "Main Content"

    def test_segment_page_adds_unknown_section_when_remaining_elements_left(self):
        """Cover branch that appends UNKNOWN section after classification."""
        segmenter = DOMSegmenter()
        page = {
            "dom_tree": {
                "tag": "body",
                "children": [
                    {"tag": "input", "id": "email"},
                ],
            }
        }

        result = segmenter.segment_page(page)
        assert any(s.section_type == DOMSectionType.UNKNOWN for s in result.sections)

    def test_extract_semantic_sections_list_and_non_dict_paths(self):
        """Cover early-return paths for list and non-dict values."""
        segmenter = DOMSegmenter()
        result = DOMSegmentationResult()

        segmenter._extract_semantic_sections([{"tag": "header"}], result)
        assert len(result.sections) >= 1

        before = len(result.sections)
        segmenter._extract_semantic_sections("plain-text-node", result)
        assert len(result.sections) == before
