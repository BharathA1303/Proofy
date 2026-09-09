"""
backend/app/services/documents/aadhaar/aadhaar_qr_validator.py

QR / Barcode validation for UIDAI Aadhaar cards.
Crucial Semantics:
- A decoded QR payload is labeled 'PAYLOAD_DECODED', NEVER 'AUTHENTICATED'.
- Decoded fields are compared against OCR fields to yield 'MATCHED' or 'MISMATCH'.
- Does NOT claim cryptographic authenticity without public-key signature verification.
"""
from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from app.services.documents.aadhaar.aadhaar_identifier_validator import (
    mask_aadhaar,
    normalize_aadhaar,
)

logger = logging.getLogger(__name__)

# Backward compatibility aliases used by orchestrator
mask_national_id = mask_aadhaar
normalize_national_id = normalize_aadhaar


class QRStatus(str, Enum):
    NOT_FOUND = "NOT_FOUND"
    PAYLOAD_DECODED = "PAYLOAD_DECODED"
    PAYLOAD_MALFORMED = "PAYLOAD_MALFORMED"
    UNAUTHENTICATED = "UNAUTHENTICATED"


class FieldComparisonResult(str, Enum):
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


def parse_national_id_qr_payload(payload: str) -> Dict[str, Any]:
    """
    Parse a QR code payload from a UIDAI Aadhaar card.
    Supports:
      - Standard XML format (<PrintLetterBarcodeData uid="..." name="..." dob="..." gender="..." />)
      - JSON format ({"uid": "...", "name": "...", "dob": "..."})
      - Delimited text (UID:123456789012|NAME:JOHN DOE|DOB:01/01/1990)
    """
    res = {
        "status": QRStatus.PAYLOAD_DECODED.value,
        "is_authenticated": False,  # Strict: payload decoded != authenticated
        "identity_number": None,
        "masked_identity_number": None,
        "name": None,
        "dob": None,
        "year_of_birth": None,
        "gender": None,
        "address": None,
        "raw_payload": payload,
    }

    if not payload or not isinstance(payload, str):
        res["status"] = QRStatus.NOT_FOUND.value
        return res

    clean = payload.strip()
    if not clean:
        res["status"] = QRStatus.NOT_FOUND.value
        return res

    # 1. XML parsing (standard UIDAI barcode data format)
    if "<PrintLetterBarcodeData" in clean or "uid=" in clean:
        uid_match    = re.search(r'uid=["\']([\S]+)["\']', clean, re.IGNORECASE)
        name_match   = re.search(r'name=["\']([\S][^"\']*)["\']', clean, re.IGNORECASE)
        dob_match    = re.search(r'dob=["\']([\S]+)["\']', clean, re.IGNORECASE)
        yob_match    = re.search(r'yob=["\']([\S]+)["\']', clean, re.IGNORECASE)
        gender_match = re.search(r'gender=["\']([\S]+)["\']', clean, re.IGNORECASE)
        co_match     = re.search(r'co=["\']([\S][^"\']*)["\']', clean, re.IGNORECASE)
        house_match  = re.search(r'house=["\']([\S][^"\']*)["\']', clean, re.IGNORECASE)
        loc_match    = re.search(r'loc=["\']([\S][^"\']*)["\']', clean, re.IGNORECASE)
        vtc_match    = re.search(r'vtc=["\']([\S][^"\']*)["\']', clean, re.IGNORECASE)
        dist_match   = re.search(r'dist=["\']([\S][^"\']*)["\']', clean, re.IGNORECASE)
        state_match  = re.search(r'state=["\']([\S][^"\']*)["\']', clean, re.IGNORECASE)
        pc_match     = re.search(r'pc=["\']([\S]+)["\']', clean, re.IGNORECASE)

        if uid_match:
            uid_norm, _ = normalize_aadhaar(uid_match.group(1))
            res["identity_number"] = uid_norm
            res["masked_identity_number"] = mask_aadhaar(uid_norm)
        if name_match:
            res["name"] = name_match.group(1).strip().upper()
        if dob_match:
            res["dob"] = dob_match.group(1).strip()
        if yob_match:
            try:
                res["year_of_birth"] = int(yob_match.group(1).strip())
            except ValueError:
                pass
        if gender_match:
            g = gender_match.group(1).strip().upper()
            res["gender"] = "MALE" if g in ("M", "MALE") else ("FEMALE" if g in ("F", "FEMALE") else g)

        addr_parts = [p.group(1).strip() for p in (co_match, house_match, loc_match, vtc_match, dist_match, state_match, pc_match) if p]
        if addr_parts:
            res["address"] = ", ".join(addr_parts)

        return res

    # 2. JSON-like format
    import json
    try:
        data = json.loads(clean)
        if isinstance(data, dict):
            raw_uid = data.get("uid") or data.get("identity_number") or data.get("id")
            if raw_uid:
                uid_norm, _ = normalize_aadhaar(str(raw_uid))
                res["identity_number"] = uid_norm
                res["masked_identity_number"] = mask_aadhaar(uid_norm)
            res["name"]    = (data.get("name", "") or "").strip().upper() or None
            res["dob"]     = data.get("dob")
            res["gender"]  = data.get("gender")
            res["address"] = data.get("address")
            return res
    except Exception:
        pass

    # 3. Delimited format UID:xxx|NAME:yyy
    parts = clean.split("|")
    parsed_any = False
    for part in parts:
        if ":" in part:
            k, v = part.split(":", 1)
            k_upper = k.strip().upper()
            v_val   = v.strip()
            if k_upper in ("UID", "ID", "AADHAAR"):
                uid_norm, _ = normalize_aadhaar(v_val)
                res["identity_number"] = uid_norm
                res["masked_identity_number"] = mask_aadhaar(uid_norm)
                parsed_any = True
            elif k_upper == "NAME":
                res["name"] = v_val.upper()
                parsed_any = True
            elif k_upper == "DOB":
                res["dob"] = v_val
                parsed_any = True
            elif k_upper == "GENDER":
                res["gender"] = v_val.upper()
                parsed_any = True

    if not parsed_any:
        res["status"] = QRStatus.PAYLOAD_MALFORMED.value

    return res


