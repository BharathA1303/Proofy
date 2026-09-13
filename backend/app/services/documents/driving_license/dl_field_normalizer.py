"""
backend/app/services/documents/driving_license/dl_field_normalizer.py

Deterministic normalization functions for Driving License fields.
Focused on Indian Driving Licence (MoRTH / Sarathi standard).

ARCHITECTURAL CONTRACT (Phase 3 — Field Normalization Hardening):
  NORMALIZATION cleans/standardizes representation without changing meaning.
  VALIDATION determines whether the normalized value satisfies expected DL rules.

  The normalizer must NOT:
    - Invent missing characters or digits
    - Guess or substitute characters based on speculative assumptions
    - Convert malformed identifiers into valid ones
    - Repair impossible calendar dates or roll them forward/backward
    - Assign semantic roles to dates (semantic role assignment is parser/layout logic)
    - Guess nearest blood group
    - Silently convert arbitrary OCR tokens into valid vehicle classes
    - Fuzzy-correct names or identity fields
    - Destroy original OCR evidence upstream
"""
from __future__ import annotations

import datetime
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Structured Status and Results ────────────────────────────────────────────

class NormalizationStatus(str, Enum):
    """Structured normalization outcome status."""
    NORMALIZED = "NORMALIZED"        # Representation cleaned / standardized
    UNCHANGED = "UNCHANGED"          # Value was already in standard representation
    UNKNOWN = "UNKNOWN"              # Input is None, empty, or whitespace only
    INVALID = "INVALID"              # Input is malformed, corrupt, or invalid calendar date
    UNRECOGNIZED = "UNRECOGNIZED"    # Syntactically well-formed but outside recognized taxonomy


@dataclass
class NormalizationResult:
    """Structured normalization result preserving original evidence and status."""
    status: NormalizationStatus
    value: Optional[str] = None
    raw: Optional[str] = None
    details: Optional[str] = None


class StateCodeStatus(str, Enum):
    """Status of an Indian State/UT two-letter code."""
    CURRENT = "CURRENT"
    LEGACY = "LEGACY"


@dataclass(frozen=True)
class StateCodeEntry:
    """State code mapping entry preserving historical/legacy relationships."""
    code: str
    canonical_state: str
    code_status: StateCodeStatus


# ── State / UT Code Registry ─────────────────────────────────────────────────
# Preserves historical aliases (OR/OD, UA/UK, DD/DN) with explicit status.
# Derivation from license number prefix does NOT constitute authoritative proof of issuer.

