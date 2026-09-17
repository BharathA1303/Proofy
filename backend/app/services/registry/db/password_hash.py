"""
backend/app/services/registry/db/password_hash.py

Password hashing utilities for the Meiyari officer account system.
Uses PBKDF2-HMAC-SHA256 with a per-user random salt (never Fernet-reversible —
passwords must never be recoverable, only verifiable).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

_PBKDF2_ITERATIONS = 260_000


def hash_password(plain_password: str) -> str:
    """
    Derive a salted PBKDF2-HMAC-SHA256 hash for a plaintext password.
    Returns a self-contained string: "pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>".
    """
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("utf-8"),
        base64.b64encode(derived).decode("utf-8"),
    )


def verify_password(plain_password: str, encoded_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2 hash string."""
    try:
        algorithm, iterations_str, salt_b64, hash_b64 = encoded_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False

    derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)
