"""
backend/app/services/machine_readable/__init__.py

Generic Machine-Readable and 2D Barcode Intelligence Layer (M1/M2).
"""
from app.services.machine_readable.decoder import QRDecoder
from app.services.machine_readable.detector import QRDetector
from app.services.machine_readable.parser import GenericPayloadParser
from app.services.machine_readable.schema import (
    CryptoVerificationResult,
    CryptoVerificationStatus,
    FieldComparisonStatus,
    FieldCrossCheckResult,
    MachineReadableResult,
    OverallMatchStatus,
    ParsedQRPayload,
    QRCandidate,
    QRDetectionStatus,
    QRPayloadType,
)
from app.services.machine_readable.service import MachineReadableService
from app.services.machine_readable.verifier import MachineReadableVerifier

__all__ = [
    "MachineReadableService",
    "QRDetector",
    "QRDecoder",
    "GenericPayloadParser",
    "MachineReadableVerifier",
    "QRDetectionStatus",
    "QRPayloadType",
    "FieldComparisonStatus",
    "CryptoVerificationStatus",
    "OverallMatchStatus",
    "QRCandidate",
    "ParsedQRPayload",
    "FieldCrossCheckResult",
    "CryptoVerificationResult",
    "MachineReadableResult",
]
