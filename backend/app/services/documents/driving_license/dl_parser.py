"""
backend/app/services/documents/driving_license/dl_parser.py

Deterministic Driving License field extraction from raw OCR regions.
Focused on Indian Driving Licence (MoRTH / Sarathi standard).
Preserves bounding boxes, confidence scores, and raw OCR text.

ARCHITECTURAL CONTRACT (Phase 2 — no-guessing hardening):
  The parser answers ONLY "what does the document appear to contain?".
  It must never fabricate, guess, silently repair, or arbitrarily select a
  field value when the OCR/layout evidence is ambiguous or insufficient.

  When evidence is insufficient, a field is left with value=None and its
  `status` records WHY: MISSING (no evidence at all), AMBIGUOUS (multiple
  competing candidates, none singled out by label/layout evidence), or
  LOW_CONFIDENCE (a single candidate below the OCR confidence floor).
  These are information-quality states, not authenticity findings — they
  must never be escalated into a forgery/tampering conclusion. That
  escalation, if any, belongs to the validator/forensics modules, not here.

  Structural/authenticity judgment (format validity, forgery, tampering)
  is explicitly out of scope for this module — see dl_validator.py (M2),
  the forensics engine (M3), and the registry engine (M5).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from app.schemas.ocr import OCRRegionRaw
from app.services.documents.driving_license.dl_field_normalizer import (
    extract_state_from_license_number,
    normalize_blood_group,
    normalize_dl_date,
    normalize_dl_text,
    normalize_license_number,
    normalize_vehicle_classes,
    normalize_vehicle_classes_detailed,
)

logger = logging.getLogger(__name__)

# OCR confidence floor below which a single, otherwise-valid candidate is
# still surfaced (value is kept — validators/officers may still want it)
# but flagged LOW_CONFIDENCE rather than treated as a clean FOUND result.
LOW_CONFIDENCE_THRESHOLD = 0.55


class FieldStatus(str, Enum):
    """Information-quality state of a parsed field. Never an authenticity verdict."""
    FOUND = "FOUND"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class DateRole(str, Enum):
    """Semantic role a date candidate is confidently tied to via label/layout evidence."""
    DOB = "DOB"
    ISSUE_DATE = "ISSUE_DATE"
    VALID_FROM = "VALID_FROM"
    EXPIRY_DATE = "EXPIRY_DATE"
    UNKNOWN_DATE = "UNKNOWN_DATE"


@dataclass
class DateCandidate:
    """
    A single date-shaped OCR observation, retained regardless of whether
    its role could be confidently resolved. Ambiguous/unresolved dates are
    preserved here rather than being discarded or guessed into a role.
    """
    raw_value: Optional[str] = None
    normalized_value: Optional[str] = None
    bbox: Optional[List[List[int]]] = None
    confidence: Optional[float] = None
    source: Optional[str] = None
    role: DateRole = DateRole.UNKNOWN_DATE
    status: FieldStatus = FieldStatus.FOUND


@dataclass
class DLField:
    """A single parsed driving license field with provenance and telemetry."""
    value: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[List[List[int]]] = None
    raw: Optional[str] = None
    # Phase 2 additions — additive, default-backed, backward compatible.
    status: FieldStatus = FieldStatus.MISSING
    source: Optional[str] = None
    candidates: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Preserve the historical contract used throughout the codebase and
        # tests: a DLField constructed with a plain value and no explicit
        # status is a clean FOUND result.
        if self.value is not None and self.status == FieldStatus.MISSING:
            self.status = FieldStatus.FOUND


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
    # Phase 2 addition — every date-shaped OCR observation on the document,
    # whether or not its semantic role (DOB/ISSUE_DATE/VALID_FROM/EXPIRY_DATE)
    # could be confidently resolved. Populated in addition to, never instead
    # of, the resolved dob/valid_from/valid_to fields above.
    date_candidates: List[DateCandidate] = field(default_factory=list)

    def to_dict(self) -> dict:
        """
        Serialize parsed fields, including both the DL-native snake_case keys
        and their TravelerFields-aligned aliases (licenseNumber, vehicleClass,
        bloodGroup, authority) so generic consumers that filter a traveler
        dict against TravelerFields.model_fields (e.g. the orchestrator) do
        not silently drop DL-specific fields. Mirrors the alias convention
        already used by aadhaar_parser.to_dict().
        """
        return {
            "docNumber": self.docNumber.value or self.license_number.value,
            "license_number": self.license_number.value,
            "licenseNumber": self.license_number.value,
            "name": self.name.value,
            "dob": self.dob.value,
            "valid_from": self.valid_from.value,
            "valid_to": self.valid_to.value,
            "issuedDate": self.issuedDate.value or self.valid_from.value,
            "expiry": self.expiry.value or self.valid_to.value,
            "blood_group": self.blood_group.value,
            "bloodGroup": self.blood_group.value,
            "vehicle_classes": self.vehicle_classes.value,
            "vehicleClass": self.vehicle_classes.value,
            "issuing_authority": self.issuing_authority.value,
            "authority": self.issuing_authority.value,
            "state": self.state.value,
            "address": self.address.value,
        }


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

    Phase 2 contract: a field is populated ONLY when label/layout evidence
    confidently ties a value to that field's semantic role. When multiple
    candidates compete for a role and none is distinguished by evidence,
    the field is left unset with status=AMBIGUOUS and every competing raw
    candidate is preserved on DLField.candidates — never resolved by
    picking the first, last, longest, or highest-confidence candidate.
    """
    result = ParsedDrivingLicenseData()
    if not regions:
        result.unsupported_layout = True
        return result

    lines: List[Tuple[str, float, List[List[int]]]] = [
        (r.text.strip(), r.confidence, r.bbox) for r in regions if r.text.strip()
    ]
    all_text_combined = " ".join([t[0].upper() for t in lines])

    def _text_below(label_bbox, max_dy: int = 60):
        """
        Find the OCR line whose bbox sits directly below label_bbox (same
        column, next row down). Multi-column DL layouts (DOB next to Blood
        Group, Vehicle Class next to smart-card metadata, etc.) print several
        labels on one row and their values on the row(s) beneath — the next
        OCR line in reading order is often a neighboring column's label
        rather than this label's own value.
        """
        if not label_bbox:
            return None
        lx0, ly0 = label_bbox[0]
        lx1 = label_bbox[1][0] if len(label_bbox) > 1 else lx0 + 100
        ly_bottom = max(pt[1] for pt in label_bbox)
        best = None
        best_dy = None
        for cand_text, cand_conf, cand_bbox in lines:
            if not cand_bbox:
                continue
            cx0, cy0 = cand_bbox[0]
            dy = cy0 - ly_bottom
            if dy <= 0 or dy > max_dy:
                continue
            cx1 = cand_bbox[1][0] if len(cand_bbox) > 1 else cx0 + 100
            overlap = min(lx1, cx1) - max(lx0, cx0)
            if overlap <= -20:
                continue
            if best_dy is None or dy < best_dy:
                best = (cand_text, cand_conf, cand_bbox)
                best_dy = dy
        return best

    def _apply_confidence_status(f: DLField) -> DLField:
        """A single accepted candidate below the OCR confidence floor is kept
        (never discarded) but flagged LOW_CONFIDENCE rather than FOUND."""
        if f.value is not None and f.confidence is not None and f.confidence < LOW_CONFIDENCE_THRESHOLD:
            f.status = FieldStatus.LOW_CONFIDENCE
        return f

    # Check for general Driving License indication
    dl_indicators = [
        "DRIVING", "LICENCE", "LICENSE", "UNION OF INDIA",
        "TRANSPORT", "DL NO", "FORM 7", "SARATHI",
    ]
    has_dl_indicator = any(kw in all_text_combined for kw in dl_indicators)

    # ── Field 1: License Number ──────────────────────────────────────────────
    # Collect every distinct candidate found by any detection mechanism
    # across the whole document before deciding — a single early match is
    # no longer accepted purely because it was encountered first.
    license_candidates: List[Tuple[str, float, List[List[int]], str]] = []  # (norm, conf, bbox, raw)

    def _add_license_candidate(norm_val, conf, bbox, raw):
        if norm_val and not any(norm_val == c[0] for c in license_candidates):
            license_candidates.append((norm_val, conf, bbox, raw))

    for idx, (text, conf, bbox) in enumerate(lines):
        clean_upper = text.upper()

        # Regex for labeled DL No: e.g. DL NO : DL0420110012345 or LICENCE NO: TN09 20201234567
        m_labeled = re.search(
            r"(?:DL\s*(?:NO|NUM|NUMBER|#)?|LICENCE\s*(?:NO|NUM)?|LICENSE\s*(?:NO|NUM)?)\s*[:.\-]?\s*([A-Z]{2}[-\s]?\d{2}[-\s]?(?:19|20)?\d{2,4}[-\s]?\d{4,8})",
            clean_upper,
        )
        if m_labeled:
            norm_val = normalize_license_number(m_labeled.group(1))
            if norm_val and len(norm_val) >= 9:
                _add_license_candidate(norm_val, conf, bbox, m_labeled.group(1))
                continue  # labeled match on this line is authoritative for this line

        # Check next line if label is alone
        if clean_upper in ("DL NO", "DL NO.", "LICENCE NO", "LICENCE NO.", "LICENSE NO", "LICENSE NO.") and idx + 1 < len(lines):
            next_text = lines[idx + 1][0]
            norm_val = normalize_license_number(next_text)
            if norm_val and len(norm_val) >= 9:
                _add_license_candidate(norm_val, lines[idx + 1][1], lines[idx + 1][2], next_text)
                continue

        # Direct pattern match: e.g. TN0920201234567 or DL0420110012345 (2 letters, 2 digits, 4 digits year, 7 digits seq)
        m_direct = re.search(r"\b([A-Z]{2}[-\s]?\d{2}[-\s]?(?:19|20)\d{2}[-\s]?\d{7})\b", clean_upper)
        if m_direct:
            norm_val = normalize_license_number(m_direct.group(1))
            if norm_val:
                _add_license_candidate(norm_val, conf, bbox, m_direct.group(1))

    if len(license_candidates) == 1:
        norm_val, conf, bbox, raw = license_candidates[0]
        result.license_number = _apply_confidence_status(
            DLField(value=norm_val, confidence=conf, bbox=bbox, raw=raw, source="LABEL_OR_PATTERN_MATCH")
        )
    elif len(license_candidates) > 1:
        # Multiple distinct license-number-shaped values found with no
        # evidence to prefer one — surface ambiguity rather than silently
        # taking whichever appeared first in reading order.
        result.license_number = DLField(
            status=FieldStatus.AMBIGUOUS,
            candidates=[c[0] for c in license_candidates],
            source="LABEL_OR_PATTERN_MATCH",
        )
        logger.warning(
            "Driving license parser: %d competing license-number candidates found, none resolved: %s",
            len(license_candidates), [c[0] for c in license_candidates],
        )

    # Alias docNumber to license_number
    result.docNumber = result.license_number

    # Derive State from license number ONLY when the license number itself
    # was unambiguously resolved. The derived value's provenance explicitly
    # records that it is inferred from the identifier prefix, not read
    # directly off the card and not proof of the issuing authority.
    if result.license_number.status == FieldStatus.FOUND or result.license_number.status == FieldStatus.LOW_CONFIDENCE:
        state_name = extract_state_from_license_number(result.license_number.value)
        if state_name:
            result.state = DLField(
                value=state_name,
                confidence=result.license_number.confidence,
                raw=result.license_number.value[:2],
                source="DERIVED_FROM_LICENSE_NUMBER",
            )

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
                result.dob = _apply_confidence_status(
                    DLField(value=norm_dob, confidence=conf, bbox=bbox, raw=m_dob.group(1), source="LABELED_SAME_LINE")
                )
                result.date_candidates.append(DateCandidate(
                    raw_value=m_dob.group(1), normalized_value=norm_dob, bbox=bbox, confidence=conf,
                    source="LABELED_SAME_LINE", role=DateRole.DOB, status=FieldStatus.FOUND,
                ))
                break

        if any(kw in clean_upper for kw in ("DOB", "D.O.B", "DATE OF BIRTH", "DATE OFBIRTH", "BIRTH DATE")):
            # A label with no inline value: look ahead for a date-shaped line,
            # but only accept it if exactly one such candidate is found
            # before the window closes — two competing dates in the window
            # means the label-to-value association itself is ambiguous.
            lookahead_dates = []
            for look_ahead in range(1, min(4, len(lines) - idx)):
                candidate_text = lines[idx + look_ahead][0]
                m_dt = re.search(r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", candidate_text)
                if m_dt:
                    norm_dob = normalize_dl_date(m_dt.group(1))
                    if norm_dob:
                        lookahead_dates.append((norm_dob, lines[idx + look_ahead][1], lines[idx + look_ahead][2], m_dt.group(1)))
            if len(lookahead_dates) == 1 and not result.dob.value:
                norm_dob, dconf, dbbox, draw = lookahead_dates[0]
                result.dob = _apply_confidence_status(
                    DLField(value=norm_dob, confidence=dconf, bbox=dbbox, raw=draw, source="LABELED_LOOKAHEAD")
                )
                result.date_candidates.append(DateCandidate(
                    raw_value=draw, normalized_value=norm_dob, bbox=dbbox, confidence=dconf,
                    source="LABELED_LOOKAHEAD", role=DateRole.DOB, status=FieldStatus.FOUND,
                ))
            elif len(lookahead_dates) > 1 and not result.dob.value:
                result.dob = DLField(
                    status=FieldStatus.AMBIGUOUS,
                    candidates=[d[0] for d in lookahead_dates],
                    source="LABELED_LOOKAHEAD",
                )
                for norm_dob, dconf, dbbox, draw in lookahead_dates:
                    result.date_candidates.append(DateCandidate(
                        raw_value=draw, normalized_value=norm_dob, bbox=dbbox, confidence=dconf,
                        source="LABELED_LOOKAHEAD", role=DateRole.UNKNOWN_DATE, status=FieldStatus.AMBIGUOUS,
                    ))
            if result.dob.value:
                break

    # ── Field 3: Name ────────────────────────────────────────────────────────
    labeled_name: Optional[DLField] = None
    for idx, (text, conf, bbox) in enumerate(lines):
        clean_upper = text.upper()
        # Labeled Name
        m_name = re.search(
            r"(?:NAME|HOLDER(?:'S)?\s*NAME|BEARER)\s*[:.\-]?\s*([A-Z\s]{2,40})",
            clean_upper,
        )
        if m_name and not labeled_name:
            candidate = m_name.group(1).strip()
            # Avoid picking up labels
            if candidate and not any(kw in candidate for kw in ("DATE", "DOB", "VALID", "FATHER", "S/O", "ADDRESS", "INDIAN")):
                norm_name = normalize_dl_text(candidate)
                if norm_name and len(norm_name) >= 2:
                    labeled_name = _apply_confidence_status(
                        DLField(value=norm_name, confidence=conf, bbox=bbox, raw=candidate, source="LABELED_SAME_LINE")
                    )
                    break

        if any(clean_upper == kw for kw in ("NAME", "NAME:", "HOLDER NAME", "HOLDER NAME:", "HOLDER'S NAME:", "BEARER NAME:")) and idx + 1 < len(lines) and not labeled_name:
            next_text = lines[idx + 1][0]
            norm_name = normalize_dl_text(next_text)
            if norm_name and len(norm_name) >= 2 and not any(kw in norm_name for kw in ("DOB", "VALID", "FATHER", "ADDRESS", "INDIAN")):
                labeled_name = _apply_confidence_status(
                    DLField(value=norm_name, confidence=lines[idx + 1][1], bbox=lines[idx + 1][2], raw=next_text, source="LABELED_LOOKAHEAD")
                )
                break

    # Positional fallback: the line immediately preceding a parentage marker
    # (S/O, D/O, W/O). This is real layout evidence (Indian DL cards
    # consistently print the bearer name directly above the parentage line)
    # for documents that have NO explicit NAME label at all — it is only
    # ever attempted when the labeled mechanism above found nothing, never
    # used to second-guess a clean labeled match. A card can legitimately
    # print several unrelated short lines (e.g. "Organ Donor: N") between
    # the actual name block and the parentage line, so this heuristic is
    # weaker than an explicit label and must not be allowed to veto one.
    if not labeled_name:
        for idx, (text, conf, bbox) in enumerate(lines):
            clean_upper = text.upper()
            if "S/O" in clean_upper or "D/O" in clean_upper or "W/O" in clean_upper or "SON/DAUGHTER" in clean_upper:
                if idx > 0:
                    prev_text = lines[idx - 1][0]
                    norm_prev = normalize_dl_text(prev_text)
                    if norm_prev and not any(
                        kw in norm_prev
                        for kw in ("LICENCE", "UNION", "INDIA", "TRANSPORT", "DL", "DATE", "ORGAN", "DONOR", "BLOOD", "GROUP", "ADDRESS", "VALID", "ISSUE")
                    ):
                        result.name = _apply_confidence_status(
                            DLField(value=norm_prev, confidence=lines[idx - 1][1], bbox=lines[idx - 1][2], raw=prev_text, source="POSITIONAL_ABOVE_PARENTAGE_LINE")
                        )
                        break
    else:
        result.name = labeled_name

    # ── Field 4: Validity Dates (valid_from, valid_to) ───────────────────────
    # Labeled matches are the only mechanism trusted to assign a role
    # (VALID_FROM / EXPIRY_DATE). There is NO cross-document "pick the
    # latest remaining date" fallback: an unresolved role stays null and
    # status=MISSING/AMBIGUOUS, with the observed date preserved only as an
    # UNKNOWN_DATE candidate for officer/audit visibility.
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
                result.valid_to = _apply_confidence_status(
                    DLField(value=norm_exp, confidence=conf, bbox=bbox, raw=m_expiry.group(1), source="LABELED_SAME_LINE")
                )
                result.expiry = result.valid_to
                result.date_candidates.append(DateCandidate(
                    raw_value=m_expiry.group(1), normalized_value=norm_exp, bbox=bbox, confidence=conf,
                    source="LABELED_SAME_LINE", role=DateRole.EXPIRY_DATE, status=FieldStatus.FOUND,
                ))

        if any(kw in clean_upper for kw in ("VALID TILL", "VALIDITY (NT)", "VALIDITY(NT)", "VALID UPTO", "VALID UNTIL", "EXPIRY")) and not result.valid_to.value:
            lookahead_dates = []
            for look_ahead in range(1, min(5, len(lines) - idx)):
                candidate_text = lines[idx + look_ahead][0]
                m_dt = re.search(r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", candidate_text)
                if m_dt:
                    norm_exp = normalize_dl_date(m_dt.group(1))
                    if norm_exp:
                        lookahead_dates.append((norm_exp, lines[idx + look_ahead][1], lines[idx + look_ahead][2], m_dt.group(1)))
            if len(lookahead_dates) == 1:
                norm_exp, dconf, dbbox, draw = lookahead_dates[0]
                result.valid_to = _apply_confidence_status(
                    DLField(value=norm_exp, confidence=dconf, bbox=dbbox, raw=draw, source="LABELED_LOOKAHEAD")
                )
                result.expiry = result.valid_to
                result.date_candidates.append(DateCandidate(
                    raw_value=draw, normalized_value=norm_exp, bbox=dbbox, confidence=dconf,
                    source="LABELED_LOOKAHEAD", role=DateRole.EXPIRY_DATE, status=FieldStatus.FOUND,
                ))
            elif len(lookahead_dates) > 1:
                result.valid_to = DLField(
                    status=FieldStatus.AMBIGUOUS,
                    candidates=[d[0] for d in lookahead_dates],
                    source="LABELED_LOOKAHEAD",
                )
                result.expiry = result.valid_to
                for norm_exp, dconf, dbbox, draw in lookahead_dates:
                    result.date_candidates.append(DateCandidate(
                        raw_value=draw, normalized_value=norm_exp, bbox=dbbox, confidence=dconf,
                        source="LABELED_LOOKAHEAD", role=DateRole.UNKNOWN_DATE, status=FieldStatus.AMBIGUOUS,
                    ))

        # Valid From / Date of Issue
        m_doi = re.search(
            r"(?:VALID\s*FROM|ISSUE\s*DATE|DATE\s*OF\s*(?:FIRST\s*)?ISSUE|DOI)\s*[:.\-]?\s*([0-9A-Za-z\/\.\-]+)",
            clean_upper,
        )
        if m_doi and not result.valid_from.value:
            norm_doi = normalize_dl_date(m_doi.group(1))
            if norm_doi:
                result.valid_from = _apply_confidence_status(
                    DLField(value=norm_doi, confidence=conf, bbox=bbox, raw=m_doi.group(1), source="LABELED_SAME_LINE")
                )
                result.issuedDate = result.valid_from
                result.date_candidates.append(DateCandidate(
                    raw_value=m_doi.group(1), normalized_value=norm_doi, bbox=bbox, confidence=conf,
                    source="LABELED_SAME_LINE", role=DateRole.ISSUE_DATE, status=FieldStatus.FOUND,
                ))

        if any(kw in clean_upper for kw in ("ISSUE DATE", "ISSUEDATE", "DATE OF ISSUE", "DATE OF FIRST ISSUE", "VALID FROM")) and not result.valid_from.value:
            lookahead_dates = []
            for look_ahead in range(1, min(5, len(lines) - idx)):
                candidate_text = lines[idx + look_ahead][0]
                m_dt = re.search(r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", candidate_text)
                if m_dt:
                    norm_doi = normalize_dl_date(m_dt.group(1))
                    if norm_doi:
                        lookahead_dates.append((norm_doi, lines[idx + look_ahead][1], lines[idx + look_ahead][2], m_dt.group(1)))
            if len(lookahead_dates) == 1:
                norm_doi, dconf, dbbox, draw = lookahead_dates[0]
                result.valid_from = _apply_confidence_status(
                    DLField(value=norm_doi, confidence=dconf, bbox=dbbox, raw=draw, source="LABELED_LOOKAHEAD")
                )
                result.issuedDate = result.valid_from
                result.date_candidates.append(DateCandidate(
                    raw_value=draw, normalized_value=norm_doi, bbox=dbbox, confidence=dconf,
                    source="LABELED_LOOKAHEAD", role=DateRole.ISSUE_DATE, status=FieldStatus.FOUND,
                ))
            elif len(lookahead_dates) > 1:
                result.valid_from = DLField(
                    status=FieldStatus.AMBIGUOUS,
                    candidates=[d[0] for d in lookahead_dates],
                    source="LABELED_LOOKAHEAD",
                )
                result.issuedDate = result.valid_from
                for norm_doi, dconf, dbbox, draw in lookahead_dates:
                    result.date_candidates.append(DateCandidate(
                        raw_value=draw, normalized_value=norm_doi, bbox=dbbox, confidence=dconf,
                        source="LABELED_LOOKAHEAD", role=DateRole.UNKNOWN_DATE, status=FieldStatus.AMBIGUOUS,
                    ))

    # Every remaining date-shaped OCR line that was never claimed by a
    # labeled extraction above is preserved for visibility as an
    # UNKNOWN_DATE candidate. It is NEVER promoted into valid_from/expiry —
    # there is no "pick the latest future date" resolution step.
    _claimed_raw = {dc.raw_value for dc in result.date_candidates}
    for text, conf, bbox in lines:
        for m in re.finditer(r"\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b", text):
            raw_val = m.group(1)
            if raw_val in _claimed_raw:
                continue
            nd = normalize_dl_date(raw_val)
            if nd:
                result.date_candidates.append(DateCandidate(
                    raw_value=raw_val, normalized_value=nd, bbox=bbox, confidence=conf,
                    source="UNLABELED_TEXT_SCAN", role=DateRole.UNKNOWN_DATE, status=FieldStatus.UNKNOWN,
                ))
                _claimed_raw.add(raw_val)

    # ── Field 5: Blood Group ─────────────────────────────────────────────────
    for idx, (text, conf, bbox) in enumerate(lines):
        clean_upper = text.upper()
        m_bg = re.search(
            r"(?:BLOOD\s*(?:GRP|GROUP)|BG)\s*[:.\-]?\s*([A-Z0-9\+\-]+)",
            clean_upper,
        )
        if m_bg and not result.blood_group.value and result.blood_group.status == FieldStatus.MISSING:
            norm_bg = normalize_blood_group(m_bg.group(1))
            if norm_bg:
                result.blood_group = _apply_confidence_status(
                    DLField(value=norm_bg, confidence=conf, bbox=bbox, raw=m_bg.group(1), source="LABELED_SAME_LINE")
                )
                break
            else:
                # A blood-group label produced a candidate that does not
                # match any recognized ABO/Rh group — preserve it as an
                # unresolved candidate rather than silently discarding it
                # (which would be indistinguishable from the field being
                # entirely absent from the document).
                result.blood_group = DLField(
                    status=FieldStatus.UNKNOWN,
                    candidates=[m_bg.group(1)],
                    confidence=conf,
                    bbox=bbox,
                    raw=m_bg.group(1),
                    source="LABELED_SAME_LINE",
                )
        elif re.search(r"(?:BLOOD\s*(?:GRP|GROUP)?|BG)\s*$", clean_upper):
            below = _text_below(bbox)
            if below and not result.blood_group.value and result.blood_group.status == FieldStatus.MISSING:
                norm_bg = normalize_blood_group(below[0].strip())
                if norm_bg:
                    result.blood_group = _apply_confidence_status(
                        DLField(value=norm_bg, confidence=below[1], bbox=below[2], raw=below[0], source="LABELED_LOOKAHEAD")
                    )
                    break
                else:
                    result.blood_group = DLField(
                        status=FieldStatus.UNKNOWN,
                        candidates=[below[0].strip()],
                        confidence=below[1],
                        bbox=below[2],
                        raw=below[0],
                        source="LABELED_LOOKAHEAD",
                    )

    # ── Field 6: Vehicle Classes (COV) ───────────────────────────────────────
    # Phase 3 hardening: uses explicit configured taxonomy in dl_field_normalizer.
    # Recognized classes populate `value`; unrecognized tokens are preserved in
    # `candidates` with status UNKNOWN / UNRECOGNIZED — never silently accepted.
    for idx, (text, conf, bbox) in enumerate(lines):
        clean_upper = text.upper()
        is_cov_label = any(kw in clean_upper for kw in ("COV", "CLASS OF VEHICLE", "VEHICLE CLASS", "AUTHORISATION TO DRIVE"))
        if not is_cov_label:
            continue
        # Try the label line itself first (covers "COV: MCWG, LMV" inline layouts)
        cov_res = normalize_vehicle_classes_detailed(clean_upper)
        source = "LABELED_SAME_LINE"
        if not cov_res.recognized and not cov_res.unrecognized and idx + 1 < len(lines):
            # Label-only line (e.g. "CLASS OF VEHICLES (COV)") — value is on the next line.
            cov_res = normalize_vehicle_classes_detailed(lines[idx + 1][0].upper())
            source = "LABELED_LOOKAHEAD"
        recognized = cov_res.recognized
        unrecognized = cov_res.unrecognized
        if (recognized or unrecognized) and not result.vehicle_classes.value and result.vehicle_classes.status == FieldStatus.MISSING:
            if recognized:
                result.vehicle_classes = _apply_confidence_status(
                    DLField(
                        value=", ".join(recognized),
                        confidence=conf,
                        bbox=bbox,
                        raw=clean_upper,
                        source=source,
                        candidates=unrecognized,
                    )
                )
            else:
                # Every token extracted is outside the known COV taxonomy —
                # do not guess that an unfamiliar token is a valid class.
                # Preserve it for officer/audit visibility only.
                result.vehicle_classes = DLField(
                    status=FieldStatus.UNKNOWN,
                    candidates=unrecognized,
                    confidence=conf,
                    bbox=bbox,
                    raw=clean_upper,
                    source=source,
                )
            break

    # ── Field 7: Issuing Authority / RTO ─────────────────────────────────────
    for idx, (text, conf, bbox) in enumerate(lines):
        clean_upper = text.upper()
        # "RTO"/"DTO" followed directly by a place name (e.g. "RTO DELHI CENTRAL")
        # is itself the office name — keep the prefix rather than treating it as
        # a bare label to strip.
        m_office = re.match(r"^(RTO|DTO)\s+([A-Za-z][A-Za-z\s,\-]{2,40})$", clean_upper)
        if m_office and not result.issuing_authority.value:
            norm_auth = normalize_dl_text(clean_upper)
            if norm_auth:
                result.issuing_authority = _apply_confidence_status(
                    DLField(value=norm_auth, confidence=conf, bbox=bbox, raw=clean_upper, source="OFFICE_PREFIX_PATTERN")
                )
                break

        m_auth = re.search(
            r"(?:ISSUING\s*AUTHORITY|LICENSING\s*AUTHORITY)\s*[:.\-]?\s*([A-Za-z0-9\s,\-]+)",
            clean_upper,
        )
        if m_auth and m_auth.group(1).strip() and not result.issuing_authority.value:
            norm_auth = normalize_dl_text(m_auth.group(1))
            if norm_auth and len(norm_auth) >= 3:
                result.issuing_authority = _apply_confidence_status(
                    DLField(value=norm_auth, confidence=conf, bbox=bbox, raw=m_auth.group(1), source="LABELED_SAME_LINE")
                )
                break
        elif (
            not result.issuing_authority.value
            and re.search(r"(?:ISSUING\s*AUTHORITY|LICENSING\s*AUTHORITY)\s*$", clean_upper)
        ):
            below = _text_below(bbox)
            if below:
                norm_auth = normalize_dl_text(below[0])
                if norm_auth and len(norm_auth) >= 3:
                    result.issuing_authority = _apply_confidence_status(
                        DLField(value=norm_auth, confidence=below[1], bbox=below[2], raw=below[0], source="LABELED_LOOKAHEAD")
                    )
                    break

    # ── Profile Compatibility Assessment ─────────────────────────────────────
    # If there are zero indicators and no primary fields, flag unsupported layout
    primary_fields_count = sum(1 for f in [result.license_number.value, result.name.value, result.dob.value] if f)
    if not has_dl_indicator and primary_fields_count == 0:
        result.unsupported_layout = True
        logger.warning("Driving license parser: document lacks recognizable DL layout or fields.")

    return result
