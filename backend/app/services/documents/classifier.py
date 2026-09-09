"""
backend/app/services/documents/classifier.py

Document Type Classification & Strict Verification Station Isolation Guard.

Enforces the operational security mandate:
Credentials submitted to the wrong verification station (e.g., a Passport
submitted to the Visa station, or a Driving License submitted to the Passport station)
must be strictly identified and rejected prior to pipeline execution.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Human-readable labels for document types
DOCUMENT_TYPE_LABELS = {
    "passport":        "Passport",
    "visa":            "Visa",
    "driving_license": "Driving License",
    "drivingLicense":  "Driving License",
    # Indian identity documents
    "aadhaar":         "Aadhaar Card",
    "aadhaarCard":     "Aadhaar Card",
    "voter_id":        "Voter ID / EPIC",
    "voterId":         "Voter ID / EPIC",
    "voterID":         "Voter ID / EPIC",
    "epic":            "Voter ID / EPIC",
    "pan_card":        "PAN Card",
    "panCard":         "PAN Card",
    # Legacy compat
    "national_id":     "Aadhaar Card (legacy)",
    "nationalId":      "Aadhaar Card (legacy)",
    "border_permit":   "Border / Work Permit",
    "borderPermit":    "Border / Work Permit",
}


@dataclass(frozen=True)
class DocumentClassificationResult:
    """Result of document type analysis from extracted OCR text."""
    declared_type: str
    detected_type: Optional[str]
    is_mismatch: bool
    confidence: float
    reasons: List[str]
    error_message: Optional[str] = None


def detect_document_type_from_text(raw_text: str) -> Optional[str]:
    """
    Examines extracted raw text lines / tokens and identifies the document type
    based on distinctive official headers, terminology, and structural markers.

    Returns the canonical document type key ('passport', 'visa', 'driving_license',
    'national_id', 'border_permit') or None if indeterminate.
    """
    if not raw_text:
        return None

    upper = raw_text.upper()

    # 1. Visa Markers (Checked first because Visas frequently mention "Passport No.")
    # A Visa document has primary headers like "ENTRY VISA", "VISA / VISA", "CONSULAR",
    # or an MRZ beginning with 'V<' (ICAO Doc 9303 MRVA/B).
    has_visa_header = any(k in upper for k in ["ENTRY VISA", "VISA / VISA", "VISA NUMBER", "TYPE OF VISA", "VISA TYPE"])
    has_visa_word = bool(re.search(r"\bVISA\b", upper)) and not any(k in upper for k in ["PASSPORT", "DRIVING LICENCE", "DRIVING LICENSE"])
    has_visa_mrz = bool(re.search(r"\bV[<A-Z0-9]{30,}", upper))

    if has_visa_header or (has_visa_word and "CONSULAR" in upper) or has_visa_mrz:
        return "visa"

    # 2. Border Permit / Work Permit Markers
    # Checked before Passport because Border / Work Permits routinely cite "Passport Number: ..."
    has_permit_header = any(k in upper for k in [
        "BORDER PERMIT", "ENTRY PERMIT", "CROSS-BORDER", "WORK PERMIT",
        "EMPLOYMENT PERMIT", "CROSSING PERMIT", "BORDER CONTROL", "REGIONAL BORDER",
        "BORDER MANAGEMENT"
    ]) or bool(re.search(r"\bPERMIT\s*NO\b", upper)) or bool(re.search(r"\bBP[-0-9]{5,}\b", upper))

    if has_permit_header:
        return "border_permit"

    # 3. Passport Markers
    # TD3 Passports prominently declare "PASSPORT", "REPUBLIC OF INDIA PASSPORT",
    # or have a TD3 MRZ beginning with 'P<'.
    has_passport_header = bool(re.search(r"\bPASSPORT\b", upper)) or "REPUBLIC OF INDIA" in upper or "PASSEPORT" in upper
    has_passport_mrz = bool(re.search(r"\bP<[A-Z]{3}", upper))

    # Guard: Ensure it's not a Visa or Permit citing a passport
    if (has_passport_header or has_passport_mrz) and not ("ENTRY VISA" in upper or "VISA NUMBER" in upper or has_permit_header):
        return "passport"

    # 4. Driving License Markers
    has_dl_header = any(k in upper for k in [
        "DRIVING LICENCE", "DRIVING LICENSE", "UNION OF INDIA DRIVING",
        "TRANSPORT DEPARTMENT", "MOTOR VEHICLES", "FORM 7", "COV", "MCWG"
    ]) or bool(re.search(r"\bDL\s*NO\b", upper))

    if has_dl_header:
        return "driving_license"

    # 5a. Aadhaar Card (UIDAI) — highest-specificity markers
    has_aadhaar_header = any(k in upper for k in [
        "AADHAAR", "UNIQUE IDENTIFICATION AUTHORITY OF INDIA", "MERA AADHAAR",
        "UIDAI", "ENROLMENT NO", "MERI PEHCHAN",
    ]) or bool(re.search(r"\b\d{4}\s\d{4}\s\d{4}\b", upper))

    if has_aadhaar_header and not has_passport_header and not has_dl_header:
        return "aadhaar"

    # 5b. Voter ID / EPIC — Election Commission markers
    has_voter_header = any(k in upper for k in [
        "ELECTION COMMISSION", "ELECTORS PHOTO IDENTITY", "EPIC", "ELECTORAL ROLL", "VOTER ID",
    ]) or bool(re.search(r"\b[A-Z]{3}\d{7}\b", upper))

    if has_voter_header and not has_passport_header and not has_dl_header:
        return "voter_id"

    # 5c. PAN Card — Income Tax Department markers
    has_pan_header = any(k in upper for k in [
        "INCOME TAX DEPARTMENT", "PERMANENT ACCOUNT NUMBER", "INCOME TAX INDIA",
        "NSDL", "UTIITSL",
    ]) or bool(re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", upper))

    if has_pan_header and not has_passport_header and not has_dl_header:
        return "pan_card"

    return None


def classify_and_guard_document_type(
    ocr_regions: list,
    declared_type: str,
) -> DocumentClassificationResult:
    """
    Classifies the document from OCR text and enforces strict type isolation.

    If a document exhibits unmistakable markers of Document Type A (e.g. Passport)
    while being submitted under Document Type B (e.g. Visa), this function
    flags a critical mismatch.
    """
    canonical_declared = declared_type.lower().strip()
    # Normalize aliases to canonical snake_case types
    if canonical_declared in ("drivinglicense", "driving_license", "dl"):
        canonical_declared = "driving_license"
    elif canonical_declared in ("aadhaarcard", "aadhaar", "uid"):
        canonical_declared = "aadhaar"
    elif canonical_declared in ("voterid", "voterid", "voter_id", "epic", "voter"):
        canonical_declared = "voter_id"
    elif canonical_declared in ("pancard", "pan_card", "pan"):
        canonical_declared = "pan_card"
    elif canonical_declared in ("nationalid", "national_id", "nid"):
        # Legacy fallback — route to aadhaar for detection purposes
        canonical_declared = "aadhaar"
    elif canonical_declared in ("borderpermit", "border_permit", "work_permit", "workpermit"):
        canonical_declared = "border_permit"

    # Combine all region text
    all_text = " \n ".join(getattr(r, "text", str(r)) for r in ocr_regions)
    detected = detect_document_type_from_text(all_text)

    if detected and detected != canonical_declared:
        detected_label = DOCUMENT_TYPE_LABELS.get(detected, detected.replace("_", " ").title())
        declared_label = DOCUMENT_TYPE_LABELS.get(canonical_declared, canonical_declared.replace("_", " ").title())

        err_msg = (
            f"DOCUMENT TYPE MISMATCH: The uploaded document was identified as a {detected_label}, "
            f"but was submitted to the {declared_label} verification section. "
            f"A {detected_label} cannot be verified in the {declared_label} section. "
            f"Please switch to the {detected_label} section to verify this credential."
        )
        logger.warning(
            "Document type mismatch rejected: declared=%s detected=%s",
            canonical_declared, detected,
        )
        return DocumentClassificationResult(
            declared_type=canonical_declared,
            detected_type=detected,
            is_mismatch=True,
            confidence=0.95,
            reasons=[f"Document text exhibits structural features of {detected_label}"],
            error_message=err_msg,
        )

    return DocumentClassificationResult(
        declared_type=canonical_declared,
        detected_type=detected or canonical_declared,
        is_mismatch=False,
        confidence=0.90 if detected else 0.50,
        reasons=["Declared document type matches detected optical structure"],
        error_message=None,
    )
