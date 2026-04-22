"""Tests for DOM preprocessor."""

import pytest

from app.domain.dom.preprocessor import DOMPreprocessor


class TestDOMPreprocessor:
    """Tests for DOMPreprocessor."""

    def test_skip_script_tags(self):
        """Test that script tags are removed."""
        preprocessor = DOMPreprocessor()
        element = {
            "tag": "script",
            "text": "console.log('test');",
        }

        result = preprocessor._preprocess_element(element)

        assert result is None

    def test_skip_style_tags(self):
        """Test that style tags are removed."""
        preprocessor = DOMPreprocessor()
        element = {
            "tag": "style",
            "text": "body { color: red; }",
        }

        result = preprocessor._preprocess_element(element)

        assert result is None

    def test_preserve_button_element(self):
        """Test that button elements are preserved."""
        preprocessor = DOMPreprocessor()
        element = {
            "tag": "button",
            "attributes": {"type": "submit", "id": "submit-btn"},
            "text": "Submit",
        }

        result = preprocessor._preprocess_element(element)

        assert result is not None
        assert result["tag"] == "button"
        assert result["type"] == "submit"
        assert result["id"] == "submit-btn"
        assert result["text"] == "Submit"

    def test_remove_style_attribute(self):
        """Test that style attributes are removed."""
        preprocessor = DOMPreprocessor()
        element = {
            "tag": "div",
            "attributes": {
                "id": "content",
                "style": "color: red; font-size: 14px; margin: 10px;",
            },
        }

        result = preprocessor._preprocess_element(element)

        assert result is not None
        assert "style" not in result
        assert result["id"] == "content"

    def test_preserve_aria_attributes(self):
        """Test that ARIA attributes are preserved."""
        preprocessor = DOMPreprocessor()
        element = {
            "tag": "div",
            "attributes": {
                "aria-label": "Menu",
                "aria-expanded": "false",
                "id": "menu",
            },
        }

        result = preprocessor._preprocess_element(element)

        assert result["aria-label"] == "Menu"
        assert result["aria-expanded"] == "false"

    def test_truncate_text_content(self):
        """Test that text content is truncated."""
        preprocessor = DOMPreprocessor(max_text_per_element=50)
        element = {
            "tag": "p",
            "text": "A" * 200,  # 200 chars, should be truncated to 50
        }

        result = preprocessor._preprocess_element(element)

        assert len(result["text"]) == 50

    def test_preserve_data_testid(self):
        """Test that data-testid attributes are preserved."""
        preprocessor = DOMPreprocessor()
        element = {
            "tag": "input",
            "attributes": {
                "data-testid": "email-input",
                "type": "email",
            },
        }

        result = preprocessor._preprocess_element(element)

        assert result["data-testid"] == "email-input"

    def test_remove_onclick_in_nested_children(self):
        """Test preprocessing nested elements."""
        preprocessor = DOMPreprocessor()
        element = {
            "tag": "div",
            "children": [
                {
                    "tag": "button",
                    "attributes": {"onclick": "handleClick()"},
                    "text": "Click",
                },
                {
                    "tag": "script",
                    "text": "console.log('x');",
                },
            ],
        }

        result = preprocessor._preprocess_element(element)

        assert "children" in result
        assert len(result["children"]) == 1  # script filtered out
        assert result["children"][0]["tag"] == "button"

    def test_preprocess_page_structure(self):
        """Test preprocessing complete page structure."""
        preprocessor = DOMPreprocessor()
        page = {
            "url": "https://example.com",
            "dom_tree": {
                "tag": "html",
                "children": [
                    {
                        "tag": "header",
                        "attributes": {
                            "style": "background: blue;",
                            "id": "header",
                        },
                        "children": [
                            {
                                "tag": "script",
                                "text": "analytics code",
                            }
                        ],
                    }
                ],
            },
        }

        result = preprocessor.preprocess_page_structure(page)

        assert result["url"] == "https://example.com"
        assert result["dom_tree"]["tag"] == "html"
        assert "style" not in result["dom_tree"]["children"][0]

    def test_estimate_total_chars(self):
        """Test character estimation for page."""
        preprocessor = DOMPreprocessor()
        page = {
            "dom_tree": {
                "tag": "body",
                "attributes": {"id": "main"},
                "text": "Page content",
                "children": [
                    {"tag": "button", "text": "Click me"},
                ],
            }
        }

        size = preprocessor.estimate_total_chars(page)

        assert size > 20  # At least some characters

    def test_should_preserve_attribute_id(self):
        """Test that id attributes are preserved."""
        preprocessor = DOMPreprocessor()

        assert preprocessor._should_preserve_attribute("id", "my-id") is True
        assert preprocessor._should_preserve_attribute("id", "") is False

    def test_should_preserve_attribute_role(self):
        """Test that role attributes are preserved."""
        preprocessor = DOMPreprocessor()

        assert preprocessor._should_preserve_attribute("role", "button") is True
        assert preprocessor._should_preserve_attribute("role", None) is False

    def test_should_not_preserve_style(self):
        """Test that style attributes are not preserved."""
        preprocessor = DOMPreprocessor()

        assert preprocessor._should_preserve_attribute("style", "color: red;") is False

    def test_should_preserve_data_attributes(self):
        """Test that data-* attributes are preserved."""
        preprocessor = DOMPreprocessor()

        assert preprocessor._should_preserve_attribute("data-testid", "input-1") is True
        assert preprocessor._should_preserve_attribute("data-action", "click") is True

    def test_clean_attribute_value_truncates_long_class(self):
        """Test that long class lists are cleaned."""
        preprocessor = DOMPreprocessor()

        long_classes = " ".join([f"class-{i}" for i in range(20)])
        result = preprocessor._clean_attribute_value("class", long_classes)

        assert result is not None
        assert len(result) <= preprocessor.MAX_ATTR_LENGTH.get("class", 500)

    def test_create_processed_element(self):
        """Test conversion to ProcessedElement domain model."""
        preprocessor = DOMPreprocessor()
        element_dict = {
            "tag": "input",
            "id": "email",
            "type": "email",
            "placeholder": "Enter email",
        }

        elem = preprocessor.create_processed_element(element_dict)

        assert elem.tag == "input"
        assert elem.id == "email"
        assert elem.type == "email"
        assert elem.placeholder == "Enter email"

    def test_dom_size_reduction(self):
        """Test that preprocessing reduces DOM size significantly."""
        preprocessor = DOMPreprocessor()

        original = {
            "dom_tree": {
                "tag": "div",
                "attributes": {
                    "style": "color: red; font-size: 14px; margin: 10px; padding: 5px; background: white;",
                    "class": "container wrapper main-container d-flex justify-content-center align-items-center mx-auto my-4 p-3",
                    "id": "content",
                    "onclick": "handleClick()",
                },
                "text": "Some content here",
            }
        }

        import json

        original_size = len(json.dumps(original))

        preprocessed = preprocessor.preprocess_page_structure(original)
        preprocessed_size = len(json.dumps(preprocessed))

        # Should be significantly smaller
        reduction = (original_size - preprocessed_size) / original_size
        assert reduction > 0.3  # At least 30% reduction

    def test_preprocess_element_returns_none_for_invalid_input(self):
        preprocessor = DOMPreprocessor()
        assert preprocessor._preprocess_element(None) is None
        assert preprocessor._preprocess_element("not-a-dict") is None

    def test_preprocess_element_keeps_xpath_and_visible_false(self):
        preprocessor = DOMPreprocessor()
        element = {
            "tag": "button",
            "xpath": "//button[@id='x']",
            "visible": False,
        }

        result = preprocessor._preprocess_element(element)

        assert result["xpath"] == "//button[@id='x']"
        assert result["visible"] is False

    def test_should_preserve_attribute_unknown_returns_false(self):
        preprocessor = DOMPreprocessor()
        assert preprocessor._should_preserve_attribute("custom-attr", "abc") is False

    def test_clean_attribute_value_none_returns_none(self):
        preprocessor = DOMPreprocessor()
        assert preprocessor._clean_attribute_value("class", None) is None

    def test_clean_attribute_value_non_class_too_long_returns_none(self):
        preprocessor = DOMPreprocessor()
        assert preprocessor._clean_attribute_value("title", "A" * 600) is None

    def test_estimate_total_chars_without_dom_tree(self):
        preprocessor = DOMPreprocessor()
        assert preprocessor.estimate_total_chars({"url": "x"}) == 0

    def test_estimate_element_chars_invalid_input(self):
        preprocessor = DOMPreprocessor()
        assert preprocessor._estimate_element_chars(None) == 0

    def test_estimate_element_chars_counts_named_attributes(self):
        preprocessor = DOMPreprocessor()
        element = {
            "tag": "input",
            "id": "email",
            "name": "email",
            "role": "textbox",
            "xpath": "//input",
        }

        size = preprocessor._estimate_element_chars(element)
        assert size > len("input")
