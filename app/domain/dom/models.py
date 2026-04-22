"""Domain models for DOM processing and segmentation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DOMSectionType(str, Enum):
    """Logical sections of a page DOM."""

    HEADER = "header"
    NAVIGATION = "navigation"
    MAIN_CONTENT = "main_content"
    FORMS = "forms"
    SIDEBAR = "sidebar"
    FOOTER = "footer"
    MODAL = "modal"
    UNKNOWN = "unknown"


@dataclass
class ProcessedElement:
    """A preprocessed DOM element with minimal essential attributes."""

    tag: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    role: str | None = None
    aria_label: str | None = None
    aria_labelledby: str | None = None
    href: str | None = None
    type: str | None = None
    placeholder: str | None = None
    onclick: str | None = None
    xpath: str | None = None
    visible: bool = True
    children: list["ProcessedElement"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding None values and empty lists."""
        data = {}
        if self.tag:
            data["tag"] = self.tag
        if self.text:
            data["text"] = self.text
        if self.id:
            data["id"] = self.id
        if self.name:
            data["name"] = self.name
        if self.role:
            data["role"] = self.role
        if self.aria_label:
            data["aria_label"] = self.aria_label
        if self.aria_labelledby:
            data["aria_labelledby"] = self.aria_labelledby
        if self.href:
            data["href"] = self.href
        if self.type:
            data["type"] = self.type
        if self.placeholder:
            data["placeholder"] = self.placeholder
        if self.onclick:
            data["onclick"] = self.onclick
        if self.xpath:
            data["xpath"] = self.xpath
        if not self.visible:
            data["visible"] = False
        if self.children:
            data["children"] = [child.to_dict() for child in self.children]
        return data

    def estimate_char_size(self) -> int:
        """Estimate character size for token calculation."""
        size = len(self.tag) + 10  # tag and minimal structure
        if self.text:
            size += len(self.text)
        if self.id:
            size += len(self.id) + 5
        if self.xpath:
            size += len(self.xpath) + 5
        for child in self.children:
            size += child.estimate_char_size()
        return size


@dataclass
class DOMSection:
    """A logical section of the DOM with related elements."""

    section_type: DOMSectionType
    name: str  # Human-readable name
    elements: list[ProcessedElement] = field(default_factory=list)
    raw_html: str = ""  # Original HTML snippet

    def estimate_char_size(self) -> int:
        """Estimate total character size."""
        size = len(self.raw_html)
        for elem in self.elements:
            size += elem.estimate_char_size()
        return size

    def to_dict(self) -> dict[str, Any]:
        """Convert section to dictionary."""
        return {
            "type": self.section_type.value,
            "name": self.name,
            "elements": [elem.to_dict() for elem in self.elements],
            "estimated_size": self.estimate_char_size(),
        }


@dataclass
class DOMSegmentationResult:
    """Result of DOM segmentation into sections."""

    sections: list[DOMSection] = field(default_factory=list)
    total_char_size: int = 0
    segmentation_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sections": [section.to_dict() for section in self.sections],
            "total_char_size": self.total_char_size,
            "section_count": len(self.sections),
            "metadata": self.segmentation_metadata,
        }


@dataclass
class DOMChunk:
    """A chunk of DOM small enough for LLM processing."""

    chunk_id: str
    section_type: DOMSectionType
    section_name: str
    elements: list[ProcessedElement]
    char_size: int
    priority: int = 0  # Higher priority first

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "section_type": self.section_type.value,
            "section_name": self.section_name,
            "elements": [elem.to_dict() for elem in self.elements],
            "char_size": self.char_size,
            "priority": self.priority,
        }


@dataclass
class ChunkProcessingResult:
    """Result from processing a single DOM chunk through LLM."""

    chunk_id: str
    section_type: DOMSectionType
    section_name: str
    generated_test: str  # Robot Framework code
    token_usage: dict[str, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
