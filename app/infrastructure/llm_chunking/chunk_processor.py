"""Chunk-based test generation from DOM chunks."""

import asyncio
import json
import logging
from typing import Optional

from tenacity import RetryError

from app.domain.dom.models import DOMChunk, ChunkProcessingResult
from app.llm.groq_client import GroqClient, PayloadTooLargeError
from app.core.config import settings

logger = logging.getLogger(__name__)


class ChunkProcessor:
    """Processes individual DOM chunks through LLM for test generation."""

    def __init__(self, groq_client: GroqClient | None = None):
        """Initialize processor.
        
        Args:
            groq_client: Optional GroqClient instance
        """
        self._groq_client = groq_client or GroqClient()

    async def process_chunk(
        self,
        chunk: DOMChunk,
        user_prompt: str,
        context: str | None = None,
        retry_on_large_payload: bool = True,
    ) -> ChunkProcessingResult:
        """Process a single DOM chunk through LLM.
        
        Args:
            chunk: DOMChunk to process
            user_prompt: User's test generation prompt
            context: Optional context/additional instructions
            retry_on_large_payload: If True, retry with compact format on PayloadTooLargeError
            
        Returns:
            ChunkProcessingResult with generated test
            
        Raises:
            PayloadTooLargeError: If chunk still too large even after retries
            RetryError: If LLM call retries exhausted
        """
        logger.info("Processing chunk: %s (%d chars)", chunk.chunk_id, chunk.char_size)
        
        # Create section-specific context
        section_context = self._create_section_context(chunk, user_prompt, context)
        
        # Convert chunk to dict for LLM
        chunk_dict = chunk.to_dict()
        
        try:
            # Generate test for this chunk
            content = await asyncio.to_thread(
                self._groq_client.generate_robot_test,
                prompt=section_context,
                context=None,  # Context already included in section_context
                page_structure={"chunk": chunk_dict},
            )
            
            result = ChunkProcessingResult(
                chunk_id=chunk.chunk_id,
                section_type=chunk.section_type,
                section_name=chunk.section_name,
                generated_test=content,
                metadata={
                    "chunk_size_chars": chunk.char_size,
                    "element_count": len(chunk.elements),
                },
            )
            
            logger.info("Successfully processed chunk: %s", chunk.chunk_id)
            return result
            
        except PayloadTooLargeError as exc:
            if not retry_on_large_payload:
                raise
            
            logger.warning(
                "Chunk %s exceeded token limit, retrying with compact format",
                chunk.chunk_id
            )
            
            # Retry with minimal element data
            compact_chunk = self._compact_chunk(chunk)
            compact_dict = compact_chunk.to_dict()
            
            try:
                content = await asyncio.to_thread(
                    self._groq_client.generate_robot_test,
                    prompt=section_context,
                    context=None,
                    page_structure={"chunk": compact_dict},
                )
                
                result = ChunkProcessingResult(
                    chunk_id=chunk.chunk_id,
                    section_type=chunk.section_type,
                    section_name=chunk.section_name,
                    generated_test=content,
                    metadata={
                        "chunk_size_chars": compact_chunk.char_size,
                        "element_count": len(compact_chunk.elements),
                        "compacted": True,
                    },
                )
                
                logger.info("Successfully processed (compacted) chunk: %s", chunk.chunk_id)
                return result
                
            except PayloadTooLargeError as retry_exc:
                logger.error("Chunk %s still too large after compaction", chunk.chunk_id)
                raise retry_exc from exc

    async def process_chunks_batch(
        self,
        chunks: list[DOMChunk],
        user_prompt: str,
        context: str | None = None,
        max_concurrent: int = 3,
    ) -> list[ChunkProcessingResult]:
        """Process multiple chunks concurrently.
        
        Args:
            chunks: List of DOMChunk objects
            user_prompt: User's test generation prompt
            context: Optional context
            max_concurrent: Max concurrent chunk processing
            
        Returns:
            List of ChunkProcessingResult objects
        """
        logger.info("Processing %d chunks concurrently (max %d)", len(chunks), max_concurrent)
        
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(chunk):
            async with semaphore:
                try:
                    return await self.process_chunk(chunk, user_prompt, context)
                except Exception as e:
                    logger.error("Failed to process chunk %s: %s", chunk.chunk_id, e)
                    # Return a failed result instead of raising
                    return ChunkProcessingResult(
                        chunk_id=chunk.chunk_id,
                        section_type=chunk.section_type,
                        section_name=chunk.section_name,
                        generated_test="",
                        metadata={"error": str(e)},
                    )
        
        results = await asyncio.gather(
            *[process_with_semaphore(chunk) for chunk in chunks],
            return_exceptions=False,
        )
        
        successful = [r for r in results if r.generated_test]
        failed = [r for r in results if not r.generated_test]
        
        logger.info(
            "Batch processing complete: %d successful, %d failed",
            len(successful),
            len(failed),
        )
        
        return results

    def _create_section_context(
        self,
        chunk: DOMChunk,
        user_prompt: str,
        context: str | None = None,
    ) -> str:
        """Create section-specific prompt context.
        
        Args:
            chunk: DOMChunk being processed
            user_prompt: User's test prompt
            context: Optional user context
            
        Returns:
            Section-specific prompt
        """
        section_desc = f"Generate Robot Framework tests for the {chunk.section_type.value.replace('_', ' ')} section"
        
        prompt_parts = [
            section_desc,
            f"Section name: {chunk.section_name}",
            f"Number of elements: {len(chunk.elements)}",
        ]
        
        if context:
            prompt_parts.append(f"Additional context:\n{context}")
        
        prompt_parts.append(f"\nUser request:\n{user_prompt}")
        
        return "\n\n".join(prompt_parts)

    def _compact_chunk(self, chunk: DOMChunk) -> DOMChunk:
        """Create a compacted version of chunk with minimal text.
        
        Args:
            chunk: Original DOMChunk
            
        Returns:
            Compacted DOMChunk
        """
        # Remove text content and long attributes
        compacted_elements = []
        for elem in chunk.elements:
            elem.text = None if elem.text and len(elem.text) > 50 else elem.text
            compacted_elements.append(elem)
        
        return DOMChunk(
            chunk_id=chunk.chunk_id,
            section_type=chunk.section_type,
            section_name=chunk.section_name,
            elements=compacted_elements,
            char_size=sum(e.estimate_char_size() for e in compacted_elements),
            priority=chunk.priority,
        )
