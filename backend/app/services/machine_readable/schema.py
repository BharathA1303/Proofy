"""
backend/app/services/machine_readable/schema.py

Generic Machine-Readable and 2D Barcode Data Models and Enums (M1/M2).
Provides document-agnostic structures for:
  - QR / Barcode detection states, bounding boxes, and candidate telemetry
  - Raw and parsed payload representations (JSON, delimited, positional, XML, binary)
  - Cryptographic verification statuses and signatures
  - OCR vs QR cross-validation evidence records
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.services.document_intelligence.schema import NormalizedBBox


class QRDetectionStatus(str, Enum):
    """Detection state of a machine-readable barcode / QR code."""
    DECODED = "DECODED"
    DETECTED_NOT_DECODABLE = "DETECTED_NOT_DECODABLE"
    NOT_DETECTED = "NOT_DETECTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class QRPayloadType(str, Enum):
    """Format and serialization family of the decoded payload."""
    JSON = "JSON"
    DELIMITED_KEY_VALUE = "DELIMITED_KEY_VALUE"
    POSITIONAL_DELIMITED = "POSITIONAL_DELIMITED"
    XML = "XML"
    PLAIN_TEXT = "PLAIN_TEXT"
    BINARY = "BINARY"
    CORRUPTED = "CORRUPTED"
    UNKNOWN = "UNKNOWN"


class FieldComparisonStatus(str, Enum):
    """Structured evidence outcomes for OCR <-> QR cross-validation."""
    QR_FIELD_MATCH = "QR_FIELD_MATCH"
    QR_FIELD_MISMATCH = "QR_FIELD_MISMATCH"
    QR_FIELD_MISSING = "QR_FIELD_MISSING"
    QR_FIELD_AMBIGUOUS = "QR_FIELD_AMBIGUOUS"
    QR_FIELD_UNAVAILABLE = "QR_FIELD_UNAVAILABLE"


class CryptoVerificationStatus(str, Enum):
    """Cryptographic signature verification outcome."""
    CRYPTO_VERIFICATION_NOT_CONFIGURED = "CRYPTO_VERIFICATION_NOT_CONFIGURED"
    CRYPTO_VERIFICATION_UNAVAILABLE = "CRYPTO_VERIFICATION_UNAVAILABLE"
    CRYPTO_VERIFICATION_NOT_APPLICABLE = "CRYPTO_VERIFICATION_NOT_APPLICABLE"
    CRYPTO_VERIFICATION_PASSED = "CRYPTO_VERIFICATION_PASSED"
    CRYPTO_VERIFICATION_FAILED = "CRYPTO_VERIFICATION_FAILED"


class OverallMatchStatus(str, Enum):
    """Aggregate cross-validation summary across all compared fields."""
    ALL_MATCHED = "ALL_MATCHED"
    MISMATCH_DETECTED = "MISMATCH_DETECTED"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    NO_QR_DATA = "NO_QR_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class QRCandidate:
    """Represents a localized QR code instance in the document."""
    candidate_id: str
    status: QRDetectionStatus
    bbox: NormalizedBBox
    pixel_bbox: List[List[int]]
    raw_payload: Optional[str] = None
    payload_bytes: Optional[bytes] = None
    payload_sha256: Optional[str] = None
    side: Optional[str] = None
    confidence: float = 1.0
    is_primary: bool = False
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        if self.payload_sha256 is None:
            if self.payload_bytes is not None:
                self.payload_sha256 = hashlib.sha256(self.payload_bytes).hexdigest()
            elif self.raw_payload is not None:
                self.payload_sha256 = hashlib.sha256(self.raw_payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "bbox": {
                "x": self.bbox.x,
                "y": self.bbox.y,
                "width": self.bbox.width,
                "height": self.bbox.height,
            },
            "pixel_bbox": self.pixel_bbox,
            "raw_payload": self.raw_payload,
            "payload_sha256": self.payload_sha256,
            "side": self.side,
            "confidence": self.confidence,
            "is_primary": self.is_primary,
            "error_message": self.error_message,
        }


@dataclass
class ParsedQRPayload:
    """Parsed and structured fields extracted from a QR payload."""
    payload_type: QRPayloadType
    raw_text: str
    payload_sha256: str
    canonical_fields: Dict[str, Any] = field(default_factory=dict)
    raw_fields: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    signature_data: Optional[Dict[str, Any]] = None
    parse_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_type": self.payload_type.value if isinstance(self.payload_type, Enum) else str(self.payload_type),
            "raw_text": self.raw_text,
            "payload_sha256": self.payload_sha256,
            "canonical_fields": self.canonical_fields,
            "raw_fields": self.raw_fields,
            "metadata": self.metadata,
            "signature_data": self.signature_data,
            "parse_errors": self.parse_errors,
        }


@dataclass
class FieldCrossCheckResult:
    """Cross-validation comparison result for a single field between OCR and QR."""
    field_name: str
    status: FieldComparisonStatus
    qr_value: Optional[Any] = None
    ocr_value: Optional[Any] = None
    details: str = ""
    confidence: float = 1.0
    is_match: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "qr_value": self.qr_value,
            "ocr_value": self.ocr_value,
            "details": self.details,
            "confidence": self.confidence,
            "is_match": self.is_match,
        }


@dataclass
class CryptoVerificationResult:
    """Cryptographic signature verification details."""
    status: CryptoVerificationStatus
    algorithm: Optional[str] = None
    details: str = ""
    key_id: Optional[str] = None
    signature_present: bool = False
    verified_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "algorithm": self.algorithm,
            "details": self.details,
            "key_id": self.key_id,
            "signature_present": self.signature_present,
            "verified_at": self.verified_at,
        }


@dataclass
class MachineReadableResult:
    """Overall intelligence result from machine-readable processing."""
    document_type: str
    applicable: bool
    detection_status: QRDetectionStatus
    primary_qr: Optional[QRCandidate] = None
    all_candidates: List[QRCandidate] = field(default_factory=list)
    parsed_payload: Optional[ParsedQRPayload] = None
    field_cross_checks: Dict[str, FieldCrossCheckResult] = field(default_factory=dict)
    crypto_verification: Optional[CryptoVerificationResult] = None
    overall_match_status: OverallMatchStatus = OverallMatchStatus.NO_QR_DATA
    warnings: List[str] = field(default_factory=list)
    telemetry: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_type": self.document_type,
            "applicable": self.applicable,
            "detection_status": self.detection_status.value if isinstance(self.detection_status, Enum) else str(self.detection_status),
            "primary_qr": self.primary_qr.to_dict() if self.primary_qr else None,
            "all_candidates": [c.to_dict() for c in self.all_candidates],
            "parsed_payload": self.parsed_payload.to_dict() if self.parsed_payload else None,
            "field_cross_checks": {k: v.to_dict() for k, v in self.field_cross_checks.items()},
            "crypto_verification": self.crypto_verification.to_dict() if self.crypto_verification else None,
            "overall_match_status": self.overall_match_status.value if isinstance(self.overall_match_status, Enum) else str(self.overall_match_status),
            "warnings": self.warnings,
            "telemetry": self.telemetry,
        }
