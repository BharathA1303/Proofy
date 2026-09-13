"""
backend/app/services/machine_readable/service.py

Unified Machine-Readable Intelligence Service (M1/M2).
Coordinates detection, decoding, parsing, cryptographic verification,
and independent OCR vs QR cross-validation for all credential types.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Union

from app.services.documents.profiles.document_profile_registry import (
    document_profile_registry,
)
from app.services.machine_readable.decoder import QRDecoder
from app.services.machine_readable.detector import QRDetector
from app.services.machine_readable.parser import GenericPayloadParser
from app.services.machine_readable.schema import (
    CryptoVerificationResult,
    CryptoVerificationStatus,
    FieldCrossCheckResult,
    MachineReadableResult,
    OverallMatchStatus,
    ParsedQRPayload,
    QRCandidate,
    QRDetectionStatus,
)
from app.services.machine_readable.verifier import MachineReadableVerifier

logger = logging.getLogger(__name__)


class MachineReadableService:
    """
    Production-grade, document-agnostic service for 2D barcode and QR intelligence.
    Orchestrates:
      - Computer vision QR localization and polygon geometry extraction
      - Candidate scoring and primary selection
      - Multi-format payload parsing (JSON, Delimited, Positional, XML)
      - Independent OCR vs QR cross-check without overwriting either source
      - Real cryptographic digital signature verification
    """

    def __init__(
        self,
        detector: Optional[QRDetector] = None,
        decoder: Optional[QRDecoder] = None,
        parser: Optional[GenericPayloadParser] = None,
        verifier: Optional[MachineReadableVerifier] = None,
    ) -> None:
        self.detector = detector or QRDetector()
        self.decoder = decoder or QRDecoder()
        self.parser = parser or GenericPayloadParser()
        self.verifier = verifier or MachineReadableVerifier()

    def process(
        self,
        image_input: Optional[Any] = None,
        document_type: str = "driving_license",
        ocr_data: Optional[Dict[str, Any]] = None,
        side: Optional[str] = None,
        raw_payload_text: Optional[str] = None,
        public_key_pem: Optional[str] = None,
        profile_override: Optional[Dict[str, Any]] = None,
    ) -> MachineReadableResult:
        """
        Execute end-to-end machine-readable intelligence on a document credential.

        Args:
            image_input: Image array, PIL Image, bytes, or file path.
            document_type: Document profile identifier (default: 'driving_license').
            ocr_data: Dictionary of extracted OCR or normalized fields.
            side: Physical face of the document ('front', 'back', 'unknown').
            raw_payload_text: Explicit decoded text (for testing or direct payload inputs).
            public_key_pem: Public key PEM string for digital signature verification.
            profile_override: Optional profile config override for tests.

        Returns:
            MachineReadableResult
        """
        start_time = time.perf_counter()
        warnings: List[str] = []
        telemetry: Dict[str, Any] = {
            "document_type": document_type,
            "side": side,
        }

        # 1. Resolve Document Profile Configuration
        mr_config = self._get_profile_config(document_type, profile_override)
        applicable = mr_config.get("applicable", True)

        if not applicable:
            telemetry["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
            return MachineReadableResult(
                document_type=document_type,
                applicable=False,
                detection_status=QRDetectionStatus.NOT_APPLICABLE,
                primary_qr=None,
                all_candidates=[],
                parsed_payload=None,
                field_cross_checks={},
                crypto_verification=CryptoVerificationResult(
                    status=CryptoVerificationStatus.CRYPTO_VERIFICATION_NOT_APPLICABLE,
                    details="Machine-readable verification not applicable for this document type",
                ),
                overall_match_status=OverallMatchStatus.NOT_APPLICABLE,
                warnings=["Machine-readable QR processing is marked not applicable in document profile"],
                telemetry=telemetry,
            )

        expected_region = mr_config.get("expected_region")
        expected_side = mr_config.get("expected_side")
        cross_check_fields = mr_config.get("cross_check_fields")
        crypto_config = mr_config.get("crypto_verification", {})

        # 2. Localize and Decode QR
        candidates: List[QRCandidate] = []
        primary_qr: Optional[QRCandidate] = None
        detection_status = QRDetectionStatus.NOT_DETECTED

        if raw_payload_text is not None:
            # Direct payload provided (e.g. from upstream scanner or test fixture)
            clean_text, sha256_hash, _, dec_err = self.decoder.decode_raw(raw_text=raw_payload_text)
            from app.services.document_intelligence.schema import NormalizedBBox
            dummy_bbox = expected_region or NormalizedBBox(0.60, 0.30, 0.35, 0.50)
            primary_qr = QRCandidate(
                candidate_id="qr_direct",
                status=QRDetectionStatus.DECODED if clean_text else QRDetectionStatus.DETECTED_NOT_DECODABLE,
                bbox=dummy_bbox,
                pixel_bbox=[[0, 0], [100, 0], [100, 100], [0, 100]],
                raw_payload=clean_text,
                side=side,
                confidence=1.0,
                is_primary=True,
                error_message=dec_err,
            )
            candidates = [primary_qr]
            detection_status = primary_qr.status
        elif image_input is not None:
            status, cands, prim, det_warnings = self.detector.detect_and_decode(
                image_input=image_input,
                expected_region=expected_region,
                side=side,
                expected_side=expected_side,
            )
            detection_status = status
            candidates = cands
            primary_qr = prim
            warnings.extend(det_warnings)
        else:
            detection_status = QRDetectionStatus.NOT_DETECTED
            warnings.append("Neither image_input nor raw_payload_text provided")

        telemetry["detection_status"] = detection_status.value
        telemetry["candidate_count"] = len(candidates)

        # 3. Parse Payload
        parsed_payload: Optional[ParsedQRPayload] = None
        if primary_qr and primary_qr.status == QRDetectionStatus.DECODED and primary_qr.raw_payload:
            parsed_payload = self.parser.parse(
                raw_text=primary_qr.raw_payload,
                payload_sha256=primary_qr.payload_sha256 or "",
            )
            telemetry["payload_type"] = parsed_payload.payload_type.value
            telemetry["canonical_field_count"] = len(parsed_payload.canonical_fields)

        # 4. OCR vs QR Cross-Check
        field_cross_checks: Dict[str, FieldCrossCheckResult] = {}
        overall_match_status = OverallMatchStatus.NO_QR_DATA

        if parsed_payload and ocr_data is not None:
            checks, m_status, cc_warnings = self.verifier.cross_check(
                ocr_data=ocr_data,
                parsed_qr=parsed_payload,
                cross_check_fields=cross_check_fields,
            )
            field_cross_checks = checks
            overall_match_status = m_status
            warnings.extend(cc_warnings)
        elif parsed_payload and ocr_data is None:
            overall_match_status = OverallMatchStatus.NO_QR_DATA
            warnings.append("OCR data not provided for cross-validation")
        elif detection_status == QRDetectionStatus.DETECTED_NOT_DECODABLE:
            overall_match_status = OverallMatchStatus.NO_QR_DATA
            warnings.append("QR detected but not decodable; cross-check skipped")
        else:
            overall_match_status = OverallMatchStatus.NO_QR_DATA

        # 5. Cryptographic Verification
        crypto_res = self.verifier.verify_cryptographic_signature(
            parsed_qr=parsed_payload,
            crypto_config=crypto_config,
            public_key_pem=public_key_pem,
        )

        telemetry["crypto_status"] = crypto_res.status.value
        telemetry["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 2)

        return MachineReadableResult(
            document_type=document_type,
            applicable=True,
            detection_status=detection_status,
            primary_qr=primary_qr,
            all_candidates=candidates,
            parsed_payload=parsed_payload,
            field_cross_checks=field_cross_checks,
            crypto_verification=crypto_res,
            overall_match_status=overall_match_status,
            warnings=warnings,
            telemetry=telemetry,
        )

    def _get_profile_config(self, document_type: str, profile_override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Fetch profile machine_readable_config or apply overrides."""
        if profile_override:
            return profile_override

        try:
            profile = document_profile_registry.resolve(document_type)
            if profile and hasattr(profile, "machine_readable_config"):
                return profile.machine_readable_config or {}
        except Exception:
            pass
        return {}
