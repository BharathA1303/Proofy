"""
backend/app/services/documents/border_permit/border_permit_field_normalizer.py

Field normalization utilities for Border Permit documents.
Supports deterministic parsing, unambiguous normalization, and ISO formatting.
Does NOT perform silent error repair or probabilistic guessing.
"""
from __future__ import annotations

import datetime
import re
from typing import Optional, Tuple

_DATE_PATTERNS = [
    # YYYY-MM-DD
    (re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$"), lambda y, m, d: (int(y), int(m), int(d))),
    # DD-MM-YYYY or DD/MM/YYYY or DD.MM.YYYY
    (re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$"), lambda d, m, y: (int(y), int(m), int(d))),
]

_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

_PERMIT_TYPE_MAP = {
    "entry": "ENTRY",
    "entry permit": "ENTRY",
    "visitor": "ENTRY",
    "transit": "TRANSIT",
    "transit permit": "TRANSIT",
    "local": "LOCAL_BORDER",
    "local border": "LOCAL_BORDER",
    "local_border": "LOCAL_BORDER",
    "border crossing": "LOCAL_BORDER",
    "commercial": "COMMERCIAL",
    "crew": "COMMERCIAL",
    "special": "SPECIAL_ACCESS",
    "special access": "SPECIAL_ACCESS",
    "diplomatic": "SPECIAL_ACCESS",
}


def normalize_permit_number(raw: Optional[str]) -> Tuple[Optional[str], bool]:
    """
    Normalize Border Permit identifier.
    Canonical format: BP followed by 4-digit year and 6-digit sequence:
      e.g. 'BP-2026-000123' -> 'BP2026000123'
      or   'BP2026000123'   -> 'BP2026000123'

    Returns:
        (normalized_id, is_ambiguous)
    """
    if not raw:
        return None, False

    clean = raw.strip().upper()

    # Check for confusing substitution characters in numeric slot (e.g. 'O' or 'D' instead of '0')
    is_ambiguous = False
    if re.search(r"BP[- ]?(?:20\d{2}|19\d{2})[- ]?[0-9OIl]{6}", clean, re.IGNORECASE):
        # Contains potential OCR substitution character in sequence
        tail = clean[-6:]
        if any(c in "OIlBD" for c in tail) and not all(c.isdigit() for c in tail):
            is_ambiguous = True

    # Strip visual separators (hyphen, space, slash)
    compact = re.sub(r"[\s\-_/]", "", clean)

    # Validate against canonical pattern: BP + 4 digits (year) + 6 digits (seq)
    if re.match(r"^BP\d{10}$", compact):
        return compact, is_ambiguous

    # Also accept short prefix BP + 6 to 10 digits
    if re.match(r"^BP\d{6,12}$", compact):
        return compact, is_ambiguous

    # Return stripped alphanumeric representation if it starts with BP
    if compact.startswith("BP") and len(compact) >= 8:
        return compact, is_ambiguous or not compact[2:].isdigit()

    return compact, is_ambiguous or not compact.isalnum()


def normalize_border_date(raw: Optional[str]) -> Optional[str]:
    """
    Normalize date strings into ISO format YYYY-MM-DD.
    Accepts numeric and textual month variations.
    """
    if not raw:
        return None

    clean = raw.strip()

    # Try textual month patterns e.g. "12 AUG 2026", "12-AUG-2026", "AUG 12, 2026"
    text_m = re.match(r"^(\d{1,2})[-/ ]+([A-Za-z]+)[-/ ]+(\d{4})$", clean)
    if text_m:
        d_str, mon_str, y_str = text_m.groups()
        mon = _MONTH_NAMES.get(mon_str.lower())
        if mon:
            try:
                dt = datetime.date(int(y_str), mon, int(d_str))
                return dt.isoformat()
            except ValueError:
                return None

    # Try standard numeric regexes
    for regex, extractor in _DATE_PATTERNS:
        match = regex.match(clean)
        if match:
            try:
                y, m, d = extractor(*match.groups())
                dt = datetime.date(y, m, d)
                return dt.isoformat()
            except ValueError:
                return None

    return None


def normalize_permit_type(raw: Optional[str]) -> Optional[str]:
    """Normalize permit category descriptor."""
    if not raw:
        return None
    key = raw.strip().lower()
    return _PERMIT_TYPE_MAP.get(key, raw.strip().upper())


def normalize_holder_name(raw: Optional[str]) -> Optional[str]:
    """Normalize bearer full name into clean uppercase string."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\t\n]+", " ", raw.strip())
    # Strip common label artifacts
    cleaned = re.sub(r"^(?:HOLDER\s*NAME|NAME|HOLDER)\s*[:.-]?\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip().upper() or None
