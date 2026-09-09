"""
backend/app/services/registry/db/registry_db.py

Government Registry SQLite Database Manager.
Stores authentic citizen credentials and blacklisted / watchlist records
in completely separate tables under strong AES encryption.

Zero plaintext sensitive data is saved to SQLite.
Direct inspection of government_registry.db reveals ONLY encrypted ciphertexts
and cryptographic blind-index HMAC hashes.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.registry.db.crypto import (
    compute_blind_index,
    decrypt_field,
    encrypt_field,
    normalize_doc_number,
)

logger = logging.getLogger(__name__)

# Default location for the government registry database file
DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "government_registry.db"


class GovernmentRegistryDB:
    """
    Thread-safe SQLite database manager for encrypted government records.
    Maintains strict separation between official registered citizens and watchlist entities.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        """Create separate encrypted tables and HMAC blind index search structures."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Authentic Official Citizens Registry
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS official_citizens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_type TEXT NOT NULL,
                    doc_number_hash TEXT NOT NULL,
                    full_name_encrypted TEXT NOT NULL,
                    doc_number_encrypted TEXT NOT NULL,
                    dob_encrypted TEXT NOT NULL,
                    status_encrypted TEXT NOT NULL,
                    authority_encrypted TEXT NOT NULL,
                    expiry_encrypted TEXT NOT NULL,
                    metadata_json_encrypted TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_official_lookup
                ON official_citizens (doc_type, doc_number_hash);
            """)

            # 2. Blacklisted / Watchlist Records (Strictly Isolated Table)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blacklisted_watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_type TEXT NOT NULL,
                    doc_number_hash TEXT NOT NULL,
                    full_name_encrypted TEXT NOT NULL,
                    doc_number_encrypted TEXT NOT NULL,
                    dob_encrypted TEXT NOT NULL,
                    status_encrypted TEXT NOT NULL,
                    authority_encrypted TEXT NOT NULL,
                    expiry_encrypted TEXT NOT NULL,
                    watchlist_reason_encrypted TEXT NOT NULL,
                    metadata_json_encrypted TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_blacklist_lookup
                ON blacklisted_watchlist (doc_type, doc_number_hash);
            """)

            conn.commit()

    def insert_official_record(
        self,
        doc_type: str,
        doc_number: str,
        full_name: str,
        dob: str,
        status: str = "ACTIVE",
        authority: str = "GOVERNMENT AUTHORITY",
        expiry: str = "2030-01-01",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert a normal verified citizen record with full field encryption."""
        canonical_type = doc_type.lower().strip()
        doc_hash = compute_blind_index(canonical_type, doc_number)
        meta_str = json.dumps(metadata or {})

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Remove any existing record for this document hash to allow clean re-seeding
            cursor.execute(
                "DELETE FROM official_citizens WHERE doc_type = ? AND doc_number_hash = ?",
                (canonical_type, doc_hash),
            )
            cursor.execute(
                """
                INSERT INTO official_citizens (
                    doc_type, doc_number_hash, full_name_encrypted, doc_number_encrypted,
                    dob_encrypted, status_encrypted, authority_encrypted, expiry_encrypted,
                    metadata_json_encrypted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    canonical_type,
                    doc_hash,
                    encrypt_field(full_name),
                    encrypt_field(doc_number),
                    encrypt_field(dob),
                    encrypt_field(status),
                    encrypt_field(authority),
                    encrypt_field(expiry),
                    encrypt_field(meta_str),
                ),
            )
            conn.commit()

    def insert_blacklisted_record(
        self,
        doc_type: str,
        doc_number: str,
        full_name: str,
        dob: str,
        watchlist_reason: str,
        status: str = "REVOKED",
        authority: str = "GOVERNMENT AUTHORITY",
        expiry: str = "2028-01-01",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert a blacklisted / watchlist entity into the isolated watchlist table."""
        canonical_type = doc_type.lower().strip()
        doc_hash = compute_blind_index(canonical_type, doc_number)
        meta_str = json.dumps(metadata or {})

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM blacklisted_watchlist WHERE doc_type = ? AND doc_number_hash = ?",
                (canonical_type, doc_hash),
            )
            cursor.execute(
                """
                INSERT INTO blacklisted_watchlist (
                    doc_type, doc_number_hash, full_name_encrypted, doc_number_encrypted,
                    dob_encrypted, status_encrypted, authority_encrypted, expiry_encrypted,
                    watchlist_reason_encrypted, metadata_json_encrypted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    canonical_type,
                    doc_hash,
                    encrypt_field(full_name),
                    encrypt_field(doc_number),
                    encrypt_field(dob),
                    encrypt_field(status),
                    encrypt_field(authority),
                    encrypt_field(expiry),
                    encrypt_field(watchlist_reason),
                    encrypt_field(meta_str),
                ),
            )
            conn.commit()

    def lookup_document(
        self,
        doc_type: str,
        doc_number: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Verify if a credential holder exists in the government registry database.
        Execution sequence:
          1. Checks the encrypted blacklisted table first.
          2. If not blacklisted, checks the encrypted official citizens table.
          3. Evaluates document normalization variations (spaces, hyphens, check digits).
        """
        canonical_type = doc_type.lower().strip()
        if not doc_number:
            return None

        # Build search candidates (raw, stripped, normalized, without trailing check digit)
        clean = normalize_doc_number(doc_number)
        candidates = [clean, doc_number.strip().upper()]

        # For passports: check digit often appends to 8-char number (e.g. Z12345671 -> Z1234567)
        if canonical_type == "passport" and len(clean) == 9:
            candidates.append(clean[:8])
        elif canonical_type == "passport" and len(clean) == 8:
            # Also search potential 9-char form
            for digit in "0123456789":
                candidates.append(clean + digit)

        # For driving licenses: handle state code with/without space
        if canonical_type in ("driving_license", "drivinglicense"):
            if clean.startswith("TN05") and len(clean) > 4:
                candidates.append(f"TN05 {clean[4:]}")
            if clean.startswith("DL04") and len(clean) > 4:
                candidates.append(f"DL-04{clean[4:]}")
            if clean.startswith("DL01") and len(clean) > 4:
                candidates.append(f"DL-01{clean[4:]}")

        # For border permits: handle hyphenated format
        if canonical_type in ("border_permit", "borderpermit"):
            if clean.startswith("BP") and "-" not in doc_number:
                # e.g. BP2026880011 -> BP-2026-880011
                if len(clean) == 12:
                    candidates.append(f"BP-{clean[2:6]}-{clean[6:]}")
                elif len(clean) == 10:
                    candidates.append(f"BP-{clean[2:6]}-{clean[6:]}")

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # ── 1. Check Blacklisted Watchlist Table ───────────────────────────
            for cand in candidates:
                cand_hash = compute_blind_index(canonical_type, cand)
                cursor.execute(
                    """
                    SELECT full_name_encrypted, doc_number_encrypted, dob_encrypted,
                           status_encrypted, authority_encrypted, expiry_encrypted,
                           watchlist_reason_encrypted, metadata_json_encrypted
                    FROM blacklisted_watchlist
                    WHERE doc_type = ? AND doc_number_hash = ?
                    LIMIT 1
                    """,
                    (canonical_type, cand_hash),
                )
                row = cursor.fetchone()
                if row:
                    meta_dec = decrypt_field(row["metadata_json_encrypted"])
                    meta_dict = json.loads(meta_dec) if meta_dec else {}
                    res = {
                        "document_number": decrypt_field(row["doc_number_encrypted"]) or cand,
                        "registry_document_status": decrypt_field(row["status_encrypted"]) or "REVOKED",
                        "name": decrypt_field(row["full_name_encrypted"]),
                        "date_of_birth": decrypt_field(row["dob_encrypted"]),
                        "expiry_date": decrypt_field(row["expiry_encrypted"]),
                        "issuing_authority": decrypt_field(row["authority_encrypted"]),
                        "is_blacklisted": True,
                        "watchlist_reason": decrypt_field(row["watchlist_reason_encrypted"]),
                    }
                    res.update(meta_dict)
                    return res

            # ── 2. Check Official Citizens Table ──────────────────────────────
            for cand in candidates:
                cand_hash = compute_blind_index(canonical_type, cand)
                cursor.execute(
                    """
                    SELECT full_name_encrypted, doc_number_encrypted, dob_encrypted,
                           status_encrypted, authority_encrypted, expiry_encrypted,
                           metadata_json_encrypted
                    FROM official_citizens
                    WHERE doc_type = ? AND doc_number_hash = ?
                    LIMIT 1
                    """,
                    (canonical_type, cand_hash),
                )
                row = cursor.fetchone()
                if row:
                    meta_dec = decrypt_field(row["metadata_json_encrypted"])
                    meta_dict = json.loads(meta_dec) if meta_dec else {}
                    res = {
                        "document_number": decrypt_field(row["doc_number_encrypted"]) or cand,
                        "registry_document_status": decrypt_field(row["status_encrypted"]) or "ACTIVE",
                        "name": decrypt_field(row["full_name_encrypted"]),
                        "date_of_birth": decrypt_field(row["dob_encrypted"]),
                        "expiry_date": decrypt_field(row["expiry_encrypted"]),
                        "issuing_authority": decrypt_field(row["authority_encrypted"]),
                        "is_blacklisted": False,
                        "watchlist_reason": None,
                    }
                    res.update(meta_dict)
                    return res

        return None

    def get_all_records_for_type(self, doc_type: str) -> Dict[str, Dict[str, Any]]:
        """
        Decrypt and return a memory mapping of all records for a document category.
        Used by compatibility proxies and legacy test suites.
        """
        canonical_type = doc_type.lower().strip()
        out: Dict[str, Dict[str, Any]] = {}

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Official citizens
            cursor.execute(
                """
                SELECT full_name_encrypted, doc_number_encrypted, dob_encrypted,
                       status_encrypted, authority_encrypted, expiry_encrypted,
                       metadata_json_encrypted
                FROM official_citizens WHERE doc_type = ?
                """,
                (canonical_type,),
            )
            for row in cursor.fetchall():
                doc_num = decrypt_field(row["doc_number_encrypted"])
                meta_dec = decrypt_field(row["metadata_json_encrypted"])
                meta_dict = json.loads(meta_dec) if meta_dec else {}
                rec = {
                    "document_number": doc_num,
                    "registry_document_status": decrypt_field(row["status_encrypted"]),
                    "name": decrypt_field(row["full_name_encrypted"]),
                    "date_of_birth": decrypt_field(row["dob_encrypted"]),
                    "expiry_date": decrypt_field(row["expiry_encrypted"]),
                    "issuing_authority": decrypt_field(row["authority_encrypted"]),
                }
                rec.update(meta_dict)
                if doc_num:
                    out[doc_num] = rec

            # Blacklist watchlist
            cursor.execute(
                """
                SELECT full_name_encrypted, doc_number_encrypted, dob_encrypted,
                       status_encrypted, authority_encrypted, expiry_encrypted,
                       watchlist_reason_encrypted, metadata_json_encrypted
                FROM blacklisted_watchlist WHERE doc_type = ?
                """,
                (canonical_type,),
            )
            for row in cursor.fetchall():
                doc_num = decrypt_field(row["doc_number_encrypted"])
                meta_dec = decrypt_field(row["metadata_json_encrypted"])
                meta_dict = json.loads(meta_dec) if meta_dec else {}
                rec = {
                    "document_number": doc_num,
                    "registry_document_status": decrypt_field(row["status_encrypted"]),
                    "name": decrypt_field(row["full_name_encrypted"]),
                    "date_of_birth": decrypt_field(row["dob_encrypted"]),
                    "expiry_date": decrypt_field(row["expiry_encrypted"]),
                    "issuing_authority": decrypt_field(row["authority_encrypted"]),
                    "is_blacklisted": True,
                    "watchlist_reason": decrypt_field(row["watchlist_reason_encrypted"]),
                }
                rec.update(meta_dict)
                if doc_num:
                    out[doc_num] = rec

        return out

    def delete_all_records_for_type(self, doc_type: str) -> int:
        """
        Delete ALL records (official + blacklisted) for a given document type.
        Used during DB migration to purge legacy or renamed type records.
        Returns total rows deleted.
        """
        canonical_type = doc_type.lower().strip()
        total_deleted = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM official_citizens WHERE doc_type = ?", (canonical_type,))
            total_deleted += cursor.rowcount
            cursor.execute("DELETE FROM blacklisted_watchlist WHERE doc_type = ?", (canonical_type,))
            total_deleted += cursor.rowcount
            conn.commit()
        if total_deleted > 0:
            logger.info("Purged %d legacy records for doc_type='%s'", total_deleted, canonical_type)
        return total_deleted

    def seed_initial_records(self) -> None:
        """
        Populates official citizens and blacklisted entities under full encryption.
        Called once on system initialization.
        """
        logger.info("Initializing and seeding Encrypted Government Registry Database...")

        # ── 1. PASSPORTS ───────────────────────────────────────────────────────
        # Official Genuine
        self.insert_official_record(
            doc_type="passport",
            doc_number="Z1234567",
            full_name="AARAV SHARMA",
            dob="1990-05-15",
            status="ACTIVE",
            authority="REGIONAL PASSPORT OFFICE DELHI",
            expiry="2030-01-09",
            metadata={"nationality": "IND", "gender": "M"},
        )
        self.insert_official_record(
            doc_type="passport",
            doc_number="Z12345671",  # MRZ check-digit variant
            full_name="AARAV SHARMA",
            dob="1990-05-15",
            status="ACTIVE",
            authority="REGIONAL PASSPORT OFFICE DELHI",
            expiry="2030-01-09",
            metadata={"nationality": "IND", "gender": "M"},
        )
        self.insert_official_record(
            doc_type="passport",
            doc_number="T9876543",
            full_name="TEST USER",
            dob="1985-06-15",
            status="ACTIVE",
            authority="SYNTHETIC TEST AUTHORITY",
            expiry="2029-12-31",
            metadata={"nationality": "IND", "gender": "M"},
        )
        self.insert_official_record(
            doc_type="passport",
            doc_number="TESTPASS001",
            full_name="TEST USER ONE",
            dob="1990-01-01",
            status="ACTIVE",
            authority="DEVELOPMENT MOCK AUTHORITY",
            expiry="2030-01-01",
            metadata={"nationality": "IND", "gender": "M"},
        )
        self.insert_official_record(
            doc_type="passport",
            doc_number="TESTEXPIRED001",
            full_name="TEST EXPIRED",
            dob="1985-06-15",
            status="EXPIRED",
            authority="DEVELOPMENT MOCK AUTHORITY",
            expiry="2020-01-01",
            metadata={"nationality": "IND", "gender": "F"},
        )
        self.insert_official_record(
            doc_type="passport",
            doc_number="TESTMISMATCH001",
            full_name="DIFFERENT NAME ENTIRELY",
            dob="1984-06-15",
            status="ACTIVE",
            authority="DEVELOPMENT MOCK AUTHORITY",
            expiry="2029-01-01",
            metadata={"nationality": "USA", "gender": "M"},
        )
        self.insert_official_record(
            doc_type="passport",
            doc_number="TESTAMBIGUOUS001",
            full_name="TEST AMBIGUOUS",
            dob="1992-07-04",
            status="ACTIVE",
            authority="DEVELOPMENT MOCK AUTHORITY",
            expiry="2032-07-04",
            metadata={"nationality": "IND", "gender": "M"},
        )

        # Blacklisted Watchlist Passports
        self.insert_blacklisted_record(
            doc_type="passport",
            doc_number="Z7654321",
            full_name="VIKRAM MALHOTRA",
            dob="1982-11-20",
            status="REVOKED",
            authority="REGIONAL PASSPORT OFFICE MUMBAI",
            expiry="2028-04-11",
            watchlist_reason="Active Red Notice: Financial forgery and cross-border identity fraud watchlist hit.",
            metadata={"nationality": "IND", "gender": "M"},
        )
        self.insert_blacklisted_record(
            doc_type="passport",
            doc_number="Z76543219",  # MRZ check digit variant
            full_name="VIKRAM MALHOTRA",
            dob="1982-11-20",
            status="REVOKED",
            authority="REGIONAL PASSPORT OFFICE MUMBAI",
            expiry="2028-04-11",
            watchlist_reason="Active Red Notice: Financial forgery and cross-border identity fraud watchlist hit.",
            metadata={"nationality": "IND", "gender": "M"},
        )
        self.insert_blacklisted_record(
            doc_type="passport",
            doc_number="TESTREVOKED001",
            full_name="TEST REVOKED",
            dob="1975-03-20",
            status="REVOKED",
            authority="DEVELOPMENT MOCK AUTHORITY",
            expiry="2028-03-20",
            watchlist_reason="Document officially revoked by immigration authority.",
            metadata={"nationality": "IND", "gender": "M"},
        )
        self.insert_blacklisted_record(
            doc_type="passport",
            doc_number="TESTSUSPENDED001",
            full_name="TEST SUSPENDED",
            dob="1980-12-10",
            status="SUSPENDED",
            authority="DEVELOPMENT MOCK AUTHORITY",
            expiry="2031-12-10",
            watchlist_reason="Document administrative suspension pending investigation.",
            metadata={"nationality": "IND", "gender": "F"},
        )

        # ── 2. DRIVING LICENSES ───────────────────────────────────────────────
        # Official Genuine (Bharath A)
        self.insert_official_record(
            doc_type="driving_license",
            doc_number="TN0520250014128",
            full_name="BHARATH A",
            dob="2007-03-13",
            status="ACTIVE",
            authority="GOVERNMENT OF TAMIL NADU",
            expiry="2047-03-12",
            metadata={"blood_group": "A1B+", "vehicle_classes": "LMV, MCWG", "state": "Tamil Nadu"},
        )
        self.insert_official_record(
            doc_type="driving_license",
            doc_number="TN05 20250014128",
            full_name="BHARATH A",
            dob="2007-03-13",
            status="ACTIVE",
            authority="GOVERNMENT OF TAMIL NADU",
            expiry="2047-03-12",
            metadata={"blood_group": "A1B+", "vehicle_classes": "LMV, MCWG", "state": "Tamil Nadu"},
        )
        # Official Genuine (Priya Sundar)
        self.insert_official_record(
            doc_type="driving_license",
            doc_number="DL-0420230012345",
            full_name="PRIYA SUNDAR",
            dob="1994-03-22",
            status="ACTIVE",
            authority="RTO DELHI CENTRAL",
            expiry="2034-03-21",
            metadata={"blood_group": "B+", "vehicle_classes": "MCWG, LMV", "state": "Delhi"},
        )
        self.insert_official_record(
            doc_type="driving_license",
            doc_number="DL0420230012345",
            full_name="PRIYA SUNDAR",
            dob="1994-03-22",
            status="ACTIVE",
            authority="RTO DELHI CENTRAL",
            expiry="2034-03-21",
            metadata={"blood_group": "B+", "vehicle_classes": "MCWG, LMV", "state": "Delhi"},
        )
        self.insert_official_record(
            doc_type="driving_license",
            doc_number="TESTDL001",
            full_name="RAHUL SHARMA",
            dob="1992-05-15",
            status="ACTIVE",
            authority="RTO DELHI",
            expiry="2035-05-14",
            metadata={"blood_group": "O+", "vehicle_classes": "LMV, MCWG", "state": "Delhi"},
        )
        self.insert_official_record(
            doc_type="driving_license",
            doc_number="TESTDLEXPIRED001",
            full_name="TEST EXPIRED",
            dob="1980-01-01",
            status="EXPIRED",
            authority="RTO DELHI",
            expiry="2020-01-01",
        )
        self.insert_official_record(
            doc_type="driving_license",
            doc_number="TESTDLMISMATCH001",
            full_name="MISMATCHED NAME",
            dob="1970-01-01",
            status="ACTIVE",
            authority="RTO DELHI",
            expiry="2035-01-01",
        )

        # Blacklisted Watchlist DL (Kabir Mehta)
        self.insert_blacklisted_record(
            doc_type="driving_license",
            doc_number="DL-0120180099887",
            full_name="KABIR MEHTA",
            dob="1986-07-14",
            status="REVOKED",
            authority="RTO MUMBAI WEST",
            expiry="2038-07-13",
            watchlist_reason="License permanently revoked following hit-and-run felony & fabricated address records.",
            metadata={"blood_group": "O+", "vehicle_classes": "MCWG, LMV"},
        )
        self.insert_blacklisted_record(
            doc_type="driving_license",
            doc_number="DL0120180099887",
            full_name="KABIR MEHTA",
            dob="1986-07-14",
            status="REVOKED",
            authority="RTO MUMBAI WEST",
            expiry="2038-07-13",
            watchlist_reason="License permanently revoked following hit-and-run felony & fabricated address records.",
            metadata={"blood_group": "O+", "vehicle_classes": "MCWG, LMV"},
        )
        self.insert_blacklisted_record(
            doc_type="driving_license",
            doc_number="TESTDLREVOKED001",
            full_name="TEST REVOKED",
            dob="1975-06-15",
            status="REVOKED",
            authority="RTO MUMBAI",
            expiry="2030-01-01",
            watchlist_reason="Fraudulent issuance revocation.",
        )
        self.insert_blacklisted_record(
            doc_type="driving_license",
            doc_number="TESTDLSUSPENDED001",
            full_name="TEST SUSPENDED",
            dob="1988-10-20",
            status="SUSPENDED",
            authority="RTO BANGALORE",
            expiry="2032-05-15",
            watchlist_reason="Judicial suspension.",
        )

        # ── 3. AADHAAR (UIDAI) ───────────────────────────────────────────────
        # Purge any old 'national_id' rows from previous schema
        self.delete_all_records_for_type("national_id")

        # Official Genuine — Sneha Patel (migrated + kept same Aadhaar number)
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="847291038473",
            full_name="SNEHA PATEL",
            dob="1992-09-18",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "FEMALE", "address": "42 BAKER STREET, NEW DELHI 110001"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="8472 9103 8473",
            full_name="SNEHA PATEL",
            dob="1992-09-18",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "FEMALE", "address": "42 BAKER STREET, NEW DELHI 110001"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="XXXX XXXX 8473",
            full_name="SNEHA PATEL",
            dob="1992-09-18",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "FEMALE", "address": "42 BAKER STREET, NEW DELHI 110001"},
        )

        # Official Genuine — Bharath A (Real Test Identity)
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="769766721283",
            full_name="BHARATH A",
            dob="2007-03-13",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "MALE"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="7697 6672 1283",
            full_name="BHARATH A",
            dob="2007-03-13",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "MALE"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="XXXX XXXX 1283",
            full_name="BHARATH A",
            dob="2007-03-13",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "MALE"},
        )

        # Official Genuine — Sudha A (Real Test Identity)
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="366347670846",
            full_name="SUDHA A",
            dob="1985-01-01",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "FEMALE", "address": "18/12 Shirdi Ananda Flat, Mukunta Ramanujam St, Perambur, Chennai 600011"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="3663 4767 0846",
            full_name="SUDHA A",
            dob="1985-01-01",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "FEMALE", "address": "18/12 Shirdi Ananda Flat, Mukunta Ramanujam St, Perambur, Chennai 600011"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="XXXX XXXX 0846",
            full_name="SUDHA A",
            dob="1985-01-01",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "FEMALE", "address": "18/12 Shirdi Ananda Flat, Mukunta Ramanujam St, Perambur, Chennai 600011"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="987654321098",
            full_name="RAHUL SHARMA",
            dob="1992-05-15",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "MALE"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="TESTAADHAAR001",
            full_name="RAHUL SHARMA",
            dob="1992-05-15",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "MALE"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="TESTAADHAAREXPIRED001",
            full_name="TEST EXPIRED",
            dob="1980-01-01",
            status="EXPIRED",
            authority="Unique Identification Authority of India",
            expiry="2010-01-01",
            metadata={"gender": "MALE"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="TESTAADHAARMISMATCH001",
            full_name="VIKRAM SINGH",
            dob="1965-03-12",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "MALE"},
        )

        # Blacklisted — Tariq Ahmed (migrated)
        self.insert_blacklisted_record(
            doc_type="aadhaar",
            doc_number="654123987101",
            full_name="TARIQ AHMED",
            dob="1980-04-05",
            status="REVOKED",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            watchlist_reason="De-duplicated biometric suspension: duplicate Aadhaar enrolment & security flagged.",
            metadata={"gender": "MALE", "address": "15 MARINE DRIVE, MUMBAI 400020"},
        )
        self.insert_blacklisted_record(
            doc_type="aadhaar",
            doc_number="6541 2398 7101",
            full_name="TARIQ AHMED",
            dob="1980-04-05",
            status="REVOKED",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            watchlist_reason="De-duplicated biometric suspension: duplicate Aadhaar enrolment & security flagged.",
            metadata={"gender": "MALE", "address": "15 MARINE DRIVE, MUMBAI 400020"},
        )
        self.insert_blacklisted_record(
            doc_type="aadhaar",
            doc_number="XXXX XXXX 7101",
            full_name="TARIQ AHMED",
            dob="1980-04-05",
            status="REVOKED",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            watchlist_reason="De-duplicated biometric suspension: duplicate Aadhaar enrolment & security flagged.",
            metadata={"gender": "MALE", "address": "15 MARINE DRIVE, MUMBAI 400020"},
        )
        self.insert_blacklisted_record(
            doc_type="aadhaar",
            doc_number="TESTAADHAARREVOKED001",
            full_name="TEST REVOKED",
            dob="1975-06-15",
            status="REVOKED",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            watchlist_reason="National security flag: Aadhaar revoked.",
        )
        self.insert_blacklisted_record(
            doc_type="aadhaar",
            doc_number="TESTAADHAARSUSPENDED001",
            full_name="TEST SUSPENDED",
            dob="1988-10-20",
            status="SUSPENDED",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            watchlist_reason="Identity theft investigation: Aadhaar suspended.",
        )

        # Legacy TESTNID aliases for backward compatibility
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="TESTNID001",
            full_name="RAHUL SHARMA",
            dob="1992-05-15",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "MALE"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="TESTNIDEXPIRED001",
            full_name="TEST EXPIRED",
            dob="1980-01-01",
            status="EXPIRED",
            authority="Unique Identification Authority of India",
            expiry="2010-01-01",
            metadata={"gender": "MALE"},
        )
        self.insert_official_record(
            doc_type="aadhaar",
            doc_number="TESTNIDMISMATCH001",
            full_name="VIKRAM SINGH",
            dob="1965-03-12",
            status="ACTIVE",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            metadata={"gender": "MALE"},
        )
        self.insert_blacklisted_record(
            doc_type="aadhaar",
            doc_number="TESTNIDREVOKED001",
            full_name="TEST REVOKED",
            dob="1975-06-15",
            status="REVOKED",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            watchlist_reason="National security flag: Aadhaar revoked.",
        )
        self.insert_blacklisted_record(
            doc_type="aadhaar",
            doc_number="TESTNIDSUSPENDED001",
            full_name="TEST SUSPENDED",
            dob="1988-10-20",
            status="SUSPENDED",
            authority="Unique Identification Authority of India",
            expiry="2099-12-31",
            watchlist_reason="Identity theft investigation: Aadhaar suspended.",
        )

        # ── 4. VOTER ID / EPIC (Election Commission of India) ─────────────────
        # Official Genuine
        self.insert_official_record(
            doc_type="voter_id",
            doc_number="ABC1234567",
            full_name="PRIYA KRISHNAMURTHY",
            dob="1988-07-22",
            status="ACTIVE",
            authority="Election Commission of India",
            expiry="2099-12-31",
            metadata={"gender": "FEMALE", "constituency": "CHENNAI NORTH", "state": "Tamil Nadu"},
        )
        self.insert_official_record(
            doc_type="voter_id",
            doc_number="MNP9876543",
            full_name="ARJUN VENKATESH",
            dob="1985-03-14",
            status="ACTIVE",
            authority="Election Commission of India",
            expiry="2099-12-31",
            metadata={"gender": "MALE", "constituency": "DELHI SOUTH", "state": "Delhi"},
        )
        self.insert_official_record(
            doc_type="voter_id",
            doc_number="TESTVOTERID001",
            full_name="MEERA PILLAI",
            dob="1990-11-30",
            status="ACTIVE",
            authority="Election Commission of India",
            expiry="2099-12-31",
            metadata={"gender": "FEMALE", "constituency": "ERNAKULAM", "state": "Kerala"},
        )
        self.insert_official_record(
            doc_type="voter_id",
            doc_number="TESTVOTEREXPIRED001",
            full_name="TEST EXPIRED VOTER",
            dob="1965-01-01",
            status="EXPIRED",
            authority="Election Commission of India",
            expiry="2015-01-01",
        )
        self.insert_official_record(
            doc_type="voter_id",
            doc_number="TESTVOTEMISMATCH001",
            full_name="DIFFERENT VOTER NAME",
            dob="1975-06-15",
            status="ACTIVE",
            authority="Election Commission of India",
            expiry="2099-12-31",
        )

        # Blacklisted Voter ID
        self.insert_blacklisted_record(
            doc_type="voter_id",
            doc_number="XYZ7654321",
            full_name="RAHUL DEVANAND",
            dob="1977-09-05",
            status="REVOKED",
            authority="Election Commission of India",
            expiry="2099-12-31",
            watchlist_reason="Voter ID revoked: electoral fraud and duplicate registration detected by ECI.",
            metadata={"gender": "MALE", "constituency": "VARANASI WEST", "state": "Uttar Pradesh"},
        )
        self.insert_blacklisted_record(
            doc_type="voter_id",
            doc_number="TESTVOTERREVOKED001",
            full_name="TEST REVOKED VOTER",
            dob="1975-06-15",
            status="REVOKED",
            authority="Election Commission of India",
            expiry="2099-12-31",
            watchlist_reason="Voter ID revoked by election authorities.",
        )
        self.insert_blacklisted_record(
            doc_type="voter_id",
            doc_number="TESTVOTERSUSPENDED001",
            full_name="TEST SUSPENDED VOTER",
            dob="1980-10-20",
            status="SUSPENDED",
            authority="Election Commission of India",
            expiry="2099-12-31",
            watchlist_reason="Voter ID suspended pending constituency verification.",
        )

        # ── 5. PAN CARD (Income Tax Department of India) ──────────────────────
        # Official Genuine
        self.insert_official_record(
            doc_type="pan_card",
            doc_number="AABCP1234C",
            full_name="KAVITHA PRABHAKAR",
            dob="1983-04-12",
            status="ACTIVE",
            authority="Income Tax Department, Government of India",
            expiry="2099-12-31",
            metadata={"taxpayer_category": "Individual"},
        )
        self.insert_official_record(
            doc_type="pan_card",
            doc_number="BBBPK5678D",
            full_name="SUNDAR KRISHNAN",
            dob="1979-08-25",
            status="ACTIVE",
            authority="Income Tax Department, Government of India",
            expiry="2099-12-31",
            metadata={"taxpayer_category": "Individual"},
        )
        self.insert_official_record(
            doc_type="pan_card",
            doc_number="TESTPAN0001A",
            full_name="RAMESH BABU",
            dob="1975-12-01",
            status="ACTIVE",
            authority="Income Tax Department, Government of India",
            expiry="2099-12-31",
            metadata={"taxpayer_category": "Individual"},
        )
        self.insert_official_record(
            doc_type="pan_card",
            doc_number="TESTPANEXPIRED001",
            full_name="TEST EXPIRED PAN",
            dob="1960-01-01",
            status="EXPIRED",
            authority="Income Tax Department, Government of India",
            expiry="2010-01-01",
        )
        self.insert_official_record(
            doc_type="pan_card",
            doc_number="TESTPANMISMATCH001",
            full_name="DIFFERENT PAN HOLDER",
            dob="1970-03-15",
            status="ACTIVE",
            authority="Income Tax Department, Government of India",
            expiry="2099-12-31",
        )

        # Blacklisted PAN Card
        self.insert_blacklisted_record(
            doc_type="pan_card",
            doc_number="AAAFT9999Z",
            full_name="SURESH FRAUDWALA",
            dob="1972-06-10",
            status="REVOKED",
            authority="Income Tax Department, Government of India",
            expiry="2099-12-31",
            watchlist_reason="PAN Card revoked: tax evasion fraud & identity impersonation flagged by Income Tax Department.",
            metadata={"taxpayer_category": "Individual"},
        )
        self.insert_blacklisted_record(
            doc_type="pan_card",
            doc_number="TESTPANREVOKED001",
            full_name="TEST REVOKED PAN",
            dob="1975-06-15",
            status="REVOKED",
            authority="Income Tax Department, Government of India",
            expiry="2099-12-31",
            watchlist_reason="PAN Card revoked by Income Tax Department.",
        )
        self.insert_blacklisted_record(
            doc_type="pan_card",
            doc_number="TESTPANSUSPENDED001",
            full_name="TEST SUSPENDED PAN",
            dob="1982-09-12",
            status="SUSPENDED",
            authority="Income Tax Department, Government of India",
            expiry="2099-12-31",
            watchlist_reason="PAN Card suspended pending tax fraud investigation.",
        )

        # ── 6. ENTRY VISAS ────────────────────────────────────────────────────
        # Official Genuine (Aarav Sharma / Elena Rostova)
        self.insert_official_record(
            doc_type="visa",
            doc_number="V1002003",
            full_name="AARAV SHARMA",
            dob="1990-05-15",
            status="ACTIVE",
            authority="CONSULAR SECTION DELHI",
            expiry="2028-01-31",
            metadata={
                "nationality": "IND",
                "gender": "M",
                "passport_number": "Z1234567",
                "visa_type": "BUSINESS",
            },
        )
        self.insert_official_record(
            doc_type="visa",
            doc_number="V1002002",
            full_name="ELENA ROSTOVA",
            dob="1991-10-12",
            status="ACTIVE",
            authority="CONSULAR POST DELHI",
            expiry="2027-10-11",
            metadata={
                "nationality": "RUS",
                "gender": "F",
                "passport_number": "Z1234567",
                "visa_type": "TOURIST",
                "entries": "M",
            },
        )
        self.insert_official_record(
            doc_type="visa",
            doc_number="V1002001",
            full_name="AARAV SHARMA",
            dob="1990-05-15",
            status="ACTIVE",
            authority="CONSULAR POST DELHI",
            expiry="2028-01-01",
            metadata={
                "nationality": "IND",
                "gender": "M",
                "passport_number": "Z1234567",
                "visa_type": "TOURIST",
            },
        )
        self.insert_official_record(
            doc_type="visa",
            doc_number="TESTVISA001",
            full_name="SARAH CONNOR",
            dob="1985-05-12",
            status="ACTIVE",
            authority="EMBASSY LONDON",
            expiry="2033-01-15",
            metadata={
                "nationality": "USA",
                "gender": "F",
                "passport_number": "P9876543",
                "visa_type": "B1/B2",
            },
        )
        self.insert_official_record(
            doc_type="visa",
            doc_number="TESTVISAEXPIRED001",
            full_name="SARAH CONNOR",
            dob="1985-05-12",
            status="EXPIRED",
            authority="EMBASSY LONDON",
            expiry="2020-01-01",
            metadata={
                "nationality": "USA",
                "gender": "F",
                "passport_number": "P9876543",
                "visa_type": "B1/B2",
            },
        )
        self.insert_official_record(
            doc_type="visa",
            doc_number="TESTVISAMISMATCH001",
            full_name="GENUINE VISA HOLDER",
            dob="1985-05-12",
            status="ACTIVE",
            authority="EMBASSY LONDON",
            expiry="2033-01-15",
            metadata={
                "nationality": "USA",
                "gender": "F",
                "passport_number": "P9876543",
                "visa_type": "B1/B2",
            },
        )

        # Blacklisted Watchlist Visa (Vikram Malhotra / Chen Wei)
        self.insert_blacklisted_record(
            doc_type="visa",
            doc_number="V7008009",
            full_name="VIKRAM MALHOTRA",
            dob="1982-11-20",
            status="REVOKED",
            authority="CONSULAR SECTION MUMBAI",
            expiry="2027-05-09",
            watchlist_reason="Consular visa revoked: international red-alert watch list and security interdiction.",
            metadata={
                "nationality": "IND",
                "gender": "M",
                "passport_number": "Z7654321",
                "visa_type": "TOURIST",
            },
        )
        self.insert_blacklisted_record(
            doc_type="visa",
            doc_number="V7008001",
            full_name="CHEN WEI",
            dob="1978-03-22",
            status="REVOKED",
            authority="CONSULAR SECTION BEIJING",
            expiry="2027-05-09",
            watchlist_reason="Consular visa revoked: watchlist hit.",
            metadata={"nationality": "CHN", "gender": "M", "passport_number": "Z7654321"},
        )
        self.insert_blacklisted_record(
            doc_type="visa",
            doc_number="TESTVISAREVOKED001",
            full_name="SARAH CONNOR",
            dob="1985-05-12",
            status="REVOKED",
            authority="EMBASSY LONDON",
            metadata={"nationality": "USA", "gender": "F"},
            watchlist_reason="Consular visa revoked: compliance alert.",
        )
        self.insert_blacklisted_record(
            doc_type="visa",
            doc_number="TESTVISASUSPENDED001",
            full_name="SARAH CONNOR",
            dob="1985-05-12",
            status="SUSPENDED",
            authority="EMBASSY LONDON",
            metadata={"nationality": "USA", "gender": "F"},
            watchlist_reason="Consular visa suspended pending background adjudication.",
        )

        # ── 5. BORDER PERMITS ─────────────────────────────────────────────────
        # Official Genuine (Elena Rostova / Arjun Nair)
        self.insert_official_record(
            doc_type="border_permit",
            doc_number="BP-2026-880011",
            full_name="ELENA ROSTOVA",
            dob="1991-10-12",
            status="ACTIVE",
            authority="BORDER IMMIGRATION & LABOUR AUTHORITY",
            expiry="2026-12-31",
            metadata={"passport_number": "Z1234567", "port_of_entry": "NORTH GATE TERMINAL"},
        )
        self.insert_official_record(
            doc_type="border_permit",
            doc_number="BP2026880011",
            full_name="ELENA ROSTOVA",
            dob="1991-10-12",
            status="ACTIVE",
            authority="BORDER IMMIGRATION & LABOUR AUTHORITY",
            expiry="2026-12-31",
            metadata={"passport_number": "Z1234567", "port_of_entry": "NORTH GATE TERMINAL"},
        )
        self.insert_official_record(
            doc_type="border_permit",
            doc_number="BP2026112233",
            full_name="ARJUN NAIR",
            dob="1994-08-15",
            status="ACTIVE",
            authority="BORDER IMMIGRATION & LABOUR AUTHORITY",
            expiry="2026-12-31",
            metadata={"passport_number": "Z1234567"},
        )
        self.insert_official_record(
            doc_type="border_permit",
            doc_number="BP-2026-112233",
            full_name="ARJUN NAIR",
            dob="1994-08-15",
            status="ACTIVE",
            authority="BORDER IMMIGRATION & LABOUR AUTHORITY",
            expiry="2026-12-31",
            metadata={"passport_number": "Z1234567"},
        )
        self.insert_official_record(
            doc_type="border_permit",
            doc_number="BP2026000123",
            full_name="ALEX DUPONT",
            dob="1990-08-12",
            status="ACTIVE",
            authority="Border Management Authority",
            expiry="2026-12-31",
            metadata={"passport_number": "P1234567"},
        )
        self.insert_official_record(
            doc_type="border_permit",
            doc_number="TESTBP001",
            full_name="ALEX DUPONT",
            dob="1990-08-12",
            status="ACTIVE",
            authority="Border Management Authority",
            expiry="2026-12-31",
            metadata={"passport_number": "P1234567"},
        )
        self.insert_official_record(
            doc_type="border_permit",
            doc_number="TESTBPEXPIRED001",
            full_name="TEST EXPIRED",
            dob="1980-01-01",
            status="EXPIRED",
            authority="IMMIGRATION CONTROL DELHI",
            expiry="2020-01-01",
            metadata={"border_zone": "NORTHERN-ZONE", "port_of_entry": "DELHI BORDER"},
        )
        self.insert_official_record(
            doc_type="border_permit",
            doc_number="TESTBPMISMATCH001",
            full_name="MARCUS VANCE",
            dob="1985-01-01",
            status="ACTIVE",
            authority="IMMIGRATION CONTROL DELHI",
            expiry="2026-12-31",
            metadata={"border_zone": "NORTHERN-ZONE", "port_of_entry": "DELHI BORDER"},
        )

        # Blacklisted Watchlist Border Permit (Marcus Vance / David Kim)
        self.insert_blacklisted_record(
            doc_type="border_permit",
            doc_number="BP-2025-443322",
            full_name="MARCUS VANCE",
            dob="1983-06-20",
            status="REVOKED",
            authority="BORDER IMMIGRATION & LABOUR AUTHORITY",
            expiry="2026-06-01",
            watchlist_reason="Permit revoked on border watchlist: illicit transit and contraband smuggling alert.",
            metadata={"passport_number": "Z7654321"},
        )
        self.insert_blacklisted_record(
            doc_type="border_permit",
            doc_number="BP2025443322",
            full_name="MARCUS VANCE",
            dob="1983-06-20",
            status="REVOKED",
            authority="BORDER IMMIGRATION & LABOUR AUTHORITY",
            expiry="2026-06-01",
            watchlist_reason="Permit revoked on border watchlist: illicit transit and contraband smuggling alert.",
            metadata={"passport_number": "Z7654321"},
        )
        self.insert_blacklisted_record(
            doc_type="border_permit",
            doc_number="BP2025998877",
            full_name="DAVID KIM",
            dob="1987-03-25",
            status="REVOKED",
            authority="BORDER IMMIGRATION & LABOUR AUTHORITY",
            expiry="2026-06-01",
            watchlist_reason="Watchlist hit: revoked work credential.",
            metadata={"passport_number": "Z7654321"},
        )
        self.insert_blacklisted_record(
            doc_type="border_permit",
            doc_number="BP-2025-998877",
            full_name="DAVID KIM",
            dob="1987-03-25",
            status="REVOKED",
            authority="BORDER IMMIGRATION & LABOUR AUTHORITY",
            expiry="2026-06-01",
            watchlist_reason="Watchlist hit: revoked work credential.",
            metadata={"passport_number": "Z7654321"},
        )
        self.insert_blacklisted_record(
            doc_type="border_permit",
            doc_number="TESTBPREVOKED001",
            full_name="TEST REVOKED",
            dob="1985-01-01",
            status="REVOKED",
            authority="IMMIGRATION CONTROL DELHI",
            expiry="2026-12-31",
            watchlist_reason="Revoked by border immigration authority.",
        )
        self.insert_blacklisted_record(
            doc_type="border_permit",
            doc_number="TESTBPSUSPENDED001",
            full_name="TEST SUSPENDED",
            dob="1985-01-01",
            status="SUSPENDED",
            authority="IMMIGRATION CONTROL DELHI",
            expiry="2026-12-31",
            watchlist_reason="Suspended pending judicial investigation.",
        )

        logger.info("Encrypted Government Registry Database seeded successfully.")


# Global singleton instance
government_registry_db = GovernmentRegistryDB()
government_registry_db.seed_initial_records()
