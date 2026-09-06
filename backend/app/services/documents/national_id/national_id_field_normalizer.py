"""
backend/app/services/documents/national_id/national_id_field_normalizer.py

Field normalization utilities for the Indian National ID Reference Profile.
Handles:
- Full DOB vs. Year of Birth (YOB) explicitly without fabricating day/month.
- Gender normalization (document consistency only; zero demographic profiling).
- Address text sanitation.
- Bearer name cleaning.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple


def normalize_dob_or_yob(raw_val: Optional[str]) -> Dict[str, Any]:
    """
    Parse a date or year of birth string.
    Distinguishes full DOB from Year of Birth explicitly.
    Never fabricates day or month when only year is present.

    Returns dict:
      {
        "date_of_birth": "YYYY-MM-DD" or None,
        "year_of_birth": int or None,
        "is_year_only": bool
      }
    """
    res = {
        "date_of_birth": None,
        "year_of_birth": None,
        "is_year_only": False,
    }
    if not raw_val or not isinstance(raw_val, str):
        return res

    clean = raw_val.strip()

    # Match standard 4-digit year directly (e.g. "1995" or "Year of Birth: 1995" / "YOB: 1995")
    # First check if it's a full date:
    # Formats: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, DD.MM.YYYY
    date_patterns = [
        (r"(\d{2})[/.-](\d{2})[/.-](\d{4})", "%d/%m/%Y", "/"),
        (r"(\d{4})[/.-](\d{2})[/.-](\d{2})", "%Y-%m-%d", "-"),
    ]

    for regex, _, _ in date_patterns:
        match = re.search(regex, clean)
        if match:
            # Check if it parses as a valid calendar date
            s = match.group(0).replace(".", "/").replace("-", "/")
            parts = s.split("/")
            if len(parts[0]) == 4:
                # YYYY/MM/DD
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            else:
                # DD/MM/YYYY
                d, m, y = int(parts[0]), int(parts[1]), int(parts[2])

            try:
                dt = datetime(y, m, d)
                res["date_of_birth"] = dt.strftime("%Y-%m-%d")
                res["year_of_birth"] = y
                res["is_year_only"] = False
                return res
            except ValueError:
                pass

    # If full date did not match, check for Year of Birth pattern (4 digits between 1900 and 2099)
    yob_match = re.search(r"\b(19\d\d|20[0-2]\d)\b", clean)
    if yob_match:
        y = int(yob_match.group(1))
        res["date_of_birth"] = None
        res["year_of_birth"] = y
        res["is_year_only"] = True
        return res

    return res


def normalize_gender(raw_val: Optional[str]) -> Optional[str]:
    """
    Normalize gender to MALE, FEMALE, or TRANSGENDER.
    Used exclusively for document/registry consistency, NEVER as a risk factor.
    """
    if not raw_val or not isinstance(raw_val, str):
        return None

    clean = raw_val.strip().upper()
    if clean in ("M", "MALE", "PURUSH", "MAN"):
        return "MALE"
    if clean in ("F", "FEMALE", "MAHILA", "WOMAN"):
        return "FEMALE"
    if clean in ("T", "TG", "TRANSGENDER", "OTHER"):
        return "TRANSGENDER"

    # Regex search within text
    if re.search(r"\b(FEMALE|MAHILA)\b", clean):
        return "FEMALE"
    if re.search(r"\b(MALE|PURUSH)\b", clean):
        return "MALE"
    if re.search(r"\b(TRANSGENDER)\b", clean):
        return "TRANSGENDER"

    return None


def normalize_name(raw_name: Optional[str]) -> Optional[str]:
    """
    Clean bearer name by stripping non-name noise and collapsing whitespace.
    """
    if not raw_name or not isinstance(raw_name, str):
        return None

    clean = re.sub(r"[^A-Za-z\s.'-]", "", raw_name)
    clean = re.sub(r"\s+", " ", clean).strip().upper()
    return clean if clean else None


def normalize_address(raw_addr: Optional[str]) -> Optional[str]:
    """
    Clean address text. Strips common prefixes like 'Address:', 'C/O', 'S/O', etc.
    """
    if not raw_addr or not isinstance(raw_addr, str):
        return None

    clean = re.sub(r"^(ADDRESS|ADDR|PATTA|C/O|S/O|D/O|W/O)\s*[:\-]?\s*", "", raw_addr.strip(), flags=re.IGNORECASE)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean if clean else None
