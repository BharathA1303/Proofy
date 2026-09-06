"""
backend/app/services/case/case_store.py

Thread-safe, TTL-bounded in-memory storage for VerificationCase sessions.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional, Tuple

from app.core.config import settings
from app.services.case.verification_case import VerificationCase

logger = logging.getLogger(__name__)


class VerificationCaseStore:
    """Thread-safe in-memory store for Multi-Document Verification Cases."""

    def __init__(self, ttl_seconds: Optional[int] = None, max_entries: int = 200) -> None:
        self._ttl = ttl_seconds or getattr(settings, "CASE_SESSION_TTL_SECONDS", 3600)
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._access_counter = 0
        # map: case_id -> (timestamp, access_counter, VerificationCase)
        self._store: Dict[str, Tuple[float, int, VerificationCase]] = {}

    def get(self, case_id: str) -> Optional[VerificationCase]:
        with self._lock:
            self._evict_expired()
            entry = self._store.get(case_id)
            if entry is None:
                return None
            _, _, case = entry
            self._access_counter += 1
            self._store[case_id] = (time.time(), self._access_counter, case)
            return case

    def set(self, case_id: str, case: VerificationCase) -> None:
        with self._lock:
            self._evict_expired()
            if len(self._store) >= self._max_entries and case_id not in self._store:
                oldest_id = min(self._store.keys(), key=lambda k: self._store[k][1])
                del self._store[oldest_id]
                logger.info("VerificationCaseStore: evicted oldest case id=%s", oldest_id)
            self._access_counter += 1
            self._store[case_id] = (time.time(), self._access_counter, case)

    def delete(self, case_id: str) -> bool:
        with self._lock:
            if case_id in self._store:
                del self._store[case_id]
                return True
            return False

    def has(self, case_id: str) -> bool:
        with self._lock:
            self._evict_expired()
            return case_id in self._store

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [
            cid for cid, (ts, _, _) in self._store.items()
            if now - ts > self._ttl
        ]
        for cid in expired:
            del self._store[cid]
            logger.info("VerificationCaseStore: expired case id=%s", cid)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


case_store = VerificationCaseStore()
