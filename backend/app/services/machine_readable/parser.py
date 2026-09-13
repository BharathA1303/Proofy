"""
backend/app/services/machine_readable/parser.py

Generic Machine-Readable Payload Parser.
Transforms raw payload strings (JSON, Delimited Key-Value, Positional Delimited,
XML, Plain Text) into canonical document fields using schema-driven alias mapping.
"""
from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from app.services.machine_readable.schema import ParsedQRPayload, QRPayloadType

logger = logging.getLogger(__name__)

# Canonical field alias mapping dictionary
CANONICAL_FIELD_ALIASES: Dict[str, List[str]] = {
    "license_number": [
        "license_number", "lic_no", "lic_num", "dl_number", "dl_no",
        "dlno", "dlnum", "dl", "docnumber", "doc_no", "id_number",
        "dlnumber", "licensenumber", "lic_number", "license_no", "licenseno",
    ],
    "name": [
        "name", "holder_name", "applicant_name", "licensee_name",
        "full_name", "fname", "customer_name", "holder", "licensee"
    ],
    "dob": [
        "dob", "date_of_birth", "birth_date", "birthdate", "d_o_b",
        "birth", "dateofbirth"
    ],
    "valid_from": [
        "valid_from", "issue_date", "issued_date", "issuedate", "doi",
        "from_date", "validfrom", "issue", "issued"
    ],
    "valid_to": [
        "valid_to", "valid_till", "valid_upto", "expiry", "expiry_date",
        "validto", "validupto", "doe", "expirydate", "valid_until", "exp_date"
    ],
    "cov": [
        "cov", "covs", "vehicle_classes", "vehicle_class", "class_of_vehicle",
        "cov_details", "classes", "vehicleclasses"
    ],
    "blood_group": [
        "blood_group", "bg", "blood_grp", "bloodgroup"
    ],
    "address": [
        "address", "addr", "permanent_address", "perm_addr", "residence"
    ],
    "issuing_authority": [
        "issuing_authority", "authority", "rto", "rto_code", "issue_auth"
    ],
    "father_name": [
        "father_name", "swd_name", "care_of", "co", "relation_name",
        "father_or_husband_name", "sdw_name"
    ],
}

# Reverse mapping: lowercase alias -> canonical field name
_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical_key, aliases in CANONICAL_FIELD_ALIASES.items():
    _ALIAS_TO_CANONICAL[canonical_key.lower()] = canonical_key
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower()] = canonical_key


