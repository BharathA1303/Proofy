"""
backend/app/services/ocr/ocr_cache.py

High-Performance Deterministic Extraction Cache.
Speeds up repeated inspections, test vectors, and rapid screening by indexing
OCR extraction results using SHA-256 content digests.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

_OCR_CACHE: Dict[str, Any] = {}


def compute_image_hash(raw_bytes: bytes) -> str:
    """Compute deterministic SHA-256 fingerprint for document content."""
    return hashlib.sha256(raw_bytes).hexdigest()


def get_cached_ocr(raw_bytes: bytes, doc_type: str) -> Optional[Any]:
    """Retrieve cached OCR response payload if exact image was previously ingested."""
    digest = compute_image_hash(raw_bytes)
    key = f"{doc_type.lower().strip()}:{digest}"
    return _OCR_CACHE.get(key)


def set_cached_ocr(raw_bytes: bytes, doc_type: str, result_dict: Any) -> None:
    """Cache OCR results for subsequent zero-latency verification."""
    digest = compute_image_hash(raw_bytes)
    key = f"{doc_type.lower().strip()}:{digest}"
    _OCR_CACHE[key] = result_dict


def clear_ocr_cache() -> None:
    """Clear all entries in the OCR extraction cache."""
    _OCR_CACHE.clear()

