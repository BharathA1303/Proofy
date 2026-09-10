"""
backend/app/services/documents/aadhaar/aadhaar_parser.py

Deterministic Aadhaar card field extraction from raw OCR regions.
Focused on UIDAI Aadhaar reference standard.
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
from app.services.documents.aadhaar.aadhaar_field_normalizer import (
    normalize_address,
    normalize_dob_or_yob,
    normalize_gender,
    normalize_name,
)
from app.services.documents.aadhaar.aadhaar_identifier_validator import (
    ChecksumStatus,
    mask_aadhaar,
    normalize_aadhaar,
    validate_verhoeff_checksum,
)
from app.services.documents.aadhaar.aadhaar_qr_validator import (
    parse_national_id_qr_payload,
)

logger = logging.getLogger(__name__)


@dataclass
class AadhaarField:
    """A single parsed Aadhaar field with provenance."""
    value: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[List[List[int]]] = None
    raw: Optional[str] = None


@dataclass
class ParsedAadhaarData:
    """Structured fields extracted from a UIDAI Aadhaar card."""
    identity_number: AadhaarField = field(default_factory=AadhaarField)
    docNumber: AadhaarField = field(default_factory=AadhaarField)   # Canonical alias
    masked_identity_number: Optional[str] = None
    name: AadhaarField = field(default_factory=AadhaarField)
    dob: AadhaarField = field(default_factory=AadhaarField)
    year_of_birth: AadhaarField = field(default_factory=AadhaarField)
    gender: AadhaarField = field(default_factory=AadhaarField)
    address: AadhaarField = field(default_factory=AadhaarField)
    issuing_authority: AadhaarField = field(default_factory=AadhaarField)
    qr_payload: Optional[str] = None
    qr_decoded: bool = False
    qr_parsed_data: Optional[Dict[str, Any]] = None
    is_ambiguous_identifier: bool = False
    unsupported_layout: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "docNumber": self.docNumber.value or self.identity_number.value,
            "identity_number": self.identity_number.value,
            "identityNumber": self.identity_number.value,
            "masked_identity_number": self.masked_identity_number,
            "maskedIdentityNumber": self.masked_identity_number,
            "name": self.name.value,
            "dob": self.dob.value,
            "date_of_birth": self.dob.value or self.year_of_birth.value,
            "year_of_birth": self.year_of_birth.value,
            "yearOfBirth": self.year_of_birth.value,
            "gender": self.gender.value,
            "address": self.address.value,
            "issuing_authority": self.issuing_authority.value,
            "authority": self.issuing_authority.value,
            "qr_payload": self.qr_payload,
            "qrPayload": self.qr_payload,
            "qr_decoded": self.qr_decoded,
            "qrDecoded": self.qr_decoded,
        }


# Backward compatibility: old code that imports ParsedNationalIdData & NationalIdField still works
NationalIdField = AadhaarField
ParsedNationalIdData = ParsedAadhaarData

# Known header tokens to discard when searching for names
_HEADER_NOISE_TOKENS = (
    "GOVERNMENT", "INDIA", "BHARAT", "SARKAR", "UNIQUE",
    "IDENTIFICATION", "AUTHORITY", "UIDAI", "AADHAAR",
    "ENROLMENT", "ENROLLMENT", "MERA", "MERI", "PEHCHAN",
    "HELP", "WWW", "VID", "HELP@UIDAI.GOV.IN",
    "PROOF OF IDENTITY", "CITIZENSHIP", "VERIFICATION",
    "OFFLINE", "XML", "QR", "CODE",
    "DATE", "BIRTH", "DOB", "BIRTHDOB", "GENDER", "ADDRESS",
)

_ADDR_PREFIXES = (
    "W/O", "S/O", "D/O", "C/O", "FLAT", "STREET", "ROAD",
    "NAGAR", "DISTRICT", "STATE", "PIN", "MOBILE", "VTC", "PO:",
)


def _is_disclaimer_text(s: str) -> bool:
    su = s.upper()
    return any(w in su for w in ("PROOF OF IDENTITY", "CITIZENSHIP", "VERIFICATION ONLINE", "OFFLINE XML"))


def parse_aadhaar(
    regions: List[OCRRegionRaw],
    raw_qr_payload: Optional[str] = None,
) -> ParsedAadhaarData:
    """
    Extract structured fields from OCR regions on a UIDAI Aadhaar card image.
    Supports both compact card-sized and long letter e-Aadhaar layouts.
    """
    result = ParsedAadhaarData()
    if not regions and not raw_qr_payload:
        result.unsupported_layout = True
        return result

    lines: List[Tuple[str, float, List[List[int]]]] = [
        (r.text.strip(), r.confidence, r.bbox) for r in regions if r.text.strip()
    ]
    all_text_combined = " ".join([t[0].upper() for t in lines])

    # Check for Aadhaar indicators
    nid_indicators = [
        "GOVERNMENT OF INDIA", "BHARAT SARKAR", "UIDAI", "AADHAAR",
        "UNIQUE IDENTIFICATION AUTHORITY OF INDIA", "ENROLMENT", "MERI PEHCHAN",
    ]
    has_nid_indicator = any(kw in all_text_combined for kw in nid_indicators)

    # ── Field 1: Identity Number (12 digits) ─────────────────────────────────
    # We gather all 12-digit candidate sequences and prioritize the ones passing Verhoeff checksum.
    candidates: List[Tuple[str, float, List[List[int]], str, bool]] = []
    # (normalized_12_digits, confidence, bbox, raw_text, passes_verhoeff)

    for text, conf, bbox in lines:
        clean_text = text.strip()
        clean_upper = clean_text.upper()

        # Check standard 4-4-4 format (separated by spaces, dots, or hyphens)
        for m in re.finditer(r"(?:\b|[^\d])([0-9A-Z]{4}[\s\.\-][0-9A-Z]{4}[\s\.\-][0-9A-Z]{4})(?:\b|[^\d])", clean_upper):
            raw_c = m.group(1)
            clean_c = re.sub(r"[\s\.\-]", "", raw_c)
            norm_c, err = normalize_aadhaar(clean_c)
            if err == "AMBIGUOUS_IDENTIFIER":
                result.is_ambiguous_identifier = True
            if norm_c and len(norm_c) == 12:
                chk = validate_verhoeff_checksum(norm_c)
                candidates.append((norm_c, conf, bbox, raw_c, chk == ChecksumStatus.PASS))

        # Check 8-4 or 4-8 or irregular spacing (e.g. "36634767 0846")
        for m in re.finditer(r"(?:\b|[^\d])([0-9A-Z]{4,8}[\s\.\-][0-9A-Z]{4,8})(?:\b|[^\d])", clean_upper):
            raw_c = m.group(1)
            clean_c = re.sub(r"[\s\.\-]", "", raw_c)
            if len(clean_c) == 12:
                norm_c, err = normalize_aadhaar(clean_c)
                if err == "AMBIGUOUS_IDENTIFIER":
                    result.is_ambiguous_identifier = True
                if norm_c and len(norm_c) == 12:
                    chk = validate_verhoeff_checksum(norm_c)
                    candidates.append((norm_c, conf, bbox, raw_c, chk == ChecksumStatus.PASS))

        # Check unseparated 12 alphanumeric characters
        for m in re.finditer(r"\b([0-9A-Z]{12})\b", clean_upper):
            raw_c = m.group(1)
            norm_c, err = normalize_aadhaar(raw_c)
            if err == "AMBIGUOUS_IDENTIFIER":
                result.is_ambiguous_identifier = True
            if norm_c and len(norm_c) == 12:
                chk = validate_verhoeff_checksum(norm_c)
                candidates.append((norm_c, conf, bbox, raw_c, chk == ChecksumStatus.PASS))

        # Extract digits-only if count is exactly 12 (handles surrounding Tamil/English noise)
        digits_only = re.sub(r"\D", "", clean_text)
        if len(digits_only) == 12:
            norm_c, _ = normalize_aadhaar(digits_only)
            if norm_c and len(norm_c) == 12:
                chk = validate_verhoeff_checksum(norm_c)
                candidates.append((norm_c, conf, bbox, clean_text, chk == ChecksumStatus.PASS))
        elif len(digits_only) > 12:
            # Check sliding window of 12 digits that passes Verhoeff
            for i in range(len(digits_only) - 11):
                sub_digits = digits_only[i:i+12]
                if validate_verhoeff_checksum(sub_digits) == ChecksumStatus.PASS:
                    candidates.append((sub_digits, conf, bbox, clean_text, True))

    if candidates:
        passing = [c for c in candidates if c[4]]
        best = passing[0] if passing else candidates[0]
        norm_id, conf, bbox, raw_val, _ = best
        result.identity_number = AadhaarField(value=norm_id, confidence=conf, bbox=bbox, raw=raw_val)
        result.masked_identity_number = mask_aadhaar(norm_id)

    result.docNumber = result.identity_number

    # ── Field 2: Date of Birth or Year of Birth ───────────────────────────────
    # Pass 1: Explicit DOB indicators with date pattern (excluding footer disclaimers)
    for text, conf, bbox in lines:
        if _is_disclaimer_text(text):
            continue
        clean_upper = text.upper()
        # Matches: DOB: 13/03/2007, 5/D0B:13/03/2007, DO01/01/1985, DOB01/01/1985, பிறந்த நாள் / DOB: 13/03/2007
        m_dob = re.search(
            r"(?:DOB|D0B|D\.O\.B|DATE\s*OF\s*BIRTH|BIRTH\s*DATE|JANMA\s*TITHI|DO)[:\.\-\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
            clean_upper,
        )
        if m_dob and not result.dob.value:
            dob_info = normalize_dob_or_yob(m_dob.group(1))
            if dob_info["date_of_birth"]:
                result.dob = AadhaarField(value=dob_info["date_of_birth"], confidence=conf, bbox=bbox, raw=m_dob.group(0))
                result.year_of_birth = AadhaarField(value=str(dob_info["year_of_birth"]), confidence=conf, bbox=bbox, raw=str(dob_info["year_of_birth"]))
                break

    # Pass 2: Standalone calendar date DD/MM/YYYY on any non-disclaimer line
    if not result.dob.value:
        for text, conf, bbox in lines:
            if _is_disclaimer_text(text):
                continue
            clean_upper = text.upper()
            m_date = re.search(r"\b(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})\b", clean_upper)
            if m_date:
                dob_info = normalize_dob_or_yob(m_date.group(1))
                if dob_info["date_of_birth"]:
                    result.dob = AadhaarField(value=dob_info["date_of_birth"], confidence=conf, bbox=bbox, raw=m_date.group(1))
                    result.year_of_birth = AadhaarField(value=str(dob_info["year_of_birth"]), confidence=conf, bbox=bbox, raw=str(dob_info["year_of_birth"]))
                    break

    # Pass 3: Year of birth only (e.g. "Year of Birth: 1985")
    if not result.dob.value and not result.year_of_birth.value:
        for text, conf, bbox in lines:
            if _is_disclaimer_text(text):
                continue
            clean_upper = text.upper()
            m_yob = re.search(r"(?:YEAR\s*OF\s*BIRTH|YOB|JANMA\s*VARSH)[:\.\-\s]*(\d{4})", clean_upper)
            if m_yob:
                yob_info = normalize_dob_or_yob(m_yob.group(1))
                if yob_info["year_of_birth"]:
                    result.year_of_birth = AadhaarField(value=str(yob_info["year_of_birth"]), confidence=conf, bbox=bbox, raw=m_yob.group(0))
                    break

    # ── Field 3: Gender ───────────────────────────────────────────────────────
    for text, conf, bbox in lines:
        if _is_disclaimer_text(text):
            continue
        clean_upper = text.upper()
        # Check FEMALE first to prevent substring matching of MALE within FEMALE
        if re.search(r"(?:\b|[/_\-\s])(FEMALE|MAHILA|WOMAN)(?:\b|[/_\-\s])", clean_upper) or clean_upper.endswith("FEMALE"):
            result.gender = AadhaarField(value="FEMALE", confidence=conf, bbox=bbox, raw=text)
            break
        elif re.search(r"(?:\b|[/_\-\s])(MALE|PURUSH|MAN)(?:\b|[/_\-\s])", clean_upper) or clean_upper.endswith("MALE"):
            result.gender = AadhaarField(value="MALE", confidence=conf, bbox=bbox, raw=text)
            break
        elif re.search(r"(?:\b|[/_\-\s])(TRANSGENDER|TG)(?:\b|[/_\-\s])", clean_upper):
            result.gender = AadhaarField(value="TRANSGENDER", confidence=conf, bbox=bbox, raw=text)
            break

    # ── Field 4: Bearer Name ──────────────────────────────────────────────────
    def _is_valid_name_token(token: str) -> bool:
        clean = token.strip()
        if not clean or len(clean) < 3 or len(clean) > 45 or re.search(r"\d", clean):
            return False
        clean_up = clean.upper()
        if any(clean_up.startswith(p) for p in _ADDR_PREFIXES) or _is_disclaimer_text(clean):
            return False
        words = clean_up.split()
        if any(w in _HEADER_NOISE_TOKENS for w in words):
            return False
        if not re.search(r"[AEIOUYaeiouy]", clean):
            return False
        if clean_up in ("ANS", "QN", "CSA AM", "MALE", "FEMALE", "TRANSGENDER", "TO", "BTER"):
            return False
        return True

    # Strategy 1: Look directly above the DOB line (Compact card & cut-out card)
    dob_line_idx = -1
    if result.dob.raw:
        for idx, (t, _, _) in enumerate(lines):
            if result.dob.raw in t or (result.dob.value and result.dob.value in t):
                dob_line_idx = idx
                break
    if dob_line_idx == -1:
        for idx, (t, _, _) in enumerate(lines):
            if not _is_disclaimer_text(t) and re.search(r"\d{2}[/\-\.]\d{2}[/\-\.]\d{4}", t):
                dob_line_idx = idx
                break

    if dob_line_idx > 0:
        for cand_idx in range(dob_line_idx - 1, max(-1, dob_line_idx - 5), -1):
            cand_text, cand_conf, cand_bbox = lines[cand_idx]
            if _is_valid_name_token(cand_text):
                norm = normalize_name(cand_text)
                if norm:
                    result.name = AadhaarField(value=norm, confidence=cand_conf, bbox=cand_bbox, raw=cand_text)
                    break

    # Strategy 2: Look for 'To' in address block (Long letter e-Aadhaar)
    if not result.name.value:
        for idx, (t, _, _) in enumerate(lines):
            if t.strip().upper() == "TO" and idx + 1 < len(lines):
                cand_text, cand_conf, cand_bbox = lines[idx + 1]
                if _is_valid_name_token(cand_text):
                    norm = normalize_name(cand_text)
                    if norm:
                        result.name = AadhaarField(value=norm, confidence=cand_conf, bbox=cand_bbox, raw=cand_text)
                        break

    # Strategy 3: Explicit 'NAME:' prefix
    if not result.name.value:
        for text, conf, bbox in lines:
            clean_upper = text.upper()
            m_name = re.search(r"\bNAME\s*[:\.\-]?\s*([A-Z\s.'-]{3,40})", clean_upper)
            if m_name:
                cand = m_name.group(1).strip()
                if _is_valid_name_token(cand):
                    norm = normalize_name(cand)
                    if norm:
                        result.name = AadhaarField(value=norm, confidence=conf, bbox=bbox, raw=cand)
                        break

    # Strategy 4: Fallback scan for first valid name after header
    if not result.name.value:
        header_seen = False
        for text, conf, bbox in lines:
            if any(w in text.upper() for w in ("GOVERNMENT", "INDIA", "BHARAT")):
                header_seen = True
                continue
            if header_seen and _is_valid_name_token(text):
                norm = normalize_name(text)
                if norm:
                    result.name = AadhaarField(value=norm, confidence=conf, bbox=bbox, raw=text)
                    break

    # ── Field 5: Issuing Authority ────────────────────────────────────────────
    if has_nid_indicator or "UIDAI" in all_text_combined:
        result.issuing_authority = AadhaarField(
            value="Unique Identification Authority of India",
            confidence=0.95,
            raw="UIDAI",
        )

    # ── Field 6: Address ──────────────────────────────────────────────────────
    addr_lines = []
    # 1. Extract from 'To' block in long e-Aadhaar
    to_idx = -1
    for idx, (t, _, _) in enumerate(lines):
        if t.strip().upper() == "TO":
            to_idx = idx
            break
    if to_idx >= 0:
        for idx in range(to_idx + 2, min(to_idx + 12, len(lines))):
            t = lines[idx][0]
            tu = t.upper()
            if any(kw in tu for kw in ("YOUR AADHAAR", "AADHAAR NO", "ENROLMENT", "KD4", "MOBILE", "PIN CODE")):
                if "PIN CODE" in tu:
                    na = normalize_address(t)
                    if na:
                        addr_lines.append(na)
                break
            if re.search(r"\b\d{12}\b", tu):
                break
            na = normalize_address(t)
            if na and len(na) > 2:
                addr_lines.append(na)

    # 2. Extract via 'Address:' prefix if not found via 'To'
    if not addr_lines:
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
                if any(kw in clean_upper for kw in ("UID", "DOB", "YEAR OF BIRTH", "WWW.", "HELP@")):
                    break
                if re.search(r"\b\d{12}\b", clean_upper):
                    break
                norm_a = normalize_address(text)
                if norm_a:
                    addr_lines.append(norm_a)

    if addr_lines:
        full_addr = ", ".join(addr_lines)
        result.address = AadhaarField(value=full_addr, confidence=0.88, raw=full_addr)

    # ── Field 7: QR / Barcode Payload ─────────────────────────────────────────
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

        if not result.identity_number.value and qr_parsed.get("identity_number"):
            result.identity_number = AadhaarField(value=qr_parsed["identity_number"], confidence=0.95, raw=qr_parsed["identity_number"])
            result.masked_identity_number = qr_parsed.get("masked_identity_number")
            result.docNumber = result.identity_number

        if not result.name.value and qr_parsed.get("name"):
            result.name = AadhaarField(value=qr_parsed["name"], confidence=0.95, raw=qr_parsed["name"])

        if not result.dob.value and not result.year_of_birth.value:
            if qr_parsed.get("dob"):
                d_info = normalize_dob_or_yob(qr_parsed["dob"])
                if d_info["date_of_birth"]:
                    result.dob = AadhaarField(value=d_info["date_of_birth"], confidence=0.95, raw=qr_parsed["dob"])
                    result.year_of_birth = AadhaarField(value=str(d_info["year_of_birth"]), confidence=0.95, raw=str(d_info["year_of_birth"]))
                elif d_info["year_of_birth"]:
                    result.year_of_birth = AadhaarField(value=str(d_info["year_of_birth"]), confidence=0.95, raw=qr_parsed["dob"])
            elif qr_parsed.get("year_of_birth"):
                result.year_of_birth = AadhaarField(value=str(qr_parsed["year_of_birth"]), confidence=0.95, raw=str(qr_parsed["year_of_birth"]))

        if not result.gender.value and qr_parsed.get("gender"):
            result.gender = AadhaarField(value=qr_parsed["gender"], confidence=0.95, raw=qr_parsed["gender"])
        if not result.address.value and qr_parsed.get("address"):
            result.address = AadhaarField(value=qr_parsed["address"], confidence=0.95, raw=qr_parsed["address"])

    # ── Profile Compatibility Assessment ──────────────────────────────────────
    primary_fields_count = sum(1 for f in [result.identity_number.value, result.name.value, result.dob.value, result.year_of_birth.value] if f)
    if not has_nid_indicator and primary_fields_count == 0 and not result.qr_decoded:
        result.unsupported_layout = True
        logger.warning("Aadhaar parser: document lacks recognizable Aadhaar layout or fields.")

    return result


# Backward compatibility alias
parse_national_id = parse_aadhaar
