"""
backend/app/services/documents/border_permit/border_permit_qr_validator.py

QR / Barcode detection and payload validation for Border Permits.

CRITICAL RULES:
- Successful QR decoding does NOT mean the permit is authentic.
- Decoded payloads are labeled:
    Payload: PAYLOAD_DECODED
    Authentication: NOT VERIFIED
- QR payloads are treated as UNTRUSTED input.
- Payload data is compared against visual OCR fields to detect inconsistencies.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional
from xml.etree import ElementTree

from app.schemas.cross_document import RelationshipStatus
from app.services.documents.border_permit.border_permit_field_normalizer import (
    normalize_border_date,
    normalize_holder_name,
    normalize_permit_number,
)

logger = logging.getLogger(__name__)


def parse_border_permit_qr_payload(raw_payload: Optional[str]) -> Dict[str, Any]:
    """
    Parse a decoded QR/barcode string into a structured dictionary of attributes.
    Supports JSON payloads, XML tags, and delimited key=value strings.
    """
    if not raw_payload or not raw_payload.strip():
        return {
            "decoded": False,
            "status": "absent",
            "authentication": "NOT VERIFIED",
            "fields": {},
        }

    clean = raw_payload.strip()
    fields: Dict[str, Any] = {}

    # 1. Try JSON parsing
    if (clean.startswith("{") and clean.endswith("}")) or (clean.startswith("[") and clean.endswith("]")):
        try:
            data = json.loads(clean)
            if isinstance(data, dict):
                norm_p, _ = normalize_permit_number(data.get("permit_number") or data.get("permitNo") or data.get("docNumber"))
                fields["permit_number"] = norm_p
                fields["name"] = normalize_holder_name(data.get("name") or data.get("holder_name"))
                fields["dob"] = normalize_border_date(data.get("dob") or data.get("date_of_birth"))
                fields["passport_number"] = data.get("passport_number") or data.get("passportNo") or data.get("passportNumber")
                fields["valid_from"] = normalize_border_date(data.get("valid_from") or data.get("validFrom"))
                fields["valid_to"] = normalize_border_date(data.get("valid_to") or data.get("validTo") or data.get("expiry"))
                fields["permit_type"] = data.get("permit_type") or data.get("type")
                return {
                    "decoded": True,
                    "status": "PAYLOAD_DECODED",
                    "authentication": "NOT VERIFIED",
                    "format": "JSON",
                    "fields": fields,
                }
        except Exception:
            pass

    # 2. Try XML tag parsing
    if clean.startswith("<") and clean.endswith(">"):
        try:
            root = ElementTree.fromstring(clean)
            attribs = root.attrib
            norm_p, _ = normalize_permit_number(attribs.get("permit_number") or attribs.get("permitNo") or attribs.get("docNumber"))
            fields["permit_number"] = norm_p
            fields["name"] = normalize_holder_name(attribs.get("name") or attribs.get("holder_name"))
            fields["dob"] = normalize_border_date(attribs.get("dob") or attribs.get("date_of_birth"))
            fields["passport_number"] = attribs.get("passport_number") or attribs.get("passportNo")
            fields["valid_from"] = normalize_border_date(attribs.get("valid_from") or attribs.get("validFrom"))
            fields["valid_to"] = normalize_border_date(attribs.get("valid_to") or attribs.get("validTo") or attribs.get("expiry"))
            return {
                "decoded": True,
                "status": "PAYLOAD_DECODED",
                "authentication": "NOT VERIFIED",
                "format": "XML",
                "fields": fields,
            }
        except Exception:
            pass

    # 3. Try pipe or semicolon key-value pairs (e.g. "BP=BP2026000123|NAME=ALEX DUPONT|PPT=P1234567")
    kv_pattern = re.findall(r"([A-Z_]+)\s*[:=]\s*([^|;\n\r]+)", clean, re.IGNORECASE)
    if kv_pattern:
        kv_dict = {k.strip().upper(): v.strip() for k, v in kv_pattern}
        norm_p, _ = normalize_permit_number(kv_dict.get("BP") or kv_dict.get("PERMIT") or kv_dict.get("DOCNUMBER"))
        fields["permit_number"] = norm_p
        fields["name"] = normalize_holder_name(kv_dict.get("NAME") or kv_dict.get("HOLDER"))
        fields["dob"] = normalize_border_date(kv_dict.get("DOB"))
        fields["passport_number"] = kv_dict.get("PPT") or kv_dict.get("PASSPORT") or kv_dict.get("PASSPORTNUMBER")
        fields["valid_from"] = normalize_border_date(kv_dict.get("FROM") or kv_dict.get("VALIDFROM"))
        fields["valid_to"] = normalize_border_date(kv_dict.get("TO") or kv_dict.get("VALIDTO") or kv_dict.get("EXPIRY"))
        return {
            "decoded": True,
            "status": "PAYLOAD_DECODED",
            "authentication": "NOT VERIFIED",
            "format": "DELIMITED_KV",
            "fields": fields,
        }

    return {
        "decoded": False,
        "status": "MALFORMED_PAYLOAD",
        "authentication": "NOT VERIFIED",
        "fields": {},
    }


def compare_ocr_and_border_permit_qr(
    ocr_fields: Dict[str, Any],
    qr_payload: Optional[str],
) -> Dict[str, Any]:
    """
    Compare fields extracted via OCR with attributes extracted from the QR code payload.
    Produces field-level consistency status (MATCHED or MISMATCH).
    """
    parsed = parse_border_permit_qr_payload(qr_payload)
    if not parsed.get("decoded"):
        return {
            "status": "NOT_AVAILABLE",
            "qr_status": parsed.get("status"),
            "authentication": "NOT VERIFIED",
            "field_matches": {},
            "inconsistencies": [],
        }

    qr_fields = parsed["fields"]
    matches: Dict[str, str] = {}
    inconsistencies = []

    # Compare Permit Number
    ocr_num, _ = normalize_permit_number(ocr_fields.get("permitNumber") or ocr_fields.get("docNumber"))
    qr_num = qr_fields.get("permit_number")
    if ocr_num and qr_num:
        if ocr_num == qr_num:
            matches["permit_number"] = RelationshipStatus.MATCHED.value
        else:
            matches["permit_number"] = RelationshipStatus.MISMATCH.value
            inconsistencies.append(f"Permit number mismatch: OCR '{ocr_num}' vs QR '{qr_num}'")

    # Compare Holder Name
    ocr_name = normalize_holder_name(ocr_fields.get("name"))
    qr_name = qr_fields.get("name")
    if ocr_name and qr_name:
        ocr_tokens = set(ocr_name.split())
        qr_tokens = set(qr_name.split())
        if ocr_tokens == qr_tokens or ocr_name in qr_name or qr_name in ocr_name:
            matches["name"] = RelationshipStatus.MATCHED.value
        else:
            matches["name"] = RelationshipStatus.MISMATCH.value
            inconsistencies.append(f"Name mismatch: OCR '{ocr_name}' vs QR '{qr_name}'")

    # Compare Passport Number
    ocr_ppt = ocr_fields.get("passportNumber")
    qr_ppt = qr_fields.get("passport_number")
    if ocr_ppt and qr_ppt:
        if ocr_ppt.strip().upper() == qr_ppt.strip().upper():
            matches["passport_number"] = RelationshipStatus.MATCHED.value
        else:
            matches["passport_number"] = RelationshipStatus.MISMATCH.value
            inconsistencies.append(f"Passport reference mismatch: OCR '{ocr_ppt}' vs QR '{qr_ppt}'")

    overall_status = RelationshipStatus.MISMATCH.value if inconsistencies else RelationshipStatus.MATCHED.value

    return {
        "status": overall_status,
        "qr_status": parsed.get("status"),
        "authentication": parsed.get("authentication"),
        "field_matches": matches,
        "inconsistencies": inconsistencies,
    }
