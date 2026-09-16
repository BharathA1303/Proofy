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
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

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

# Indian passport file number: 2 letters (RPO code) + 13-16 digits, e.g. "DL0012345671234"
_FILE_NUMBER_PATTERN = re.compile(r"\b[A-Z]{2}\d{13,16}\b")

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
    "placeOfIssue":["place of issue", "issue place"],
    "fileNumber":  ["file number", "file no", "file no.", "application number"],
}

# Gender normalisation
_GENDER_MAP = {
    "m": "M", "male": "M", "♂": "M",
    "f": "F", "female": "F", "♀": "F",
    "x": "X", "unspecified": "X",
}

# ── Positional / contextual anchors for passport & file number extraction ──
# Requirement #4: a bare regex match for "shape looks like a passport number"
# is not enough — a stray sticker, a visa reference number, or an adjacent
# unrelated block on the page can match the same shape. We prefer a match
# found spatially adjacent to one of these anchor terms; only when no
# anchor-adjacent match exists do we fall back to a vertically-constrained
# scan of the plausible VIZ zone (never the whole page, and never the MRZ
# band, which has its own dedicated, already-validated extraction path).
_PASSPORT_NUMBER_ANCHORS = ("passport no", "passport number", "document no", "doc no", "pasport no")
_FILE_NUMBER_ANCHORS = ("file number", "file no", "file no.", "application number", "application no")

# MRZ occupies roughly the bottom ~18% of a TD3 passport bio-data page
# (mirrors passport_profile.expected_regions["mrz"]: relative_y=0.82).
# VIZ-field extraction must never reach into this band — the MRZ has its
# own dedicated, already-validated extraction path (_extract_mrz), and
# letting VIZ regex scans wander into MRZ text risks picking up a MRZ
# fragment that merely happens to match the VIZ field's shape.
_MRZ_ZONE_TOP_FRACTION = 0.80

# Requirement #2: hard length caps per field to prevent unbounded OCR noise
# (a misread barcode, a smudge interpreted as dense text, or a deliberately
# oversized injected string) from ever reaching the structured record.
_FIELD_MAX_LENGTH = {
    "name": 100,
    "authority": 100,
    "placeOfBirth": 80,
    "placeOfIssue": 80,
    "docNumber": 20,
    "fileNumber": 24,
    "nationality": 40,
    "gender": 12,
    "dob": 20,
    "expiry": 20,
    "issuedDate": 20,
}
_DEFAULT_FIELD_MAX_LENGTH = 100

# A name/authority/place field must be predominantly alphabetic (plus
# spaces and a small set of legitimate punctuation used in personal/place
# names) — this rejects candidates that absorbed structural noise (MRZ-like
# filler runs, standalone digit blocks, barcode misreads) from an adjacent
# region instead of the intended text.
_ALPHA_FIELD_CHARS = re.compile(r"[A-Za-zÀ-ɏ\s\.\-'’]")
_MIN_ALPHA_RATIO = 0.6


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
    placeOfIssue: ParsedField = field(default_factory=ParsedField)
    authority: ParsedField = field(default_factory=ParsedField)
    issuedDate: ParsedField = field(default_factory=ParsedField)
    expiry: ParsedField = field(default_factory=ParsedField)
    fileNumber: ParsedField = field(default_factory=ParsedField)
    mrz_line1: ParsedField = field(default_factory=ParsedField)
    mrz_line2: ParsedField = field(default_factory=ParsedField)
    # Tracking flags for MRZ auto-correction (see _normalize_mrz_line / _extract_mrz).
    # `mrz_auto_corrected=True` means at least one of the two MRZ lines required
    # ANY structural adjustment — including safe, unambiguous trailing-filler
    # padding — to reach a nominally valid 44-char shape. This is tracking
    # metadata, not a validation verdict by itself: correction tags ending in
    # "_safe" (pure filler padding after a truncated OCR detection box; no
    # detected character was altered or guessed) carry materially less risk
    # than "filler_insert" tags (a genuine character-level guess about what
    # OCR missed). Module 2 (passport_validation_service.py) MUST use
    # `mrz_has_high_risk_correction` — not this flag alone — to decide
    # whether a correction is tampering-relevant enough to hard-fail
    # validation; see `_mrz_correction_is_high_risk()`.
    mrz_auto_corrected: bool = False
    mrz_auto_corrected_indices: list[str] = field(default_factory=list)
    mrz_has_high_risk_correction: bool = False