STATE_CODE_REGISTRY: Dict[str, StateCodeEntry] = {
    "AN": StateCodeEntry("AN", "Andaman and Nicobar Islands", StateCodeStatus.CURRENT),
    "AP": StateCodeEntry("AP", "Andhra Pradesh", StateCodeStatus.CURRENT),
    "AR": StateCodeEntry("AR", "Arunachal Pradesh", StateCodeStatus.CURRENT),
    "AS": StateCodeEntry("AS", "Assam", StateCodeStatus.CURRENT),
    "BR": StateCodeEntry("BR", "Bihar", StateCodeStatus.CURRENT),
    "CH": StateCodeEntry("CH", "Chandigarh", StateCodeStatus.CURRENT),
    "CG": StateCodeEntry("CG", "Chhattisgarh", StateCodeStatus.CURRENT),
    "DD": StateCodeEntry("DD", "Daman and Diu", StateCodeStatus.LEGACY),
    "DH": StateCodeEntry("DH", "Dadra and Nagar Haveli and Daman and Diu", StateCodeStatus.CURRENT),
    "DL": StateCodeEntry("DL", "Delhi", StateCodeStatus.CURRENT),
    "DN": StateCodeEntry("DN", "Dadra and Nagar Haveli", StateCodeStatus.LEGACY),
    "GA": StateCodeEntry("GA", "Goa", StateCodeStatus.CURRENT),
    "GJ": StateCodeEntry("GJ", "Gujarat", StateCodeStatus.CURRENT),
    "HR": StateCodeEntry("HR", "Haryana", StateCodeStatus.CURRENT),
    "HP": StateCodeEntry("HP", "Himachal Pradesh", StateCodeStatus.CURRENT),
    "JK": StateCodeEntry("JK", "Jammu and Kashmir", StateCodeStatus.CURRENT),
    "JH": StateCodeEntry("JH", "Jharkhand", StateCodeStatus.CURRENT),
    "KA": StateCodeEntry("KA", "Karnataka", StateCodeStatus.CURRENT),
    "KL": StateCodeEntry("KL", "Kerala", StateCodeStatus.CURRENT),
    "LA": StateCodeEntry("LA", "Ladakh", StateCodeStatus.CURRENT),
    "LD": StateCodeEntry("LD", "Lakshadweep", StateCodeStatus.CURRENT),
    "MP": StateCodeEntry("MP", "Madhya Pradesh", StateCodeStatus.CURRENT),
    "MH": StateCodeEntry("MH", "Maharashtra", StateCodeStatus.CURRENT),
    "MN": StateCodeEntry("MN", "Manipur", StateCodeStatus.CURRENT),
    "ML": StateCodeEntry("ML", "Meghalaya", StateCodeStatus.CURRENT),
    "MZ": StateCodeEntry("MZ", "Mizoram", StateCodeStatus.CURRENT),
    "NL": StateCodeEntry("NL", "Nagaland", StateCodeStatus.CURRENT),
    "OD": StateCodeEntry("OD", "Odisha", StateCodeStatus.CURRENT),
    "OR": StateCodeEntry("OR", "Odisha", StateCodeStatus.LEGACY),
    "PY": StateCodeEntry("PY", "Puducherry", StateCodeStatus.CURRENT),
    "PB": StateCodeEntry("PB", "Punjab", StateCodeStatus.CURRENT),
    "RJ": StateCodeEntry("RJ", "Rajasthan", StateCodeStatus.CURRENT),
    "SK": StateCodeEntry("SK", "Sikkim", StateCodeStatus.CURRENT),
    "TN": StateCodeEntry("TN", "Tamil Nadu", StateCodeStatus.CURRENT),
    "TS": StateCodeEntry("TS", "Telangana", StateCodeStatus.CURRENT),
    "TG": StateCodeEntry("TG", "Telangana", StateCodeStatus.CURRENT),
    "TR": StateCodeEntry("TR", "Tripura", StateCodeStatus.CURRENT),
    "UP": StateCodeEntry("UP", "Uttar Pradesh", StateCodeStatus.CURRENT),
    "UK": StateCodeEntry("UK", "Uttarakhand", StateCodeStatus.CURRENT),
    "UA": StateCodeEntry("UA", "Uttarakhand", StateCodeStatus.LEGACY),
    "WB": StateCodeEntry("WB", "West Bengal", StateCodeStatus.CURRENT),
}

# Backward compatibility mapping (code -> state name)
_INDIAN_STATE_CODES: Dict[str, str] = {
    code: entry.canonical_state for code, entry in STATE_CODE_REGISTRY.items()
}


# ── Blood Group Taxonomy ─────────────────────────────────────────────────────

VALID_BLOOD_GROUPS: Set[str] = {
    "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-",
    "A1+", "A1-", "A1B+", "A1B-", "A2+", "A2-", "A2B+", "A2B-",
}


# ── Vehicle Classes (COV) Taxonomy ───────────────────────────────────────────

KNOWN_VEHICLE_CLASSES: Dict[str, str] = {
    # Two-wheelers
    "MCWG": "Motor Cycle With Gear",
    "MCWOG": "Motor Cycle Without Gear",
    "M/CYCL.WG": "Motor Cycle With Gear",
    "M/CYCL.WOG": "Motor Cycle Without Gear",
    "MC WITH GEAR": "Motor Cycle With Gear",
    "MC WITHOUT GEAR": "Motor Cycle Without Gear",
    "M/CYCL": "Motorcycle",

    # Light vehicles
    "LMV": "Light Motor Vehicle",
    "LMV-NT": "Light Motor Vehicle - Non Transport",
    "LMV-TR": "Light Motor Vehicle - Transport",
    "3W-CAB": "Three Wheeler Cab",
    "3W-NT": "Three Wheeler Non-Transport",
    "3W-TR": "Three Wheeler Transport",
    "3W-GV": "Three Wheeler Goods Vehicle",

    # Medium and Heavy transport vehicles
    "TRANS": "Transport Vehicle",
    "HGMV": "Heavy Goods Motor Vehicle",
    "HPMV": "Heavy Passenger Motor Vehicle",
    "HTV": "Heavy Transport Vehicle",
    "HPV": "Heavy Passenger Vehicle",
    "HGV": "Heavy Goods Vehicle",
    "MGV": "Medium Goods Vehicle",
    "MMV": "Medium Motor Vehicle",
    "MPV": "Medium Passenger Vehicle",

    # Other categories
    "TRAILR": "Trailer",
    "TRLR": "Trailer",
    "E-RICKSHAW": "E-Rickshaw",
    "E-CART": "E-Cart",
    "ERICK": "E-Rickshaw",
    "ECART": "E-Cart",
    "PSV": "Public Service Vehicle",
    "D/CAB": "Dual Cab",
    "INVCRG": "Invalid Carriage",
    "LDRXCV": "Loader Excavator",
    "CRANE": "Crane",
    "FORK": "Forklift",
    "AGR-TRAC": "Agricultural Tractor",
    "TRACTOR": "Tractor",
}

