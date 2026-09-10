"""
backend/app/services/documents/visa/visa_field_normalizer.py

Deterministic normalization functions for Visa fields.
"""
from __future__ import annotations

import datetime
import re
from typing import Optional

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def normalize_visa_text(raw: Optional[str]) -> Optional[str]:
    """Clean and normalize generic visa text fields."""
    if not raw:
        return None
    cleaned = re.sub(r"[^\w\s\-\.,/]", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.upper() if cleaned else None


def normalize_visa_number(raw: Optional[str]) -> Optional[str]:
    """Clean and normalize a visa credential number (alphanumeric, uppercase)."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-_]", "", raw).upper()
    # Retain alphanumeric characters only
    cleaned = re.sub(r"[^A-Z0-9]", "", cleaned)
    return cleaned if cleaned else None


def normalize_visa_date(raw: Optional[str]) -> Optional[str]:
    """
    Parse multiple date representations into canonical ISO-8601 (YYYY-MM-DD).

    Supports formats:
      - 2028-10-15 (ISO)
      - 15/10/2028 or 15-10-2028
      - 15 OCT 2028 or 15-OCT-2028
      - OCT 15 2028
    """
    if not raw:
        return None

    raw_clean = re.sub(r"[,/]", " ", raw).strip()
    raw_clean = re.sub(r"\s+", " ", raw_clean)

    # 1. Direct ISO YYYY-MM-DD match
    m_iso = re.match(r"^(\d{4})[-\s](\d{1,2})[-\s](\d{1,2})$", raw_clean)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        try:
            return datetime.date(y, m, d).isoformat()
        except ValueError:
            return None

    # 2. DD MMM YYYY match (e.g. 15 OCT 2028, 15-OCT-2028, or no-separator 15OCT2028)
    m_alpha = re.search(r"(\d{1,2})[-\s]?([a-zA-Z]{3,9})[-\s]?(\d{4})", raw)
    if m_alpha:
        d_str, mon_str, y_str = m_alpha.group(1), m_alpha.group(2)[:3].lower(), m_alpha.group(3)
        month = _MONTH_MAP.get(mon_str)
        if month:
            try:
                return datetime.date(int(y_str), month, int(d_str)).isoformat()
            except ValueError:
                return None

    # 3. DD MM YYYY match (e.g. 15/10/2028 or 15.10.2028 or 15-10-2028)
    m_dmy = re.search(r"(\d{1,2})[.\-\s/](\d{1,2})[.\-\s/](\d{4})", raw)
    if m_dmy:
        d, m, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        try:
            return datetime.date(y, m, d).isoformat()
        except ValueError:
            return None

    return None


def normalize_entries(raw: Optional[str]) -> Optional[str]:
    """Normalize visa entry count (SINGLE, MULTIPLE, 1, 2, M)."""
    if not raw:
        return None
    c = raw.strip().upper()
    if "MULT" in c or c == "M":
        return "MULTIPLE"
    if "SING" in c or c == "S" or c == "1":
        return "SINGLE"
    if c == "2" or "DOUB" in c:
        return "DOUBLE"
    return c
