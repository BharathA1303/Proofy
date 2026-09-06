"""
backend/app/services/face/session_store.py

In-memory document cache for verification sessions.

Privacy & Security Design:
  - Ephemeral in-memory storage only — never written to disk or database.
  - Bounded size and automatic TTL expiry (default: 15 minutes).
  - Explicit evict() called after processing or on session reset.
  - Thread-safe access.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class SessionDocumentStore:
    """Thread-safe, TTL-bounded in-memory store for session document images."""

    def __init__(self, ttl_seconds: int | None = None, max_entries: int = 100) -> None:
        self._ttl = ttl_seconds or settings.BIOMETRIC_SESSION_TTL_SECONDS
        self._max_entries = max_entries
        self._lock = threading.Lock()
        # map: verification_id -> (timestamp, raw_bytes)
        self._store: dict[str, tuple[float, bytes]] = {}

    def set(self, verification_id: str, raw_bytes: bytes) -> None:
        """Store document raw bytes for a verification session."""
        with self._lock:
            self._cleanup_expired_unlocked()
            if len(self._store) >= self._max_entries:
                # Evict oldest entry
                oldest_id = min(self._store, key=lambda k: self._store[k][0])
                del self._store[oldest_id]
                logger.debug("SessionDocumentStore evicted oldest session=%s", oldest_id)

            self._store[verification_id] = (time.time(), raw_bytes)
            logger.debug(
                "SessionDocumentStore cached document for session=%s (size=%d bytes)",
                verification_id, len(raw_bytes),
            )

    def get(self, verification_id: str) -> Optional[bytes]:
        """Retrieve document bytes if session is active and not expired."""
        with self._lock:
            self._cleanup_expired_unlocked()
            entry = self._store.get(verification_id)
            if entry is None:
                return None
            ts, raw_bytes = entry
            if (time.time() - ts) > self._ttl:
                del self._store[verification_id]
                return None
            return raw_bytes

    def evict(self, verification_id: str) -> bool:
        """Explicitly remove document bytes for a session."""
        with self._lock:
            if verification_id in self._store:
                del self._store[verification_id]
                logger.debug("SessionDocumentStore evicted session=%s", verification_id)
                return True
            return False

    def _cleanup_expired_unlocked(self) -> None:
        """Remove all expired sessions (must hold self._lock)."""
        now = time.time()
        expired_keys = [k for k, (ts, _) in self._store.items() if (now - ts) > self._ttl]
        for k in expired_keys:
            del self._store[k]


session_document_store = SessionDocumentStore()
