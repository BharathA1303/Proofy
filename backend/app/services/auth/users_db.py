"""
backend/app/services/auth/users_db.py

Encrypted Meiyari Officer Accounts Database.
Stores registered officer accounts in a table completely separate from the
government registry tables (official_citizens / blacklisted_watchlist).

Zero plaintext sensitive data is saved to SQLite:
  - Names / emails / usernames: Fernet field encryption (reversible, needed for display)
  - Passwords: PBKDF2-HMAC-SHA256 salted hash (one-way, never reversible)
  - TOTP MFA secrets: Fernet field encryption (reversible, needed to verify codes)
Direct inspection of government_registry.db reveals no readable credentials.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from app.services.registry.db.crypto import compute_blind_index, decrypt_field, encrypt_field
from app.services.registry.db.password_hash import hash_password, verify_password

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "government_registry.db"


class MeiyariUsersDB:
    """Thread-safe SQLite manager for encrypted Meiyari officer accounts."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_table()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_table(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS meiyari_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    public_id TEXT NOT NULL UNIQUE,
                    username_hash TEXT NOT NULL UNIQUE,
                    email_hash TEXT NOT NULL UNIQUE,
                    full_name_encrypted TEXT NOT NULL,
                    username_encrypted TEXT NOT NULL,
                    email_encrypted TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    mfa_secret_encrypted TEXT NOT NULL,
                    role_encrypted TEXT NOT NULL,
                    station_encrypted TEXT NOT NULL,
                    clearance_level_encrypted TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_meiyari_users_username
                ON meiyari_users (username_hash);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_meiyari_users_email
                ON meiyari_users (email_hash);
            """)
            conn.commit()

    def _row_to_public_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Decrypt a row into the officer object shape the frontend expects. Never includes password/mfa secret."""
        return {
            "id": row["public_id"],
            "name": decrypt_field(row["full_name_encrypted"]),
            "username": decrypt_field(row["username_encrypted"]),
            "email": decrypt_field(row["email_encrypted"]),
            "role": decrypt_field(row["role_encrypted"]),
            "station": decrypt_field(row["station_encrypted"]),
            "clearanceLevel": decrypt_field(row["clearance_level_encrypted"]),
            "mfaEnabled": True,
        }

    def find_by_identifier(self, identifier: str) -> Optional[sqlite3.Row]:
        """Look up a raw row by username or email (case-insensitive, via blind index)."""
        clean = identifier.strip().lower()
        username_hash = compute_blind_index("meiyari_username", clean)
        email_hash = compute_blind_index("meiyari_email", clean)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM meiyari_users WHERE username_hash = ? OR email_hash = ? LIMIT 1",
                (username_hash, email_hash),
            )
            return cursor.fetchone()

    def create_user(
        self,
        public_id: str,
        full_name: str,
        username: str,
        email: str,
        plain_password: str,
        mfa_secret: str,
        role: str = "Verification Officer",
        station: str = "Terminal 3 · Checkpoint Gate 4",
        clearance_level: str = "Level 2 — Verification Officer",
    ) -> Dict[str, Any]:
        """Create a new officer account. Raises ValueError if username/email already exists."""
        clean_username = username.strip().lower()
        clean_email = email.strip().lower()

        if self.find_by_identifier(clean_username) or self.find_by_identifier(clean_email):
            raise ValueError("An account with this username or email already exists.")

        username_hash = compute_blind_index("meiyari_username", clean_username)
        email_hash = compute_blind_index("meiyari_email", clean_email)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO meiyari_users (
                    public_id, username_hash, email_hash, full_name_encrypted,
                    username_encrypted, email_encrypted, password_hash,
                    mfa_secret_encrypted, role_encrypted, station_encrypted,
                    clearance_level_encrypted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    public_id,
                    username_hash,
                    email_hash,
                    encrypt_field(full_name.strip()),
                    encrypt_field(clean_username),
                    encrypt_field(clean_email),
                    hash_password(plain_password),
                    encrypt_field(mfa_secret),
                    encrypt_field(role),
                    encrypt_field(station),
                    encrypt_field(clearance_level),
                ),
            )
            conn.commit()

        row = self.find_by_identifier(clean_username)
        return self._row_to_public_dict(row)

    def verify_credentials(self, identifier: str, plain_password: str) -> Optional[Dict[str, Any]]:
        """Verify username/email + password. Returns the public officer dict, or None if invalid."""
        row = self.find_by_identifier(identifier)
        if not row:
            return None
        if not verify_password(plain_password, row["password_hash"]):
            return None
        return self._row_to_public_dict(row)

    def get_mfa_secret(self, identifier: str) -> Optional[str]:
        """Decrypt and return the TOTP secret for a user, needed to verify a 6-digit code."""
        row = self.find_by_identifier(identifier)
        if not row:
            return None
        return decrypt_field(row["mfa_secret_encrypted"])

    def get_public_profile(self, identifier: str) -> Optional[Dict[str, Any]]:
        row = self.find_by_identifier(identifier)
        if not row:
            return None
        return self._row_to_public_dict(row)


# Global singleton instance
meiyari_users_db = MeiyariUsersDB()
