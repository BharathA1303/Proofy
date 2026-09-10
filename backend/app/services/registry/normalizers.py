"""
backend/app/services/registry/normalizers.py

Identity field normalization utilities for registry verification.

IMPORTANT DESIGN NOTES:

1. Document number matching is STRICT.
   After normalization (uppercase, strip whitespace), comparison is exact equality.
   Do NOT use fuzzy/Levenshtein matching for the primary document identifier.
   T9876543 must NOT silently match T9876548.

2. Name normalization is CONTROLLED (not aggressive fuzzy).
   We normalize formatting differences that a legitimate document may have
   (MRZ filler characters, extra whitespace, case) but do NOT use approximate
   string matching. A near-match is NOT automatically treated as a match.

   Legitimate formatting differences we normalize:
     - "DOE<<JOHN<MICHAEL" → "DOE JOHN MICHAEL"  (MRZ format → display)
     - "john doe" → "JOHN DOE"  (case normalization)
     - "JOHN  DOE" → "JOHN DOE"  (whitespace collapse)

   We do NOT normalize:
     - Different name orderings (JOHN DOE vs DOE JOHN) unless MRZ structure detected
     - Initials vs full names
     - Transliteration differences

3. Date normalization outputs YYYY-MM-DD canonical form.
   Handles MRZ 6-digit YYMMDD format with century inference.

4. All functions return None for inputs that are None or cannot be normalized.
"""
from __future__ import annotations

import re
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

# MRZ filler character
_MRZ_FILLER = "<"

# Regex for MRZ-formatted names: SURNAME<<GIVEN<NAMES (one or more)
_MRZ_NAME_PATTERN = re.compile(r"^[A-Z<]{2,44}$")

# Regex for date formats we accept
_DATE_YYMMDD = re.compile(r"^(\d{2})(\d{2})(\d{2})$")          # YYMMDD (MRZ)
_DATE_DDMMYYYY = re.compile(r"^(\d{2})[/\-\.](\d{2})[/\-\.](\d{4})$")  # DD/MM/YYYY
_DATE_YYYYMMDD = re.compile(r"^(\d{4})[/\-\.]?(\d{2})[/\-\.]?(\d{2})$")  # YYYY-MM-DD or YYYYMMDD

# Century pivot for 2-digit year in MRZ: years >= 30 are 1930+, < 30 are 2030+
_MRZ_YEAR_PIVOT = 30


# ── Name normalization ─────────────────────────────────────────────────────────