COV_CANONICAL_MAP: Dict[str, str] = {
    "MCWG": "MCWG",
    "M/CYCL.WG": "MCWG",
    "MC WITH GEAR": "MCWG",
    "MCWOG": "MCWOG",
    "M/CYCL.WOG": "MCWOG",
    "MC WITHOUT GEAR": "MCWOG",
    "LMV": "LMV",
    "LMV-NT": "LMV-NT",
    "LMVNT": "LMV-NT",
    "LMV-TR": "LMV-TR",
    "LMVTR": "LMV-TR",
    "TRANS": "TRANS",
    "HGMV": "HGMV",
    "HPMV": "HPMV",
    "HTV": "HTV",
    "HPV": "HPV",
    "HGV": "HGV",
    "MGV": "MGV",
    "MMV": "MMV",
    "MPV": "MPV",
    "3W-CAB": "3W-CAB",
    "3WCAB": "3W-CAB",
    "3W-NT": "3W-NT",
    "3WNT": "3W-NT",
    "3W-TR": "3W-TR",
    "3WTR": "3W-TR",
    "3W-GV": "3W-GV",
    "TRAILR": "TRAILR",
    "TRLR": "TRAILR",
    "E-RICKSHAW": "E-RICKSHAW",
    "E-CART": "E-CART",
    "ERICK": "E-RICKSHAW",
    "ECART": "E-CART",
    "PSV": "PSV",
    "INVCRG": "INVCRG",
    "LDRXCV": "LDRXCV",
    "TRACTOR": "TRACTOR",
}

COV_LABEL_STOPWORDS: Set[str] = {
    "COV", "CLASS", "CLASSES", "VEHICLE", "VEHICLES",
    "AUTHORISATION", "AUTHORIZATION", "DRIVE", "OF", "TO",
    "VALID", "FROM", "DATE", "ISSUE",
}


@dataclass
class COVItem:
    """Individual vehicle class token result with recognition status."""
    code: str
    is_recognized: bool
    status: str = "RECOGNIZED_COV"
    description: Optional[str] = None
    raw: str = ""


@dataclass
class COVNormalizationResult:
    """Structured result for vehicle class extraction and normalization."""
    recognized: List[str] = field(default_factory=list)
    unrecognized: List[str] = field(default_factory=list)
    unrecognized_covs: List[str] = field(default_factory=list)
    items: List[COVItem] = field(default_factory=list)
    raw_tokens: List[str] = field(default_factory=list)
    status: NormalizationStatus = NormalizationStatus.UNKNOWN


# ── Month Name Mapping ───────────────────────────────────────────────────────

_MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


# ── 1. License Number Normalization ──────────────────────────────────────────

