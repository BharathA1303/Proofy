"""
backend/app/services/documents/pan_card/pan_card_parser.py

PAN Card field extraction from raw OCR regions.
Permanent Account Number card issued by Income Tax Department of India.

PAN number format: AAAAA0000A (5 uppercase letters + 4 digits + 1 uppercase letter)
The 4th character encodes taxpayer category:
  P = Person, C = Company, H = Hindu Undivided Family, F = Firm,
  A = AOP (Association of Persons), T = Trust, etc.
The 5th character is the first letter of the surname (for persons).

Extracts: PAN number, name, father's name, DOB, issuing authority (ITD).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.ocr import OCRRegionRaw

logger = logging.getLogger(__name__)

# PAN number pattern: 5 uppercase letters + 4 digits + 1 uppercase letter
PAN_PATTERN = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z]{1})\b")

# Taxpayer category codes (4th character)
PAN_CATEGORY_MAP = {
    "P": "Individual / Person",
    "C": "Company",
    "H": "Hindu Undivided Family",
    "F": "Firm",
    "A": "Association of Persons",
    "T": "Trust",
    "B": "Body of Individuals",
    "L": "Local Authority",
    "J": "Artificial Juridical Person",
    "G": "Government",
}

_PAN_NOISE_TOKENS = (
    "INCOME", "TAX", "DEPARTMENT", "GOVERNMENT", "INDIA",
    "PERMANENT", "ACCOUNT", "NUMBER", "CARD", "ITD",
    "NSDL", "UTIITSL",
)


@dataclass
class PanCardField:
    """A single parsed PAN Card field with provenance."""
    value: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[List[List[int]]] = None
    raw: Optional[str] = None


@dataclass
class ParsedPanCardData:
    """Structured fields extracted from a PAN Card."""
    pan_number: PanCardField = field(default_factory=PanCardField)
    docNumber: PanCardField = field(default_factory=PanCardField)    # Canonical alias
    name: PanCardField = field(default_factory=PanCardField)
    father_name: PanCardField = field(default_factory=PanCardField)
    dob: PanCardField = field(default_factory=PanCardField)
    taxpayer_category: Optional[str] = None
    issuing_authority: PanCardField = field(default_factory=PanCardField)
    unsupported_layout: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "docNumber": self.docNumber.value or self.pan_number.value,
            "document_number": self.docNumber.value or self.pan_number.value,
            "pan_number": self.pan_number.value,
            "panNumber": self.pan_number.value,
            "name": self.name.value,
            "father_name": self.father_name.value,
            "fatherName": self.father_name.value,
            "dob": self.dob.value,
            "date_of_birth": self.dob.value,
            "taxpayer_category": self.taxpayer_category,
            "taxpayerCategory": self.taxpayer_category,
            "issuing_authority": self.issuing_authority.value,
            "authority": self.issuing_authority.value,
        }


def normalize_pan_number(raw: Optional[str]) -> Optional[str]:
    """Normalize PAN number to 10-char uppercase (AAAAA0000A)."""
    if not raw:
        return None
    clean = re.sub(r"[\s\-]", "", raw.strip().upper())
    m = PAN_PATTERN.search(clean)
    if m:
        return m.group(1)
    return None


def decode_pan_category(pan: str) -> Optional[str]:
    """Decode the taxpayer category from PAN's 4th character."""
    if pan and len(pan) >= 4:
        return PAN_CATEGORY_MAP.get(pan[3].upper(), "Unknown")
    return None


