"""Tests for chunk processor."""

import pytest
from unittest.mock import Mock
from app.domain.dom.models import DOMChunk, DOMSectionType, ProcessedElement, ChunkProcessingResult
from app.infrastructure.llm_chunking.chunk_processor import ChunkProcessor
from app.llm.groq_client import PayloadTooLargeError


class TestChunkProcessorBasic:
    """Basic tests for ChunkProcessor."""

    @pytest.fixture
    def mock_groq_client(self):
        """Mock Groq client."""
        client = Mock()
        client.generate_robot_test = Mock(return_value="Test Chunk\n    Click Button")
        return client

    @pytest.mark.asyncio
    async def test_process_chunk_basic(self, mock_groq_client):
        """Test basic chunk processing."""
        processor = ChunkProcessor(groq_client=mock_groq_client)
        
        chunk = DOMChunk(
            chunk_id="chunk_1",
            section_type=DOMSectionType.FORMS,
            section_name="forms",
            elements=[ProcessedElement(tag="input", id="email")],
            char_size=100,
        )

        result = await processor.process_chunk(
            chunk=chunk,
            user_prompt="Generate test",
        )

        assert isinstance(result, ChunkProcessingResult)
        assert result.chunk_id == "chunk_1"

    @pytest.mark.asyncio
    async def test_process_chunk_preserves_metadata(self, mock_groq_client):
        """Test that chunk metadata is preserved."""
        processor = ChunkProcessor(groq_client=mock_groq_client)
        
        chunk = DOMChunk(
            chunk_id="chunk_test",
            section_type=DOMSectionType.HEADER,
            section_name="header",
            elements=[],
            char_size=50,
            priority=10,
        )

        result = await processor.process_chunk(
            chunk=chunk,
            user_prompt="test",
        )

        assert result.chunk_id == "chunk_test"
        assert result.section_type == DOMSectionType.HEADER

    @pytest.mark.asyncio
    async def test_process_chunks_batch_basic(self, mock_groq_client):
        """Test batch processing of chunks."""
        processor = ChunkProcessor(groq_client=mock_groq_client)
        
        chunks = [
            DOMChunk(
                chunk_id=f"chunk_{i}",
                section_type=DOMSectionType.FORMS,
                section_name="forms",
                elements=[],
                char_size=100,
            )
            for i in range(3)
        ]

        results = await processor.process_chunks_batch(
            chunks=chunks,
            user_prompt="Generate test",
        )

        assert len(results) == 3
        assert all(isinstance(r, ChunkProcessingResult) for r in results)

    @pytest.mark.asyncio
    async def test_process_chunk_with_context(self, mock_groq_client):
        """Test chunk processing with context."""
        processor = ChunkProcessor(groq_client=mock_groq_client)
        
        chunk = DOMChunk(
            chunk_id="chunk_1",
            section_type=DOMSectionType.FORMS,
            section_name="forms",
            elements=[],
            char_size=100,
        )

        result = await processor.process_chunk(
            chunk=chunk,
            user_prompt="Generate test",
            context="Additional context",
        )

        assert isinstance(result, ChunkProcessingResult)

    def test_processor_initialization(self, mock_groq_client):
        """Test processor initialization."""
        processor = ChunkProcessor(groq_client=mock_groq_client)

        assert processor._groq_client is not None

    def test_create_section_context_includes_all_parts(self, mock_groq_client):
        """Test internal section context construction."""
        processor = ChunkProcessor(groq_client=mock_groq_client)
        chunk = DOMChunk(
            chunk_id="c1",
            section_type=DOMSectionType.MAIN_CONTENT,
            section_name="content",
            elements=[ProcessedElement(tag="p", text="hello")],
            char_size=10,
        )

        context = processor._create_section_context(
            chunk=chunk,
            user_prompt="Generate robust tests",
            context="Prefer accessibility locators",
        )

        assert "main content" in context
        assert "Section name: content" in context
        assert "Additional context" in context
        assert "Generate robust tests" in context

    def test_compact_chunk_truncates_long_text(self, mock_groq_client):
        """Test _compact_chunk strips long text from elements."""
        processor = ChunkProcessor(groq_client=mock_groq_client)
        chunk = DOMChunk(
            chunk_id="c2",
            section_type=DOMSectionType.FORMS,
            section_name="forms",
            elements=[
                ProcessedElement(tag="input", text="A" * 80),
                ProcessedElement(tag="button", text="short"),
            ],
            char_size=200,
        )

        compact = processor._compact_chunk(chunk)

        assert compact.elements[0].text is None
        assert compact.elements[1].text == "short"
        assert compact.char_size >= 0

    @pytest.mark.asyncio
    async def test_process_chunk_retries_after_payload_too_large(self):
        """Test retry path when first call exceeds payload and second succeeds."""
        groq = Mock()
        groq.generate_robot_test = Mock(
            side_effect=[PayloadTooLargeError("too large"), "Recovered test"]
        )
        processor = ChunkProcessor(groq_client=groq)

        chunk = DOMChunk(
            chunk_id="retry_chunk",
            section_type=DOMSectionType.FORMS,
            section_name="forms",
            elements=[ProcessedElement(tag="input", text="A" * 120)],
            char_size=300,
        )

        result = await processor.process_chunk(chunk=chunk, user_prompt="Generate")

        assert result.generated_test == "Recovered test"
        assert result.metadata.get("compacted") is True

    @pytest.mark.asyncio
    async def test_process_chunk_raises_when_retry_disabled(self):
        """Test PayloadTooLargeError is propagated when retry is disabled."""
        groq = Mock()
        groq.generate_robot_test = Mock(side_effect=PayloadTooLargeError("too large"))
        processor = ChunkProcessor(groq_client=groq)

        chunk = DOMChunk(
            chunk_id="no_retry",
            section_type=DOMSectionType.FORMS,
            section_name="forms",
            elements=[ProcessedElement(tag="input", text="A")],
            char_size=50,
        )

        with pytest.raises(PayloadTooLargeError):
            await processor.process_chunk(
                chunk=chunk,
                user_prompt="Generate",
                retry_on_large_payload=False,
            )

    @pytest.mark.asyncio
    async def test_process_chunks_batch_returns_failed_result_on_exception(self):
        """Test batch processing returns empty generated_test for failed chunks."""
        groq = Mock()
        groq.generate_robot_test = Mock(side_effect=Exception("boom"))
        processor = ChunkProcessor(groq_client=groq)

        chunks = [
            DOMChunk(
                chunk_id="bad_chunk",
                section_type=DOMSectionType.UNKNOWN,
                section_name="unknown",
                elements=[],
                char_size=10,
            )
        ]

        results = await processor.process_chunks_batch(chunks, user_prompt="Generate")

        assert len(results) == 1
        assert results[0].generated_test == ""
        assert "error" in results[0].metadata

    @pytest.mark.asyncio
    async def test_process_chunk_raises_when_compacted_retry_also_too_large(self):
        groq = Mock()
        groq.generate_robot_test = Mock(
            side_effect=[PayloadTooLargeError("too large"), PayloadTooLargeError("still too large")]
        )
        processor = ChunkProcessor(groq_client=groq)

        chunk = DOMChunk(
            chunk_id="retry_fail",
            section_type=DOMSectionType.FORMS,
            section_name="forms",
            elements=[ProcessedElement(tag="input", text="A" * 150)],
            char_size=400,
        )

        with pytest.raises(PayloadTooLargeError):
            await processor.process_chunk(chunk=chunk, user_prompt="Generate")
