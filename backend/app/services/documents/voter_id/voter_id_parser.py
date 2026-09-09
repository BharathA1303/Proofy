"""
backend/app/services/documents/voter_id/voter_id_parser.py

Voter ID / EPIC card field extraction from raw OCR regions.
Indian Electors Photo Identity Card issued by the Election Commission of India.

EPIC number format: 3 uppercase letters + 7 digits (e.g. ABC1234567).
Extracts: EPIC number, name, father's name, DOB/age, gender, constituency,
          part number, serial number, issuing state, issuing authority.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.ocr import OCRRegionRaw

logger = logging.getLogger(__name__)

# EPIC number pattern: exactly 3 uppercase letters followed by 7 digits
EPIC_PATTERN = re.compile(r"\b([A-Z]{3}[0-9]{7})\b")

# Header noise to exclude from name extraction
_EPIC_NOISE_TOKENS = (
    "ELECTION", "COMMISSION", "INDIA", "ELECTORS", "PHOTO",
    "IDENTITY", "CARD", "VOTER", "EPIC", "GOVERNMENT", "BHARAT",
    "ELECTOR", "CONSTITUENCY", "PART", "SERIAL", "STATE",
)


@dataclass
class VoterIdField:
    """A single parsed Voter ID field with provenance."""
    value: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[List[List[int]]] = None
    raw: Optional[str] = None


@dataclass
class ParsedVoterIdData:
    """Structured fields extracted from a Voter ID / EPIC card."""
    epic_number: VoterIdField = field(default_factory=VoterIdField)
    docNumber: VoterIdField = field(default_factory=VoterIdField)   # Canonical alias
    name: VoterIdField = field(default_factory=VoterIdField)
    father_name: VoterIdField = field(default_factory=VoterIdField)
    dob: VoterIdField = field(default_factory=VoterIdField)
    age: VoterIdField = field(default_factory=VoterIdField)
    gender: VoterIdField = field(default_factory=VoterIdField)
    constituency: VoterIdField = field(default_factory=VoterIdField)
    part_number: VoterIdField = field(default_factory=VoterIdField)
    serial_number: VoterIdField = field(default_factory=VoterIdField)
    issuing_authority: VoterIdField = field(default_factory=VoterIdField)
    issuing_state: VoterIdField = field(default_factory=VoterIdField)
    unsupported_layout: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "docNumber": self.docNumber.value or self.epic_number.value,
            "document_number": self.docNumber.value or self.epic_number.value,
            "epic_number": self.epic_number.value,
            "epicNumber": self.epic_number.value,
            "name": self.name.value,
            "father_name": self.father_name.value,
            "fatherName": self.father_name.value,
            "dob": self.dob.value,
            "date_of_birth": self.dob.value,
            "age": self.age.value,
            "gender": self.gender.value,
            "constituency": self.constituency.value,
            "part_number": self.part_number.value,
            "serial_number": self.serial_number.value,
            "issuing_authority": self.issuing_authority.value,
            "authority": self.issuing_authority.value,
            "issuing_state": self.issuing_state.value,
            "state": self.issuing_state.value,
        }


def normalize_epic_number(raw: Optional[str]) -> Optional[str]:
    """Normalize an EPIC number to 10-char uppercase (3 letters + 7 digits)."""
    if not raw:
        return None
    clean = re.sub(r"[\s\-]", "", raw.strip().upper())
    m = EPIC_PATTERN.search(clean)
    if m:
        return m.group(1)
    return None


def parse_voter_id(
    regions: List[OCRRegionRaw],
    raw_qr_payload: Optional[str] = None,
) -> ParsedVoterIdData:
    """
    Extract structured fields from OCR regions on a Voter ID / EPIC card image.
    """
    result = ParsedVoterIdData()
    if not regions:
        result.unsupported_layout = True
        return result

    lines: List[Tuple[str, float, List[List[int]]]] = [
        (r.text.strip(), r.confidence, r.bbox) for r in regions if r.text.strip()
    ]
    all_text_combined = " ".join([t[0].upper() for t in lines])

    # Check for Voter ID indicators
    voter_id_indicators = [
        "ELECTION COMMISSION", "ELECTORS PHOTO IDENTITY",
        "VOTER ID", "EPIC", "ELECTORAL ROLL",
    ]
    has_voter_indicator = any(kw in all_text_combined for kw in voter_id_indicators)

    # ── Field 1: EPIC Number ──────────────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        # Look for labeled EPIC number
        m_label = re.search(r"(?:EPIC\s*(?:NO|NUMBER|#|:)?|VOTER\s*ID\s*(?:NO|NUMBER|#|:)?)\s*[:\-]?\s*([A-Z]{3}[0-9]{7})", clean_upper)
        if m_label and not result.epic_number.value:
            result.epic_number = VoterIdField(value=m_label.group(1), confidence=conf, bbox=bbox, raw=m_label.group(1))
            break

    # If not found by label, scan for standalone EPIC pattern
    if not result.epic_number.value:
        for text, conf, bbox in lines:
            m = EPIC_PATTERN.search(text.upper())
            if m:
                result.epic_number = VoterIdField(value=m.group(1), confidence=conf, bbox=bbox, raw=m.group(1))
                break

    result.docNumber = result.epic_number

    # ── Field 2: Name ─────────────────────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_name = re.search(r"(?:NAME|ELECTOR'?S?\s*NAME)\s*[:\-]?\s*([A-Z][A-Z\s.'-]{2,40})", clean_upper)
        if m_name and not result.name.value:
            cand = m_name.group(1).strip()
            if not any(tok in cand for tok in _EPIC_NOISE_TOKENS):
                result.name = VoterIdField(value=cand, confidence=conf, bbox=bbox, raw=cand)
                break

    # ── Field 3: Father's Name ────────────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_father = re.search(
            r"(?:FATHER'?S?\s*NAME|HUSBAND'?S?\s*NAME|RELATION\s*NAME|S/O|D/O|W/O|F/O)\s*[:\-]?\s*([A-Z][A-Z\s.'-]{2,40})",
            clean_upper,
        )
        if m_father and not result.father_name.value:
            cand = m_father.group(1).strip()
            if not any(tok in cand for tok in _EPIC_NOISE_TOKENS):
                result.father_name = VoterIdField(value=cand, confidence=conf, bbox=bbox, raw=cand)
                break

    # ── Field 4: Date of Birth / Age ──────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_dob = re.search(r"(?:DOB|DATE\s*OF\s*BIRTH|D\.O\.B)\s*[:\-]?\s*(\d{1,2}[\/.\-]\d{1,2}[\/.\-]\d{4})", clean_upper)
        if m_dob and not result.dob.value:
            result.dob = VoterIdField(value=m_dob.group(1), confidence=conf, bbox=bbox, raw=m_dob.group(1))
            break

    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_age = re.search(r"(?:AGE|UM?RA?|VARSH)\s*[:\-]?\s*(\d{1,3})\s*(?:YRS?|YEARS?)?", clean_upper)
        if m_age and not result.age.value:
            result.age = VoterIdField(value=m_age.group(1), confidence=conf, bbox=bbox, raw=m_age.group(1))
            break

    # ── Field 5: Gender ───────────────────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_gender = re.search(r"(?:SEX|GENDER|LING)\s*[:\-]?\s*(MALE|FEMALE|TRANSGENDER|M\b|F\b)", clean_upper)
        if m_gender and not result.gender.value:
            g = m_gender.group(1)
            g_norm = "MALE" if g in ("M", "MALE") else ("FEMALE" if g in ("F", "FEMALE") else "TRANSGENDER")
            result.gender = VoterIdField(value=g_norm, confidence=conf, bbox=bbox, raw=g)
            break

    # ── Field 6: Constituency / AC Name ───────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_const = re.search(r"(?:CONSTITUENCY|AC\s*NAME|ASSEMBLY\s*CONSTITUENCY|VIDHAN\s*SABHA)\s*[:\-]?\s*([A-Z][A-Z\s]{2,40})", clean_upper)
        if m_const and not result.constituency.value:
            cand = m_const.group(1).strip()
            result.constituency = VoterIdField(value=cand, confidence=conf, bbox=bbox, raw=cand)
            break

    # ── Field 7: Part & Serial Number ────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_part = re.search(r"(?:PART\s*(?:NO|NUMBER|#)?|BHAG)\s*[:\-]?\s*(\d{1,6})", clean_upper)
        if m_part and not result.part_number.value:
            result.part_number = VoterIdField(value=m_part.group(1), confidence=conf, bbox=bbox, raw=m_part.group(1))

        m_serial = re.search(r"(?:SERIAL\s*(?:NO|NUMBER|#)?|KRAMA\s*SANKHYA?)\s*[:\-]?\s*(\d{1,6})", clean_upper)
        if m_serial and not result.serial_number.value:
            result.serial_number = VoterIdField(value=m_serial.group(1), confidence=conf, bbox=bbox, raw=m_serial.group(1))

    # ── Field 8: Issuing Authority ────────────────────────────────────────────
    if has_voter_indicator or "ELECTION COMMISSION" in all_text_combined:
        result.issuing_authority = VoterIdField(
            value="Election Commission of India",
            confidence=0.95,
            raw="ELECTION COMMISSION OF INDIA",
        )

    # ── Profile Compatibility Assessment ──────────────────────────────────────
    primary_count = sum(1 for f in [result.epic_number.value, result.name.value] if f)
    if not has_voter_indicator and primary_count == 0:
        result.unsupported_layout = True
        logger.warning("Voter ID parser: document lacks recognizable EPIC / Voter ID layout.")

    return result
