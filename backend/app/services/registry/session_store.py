"""
backend/app/services/registry/session_store.py

In-memory session store for normalized registry verification data.

Stores the document identity fields needed for registry verification,
keyed by verification_id. Populated at /ocr time (Module 1).
Read at /registry time (Module 5).

Privacy & Security Design:
  - Ephemeral in-memory storage only — never written to disk or database.
  - Bounded size and automatic TTL expiry (default: 15 minutes).
  - Thread-safe access.
  - Contains only normalized identity fields — no raw images or biometric data.
  - Session isolation: each verification_id accesses only its own data.

Follows the same pattern as SessionDocumentStore in services/face/session_store.py.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class RegistrySessionStore:
    """Thread-safe, TTL-bounded in-memory store for registry verification session data."""

    def __init__(self, ttl_seconds: int | None = None, max_entries: int = 100) -> None:
        self._ttl = ttl_seconds or settings.REGISTRY_SESSION_TTL_SECONDS
        self._max_entries = max_entries
        self._lock = threading.Lock()
        # map: verification_id → (timestamp, session_data_dict)
        self._store: Dict[str, tuple[float, Dict[str, Any]]] = {}

    def set(self, verification_id: str, session_data: Dict[str, Any]) -> None:
        """
        Store normalized identity fields for a verification session.

        Args:
            verification_id: Unique session ID from Module 1 /ocr.
            session_data: Normalized identity fields dict. Example keys:
                          'document_number', 'name', 'date_of_birth',
                          'nationality', 'expiry_date', 'issuing_authority',
                          'document_type', 'mrz_data', 'traveler_data'
        """
        with self._lock:
            self._cleanup_expired_unlocked()
            if len(self._store) >= self._max_entries:
                # Evict oldest entry
                oldest_id = min(self._store, key=lambda k: self._store[k][0])
                del self._store[oldest_id]
                logger.debug("RegistrySessionStore evicted oldest session=%s", oldest_id)

            self._store[verification_id] = (time.time(), session_data)
            logger.debug(
                "RegistrySessionStore cached session=%s field_count=%d",
                verification_id, len(session_data),
            )

    def get(self, verification_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data if active and not expired.

        Returns None if the session does not exist or has expired.
        """
        with self._lock:
            self._cleanup_expired_unlocked()
            entry = self._store.get(verification_id)
            if entry is None:
                return None
            ts, session_data = entry
            if (time.time() - ts) > self._ttl:
                del self._store[verification_id]
                logger.debug(
                    "RegistrySessionStore session expired: id=%s", verification_id
                )
                return None
            return session_data

    def evict(self, verification_id: str) -> bool:
        """Explicitly remove session data."""
        with self._lock:
            if verification_id in self._store:
                del self._store[verification_id]
                logger.debug("RegistrySessionStore evicted session=%s", verification_id)
                return True
            return False

    def _cleanup_expired_unlocked(self) -> None:
        """Remove all expired sessions. Must hold self._lock."""
        now = time.time()
        expired_keys = [
            k for k, (ts, _) in self._store.items() if (now - ts) > self._ttl
        ]
        for k in expired_keys:
            del self._store[k]

    @property
    def session_count(self) -> int:
        """Number of active sessions (for monitoring)."""
        with self._lock:
            self._cleanup_expired_unlocked()
            return len(self._store)


# Singleton instance — shared across the application
registry_session_store = RegistrySessionStore()
