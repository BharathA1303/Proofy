"""
backend/app/services/machine_readable/decoder.py

Generic Machine-Readable Payload Decoder and Byte Processor.
Handles binary vs text payloads, UTF-8 normalization, SHA-256 hash generation,
and safe sanitization of machine-readable string inputs.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional, Tuple

from app.services.machine_readable.schema import QRPayloadType

logger = logging.getLogger(__name__)

# Maximum allowed payload length to prevent DoS via massive payloads
MAX_PAYLOAD_BYTES = 64 * 1024  # 64 KB


class QRDecoder:
    """
    Decodes and sanitizes machine-readable payload bytes and strings.
    Guarantees tamper-evident SHA-256 hash computation and safe encoding handling.
    """

    def decode_raw(
        self,
        raw_text: Optional[str] = None,
        raw_bytes: Optional[bytes] = None,
    ) -> Tuple[Optional[str], str, QRPayloadType, Optional[str]]:
        """
        Process raw text or bytes into a clean, hashed representation.

        Args:
            raw_text: Decoded string if available.
            raw_bytes: Raw bytes if available.

        Returns:
            Tuple of:
              - cleaned text string (or None if purely binary/undecodable)
              - SHA-256 hex digest of the raw payload
              - initial QRPayloadType classification
              - error message (if any)
        """
        if raw_bytes is None and raw_text is not None:
            raw_bytes = raw_text.encode("utf-8", errors="replace")

        if raw_bytes is None:
            return None, "", QRPayloadType.CORRUPTED, "No payload content provided"

        if len(raw_bytes) > MAX_PAYLOAD_BYTES:
            sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
            return None, sha256_hash, QRPayloadType.CORRUPTED, f"Payload exceeds max allowed size ({len(raw_bytes)} > {MAX_PAYLOAD_BYTES} bytes)"

        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()

        # Try UTF-8 decoding
        try:
            text = raw_bytes.decode("utf-8")
            # Filter null bytes or control characters except standard whitespace
            cleaned_text = "".join(ch for ch in text if ch in "\t\r\n" or ord(ch) >= 32)
            return cleaned_text, sha256_hash, QRPayloadType.UNKNOWN, None
        except UnicodeDecodeError:
            # Fallback to latin-1 / binary classification
            return None, sha256_hash, QRPayloadType.BINARY, "Payload contains non-UTF8 binary data"
