"""DOM segmentation to split page into logical sections for independent processing."""

import logging
import re
from typing import Any

from app.domain.dom.models import (
    DOMSection, DOMSectionType, DOMSegmentationResult, ProcessedElement
)

logger = logging.getLogger(__name__)


class DOMSegmenter:
    """Segments DOM into logical sections (header, nav, main, forms, etc.)."""

    # Section detection patterns (tag + attributes)
    SECTION_PATTERNS: dict[DOMSectionType, list[dict[str, Any]]] = {
        DOMSectionType.HEADER: [
            {"tag": "header"},
            {"tag": "div", "id_pattern": r"(header|top|banner)"},
            {"tag": "div", "class_pattern": r"(header|navbar-top|top-bar)"},
        ],
        DOMSectionType.NAVIGATION: [
            {"tag": "nav"},
            {"tag": "ul", "id_pattern": r"(nav|menu)"},
            {"tag": "div", "id_pattern": r"(nav|menu|sidebar)"},
            {"tag": "div", "class_pattern": r"(navbar|nav|menu|sidebar)"},
        ],
        DOMSectionType.MAIN_CONTENT: [
            {"tag": "main"},
            {"tag": "article"},
            {"tag": "div", "id_pattern": r"(content|main|article)"},
            {"tag": "div", "class_pattern": r"(content|main|article|page)"},
        ],
        DOMSectionType.FORMS: [
            {"tag": "form"},
        ],
        DOMSectionType.SIDEBAR: [
            {"tag": "aside"},
            {"tag": "div", "id_pattern": r"(sidebar|aside|right-panel)"},
            {"tag": "div", "class_pattern": r"(sidebar|aside|right-panel|side-nav)"},
        ],
        DOMSectionType.FOOTER: [
            {"tag": "footer"},
            {"tag": "div", "id_pattern": r"(footer|bottom)"},
            {"tag": "div", "class_pattern": r"(footer|bottom-bar)"},
        ],
        DOMSectionType.MODAL: [
            {"tag": "dialog"},
            {"tag": "div", "role": "dialog"},
            {"tag": "div", "id_pattern": r"(modal|dialog|popup)"},
            {"tag": "div", "class_pattern": r"(modal|dialog|popup)"},
        ],
    }

    def __init__(self):
        """Initialize segmenter."""
        self._processed_elements: dict[str, DOMSection] = {}

    def segment_page(self, page_structure: dict) -> DOMSegmentationResult:
        """Segment page into logical sections.
        
        Args:
            page_structure: Page structure dict
            
        Returns:
            DOMSegmentationResult with identified sections
        """
        self._processed_elements = {}
        result = DOMSegmentationResult()
        
        if "dom_tree" not in page_structure:
            logger.warning("No dom_tree in page_structure")
            return result
        
        # First pass: identify known sections by semantic tags/ids/classes
        dom_tree = page_structure["dom_tree"]
        self._extract_semantic_sections(dom_tree, result)
        
        # Second pass: collect remaining interactive elements into appropriate sections
        remaining = self._collect_interactive_elements(dom_tree)
        self._classify_remaining_elements(remaining, result)
        
        # Add unclassified elements to unknown section if any
        if remaining:
            unknown_section = DOMSection(
                section_type=DOMSectionType.UNKNOWN,
                name="Other Elements",
                elements=remaining,
            )
            result.sections.append(unknown_section)
        
        # Calculate total size
        result.total_char_size = sum(s.estimate_char_size() for s in result.sections)
        
        logger.info(
            "Segmented page into %d sections (total size: %d chars)",
            len(result.sections),
            result.total_char_size,
        )
        
        return result

    def _extract_semantic_sections(
        self, elem: dict | list, result: DOMSegmentationResult
    ) -> None:
        """Recursively extract semantic sections from DOM tree."""
        if isinstance(elem, list):
            for child in elem:
                self._extract_semantic_sections(child, result)
            return
        
        if not isinstance(elem, dict):
            return
        
        # Check if this element matches a known section pattern
        section_type = self._match_section_pattern(elem)
        if section_type:
            section = self._extract_section(elem, section_type)
            if section:
                result.sections.append(section)
                return  # Don't process children further
        
        # Recurse into children
        for child in elem.get("children", []):
            self._extract_semantic_sections(child, result)

    def _match_section_pattern(self, elem: dict) -> DOMSectionType | None:
        """Check if element matches a known section type pattern."""
        tag = elem.get("tag", "").lower()
        elem_id = elem.get("id", "").lower()
        elem_class = elem.get("class", "").lower()
        elem_role = elem.get("role", "").lower()
        
        for section_type, patterns in self.SECTION_PATTERNS.items():
            for pattern in patterns:
                if not self._match_pattern(pattern, tag, elem_id, elem_class, elem_role):
                    continue
                return section_type
        
        return None

    def _match_pattern(
        self, pattern: dict, tag: str, elem_id: str, elem_class: str, elem_role: str
    ) -> bool:
        """Check if element matches pattern."""
        if pattern.get("tag") and pattern["tag"] != tag:
            return False
        
        if pattern.get("id_pattern"):
            if not elem_id or not re.search(pattern["id_pattern"], elem_id):
                return False
        
        if pattern.get("class_pattern"):
            if not elem_class or not re.search(pattern["class_pattern"], elem_class):
                return False
        
        if pattern.get("role"):
            if pattern["role"] != elem_role:
                return False
        
        return True

    def _extract_section(self, elem: dict, section_type: DOMSectionType) -> DOMSection | None:
        """Extract a complete section (elem + children) as DOM elements."""
        if not isinstance(elem, dict):
            return None
        
        processed_elem = self._dict_to_element(elem)
        if not processed_elem:
            return None
        
        # Flatten element tree to list for easier processing
        elements = []
        self._flatten_elements(processed_elem, elements)
        
        name = self._get_section_name(section_type, elem)
        return DOMSection(
            section_type=section_type,
            name=name,
            elements=elements,
            raw_html=elem.get("tag", ""),
        )

    def _collect_interactive_elements(self, elem: dict | list) -> list[ProcessedElement]:
        """Collect all interactive elements from the tree."""
        elements = []
        self._collect_interactive_recursive(elem, elements)
        return elements

    def _collect_interactive_recursive(
        self, elem: dict | list, result: list[ProcessedElement]
    ) -> None:
        """Recursively collect interactive elements."""
        if isinstance(elem, list):
            for child in elem:
                self._collect_interactive_recursive(child, result)
            return
        
        if not isinstance(elem, dict):
            return
        
        tag = elem.get("tag", "").lower()
        interactive_tags = {
            "button", "a", "input", "select", "textarea", "form",
            "label", "option", "fieldset"
        }
        
        # Add interactive elements directly
        if tag in interactive_tags:
            processed = self._dict_to_element(elem)
            if processed:
                result.append(processed)
        
        # Recurse into children
        for child in elem.get("children", []):
            self._collect_interactive_recursive(child, result)

    def _classify_remaining_elements(
        self, elements: list[ProcessedElement], result: DOMSegmentationResult
    ) -> None:
        """Classify unassigned elements into logical sections based on content."""
        form_elements = []
        nav_elements = []
        other_elements = []
        
        for elem in elements:
            if elem.tag in {"input", "textarea", "select", "label", "fieldset"}:
                form_elements.append(elem)
            elif elem.tag == "a":
                nav_elements.append(elem)
            else:
                other_elements.append(elem)
        
        if form_elements:
            result.sections.append(DOMSection(
                section_type=DOMSectionType.FORMS,
                name="Form Elements",
                elements=form_elements,
            ))
        
        if nav_elements:
            result.sections.append(DOMSection(
                section_type=DOMSectionType.NAVIGATION,
                name="Navigation Links",
                elements=nav_elements,
            ))
        
        # Store other elements for later
        for elem in other_elements:
            elements.remove(elem)

    def _dict_to_element(self, elem_dict: dict) -> ProcessedElement | None:
        """Convert dict element to ProcessedElement."""
        if not elem_dict:
            return None
        
        return ProcessedElement(
            tag=elem_dict.get("tag", ""),
            text=elem_dict.get("text"),
            id=elem_dict.get("id"),
            name=elem_dict.get("name"),
            role=elem_dict.get("role"),
            aria_label=elem_dict.get("aria-label"),
            aria_labelledby=elem_dict.get("aria-labelledby"),
            href=elem_dict.get("href"),
            type=elem_dict.get("type"),
            placeholder=elem_dict.get("placeholder"),
            onclick=elem_dict.get("onclick"),
            xpath=elem_dict.get("xpath"),
            visible=elem_dict.get("visible", True),
            children=[self._dict_to_element(child) 
                     for child in elem_dict.get("children", []) if child],
        )

    def _flatten_elements(
        self, elem: ProcessedElement, result: list[ProcessedElement]
    ) -> None:
        """Flatten nested element tree to list."""
        result.append(elem)
        for child in elem.children:
            self._flatten_elements(child, result)

    def _get_section_name(self, section_type: DOMSectionType, elem: dict) -> str:
        """Get human-readable name for section."""
        elem_id = elem.get("id", "")
        if elem_id:
            return f"{section_type.value.title()} ({elem_id})"
        return section_type.value.replace("_", " ").title()
