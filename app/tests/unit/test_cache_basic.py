"""Tests for segmentation cache."""

import pytest
from app.domain.dom.models import DOMSegmentationResult, DOMSection, DOMSectionType
from app.infrastructure.dom_cache.segmentation_cache import DOMSegmentationCache, DOMHasher


class TestDOMHasherBasic:
    """Basic tests for DOMHasher."""

    def test_hash_dom_tree_simple(self):
        """Test hashing a simple DOM tree."""
        dom_tree = {"tag": "div", "children": []}
        
        hash_value = DOMHasher.hash_dom_tree(dom_tree)

        assert isinstance(hash_value, str)
        assert len(hash_value) > 0

    def test_hash_dom_tree_consistency(self):
        """Test that same DOM produces same hash."""
        dom_tree = {"tag": "div", "id": "content", "children": []}
        
        hash1 = DOMHasher.hash_dom_tree(dom_tree)
        hash2 = DOMHasher.hash_dom_tree(dom_tree)

        assert hash1 == hash2

    def test_hash_dom_tree_different_inputs(self):
        """Test that different DOMs produce different hashes."""
        # Note: hash_dom_tree normalizes and removes 'text', so same tag gives same hash
        # Use attributes that are preserved
        dom1 = {"tag": "div", "id": "content1"}
        dom2 = {"tag": "div", "id": "content2"}
        
        hash1 = DOMHasher.hash_dom_tree(dom1)
        hash2 = DOMHasher.hash_dom_tree(dom2)

        assert hash1 != hash2

    def test_hash_page_structure(self):
        """Test hashing page structure."""
        page = {
            "url": "https://example.com",
            "dom_tree": {"tag": "body", "children": []},
        }
        
        hash_value = DOMHasher.hash_page_structure(page)

        assert isinstance(hash_value, str)
        assert len(hash_value) > 0

    def test_hash_dom_tree_none_returns_empty(self):
        assert DOMHasher.hash_dom_tree(None) == ""

    def test_normalize_for_hash_removes_non_structural_fields(self):
        normalized = DOMHasher._normalize_for_hash(
            {"tag": "input", "text": "x", "onclick": "y", "value": "z", "id": "a"}
        )
        assert "text" not in normalized
        assert "onclick" not in normalized
        assert "value" not in normalized
        assert normalized["id"] == "a"


class TestDOMSegmentationCacheBasic:
    """Basic tests for DOMSegmentationCache."""

    def test_cache_get_miss(self):
        """Test cache miss returns None."""
        cache = DOMSegmentationCache(max_entries=100)
        
        result = cache.get(page_url="https://example.com", dom_hash="nonexistent")

        assert result is None

    def test_cache_set_and_get(self):
        """Test cache set and get."""
        cache = DOMSegmentationCache(max_entries=100)
        
        result = DOMSegmentationResult(sections=[], total_char_size=100)
        key = "test_key"
        
        cache.set(page_url="https://example.com", dom_hash=key, result=result)
        retrieved = cache.get(page_url="https://example.com", dom_hash=key)

        assert retrieved is not None
        assert retrieved.total_char_size == 100

    def test_cache_clear(self):
        """Test clearing cache."""
        cache = DOMSegmentationCache(max_entries=100)
        
        result = DOMSegmentationResult(sections=[], total_char_size=100)
        cache.set(page_url="https://example.com", dom_hash="key1", result=result)
        
        cache.clear()
        
        retrieved = cache.get(page_url="https://example.com", dom_hash="key1")

        assert retrieved is None

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = DOMSegmentationCache(max_entries=100)
        
        result = DOMSegmentationResult(sections=[], total_char_size=100)
        cache.set(page_url="https://example.com", dom_hash="key1", result=result)
        
        stats = cache.stats()

        assert "entries" in stats
        assert stats["entries"] >= 1
        assert "max_entries" in stats

    def test_cache_respects_max_entries(self):
        """Test that cache respects max_entries limit."""
        cache = DOMSegmentationCache(max_entries=5)
        
        result = DOMSegmentationResult(sections=[], total_char_size=100)
        
        for i in range(10):
            cache.set(
                page_url=f"https://example{i}.com",
                dom_hash=f"key_{i}",
                result=result,
            )
        
        stats = cache.stats()

        assert stats["entries"] <= 5

    def test_cache_without_url(self):
        """Test cache without URL (hash-only lookup)."""
        cache = DOMSegmentationCache(max_entries=100)
        
        result = DOMSegmentationResult(sections=[], total_char_size=100)
        
        cache.set(page_url=None, dom_hash="hash_only", result=result)
        retrieved = cache.get(page_url=None, dom_hash="hash_only")

        assert retrieved is not None

    def test_cache_get_with_empty_dom_hash_returns_none(self):
        cache = DOMSegmentationCache(max_entries=10)
        assert cache.get(page_url="https://x", dom_hash=None) is None

    def test_cache_set_with_empty_dom_hash_is_noop(self):
        cache = DOMSegmentationCache(max_entries=10)
        result = DOMSegmentationResult(sections=[], total_char_size=1)
        cache.set(page_url="https://x", dom_hash="", result=result)
        assert cache.stats()["entries"] == 0

    def test_cache_set_existing_key_updates_access_order(self):
        cache = DOMSegmentationCache(max_entries=10)
        result = DOMSegmentationResult(sections=[], total_char_size=1)
        cache.set(page_url="https://x", dom_hash="h1", result=result)
        cache.set(page_url="https://x", dom_hash="h1", result=result)
        assert cache.stats()["entries"] == 1
