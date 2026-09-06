"""
backend/app/services/risk/risk_session_store.py

In-memory session store that accumulates Module 1–5 evidence summaries
needed by the Module 6 Risk Engine.

Each verification module endpoint populates its section when it runs.
The risk engine reads the accumulated data when /risk is called.

Privacy & Security Design:
  - Ephemeral in-memory storage only — never written to disk or database.
  - TTL-bounded and thread-safe (same pattern as RegistrySessionStore).
  - Stores ONLY normalized evidence summaries — no raw images, embeddings,
    or authentication credentials.
  - Session isolation: each verification_id has its own slot.

Module keys:
  "m1_ocr"        — OCR extraction metadata
  "m2_validation" — Document validation checks
  "m3_forensics"  — Forensic analysis signals
  "m4_biometrics" — Biometric verification results
  "m5_registry"   — Registry verification status & field results
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

MODULE_KEYS = ("m1_ocr", "m2_validation", "m3_forensics", "m4_biometrics", "m5_registry")


class RiskSessionStore:
    """
    Thread-safe, TTL-bounded in-memory accumulator for M1–M5 evidence.
    Each module endpoint adds its evidence summary when it completes.
    """

    def __init__(self, ttl_seconds: int | None = None, max_entries: int = 100) -> None:
        self._ttl = ttl_seconds or getattr(settings, "RISK_SESSION_TTL_SECONDS", 900)
        self._max_entries = max_entries
        self._lock = threading.Lock()
        # map: verification_id → (timestamp, { module_key: evidence_dict })
        self._store: Dict[str, tuple[float, Dict[str, Any]]] = {}

    def update_module(
        self,
        verification_id: str,
        module_key: str,
        evidence: Dict[str, Any],
    ) -> None:
        """
        Add or update evidence for one module in the session.

        Idempotent: re-calling with the same verification_id and module_key
        replaces the previous evidence for that module.

        Args:
            verification_id: Session ID from /ocr.
            module_key:       One of MODULE_KEYS.
            evidence:         JSON-serializable evidence summary dict.
        """
        if module_key not in MODULE_KEYS:
            logger.warning(
                "RiskSessionStore: unknown module_key=%s for id=%s",
                module_key, verification_id,
            )

        with self._lock:
            self._cleanup_expired_unlocked()

            if verification_id in self._store:
                ts, session = self._store[verification_id]
                session[module_key] = evidence
                # Refresh timestamp on any update
                self._store[verification_id] = (time.time(), session)
            else:
                if len(self._store) >= self._max_entries:
                    oldest = min(self._store, key=lambda k: self._store[k][0])
                    del self._store[oldest]
                    logger.debug("RiskSessionStore evicted oldest session=%s", oldest)
                self._store[verification_id] = (time.time(), {module_key: evidence})

        logger.debug(
            "RiskSessionStore updated: id=%s module=%s",
            verification_id, module_key,
        )

    def get(self, verification_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve all accumulated evidence for a session.

        Returns None if session does not exist or has expired.
        Returns a dict with any subset of MODULE_KEYS that have been populated.
        """
        with self._lock:
            self._cleanup_expired_unlocked()
            entry = self._store.get(verification_id)
            if entry is None:
                return None
            ts, session = entry
            if (time.time() - ts) > self._ttl:
                del self._store[verification_id]
                logger.debug("RiskSessionStore expired: id=%s", verification_id)
                return None
            return dict(session)  # return a shallow copy

    def evict(self, verification_id: str) -> bool:
        """Explicitly remove a session."""
        with self._lock:
            if verification_id in self._store:
                del self._store[verification_id]
                return True
            return False

    def _cleanup_expired_unlocked(self) -> None:
        """Remove all expired sessions. Must hold self._lock."""
        now = time.time()
        expired = [k for k, (ts, _) in self._store.items() if (now - ts) > self._ttl]
        for k in expired:
            del self._store[k]

    @property
    def session_count(self) -> int:
        with self._lock:
            self._cleanup_expired_unlocked()
            return len(self._store)


# Singleton shared across the application
risk_session_store = RiskSessionStore()
