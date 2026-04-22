"""Tests for chunked test generation orchestrator."""

import pytest
from unittest.mock import Mock, AsyncMock

from app.domain.dom.models import (
    DOMSection,
    DOMSectionType,
    DOMSegmentationResult,
    DOMChunk,
    ProcessedElement,
    ChunkProcessingResult,
)
from app.infrastructure.llm_chunking.orchestrator import (
    ChunkedTestGenerationOrchestrator,
)


class TestChunkedTestGenerationOrchestratorBasic:
    """Coverage-focused tests for orchestrator."""

    def _build_orchestrator(self):
        orch = ChunkedTestGenerationOrchestrator(
            groq_client=Mock(), test_repository=Mock()
        )
        return orch

    @pytest.mark.asyncio
    async def test_generate_test_chunked_happy_path(self, monkeypatch):
        """Test main async pipeline and metadata creation."""
        orch = self._build_orchestrator()

        section = DOMSection(
            section_type=DOMSectionType.FORMS,
            name="forms",
            elements=[ProcessedElement(tag="input", id="email")],
        )
        segmentation_result = DOMSegmentationResult(
            sections=[section], total_char_size=123
        )
        chunks = [
            DOMChunk(
                chunk_id="forms_0",
                section_type=DOMSectionType.FORMS,
                section_name="forms",
                elements=section.elements,
                char_size=50,
                priority=1,
            )
        ]
        chunk_results = [
            ChunkProcessingResult(
                chunk_id="forms_0",
                section_type=DOMSectionType.FORMS,
                section_name="forms",
                generated_test="*** Test Cases ***\nForm Test\n    No Operation",
            )
        ]

        orch._preprocess_dom = Mock(return_value={"dom_tree": {"tag": "body"}})
        orch._segment_dom = Mock(return_value=segmentation_result)
        orch._process_chunks = AsyncMock(return_value=chunk_results)
        orch._test_aggregator = Mock()
        orch._test_aggregator.aggregate_results.return_value = (
            "*** Test Cases ***\nForm Test\n    No Operation",
            {"sections_processed": 1},
        )

        class _FakeAdaptive:
            def __init__(self, total_token_budget, strategy):
                self.total_token_budget = total_token_budget
                self.strategy = strategy

            def chunk_all_sections_adaptive(self, sections):
                return chunks

        monkeypatch.setattr(
            "app.infrastructure.llm_chunking.orchestrator.AdaptiveChunker",
            _FakeAdaptive,
        )

        fake_request = Mock(id=10)
        fake_session = Mock()

        final_test, metadata = await orch.generate_test_chunked(
            session=fake_session,
            test_request=fake_request,
            page_structure={"dom_tree": {"tag": "body"}},
            user_prompt="Generate login test",
            context="Use Browser library",
            page_url="https://example.com",
        )

        assert "*** Test Cases ***" in final_test
        assert metadata["strategy"] == "chunked"
        assert metadata["chunk_count"] == 1
        assert metadata["sections_count"] == 1
        assert metadata["successful_chunks"] == 1
        assert metadata["total_dom_chars"] == 123

    def test_preprocess_dom_handles_none(self):
        """Test preprocess helper for missing payload."""
        orch = self._build_orchestrator()

        assert orch._preprocess_dom(None) == {}

    def test_preprocess_dom_uses_preprocessor(self):
        """Test preprocess helper delegates to preprocessor."""
        orch = self._build_orchestrator()
        orch._preprocessor = Mock()
        orch._preprocessor.preprocess_page_structure.return_value = {
            "dom_tree": {"tag": "html"}
        }

        result = orch._preprocess_dom({"dom_tree": {"tag": "body"}})

        assert result == {"dom_tree": {"tag": "html"}}
        orch._preprocessor.preprocess_page_structure.assert_called_once()

    def test_segment_dom_cache_hit(self):
        """Test segmentation returns cached entry when available."""
        orch = self._build_orchestrator()
        cached = DOMSegmentationResult(sections=[], total_char_size=10)

        orch._segmentation_cache = Mock()
        orch._segmentation_cache.get.return_value = cached

        result = orch._segment_dom(
            {"dom_tree": {}}, dom_hash="abc", page_url="https://x"
        )

        assert result is cached
        orch._segmentation_cache.set.assert_not_called()

    def test_segment_dom_cache_miss_sets_cache(self):
        """Test segmentation computes and stores cache on miss."""
        orch = self._build_orchestrator()
        computed = DOMSegmentationResult(sections=[], total_char_size=42)

        orch._segmentation_cache = Mock()
        orch._segmentation_cache.get.return_value = None
        orch._segmenter = Mock()
        orch._segmenter.segment_page.return_value = computed

        result = orch._segment_dom({"dom_tree": {}}, dom_hash="hash", page_url=None)

        assert result is computed
        orch._segmentation_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_chunks_delegates_to_processor(self):
        """Test _process_chunks passes through to chunk processor."""
        orch = self._build_orchestrator()
        orch._chunk_processor = Mock()
        expected = [
            ChunkProcessingResult(
                chunk_id="c1",
                section_type=DOMSectionType.UNKNOWN,
                section_name="unknown",
                generated_test="ok",
            )
        ]
        orch._chunk_processor.process_chunks_batch = AsyncMock(return_value=expected)

        result = await orch._process_chunks(
            chunks=[],
            user_prompt="Generate",
            context="ctx",
        )

        assert result == expected
        orch._chunk_processor.process_chunks_batch.assert_awaited_once()

    def test_cache_helpers(self):
        """Test cache stats and clear helpers."""
        orch = self._build_orchestrator()
        orch._segmentation_cache = Mock()
        orch._segmentation_cache.stats.return_value = {"entries": 3, "max_entries": 100}

        stats = orch.get_cache_stats()

        assert "segmentation_cache" in stats
        assert stats["segmentation_cache"]["entries"] == 3

        orch.clear_caches()
        orch._segmentation_cache.clear.assert_called_once()

    def test_last_generation_metadata_property(self):
        orch = self._build_orchestrator()
        orch._last_generation_metadata = {"k": "v"}
        assert orch.last_generation_metadata == {"k": "v"}
