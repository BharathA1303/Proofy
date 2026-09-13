"""
backend/app/services/machine_readable/verifier.py

Generic Machine-Readable Verifier and Cross-Validation Engine (M2).
Executes:
  1. Strict OCR vs QR field-by-field cross-validation with safe canonical normalizations.
  2. Cryptographic signature verification using real public-key cryptography (RSA/ECDSA/Ed25519).
  3. Absolute independence of sources: preserves OCR and QR evidence without overwriting.
"""
from __future__ import annotations

import base64
from datetime import datetime
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from app.services.machine_readable.schema import (
    CryptoVerificationResult,
    CryptoVerificationStatus,
    FieldComparisonStatus,
    FieldCrossCheckResult,
    OverallMatchStatus,
    ParsedQRPayload,
)

logger = logging.getLogger(__name__)


def _parse_flexible_date(date_str: Any) -> Optional[datetime.date]:
    """Parse flexible date strings into standard datetime.date."""
    if not date_str or not isinstance(date_str, (str, int, float)):
        return None
    s = str(date_str).strip()
    formats = [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
        "%Y/%m/%d", "%Y.%m.%d", "%d%m%Y", "%Y%m%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_dl_number(val: Any) -> str:
    """Normalize driving license number by stripping spaces, hyphens, and slashes."""
    if not val:
        return ""
    return re.sub(r"[\s\-_/]", "", str(val).upper())


def _normalize_name(val: Any) -> str:
    """Normalize person name by collapsing whitespace and uppercasing."""
    if not val:
        return ""
    return " ".join(str(val).upper().split())


def _normalize_cov(val: Any) -> Set[str]:
    """Normalize Class of Vehicle values into a clean set of vehicle class codes."""
    if not val:
        return set()
    raw_tokens: List[str] = []
    if isinstance(val, (list, tuple, set)):
        for item in val:
            raw_tokens.extend(re.split(r"[,;/]+", str(item)))
    else:
        raw_tokens = re.split(r"[,;/]+", str(val))

    cleaned = set()
    for token in raw_tokens:
        tok_clean = token.strip().upper()
        if tok_clean:
            cleaned.add(tok_clean)
    return cleaned


class MachineReadableVerifier:
    """
    Independent cross-validation and cryptographic verification engine.
    Ensures OCR and QR data remain strictly independent evidence sources.
    """

    def cross_check(
        self,
        ocr_data: Dict[str, Any],
        parsed_qr: Optional[ParsedQRPayload],
        cross_check_fields: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, FieldCrossCheckResult], OverallMatchStatus, List[str]]:
        """
        Cross-check parsed QR fields against extracted OCR document fields.

        Args:
            ocr_data: Dictionary of normalized or raw fields from OCR / semantic pipeline.
            parsed_qr: Parsed QR payload containing canonical_fields.
            cross_check_fields: List of fields to compare (if None, default fields used).

        Returns:
            Tuple of:
              - Dict of field_name -> FieldCrossCheckResult
              - aggregate OverallMatchStatus
              - List of warnings
        """
        results: Dict[str, FieldCrossCheckResult] = {}
        warnings: List[str] = []

        if parsed_qr is None or not parsed_qr.canonical_fields:
            return results, OverallMatchStatus.NO_QR_DATA, ["No parsed QR payload available for cross-validation"]

        fields_to_check = cross_check_fields or [
            "license_number",
            "name",
            "dob",
            "valid_from",
            "valid_to",
            "cov",
        ]

        qr_fields = parsed_qr.canonical_fields

        for field_name in fields_to_check:
            qr_val = qr_fields.get(field_name)
            ocr_val = self._extract_ocr_field(ocr_data, field_name)

            res = self._compare_single_field(field_name, qr_val, ocr_val)
            results[field_name] = res

        # Determine overall match status
        any_mismatch = any(r.status == FieldComparisonStatus.QR_FIELD_MISMATCH for r in results.values())
        any_missing = any(r.status == FieldComparisonStatus.QR_FIELD_MISSING for r in results.values())
        any_ambiguous = any(r.status == FieldComparisonStatus.QR_FIELD_AMBIGUOUS for r in results.values())
        any_match = any(r.status == FieldComparisonStatus.QR_FIELD_MATCH for r in results.values())

        if any_mismatch:
            overall_status = OverallMatchStatus.MISMATCH_DETECTED
            mismatched_fields = [k for k, v in results.items() if v.status == FieldComparisonStatus.QR_FIELD_MISMATCH]
            warnings.append(f"Discrepancy detected between QR and OCR on fields: {', '.join(mismatched_fields)}")
        elif any_missing or any_ambiguous:
            overall_status = OverallMatchStatus.PARTIAL_MATCH
        elif any_match:
            # All tested fields that were present matched cleanly (with remaining fields unavailable in both)
            overall_status = OverallMatchStatus.ALL_MATCHED
        else:
            overall_status = OverallMatchStatus.NO_QR_DATA

        return results, overall_status, warnings

    def _extract_ocr_field(self, ocr_data: Dict[str, Any], field_name: str) -> Optional[Any]:
        """Extract field value from OCR data handling common alias keys and nested dicts."""
        if not ocr_data:
            return None

        # Direct key
        if field_name in ocr_data:
            val = ocr_data[field_name]
            # Handle semantic field dicts that have a 'value' key
            if isinstance(val, dict) and "value" in val:
                return val["value"]
            return val

        # Common aliases in DL
        alias_map = {
            "license_number": ["docNumber", "dl_number", "dl_no", "license_no", "dlNo"],
            "name": ["holder_name", "fullName", "full_name"],
            "dob": ["date_of_birth", "birthDate"],
            "valid_from": ["issuedDate", "issue_date", "validFrom"],
            "valid_to": ["expiry", "expiry_date", "validTo"],
            "cov": ["vehicle_classes", "vehicleClasses", "classes"],
        }
        for alias in alias_map.get(field_name, []):
            if alias in ocr_data:
                val = ocr_data[alias]
                if isinstance(val, dict) and "value" in val:
                    return val["value"]
                return val

        return None

    def _compare_single_field(
        self,
        field_name: str,
        qr_val: Optional[Any],
        ocr_val: Optional[Any],
    ) -> FieldCrossCheckResult:
        """Execute strict canonical comparison for a single field."""
        # Check availability
        if qr_val is None and ocr_val is None:
            return FieldCrossCheckResult(
                field_name=field_name,
                status=FieldComparisonStatus.QR_FIELD_UNAVAILABLE,
                qr_value=None,
                ocr_value=None,
                details=f"Field '{field_name}' not available in either QR or OCR",
                is_match=False,
            )

        if qr_val is not None and ocr_val is None:
            return FieldCrossCheckResult(
                field_name=field_name,
                status=FieldComparisonStatus.QR_FIELD_MISSING,
                qr_value=qr_val,
                ocr_value=None,
                details=f"Field '{field_name}' present in QR ('{qr_val}') but absent in OCR",
                is_match=False,
            )

        if qr_val is None and ocr_val is not None:
            return FieldCrossCheckResult(
                field_name=field_name,
                status=FieldComparisonStatus.QR_FIELD_MISSING,
                qr_value=None,
                ocr_value=ocr_val,
                details=f"Field '{field_name}' present in OCR ('{ocr_val}') but absent in QR",
                is_match=False,
            )

        # Field-specific normalization and comparison
        if field_name == "license_number":
            qr_norm = _normalize_dl_number(qr_val)
            ocr_norm = _normalize_dl_number(ocr_val)
            if qr_norm and qr_norm == ocr_norm:
                return FieldCrossCheckResult(
                    field_name=field_name,
                    status=FieldComparisonStatus.QR_FIELD_MATCH,
                    qr_value=qr_val,
                    ocr_value=ocr_val,
                    details=f"Identifier match after canonical formatting: '{qr_norm}'",
                    is_match=True,
                )
            return FieldCrossCheckResult(
                field_name=field_name,
                status=FieldComparisonStatus.QR_FIELD_MISMATCH,
                qr_value=qr_val,
                ocr_value=ocr_val,
                details=f"Identifier mismatch: QR has '{qr_norm}', OCR has '{ocr_norm}'",
                is_match=False,
            )

        if field_name in ("dob", "valid_from", "valid_to"):
            qr_date = _parse_flexible_date(qr_val)
            ocr_date = _parse_flexible_date(ocr_val)

            if qr_date and ocr_date:
                if qr_date == ocr_date:
                    return FieldCrossCheckResult(
                        field_name=field_name,
                        status=FieldComparisonStatus.QR_FIELD_MATCH,
                        qr_value=qr_val,
                        ocr_value=ocr_val,
                        details=f"Date match after normalization: {qr_date.isoformat()}",
                        is_match=True,
                    )
                return FieldCrossCheckResult(
                    field_name=field_name,
                    status=FieldComparisonStatus.QR_FIELD_MISMATCH,
                    qr_value=qr_val,
                    ocr_value=ocr_val,
                    details=f"Date mismatch: QR has {qr_date.isoformat()}, OCR has {ocr_date.isoformat()}",
                    is_match=False,
                )

            # Fallback to string comparison if parsing failed
            if str(qr_val).strip() == str(ocr_val).strip():
                return FieldCrossCheckResult(
                    field_name=field_name,
                    status=FieldComparisonStatus.QR_FIELD_MATCH,
                    qr_value=qr_val,
                    ocr_value=ocr_val,
                    details="Date string exact match (unparsed)",
                    is_match=True,
                )
            return FieldCrossCheckResult(
                field_name=field_name,
                status=FieldComparisonStatus.QR_FIELD_MISMATCH,
                qr_value=qr_val,
                ocr_value=ocr_val,
                details=f"Date mismatch: QR has '{qr_val}', OCR has '{ocr_val}'",
                is_match=False,
            )

        if field_name == "name":
            qr_name_norm = _normalize_name(qr_val)
            ocr_name_norm = _normalize_name(ocr_val)
            if qr_name_norm == ocr_name_norm:
                return FieldCrossCheckResult(
                    field_name=field_name,
                    status=FieldComparisonStatus.QR_FIELD_MATCH,
                    qr_value=qr_val,
                    ocr_value=ocr_val,
                    details="Name match after whitespace and case normalization",
                    is_match=True,
                )
            return FieldCrossCheckResult(
                field_name=field_name,
                status=FieldComparisonStatus.QR_FIELD_MISMATCH,
                qr_value=qr_val,
                ocr_value=ocr_val,
                details=f"Name mismatch: QR has '{qr_val}', OCR has '{ocr_val}'",
                is_match=False,
            )

        if field_name == "cov":
            qr_cov = _normalize_cov(qr_val)
            ocr_cov = _normalize_cov(ocr_val)
            if qr_cov and qr_cov == ocr_cov:
                return FieldCrossCheckResult(
                    field_name=field_name,
                    status=FieldComparisonStatus.QR_FIELD_MATCH,
                    qr_value=qr_val,
                    ocr_value=ocr_val,
                    details=f"Vehicle classes match: {sorted(list(qr_cov))}",
                    is_match=True,
                )
            return FieldCrossCheckResult(
                field_name=field_name,
                status=FieldComparisonStatus.QR_FIELD_MISMATCH,
                qr_value=qr_val,
                ocr_value=ocr_val,
                details=f"Vehicle classes mismatch: QR has {sorted(list(qr_cov))}, OCR has {sorted(list(ocr_cov))}",
                is_match=False,
            )

        # Generic string comparison
        qr_str = str(qr_val).strip().lower()
        ocr_str = str(ocr_val).strip().lower()
        if qr_str == ocr_str:
            return FieldCrossCheckResult(
                field_name=field_name,
                status=FieldComparisonStatus.QR_FIELD_MATCH,
                qr_value=qr_val,
                ocr_value=ocr_val,
                details="Exact match after string normalization",
                is_match=True,
            )
        return FieldCrossCheckResult(
            field_name=field_name,
            status=FieldComparisonStatus.QR_FIELD_MISMATCH,
            qr_value=qr_val,
            ocr_value=ocr_val,
            details=f"Value mismatch: QR has '{qr_val}', OCR has '{ocr_val}'",
            is_match=False,
        )

    def verify_cryptographic_signature(
        self,
        parsed_qr: Optional[ParsedQRPayload],
        crypto_config: Optional[Dict[str, Any]] = None,
        public_key_pem: Optional[str] = None,
    ) -> CryptoVerificationResult:
        """
        Verify cryptographic digital signature of the QR payload.
        NEVER fakes verification. Requires genuine mathematical cryptographic check.

        Args:
            parsed_qr: Parsed QR payload containing raw_text and signature_data.
            crypto_config: Document profile cryptographic configuration.
            public_key_pem: Optional PEM encoded public key for verification.

        Returns:
            CryptoVerificationResult
        """
        config = crypto_config or {}
        is_supported = config.get("supported", False)
        reason = config.get("reason", "No public key infrastructure configured")

        if not is_supported and not public_key_pem:
            # Document type has no offline verification PKI
            status_str = config.get("status", "CRYPTO_VERIFICATION_UNAVAILABLE")
            try:
                status_enum = CryptoVerificationStatus(status_str)
            except ValueError:
                status_enum = CryptoVerificationStatus.CRYPTO_VERIFICATION_UNAVAILABLE

            return CryptoVerificationResult(
                status=status_enum,
                details=reason,
                signature_present=parsed_qr.signature_data is not None if parsed_qr else False,
            )

        if parsed_qr is None:
            return CryptoVerificationResult(
                status=CryptoVerificationStatus.CRYPTO_VERIFICATION_NOT_APPLICABLE,
                details="No QR payload present to verify",
            )

        sig_data = parsed_qr.signature_data
        if not sig_data or not sig_data.get("signature"):
            return CryptoVerificationResult(
                status=CryptoVerificationStatus.CRYPTO_VERIFICATION_NOT_APPLICABLE,
                details="Payload does not contain digital signature",
                signature_present=False,
            )

        if not public_key_pem and "public_key" not in config:
            return CryptoVerificationResult(
                status=CryptoVerificationStatus.CRYPTO_VERIFICATION_UNAVAILABLE,
                details="Signature present in payload but verification public key is not available",
                signature_present=True,
            )

        # Genuine cryptographic verification execution
        pem_key = public_key_pem or config.get("public_key")
        raw_signature = sig_data.get("signature")

        try:
            # Decode signature (hex or base64)
            if isinstance(raw_signature, str):
                try:
                    sig_bytes = bytes.fromhex(raw_signature)
                except ValueError:
                    sig_bytes = base64.b64decode(raw_signature)
            elif isinstance(raw_signature, bytes):
                sig_bytes = raw_signature
            else:
                return CryptoVerificationResult(
                    status=CryptoVerificationStatus.CRYPTO_VERIFICATION_FAILED,
                    details=f"Invalid signature encoding type: {type(raw_signature)}",
                    signature_present=True,
                )

            # Load public key
            if isinstance(pem_key, str):
                key_bytes = pem_key.encode("utf-8")
            else:
                key_bytes = pem_key

            public_key = load_pem_public_key(key_bytes)
            data_bytes = parsed_qr.raw_text.encode("utf-8")

            # RSA verification
            if isinstance(public_key, rsa.RSAPublicKey):
                try:
                    public_key.verify(sig_bytes, data_bytes, padding.PKCS1v15(), hashes.SHA256())
                    return CryptoVerificationResult(
                        status=CryptoVerificationStatus.CRYPTO_VERIFICATION_PASSED,
                        algorithm="RSA-PKCS1v15-SHA256",
                        details="Genuine RSA digital signature mathematically verified",
                        signature_present=True,
                        verified_at=datetime.utcnow().isoformat(),
                    )
                except InvalidSignature:
                    return CryptoVerificationResult(
                        status=CryptoVerificationStatus.CRYPTO_VERIFICATION_FAILED,
                        algorithm="RSA-PKCS1v15-SHA256",
                        details="Cryptographic signature verification failed: signature does not match data and key",
                        signature_present=True,
                    )

            # ECDSA verification
            elif isinstance(public_key, ec.EllipticCurvePublicKey):
                try:
                    public_key.verify(sig_bytes, data_bytes, ec.ECDSA(hashes.SHA256()))
                    return CryptoVerificationResult(
                        status=CryptoVerificationStatus.CRYPTO_VERIFICATION_PASSED,
                        algorithm="ECDSA-SHA256",
                        details="Genuine ECDSA digital signature mathematically verified",
                        signature_present=True,
                        verified_at=datetime.utcnow().isoformat(),
                    )
                except InvalidSignature:
                    return CryptoVerificationResult(
                        status=CryptoVerificationStatus.CRYPTO_VERIFICATION_FAILED,
                        algorithm="ECDSA-SHA256",
                        details="Cryptographic signature verification failed: signature does not match data and key",
                        signature_present=True,
                    )

            # Ed25519 verification
            elif isinstance(public_key, ed25519.Ed25519PublicKey):
                try:
                    public_key.verify(sig_bytes, data_bytes)
                    return CryptoVerificationResult(
                        status=CryptoVerificationStatus.CRYPTO_VERIFICATION_PASSED,
                        algorithm="Ed25519",
                        details="Genuine Ed25519 digital signature mathematically verified",
                        signature_present=True,
                        verified_at=datetime.utcnow().isoformat(),
                    )
                except InvalidSignature:
                    return CryptoVerificationResult(
                        status=CryptoVerificationStatus.CRYPTO_VERIFICATION_FAILED,
                        algorithm="Ed25519",
                        details="Cryptographic signature verification failed: signature does not match data and key",
                        signature_present=True,
                    )

            else:
                return CryptoVerificationResult(
                    status=CryptoVerificationStatus.CRYPTO_VERIFICATION_UNAVAILABLE,
                    details=f"Unsupported public key type: {type(public_key)}",
                    signature_present=True,
                )

        except Exception as exc:
            logger.warning("Cryptographic verification raised exception: %s", exc)
            return CryptoVerificationResult(
                status=CryptoVerificationStatus.CRYPTO_VERIFICATION_FAILED,
                details=f"Cryptographic verification execution error: {exc}",
                signature_present=True,
            )
