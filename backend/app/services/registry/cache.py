"""
backend/app/services/registry/cache.py

Thread-safe in-memory registry verification response cache.

Provides query-hash keyed deduplication and short-term caching to prevent
redundant calls to authoritative external providers or mock registries.
Tracks freshness metadata (retrieved_at, ttl_seconds, is_fresh, cached)
without storing plain-text PII keys.
"""
from __future__ import annotations

import copy
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from app.schemas.registry import RegistryStatus, RegistryVerificationResponse

logger = logging.getLogger(__name__)

# Non-cacheable statuses (transient or infra failures that should be retried)
NON_CACHEABLE_STATUSES = {
    RegistryStatus.UNAVAILABLE,
    RegistryStatus.TIMEOUT,
    RegistryStatus.PROVIDER_ERROR,
    RegistryStatus.RATE_LIMITED,
    RegistryStatus.ERROR,
}


class RegistryCacheEntry:
    """Represents a cached registry response entry."""

    def __init__(
        self,
        response: RegistryVerificationResponse,
        ttl_seconds: float,
        retrieved_at: Optional[str] = None,
    ) -> None:
        self.response = response.model_copy(deep=True)
        self.cached_at = time.time()
        self.ttl_seconds = ttl_seconds
        self.retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.cached_at) > self.ttl_seconds

    @property
    def remaining_ttl(self) -> float:
        return max(0.0, (self.cached_at + self.ttl_seconds) - time.time())


class RegistryCache:
    """Thread-safe in-memory cache for registry verification responses."""

    def __init__(self, default_ttl_seconds: float = 300.0) -> None:
        self._default_ttl = default_ttl_seconds
        self._cache: Dict[Tuple[str, str, str], RegistryCacheEntry] = {}
        self._lock = threading.Lock()

    def _make_key(self, document_type: str, query_hash: str, provider_id: str = "") -> Tuple[str, str, str]:
        return (
            (document_type or "").strip().lower(),
            (query_hash or "").strip(),
            (provider_id or "").strip().lower(),
        )

    def get(
        self,
        document_type: str,
        query_hash: str,
        provider_id: str = "",
    ) -> Optional[RegistryVerificationResponse]:
        """
        Retrieve a cached response if present and not expired.
        Returns a deep copy with updated freshness telemetry.
        """
        if not query_hash:
            return None

        key = self._make_key(document_type, query_hash, provider_id)

        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            if entry.is_expired:
                del self._cache[key]
                logger.debug("RegistryCache expired for key %s", key)
                return None

            # Clone response to prevent mutation
            cloned = entry.response.model_copy(deep=True)
            remaining = round(entry.remaining_ttl, 1)
            cloned.freshness = {
                "cached": True,
                "is_fresh": True,
                "retrieved_at": entry.retrieved_at,
                "ttl_seconds": remaining,
                "source": "cache",
            }
            logger.info(
                "RegistryCache hit for doc_type=%s hash=%s provider=%s remaining_ttl=%.1fs",
                document_type, query_hash[:8], provider_id, remaining,
            )
            return cloned

    def set(
        self,
        document_type: str,
        query_hash: str,
        response: RegistryVerificationResponse,
        provider_id: str = "",
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """
        Cache a registry response.
        Transient errors (TIMEOUT, UNAVAILABLE, etc.) are NOT cached.
        """
        if not query_hash:
            return

        # Check status
        status_val = response.registry.get("status")
        if status_val:
            try:
                status = RegistryStatus(status_val)
                if status in NON_CACHEABLE_STATUSES:
                    logger.debug("RegistryCache skipping non-cacheable status %s", status_val)
                    return
            except ValueError:
                pass

        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        key = self._make_key(document_type, query_hash, provider_id)

        retrieved_at = (
            response.freshness.get("retrieved_at")
            if response.freshness
            else datetime.now(timezone.utc).isoformat()
        )

        with self._lock:
            self._cache[key] = RegistryCacheEntry(
                response=response,
                ttl_seconds=ttl,
                retrieved_at=retrieved_at,
            )
            logger.debug(
                "RegistryCache stored doc_type=%s hash=%s provider=%s ttl=%.1fs",
                document_type, query_hash[:8], provider_id, ttl,
            )

    def invalidate(self, document_type: str, query_hash: str, provider_id: str = "") -> bool:
        """Invalidate a specific cache entry."""
        key = self._make_key(document_type, query_hash, provider_id)
        with self._lock:
            return self._cache.pop(key, None) is not None

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Return number of cached entries (including potentially expired ones)."""
        with self._lock:
            return len(self._cache)


# Global singleton instance
registry_cache = RegistryCache()
