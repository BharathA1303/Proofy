"""
backend/app/services/documents/driving_license/dl_field_normalizer.py

Deterministic normalization functions for Driving License fields.
Focused on Indian Driving Licence (MoRTH / Sarathi standard).
"""
from __future__ import annotations

import datetime
import re
from typing import List, Optional

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_INDIAN_STATE_CODES = {
    "AN": "Andaman and Nicobar Islands",
    "AP": "Andhra Pradesh",
    "AR": "Arunachal Pradesh",
    "AS": "Assam",
    "BR": "Bihar",
    "CH": "Chandigarh",
    "CG": "Chhattisgarh",
    "DD": "Daman and Diu",
    "DL": "Delhi",
    "DN": "Dadra and Nagar Haveli",
    "GA": "Goa",
    "GJ": "Gujarat",
    "HR": "Haryana",
    "HP": "Himachal Pradesh",
    "JK": "Jammu and Kashmir",
    "JH": "Jharkhand",
    "KA": "Karnataka",
    "KL": "Kerala",
    "LA": "Ladakh",
    "LD": "Lakshadweep",
    "MP": "Madhya Pradesh",
    "MH": "Maharashtra",
    "MN": "Manipur",
    "ML": "Meghalaya",
    "MZ": "Mizoram",
    "NL": "Nagaland",
    "OD": "Odisha",
    "OR": "Odisha",
    "PY": "Puducherry",
    "PB": "Punjab",
    "RJ": "Rajasthan",
    "SK": "Sikkim",
    "TN": "Tamil Nadu",
    "TS": "Telangana",
    "TR": "Tripura",
    "UP": "Uttar Pradesh",
    "UK": "Uttarakhand",
    "UA": "Uttarakhand",
    "WB": "West Bengal",
}

VALID_BLOOD_GROUPS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}


def normalize_license_number(raw: Optional[str]) -> Optional[str]:
    """
    Normalize driving license number.

    Indian standard format: SS-RR-YYYY-NNNNNNN or SSRRYYYYNNNNNNN
    Where:
      SS = 2-letter state code
      RR = 2-digit RTO office code
      YYYY = 4-digit issue year
      NNNNNNN = 7-digit sequential number
    Total canonical length: 15-16 alphanumeric characters.

    Strict normalization:
      - Strip whitespace, hyphens, slashes
      - Convert to uppercase alphanumeric only
      - Retain raw input for audit
      - NO fuzzy matching or speculative correction
    """
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-_/]", "", raw).upper()
    cleaned = re.sub(r"[^A-Z0-9]", "", cleaned)
    return cleaned if cleaned else None


def normalize_dl_date(raw: Optional[str]) -> Optional[str]:
    """
    Parse multiple date representations into canonical ISO-8601 (YYYY-MM-DD).

    Supports:
      - 1995-01-01 (ISO)
      - 01/01/1995 or 01-01-1995 or 01.01.1995 (DMY)
      - 01 JAN 1995 or 01-JAN-1995
    """
    if not raw:
        return None

    raw_clean = re.sub(r"[,/]", " ", raw).strip()
    raw_clean = re.sub(r"\s+", " ", raw_clean)

    # 1. Direct ISO YYYY-MM-DD
    m_iso = re.match(r"^(\d{4})[-\s](\d{1,2})[-\s](\d{1,2})$", raw_clean)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        try:
            return datetime.date(y, m, d).isoformat()
        except ValueError:
            return None

    # 2. DD MMM YYYY (e.g. 15 MAY 1992 or 15-MAY-1992)
    m_alpha = re.search(r"(\d{1,2})[-\s]([a-zA-Z]{3,9})[-\s](\d{4})", raw)
    if m_alpha:
        d_str, mon_str, y_str = m_alpha.group(1), m_alpha.group(2)[:3].lower(), m_alpha.group(3)
        month = _MONTH_MAP.get(mon_str)
        if month:
            try:
                return datetime.date(int(y_str), month, int(d_str)).isoformat()
            except ValueError:
                return None

    # 3. DD MM YYYY (e.g. 15/05/1992 or 15-05-1992 or 15.05.1992)
    m_dmy = re.search(r"(\d{1,2})[.\-\s/](\d{1,2})[.\-\s/](\d{4})", raw)
    if m_dmy:
        d, m, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        try:
            return datetime.date(y, m, d).isoformat()
        except ValueError:
            return None

    return None


def normalize_dl_text(raw: Optional[str]) -> Optional[str]:
    """Clean and normalize general text fields (name, authority, etc.)."""
    if not raw:
        return None
    cleaned = re.sub(r"[^\w\s\-\.,/]", " ", raw)
    # Remove common parentage noise prefixes if present at start
    cleaned = re.sub(r"^(?:S/O|D/O|W/O|C/O)\s*[:.\-]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.upper() if cleaned else None


def normalize_blood_group(raw: Optional[str]) -> Optional[str]:
    """Normalize blood group string (e.g. O+ve, B POSITIVE -> O+, B+)."""
    if not raw:
        return None
    c = raw.strip().upper().replace(" ", "").replace("VE", "").replace("POSITIVE", "+").replace("NEGATIVE", "-")
    c = re.sub(r"[^ABO\+\-]", "", c)
    if c in VALID_BLOOD_GROUPS:
        return c
    return None


def normalize_vehicle_classes(raw: Optional[str]) -> List[str]:
    """Extract and normalize vehicle classes (MCWG, LMV, etc.)."""
    if not raw:
        return []
    tokens = re.split(r"[\s,;/\-]+", raw.upper())
    recognized = []
    known_classes = {
        "MCWG", "MCWOG", "LMV", "LMV-NT", "LMV-TR", "TRANS",
        "HGMV", "HPMV", "MGV", "3W-CAB", "3W-NT", "TRAILR",
    }
    for t in tokens:
        cleaned = re.sub(r"[^A-Z0-9]", "", t)
        if cleaned in known_classes or (len(cleaned) in (3, 4, 5) and cleaned.isalnum()):
            recognized.append(cleaned)
    return sorted(list(set(recognized)))


def extract_state_from_license_number(license_number: Optional[str]) -> Optional[str]:
    """Extract State/UT name from the first two letters of an Indian DL number."""
    if not license_number or len(license_number) < 2:
        return None
    code = license_number[:2].upper()
    return _INDIAN_STATE_CODES.get(code)
