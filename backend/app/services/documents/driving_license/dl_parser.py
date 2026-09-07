"""
backend/app/services/documents/driving_license/dl_parser.py

Deterministic Driving License field extraction from raw OCR regions.
Focused on Indian Driving Licence (MoRTH / Sarathi standard).
Preserves bounding boxes, confidence scores, and raw OCR text.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.schemas.ocr import OCRRegionRaw
from app.services.documents.driving_license.dl_field_normalizer import (
    extract_state_from_license_number,
    normalize_blood_group,
    normalize_dl_date,
    normalize_dl_text,
    normalize_license_number,
    normalize_vehicle_classes,
)

logger = logging.getLogger(__name__)


@dataclass
class DLField:
    """A single parsed driving license field with provenance and telemetry."""
    value: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[List[List[int]]] = None
    raw: Optional[str] = None


@dataclass
class ParsedDrivingLicenseData:
    """Structured fields extracted from a Driving License document."""
    license_number: DLField = field(default_factory=DLField)
    docNumber: DLField = field(default_factory=DLField)          # Canonical alias to license_number
    name: DLField = field(default_factory=DLField)
    dob: DLField = field(default_factory=DLField)
    valid_from: DLField = field(default_factory=DLField)
    valid_to: DLField = field(default_factory=DLField)
    issuedDate: DLField = field(default_factory=DLField)          # Canonical alias to valid_from
    expiry: DLField = field(default_factory=DLField)              # Canonical alias to valid_to
    blood_group: DLField = field(default_factory=DLField)
    vehicle_classes: DLField = field(default_factory=DLField)
    issuing_authority: DLField = field(default_factory=DLField)
    state: DLField = field(default_factory=DLField)
    address: DLField = field(default_factory=DLField)
    unsupported_layout: bool = False


def parse_driving_license(
    regions: List[OCRRegionRaw],
    image_height: Optional[int] = None,
) -> ParsedDrivingLicenseData:
    """
    Extract structured fields from OCR regions on a Driving License image.

    Pipeline:
      1. Inspect OCR regions for Indian DL structure.
      2. Extract license number, bearer name, DOB, validity dates, COV, blood group.
      3. Normalize values conservatively.
      4. Detect unsupported layout or low recognition confidence without guessing.
    """
    result = ParsedDrivingLicenseData()
    if not regions:
        result.unsupported_layout = True
        return result

    lines: List[Tuple[str, float, List[List[int]]]] = [
        (r.text.strip(), r.confidence, r.bbox) for r in regions if r.text.strip()
    ]
    all_text_combined = " ".join([t[0].upper() for t in lines])

    # Check for general Driving License indication
    dl_indicators = [
        "DRIVING", "LICENCE", "LICENSE", "UNION OF INDIA",
        "TRANSPORT", "DL NO", "FORM 7", "SARATHI",
    ]
    has_dl_indicator = any(kw in all_text_combined for kw in dl_indicators)

    # ── Field 1: License Number ──────────────────────────────────────────────
    for idx, (text, conf, bbox) in enumerate(lines):
        clean_upper = text.upper()

        # Regex for labeled DL No: e.g. DL NO : DL0420110012345 or LICENCE NO: TN09 20201234567
        m_labeled = re.search(
            r"(?:DL\s*(?:NO|NUM|NUMBER|#)?|LICENCE\s*(?:NO|NUM)?|LICENSE\s*(?:NO|NUM)?)\s*[:.\-]?\s*([A-Z]{2}[-\s]?\d{2}[-\s]?(?:19|20)?\d{2,4}[-\s]?\d{4,8})",
            clean_upper,
        )
        if m_labeled and not result.license_number.value:
            norm_val = normalize_license_number(m_labeled.group(1))
            if norm_val and len(norm_val) >= 9:
                result.license_number = DLField(value=norm_val, confidence=conf, bbox=bbox, raw=m_labeled.group(1))
                break

        # Check next line if label is alone
        if clean_upper in ("DL NO", "DL NO.", "LICENCE NO", "LICENCE NO.", "LICENSE NO", "LICENSE NO.") and idx + 1 < len(lines):
            next_text = lines[idx + 1][0]
            norm_val = normalize_license_number(next_text)
            if norm_val and len(norm_val) >= 9:
                result.license_number = DLField(value=norm_val, confidence=lines[idx + 1][1], bbox=lines[idx + 1][2], raw=next_text)
                break

        # Direct pattern match: e.g. TN0920201234567 or DL0420110012345 (2 letters, 2 digits, 4 digits year, 7 digits seq)
        m_direct = re.search(r"\b([A-Z]{2}[-\s]?\d{2}[-\s]?(?:19|20)\d{2}[-\s]?\d{7})\b", clean_upper)
        if m_direct and not result.license_number.value:
            norm_val = normalize_license_number(m_direct.group(1))
            if norm_val:
                result.license_number = DLField(value=norm_val, confidence=conf, bbox=bbox, raw=m_direct.group(1))
                break

    # Alias docNumber to license_number
    result.docNumber = result.license_number

    # Infer State if license number is found
    if result.license_number.value:
        state_name = extract_state_from_license_number(result.license_number.value)
        if state_name:
            result.state = DLField(value=state_name, confidence=result.license_number.confidence, raw=result.license_number.value[:2])

    # ── Field 2: Date of Birth (DOB) ─────────────────────────────────────────
    for idx, (text, conf, bbox) in enumerate(lines):
        clean_upper = text.upper()
        m_dob = re.search(
            r"(?:DOB|D\.O\.B|DATE\s*OF\s*BIRTH|BIRTH\s*DATE)\s*[:.\-]?\s*([0-9A-Za-z\/\.\-]+)",
            clean_upper,
        )
        if m_dob and not result.dob.value:
            norm_dob = normalize_dl_date(m_dob.group(1))
            if norm_dob:
                result.dob = DLField(value=norm_dob, confidence=conf, bbox=bbox, raw=m_dob.group(1))
                break

        if any(kw in clean_upper for kw in ("DOB", "D.O.B", "DATE OF BIRTH", "DATE OFBIRTH", "BIRTH DATE")):
            # Check up to 3 lines forward for date
            for look_ahead in range(1, min(4, len(lines) - idx)):
                candidate_text = lines[idx + look_ahead][0]
                m_dt = re.search(r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", candidate_text)
                if m_dt:
                    norm_dob = normalize_dl_date(m_dt.group(1))
                    if norm_dob:
                        result.dob = DLField(value=norm_dob, confidence=lines[idx + look_ahead][1], bbox=lines[idx + look_ahead][2], raw=candidate_text)
                        break
            if result.dob.value:
                break

    # ── Field 3: Name ────────────────────────────────────────────────────────
    for idx, (text, conf, bbox) in enumerate(lines):
        clean_upper = text.upper()
        # Labeled Name
        m_name = re.search(
            r"(?:NAME|HOLDER(?:'S)?\s*NAME|BEARER)\s*[:.\-]?\s*([A-Z\s]{2,40})",
            clean_upper,
        )
        if m_name and not result.name.value:
            candidate = m_name.group(1).strip()
            # Avoid picking up labels
            if candidate and not any(kw in candidate for kw in ("DATE", "DOB", "VALID", "FATHER", "S/O", "ADDRESS", "INDIAN")):
                norm_name = normalize_dl_text(candidate)
                if norm_name and len(norm_name) >= 2:
                    result.name = DLField(value=norm_name, confidence=conf, bbox=bbox, raw=candidate)
                    break

        if any(clean_upper == kw for kw in ("NAME", "NAME:", "HOLDER NAME", "HOLDER NAME:", "HOLDER'S NAME:", "BEARER NAME:")) and idx + 1 < len(lines):
            next_text = lines[idx + 1][0]
            norm_name = normalize_dl_text(next_text)
            if norm_name and len(norm_name) >= 2 and not any(kw in norm_name for kw in ("DOB", "VALID", "FATHER", "ADDRESS", "INDIAN")):
                result.name = DLField(value=norm_name, confidence=lines[idx + 1][1], bbox=lines[idx + 1][2], raw=next_text)
                break

    # Fallback name search: line before DOB or S/O line
    if not result.name.value:
        for idx, (text, conf, bbox) in enumerate(lines):
            clean_upper = text.upper()
            if "S/O" in clean_upper or "D/O" in clean_upper or "W/O" in clean_upper or "SON/DAUGHTER" in clean_upper:
                if idx > 0:
                    prev_text = lines[idx - 1][0]
                    norm_prev = normalize_dl_text(prev_text)
                    if norm_prev and not any(kw in norm_prev for kw in ("LICENCE", "UNION", "INDIA", "TRANSPORT", "DL", "DATE")):
                        result.name = DLField(value=norm_prev, confidence=lines[idx - 1][1], bbox=lines[idx - 1][2], raw=prev_text)
                        break

    # ── Field 4: Validity Dates (valid_from, valid_to) ───────────────────────
    for idx, (text, conf, bbox) in enumerate(lines):
        clean_upper = text.upper()

        # Expiry / Valid Till / Validity (NT)
        m_expiry = re.search(
            r"(?:VALID\s*(?:TILL|UPTO|UNTIL|TO)|VALIDITY\s*(?:\(NT\)|\(TR\))?|EXPIRY(?:\s*DATE)?)\s*[:.\-]?\s*([0-9A-Za-z\/\.\-]+)",
            clean_upper,
        )
        if m_expiry and not result.valid_to.value:
            norm_exp = normalize_dl_date(m_expiry.group(1))
            if norm_exp:
                result.valid_to = DLField(value=norm_exp, confidence=conf, bbox=bbox, raw=m_expiry.group(1))
                result.expiry = result.valid_to

        if any(kw in clean_upper for kw in ("VALID TILL", "VALIDITY (NT)", "VALIDITY(NT)", "VALID UPTO", "VALID UNTIL", "EXPIRY")) and not result.valid_to.value:
            # Check up to 4 lines forward for date
            for look_ahead in range(1, min(5, len(lines) - idx)):
                candidate_text = lines[idx + look_ahead][0]
                m_dt = re.search(r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", candidate_text)
                if m_dt:
                    norm_exp = normalize_dl_date(m_dt.group(1))
                    if norm_exp:
                        result.valid_to = DLField(value=norm_exp, confidence=lines[idx + look_ahead][1], bbox=lines[idx + look_ahead][2], raw=candidate_text)
                        result.expiry = result.valid_to
                        break

        # Valid From / Date of Issue
        m_doi = re.search(
            r"(?:VALID\s*FROM|ISSUE\s*DATE|DATE\s*OF\s*(?:FIRST\s*)?ISSUE|DOI)\s*[:.\-]?\s*([0-9A-Za-z\/\.\-]+)",
            clean_upper,
        )
        if m_doi and not result.valid_from.value:
            norm_doi = normalize_dl_date(m_doi.group(1))
            if norm_doi:
                result.valid_from = DLField(value=norm_doi, confidence=conf, bbox=bbox, raw=m_doi.group(1))
                result.issuedDate = result.valid_from

        if any(kw in clean_upper for kw in ("ISSUE DATE", "ISSUEDATE", "DATE OF ISSUE", "DATE OF FIRST ISSUE", "VALID FROM")) and not result.valid_from.value:
            for look_ahead in range(1, min(5, len(lines) - idx)):
                candidate_text = lines[idx + look_ahead][0]
                m_dt = re.search(r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", candidate_text)
                if m_dt:
                    norm_doi = normalize_dl_date(m_dt.group(1))
                    if norm_doi:
                        result.valid_from = DLField(value=norm_doi, confidence=lines[idx + look_ahead][1], bbox=lines[idx + look_ahead][2], raw=candidate_text)
                        result.issuedDate = result.valid_from
                        break

    # Date Chronology Resolution: If valid_to is <= valid_from or equal, find the future date
    if result.valid_from.value and (not result.valid_to.value or result.valid_to.value <= result.valid_from.value):
        found_dates = []
        for text, conf, bbox in lines:
            for m in re.finditer(r"\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b", text):
                nd = normalize_dl_date(m.group(1))
                if nd and nd > result.valid_from.value:
                    found_dates.append((nd, conf, bbox, m.group(1)))
        if found_dates:
            # Pick latest future date as valid_to
            found_dates.sort(key=lambda x: x[0], reverse=True)
            result.valid_to = DLField(value=found_dates[0][0], confidence=found_dates[0][1], bbox=found_dates[0][2], raw=found_dates[0][3])
            result.expiry = result.valid_to

    # ── Field 5: Blood Group ─────────────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_bg = re.search(
            r"(?:BLOOD\s*(?:GRP|GROUP)?|BG)\s*[:.\-]?\s*([A-Z0-9\+\-]+)",
            clean_upper,
        )
        if m_bg and not result.blood_group.value:
            norm_bg = normalize_blood_group(m_bg.group(1))
            if norm_bg:
                result.blood_group = DLField(value=norm_bg, confidence=conf, bbox=bbox, raw=m_bg.group(1))
                break

    # ── Field 6: Vehicle Classes (COV) ───────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        if any(kw in clean_upper for kw in ("COV", "CLASS OF VEHICLE", "VEHICLE CLASS", "AUTHORISATION TO DRIVE")):
            classes = normalize_vehicle_classes(clean_upper)
            if classes and not result.vehicle_classes.value:
                result.vehicle_classes = DLField(
                    value=", ".join(classes),
                    confidence=conf,
                    bbox=bbox,
                    raw=clean_upper,
                )
                break

    # ── Field 7: Issuing Authority / RTO ─────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_auth = re.search(
            r"(?:RTO|DTO|ISSUING\s*AUTHORITY|LICENSING\s*AUTHORITY)\s*[:.\-]?\s*([A-Za-z0-9\s,\-]+)",
            clean_upper,
        )
        if m_auth and not result.issuing_authority.value:
            norm_auth = normalize_dl_text(m_auth.group(1))
            if norm_auth and len(norm_auth) >= 3:
                result.issuing_authority = DLField(value=norm_auth, confidence=conf, bbox=bbox, raw=m_auth.group(1))
                break

    # ── Profile Compatibility Assessment ─────────────────────────────────────
    # If there are zero indicators and no primary fields, flag unsupported layout
    primary_fields_count = sum(1 for f in [result.license_number.value, result.name.value, result.dob.value] if f)
    if not has_dl_indicator and primary_fields_count == 0:
        result.unsupported_layout = True
        logger.warning("Driving license parser: document lacks recognizable DL layout or fields.")

    return result
