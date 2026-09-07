"""
backend/app/services/documents/national_id/national_id_parser.py

Deterministic National ID field extraction from raw OCR regions.
Focused on Indian National ID (UIDAI Aadhaar reference standard).
Preserves bounding boxes, confidence scores, and raw OCR text.
Crucial:
- Distinguishes Full DOB from Year of Birth explicitly.
- Flags ambiguous identifiers rather than silently guessing OCR misreads.
- Masks sensitive 12-digit identity numbers for telemetry and logging.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.ocr import OCRRegionRaw
from app.services.documents.national_id.national_id_field_normalizer import (
    normalize_address,
    normalize_dob_or_yob,
    normalize_gender,
    normalize_name,
)
from app.services.documents.national_id.national_id_identifier_validator import (
    mask_national_id,
    normalize_national_id,
)
from app.services.documents.national_id.national_id_qr_validator import (
    parse_national_id_qr_payload,
)

logger = logging.getLogger(__name__)


@dataclass
class NationalIdField:
    """A single parsed National ID field with provenance."""
    value: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[List[List[int]]] = None
    raw: Optional[str] = None


@dataclass
class ParsedNationalIdData:
    """Structured fields extracted from a National ID document."""
    identity_number: NationalIdField = field(default_factory=NationalIdField)
    docNumber: NationalIdField = field(default_factory=NationalIdField)  # Canonical alias
    masked_identity_number: Optional[str] = None
    name: NationalIdField = field(default_factory=NationalIdField)
    dob: NationalIdField = field(default_factory=NationalIdField)          # Full date (YYYY-MM-DD) or None
    year_of_birth: NationalIdField = field(default_factory=NationalIdField)# 4-digit year or None
    gender: NationalIdField = field(default_factory=NationalIdField)
    address: NationalIdField = field(default_factory=NationalIdField)
    issuing_authority: NationalIdField = field(default_factory=NationalIdField)
    qr_payload: Optional[str] = None
    qr_decoded: bool = False
    qr_parsed_data: Optional[Dict[str, Any]] = None
    is_ambiguous_identifier: bool = False
    unsupported_layout: bool = False


# Known header tokens to discard when searching for names
_HEADER_NOISE_TOKENS = (
    "GOVERNMENT", "INDIA", "BHARAT", "SARKAR", "UNIQUE",
    "IDENTIFICATION", "AUTHORITY", "UIDAI", "AADHAAR",
    "ENROLMENT", "ENROLLMENT", "MERA", "MERI", "PEHCHAN",
    "HELP", "WWW", "VID", "HELP@UIDAI.GOV.IN",
)


def parse_national_id(
    regions: List[OCRRegionRaw],
    raw_qr_payload: Optional[str] = None,
) -> ParsedNationalIdData:
    """
    Extract structured fields from OCR regions on an Indian National ID image.
    """
    result = ParsedNationalIdData()
    if not regions and not raw_qr_payload:
        result.unsupported_layout = True
        return result

    lines: List[Tuple[str, float, List[List[int]]]] = [
        (r.text.strip(), r.confidence, r.bbox) for r in regions if r.text.strip()
    ]
    all_text_combined = " ".join([t[0].upper() for t in lines])

    # Check for general Indian National ID indicators
    nid_indicators = [
        "GOVERNMENT OF INDIA", "BHARAT SARKAR", "UIDAI", "AADHAAR",
        "UNIQUE IDENTIFICATION AUTHORITY OF INDIA", "ENROLMENT", "MERI PEHCHAN",
    ]
    has_nid_indicator = any(kw in all_text_combined for kw in nid_indicators)

    # ── Field 1: Identity Number (12 digits) ──────────────────────────────────
    # Check for ambiguous strings first (e.g. 1234 56B8 9012)
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        # Look for 4-4-4 character groups
        m_ambig = re.search(r"\b([0-9A-Z]{4}[\s\-][0-9A-Z]{4}[\s\-][0-9A-Z]{4})\b", clean_upper)
        if m_ambig:
            candidate = m_ambig.group(1)
            norm_id, err = normalize_national_id(candidate)
            if err == "AMBIGUOUS_IDENTIFIER":
                result.is_ambiguous_identifier = True
                result.identity_number = NationalIdField(
                    value=None,
                    confidence=conf,
                    bbox=bbox,
                    raw=candidate,
                )
                logger.warning("National ID parser: Ambiguous characters detected in identifier '%s'", candidate)
                break
            elif norm_id and not result.identity_number.value:
                result.identity_number = NationalIdField(
                    value=norm_id,
                    confidence=conf,
                    bbox=bbox,
                    raw=candidate,
                )
                result.masked_identity_number = mask_national_id(norm_id)
                break

    # If not found via 4-4-4 spaced search, check for 12 consecutive digits or labeled number
    if not result.identity_number.value and not result.is_ambiguous_identifier:
        for text, conf, bbox in lines:
            clean_upper = text.upper()
            m_digits = re.search(r"\b(\d{12})\b", clean_upper)
            if m_digits:
                norm_id, err = normalize_national_id(m_digits.group(1))
                if norm_id:
                    result.identity_number = NationalIdField(
                        value=norm_id,
                        confidence=conf,
                        bbox=bbox,
                        raw=m_digits.group(1),
                    )
                    result.masked_identity_number = mask_national_id(norm_id)
                    break

    # Canonical alias: docNumber
    result.docNumber = result.identity_number

    # ── Field 2: Date of Birth or Year of Birth ──────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        # Look for DOB label
        m_dob = re.search(
            r"(?:DOB|D\.O\.B|DATE\s*OF\s*BIRTH|BIRTH\s*DATE|JANMA\s*TITHI)\s*[:.\-]?\s*([0-9A-Za-z\/\.\-]+)",
            clean_upper,
        )
        if m_dob and not result.dob.value and not result.year_of_birth.value:
            dob_info = normalize_dob_or_yob(m_dob.group(1))
            if dob_info["date_of_birth"]:
                result.dob = NationalIdField(
                    value=dob_info["date_of_birth"],
                    confidence=conf,
                    bbox=bbox,
                    raw=m_dob.group(1),
                )
                result.year_of_birth = NationalIdField(
                    value=str(dob_info["year_of_birth"]),
                    confidence=conf,
                    bbox=bbox,
                    raw=str(dob_info["year_of_birth"]),
                )
                break
            elif dob_info["year_of_birth"]:
                result.year_of_birth = NationalIdField(
                    value=str(dob_info["year_of_birth"]),
                    confidence=conf,
                    bbox=bbox,
                    raw=m_dob.group(1),
                )
                break

        # Look for Year of Birth label
        m_yob = re.search(
            r"(?:YEAR\s*OF\s*BIRTH|YOB|JANMA\s*VARSH)\s*[:.\-]?\s*(\d{4})",
            clean_upper,
        )
        if m_yob and not result.year_of_birth.value:
            yob_info = normalize_dob_or_yob(m_yob.group(1))
            if yob_info["year_of_birth"]:
                result.year_of_birth = NationalIdField(
                    value=str(yob_info["year_of_birth"]),
                    confidence=conf,
                    bbox=bbox,
                    raw=m_yob.group(1),
                )
                break

    # If still not found, check lines for a standalone date or YOB pattern
    if not result.dob.value and not result.year_of_birth.value:
        for idx, (text, conf, bbox) in enumerate(lines):
            clean_upper = text.upper()
            if "DOB" in clean_upper or "BIRTH" in clean_upper:
                dob_info = normalize_dob_or_yob(clean_upper)
                if dob_info["date_of_birth"]:
                    result.dob = NationalIdField(
                        value=dob_info["date_of_birth"],
                        confidence=conf,
                        bbox=bbox,
                        raw=clean_upper,
                    )
                    result.year_of_birth = NationalIdField(
                        value=str(dob_info["year_of_birth"]),
                        confidence=conf,
                        bbox=bbox,
                        raw=str(dob_info["year_of_birth"]),
                    )
                    break
                elif dob_info["year_of_birth"]:
                    result.year_of_birth = NationalIdField(
                        value=str(dob_info["year_of_birth"]),
                        confidence=conf,
                        bbox=bbox,
                        raw=clean_upper,
                    )
                    break
                else:
                    # Look ahead up to 3 lines for the date value
                    for look in range(1, min(4, len(lines) - idx)):
                        cand_text = lines[idx + look][0]
                        cand_dob = normalize_dob_or_yob(cand_text)
                        if cand_dob["date_of_birth"]:
                            result.dob = NationalIdField(
                                value=cand_dob["date_of_birth"],
                                confidence=lines[idx + look][1],
                                bbox=lines[idx + look][2],
                                raw=cand_text,
                            )
                            result.year_of_birth = NationalIdField(
                                value=str(cand_dob["year_of_birth"]),
                                confidence=lines[idx + look][1],
                                bbox=lines[idx + look][2],
                                raw=str(cand_dob["year_of_birth"]),
                            )
                            break
                        elif cand_dob["year_of_birth"]:
                            result.year_of_birth = NationalIdField(
                                value=str(cand_dob["year_of_birth"]),
                                confidence=lines[idx + look][1],
                                bbox=lines[idx + look][2],
                                raw=cand_text,
                            )
                            break
                    if result.dob.value or result.year_of_birth.value:
                        break

    # ── Field 3: Gender ──────────────────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        # Labeled or standalone gender
        norm_g = normalize_gender(clean_upper)
        if norm_g and not result.gender.value:
            # Check if this line is strictly a gender line (avoid partial words like 'FEMALE' in address)
            if any(w in clean_upper.split() for w in ("MALE", "FEMALE", "TRANSGENDER", "PURUSH", "MAHILA")):
                result.gender = NationalIdField(
                    value=norm_g,
                    confidence=conf,
                    bbox=bbox,
                    raw=clean_upper,
                )
                break

    # ── Field 4: Bearer Name ─────────────────────────────────────────────────
    # In Indian National ID, the bearer's English name is typically located:
    # 1. Immediately above the DOB line
    # 2. Or labeled "Name:" / "To:"
    # 3. Discard lines containing header noise tokens
    for idx, (text, conf, bbox) in enumerate(lines):
        clean_upper = text.upper()
        m_name = re.search(r"(?:NAME|TO)\s*[:.\-]?\s*([A-Z\s.'-]{3,40})", clean_upper)
        if m_name and not result.name.value:
            cand = m_name.group(1).strip()
            norm = normalize_name(cand)
            if norm and not any(kw in norm for kw in _HEADER_NOISE_TOKENS):
                result.name = NationalIdField(value=norm, confidence=conf, bbox=bbox, raw=cand)
                break

    # If no labeled name, search backwards from the DOB / YOB line
    if not result.name.value:
        dob_idx = -1
        for idx, (text, conf, bbox) in enumerate(lines):
            clean_upper = text.upper()
            if "DOB" in clean_upper or "BIRTH" in clean_upper or (result.dob.raw and result.dob.raw in clean_upper):
                dob_idx = idx
                break

        if dob_idx > 0:
            for cand_idx in range(dob_idx - 1, -1, -1):
                cand_text = lines[cand_idx][0]
                norm = normalize_name(cand_text)
                if norm and len(norm) >= 3 and not any(kw in norm for kw in _HEADER_NOISE_TOKENS):
                    result.name = NationalIdField(
                        value=norm,
                        confidence=lines[cand_idx][1],
                        bbox=lines[cand_idx][2],
                        raw=cand_text,
                    )
                    break

    # ── Field 5: Issuing Authority ───────────────────────────────────────────
    if has_nid_indicator or "UIDAI" in all_text_combined:
        result.issuing_authority = NationalIdField(
            value="Unique Identification Authority of India",
            confidence=0.95,
            raw="UIDAI",
        )

    # ── Field 6: Address ─────────────────────────────────────────────────────
    addr_lines = []
    collecting_addr = False
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        if "ADDRESS" in clean_upper:
            collecting_addr = True
            norm_a = normalize_address(text)
            if norm_a:
                addr_lines.append(norm_a)
            continue
        if collecting_addr:
            # Stop collecting if we hit another field or ID number
            if any(kw in clean_upper for kw in ("UID", "DOB", "YEAR OF BIRTH", "WWW.", "HELP@")):
                break
            if re.search(r"\b\d{12}\b", clean_upper):
                break
            norm_a = normalize_address(text)
            if norm_a:
                addr_lines.append(norm_a)

    if addr_lines:
        full_addr = ", ".join(addr_lines)
        result.address = NationalIdField(
            value=full_addr,
            confidence=0.85,
            raw=full_addr,
        )

    # ── Field 7: QR / Barcode Payload ────────────────────────────────────────
    # Check if raw_qr_payload was provided or if OCR text contains an XML barcode payload
    qr_payload_to_parse = raw_qr_payload
    if not qr_payload_to_parse:
        for text, _, _ in lines:
            if "<PrintLetterBarcodeData" in text or "uid=" in text:
                qr_payload_to_parse = text
                break

    if qr_payload_to_parse:
        qr_parsed = parse_national_id_qr_payload(qr_payload_to_parse)
        result.qr_payload = qr_payload_to_parse
        result.qr_parsed_data = qr_parsed
        result.qr_decoded = qr_parsed.get("status") == "PAYLOAD_DECODED"

        # If OCR missed fields, fill from QR data if available
        if not result.identity_number.value and qr_parsed.get("identity_number"):
            result.identity_number = NationalIdField(
                value=qr_parsed["identity_number"],
                confidence=0.95,
                raw=qr_parsed["identity_number"],
            )
            result.masked_identity_number = qr_parsed.get("masked_identity_number")
            result.docNumber = result.identity_number

        if not result.name.value and qr_parsed.get("name"):
            result.name = NationalIdField(
                value=qr_parsed["name"],
                confidence=0.95,
                raw=qr_parsed["name"],
            )

        if not result.dob.value and not result.year_of_birth.value:
            if qr_parsed.get("dob"):
                d_info = normalize_dob_or_yob(qr_parsed["dob"])
                if d_info["date_of_birth"]:
                    result.dob = NationalIdField(value=d_info["date_of_birth"], confidence=0.95, raw=qr_parsed["dob"])
                    result.year_of_birth = NationalIdField(value=str(d_info["year_of_birth"]), confidence=0.95, raw=str(d_info["year_of_birth"]))
                elif d_info["year_of_birth"]:
                    result.year_of_birth = NationalIdField(value=str(d_info["year_of_birth"]), confidence=0.95, raw=qr_parsed["dob"])
            elif qr_parsed.get("year_of_birth"):
                result.year_of_birth = NationalIdField(value=str(qr_parsed["year_of_birth"]), confidence=0.95, raw=str(qr_parsed["year_of_birth"]))

        if not result.gender.value and qr_parsed.get("gender"):
            result.gender = NationalIdField(value=qr_parsed["gender"], confidence=0.95, raw=qr_parsed["gender"])

        if not result.address.value and qr_parsed.get("address"):
            result.address = NationalIdField(value=qr_parsed["address"], confidence=0.95, raw=qr_parsed["address"])

    # ── Profile Compatibility Assessment ─────────────────────────────────────
    # If there are zero indicators and no primary fields, flag unsupported layout
    primary_fields_count = sum(1 for f in [result.identity_number.value, result.name.value, result.dob.value, result.year_of_birth.value] if f)
    if not has_nid_indicator and primary_fields_count == 0 and not result.qr_decoded:
        result.unsupported_layout = True
        logger.warning("National ID parser: document lacks recognizable National ID layout or fields.")

    return result
