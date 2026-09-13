"""
backend/app/services/document_forensics/__init__.py

Document-Agnostic AI Document Tampering & Forensic Authenticity Intelligence (M3).
"""
from app.services.document_forensics.classical import ClassicalForensicEngine
from app.services.document_forensics.localization import ForensicLocalizationEngine
from app.services.document_forensics.quality import DocumentQualityEngine
from app.services.document_forensics.schema import (
    AIModelForensicResult,
    DocumentBoundaryResult,
    ForensicAnomalyState,
    ForensicFinding,
    ForensicResult,
    ForensicStatus,
    ImageQualityAssessment,
    ModelStatus,
    SignalSeverity,
    SignalStatus,
    SignalType,
    SuspiciousRegion,
)
from app.services.document_forensics.service import DocumentForensicsService
from app.services.document_forensics.tampering_model import DocumentTamperingModel

__all__ = [
    "DocumentForensicsService",
    "DocumentQualityEngine",
    "ClassicalForensicEngine",
    "DocumentTamperingModel",
    "ForensicLocalizationEngine",
    "ForensicStatus",
    "ForensicAnomalyState",
    "SignalType",
    "SignalStatus",
    "SignalSeverity",
    "ModelStatus",
    "ForensicFinding",
    "SuspiciousRegion",
    "ImageQualityAssessment",
    "DocumentBoundaryResult",
    "AIModelForensicResult",
    "ForensicResult",
]