class GenericPayloadParser:
    """
    Document-agnostic parser for 2D barcode and QR code payloads.
    Auto-detects structure (JSON, Key-Value, Positional, XML, Text)
    and maps extracted attributes to canonical credential fields.
    """

    def parse(self, raw_text: str, payload_sha256: str) -> ParsedQRPayload:
        """
        Parse raw payload text into a structured ParsedQRPayload.

        Args:
            raw_text: Raw string extracted from QR code.
            payload_sha256: Tamper-evident SHA-256 hash of payload.

        Returns:
            ParsedQRPayload containing canonical and raw fields.
        """
        if not raw_text or not raw_text.strip():
            return ParsedQRPayload(
                payload_type=QRPayloadType.CORRUPTED,
                raw_text=raw_text or "",
                payload_sha256=payload_sha256,
                parse_errors=["Empty or whitespace-only payload"],
            )

        stripped = raw_text.strip()

        # 1. Try JSON
        if stripped.startswith("{") and stripped.endswith("}"):
            parsed_json = self._try_parse_json(stripped, payload_sha256)
            if parsed_json is not None:
                return parsed_json

        # 2. Try XML
        if stripped.startswith("<") and stripped.endswith(">"):
            parsed_xml = self._try_parse_xml(stripped, payload_sha256)
            if parsed_xml is not None:
                return parsed_xml

        # 3. Try Delimited Key-Value (pipe, semicolon, comma, or newline separated)
        if any(sep in stripped for sep in (":", "=")) and any(delim in stripped for delim in ("|", ";", "\n")):
            parsed_kv = self._try_parse_key_value(stripped, payload_sha256)
            if parsed_kv is not None and len(parsed_kv.raw_fields) > 1:
                return parsed_kv

        # 4. Try Positional Delimited (e.g. PIPE-separated values without explicit keys)
        if "|" in stripped or ";" in stripped:
            parsed_pos = self._try_parse_positional(stripped, payload_sha256)
            if parsed_pos is not None:
                return parsed_pos

        # 5. Check if it's single key-value
        if ":" in stripped or "=" in stripped:
            parsed_single_kv = self._try_parse_key_value(stripped, payload_sha256)
            if parsed_single_kv is not None and len(parsed_single_kv.raw_fields) > 0:
                return parsed_single_kv

        # 6. Fallback to Plain Text
        return ParsedQRPayload(
            payload_type=QRPayloadType.PLAIN_TEXT,
            raw_text=raw_text,
            payload_sha256=payload_sha256,
            canonical_fields={},
            raw_fields={"raw": stripped},
            metadata={"notes": "Unstructured plain text payload"},
        )

    def _try_parse_json(self, text: str, payload_sha256: str) -> Optional[ParsedQRPayload]:
        """Attempt to parse JSON structure."""
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                raw_fields: Dict[str, Any] = {}
                signature_data: Optional[Dict[str, Any]] = None

                for k, v in data.items():
                    k_lower = str(k).lower().strip()
                    if k_lower in ("signature", "sig", "digital_signature", "signed_hash"):
                        signature_data = {"key": str(k), "signature": v}
                    else:
                        raw_fields[str(k)] = v

                canonical = self._map_to_canonical(raw_fields)
                return ParsedQRPayload(
                    payload_type=QRPayloadType.JSON,
                    raw_text=text,
                    payload_sha256=payload_sha256,
                    canonical_fields=canonical,
                    raw_fields=raw_fields,
                    signature_data=signature_data,
                )
        except Exception as exc:
            logger.debug("Failed JSON parse: %s", exc)
        return None

    def _try_parse_xml(self, text: str, payload_sha256: str) -> Optional[ParsedQRPayload]:
        """Attempt safe XML parse (no external entities)."""
        try:
            # ET parses XML safely without entity resolution by default in modern Python
            root = ET.fromstring(text)
            raw_fields: Dict[str, Any] = dict(root.attrib)

            # Also check child tags
            for child in root:
                tag_name = child.tag.split("}")[-1]  # strip namespaces
                child_val = child.text.strip() if child.text else ""
                if child_val:
                    raw_fields[tag_name] = child_val

            canonical = self._map_to_canonical(raw_fields)
            return ParsedQRPayload(
                payload_type=QRPayloadType.XML,
                raw_text=text,
                payload_sha256=payload_sha256,
                canonical_fields=canonical,
                raw_fields=raw_fields,
                metadata={"root_tag": root.tag},
            )
        except Exception as exc:
            logger.debug("Failed XML parse: %s", exc)
        return None

    def _try_parse_key_value(self, text: str, payload_sha256: str) -> Optional[ParsedQRPayload]:
        """Parse key-value text separated by pipe, semicolon, newline, or comma."""
        # Find primary delimiter
        delimiter = None
        for cand_delim in ("|", ";", "\n"):
            if cand_delim in text:
                delimiter = cand_delim
                break
        if delimiter is None:
            tokens = [text]
        else:
            tokens = [t.strip() for t in text.split(delimiter) if t.strip()]

        raw_fields: Dict[str, Any] = {}
        signature_data: Optional[Dict[str, Any]] = None

        for token in tokens:
            if ":" in token:
                k, v = token.split(":", 1)
            elif "=" in token:
                k, v = token.split("=", 1)
            else:
                continue

            k_clean = k.strip()
            v_clean = v.strip()
            if not k_clean:
                continue

            if k_clean.lower() in ("sig", "signature", "digital_signature"):
                signature_data = {"key": k_clean, "signature": v_clean}
            else:
                raw_fields[k_clean] = v_clean

        if not raw_fields and not signature_data:
            return None

        canonical = self._map_to_canonical(raw_fields)
        return ParsedQRPayload(
            payload_type=QRPayloadType.DELIMITED_KEY_VALUE,
            raw_text=text,
            payload_sha256=payload_sha256,
            canonical_fields=canonical,
            raw_fields=raw_fields,
            signature_data=signature_data,
        )

    def _try_parse_positional(self, text: str, payload_sha256: str) -> Optional[ParsedQRPayload]:
        """
        Parse positional delimited payloads where values are stored in ordered slots.
        Common format in Indian Driving Licences:
          Token 0: DL Number
          Token 1: Holder Name
          Token 2: DOB
          Token 3: Issue Date or Valid To
          Token 4: Vehicle Classes / COV
        """
        delim = "|" if "|" in text else ";"
        tokens = [t.strip() for t in text.split(delim)]
        if len(tokens) < 3:
            return None

        # Check if first token resembles an Indian DL Number
        # Formats: SS-RRYYYYNNNNNNN, SSRRYYYYNNNNNNN, SS-RR-YYYY-NNNNNNN, etc.
        token0_clean = re.sub(r"[\s\-_/]", "", tokens[0].upper())
        is_dl_token0 = bool(re.match(r"^[A-Z]{2}\d{11,16}$", token0_clean)) or bool(
            re.match(r"^[A-Z]{2}[-\s]?\d{2}[-\s]?\d{4}[-\s]?\d{7}$", tokens[0].strip(), re.I)
        )

        canonical_fields: Dict[str, Any] = {}
        raw_fields: Dict[str, Any] = {}

        if is_dl_token0:
            canonical_fields["license_number"] = tokens[0].strip()
            raw_fields["pos_0"] = tokens[0].strip()

            if len(tokens) > 1 and tokens[1]:
                canonical_fields["name"] = tokens[1].strip()
                raw_fields["pos_1"] = tokens[1].strip()

            date_pattern = re.compile(r"^\d{2}[-/\.]\d{2}[-/\.]\d{4}$|^\d{4}[-/\.]\d{2}[-/\.]\d{2}$")

            # Look through remaining tokens for dates and COVs
            assigned_dates: List[str] = []
            for idx in range(2, len(tokens)):
                val = tokens[idx].strip()
                raw_fields[f"pos_{idx}"] = val
                if date_pattern.match(val):
                    assigned_dates.append(val)
                elif any(cov in val.upper() for cov in ("LMV", "MCWG", "MCWOG", "TRANS", "HGMV", "3W")):
                    canonical_fields["cov"] = val
                elif not canonical_fields.get("address") and len(val) > 10 and not date_pattern.match(val):
                    canonical_fields["address"] = val

            # Assign dates
            if len(assigned_dates) >= 1:
                canonical_fields["dob"] = assigned_dates[0]
            if len(assigned_dates) >= 2:
                canonical_fields["valid_from"] = assigned_dates[1]
            if len(assigned_dates) >= 3:
                canonical_fields["valid_to"] = assigned_dates[2]

            return ParsedQRPayload(
                payload_type=QRPayloadType.POSITIONAL_DELIMITED,
                raw_text=text,
                payload_sha256=payload_sha256,
                canonical_fields=canonical_fields,
                raw_fields=raw_fields,
            )

        return None

    def _map_to_canonical(self, raw_fields: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw dictionary keys into canonical field names."""
        canonical: Dict[str, Any] = {}
        for k, v in raw_fields.items():
            k_clean = str(k).lower().strip().replace("-", "_").replace(" ", "_")
            canon_key = _ALIAS_TO_CANONICAL.get(k_clean)
            if canon_key and canon_key not in canonical:
                canonical[canon_key] = v
            elif canon_key and canon_key in canonical:
                # If already present, don't overwrite if non-empty
                if not canonical[canon_key] and v:
                    canonical[canon_key] = v
        return canonical