def parse_pan_card(
    regions: List[OCRRegionRaw],
    raw_qr_payload: Optional[str] = None,
) -> ParsedPanCardData:
    """
    Extract structured fields from OCR regions on a PAN Card image.
    """
    result = ParsedPanCardData()
    if not regions:
        result.unsupported_layout = True
        return result

    lines: List[Tuple[str, float, List[List[int]]]] = [
        (r.text.strip(), r.confidence, r.bbox) for r in regions if r.text.strip()
    ]
    all_text_combined = " ".join([t[0].upper() for t in lines])

    # Check for PAN indicators
    pan_indicators = [
        "INCOME TAX DEPARTMENT", "PERMANENT ACCOUNT NUMBER",
        "INCOME TAX", "ITD", "NSDL", "UTIITSL",
    ]
    has_pan_indicator = any(kw in all_text_combined for kw in pan_indicators)

    # ── Field 1: PAN Number ────────────────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        # Look for labeled PAN
        m_label = re.search(r"(?:PAN\s*(?:NO|NUMBER|#|:)?|PERMANENT\s*ACCOUNT\s*(?:NO|NUMBER)?)\s*[:\-]?\s*([A-Z]{5}[0-9]{4}[A-Z])", clean_upper)
        if m_label and not result.pan_number.value:
            result.pan_number = PanCardField(value=m_label.group(1), confidence=conf, bbox=bbox, raw=m_label.group(1))
            break

    # If not found by label, scan for standalone PAN pattern
    if not result.pan_number.value:
        for text, conf, bbox in lines:
            m = PAN_PATTERN.search(text.upper())
            if m:
                result.pan_number = PanCardField(value=m.group(1), confidence=conf, bbox=bbox, raw=m.group(1))
                break

    result.docNumber = result.pan_number

    # Decode taxpayer category from PAN
    if result.pan_number.value:
        result.taxpayer_category = decode_pan_category(result.pan_number.value)

    # ── Field 2: Name of Cardholder ──────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_name = re.search(r"(?:NAME|CARDHOLDER'?S?\s*NAME)\s*[:\-]?\s*([A-Z][A-Z\s.'-]{2,40})", clean_upper)
        if m_name and not result.name.value:
            cand = m_name.group(1).strip()
            if not any(tok in cand for tok in _PAN_NOISE_TOKENS):
                result.name = PanCardField(value=cand, confidence=conf, bbox=bbox, raw=cand)
                break

    # ── Field 3: Father's Name ────────────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_father = re.search(
            r"(?:FATHER'?S?\s*NAME|GUARDIAN'?S?\s*NAME|F/O|S/O)\s*[:\-]?\s*([A-Z][A-Z\s.'-]{2,40})",
            clean_upper,
        )
        if m_father and not result.father_name.value:
            cand = m_father.group(1).strip()
            if not any(tok in cand for tok in _PAN_NOISE_TOKENS):
                result.father_name = PanCardField(value=cand, confidence=conf, bbox=bbox, raw=cand)
                break

    # ── Field 4: Date of Birth ────────────────────────────────────────────────
    for text, conf, bbox in lines:
        clean_upper = text.upper()
        m_dob = re.search(
            r"(?:DATE\s*OF\s*BIRTH|DOB|D\.O\.B|BIRTH\s*DATE|JANM\s*TITHI)\s*[:\-]?\s*(\d{1,2}[\/.\-]\d{1,2}[\/.\-]\d{4})",
            clean_upper,
        )
        if m_dob and not result.dob.value:
            result.dob = PanCardField(value=m_dob.group(1), confidence=conf, bbox=bbox, raw=m_dob.group(1))
            break

    # ── Field 5: Issuing Authority ────────────────────────────────────────────
    if has_pan_indicator or "INCOME TAX" in all_text_combined:
        result.issuing_authority = PanCardField(
            value="Income Tax Department, Government of India",
            confidence=0.95,
            raw="INCOME TAX DEPARTMENT",
        )

    # ── Profile Compatibility Assessment ──────────────────────────────────────
    primary_count = sum(1 for f in [result.pan_number.value, result.name.value] if f)
    if not has_pan_indicator and primary_count == 0:
        result.unsupported_layout = True
        logger.warning("PAN parser: document lacks recognizable PAN card layout or fields.")

    return result