def normalize_license_number_detailed(raw: Optional[str]) -> NormalizationResult:
    """
    Representation-level normalization for Driving License number.

    Performs:
      - Unicode NFKC normalization
      - Whitespace trimming
      - Uppercasing
      - Removal of OCR-safe formatting separators (spaces, hyphens, slashes, dots)

    Rejects:
      - None, empty, or whitespace-only inputs (UNKNOWN)
      - Ambiguous inputs containing multiple distinct candidates (INVALID)
      - Malformed inputs containing illegal/corrupt non-separator characters (INVALID)

    Must NOT:
      - Invent missing characters or digits
      - Speculatively substitute letters/digits (e.g. O -> 0)
      - Decide whether the identifier is valid under MoRTH rules (that is VALIDATION)
    """
    if raw is None or not raw.strip():
        return NormalizationResult(status=NormalizationStatus.UNKNOWN, raw=raw)

    cleaned_raw = unicodedata.normalize("NFKC", raw).strip()

    # Ambiguity check: multiple distinct candidates separated by OR / AND / newline
    if re.search(r"[A-Za-z0-9]{9,}\s+(?:OR|AND|VS)\s+[A-Za-z0-9]{9,}", cleaned_raw, re.IGNORECASE):
        return NormalizationResult(
            status=NormalizationStatus.INVALID,
            raw=raw,
            details="Ambiguous license number input containing competing values.",
        )

    # Check for illegal/corrupt characters outside alphanumeric and safe separators [\\s\\-_/.]
    if re.search(r"[^A-Za-z0-9\s\-_/.]", cleaned_raw):
        return NormalizationResult(
            status=NormalizationStatus.INVALID,
            raw=raw,
            details=f"Input contains illegal/corrupt non-separator characters: '{cleaned_raw}'",
        )

    # Strip safe separators and uppercase
    norm_val = re.sub(r"[\s\-_/.]", "", cleaned_raw).upper()

    if not norm_val:
        return NormalizationResult(
            status=NormalizationStatus.INVALID,
            raw=raw,
            details="Input contains no alphanumeric identifier characters.",
        )

    st = NormalizationStatus.UNCHANGED if norm_val == cleaned_raw else NormalizationStatus.NORMALIZED
    return NormalizationResult(status=st, value=norm_val, raw=raw)


def normalize_license_number(raw: Optional[str]) -> Optional[str]:
    """
    Normalize driving license number representation safely.
    Returns normalized string if valid representation, None otherwise.
    """
    res = normalize_license_number_detailed(raw)
    if res.status in (NormalizationStatus.NORMALIZED, NormalizationStatus.UNCHANGED):
        return res.value
    return None


# ── 2. Date Normalization ────────────────────────────────────────────────────

def normalize_dl_date_detailed(raw: Optional[str]) -> NormalizationResult:
    """
    Parse explicitly recognized date representations into canonical ISO-8601 (YYYY-MM-DD).

    Supported explicitly recognized formats:
      - ISO: YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD, YYYY MM DD
      - DD MMM YYYY: 15 MAY 1992, 15-MAY-1992, 15/MAY/1992, 15.MAY.1992
      - DD MM YYYY: 15-05-1992, 15/05/1992, 15.05.1992, 15 05 1992

    Requirements:
      - Validates calendar dates strictly via datetime.date.
      - Invalid calendar dates (e.g. Feb 31, Apr 31, leap-year errors) return INVALID.
      - Never rolls dates forward/backward or repairs impossible dates.
      - Never infers missing year, day, or month (requires full 4-digit year).
      - Never assigns semantic roles to dates (that belongs to parser/layout logic).
    """
    if raw is None or not raw.strip():
        return NormalizationResult(status=NormalizationStatus.UNKNOWN, raw=raw)

    cleaned = unicodedata.normalize("NFKC", raw).strip()

    # Ambiguity check: date ranges or multiple dates (e.g. "15/05/1992 TO 14/05/2035")
    if re.search(r"\b(?:TO|UNTIL|UPTO|OR|AND)\b", cleaned, re.IGNORECASE) and len(re.findall(r"\d{2,4}", cleaned)) > 3:
        return NormalizationResult(
            status=NormalizationStatus.INVALID,
            raw=raw,
            details="Ambiguous date input containing a range or multiple candidates.",
        )

    # 1. Direct ISO YYYY-MM-DD (with -, /, ., or space)
    m_iso = re.match(r"^(\d{4})[-\/\. ](\d{1,2})[-\/\. ](\d{1,2})$", cleaned)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        try:
            iso_val = datetime.date(y, m, d).isoformat()
            st = NormalizationStatus.UNCHANGED if cleaned == iso_val else NormalizationStatus.NORMALIZED
            return NormalizationResult(status=st, value=iso_val, raw=raw)
        except ValueError as e:
            return NormalizationResult(
                status=NormalizationStatus.INVALID,
                raw=raw,
                details=f"Invalid calendar date in ISO pattern: {e}",
            )

    # 2. DD MMM YYYY (e.g. 15 MAY 1992 or 15-MAY-1992 or 15/MAY/1992)
    m_alpha = re.match(r"^(\d{1,2})[-\/\. ]([A-Za-z]{3,9})[-\/\. ](\d{4})$", cleaned)
    if m_alpha:
        d_val = int(m_alpha.group(1))
        mon_str = m_alpha.group(2).lower()
        y_val = int(m_alpha.group(3))
        month = _MONTH_MAP.get(mon_str) or _MONTH_MAP.get(mon_str[:3])
        if not month:
            return NormalizationResult(
                status=NormalizationStatus.INVALID,
                raw=raw,
                details=f"Unrecognized month name '{m_alpha.group(2)}'.",
            )
        try:
            iso_val = datetime.date(y_val, month, d_val).isoformat()
            return NormalizationResult(status=NormalizationStatus.NORMALIZED, value=iso_val, raw=raw)
        except ValueError as e:
            return NormalizationResult(
                status=NormalizationStatus.INVALID,
                raw=raw,
                details=f"Invalid calendar date in DD MMM YYYY pattern: {e}",
            )

    # 3. DD MM YYYY (e.g. 15/05/1992, 15-05-1992, 15.05.1992, 15 05 1992)
    m_dmy = re.match(r"^(\d{1,2})[-\/\. ](\d{1,2})[-\/\. ](\d{4})$", cleaned)
    if m_dmy:
        d_val, m_val, y_val = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        try:
            iso_val = datetime.date(y_val, m_val, d_val).isoformat()
            return NormalizationResult(status=NormalizationStatus.NORMALIZED, value=iso_val, raw=raw)
        except ValueError as e:
            return NormalizationResult(
                status=NormalizationStatus.INVALID,
                raw=raw,
                details=f"Invalid calendar date in DD-MM-YYYY pattern: {e}",
            )

    return NormalizationResult(
        status=NormalizationStatus.INVALID,
        raw=raw,
        details="Unrecognized date format or incomplete date components.",
    )


