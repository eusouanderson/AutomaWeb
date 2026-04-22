"""DOM preprocessing to reduce token usage while preserving test relevance."""

import logging
import re
from html.parser import HTMLParser
from typing import Any

from app.domain.dom.models import ProcessedElement, DOMSectionType
from app.schemas.scan import ScanResult

logger = logging.getLogger(__name__)


class DOMPreprocessor:
    """Preprocesses raw DOM to extract only test-relevant attributes and elements."""

    # Tags that are interactive or contain test-relevant information
    INTERACTIVE_TAGS = {
        "button",
        "a",
        "input",
        "select",
        "textarea",
        "form",
        "label",
        "option",
        "fieldset",
        "legend",
        "optgroup",
    }

    # Container tags that group content
    CONTAINER_TAGS = {
        "div",
        "section",
        "article",
        "aside",
        "main",
        "nav",
        "header",
        "footer",
        "body",
        "html",
        "span",
    }

    # Tags to completely skip
    SKIP_TAGS = {
        "script",
        "style",
        "meta",
        "link",
        "noscript",
        "iframe",
        "svg",
        "path",
        "defs",
        "symbol",
        "use",
        "image",
    }

    # Attributes to preserve (all others will be dropped)
    PRESERVE_ATTRIBUTES = {
        "id",
        "name",
        "role",
        "aria-label",
        "aria-labelledby",
        "aria-describedby",
        "aria-expanded",
        "aria-hidden",
        "href",
        "type",
        "placeholder",
        "onclick",
        "class",
        "data-testid",
        "value",
        "checked",
        "selected",
        "disabled",
        "required",
        "readonly",
        "autocomplete",
        "maxlength",
        "pattern",
        "min",
        "max",
        "step",
        "for",
        "tabindex",
    }

    # Minimum element text length to preserve
    MIN_TEXT_LENGTH = 1

    # Maximum text content per element
    MAX_TEXT_PER_ELEMENT = 200

    # Attributes that should be ignored if they're very long (like inline styles)
    MAX_ATTR_LENGTH = {"class": 100}

    def __init__(self, max_text_per_element: int = 200):
        """Initialize preprocessor.

        Args:
            max_text_per_element: Maximum characters for text content per element
        """
        self.max_text_per_element = max_text_per_element

    def preprocess_page_structure(self, page_structure: dict) -> dict:
        """Preprocess page structure returned from element scanner.

        Args:
            page_structure: Raw page structure dict

        Returns:
            Preprocessed page structure with reduced attributes
        """
        if "dom_tree" in page_structure:
            processed_tree = self._preprocess_element(page_structure["dom_tree"])
            page_structure = {**page_structure, "dom_tree": processed_tree}

        return page_structure

    def _preprocess_element(self, element: dict) -> dict | None:
        """Recursively preprocess an element dict.

        Args:
            element: Element dict

        Returns:
            Preprocessed element dict or None if should be skipped
        """
        if not element or not isinstance(element, dict):
            return None

        tag = element.get("tag", "").lower()

        # Skip irrelevant tags entirely
        if tag in self.SKIP_TAGS:
            return None

        # Create processed element with only relevant attributes
        processed = {
            "tag": tag,
        }

        # Extract relevant attributes
        attrs = element.get("attributes", {})
        if isinstance(attrs, dict):
            for attr_name, attr_value in attrs.items():
                if self._should_preserve_attribute(attr_name, attr_value):
                    processed_value = self._clean_attribute_value(attr_name, attr_value)
                    if processed_value:
                        # Use dash notation for aria attributes
                        attr_key = attr_name.replace("_", "-")
                        processed[attr_key] = processed_value

        # Keep text content if present and meaningful
        text = element.get("text", "").strip()
        if text and len(text) >= self.MIN_TEXT_LENGTH:
            text = text[: self.max_text_per_element]
            processed["text"] = text

        # Keep XPath for element location
        xpath = element.get("xpath")
        if xpath:
            processed["xpath"] = xpath

        # Track visibility if explicitly hidden
        if element.get("visible") is False:
            processed["visible"] = False

        # Process children, skipping None results
        children = element.get("children", [])
        if isinstance(children, list):
            processed_children = []
            for child in children:
                processed_child = self._preprocess_element(child)
                if processed_child:
                    processed_children.append(processed_child)
            if processed_children:
                processed["children"] = processed_children

        return processed

    def _should_preserve_attribute(self, attr_name: str, attr_value: Any) -> bool:
        """Check if an attribute should be preserved.

        Args:
            attr_name: Attribute name
            attr_value: Attribute value

        Returns:
            True if attribute should be preserved
        """
        if not attr_value:
            return False

        # Always preserve explicitly listed attributes
        if attr_name in self.PRESERVE_ATTRIBUTES:
            return True

        # Preserve data-* attributes (useful for test selectors)
        if attr_name.startswith("data-"):
            return True

        # Skip style attributes entirely (too verbose)
        if attr_name == "style":
            return False

        return False

    def _clean_attribute_value(self, attr_name: str, attr_value: Any) -> str | None:
        """Clean and truncate attribute value if too long.

        Args:
            attr_name: Attribute name
            attr_value: Attribute value

        Returns:
            Cleaned value or None if too long
        """
        if not attr_value:
            return None

        value_str = str(attr_value).strip()

        # Check max length for specific attributes
        max_length = self.MAX_ATTR_LENGTH.get(attr_name, 500)
        if len(value_str) > max_length:
            # For class attributes, keep only important ones
            if attr_name == "class":
                classes = value_str.split()
                # Keep key classes (not Bootstrap positioning, spacing, etc.)
                key_classes = [
                    c
                    for c in classes
                    if not re.match(
                        r"^(m-|p-|ml-|mr-|mt-|mb-|pl-|pr-|pt-|pb-|w-|h-|gap-|d-)", c
                    )
                ]
                if key_classes:
                    return " ".join(key_classes[:5])
            return None

        return value_str

    def create_processed_element(self, element_dict: dict) -> ProcessedElement:
        """Convert preprocessed dict to ProcessedElement domain model.

        Args:
            element_dict: Preprocessed element dictionary

        Returns:
            ProcessedElement domain object
        """
        return ProcessedElement(
            tag=element_dict.get("tag", ""),
            text=element_dict.get("text"),
            id=element_dict.get("id"),
            name=element_dict.get("name"),
            role=element_dict.get("role"),
            aria_label=element_dict.get("aria-label"),
            aria_labelledby=element_dict.get("aria-labelledby"),
            href=element_dict.get("href"),
            type=element_dict.get("type"),
            placeholder=element_dict.get("placeholder"),
            onclick=element_dict.get("onclick"),
            xpath=element_dict.get("xpath"),
            visible=element_dict.get("visible", True),
            children=[
                self.create_processed_element(child)
                for child in element_dict.get("children", [])
            ],
        )

    def estimate_total_chars(self, page_structure: dict) -> int:
        """Estimate total character size for token calculation.

        Args:
            page_structure: Page structure dict

        Returns:
            Estimated character count
        """
        if "dom_tree" not in page_structure:
            return 0

        return self._estimate_element_chars(page_structure["dom_tree"])

    def _estimate_element_chars(self, element: dict) -> int:
        """Recursively estimate character size of element tree.

        Args:
            element: Element dict

        Returns:
            Estimated character count
        """
        if not element or not isinstance(element, dict):
            return 0

        size = len(element.get("tag", "")) + 4

        # Count text
        text = element.get("text", "")
        if text:
            size += len(str(text))

        # Count important attributes
        for attr in ["id", "name", "role", "xpath"]:
            val = element.get(attr)
            if val:
                size += len(str(val)) + 5

        # Count children
        for child in element.get("children", []):
            size += self._estimate_element_chars(child)

        return size