def compare_ocr_and_qr(ocr_fields: Dict[str, Any], qr_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare OCR-extracted fields against QR-decoded Aadhaar payload fields.
    Produces evidence of field consistency: MATCHED, MISMATCH, or INCONCLUSIVE.
    """
    if qr_data.get("status") != QRStatus.PAYLOAD_DECODED.value:
        return {
            "qr_detected":        qr_data.get("status") != QRStatus.NOT_FOUND.value,
            "qr_decoded":         False,
            "overall_consistency": FieldComparisonResult.NOT_APPLICABLE.value,
            "field_results":      {},
        }

    field_results = {}
    mismatches = 0
    matches = 0

    # 1. Identity number comparison
    ocr_id = ocr_fields.get("identity_number") or ocr_fields.get("docNumber")
    qr_id  = qr_data.get("identity_number")
    if ocr_id and qr_id:
        norm_ocr, _ = normalize_aadhaar(ocr_id)
        norm_qr,  _ = normalize_aadhaar(qr_id)
        if norm_ocr and norm_qr:
            if norm_ocr == norm_qr:
                field_results["identity_number"] = FieldComparisonResult.MATCHED.value
                matches += 1
            else:
                field_results["identity_number"] = FieldComparisonResult.MISMATCH.value
                mismatches += 1

    # 2. Name comparison
    ocr_name = ocr_fields.get("name")
    qr_name  = qr_data.get("name")
    if ocr_name and qr_name:
        ocr_tokens = set(re.findall(r"\w+", ocr_name.upper()))
        qr_tokens  = set(re.findall(r"\w+", qr_name.upper()))
        if ocr_tokens and qr_tokens and (ocr_tokens == qr_tokens
                or ocr_tokens.issubset(qr_tokens) or qr_tokens.issubset(ocr_tokens)):
            field_results["name"] = FieldComparisonResult.MATCHED.value
            matches += 1
        else:
            field_results["name"] = FieldComparisonResult.MISMATCH.value
            mismatches += 1

    # Overall consistency
    if mismatches > 0:
        overall = FieldComparisonResult.MISMATCH.value
    elif matches > 0:
        overall = FieldComparisonResult.MATCHED.value
    else:
        overall = FieldComparisonResult.INCONCLUSIVE.value

    return {
        "qr_detected":            True,
        "qr_decoded":             True,
        "authentication_status":  "PAYLOAD_DECODED",  # Explicitly NOT 'AUTHENTICATED'
        "overall_consistency":    overall,
        "field_results":          field_results,
    }
