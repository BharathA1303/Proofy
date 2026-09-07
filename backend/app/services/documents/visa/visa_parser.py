"""
backend/app/services/documents/visa/visa_parser.py

Deterministic Visa field extraction from raw OCR regions.
Extracts VIZ labels and optional Machine-Readable Zone (MRV) data.
Preserves bounding boxes and OCR confidence scores.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from app.schemas.ocr import OCRRegionRaw
from app.services.documents.visa.visa_field_normalizer import (
    normalize_entries,
    normalize_visa_date,
    normalize_visa_number,
    normalize_visa_text,
)

logger = logging.getLogger(__name__)


@dataclass
class VisaField:
    """A single parsed visa field with provenance and quality telemetry."""
    value: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[List[List[int]]] = None
    raw: Optional[str] = None


@dataclass
class ParsedVisaData:
    """Structured fields extracted from a Visa document."""
    docNumber: VisaField = field(default_factory=VisaField)       # Visa number
    passportNumber: VisaField = field(default_factory=VisaField)  # Linked passport reference
    name: VisaField = field(default_factory=VisaField)            # Full Name / Bearer
    dob: VisaField = field(default_factory=VisaField)             # Date of birth
    nationality: VisaField = field(default_factory=VisaField)     # Nationality
    visaType: VisaField = field(default_factory=VisaField)        # Visa type / classification
    visaCategory: VisaField = field(default_factory=VisaField)    # Category (e.g. B1/B2, Tourist)
    issuedDate: VisaField = field(default_factory=VisaField)      # Date of issue
    expiry: VisaField = field(default_factory=VisaField)          # Date of expiry
    entries: VisaField = field(default_factory=VisaField)         # Number of entries (SINGLE, MULTIPLE)
    durationOfStay: VisaField = field(default_factory=VisaField)  # Allowed stay (e.g. 90 DAYS)
    authority: VisaField = field(default_factory=VisaField)       # Issuing post / authority
    mrz_line1: VisaField = field(default_factory=VisaField)       # Optional MRV line 1
    mrz_line2: VisaField = field(default_factory=VisaField)       # Optional MRV line 2


def parse_visa(
    regions: List[OCRRegionRaw],
    image_height: Optional[int] = None,
) -> ParsedVisaData:
    """
    Extract structured fields from OCR detected text regions on a Visa image.

    Pipeline:
      1. Check for optional MRV lines (MRV-A or MRV-B format).
      2. Scan text lines for labeled Visual Inspection Zone (VIZ) patterns.
      3. Normalize field values and retain bounding boxes/confidence.
    """
    result = ParsedVisaData()
    if not regions:
        return result

    # ── Step 1: Detect optional MRV lines ─────────────────────────────────────
    mrv_candidates = []
    for r in regions:
        txt = r.text.strip().replace(" ", "").upper()
        if any(kw in txt for kw in ("MACHINE", "READABLE", "ZONE", "IMMIGRATION", "CONTROL")):
            continue
        # Look for typical MRV prefixes: V< or VN or lines consisting of [A-Z0-9<] of length 35-46
        if len(txt) in range(35, 46) and "<" in txt and (txt.startswith("V<") or txt.startswith("V")):
            mrv_candidates.append(r)
        elif len(txt) in range(35, 46) and txt.count("<") >= 3:
            mrv_candidates.append(r)

    if len(mrv_candidates) >= 2:
        # Sort by vertical position (y coordinate of top-left)
        mrv_candidates.sort(key=lambda r: r.bbox[0][1] if r.bbox else 0)
        l1_reg = mrv_candidates[-2]
        l2_reg = mrv_candidates[-1]
        result.mrz_line1 = VisaField(
            value=l1_reg.text.strip(),
            confidence=l1_reg.confidence,
            bbox=l1_reg.bbox,
            raw=l1_reg.text,
        )
        result.mrz_line2 = VisaField(
            value=l2_reg.text.strip(),
            confidence=l2_reg.confidence,
            bbox=l2_reg.bbox,
            raw=l2_reg.text,
        )
        _extract_from_mrv(result, l1_reg.text.strip(), l2_reg.text.strip(), l1_reg.confidence, l2_reg.confidence)

    # ── Step 2: VIZ Field Extraction via Labels and Patterns ───────────────────
    # Combine lines for sliding pattern inspection
    lines: List[tuple[str, float, List[List[int]]]] = [
        (r.text.strip(), r.confidence, r.bbox) for r in regions
    ]

    for idx, (text, conf, bbox) in enumerate(lines):
        clean_upper = text.upper()

        # Visa Number / Document Number
        if not result.docNumber.value:
            m_num = re.search(r"(?:VISA\s*(?:NO|NUMBER|#)?|CONTROL\s*NO)\s*[:.\-]?\s*([A-Z0-9]{6,14})", clean_upper)
            if m_num:
                norm_val = normalize_visa_number(m_num.group(1))
                if norm_val:
                    result.docNumber = VisaField(value=norm_val, confidence=conf, bbox=bbox, raw=m_num.group(1))
            elif "VISA NO" in clean_upper and idx + 1 < len(lines):
                next_text = lines[idx + 1][0]
                norm_val = normalize_visa_number(next_text)
                if norm_val and len(norm_val) >= 6:
                    result.docNumber = VisaField(value=norm_val, confidence=lines[idx + 1][1], bbox=lines[idx + 1][2], raw=next_text)

        # Passport Number (Reference Document)
        if not result.passportNumber.value:
            m_ppt = re.search(r"(?:PASSPORT\s*(?:NO|NUMBER|#)?|PPT\s*NO|TRAVEL\s*DOC)\s*[:.\-]?\s*([A-Z0-9]{6,12})", clean_upper)
            if m_ppt:
                norm_val = normalize_visa_number(m_ppt.group(1))
                if norm_val:
                    result.passportNumber = VisaField(value=norm_val, confidence=conf, bbox=bbox, raw=m_ppt.group(1))
            elif "PASSPORT NO" in clean_upper and idx + 1 < len(lines):
                next_text = lines[idx + 1][0]
                norm_val = normalize_visa_number(next_text)
                if norm_val and len(norm_val) >= 6:
                    result.passportNumber = VisaField(value=norm_val, confidence=lines[idx + 1][1], bbox=lines[idx + 1][2], raw=next_text)

        # Full Name / Bearer
        if not result.name.value:
            m_name = re.search(r"(?:NAME|BEARER|FULL\s*NAME|SURNAME)\s*[:.\-]?\s*([A-Z\s]{3,35})", clean_upper)
            if m_name and not any(kw in m_name.group(1) for kw in ["PASSPORT", "NUMBER", "VALID", "EXPIRY", "BIRTH"]):
                norm_val = normalize_visa_text(m_name.group(1))
                if norm_val and len(norm_val) >= 3:
                    result.name = VisaField(value=norm_val, confidence=conf, bbox=bbox, raw=m_name.group(1))
            elif "NAME" in clean_upper and idx + 1 < len(lines):
                next_text = lines[idx + 1][0]
                if not any(kw in next_text.upper() for kw in ["VISA", "DATE", "NUMBER", "EXPIRY"]):
                    norm_val = normalize_visa_text(next_text)
                    if norm_val and len(norm_val) >= 3:
                        result.name = VisaField(value=norm_val, confidence=lines[idx + 1][1], bbox=lines[idx + 1][2], raw=next_text)

        # Date of Birth
        if not result.dob.value:
            m_dob = re.search(r"(?:DOB|DATE\s*OF\s*BIRTH|BIRTH\s*DATE)\s*[:.\-]?\s*(\d{4}[\s\-\./]\d{1,2}[\s\-\./]\d{1,2}|\d{1,2}[\s\-\./][A-Za-z0-9]{1,9}[\s\-\./]\d{2,4})", clean_upper)
            if m_dob:
                norm_val = normalize_visa_date(m_dob.group(1))
                if norm_val:
                    result.dob = VisaField(value=norm_val, confidence=conf, bbox=bbox, raw=m_dob.group(1))
            elif re.search(r"\b(?:DOB|BIRTH)\b", clean_upper) and idx + 1 < len(lines):
                norm_val = normalize_visa_date(lines[idx + 1][0])
                if norm_val:
                    result.dob = VisaField(value=norm_val, confidence=lines[idx + 1][1], bbox=lines[idx + 1][2], raw=lines[idx + 1][0])

        # Nationality
        if not result.nationality.value:
            m_nat = re.search(r"(?:NATIONALITY|CITIZENSHIP|NAT)\s*[:.\-]?\s*([A-Z]{3,20})", clean_upper)
            if m_nat:
                norm_val = normalize_visa_text(m_nat.group(1))
                if norm_val:
                    result.nationality = VisaField(value=norm_val, confidence=conf, bbox=bbox, raw=m_nat.group(1))
            elif "NATIONALITY" in clean_upper and idx + 1 < len(lines):
                next_text = lines[idx + 1][0]
                norm_val = normalize_visa_text(next_text)
                if norm_val and len(norm_val) >= 3:
                    result.nationality = VisaField(value=norm_val, confidence=lines[idx + 1][1], bbox=lines[idx + 1][2], raw=next_text)

        # Visa Type / Category
        if not result.visaType.value:
            m_type = re.search(r"(?:VISA\s*TYPE|TYPE|CLASS|CATEGORY)\s*[:.\-]?\s*([A-Z0-9\/\-\s]{1,15})", clean_upper)
            if m_type and not any(kw in m_type.group(1) for kw in ["PASSPORT", "NUMBER", "EXPIRY", "VALID"]):
                norm_val = normalize_visa_text(m_type.group(1))
                if norm_val:
                    result.visaType = VisaField(value=norm_val, confidence=conf, bbox=bbox, raw=m_type.group(1))
                    result.visaCategory = VisaField(value=norm_val, confidence=conf, bbox=bbox, raw=m_type.group(1))

        # Issue Date
        if not result.issuedDate.value:
            m_iss = re.search(r"(?:ISSUE\s*DATE|DATE\s*OF\s*ISSUE|VALID\s*FROM|ISSUED)\s*[:.\-]?\s*(\d{4}[\s\-\./]\d{1,2}[\s\-\./]\d{1,2}|\d{1,2}[\s\-\./][A-Za-z0-9]{1,9}[\s\-\./]\d{2,4})", clean_upper)
            if m_iss:
                norm_val = normalize_visa_date(m_iss.group(1))
                if norm_val:
                    result.issuedDate = VisaField(value=norm_val, confidence=conf, bbox=bbox, raw=m_iss.group(1))
            elif any(kw in clean_upper for kw in ("ISSUE DATE", "DATE OF ISSUE", "VALID FROM")):
                for look in range(1, min(5, len(lines) - idx)):
                    txt_cand = lines[idx + look][0]
                    norm_val = normalize_visa_date(txt_cand)
                    if norm_val:
                        result.issuedDate = VisaField(value=norm_val, confidence=lines[idx + look][1], bbox=lines[idx + look][2], raw=txt_cand)
                        break

        # Expiry Date
        if not result.expiry.value:
            m_exp = re.search(r"(?:EXPIRY\s*DATE|DATE\s*OF\s*EXPIRY|VALID\s*UNTIL|EXPIRES)\s*[:.\-]?\s*(\d{4}[\s\-\./]\d{1,2}[\s\-\./]\d{1,2}|\d{1,2}[\s\-\./][A-Za-z0-9]{1,9}[\s\-\./]\d{2,4})", clean_upper)
            if m_exp:
                norm_val = normalize_visa_date(m_exp.group(1))
                if norm_val:
                    result.expiry = VisaField(value=norm_val, confidence=conf, bbox=bbox, raw=m_exp.group(1))
            elif any(kw in clean_upper for kw in ("EXPIRY", "VALID UNTIL", "EXPIRES")):
                for look in range(1, min(5, len(lines) - idx)):
                    txt_cand = lines[idx + look][0]
                    norm_val = normalize_visa_date(txt_cand)
                    if norm_val:
                        result.expiry = VisaField(value=norm_val, confidence=lines[idx + look][1], bbox=lines[idx + look][2], raw=txt_cand)
                        break

        # Entries
        if not result.entries.value:
            m_ent = re.search(r"(?:ENTRIES|NO\s*OF\s*ENTRIES|ENTRY)\s*[:.\-]?\s*(SINGLE|MULTIPLE|MULT|[0-9]|M|S)", clean_upper)
            if m_ent:
                norm_val = normalize_entries(m_ent.group(1))
                if norm_val:
                    result.entries = VisaField(value=norm_val, confidence=conf, bbox=bbox, raw=m_ent.group(1))

        # Issuing Authority / Place of Issue
        if not result.authority.value:
            m_auth = re.search(r"(?:AUTHORITY|ISSUING\s*POST|ISSUED\s*AT|PLACE\s*OF\s*ISSUE)\s*[:.\-]?\s*([A-Z\s]{3,30})", clean_upper)
            if m_auth:
                norm_val = normalize_visa_text(m_auth.group(1))
                if norm_val:
                    result.authority = VisaField(value=norm_val, confidence=conf, bbox=bbox, raw=m_auth.group(1))

    return result


def _extract_from_mrv(
    data: ParsedVisaData,
    line1: str,
    line2: str,
    conf1: float,
    conf2: float,
) -> None:
    """Extract fields from standard MRV lines when available."""
    # Line 1: V<[3-letter nationality][surname]<<[given_names]...
    if len(line1) >= 10:
        nat_code = line1[2:5].replace("<", "").strip()
        if nat_code and not data.nationality.value:
            data.nationality = VisaField(value=nat_code, confidence=conf1, raw=nat_code)

        names_part = line1[5:].strip("<")
        if "<<" in names_part and not data.name.value:
            parts = names_part.split("<<")
            surname = parts[0].replace("<", " ").strip()
            given = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
            full_name = f"{given} {surname}".strip()
            data.name = VisaField(value=full_name, confidence=conf1, raw=full_name)

    # Line 2: [doc_num 9 chars][check][nationality 3 chars][dob 6 chars][check][sex 1 char][exp 6 chars]...
    if len(line2) >= 27:
        doc_no = line2[0:9].replace("<", "").strip()
        if doc_no and not data.docNumber.value:
            data.docNumber = VisaField(value=doc_no, confidence=conf2, raw=doc_no)

        # DOB: positions 13-19 (YYMMDD)
        dob_raw = line2[13:19]
        if re.match(r"^\d{6}$", dob_raw) and not data.dob.value:
            yy, mm, dd = dob_raw[0:2], dob_raw[2:4], dob_raw[4:6]
            yr = int(yy)
            full_yr = (1900 + yr) if yr >= 30 else (2000 + yr)
            data.dob = VisaField(value=f"{full_yr}-{mm}-{dd}", confidence=conf2, raw=dob_raw)

        # Expiry: positions 21-27 (YYMMDD)
        exp_raw = line2[21:27]
        if re.match(r"^\d{6}$", exp_raw) and not data.expiry.value:
            yy, mm, dd = exp_raw[0:2], exp_raw[2:4], exp_raw[4:6]
            yr = int(yy)
            full_yr = 2000 + yr
            data.expiry = VisaField(value=f"{full_yr}-{mm}-{dd}", confidence=conf2, raw=exp_raw)
