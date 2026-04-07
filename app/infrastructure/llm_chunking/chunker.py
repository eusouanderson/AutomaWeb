"""DOM chunking strategies for token-safe LLM processing."""

import json
import logging
from dataclasses import dataclass
from typing import Iterator

from app.domain.dom.models import (
    DOMSection, DOMChunk, ProcessedElement, DOMSectionType
)

logger = logging.getLogger(__name__)


class DOMChunker:
    """Splits DOM sections into LLM-safe chunks based on token estimates."""

    # Approximate token ratio: 4 characters ≈ 1 token (conservative estimate)
    CHARS_PER_TOKEN = 4

    def __init__(self, target_chunk_chars: int = 2000, reserve_chars: int = 500):
        """Initialize chunker.
        
        Args:
            target_chunk_chars: Target character size per chunk (before token conversion)
            reserve_chars: Reserve characters for prompts/formatting (not included in chunk)
        """
        self.target_chunk_chars = target_chunk_chars
        self.reserve_chars = reserve_chars

    def chunk_section(self, section: DOMSection) -> list[DOMChunk]:
        """Split a DOM section into LLM-safe chunks.
        
        Args:
            section: DOMSection to chunk
            
        Returns:
            List of DOMChunk objects
        """
        chunks = []
        current_elements = []
        current_size = 0
        chunk_index = 0

        for elem in section.elements:
            elem_size = elem.estimate_char_size()
            
            # If adding this element exceeds target, finalize current chunk
            if current_elements and (current_size + elem_size) > self.target_chunk_chars:
                chunk = self._create_chunk(
                    section, current_elements, chunk_index, current_size
                )
                chunks.append(chunk)
                current_elements = []
                current_size = 0
                chunk_index += 1
            
            current_elements.append(elem)
            current_size += elem_size
        
        # Finalize last chunk
        if current_elements:
            chunk = self._create_chunk(
                section, current_elements, chunk_index, current_size
            )
            chunks.append(chunk)
        
        logger.info(
            "Chunked section '%s' (%s) into %d chunks",
            section.name,
            section.section_type.value,
            len(chunks),
        )
        
        return chunks

    def _create_chunk(
        self,
        section: DOMSection,
        elements: list[ProcessedElement],
        chunk_index: int,
        char_size: int,
    ) -> DOMChunk:
        """Create a DOMChunk from elements."""
        chunk_id = f"{section.section_type.value}_{chunk_index}"
        
        # Assign priority: earlier chunks higher priority
        priority = len(elements) * 10 - chunk_index
        
        return DOMChunk(
            chunk_id=chunk_id,
            section_type=section.section_type,
            section_name=section.name,
            elements=elements,
            char_size=char_size,
            priority=priority,
        )

    def chunk_all_sections(self, sections: list[DOMSection]) -> list[DOMChunk]:
        """Chunk all sections.
        
        Args:
            sections: List of DOMSection objects
            
        Returns:
            Flat list of all DOMChunk objects sorted by priority
        """
        all_chunks = []
        for section in sections:
            chunks = self.chunk_section(section)
            all_chunks.extend(chunks)
        
        # Sort by priority (descending)
        all_chunks.sort(key=lambda c: c.priority, reverse=True)
        
        logger.info("Created %d total chunks from %d sections", 
                   len(all_chunks), len(sections))
        
        return all_chunks

    def estimate_tokens(self, char_size: int) -> int:
        """Estimate token count from character size.
        
        Args:
            char_size: Approximate character count
            
        Returns:
            Estimated token count
        """
        return max(1, char_size // self.CHARS_PER_TOKEN)

    def is_within_token_limit(
        self, char_size: int, token_limit: int
    ) -> bool:
        """Check if size fits within token limit.
        
        Args:
            char_size: Character size
            token_limit: Token limit
            
        Returns:
            True if within limit
        """
        estimated_tokens = self.estimate_tokens(char_size)
        # Reserve space for prompt/context
        available_tokens = token_limit - (self.reserve_chars // self.CHARS_PER_TOKEN)
        return estimated_tokens <= available_tokens


@dataclass
class ChunkingStrategy:
    """Strategy configuration for DOM chunking."""
    target_chunk_chars: int = 2000
    reserve_chars: int = 500  # Reserved for prompt and formatting
    max_chunk_count: int = 10  # Max chunks to process


class AdaptiveChunker(DOMChunker):
    """Adapts chunk size based on available token budget."""

    def __init__(self, total_token_budget: int, strategy: ChunkingStrategy | None = None):
        """Initialize adaptive chunker.
        
        Args:
            total_token_budget: Total tokens available for all chunks
            strategy: ChunkingStrategy configuration
        """
        self.strategy = strategy or ChunkingStrategy()
        self.total_token_budget = total_token_budget
        
        # Calculate chunk size based on budget
        per_chunk_tokens = total_token_budget // max(1, self.strategy.max_chunk_count)
        per_chunk_chars = per_chunk_tokens * self.CHARS_PER_TOKEN
        
        # Reduce by reserve
        per_chunk_chars = max(500, per_chunk_chars - self.strategy.reserve_chars)
        
        super().__init__(
            target_chunk_chars=per_chunk_chars,
            reserve_chars=self.strategy.reserve_chars
        )
        
        logger.info(
            "Adaptive chunker: budget=%d tokens, per_chunk=%d chars",
            total_token_budget,
            per_chunk_chars,
        )

    def chunk_all_sections_adaptive(
        self, sections: list[DOMSection]
    ) -> list[DOMChunk]:
        """Chunk sections adaptively within budget.
        
        Args:
            sections: List of DOMSection objects
            
        Returns:
            List of chunks sorted by priority
        """
        all_chunks = self.chunk_all_sections(sections)
        
        # Trim to max_chunk_count if needed
        if len(all_chunks) > self.strategy.max_chunk_count:
            logger.warning(
                "Produced %d chunks, limiting to %d",
                len(all_chunks),
                self.strategy.max_chunk_count,
            )
            all_chunks = all_chunks[:self.strategy.max_chunk_count]
        
        return all_chunks
