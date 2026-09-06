"""
backend/app/schemas/face_verification.py

Pydantic schemas for Module 4: Biometric Verification & Presentation Attack Detection.

Architecture:
  - Document-agnostic verification contracts.
  - Strict separation of Primary deep PAD (MiniFASNet) and Secondary defensive telemetry.
  - NEVER includes raw face embeddings or feature tensors.
  - NEVER includes raw camera frame pixels or binary crops.
  - Returns structured, explainable verification telemetry for border screening officers.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class FaceQualityDetail(BaseModel):
    """
    Structured face quality indicators.
    Deterministic signal measurements without fabricated probabilities.
    """
    status: str = Field(
        ...,
        description="Overall quality status: 'acceptable' | 'poor' | 'unavailable'",
    )
    blur: str = Field(
        ...,
        description="Sharpness assessment: 'acceptable' | 'poor'",
    )
    brightness: str = Field(
        ...,
        description="Luminance assessment: 'acceptable' | 'poor'",
    )
    contrast: str = Field(
        ...,
        description="Contrast assessment: 'acceptable' | 'poor'",
    )
    face_size: str = Field(
        ...,
        description="Resolution assessment: 'acceptable' | 'poor'",
    )
    pose: str = Field(
        ...,
        description="Alignment/pose assessment: 'acceptable' | 'poor'",
    )
    explanation: str = Field(
        default="",
        description="Officer-facing quality note or diagnosis",
    )


class DocumentFaceResult(BaseModel):
    """Assessment of the identity document photograph."""
    detected: bool = Field(..., description="Whether a face was detected on the document")
    face_count: int = Field(default=0, description="Number of faces detected on the document")
    quality: str = Field(
        ...,
        description="'acceptable' | 'poor' | 'unavailable'",
    )
    quality_details: Optional[FaceQualityDetail] = Field(
        default=None,
        description="Detailed quality signal breakdown",
    )
    detector_used: Optional[str] = Field(
        default=None,
        description="Detector architecture utilized (e.g. 'InsightFace-SCRFD-10G')",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error code if detection/extraction failed",
    )


class LiveFaceResult(BaseModel):
    """Assessment of the live camera capture."""
    detected: bool = Field(..., description="Whether a face was detected in live capture")
    face_count: int = Field(default=0, description="Number of faces detected in live capture")
    quality: str = Field(
        ...,
        description="'acceptable' | 'poor' | 'unavailable'",
    )
    quality_details: Optional[FaceQualityDetail] = Field(
        default=None,
        description="Detailed quality signal breakdown",
    )
    detector_used: Optional[str] = Field(
        default=None,
        description="Detector architecture utilized (e.g. 'InsightFace-SCRFD-10G')",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error code if live face processing failed",
    )


class SecondaryPADSchema(BaseModel):
    """
    Secondary defensive optical indicators.
    Evaluates physical optical artifacts alongside the primary deep PAD model.
    """
    frequency_domain: str = Field(
        default="pass",
        description="2D FFT moiré/pixel grid: 'pass' | 'suspected_spoof' | 'inconclusive'",
    )
    texture_analysis: str = Field(
        default="pass",
        description="YCrCb chrominance dispersion: 'pass' | 'suspected_spoof' | 'inconclusive'",
    )
    specular_glare: str = Field(
        default="pass",
        description="HSV glass/laminate glare: 'pass' | 'suspected_spoof' | 'inconclusive'",
    )
    temporal_variance: str = Field(
        default="pass",
        description="Micro-motion across burst frames: 'pass' | 'suspected_spoof' | 'inconclusive'",
    )


class AntiSpoofResult(BaseModel):
    """
    Primary Presentation Attack Detection (PAD) assessment.
    Conforms to ISO/IEC 30107-3 concepts (bona fide human vs presentation attack).
    """
    model: str = Field(
        default="MiniFASNetV2",
        description="Primary deep PAD model identifier",
    )
    status: str = Field(
        ...,
        description="'pass' | 'suspected_spoof' | 'inconclusive' | 'model_unavailable'",
    )
    score: Optional[float] = Field(
        default=None,
        description="Calibrated bona fide human probability (0.0 to 1.0) or None if unavailable",
    )
    explanation: str = Field(
        default="",
        description="Deterministic explanation of liveness / anti-spoof determination",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic metadata (e.g. burst frame count, individual frame metrics)",
    )


class FaceMatchResult(BaseModel):
    """
    Face embedding vector comparison.
    Cosine similarity between document photo vector and live camera vector.
    """
    status: str = Field(
        ...,
        description="'match' | 'no_match' | 'inconclusive' | 'unavailable'",
    )
    similarity: Optional[float] = Field(
        default=None,
        description="Cosine similarity metric (0.0 to 1.0) or None if unavailable",
    )
    similarity_score: Optional[float] = Field(
        default=None,
        description="Alias for similarity score for API consistency",
    )
    threshold: float = Field(
        ...,
        description="Operating threshold used for match classification",
    )
    embedding_model: str = Field(
        default="ArcFace-w600k_r50",
        description="Feature representation model used for embedding extraction",
    )
    embedding_dimension: int = Field(
        default=512,
        description="Dimensionality of normalized embedding space (512 for ArcFace)",
    )
    explanation: str = Field(
        default="",
        description="Deterministic explanation of comparison result",
    )


class FaceVerificationResponse(BaseModel):
    """
    Response schema for POST /api/v1/verification/face.
    Module 4: Biometric Verification & Presentation Attack Detection.
    """
    verification_id: str = Field(..., description="Unique session verification ID")
    document_type: str = Field(..., description="Document type key (e.g. 'passport')")
    status: str = Field(
        ...,
        description=(
            "Overall processing status: "
            "'completed' | 'failed' | 'model_unavailable' | 'processing_error'"
        ),
    )
    overall_assessment: str = Field(
        ...,
        description=(
            "Deterministic biometric assessment: "
            "'FACE_MATCH' | 'FACE_MISMATCH' | 'SUSPECTED_SPOOF' | "
            "'DOCUMENT_FACE_NOT_FOUND' | 'NO_FACE_DETECTED' | 'MULTIPLE_FACES_DETECTED' | "
            "'POOR_QUALITY' | 'BIOMETRIC_INCONCLUSIVE' | 'MODEL_UNAVAILABLE' | 'PROCESSING_ERROR'"
        ),
    )
    overall_biometric_status: str = Field(
        ...,
        description="Direct biometric decision state (e.g. 'FACE_MATCH', 'SUSPECTED_SPOOF')",
    )
    document_face: DocumentFaceResult = Field(..., description="Document face evaluation")
    live_face: LiveFaceResult = Field(..., description="Live camera face evaluation")
    anti_spoof: AntiSpoofResult = Field(..., description="Primary deep PAD evaluation (MiniFASNet)")
    secondary_pad: SecondaryPADSchema = Field(..., description="Secondary defensive optical telemetry")
    face_match: FaceMatchResult = Field(..., description="Facial vector comparison evaluation (ArcFace)")
    summary: str = Field(
        ...,
        description="Officer-facing summary statement explaining the biometric result",
    )


class ModelInfoResponse(BaseModel):
    """
    Non-sensitive model telemetry and configuration info for auditability.
    """
    face_detector: str
    detector_available: bool
    face_embedding: str
    embedding_dimension: int
    embedding_available: bool
    pad_model: str
    pad_available: bool
    face_match_threshold: float
    pad_threshold: float
