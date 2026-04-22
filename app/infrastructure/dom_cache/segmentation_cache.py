"""Caching for processed DOM structures to avoid reprocessing."""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Optional

from app.domain.dom.models import DOMSection, DOMSegmentationResult

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cached DOM processing result."""

    hash_key: str
    segmentation_result: DOMSegmentationResult
    page_url: str | None = None
    metadata: dict | None = None


class DOMSegmentationCache:
    """In-memory cache for DOM segmentation results."""

    def __init__(self, max_entries: int = 100):
        """Initialize cache.

        Args:
            max_entries: Maximum entries to keep in cache
        """
        self.max_entries = max_entries
        self._cache: dict[str, CacheEntry] = {}
        self._access_order: list[str] = []

    def get(
        self, page_url: str | None, dom_hash: str | None
    ) -> DOMSegmentationResult | None:
        """Retrieve cached segmentation result.

        Args:
            page_url: Page URL (optional)
            dom_hash: Hash of preprocessed DOM

        Returns:
            Cached DOMSegmentationResult or None
        """
        if not dom_hash:
            return None

        key = f"{page_url}:{dom_hash}" if page_url else dom_hash

        if key not in self._cache:
            return None

        entry = self._cache[key]

        # Update access order for LRU
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        logger.debug("DOM cache hit for %s", key[:30])
        return entry.segmentation_result

    def set(
        self,
        page_url: str | None,
        dom_hash: str,
        result: DOMSegmentationResult,
        metadata: dict | None = None,
    ) -> None:
        """Store segmentation result in cache.

        Args:
            page_url: Page URL (optional)
            dom_hash: Hash of preprocessed DOM
            result: DOMSegmentationResult to cache
            metadata: Optional metadata
        """
        if not dom_hash:
            return

        key = f"{page_url}:{dom_hash}" if page_url else dom_hash

        entry = CacheEntry(
            hash_key=key,
            segmentation_result=result,
            page_url=page_url,
            metadata=metadata,
        )

        self._cache[key] = entry

        # Update access order
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        # Evict oldest entry if at capacity
        if len(self._cache) > self.max_entries:
            oldest_key = self._access_order.pop(0)
            del self._cache[oldest_key]
            logger.debug("Evicted oldest cache entry: %s", oldest_key[:30])

        logger.debug("Cached DOM segmentation: %s", key[:30])

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._access_order.clear()
        logger.info("DOM cache cleared")

    def stats(self) -> dict:
        """Get cache statistics."""
        return {
            "entries": len(self._cache),
            "max_entries": self.max_entries,
        }


class DOMHasher:
    """Utility for hashing DOM structures for cache keys."""

    @staticmethod
    def hash_dom_tree(dom_tree: dict | None) -> str:
        """Generate hash from DOM tree structure.

        Args:
            dom_tree: DOM tree dict

        Returns:
            Hex hash string
        """
        if not dom_tree:
            return ""

        # Create normalized JSON for hashing
        # (hashing structure only, not text content)
        normalized = DOMHasher._normalize_for_hash(dom_tree)
        json_str = json.dumps(normalized, sort_keys=True)

        hash_obj = hashlib.md5(json_str.encode())
        return hash_obj.hexdigest()

    @staticmethod
    def hash_page_structure(page_structure: dict) -> str:
        """Generate hash from full page structure.

        Args:
            page_structure: Page structure dict

        Returns:
            Hex hash string
        """
        # Hash only structural data, not text
        normalized = {
            "dom_hash": DOMHasher.hash_dom_tree(page_structure.get("dom_tree")),
            "url": page_structure.get("url"),
        }

        json_str = json.dumps(normalized, sort_keys=True)
        hash_obj = hashlib.md5(json_str.encode())
        return hash_obj.hexdigest()

    @staticmethod
    def _normalize_for_hash(obj: dict | list | None) -> dict | list | None:
        """Normalize object for hashing (remove text, keep structure).

        Args:
            obj: Object to normalize

        Returns:
            Normalized object
        """
        if isinstance(obj, dict):
            normalized = {}
            for key, value in obj.items():
                # Skip text content and other non-structural fields
                if key in {"text", "onclick", "value"}:
                    continue
                normalized[key] = DOMHasher._normalize_for_hash(value)
            return normalized
        elif isinstance(obj, list):
            return [DOMHasher._normalize_for_hash(item) for item in obj]
        else:
            # For primitive values, just return as-is
            return obj
