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
        # map: verification_id -> (timestamp, face_result, face_crop)
        self._face_cache: dict[str, tuple[float, Any, Any]] = {}

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

    def set_face_cache(
        self,
        verification_id: str,
        doc_box: Any,
        doc_crop: Any,
        doc_aligned: Any = None,
        doc_embedding: Any = None,
        detector_used: str = "InsightFace-SCRFD-10G",
    ) -> None:
        """Cache detected document face result and pre-enhanced crop for sub-second verification."""
        with self._lock:
            self._face_cache[verification_id] = (
                time.time(),
                {
                    "doc_box": doc_box,
                    "doc_crop": doc_crop,
                    "doc_aligned": doc_aligned,
                    "doc_embedding": doc_embedding,
                    "detector_used": detector_used,
                },
            )

    def get_face_cache(self, verification_id: str) -> Optional[dict[str, Any]]:
        """Retrieve pre-detected document face result and crop if cached."""
        with self._lock:
            entry = self._face_cache.get(verification_id)
            if entry is None:
                return None
            ts, data = entry
            if (time.time() - ts) > self._ttl:
                del self._face_cache[verification_id]
                return None
            return data

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