def normalize_dl_date(raw: Optional[str]) -> Optional[str]:
    """Parse recognized date representations into canonical ISO-8601 (YYYY-MM-DD)."""
    res = normalize_dl_date_detailed(raw)
    if res.status in (NormalizationStatus.NORMALIZED, NormalizationStatus.UNCHANGED):
        return res.value
    return None


# ── 3. Blood Group Normalization ─────────────────────────────────────────────

def normalize_blood_group_detailed(
    raw: Optional[str],
    allowed_groups: Optional[Set[str]] = None,
) -> NormalizationResult:
    """
    Safely normalize blood group strings.

    Order of operations:
      1. Unicode normalization and whitespace trimming.
      2. Normalize textual polarity ('POSITIVE' -> '+', 'NEGATIVE' -> '-')
         BEFORE any OCR-specific 'VE' removal. This prevents 'NEGATIVE' from
         being corrupted by accidental substring matching.
      3. Normalize OCR suffixes (e.g. '+VE' -> '+', '-VE' -> '-').
      4. Verify against the allowed blood-group taxonomy.
      5. Reject arbitrary strings; never guess the nearest blood group.
      6. 'AB' without +/- is only accepted if explicitly in allowed_groups.
    """
    if allowed_groups is None:
        allowed_groups = VALID_BLOOD_GROUPS

    if raw is None or not raw.strip():
        return NormalizationResult(status=NormalizationStatus.UNKNOWN, raw=raw)

    cleaned = unicodedata.normalize("NFKC", raw).strip().upper()

    # Ambiguity check
    if re.search(r"\b(?:OR|AND|/)\b", cleaned) and any(bg in cleaned for bg in ("+", "-", "POS", "NEG")):
        return NormalizationResult(
            status=NormalizationStatus.INVALID,
            raw=raw,
            details="Ambiguous blood group string with multiple candidates.",
        )

    # Step 1: Textual polarity normalization FIRST (word boundaries)
    cleaned = re.sub(r"\bPOSITIVE\b", "+", cleaned)
    cleaned = re.sub(r"\bNEGATIVE\b", "-", cleaned)
    cleaned = re.sub(r"\bPOS\.?\b", "+", cleaned)
    cleaned = re.sub(r"\bNEG\.?\b", "-", cleaned)

    # Step 2: OCR '+VE' / '-VE' cleanup (now safe because NEGATIVE was processed first)
    cleaned = re.sub(r"\+\s*VE\b", "+", cleaned)
    cleaned = re.sub(r"\-\s*VE\b", "-", cleaned)
    cleaned = re.sub(r"(?<=[+\-])\s*VE\b", "", cleaned)

    # Step 3: Remove all remaining whitespace
    compact = re.sub(r"\s+", "", cleaned)

    # Step 4: Validate strictly against allowed taxonomy
    if compact in allowed_groups:
        st = NormalizationStatus.UNCHANGED if compact == raw else NormalizationStatus.NORMALIZED
        return NormalizationResult(status=st, value=compact, raw=raw)

    return NormalizationResult(
        status=NormalizationStatus.INVALID,
        raw=raw,
        details=f"Value '{compact}' is not in the recognized blood group taxonomy.",
    )


