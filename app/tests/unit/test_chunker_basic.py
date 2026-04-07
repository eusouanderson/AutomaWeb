"""Tests for DOM chunker."""

import pytest
from app.domain.dom.models import DOMSection, DOMSectionType, ProcessedElement
from app.infrastructure.llm_chunking.chunker import DOMChunker, AdaptiveChunker, ChunkingStrategy


class TestDOMChunkerBasic:
    """Basic tests for DOMChunker."""

    def test_chunk_section_returns_list(self):
        """Test that chunk_section returns list of chunks."""
        chunker = DOMChunker(target_chunk_chars=500)
        
        elements = [
            ProcessedElement(tag="input", id="email", text="email field"),
            ProcessedElement(tag="button", text="Submit"),
        ]
        section = DOMSection(
            section_type=DOMSectionType.FORMS,
            name="forms",
            elements=elements,
        )

        chunks = chunker.chunk_section(section)

        assert isinstance(chunks, list)
        assert len(chunks) > 0

    def test_chunk_preserves_section_type(self):
        """Test that chunks preserve section type."""
        chunker = DOMChunker()
        
        elements = [ProcessedElement(tag="button", text="Click")]
        section = DOMSection(
            section_type=DOMSectionType.HEADER,
                name="header",
            elements=elements,
        )

        chunks = chunker.chunk_section(section)

        assert all(c.section_type == DOMSectionType.HEADER for c in chunks)

    def test_estimate_tokens(self):
        """Test token estimation."""
        chunker = DOMChunker()

        tokens = chunker.estimate_tokens(100)

        assert tokens > 0
        assert tokens < 100  # 100 chars should be ~25 tokens

    def test_chunk_within_token_limit(self):
        """Test token limit checking."""
        chunker = DOMChunker(reserve_chars=100)

        # 100 chars / 4 chars per token = 25 tokens
        within = chunker.is_within_token_limit(100, 100)

        # 100 chars needs 25 tokens, so 50 is enough
        # With token_limit=100 and total needed=50, should fit
        assert within is True

    def test_adaptive_chunker_initialization(self):
        """Test AdaptiveChunker initialization."""
        chunker = AdaptiveChunker(total_token_budget=1000)

        assert chunker.total_token_budget == 1000

    def test_adaptive_chunker_with_strategy(self):
        """Test AdaptiveChunker with custom strategy."""
        strategy = ChunkingStrategy(target_chunk_chars=1500, max_chunk_count=5)
        chunker = AdaptiveChunker(total_token_budget=2000, strategy=strategy)

        assert chunker.strategy.max_chunk_count == 5

    def test_chunk_all_sections(self):
        """Test chunking multiple sections."""
        chunker = DOMChunker()
        
        sections = [
            DOMSection(
                section_type=DOMSectionType.HEADER,
                    name="header",
                elements=[ProcessedElement(tag="h1", text="Title")],
            ),
            DOMSection(
                section_type=DOMSectionType.FORMS,
                    name="forms",
                elements=[ProcessedElement(tag="input", text="field")],
            ),
        ]

        chunks = chunker.chunk_all_sections(sections)

        assert len(chunks) >= 2

    def test_chunk_section_splits_when_target_exceeded(self):
        chunker = DOMChunker(target_chunk_chars=30)
        elements = [
            ProcessedElement(tag="button", text="A" * 30),
            ProcessedElement(tag="button", text="B" * 30),
        ]
        section = DOMSection(section_type=DOMSectionType.FORMS, name="forms", elements=elements)

        chunks = chunker.chunk_section(section)
        assert len(chunks) >= 2

    def test_adaptive_chunker_trims_to_max_chunk_count(self):
        strategy = ChunkingStrategy(target_chunk_chars=20, reserve_chars=0, max_chunk_count=1)
        chunker = AdaptiveChunker(total_token_budget=1000, strategy=strategy)

        # Many elements to produce more than one chunk before trimming
        section = DOMSection(
            section_type=DOMSectionType.MAIN_CONTENT,
            name="content",
            elements=[ProcessedElement(tag="p", text="X" * 3000), ProcessedElement(tag="p", text="Y" * 3000)],
        )

        chunks = chunker.chunk_all_sections_adaptive([section])
        assert len(chunks) == 1
