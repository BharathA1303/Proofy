"""
backend/app/services/documents/border_permit/border_permit_parser.py

Deterministic Border Permit field extraction from raw OCR regions.
Focused on regional border crossing / entry permit reference layouts.
Preserves bounding boxes, confidence scores, and raw OCR text.

Crucial:
- Reuses common OCR engine; does not create a separate OCR engine.
- Extracts permit number, bearer name, DOB, linked passport number, validity dates,
  permit type, and border entry point.
- Flags ambiguous identifiers rather than silently guessing OCR misreads.
- Unsupported layouts return unsupported_layout=True without hallucination.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.ocr import OCRRegionRaw
from app.services.documents.border_permit.border_permit_field_normalizer import (
    normalize_border_date,
    normalize_holder_name,
    normalize_permit_number,
    normalize_permit_type,
)
from app.services.documents.border_permit.border_permit_qr_validator import (
    parse_border_permit_qr_payload,
)

logger = logging.getLogger(__name__)


@dataclass
class BorderPermitField:
    """A single parsed Border Permit field with provenance."""
    value: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[List[List[int]]] = None
    raw: Optional[str] = None


@dataclass
class ParsedBorderPermitData:
    """Structured fields extracted from a Border Permit document."""
    permit_number: BorderPermitField = field(default_factory=BorderPermitField)
    docNumber: BorderPermitField = field(default_factory=BorderPermitField)
    name: BorderPermitField = field(default_factory=BorderPermitField)
    dob: BorderPermitField = field(default_factory=BorderPermitField)
    nationality: BorderPermitField = field(default_factory=BorderPermitField)
    passport_number: BorderPermitField = field(default_factory=BorderPermitField)
    valid_from: BorderPermitField = field(default_factory=BorderPermitField)
    valid_to: BorderPermitField = field(default_factory=BorderPermitField)
    expiry: BorderPermitField = field(default_factory=BorderPermitField)
    permit_type: BorderPermitField = field(default_factory=BorderPermitField)
    border_zone: BorderPermitField = field(default_factory=BorderPermitField)
    port_of_entry: BorderPermitField = field(default_factory=BorderPermitField)
    issuing_authority: BorderPermitField = field(default_factory=BorderPermitField)
    qr_payload: Optional[str] = None
    qr_decoded: bool = False
    qr_parsed_data: Optional[Dict[str, Any]] = None
    is_ambiguous_identifier: bool = False
    unsupported_layout: bool = False
    unsupported_reasons: List[str] = field(default_factory=list)


class BorderPermitParser:
    """
    Parses raw OCR bounding boxes into structured Border Permit fields.
    """

    def parse(
        self,
        regions: List[Any],
        qr_payload: Optional[str] = None,
        image_height: Optional[int] = None,
    ) -> ParsedBorderPermitData:
        result = ParsedBorderPermitData()

        if not regions:
            result.unsupported_layout = True
            result.unsupported_reasons.append("Zero OCR regions provided.")
            return result

        # Pre-process lines
        lines: List[Tuple[str, float, Any]] = []
        for r in regions:
            text = getattr(r, "text", "") or ""
            conf = getattr(r, "confidence", 0.0) or 0.0
            bbox = getattr(r, "bbox", None)
            if text.strip():
                lines.append((text.strip(), conf, bbox))

        full_text = " ".join(t for t, _, _ in lines)

        # 1. Header & Layout plausibility check
        header_patterns = [
            r"BORDER\s*(?:CROSSING)?\s*PERMIT",
            r"ENTRY\s*PERMIT",
            r"BORDER\s*PASS",
            r"CROSSING\s*PERMIT",
            r"REGIONAL\s*ENTRY",
            r"SYNTHETIC\s*TEST\s*BORDER\s*PERMIT",
            r"PERMIT\s*NO",
        ]
        has_header = any(re.search(pat, full_text, re.IGNORECASE) for pat in header_patterns)

        # 2. Extract Permit Number
        permit_re = re.compile(r"(?:PERMIT\s*(?:NO|NUMBER|#)?|BP\s*NO)?\s*[:.-]?\s*(BP[- ]?(?:20\d{2}|19\d{2})[- ]?\d{6}|BP\d{6,12})", re.IGNORECASE)
        permit_match = None

        for text, conf, bbox in lines:
            m = permit_re.search(text)
            if m:
                raw_match = m.group(1)
                norm_num, is_ambig = normalize_permit_number(raw_match)
                result.permit_number = BorderPermitField(value=norm_num, confidence=conf, bbox=bbox, raw=raw_match)
                result.docNumber = BorderPermitField(value=norm_num, confidence=conf, bbox=bbox, raw=raw_match)
                result.is_ambiguous_identifier = is_ambig
                permit_match = True
                break

        # If not matched directly, check for standalone BP-YYYY-NNNNNN
        if not permit_match:
            standalone_re = re.compile(r"\b(BP[- ]?(?:20\d{2}|19\d{2})[- ]?[0-9OIlBD]{6})\b", re.IGNORECASE)
            for text, conf, bbox in lines:
                m = standalone_re.search(text)
                if m:
                    raw_match = m.group(1)
                    norm_num, is_ambig = normalize_permit_number(raw_match)
                    result.permit_number = BorderPermitField(value=norm_num, confidence=conf, bbox=bbox, raw=raw_match)
                    result.docNumber = BorderPermitField(value=norm_num, confidence=conf, bbox=bbox, raw=raw_match)
                    result.is_ambiguous_identifier = is_ambig
                    permit_match = True
                    break

        # 3. Extract Holder Name
        name_patterns = [
            r"(?:HOLDER\s*NAME|HOLDER|NAME|TRAVELER)\s*[:.-]?\s*([A-Z\s]{3,40})",
        ]
        for text, conf, bbox in lines:
            for pat in name_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    raw_val = m.group(1)
                    norm_name = normalize_holder_name(raw_val)
                    if norm_name and not any(h in norm_name for h in ["BORDER", "PERMIT", "AUTHORITY", "GOVERNMENT"]):
                        result.name = BorderPermitField(value=norm_name, confidence=conf, bbox=bbox, raw=raw_val)
                        break
            if result.name.value:
                break

        # 4. Extract Passport Reference
        passport_patterns = [
            r"(?:PASSPORT\s*(?:NO|NUMBER|#)?|PPT\s*NO|LINKED\s*PPT)\s*[:.-]?\s*([A-Z][0-9]{7,8}|[A-Z0-9]{6,9})",
        ]
        for text, conf, bbox in lines:
            for pat in passport_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    raw_val = m.group(1).strip().upper()
                    result.passport_number = BorderPermitField(value=raw_val, confidence=conf, bbox=bbox, raw=raw_val)
                    break
            if result.passport_number.value:
                break

        # 5. Extract Date of Birth
        dob_patterns = [
            r"(?:DOB|DATE\s*OF\s*BIRTH|BIRTH\s*DATE)\s*[:.-]?\s*([0-9A-Za-z\s/.-]{8,15})",
        ]
        for text, conf, bbox in lines:
            for pat in dob_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    raw_val = m.group(1).strip()
                    iso_dob = normalize_border_date(raw_val)
                    if iso_dob:
                        result.dob = BorderPermitField(value=iso_dob, confidence=conf, bbox=bbox, raw=raw_val)
                        break
            if result.dob.value:
                break

        # 6. Extract Validity Dates
        # Valid From
        from_patterns = [
            r"(?:VALID\s*(?:FROM)?|ISSUED|ISSUE\s*DATE|FROM)\s*[:.-]?\s*([0-9A-Za-z\s/.-]{8,15})",
        ]
        for text, conf, bbox in lines:
            for pat in from_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    raw_val = m.group(1).strip()
                    iso_date = normalize_border_date(raw_val)
                    if iso_date:
                        result.valid_from = BorderPermitField(value=iso_date, confidence=conf, bbox=bbox, raw=raw_val)
                        break
            if result.valid_from.value:
                break

        # Valid To / Expiry
        to_patterns = [
            r"(?:VALID\s*(?:TO|UNTIL|THRU|TILL)|EXPIRES?|EXPIRY|EXP\s*DATE|TO)\s*[:.-]?\s*([0-9A-Za-z\s/.-]{8,15})",
        ]
        for text, conf, bbox in lines:
            for pat in to_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    raw_val = m.group(1).strip()
                    iso_date = normalize_border_date(raw_val)
                    if iso_date:
                        result.valid_to = BorderPermitField(value=iso_date, confidence=conf, bbox=bbox, raw=raw_val)
                        result.expiry = BorderPermitField(value=iso_date, confidence=conf, bbox=bbox, raw=raw_val)
                        break
            if result.valid_to.value:
                break

        # 7. Extract Permit Type
        type_patterns = [
            r"(?:PERMIT\s*TYPE|CATEGORY|TYPE)\s*[:.-]?\s*([A-Za-z_\s]{4,25})",
        ]
        for text, conf, bbox in lines:
            for pat in type_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    raw_val = m.group(1).strip()
                    norm_type = normalize_permit_type(raw_val)
                    if norm_type:
                        result.permit_type = BorderPermitField(value=norm_type, confidence=conf, bbox=bbox, raw=raw_val)
                        break
            if result.permit_type.value:
                break

        # 8. Extract Port / Border Zone
        zone_patterns = [
            r"(?:PORT\s*(?:OF\s*ENTRY)?|BORDER\s*ZONE|ENTRY\s*PORT|CHECKPOST|BORDER\s*POST)\s*[:=]\s*([A-Za-z0-9\s-]{3,35})",
            r"(?:PORT\s+OF\s+ENTRY)\s*[:.-]?\s*([A-Za-z0-9\s-]{3,35})",
            r"(?:BORDER\s+ZONE)\s*[:.-]?\s*([A-Za-z0-9\s-]{3,35})",
        ]
        for text, conf, bbox in lines:
            for pat in zone_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    raw_val = m.group(1).strip().upper()
                    result.border_zone = BorderPermitField(value=raw_val, confidence=conf, bbox=bbox, raw=raw_val)
                    result.port_of_entry = BorderPermitField(value=raw_val, confidence=conf, bbox=bbox, raw=raw_val)
                    break
            if result.border_zone.value:
                break

        # 9. Extract Issuing Authority
        auth_patterns = [
            r"(?:ISSUING\s*AUTHORITY|AUTHORITY)\s*[:.-]?\s*([A-Za-z0-9\s-]{4,50})",
            r"(BORDER\s*(?:CONTROL|MANAGEMENT|SECURITY)\s*AUTHORITY)",
            r"(IMMIGRATION\s*(?:&|AND)?\s*BORDER\s*(?:SERVICE|CONTROL))",
        ]
        for text, conf, bbox in lines:
            for pat in auth_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    raw_val = m.group(1).strip()
                    result.issuing_authority = BorderPermitField(value=raw_val, confidence=conf, bbox=bbox, raw=raw_val)
                    break
            if result.issuing_authority.value:
                break

        # 10. QR Payload integration
        if qr_payload:
            result.qr_payload = qr_payload
            qr_res = parse_border_permit_qr_payload(qr_payload)
            result.qr_decoded = qr_res.get("decoded", False)
            result.qr_parsed_data = qr_res.get("fields")

        # 11. Layout validation check:
        # If neither header nor permit number is found, mark unsupported
        if not has_header and not result.permit_number.value:
            result.unsupported_layout = True
            result.unsupported_reasons.append("Document lacks recognizable Border Permit markers or permit number.")

        return result


def parse_border_permit(
    regions: List[Any],
    qr_payload: Optional[str] = None,
    image_height: Optional[int] = None,
) -> ParsedBorderPermitData:
    """Convenience module function matching parse_passport/parse_visa/parse_dl."""
    return BorderPermitParser().parse(regions, qr_payload=qr_payload, image_height=image_height)