# ──────────────────────────────────────────────
#  Helper utilities
# ──────────────────────────────────────────────

def _is_mrz_candidate(text: str) -> bool:
    """Return True if the text looks like a MRZ line."""
    compact = text.replace(" ", "").upper()
    if len(compact) < _MRZ_MIN_LEN:
        return False
    # Exclude MRZ banner descriptions and header zone titles
    if any(kw in compact for kw in ("MACHINE", "READABLE", "DOC9303", "ZONE", "PASSEPORT", "REPUBLIC")):
        return False
    # A TD3 MRZ line must contain filler characters '<' or digits (dates/check digits)
    has_filler = "<" in compact
    has_digits = any(c.isdigit() for c in compact)
    if not has_filler and not has_digits:
        return False
    # If it starts with P< or contains filler markers <<, high probability MRZ candidate
    if compact.startswith("P<") or "<<" in compact or (compact.startswith("P") and "<" in compact):
        return True
    # High density of MRZ-valid characters
    valid_chars = sum(1 for c in compact if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")
    ratio = valid_chars / len(compact)
    return ratio >= 0.85


def _normalize_mrz_line(text: str) -> tuple[str, list[str]]:
    """
    Normalize a raw OCR MRZ line.
    - Collapse spaces (OCR may insert spaces within MRZ)
    - Re-insert dropped separator if 'PIND...' OCR error
    - Standardize length for TD3 format if trailing fillers merged

    IMPORTANT — this function performs CHARACTER-LEVEL CORRECTION of the raw
    OCR text, not just whitespace cleanup. Every corrective operation is a
    guess about what the "real" character should have been, and a guess
    that happens to coincide with what a forger typed (or a physically
    altered field) will silently launder that alteration into a
    structurally valid-looking MRZ line before check-digit validation ever
    sees it. Every correction is therefore tracked and returned alongside
    the normalized text — callers MUST propagate this to Module 2 rather
    than discard it, so a corrected MRZ is never treated as equivalent to a
    cleanly-extracted one.

    Returns:
        (normalized_text, correction_tags) — correction_tags is empty when
        no character-level correction was necessary (only whitespace
        collapsing occurred, which is not tracked as a correction since it
        does not alter which characters are present).
    """
    corrections: list[str] = []

    normalized = re.sub(r"\s+", "", text.upper())

    # Correct dropped '<' after passport indicator (e.g. PINDSHARMA -> P<INDSHARMA)
    if re.match(r"^P[A-Z]{3}", normalized) and not normalized.startswith("P<") and "<" in normalized:
        normalized = f"P<{normalized[1:]}"
        corrections.append("filler_insert:pos1")

    # Correct dropped '<' between 8-char passport number and check digit (e.g. Z12345671IND -> Z1234567<1IND)
    m2 = re.match(r"^([A-Z0-9]{8})([0-9])([A-Z]{3})(\d{6}.*)", normalized)
    if m2:
        normalized = f"{m2.group(1)}<{m2.group(2)}{m2.group(3)}{m2.group(4)}"
        corrections.append("filler_insert:pos8")

    return normalized, corrections


def _mrz_correction_is_high_risk(corrected_tags: list[str]) -> bool:
    """
    Classify a list of MRZ correction tags (from _extract_mrz) as
    "high-risk" (a genuine character-level guess about content OCR did not
    actually detect — tampering-relevant) vs. "safe" (pure trailing-filler
    padding after a truncated OCR detection box — no detected character was
    altered).

    A tag is high-risk unless it explicitly ends in "_safe" (the
    "pad_to_44_safe" tags produced by _extract_mrz). This means any FUTURE
    correction type added to this module defaults to high-risk unless
    explicitly marked otherwise — new correction logic must opt in to being
    treated leniently, not opt out of scrutiny.

    Returns False (no high-risk correction) for an empty tag list.
    """
    for tag in corrected_tags:
        # tag shape: "line{1,2}:<operation>[:<detail>]"
        parts = tag.split(":")
        operation = parts[1] if len(parts) > 1 else tag
        if not operation.endswith("_safe"):
            return True
    return False


# ──────────────────────────────────────────────
#  Text sanitization & semantic validation (Requirements #2, #3)
# ──────────────────────────────────────────────

def _sanitize_text_field(
    raw: Optional[str],
    field_name: str = "generic",
) -> Optional[str]:
    """
    Strict sanitization for any VIZ-extracted text value before it enters
    the structured record (PassportParseResult / downstream schemas).

    Applies, in order:
      1. Strip non-printable / control characters (category "C*" under
         Unicode, e.g. NUL, escape sequences, zero-width characters) —
         these have no legitimate place in a printed passport field and
         are a classic vector for log/DB injection or display corruption.
      2. Collapse internal whitespace runs to single spaces; strip ends.
      3. Cap length to a field-appropriate maximum (Requirement #2) —
         prevents unbounded OCR noise, a misread barcode, or a
         deliberately oversized injected string from ever reaching the
         structured record. Truncation is logged, never silent in effect
         (the caller receives a visibly shorter value, not an error).

    Returns None if the sanitized result is empty — an empty/whitespace-only
    field is equivalent to "not found," never an empty string placeholder.
    """
    if not raw:
        return None

    # Drop Unicode control/format/surrogate/unassigned characters (category
    # starting with "C"), but keep the space character itself (Zs "space
    # separator" is category "Zs", not "C*", so ordinary spaces survive).
    cleaned_chars = [ch for ch in raw if not unicodedata.category(ch).startswith("C")]
    cleaned = "".join(cleaned_chars)

    # Collapse whitespace runs (including any exotic Unicode spaces that
    # survived the control-character pass) to single ASCII spaces.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return None

    max_len = _FIELD_MAX_LENGTH.get(field_name, _DEFAULT_FIELD_MAX_LENGTH)
    if len(cleaned) > max_len:
        logger.warning(
            "VIZ field '%s' exceeded max length (%d > %d chars) — truncated. "
            "This may indicate OCR noise, a misread barcode, or an anomalous input.",
            field_name, len(cleaned), max_len,
        )
        cleaned = cleaned[:max_len].rstrip()

    return cleaned or None


def _looks_alphabetic(text: str, min_ratio: float = _MIN_ALPHA_RATIO) -> bool:
    """
    Semantic sanity check for name/authority/place-style fields: the text
    must be predominantly alphabetic (letters, spaces, and a small set of
    legitimate name punctuation), not structural noise absorbed from an
    adjacent block (e.g. a run of MRZ filler characters, a standalone
    digit sequence, or barcode/keyword-label leakage).

    A VIZ name/place candidate containing the MRZ filler character '<' is
    rejected outright regardless of alphabetic ratio — a name that is
    mostly letters but still carries '<' is itself evidence the candidate
    text actually came from (or leaked out of) the MRZ zone, not the VIZ,
    since '<' has no legitimate place in a printed VIZ field.

    Empty input is treated as failing the check (no signal to validate).
    """
    if not text:
        return False
    if "<" in text:
        return False
    alpha_chars = sum(1 for ch in text if _ALPHA_FIELD_CHARS.match(ch))
    ratio = alpha_chars / len(text)
    return ratio >= min_ratio and any(ch.isalpha() for ch in text)


def _looks_like_identifier(text: str) -> bool:
    """
    Semantic sanity check for a passport/file-number-style candidate: must
    be alphanumeric (plus the MRZ filler '<', which OCR sometimes leaves
    in visually-adjacent VIZ text) and must contain at least one digit —
    a pure-letter run (e.g. a misattributed word from a nearby label) is
    not a valid identifier shape even if a regex incidentally matched a
    substring of it.
    """
    if not text:
        return False
    if not re.fullmatch(r"[A-Z0-9<]+", text):
        return False
    return any(ch.isdigit() for ch in text)


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
    validator: Optional[Callable[[str], bool]] = None,
) -> Optional[tuple[str, float, list[list[int]]]]:
    """
    Find a region whose text is immediately below a region containing keyword_text.

    Requirement #3 hardening: candidates are now considered in ascending
    distance order (closest first, as before), but when `validator` is
    supplied, a spatially-closer candidate that FAILS the semantic check
    (e.g. a numeric MRZ-fragment sitting directly under a "Surname" label
    due to layout noise) is skipped in favor of the next-closest candidate
    that passes — rather than blindly accepting the nearest block
    regardless of whether it plausibly contains the expected kind of text.
    A keyword with no semantically valid candidate below it returns None,
    same as if nothing were found at all.

    Returns (text, confidence, bbox) or None.
    """
    keyword_lower = keyword_text.lower()
    for i, region in enumerate(regions):
        if keyword_lower in region.text.lower():
            # Find all regions below this one, ordered by vertical proximity
            kw_bottom_y = max(pt[1] for pt in region.bbox) if region.bbox else 0
            kw_left_x = min(pt[0] for pt in region.bbox) if region.bbox else 0
            kw_right_x = max(pt[0] for pt in region.bbox) if region.bbox else 9999

            candidates: list[tuple[str, float, list[list[int]], int]] = []
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
                        candidates.append((candidate.text, candidate.confidence, candidate.bbox, gap))

            candidates.sort(key=lambda c: c[3])

            for text, conf, bbox, _gap in candidates:
                if validator is not None and not validator(text):
                    logger.debug(
                        "VIZ keyword '%s': candidate '%s' rejected by semantic validator.",
                        keyword_text, text[:40],
                    )
                    continue
                return text, conf, bbox
    return None


