"""Orchestration service for chunked test generation."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.dom.preprocessor import DOMPreprocessor
from app.domain.dom.segmenter import DOMSegmenter
from app.domain.test_generation.aggregator import TestAggregator
from app.infrastructure.llm_chunking.chunker import AdaptiveChunker, ChunkingStrategy
from app.infrastructure.llm_chunking.chunk_processor import ChunkProcessor
from app.infrastructure.dom_cache.segmentation_cache import (
    DOMSegmentationCache,
    DOMHasher,
)
from app.llm.groq_client import GroqClient
from app.models.generated_test import GeneratedTest
from app.models.test_request import TestRequest
from app.repositories.test_repository import TestRepository

logger = logging.getLogger(__name__)


class ChunkedTestGenerationOrchestrator:
    """Orchestrates the entire chunked test generation pipeline."""

    def __init__(
        self,
        groq_client: GroqClient | None = None,
        test_repository: TestRepository | None = None,
    ):
        """Initialize orchestrator.

        Args:
            groq_client: Optional GroqClient instance
            test_repository: Optional TestRepository instance
        """
        self._groq_client = groq_client or GroqClient()
        self._test_repository = test_repository or TestRepository()

        self._preprocessor = DOMPreprocessor(
            max_text_per_element=settings.DOM_MAX_TEXT_PER_ELEMENT
        )
        self._segmenter = DOMSegmenter()
        self._chunk_processor = ChunkProcessor(groq_client=self._groq_client)
        self._test_aggregator = TestAggregator()

        # Shared cache
        self._segmentation_cache = DOMSegmentationCache(
            max_entries=settings.DOM_CACHE_MAX_ENTRIES
        )

        self._last_generation_metadata: dict | None = None

    @property
    def last_generation_metadata(self) -> dict | None:
        """Get metadata from last generation."""
        return self._last_generation_metadata

    async def generate_test_chunked(
        self,
        session: AsyncSession,
        test_request: TestRequest,
        page_structure: dict | None,
        user_prompt: str,
        context: str | None = None,
        page_url: str | None = None,
    ) -> tuple[str, dict]:
        """Generate Robot Framework test using chunked processing.

        Args:
            session: Database session
            test_request: TestRequest database object
            page_structure: Page structure dict from scanner
            user_prompt: User's test generation prompt
            context: Optional context/instructions
            page_url: Optional page URL for caching

        Returns:
            Tuple of (generated_test_content, metadata)
        """
        logger.info("Starting chunked test generation for request %d", test_request.id)

        # Step 1: Preprocess
        logger.info("Step 1: Preprocessing DOM...")
        preprocessed = self._preprocess_dom(page_structure)
        dom_hash = DOMHasher.hash_page_structure(preprocessed)

        # Step 2: Segmentation (with cache)
        logger.info("Step 2: Segmenting DOM into sections...")
        segmentation_result = self._segment_dom(preprocessed, dom_hash, page_url)

        sections = segmentation_result.sections
        logger.info("Segmented into %d sections", len(sections))

        # Step 3: Chunking
        logger.info("Step 3: Creating chunks...")
        chunking_strategy = ChunkingStrategy(
            target_chunk_chars=settings.LLM_DOM_CHUNK_TARGET_CHARS,
            reserve_chars=settings.LLM_CHUNK_RESERVE_CHARS,
            max_chunk_count=settings.LLM_MAX_CHUNKS_PER_REQUEST,
        )

        chunker = AdaptiveChunker(
            total_token_budget=settings.GROQ_CHUNK_TOKEN_BUDGET,
            strategy=chunking_strategy,
        )

        chunks = chunker.chunk_all_sections_adaptive(sections)
        logger.info("Created %d chunks for processing", len(chunks))

        # Step 4: Process chunks through LLM
        logger.info("Step 4: Processing chunks through LLM...")
        chunk_results = await self._process_chunks(chunks, user_prompt, context)

        # Step 5: Aggregate results
        logger.info("Step 5: Aggregating results...")
        final_test, agg_metadata = self._test_aggregator.aggregate_results(
            chunk_results
        )

        # Build comprehensive metadata
        self._last_generation_metadata = {
            "strategy": "chunked",
            "chunk_count": len(chunks),
            "successful_chunks": len([r for r in chunk_results if r.generated_test]),
            "sections_count": len(sections),
            "total_dom_chars": segmentation_result.total_char_size,
            "chunks_metadata": [
                {
                    "chunk_id": c.chunk_id,
                    "section_type": c.section_type.value,
                    "size_chars": c.char_size,
                    "element_count": len(c.elements),
                }
                for c in chunks
            ],
            "aggregation": agg_metadata,
        }

        logger.info(
            "Chunked generation complete: %d chunks, %d successful",
            len(chunks),
            len([r for r in chunk_results if r.generated_test]),
        )

        return final_test, self._last_generation_metadata

    def _preprocess_dom(self, page_structure: dict | None) -> dict:
        """Preprocess page structure."""
        if not page_structure:
            return {}

        logger.debug(
            "Preprocessing DOM (before: %d bytes)", len(json.dumps(page_structure))
        )

        preprocessed = self._preprocessor.preprocess_page_structure(page_structure)

        logger.debug(
            "Preprocessing complete (after: %d bytes)", len(json.dumps(preprocessed))
        )

        return preprocessed

    def _segment_dom(
        self,
        page_structure: dict,
        dom_hash: str,
        page_url: str | None = None,
    ):
        """Segment DOM with caching."""
        # Check cache
        cached = self._segmentation_cache.get(page_url, dom_hash)
        if cached:
            logger.info("Using cached segmentation")
            return cached

        # Perform segmentation
        result = self._segmenter.segment_page(page_structure)

        # Cache result
        self._segmentation_cache.set(
            page_url=page_url,
            dom_hash=dom_hash,
            result=result,
            metadata={"generated_at": datetime.utcnow().isoformat()},
        )

        return result

    async def _process_chunks(
        self,
        chunks: list,
        user_prompt: str,
        context: str | None = None,
    ) -> list:
        """Process chunks through LLM."""
        max_concurrent = settings.LLM_MAX_CONCURRENT_CHUNKS

        results = await self._chunk_processor.process_chunks_batch(
            chunks=chunks,
            user_prompt=user_prompt,
            context=context,
            max_concurrent=max_concurrent,
        )

        return results

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "segmentation_cache": self._segmentation_cache.stats(),
        }

    def clear_caches(self) -> None:
        """Clear all caches."""
        self._segmentation_cache.clear()
        logger.info("All caches cleared")
