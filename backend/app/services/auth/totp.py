"""
backend/app/services/auth/totp.py

RFC 6238 / RFC 4226 Time-based One-Time Password (TOTP) verification.
Mirrors the frontend's src/utils/totp.js implementation (SHA-1, 6 digits, 30s step)
so that QR codes generated for Google/Microsoft Authenticator remain compatible.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import struct
import time
from typing import Optional


def _base32_decode(secret: str) -> bytes:
    cleaned = re.sub(r"[\s-]", "", secret.upper())
    padding = "=" * ((8 - len(cleaned) % 8) % 8)
    return base64.b32decode(cleaned + padding)


def generate_totp(secret: str, timestamp: Optional[float] = None, digits: int = 6, period: int = 30) -> str:
    """Generate the current 6-digit TOTP code for a Base32 secret."""
    if timestamp is None:
        timestamp = time.time()
    key = _base32_decode(secret)
    counter = int(timestamp // period)
    counter_bytes = struct.pack(">Q", counter)

    hmac_digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = hmac_digest[-1] & 0x0F
    binary = (
        ((hmac_digest[offset] & 0x7F) << 24)
        | ((hmac_digest[offset + 1] & 0xFF) << 16)
        | ((hmac_digest[offset + 2] & 0xFF) << 8)
        | (hmac_digest[offset + 3] & 0xFF)
    )
    otp = binary % (10 ** digits)
    return str(otp).zfill(digits)


def verify_totp(code: str, secret: str, window_steps: int = 2, period: int = 30) -> bool:
    """
    Verify a 6-digit code against a Base32 secret, tolerating clock drift
    within ±window_steps time steps (default ±2 * 30s = ±60s).
    """
    clean_code = re.sub(r"\D", "", str(code))
    if len(clean_code) != 6 or not secret:
        return False

    now = time.time()
    for step in range(-window_steps, window_steps + 1):
        expected = generate_totp(secret, now + step * period)
        if hmac.compare_digest(clean_code, expected):
            return True
    return False