def normalize_blood_group(
    raw: Optional[str],
    allowed_groups: Optional[Set[str]] = None,
) -> Optional[str]:
    """Normalize blood group string (e.g. 'O+ve', 'B POSITIVE', 'B NEGATIVE' -> 'O+', 'B+', 'B-')."""
    res = normalize_blood_group_detailed(raw, allowed_groups=allowed_groups)
    if res.status in (NormalizationStatus.NORMALIZED, NormalizationStatus.UNCHANGED):
        return res.value
    return None


# ── 4. Vehicle Classes (COV) Normalization ───────────────────────────────────

def normalize_vehicle_classes_detailed(
    raw: Optional[str],
    taxonomy: Optional[Dict[str, str]] = None,
    canonical_map: Optional[Dict[str, str]] = None,
) -> COVNormalizationResult:
    """
    Extract and normalize vehicle classes (COV) safely.

    Strict safety rules:
      - REMOVES the unsafe concept that 'any 3-5 character alphanumeric token is a COV'.
      - Recognizes only tokens present in the explicit configured taxonomy.
      - Preserves unrecognized OCR tokens without silently discarding them.
      - Flags unrecognized values as UNRECOGNIZED_COV for candidate/provenance tracking.
      - Never silently converts an arbitrary OCR token into a valid COV.
    """
    if taxonomy is None:
        taxonomy = KNOWN_VEHICLE_CLASSES
    if canonical_map is None:
        canonical_map = COV_CANONICAL_MAP

    result = COVNormalizationResult()
    if raw is None or not raw.strip():
        return result

    cleaned = unicodedata.normalize("NFKC", raw).strip()
    result.raw_tokens = [cleaned]

    # Delimit on comma, semicolon, newline, or multiple slashes
    parts = re.split(r"[,;\n\r]+", cleaned)

    recognized_set: Set[str] = set()
    unrecognized_list: List[str] = []
    items: List[COVItem] = []

    for part in parts:
        sub_tokens = part.strip().split()
        if not sub_tokens:
            continue

        # Check full sub-phrase first (e.g. "MC WITH GEAR", "3W-CAB")
        full_phrase = " ".join(sub_tokens).upper().strip(" :.-")
        if full_phrase in canonical_map:
            canon = canonical_map[full_phrase]
            recognized_set.add(canon)
            items.append(COVItem(
                code=canon,
                is_recognized=True,
                status="RECOGNIZED_COV",
                description=taxonomy.get(canon),
                raw=full_phrase,
            ))
            continue

        # Process individual tokens
        for token in sub_tokens:
            t_upper = token.upper().strip(" :.,;()[]")
            if not t_upper or t_upper in COV_LABEL_STOPWORDS:
                continue

            if t_upper in canonical_map:
                canon = canonical_map[t_upper]
                recognized_set.add(canon)
                items.append(COVItem(
                    code=canon,
                    is_recognized=True,
                    status="RECOGNIZED_COV",
                    description=taxonomy.get(canon),
                    raw=token,
                ))
            elif re.match(r"^[A-Z0-9\-\/]{2,10}$", t_upper):
                # Preserved unrecognized token — marked UNRECOGNIZED_COV, never accepted as valid
                unrecognized_list.append(t_upper)
                items.append(COVItem(
                    code=t_upper,
                    is_recognized=False,
                    status="UNRECOGNIZED_COV",
                    description=None,
                    raw=token,
                ))

    result.recognized = sorted(list(recognized_set))
    result.unrecognized = unrecognized_list
    result.unrecognized_covs = [f"UNRECOGNIZED_COV:{t}" for t in unrecognized_list]
    result.items = items

    if result.recognized and not result.unrecognized:
        result.status = NormalizationStatus.NORMALIZED
    elif result.recognized and result.unrecognized:
        result.status = NormalizationStatus.NORMALIZED
    elif result.unrecognized:
        result.status = NormalizationStatus.UNRECOGNIZED
    else:
        result.status = NormalizationStatus.UNKNOWN

    return result