# ──────────────────────────────────────────────
#  MRZ extraction
# ──────────────────────────────────────────────

def _extract_mrz(
    regions: list[OCRRegion],
    image_height: int,
) -> tuple[ParsedField, ParsedField, bool, list[str]]:
    """
    Identify and extract MRZ Line 1 and Line 2 from OCR regions.

    Strategy:
      1. Filter candidate regions (long, mostly MRZ characters, bottom 35% of image)
      2. Sort candidates by Y position
      3. Take the bottom two candidates as line1, line2

    Returns: (mrz_line1, mrz_line2, auto_corrected, corrected_tags)
      - mrz_line1 / mrz_line2: ParsedFields — values are None if not found.
      - auto_corrected: True if ANY structural padding, truncation, or
        character injection was applied to either line to reach a
        nominally valid TD3 shape. This is a TRACKING flag, not a
        validation verdict — use `_mrz_correction_is_high_risk(corrected_tags)`
        to distinguish a genuine character-level guess (high-risk,
        tampering-relevant) from safe trailing-filler padding recovery
        (a common, benign PaddleOCR detection-box-truncation artifact).
      - corrected_tags: machine-readable list of which operations fired
        and on which line, e.g. ["line1:filler_insert:pos1", "line2:pad_to_44_safe:from_38"].

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
    corrected_tags: list[str] = []

    if len(candidates) >= 2:
        # Take the two lowest (bottom-most) MRZ-like lines
        bottom_two = candidates[-2:]
        bottom_two.sort(key=lambda x: x[0])  # top one first

        r1 = bottom_two[0][1]
        r2 = bottom_two[1][1]

        raw1 = r1.text
        raw2 = r2.text
        norm1, corr1 = _normalize_mrz_line(raw1)
        norm2, corr2 = _normalize_mrz_line(raw2)
        line1_tags = [f"line1:{tag}" for tag in corr1]
        line2_tags = [f"line2:{tag}" for tag in corr2]

        # Sanity: line1 of a TD3 passport should start with P
        if norm1 and not norm1.startswith("P") and norm2.startswith("P"):
            raw1, raw2 = raw2, raw1
            norm1, norm2 = norm2, norm1
            r1, r2 = r2, r1
            line1_tags, line2_tags = line2_tags, line1_tags

        # Ensure TD3 Line 1 length is 44 if trailing fillers were merged.
        #
        # IMPORTANT distinction from filler_insert (_normalize_mrz_line):
        # this ONLY appends '<' filler characters after text that already
        # starts with the correct "P<" prefix — it never rewrites or
        # guesses any character that OCR actually detected. This is a
        # common, benign PaddleOCR artifact: the detector's bounding box
        # for a long run of trailing '<' filler often terminates early
        # (the filler run visually thins out), truncating the DETECTED
        # box well before the physical end of the printed line, even
        # though every character OCR did read is correct. Tagged
        # "pad_to_44_safe" — distinct from the genuinely risky
        # character-level guesses in _normalize_mrz_line — so Module 2
        # can weigh it very differently (see passport_validation_service.py).
        if norm1 and norm1.startswith("P<") and len(norm1) < 44:
            pre_len = len(norm1)
            norm1 = (norm1 + "<" * 44)[:44]
            line1_tags.append(f"line1:pad_to_44_safe:from_{pre_len}")

        # Ensure TD3 Line 2 length is 44 if trailing fillers were merged.
        # Same distinction applies: when the last character is preserved
        # (a digit — the composite/optional-data check digit — or an
        # existing '<'), only filler is inserted in the middle; no
        # detected character is altered, so this is also "safe" padding.
        # The remaining else-branch (last character is neither, so its
        # true position within the 44-char line is genuinely ambiguous)
        # stays tagged as an ordinary structural correction.
        if norm2 and len(norm2) in range(35, 44) and "<" in norm2:
            pre_len = len(norm2)
            last_char = norm2[-1]
            if last_char.isdigit() or last_char == "<":
                body = norm2[:-1]
                padded_body = (body + "<" * 43)[:43]
                norm2 = f"{padded_body}{last_char}"
                line2_tags.append(f"line2:pad_to_44_safe:from_{pre_len}")
            else:
                norm2 = (norm2 + "<" * 44)[:44]
                line2_tags.append(f"line2:pad_to_44:from_{pre_len}")

        corrected_tags = line1_tags + line2_tags

        line1 = ParsedField(value=norm1, confidence=r1.confidence, bbox=r1.bbox)
        line2 = ParsedField(value=norm2, confidence=r2.confidence, bbox=r2.bbox)

        logger.info(
            "MRZ extracted: line1_len=%d line2_len=%d auto_corrected=%s",
            len(norm1), len(norm2), bool(corrected_tags),
        )

    elif len(candidates) == 1:
        r1 = candidates[0][1]
        norm1, corr1 = _normalize_mrz_line(r1.text)
        if norm1.startswith("P"):
            line1 = ParsedField(value=norm1, confidence=r1.confidence, bbox=r1.bbox)
            corrected_tags = [f"line1:{tag}" for tag in corr1]
        else:
            line2 = ParsedField(value=norm1, confidence=r1.confidence, bbox=r1.bbox)
            corrected_tags = [f"line2:{tag}" for tag in corr1]
        logger.info("MRZ: only one line found (len=%d) auto_corrected=%s", len(norm1), bool(corrected_tags))
    else:
        logger.info("MRZ: no MRZ lines detected in this image.")

    auto_corrected = bool(corrected_tags)
    if auto_corrected:
        high_risk = _mrz_correction_is_high_risk(corrected_tags)
        logger.warning(
            "TRACKING_EVENT mrz_auto_corrected: MRZ required structural correction before it reached a "
            "nominally valid shape (tags=%s, high_risk=%s). %s",
            corrected_tags, high_risk,
            "This document's MRZ must be treated as a tampering-relevant signal by Module 2."
            if high_risk else
            "All corrections were safe trailing-filler padding recovery — Module 2 should weigh this as "
            "low-risk tracking metadata, not an automatic hard failure.",
        )

    return line1, line2, auto_corrected, corrected_tags


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

    if mrz_line1 and len(mrz_line1) >= 8:
        # Name parsing from line 1 (Positions 6–44)
        name_field = mrz_line1[5:]
        if "<<" in name_field:
            parts = name_field.split("<<")
            surname = parts[0].replace("<", " ").strip()
            given = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
            full_name = f"{surname} {given}".strip() if given else surname
            parsed["name_from_mrz"] = full_name if full_name else None
        elif "<" in name_field:
            # When consecutive << merged into single <
            parts = [p.strip() for p in name_field.split("<") if p.strip()]
            if len(parts) >= 2:
                parsed["name_from_mrz"] = f"{parts[0]} {parts[1]}"
            elif parts:
                parsed["name_from_mrz"] = parts[0]
        elif name_field:
            parsed["name_from_mrz"] = name_field.replace("<", " ").strip() or None

    if mrz_line2 and len(mrz_line2) >= 9:
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
#  Positional / contextual identifier extraction (Requirement #4)
# ──────────────────────────────────────────────

def _find_anchored_identifier(
    regions: list[OCRRegion],
    pattern: re.Pattern,
    anchor_terms: tuple[str, ...],
    viz_zone_bottom: Optional[int],
    max_y_gap: int = 80,
) -> Optional[tuple[str, float, list[list[int]]]]:
    """
    Locate an identifier-shaped token (passport number / file number),
    preferring a match that is spatially adjacent to one of `anchor_terms`
    (e.g. "Passport No", "Document No", "File No") over a bare global
    shape-match anywhere on the page.

    Strategy (in priority order):
      1. Anchor-adjacent match: for each region containing an anchor term,
         search regions below/near it (same logic as _get_text_below_keyword)
         AND the anchor region's own text (labels and values sometimes share
         one OCR box, e.g. "Passport No: Z1234567") for a pattern match.
         The first anchor whose vicinity yields a match wins.
      2. Constrained fallback: if no anchor-adjacent match exists anywhere
         (e.g. the anchor label itself was not recognized by OCR), fall back
         to a plain pattern scan — but ONLY within the plausible VIZ zone
         (above the MRZ band, per `viz_zone_bottom`), never the whole page.
         This still prevents a stray token inside the MRZ, or a sticker
         placed below the normal VIZ content, from cross-contaminating the
         identifier.

    Returns (text, confidence, bbox) or None.
    """
    # ── Tier 1: anchor-adjacent match ───────────────────────────────────
    for i, region in enumerate(regions):
        region_text_lower = region.text.lower()
        if not any(anchor in region_text_lower for anchor in anchor_terms):
            continue

        # Same-box match (label and value share one OCR detection)
        same_box_match = pattern.search(region.text.upper())
        if same_box_match and _looks_like_identifier(same_box_match.group()):
            return same_box_match.group(), region.confidence, region.bbox

        # Nearby-region match (value sits in an adjacent box)
        if not region.bbox:
            continue
        kw_bottom_y = max(pt[1] for pt in region.bbox)
        kw_top_y = min(pt[1] for pt in region.bbox)
        kw_left_x = min(pt[0] for pt in region.bbox)
        kw_right_x = max(pt[0] for pt in region.bbox)

        nearby: list[tuple[str, float, list[list[int]], int]] = []
        for j, candidate in enumerate(regions):
            if j == i or not candidate.bbox:
                continue
            cand_top_y = min(pt[1] for pt in candidate.bbox)
            cand_left_x = min(pt[0] for pt in candidate.bbox)
            cand_right_x = max(pt[0] for pt in candidate.bbox)
            # Same-line to the right, or immediately below — either layout
            # is common across passport issuing authorities.
            same_line = abs(cand_top_y - kw_top_y) <= 15 and cand_left_x >= kw_right_x
            below = 0 <= (cand_top_y - kw_bottom_y) <= max_y_gap and not (
                cand_right_x < kw_left_x or cand_left_x > kw_right_x
            )
            if same_line or below:
                vertical_gap = abs(cand_top_y - kw_bottom_y)
                nearby.append((candidate.text, candidate.confidence, candidate.bbox, vertical_gap))

        nearby.sort(key=lambda c: c[3])
        for text, conf, bbox, _gap in nearby:
            m = pattern.search(text.upper())
            if m and _looks_like_identifier(m.group()):
                return m.group(), conf, bbox

    # ── Tier 2: constrained fallback (VIZ zone only, never the whole page) ──
    logger.debug(
        "Identifier extraction: no anchor-adjacent match found for anchors=%s; "
        "falling back to VIZ-zone-constrained scan.",
        anchor_terms,
    )
    for region in regions:
        if viz_zone_bottom is not None and region.bbox:
            region_top_y = min(pt[1] for pt in region.bbox)
            if region_top_y >= viz_zone_bottom:
                continue  # inside/past the MRZ band — never scanned here
        m = pattern.search(region.text.upper())
        if m and _looks_like_identifier(m.group()):
            return m.group(), region.confidence, region.bbox

    return None


# ──────────────────────────────────────────────
#  VIZ field extraction (Visual Inspection Zone)
# ──────────────────────────────────────────────

def _extract_viz_fields(
    regions: list[OCRRegion],
    image_height: Optional[int] = None,
) -> dict[str, Optional[tuple[str, float, list]]]:
    """
    Extract visible (non-MRZ) fields from the passport's Visual Inspection Zone.

    Every extracted value passes through `_sanitize_text_field` (strips
    control/non-printable characters, collapses whitespace, caps length)
    before being placed in the result — see Requirement #2. Name/authority/
    place fields are additionally required to pass `_looks_alphabetic` — see
    Requirement #3. Passport/file numbers are located via
    `_find_anchored_identifier`, which prefers a match spatially adjacent to
    a contextual anchor term over a bare global shape-match — see
    Requirement #4.

    Returns a dict of fieldname → (sanitized_value, confidence, bbox) or None.
    """
    sorted_regions = _sort_regions_top_to_bottom(regions)
    results: dict[str, Optional[tuple[str, float, list]]] = {}

    viz_zone_bottom = int(image_height * _MRZ_ZONE_TOP_FRACTION) if image_height else None

    # Passport number — anchor-adjacent first, constrained fallback second
    doc_num_hit = _find_anchored_identifier(
        sorted_regions, _PASSPORT_NUMBER_PATTERN, _PASSPORT_NUMBER_ANCHORS, viz_zone_bottom,
    )
    if doc_num_hit:
        value, conf, bbox = doc_num_hit
        sanitized = _sanitize_text_field(value, "docNumber")
        if sanitized:
            results["docNumber"] = (sanitized, conf, bbox)

    # Nationality (3-letter code) — shape is tightly constrained (ISO list),
    # so a global scan is acceptably low-risk; sanitize for consistency.
    for region in sorted_regions:
        m = _NATIONALITY_PATTERN.search(region.text.upper())
        if m:
            sanitized = _sanitize_text_field(m.group(), "nationality")
            if sanitized:
                results.setdefault("nationality", (sanitized, region.confidence, region.bbox))

    # File number — anchor-adjacent first, constrained fallback second
    file_num_hit = _find_anchored_identifier(
        sorted_regions, _FILE_NUMBER_PATTERN, _FILE_NUMBER_ANCHORS, viz_zone_bottom,
    )
    if file_num_hit:
        value, conf, bbox = file_num_hit
        sanitized = _sanitize_text_field(value, "fileNumber")
        if sanitized:
            results["fileNumber"] = (sanitized, conf, bbox)

    # Gender
    for region in sorted_regions:
        text_lower = region.text.strip().lower()
        if text_lower in _GENDER_MAP:
            results.setdefault("gender", (_GENDER_MAP[text_lower], region.confidence, region.bbox))
        elif len(text_lower) > 1:
            for key, mapped in _GENDER_MAP.items():
                if text_lower == key:
                    results.setdefault("gender", (mapped, region.confidence, region.bbox))

    # Specific extraction for Surname + Given Name in VIZ — both must look
    # alphabetic (Requirement #3), rejecting a candidate that absorbed
    # structural noise from an adjacent block.
    hit_surname = None
    hit_given = None
    for kw in ("surname", "nom"):
        hit_surname = _get_text_below_keyword(sorted_regions, kw, validator=_looks_alphabetic)
        if hit_surname:
            break
    for kw in ("given name", "given names", "prénoms", "prenoms"):
        hit_given = _get_text_below_keyword(sorted_regions, kw, validator=_looks_alphabetic)
        if hit_given:
            break

    if hit_surname and hit_given:
        full_name = f"{hit_given[0]} {hit_surname[0]}".strip()
        sanitized = _sanitize_text_field(full_name, "name")
        if sanitized:
            results["name"] = (sanitized, min(hit_surname[1], hit_given[1]), hit_surname[2])

    # Keyword-guided extraction for dates, name, authority, etc.
    # Alphabetic-style fields get the semantic validator; date/free-text
    # fields do not (dates are numeric by nature and are separately format-
    # validated below).
    _ALPHA_FIELDS = {"name", "authority", "placeOfBirth", "placeOfIssue"}

    for field_name, keywords in _FIELD_KEYWORDS.items():
        if field_name in results:
            continue
        validator = _looks_alphabetic if field_name in _ALPHA_FIELDS else None
        for kw in keywords:
            hit = _get_text_below_keyword(sorted_regions, kw, validator=validator)
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
                sanitized = _sanitize_text_field(value, field_name)
                if sanitized:
                    results[field_name] = (sanitized, conf, bbox)
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
        `mrz_auto_corrected` / `mrz_auto_corrected_indices` report whether
        either MRZ line required structural padding, truncation, or
        character injection to reach a nominally valid TD3 shape — callers
        MUST propagate this to Module 2 validation rather than discard it.

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
    mrz_line1, mrz_line2, mrz_auto_corrected, mrz_corrected_tags = _extract_mrz(regions, image_height)
    result.mrz_line1 = mrz_line1
    result.mrz_line2 = mrz_line2
    result.mrz_auto_corrected = mrz_auto_corrected
    result.mrz_auto_corrected_indices = mrz_corrected_tags
    result.mrz_has_high_risk_correction = _mrz_correction_is_high_risk(mrz_corrected_tags)

    # Step 2: Parse structured fields from MRZ
    mrz_derived: dict[str, Optional[str]] = {}
    if mrz_line1.value or mrz_line2.value:
        mrz_derived = _parse_mrz_fields(mrz_line1.value, mrz_line2.value)
        logger.debug("MRZ-derived fields: %s", {k: v for k, v in mrz_derived.items() if v})

    # Step 3: Extract VIZ (Visual Inspection Zone) fields
    viz_fields = _extract_viz_fields(regions, image_height=image_height)

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
    for field_name in ("issuedDate", "authority", "placeOfBirth", "placeOfIssue", "fileNumber"):
        if viz_fields.get(field_name):
            v, c, b = viz_fields[field_name]
            setattr(result, field_name, ParsedField(value=v, confidence=c, bbox=b))

    extracted = [f for f in [
        result.name.value, result.docNumber.value, result.dob.value,
        result.nationality.value, result.mrz_line1.value
    ] if f]
    logger.info(
        "Passport parsing complete. Extracted %d primary fields. mrz_auto_corrected=%s",
        len(extracted), result.mrz_auto_corrected,
    )

    return result