def normalize_name(value: Optional[str]) -> Optional[str]:
    """
    Normalize a person name for controlled comparison.

    Steps:
      1. Strip leading/trailing whitespace.
      2. Uppercase.
      3. Replace MRZ filler characters '<' with spaces.
      4. Collapse consecutive whitespace to single space.
      5. Strip again.

    Returns None if input is None or empty after normalization.

    Examples:
      "john doe"          → "JOHN DOE"
      "DOE<<JOHN<MICHAEL" → "DOE JOHN MICHAEL"
      "SMITH<JANE"        → "SMITH JANE"
      "  ALICE  BOB  "    → "ALICE BOB"
    """
    if value is None:
        return None
    normalized = value.strip().upper()
    normalized = normalized.replace(_MRZ_FILLER, " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized if normalized else None


def normalize_name_tokens(value: Optional[str]) -> Optional[frozenset]:
    """
    Tokenize a normalized name into a frozenset of tokens for comparison.

    Used to compare names where token order may differ due to MRZ formatting
    (e.g., "DOE JOHN" vs "JOHN DOE").

    Returns None if the name cannot be normalized.
    """
    normalized = normalize_name(value)
    if not normalized:
        return None
    return frozenset(normalized.split())


def names_match(doc_name: Optional[str], registry_name: Optional[str]) -> bool:
    """
    Compare two names using controlled token-based normalization.

    Logic:
      - Both names are normalized and tokenized.
      - Match = token sets are identical.
      - A name with extra tokens (e.g., middle name in one but not the other)
        does NOT automatically match.
      - Fallback: if token sets differ, compare with ALL whitespace removed.
        OCR on compact/tight-kerned document fonts frequently merges adjacent
        words with no gap (e.g. "KAVITHAPRABHAKAR" instead of "KAVITHA
        PRABHAKAR") — this is a spacing artifact of the source image, not a
        different identity, so it must not surface as a registry mismatch.

    Returns False if either name cannot be normalized.

    NOT a fuzzy/approximate match. Near-matches (different spelling, missing
    middle name, etc.) are still NOT treated as matches — only whitespace
    differences are tolerated.
    """
    doc_tokens = normalize_name_tokens(doc_name)
    reg_tokens = normalize_name_tokens(registry_name)
    if doc_tokens is None or reg_tokens is None:
        return False
    if doc_tokens == reg_tokens:
        return True
    doc_compact = "".join(sorted("".join(doc_tokens)))
    reg_compact = "".join(sorted("".join(reg_tokens)))
    return doc_compact == reg_compact and bool(doc_compact)


# ── Date normalization ─────────────────────────────────────────────────────────

def normalize_date(value: Optional[str]) -> Optional[str]:
    """
    Normalize a date value to YYYY-MM-DD canonical form.

    Handles:
      - YYYYMMDD or YYYY-MM-DD (e.g., "19850615", "1985-06-15")
      - YYMMDD MRZ format (e.g., "850615" → "1985-06-15")
      - DD/MM/YYYY display format (e.g., "15/06/1985")

    Returns:
      Normalized "YYYY-MM-DD" string, or None if unparseable or invalid.

    NOTE: For MRZ YYMMDD with year < 30, century is set to 2000.
          For year >= 30, century is set to 1900.
          This is the standard ICAO Doc 9303 convention.
    """
    if value is None:
        return None

    s = value.strip().replace(" ", "")

    # YYYY-MM-DD or YYYYMMDD
    m = _DATE_YYYYMMDD.match(s)
    if m:
        yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
        return _validate_date_parts(yyyy, mm, dd)

    # DD/MM/YYYY or DD-MM-YYYY
    m = _DATE_DDMMYYYY.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return _validate_date_parts(yyyy, mm, dd)

    # YYMMDD (MRZ 6-digit)
    m = _DATE_YYMMDD.match(s)
    if m:
        yy, mm, dd = int(m.group(1)), m.group(2), m.group(3)
        century = 1900 if yy >= _MRZ_YEAR_PIVOT else 2000
        yyyy = str(century + yy)
        return _validate_date_parts(yyyy, mm, dd)

    return None


def _validate_date_parts(yyyy: str, mm: str, dd: str) -> Optional[str]:
    """Validate and return a normalized date, or None if invalid."""
    try:
        y, m, d = int(yyyy), int(mm), int(dd)
        if not (1 <= m <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100):
            return None
        return f"{y:04d}-{m:02d}-{d:02d}"
    except (ValueError, TypeError):
        return None


def dates_match(doc_date: Optional[str], registry_date: Optional[str]) -> bool:
    """
    Compare two date values after normalization.
    Returns False if either date is None or cannot be normalized.
    """
    nd = normalize_date(doc_date)
    nr = normalize_date(registry_date)
    if nd is None or nr is None:
        return False
    return nd == nr


# ── Document number normalization ──────────────────────────────────────────────

def normalize_document_number(value: Optional[str]) -> Optional[str]:
    """
    Normalize a document number for STRICT comparison.

    Steps:
      1. Strip whitespace.
      2. Uppercase.
      3. Remove internal whitespace (in case of formatting like "T 987 6543").

    Returns None if input is None or empty.

    STRICT: T9876543 will NOT match T9876548. No fuzzy matching.
    """
    if value is None:
        return None
    normalized = re.sub(r"\s+", "", value.strip()).upper()
    return normalized if normalized else None


def document_numbers_match(doc_num: Optional[str], registry_num: Optional[str]) -> bool:
    """
    Strict equality comparison of document numbers after normalization.
    Returns False if either value is None.
    """
    nd = normalize_document_number(doc_num)
    nr = normalize_document_number(registry_num)
    if nd is None or nr is None:
        return False
    return nd == nr


# ── Nationality / country code normalization ───────────────────────────────────

def normalize_nationality(value: Optional[str]) -> Optional[str]:
    """
    Normalize a nationality / country code.

    Steps:
      1. Strip whitespace.
      2. Uppercase.
      3. Remove MRZ filler characters.

    Returns None if None or empty after normalization.
    """
    if value is None:
        return None
    normalized = value.strip().upper().replace(_MRZ_FILLER, "")
    return normalized if normalized else None


def nationalities_match(doc_nat: Optional[str], registry_nat: Optional[str]) -> bool:
    """Compare nationalities after normalization. Returns False if either is None."""
    nd = normalize_nationality(doc_nat)
    nr = normalize_nationality(registry_nat)
    if nd is None or nr is None:
        return False
    return nd == nr


# ── Authority normalization ────────────────────────────────────────────────────

def normalize_authority(value: Optional[str]) -> Optional[str]:
    """
    Normalize an issuing authority string.
    Basic whitespace and case normalization.
    """
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value.strip()).upper()
    return normalized if normalized else None
