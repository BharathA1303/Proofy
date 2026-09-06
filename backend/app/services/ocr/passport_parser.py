"""
backend/app/services/ocr/passport_parser.py

Converts raw PaddleOCR regions into structured passport fields.

Architecture:
  Generic OCR Engine
        ↓
  PassportParser (this module)
        ↓
  PassportOCRResult (schemas/ocr.py)

Design rules:
  - NEVER invent or fabricate field values.
  - Return None for any field that OCR cannot reliably locate.
  - MRZ extraction ≠ MRZ validation.
    Presence of MRZ lines does NOT mean the document is authentic.
    ICAO 9303 checksum validation belongs to Module 2.
  - All regex patterns are permissive — we accept partial matches
    rather than silently discarding a field.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.services.ocr.ocr_engine import OCRRegion

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────

# ICAO TD3 MRZ: two lines of exactly 44 characters each
# Character set: A-Z 0-9 < (filler)
# We allow for minor OCR noise: spaces may appear as other characters
_MRZ_LINE_PATTERN = re.compile(r"^[A-Z0-9<\s]{39,46}$")

# Minimum characters in a line to be considered a candidate MRZ line
# OCR frequently merges repetitive filler characters (<), so candidate lines can be shorter
_MRZ_MIN_LEN = 20

# Passport number: 1 letter + 7 alphanumeric (ICAO format, Indian passports etc.)
_PASSPORT_NUMBER_PATTERN = re.compile(r"\b[A-Z]\d{7}\b")

# Date patterns (various regional formats OCR may produce)
_DATE_PATTERNS = [
    re.compile(r"\b(\d{2})[/\-\.](\d{2})[/\-\.](\d{4})\b"),   # DD/MM/YYYY
    re.compile(r"\b(\d{2})[/\-\.](\d{2})[/\-\.](\d{2})\b"),   # DD/MM/YY
    re.compile(r"\b(\d{2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{4})\b", re.I),
]

# 3-letter ISO nationality codes
_NATIONALITY_PATTERN = re.compile(r"\b(IND|USA|GBR|CAN|AUS|FRA|DEU|CHN|PAK|BGD|LKA|NPL|MMR|AFG|IRN|ARE|SAU|JPN|KOR|RUS|BRA|MEX|ZAF|NGA|KEN|EGY|THA|VNM|IDN|MYS|SGP|PHL|NZL|ARG|COL|PER|CHL|VEN|ECU|BOL|PRY|URY|GTM|CUB|DOM|HND|SLV|NIC|CRI|PAN|TTO|JAM|HTI|BHS|BRB|GUY|SUR|BLZ|GRD|ATG|VCT|KNA|DMA|LCA|TUN|MAR|DZA|LBY|SDN|ETH|GHA|CIV|SEN|MLI|BFA|NER|TCD|CMR|ZMB|ZWE|MOZ|MWI|TZA|UGA|RWA|BDI|SOM|ERI|DJI|COM|MDG|MUS|SYC|CPV|GNB|GNQ|GAB|COG|COD|CAF|SSD|UKR|POL|CZE|SVK|HUN|ROU|BGR|SRB|HRV|BIH|SVN|MKD|ALB|MNE|BLR|MDA|GEO|ARM|AZE|KAZ|UZB|TKM|KGZ|TJK|MNG|TUR|GRC|PRT|ESP|ITA|NLD|BEL|CHE|AUT|SWE|NOR|DNK|FIN|IRL|ISL|LUX|LIE|MCO|SMR|VAT|AND|MLT|CYP|ISR|JOR|LBN|SYR|IRQ|KWT|BHR|QAT|OMN|YEM|PSE)\b")

# Keywords that help locate specific fields
_FIELD_KEYWORDS = {
    "name":        ["surname", "given name", "given names", "name", "holder"],
    "dob":         ["date of birth", "birth date", "dob", "born"],
    "expiry":      ["date of expiry", "expiry", "expiration", "exp", "valid until", "valid thru"],
    "issuedDate":  ["date of issue", "issued", "issue date"],
    "authority":   ["issuing authority", "authority", "issued by", "issuer"],
    "nationality": ["nationality", "national"],
    "gender":      ["sex", "gender", "m/f"],
    "placeOfBirth":["place of birth", "birth place", "pob"],
}

# Gender normalisation
_GENDER_MAP = {
    "m": "M", "male": "M", "♂": "M",
    "f": "F", "female": "F", "♀": "F",
    "x": "X", "unspecified": "X",
}


# ──────────────────────────────────────────────
#  Internal data structures
# ──────────────────────────────────────────────

@dataclass
class ParsedField:
    value: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[list[list[int]]] = None


@dataclass
class PassportParseResult:
    name: ParsedField = field(default_factory=ParsedField)
    docNumber: ParsedField = field(default_factory=ParsedField)
    dob: ParsedField = field(default_factory=ParsedField)
    nationality: ParsedField = field(default_factory=ParsedField)
    gender: ParsedField = field(default_factory=ParsedField)
    placeOfBirth: ParsedField = field(default_factory=ParsedField)
    authority: ParsedField = field(default_factory=ParsedField)
    issuedDate: ParsedField = field(default_factory=ParsedField)
    expiry: ParsedField = field(default_factory=ParsedField)
    mrz_line1: ParsedField = field(default_factory=ParsedField)
    mrz_line2: ParsedField = field(default_factory=ParsedField)


# ──────────────────────────────────────────────
#  Helper utilities
# ──────────────────────────────────────────────

def _is_mrz_candidate(text: str) -> bool:
    """Return True if the text looks like a MRZ line."""
    # Remove spaces before checking length (OCR often adds small spaces in MRZ)
    compact = text.replace(" ", "").upper()
    if len(compact) < _MRZ_MIN_LEN:
        return False
    # A TD3 MRZ line must contain filler characters '<' or digits (dates/check digits)
    has_filler = "<" in compact
    has_digits = any(c.isdigit() for c in compact)
    if not has_filler and not has_digits:
        # Plain English text without fillers or digits (e.g. disclaimer banner) is not MRZ
        return False
    # If it starts with P< or contains filler markers <<, high probability MRZ candidate
    if compact.startswith("P<") or "<<" in compact:
        return True
    # High density of MRZ-valid characters
    valid_chars = sum(1 for c in compact if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")
    ratio = valid_chars / len(compact)
    return ratio >= 0.85


def _normalize_mrz_line(text: str) -> str:
    """
    Normalize a raw OCR MRZ line.
    - Collapse spaces (OCR may insert spaces within MRZ)
    - Map common OCR confusions: O→0, I→1 in numeric positions (conservative)
    - Uppercase
    """
    # Remove whitespace
    normalized = re.sub(r"\s+", "", text.upper())
    # Replace common OCR letter/digit confusions in MRZ context
    # These are extremely common: 0/O, 1/I are often confused
    # We only normalize if the resulting string has plausible MRZ structure
    # (conservative: just uppercase and strip, do not guess substitutions)
    return normalized


def _sort_regions_top_to_bottom(regions: list[OCRRegion]) -> list[OCRRegion]:
    """Sort OCR regions by their top-left Y coordinate (top of page first)."""
    def top_y(r: OCRRegion) -> int:
        if not r.bbox:
            return 0
        return min(pt[1] for pt in r.bbox)
    return sorted(regions, key=top_y)


def _get_text_below_keyword(
    regions: list[OCRRegion],
    keyword_text: str,
    max_y_gap: int = 60,
) -> Optional[tuple[str, float, list[list[int]]]]:
    """
    Find a region whose text is immediately below a region containing keyword_text.
    Returns (text, confidence, bbox) or None.
    """
    keyword_lower = keyword_text.lower()
    for i, region in enumerate(regions):
        if keyword_lower in region.text.lower():
            # Find the closest region below this one
            kw_bottom_y = max(pt[1] for pt in region.bbox) if region.bbox else 0
            kw_left_x = min(pt[0] for pt in region.bbox) if region.bbox else 0
            kw_right_x = max(pt[0] for pt in region.bbox) if region.bbox else 9999

            best: Optional[tuple[str, float, list[list[int]], int]] = None
            for j, candidate in enumerate(regions):
                if j == i:
                    continue
                if not candidate.bbox:
                    continue
                cand_top_y = min(pt[1] for pt in candidate.bbox)
                cand_left_x = min(pt[0] for pt in candidate.bbox)
                # Must be below the keyword and within a vertical gap
                if 0 < (cand_top_y - kw_bottom_y) <= max_y_gap:
                    # Must have horizontal overlap
                    cand_right_x = max(pt[0] for pt in candidate.bbox)
                    if not (cand_right_x < kw_left_x or cand_left_x > kw_right_x):
                        gap = cand_top_y - kw_bottom_y
                        if best is None or gap < best[3]:
                            best = (candidate.text, candidate.confidence, candidate.bbox, gap)
            if best:
                return best[0], best[1], best[2]
    return None


# ──────────────────────────────────────────────
#  MRZ extraction
# ──────────────────────────────────────────────

def _extract_mrz(
    regions: list[OCRRegion],
    image_height: int,
) -> tuple[ParsedField, ParsedField]:
    """
    Identify and extract MRZ Line 1 and Line 2 from OCR regions.

    Strategy:
      1. Filter candidate regions (long, mostly MRZ characters, bottom 35% of image)
      2. Sort candidates by Y position
      3. Take the bottom two candidates as line1, line2

    Returns: (mrz_line1, mrz_line2) ParsedFields — values are None if not found.

    NOTE: This returns EXTRACTED lines only. Validation of checksums
    and ICAO structure belongs to Module 2.
    """
    mrz_zone_top = image_height * 0.55  # MRZ is typically in the bottom 45%

    candidates: list[tuple[int, OCRRegion]] = []  # (top_y, region)

    for region in regions:
        text = region.text
        if not _is_mrz_candidate(text):
            continue

        top_y = min(pt[1] for pt in region.bbox) if region.bbox else 0
        if top_y >= mrz_zone_top:
            candidates.append((top_y, region))

    # If we didn't find candidates in the bottom zone, search anywhere in the image
    if len(candidates) < 2:
        logger.debug("MRZ: Widening search to full image (found %d bottom-zone candidates)", len(candidates))
        candidates = []
        for region in regions:
            if _is_mrz_candidate(region.text):
                top_y = min(pt[1] for pt in region.bbox) if region.bbox else 0
                candidates.append((top_y, region))

    # Sort by vertical position
    candidates.sort(key=lambda x: x[0])

    line1 = ParsedField()
    line2 = ParsedField()

    if len(candidates) >= 2:
        # Take the two lowest (bottom-most) MRZ-like lines
        bottom_two = candidates[-2:]
        bottom_two.sort(key=lambda x: x[0])  # top one first

        r1 = bottom_two[0][1]
        r2 = bottom_two[1][1]

        raw1 = r1.text
        raw2 = r2.text
        norm1 = _normalize_mrz_line(raw1)
        norm2 = _normalize_mrz_line(raw2)

        # Sanity: line1 of a TD3 passport should start with P
        if norm1 and not norm1.startswith("P") and norm2.startswith("P"):
            raw1, raw2 = raw2, raw1
            norm1, norm2 = norm2, norm1
            r1, r2 = r2, r1

        line1 = ParsedField(value=norm1, confidence=r1.confidence, bbox=r1.bbox)
        line2 = ParsedField(value=norm2, confidence=r2.confidence, bbox=r2.bbox)

        logger.info("MRZ extracted: line1_len=%d line2_len=%d", len(norm1), len(norm2))

    elif len(candidates) == 1:
        r1 = candidates[0][1]
        norm1 = _normalize_mrz_line(r1.text)
        if norm1.startswith("P"):
            line1 = ParsedField(value=norm1, confidence=r1.confidence, bbox=r1.bbox)
        else:
            line2 = ParsedField(value=norm1, confidence=r1.confidence, bbox=r1.bbox)
        logger.info("MRZ: only one line found (len=%d)", len(norm1))
    else:
        logger.info("MRZ: no MRZ lines detected in this image.")

    return line1, line2


# ──────────────────────────────────────────────
#  MRZ field parsing
# ──────────────────────────────────────────────

def _parse_mrz_fields(
    mrz_line1: Optional[str],
    mrz_line2: Optional[str],
) -> dict[str, Optional[str]]:
    """
    Extract structured fields from MRZ lines.

    TD3 format (passport):
    Line 1 (44 chars): P<ISS<SURNAME<<GIVEN<NAMES<<<<<<<<<<<<<<<<<
    Line 2 (44 chars): DOCNUM0CISSDDMMYYBSEXDDMMYYBNAT<<<<<<<<<CD

    We extract what we can without performing checksum validation.
    Positions below are 1-indexed per ICAO Doc 9303 Part 4, Section 4.
    """
    parsed: dict[str, Optional[str]] = {
        "name_from_mrz": None,
        "docNumber_from_mrz": None,
        "nationality_from_mrz": None,
        "dob_from_mrz": None,
        "gender_from_mrz": None,
        "expiry_from_mrz": None,
    }

    if mrz_line1 and len(mrz_line1) >= 44:
        # Name parsing from line 1
        # Positions 6–44: SURNAME<<GIVEN<NAMES...
        name_field = mrz_line1[5:44]
        if "<<" in name_field:
            parts = name_field.split("<<")
            surname = parts[0].replace("<", " ").strip()
            given = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
            full_name = f"{surname} {given}".strip() if given else surname
            parsed["name_from_mrz"] = full_name if full_name else None
        elif name_field:
            parsed["name_from_mrz"] = name_field.replace("<", " ").strip() or None

    if mrz_line2 and len(mrz_line2) >= 43:
        # Doc number: positions 0–8 (9 chars, includes < filler)
        # Strip trailing < and whitespace
        doc_num_raw = mrz_line2[0:9].replace("<", "").strip()
        parsed["docNumber_from_mrz"] = doc_num_raw if doc_num_raw else None

        # Nationality: positions 10–12 (ICAO TD3)
        nat_raw = mrz_line2[10:13].replace("<", "").strip()
        parsed["nationality_from_mrz"] = nat_raw if nat_raw else None

        # Date of birth: positions 13–18 (0-indexed) — YYMMDD
        dob_raw = mrz_line2[13:19].strip()
        if re.match(r"^\d{6}$", dob_raw):
            yy, mm, dd = dob_raw[0:2], dob_raw[2:4], dob_raw[4:6]
            year = int(yy)
            full_year = (1900 + year) if year >= 30 else (2000 + year)
            parsed["dob_from_mrz"] = f"{dd}/{mm}/{full_year}"

        # Gender: position 20 (ICAO TD3)
        if len(mrz_line2) > 20:
            gender_raw = mrz_line2[20].strip().upper()
            if gender_raw in ("M", "F", "X"):
                parsed["gender_from_mrz"] = gender_raw

        # Expiry: positions 21–26 — YYMMDD
        if len(mrz_line2) >= 27:
            exp_raw = mrz_line2[21:27].strip()
            if re.match(r"^\d{6}$", exp_raw):
                yy, mm, dd = exp_raw[0:2], exp_raw[2:4], exp_raw[4:6]
                year = int(yy)
                full_year = (2000 + year)  # Expiry dates are always in the future
                parsed["expiry_from_mrz"] = f"{dd}/{mm}/{full_year}"

    return parsed


# ──────────────────────────────────────────────
#  VIZ field extraction (Visual Inspection Zone)
# ──────────────────────────────────────────────

def _extract_viz_fields(regions: list[OCRRegion]) -> dict[str, Optional[tuple[str, float, list]]]:
    """
    Extract visible (non-MRZ) fields from the passport's Visual Inspection Zone.

    Returns a dict of fieldname → (value, confidence, bbox) or None.
    """
    sorted_regions = _sort_regions_top_to_bottom(regions)
    results: dict[str, Optional[tuple[str, float, list]]] = {}

    # Passport number — look for the pattern directly
    for region in sorted_regions:
        m = _PASSPORT_NUMBER_PATTERN.search(region.text)
        if m:
            results.setdefault("docNumber", (m.group(), region.confidence, region.bbox))

    # Nationality (3-letter code)
    for region in sorted_regions:
        m = _NATIONALITY_PATTERN.search(region.text.upper())
        if m:
            results.setdefault("nationality", (m.group(), region.confidence, region.bbox))

    # Gender
    for region in sorted_regions:
        text_lower = region.text.strip().lower()
        if text_lower in _GENDER_MAP:
            results.setdefault("gender", (_GENDER_MAP[text_lower], region.confidence, region.bbox))
        elif len(text_lower) > 1:
            for key, mapped in _GENDER_MAP.items():
                if text_lower == key:
                    results.setdefault("gender", (mapped, region.confidence, region.bbox))

    # Keyword-guided extraction for dates, name, authority, etc.
    for field_name, keywords in _FIELD_KEYWORDS.items():
        if field_name in results:
            continue
        for kw in keywords:
            hit = _get_text_below_keyword(sorted_regions, kw)
            if hit:
                value, conf, bbox = hit
                # Validate dates
                if field_name in ("dob", "expiry", "issuedDate"):
                    has_date = any(p.search(value) for p in _DATE_PATTERNS)
                    if not has_date:
                        # Try same-line date extraction
                        for p in _DATE_PATTERNS:
                            m = p.search(value)
                            if m:
                                value = m.group()
                                break
                        else:
                            continue
                results[field_name] = (value, conf, bbox)
                break

    return results


# ──────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────

def parse_passport(
    regions: list[OCRRegion],
    image_height: int = 1000,
) -> PassportParseResult:
    """
    Parse OCR regions into structured passport fields.

    Args:
        regions:      List of OCR regions from the generic OCR engine.
        image_height: Pixel height of the processed image (for MRZ zone detection).

    Returns:
        PassportParseResult with all fields populated where found.
        Missing fields have ParsedField.value = None.

    IMPORTANT:
        - Values are only populated from actual OCR text — never invented.
        - MRZ extraction here does NOT constitute ICAO validation.
    """
    logger.info("Parsing passport from %d OCR regions (image_height=%d)", len(regions), image_height)

    result = PassportParseResult()

    if not regions:
        logger.warning("No OCR regions to parse — returning empty result.")
        return result

    # Step 1: Extract MRZ lines
    mrz_line1, mrz_line2 = _extract_mrz(regions, image_height)
    result.mrz_line1 = mrz_line1
    result.mrz_line2 = mrz_line2

    # Step 2: Parse structured fields from MRZ
    mrz_derived: dict[str, Optional[str]] = {}
    if mrz_line1.value or mrz_line2.value:
        mrz_derived = _parse_mrz_fields(mrz_line1.value, mrz_line2.value)
        logger.debug("MRZ-derived fields: %s", {k: v for k, v in mrz_derived.items() if v})

    # Step 3: Extract VIZ (Visual Inspection Zone) fields
    viz_fields = _extract_viz_fields(regions)

    # Step 4: Merge — MRZ-derived fields are preferred for docNumber/nationality/dob/gender/expiry
    # VIZ fields are preferred for name, authority, placeOfBirth, issuedDate (MRZ doesn't have these)

    # Name: VIZ first (usually cleaner), fall back to MRZ
    if viz_fields.get("name"):
        v, c, b = viz_fields["name"]
        result.name = ParsedField(value=v, confidence=c, bbox=b)
    elif mrz_derived.get("name_from_mrz"):
        result.name = ParsedField(value=mrz_derived["name_from_mrz"], confidence=mrz_line1.confidence)

    # Document number: MRZ first (more reliable), fall back to VIZ
    if mrz_derived.get("docNumber_from_mrz"):
        result.docNumber = ParsedField(value=mrz_derived["docNumber_from_mrz"], confidence=mrz_line2.confidence)
    elif viz_fields.get("docNumber"):
        v, c, b = viz_fields["docNumber"]
        result.docNumber = ParsedField(value=v, confidence=c, bbox=b)

    # Date of birth: MRZ first
    if mrz_derived.get("dob_from_mrz"):
        result.dob = ParsedField(value=mrz_derived["dob_from_mrz"], confidence=mrz_line2.confidence)
    elif viz_fields.get("dob"):
        v, c, b = viz_fields["dob"]
        result.dob = ParsedField(value=v, confidence=c, bbox=b)

    # Nationality: MRZ first
    if mrz_derived.get("nationality_from_mrz"):
        result.nationality = ParsedField(value=mrz_derived["nationality_from_mrz"], confidence=mrz_line2.confidence)
    elif viz_fields.get("nationality"):
        v, c, b = viz_fields["nationality"]
        result.nationality = ParsedField(value=v, confidence=c, bbox=b)

    # Gender: MRZ first
    if mrz_derived.get("gender_from_mrz"):
        result.gender = ParsedField(value=mrz_derived["gender_from_mrz"], confidence=mrz_line2.confidence)
    elif viz_fields.get("gender"):
        v, c, b = viz_fields["gender"]
        result.gender = ParsedField(value=v, confidence=c, bbox=b)

    # Expiry: MRZ first
    if mrz_derived.get("expiry_from_mrz"):
        result.expiry = ParsedField(value=mrz_derived["expiry_from_mrz"], confidence=mrz_line2.confidence)
    elif viz_fields.get("expiry"):
        v, c, b = viz_fields["expiry"]
        result.expiry = ParsedField(value=v, confidence=c, bbox=b)

    # VIZ-only fields (no MRZ equivalent)
    for field_name in ("issuedDate", "authority", "placeOfBirth"):
        if viz_fields.get(field_name):
            v, c, b = viz_fields[field_name]
            setattr(result, field_name, ParsedField(value=v, confidence=c, bbox=b))

    extracted = [f for f in [
        result.name.value, result.docNumber.value, result.dob.value,
        result.nationality.value, result.mrz_line1.value
    ] if f]
    logger.info("Passport parsing complete. Extracted %d primary fields.", len(extracted))

    return result