def normalize_vehicle_classes(raw: Optional[str]) -> List[str]:
    """
    Extract recognized vehicle classes (MCWG, LMV, TRANS, etc.).
    Returns ONLY recognized classes from the configured taxonomy.
    Unrecognized tokens are safely filtered out and not converted to valid COVs.
    """
    return normalize_vehicle_classes_detailed(raw).recognized


# ── 5. State Code Normalization ──────────────────────────────────────────────

def normalize_state_code(code: Optional[str]) -> Optional[StateCodeEntry]:
    """
    Look up state code information including canonical state and legacy/current status.
    Preserves historical aliases (e.g. OR -> Odisha LEGACY, OD -> Odisha CURRENT).
    """
    if not code:
        return None
    cleaned = code.strip().upper()
    return STATE_CODE_REGISTRY.get(cleaned)


def extract_state_from_license_number(license_number: Optional[str]) -> Optional[str]:
    """
    Extract State/UT name from the first two letters of an Indian DL number.
    Provenance note: Derivation from the DL prefix is NOT proof of issuing authority.
    """
    if not license_number or len(license_number) < 2:
        return None
    code = license_number[:2].upper()
    entry = STATE_CODE_REGISTRY.get(code)
    return entry.canonical_state if entry else None


def extract_state_info_from_license_number(license_number: Optional[str]) -> Optional[StateCodeEntry]:
    """
    Extract detailed StateCodeEntry (canonical state and legacy/current status)
    from the first two letters of an Indian DL number.
    """
    if not license_number or len(license_number) < 2:
        return None
    code = license_number[:2].upper()
    return STATE_CODE_REGISTRY.get(code)


# ── 6. General Text Normalization ────────────────────────────────────────────

def normalize_dl_text_detailed(
    raw: Optional[str],
    strip_parentage: bool = True,
) -> NormalizationResult:
    """
    Clean and normalize general text fields (name, authority, etc.).

    Safe operations:
      - Unicode NFKC normalization
      - Standard whitespace condensation and trimming
      - Controlled uppercasing
      - Known parentage prefix removal ONLY at the start of string

    Must NOT:
      - Perform aggressive fuzzy correction that can alter identity information
        (e.g. BHARATH -> BHARAT or KUMAR -> KUMARH are prohibited).
      - Strip parentage letter sequences that legitimately form part of names
        (e.g. SOBHA, DORAIRAJ, WARREN, COLIN are preserved).
    """
    if raw is None or not raw.strip():
        return NormalizationResult(status=NormalizationStatus.UNKNOWN, raw=raw)

    cleaned = unicodedata.normalize("NFKC", raw)
    # Remove characters outside standard name/text characters
    cleaned = re.sub(r"[^\w\s\-\.,/']", " ", cleaned)

    if strip_parentage:
        # Strip common parentage prefixes ONLY at the start of string
        cleaned = re.sub(
            r"^(?:(?:S|D|W|C)/O|(?:SON|DAUGHTER|WIFE|CARE)\s+OF)\s*[:.\-]?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return NormalizationResult(
            status=NormalizationStatus.INVALID,
            raw=raw,
            details="Text contains no valid characters after normalization.",
        )

    upper_val = cleaned.upper()
    st = NormalizationStatus.UNCHANGED if upper_val == raw else NormalizationStatus.NORMALIZED
    return NormalizationResult(status=st, value=upper_val, raw=raw)


def normalize_dl_text(
    raw: Optional[str],
    strip_parentage: bool = True,
) -> Optional[str]:
    """Clean and normalize general text fields (name, authority, etc.)."""
    res = normalize_dl_text_detailed(raw, strip_parentage=strip_parentage)
    if res.status in (NormalizationStatus.NORMALIZED, NormalizationStatus.UNCHANGED):
        return res.value
    return None

