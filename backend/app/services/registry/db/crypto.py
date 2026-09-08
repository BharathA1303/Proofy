"""
backend/app/services/registry/db/crypto.py

Cryptographic Services for Encrypted Government Registry Database.
Ensures zero sensitive identity data or blacklist information is readable in plaintext
within the SQLite database file.

Security Mechanisms:
1. Symmetric Encryption: AES-128 in CBC mode with HMAC-SHA256 authentication (Fernet).
2. Key Derivation: PBKDF2 with HMAC-SHA256 using fixed system salt.
3. Blind Indexing: Keyed HMAC-SHA256 digest over normalized document tokens.
   Permits O(1) indexed SQL search queries without exposing plaintext values.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Master government registry secret (can be overridden via environment variable)
_REGISTRY_SECRET = os.getenv(
    "GOV_REGISTRY_MASTER_KEY",
    "GOV_INDIA_BORDER_CREDENTIAL_REGISTRY_SECURE_KEY_2026_AUTH",
).encode("utf-8")

# Fixed salt for PBKDF2 deterministic key derivation across application restarts
_KEY_SALT = b"GOV_REGISTRY_ENCRYPTION_SALT_v1"
_BLIND_INDEX_PEPPER = b"GOV_REGISTRY_BLIND_INDEX_PEPPER_HMAC_v1"

# Derive 32-byte encryption key
_kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,
    salt=_KEY_SALT,
    iterations=100_000,
)
_ENCRYPTION_KEY = base64.urlsafe_b64encode(_kdf.derive(_REGISTRY_SECRET))
_cipher_suite = Fernet(_ENCRYPTION_KEY)


def encrypt_field(plaintext: Optional[str]) -> str:
    """
    Encrypt a sensitive string field into base64 ciphertext.
    Returns an encrypted string. If plaintext is None or empty, returns an encrypted empty string.
    """
    if plaintext is None:
        raw = b""
    else:
        raw = str(plaintext).encode("utf-8")
    return _cipher_suite.encrypt(raw).decode("utf-8")


def decrypt_field(ciphertext: Optional[str]) -> str:
    """
    Decrypt an encrypted ciphertext string back to plaintext.
    Returns empty string if decryption fails or field was empty.
    """
    if not ciphertext:
        return ""
    try:
        decrypted_bytes = _cipher_suite.decrypt(ciphertext.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except Exception:
        return ""


def normalize_doc_number(doc_number: str) -> str:
    """
    Standardize document numbers for deterministic blind indexing:
    uppercased, whitespace and common separators removed.
    """
    if not doc_number:
        return ""
    cleaned = re.sub(r"[\s\-_/.]+", "", str(doc_number).upper())
    return cleaned


def compute_blind_index(doc_type: str, doc_number: str) -> str:
    """
    Compute a deterministic HMAC-SHA256 blind index hash for search indexing.
    This allows exact-match O(1) SQL queries on encrypted rows without exposing
    the plaintext document number to database viewers.
    """
    normalized = normalize_doc_number(doc_number)
    key = _BLIND_INDEX_PEPPER + doc_type.lower().strip().encode("utf-8")
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
