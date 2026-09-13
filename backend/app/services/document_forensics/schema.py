"""
backend/app/services/document_forensics/schema.py

Generic Document Forensics & Tampering Analysis Data Models and Enums (M3).
Defines canonical representations for:
  - Multi-signal forensic statuses and anomaly tiers
  - Granular forensic findings with normalized bounding boxes and telemetry
  - Patch-level suspicious regions and localization heatmaps
  - Multi-dimensional image quality assessments
  - Model telemetry contracts (ensuring MODEL_UNAVAILABLE when weights are absent)
  - Full forensic result structures with tamper-evident hashing and provenance
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.services.document_intelligence.schema import NormalizedBBox


class ForensicStatus(str, Enum):
    """
    High-level forensic determination.
    Strictly evidence-oriented: NEVER outputs FORGED_DOCUMENT.
    """
    FORENSIC_CLEAN = "FORENSIC_CLEAN"
    FORENSIC_SUSPICIOUS = "FORENSIC_SUSPICIOUS"
    FORENSIC_INCONCLUSIVE = "FORENSIC_INCONCLUSIVE"
    FORENSIC_UNAVAILABLE = "FORENSIC_UNAVAILABLE"


class ForensicAnomalyState(str, Enum):
    """Granular multi-signal anomaly states at M3 aggregation."""
    NO_FORENSIC_ANOMALY = "NO_FORENSIC_ANOMALY"
    WEAK_ANOMALY = "WEAK_ANOMALY"
    MULTI_SIGNAL_ANOMALY = "MULTI_SIGNAL_ANOMALY"
    MODEL_SUPPORTED_ANOMALY = "MODEL_SUPPORTED_ANOMALY"
    INCONCLUSIVE = "INCONCLUSIVE"


class SignalType(str, Enum):
    """Independent forensic measurement modalities."""
    IMAGE_QUALITY = "IMAGE_QUALITY"
    JPEG_COMPRESSION = "JPEG_COMPRESSION"
    ELA_RESIDUAL = "ELA_RESIDUAL"
    COPY_MOVE_DUPLICATION = "COPY_MOVE_DUPLICATION"
    SPLICING_EDGE = "SPLICING_EDGE"
    TEXT_REGION_ANOMALY = "TEXT_REGION_ANOMALY"
    PORTRAIT_REGION_ANOMALY = "PORTRAIT_REGION_ANOMALY"
    DOCUMENT_BOUNDARY = "DOCUMENT_BOUNDARY"
    METADATA_EXIF = "METADATA_EXIF"
    AI_TAMPERING_MODEL = "AI_TAMPERING_MODEL"


class SignalStatus(str, Enum):
    """Evaluation status for an individual forensic signal."""
    NORMAL = "NORMAL"
    SUSPICIOUS = "SUSPICIOUS"
    ANOMALOUS = "ANOMALOUS"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXIF_PRESENT = "EXIF_PRESENT"
    EXIF_ABSENT = "EXIF_ABSENT"
    EXIF_SUSPICIOUS = "EXIF_SUSPICIOUS"
    EXIF_UNAVAILABLE = "EXIF_UNAVAILABLE"
    BOUNDARY_DETECTED = "BOUNDARY_DETECTED"
    BOUNDARY_UNAVAILABLE = "BOUNDARY_UNAVAILABLE"
    BOUNDARY_SUSPICIOUS = "BOUNDARY_SUSPICIOUS"


class SignalSeverity(str, Enum):
    """Severity level of an individual forensic indicator."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ModelStatus(str, Enum):
    """Operational status of the deep-learning forensic model."""
    MODEL_AVAILABLE = "MODEL_AVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_INFERENCE_FAILED = "MODEL_INFERENCE_FAILED"


@dataclass
class ImageQualityAssessment:
    """Multi-dimensional evaluation of raw image capture quality."""
    is_adequate: bool
    status: str  # "adequate" | "insufficient"
    width: int
    height: int
    aspect_ratio: float
    blur_score: float
    brightness_mean: float
    contrast_std: float
    noise_score: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_adequate": self.is_adequate,
            "status": self.status,
            "width": self.width,
            "height": self.height,
            "aspect_ratio": round(self.aspect_ratio, 3),
            "blur_score": round(self.blur_score, 2),
            "brightness_mean": round(self.brightness_mean, 2),
            "contrast_std": round(self.contrast_std, 2),
            "noise_score": round(self.noise_score, 2),
            "reasons": self.reasons,
        }


@dataclass
class DocumentBoundaryResult:
    """Card perimeter and boundary geometry analysis."""
    status: SignalStatus
    contour_points: Optional[List[List[int]]] = None
    normalized_bbox: Optional[NormalizedBBox] = None
    is_rectangular: bool = False
    rectangularity_score: float = 0.0
    aspect_ratio: float = 0.0
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "contour_points": self.contour_points,
            "normalized_bbox": {
                "x": self.normalized_bbox.x,
                "y": self.normalized_bbox.y,
                "width": self.normalized_bbox.width,
                "height": self.normalized_bbox.height,
            } if self.normalized_bbox else None,
            "is_rectangular": self.is_rectangular,
            "rectangularity_score": round(self.rectangularity_score, 3),
            "aspect_ratio": round(self.aspect_ratio, 3),
            "details": self.details,
        }


@dataclass
class ForensicFinding:
    """A granular finding generated by one forensic detector."""
    finding_id: str
    signal_type: SignalType
    status: SignalStatus
    severity: SignalSeverity
    confidence: float
    score: Optional[float] = None
    bbox: Optional[List[List[int]]] = None
    normalized_bbox: Optional[NormalizedBBox] = None
    region_name: Optional[str] = None
    source: str = "classical_engine"
    model_version: Optional[str] = None
    explanation: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    profile_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "signal_type": self.signal_type.value if isinstance(self.signal_type, Enum) else str(self.signal_type),
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "severity": self.severity.value if isinstance(self.severity, Enum) else str(self.severity),
            "confidence": round(self.confidence, 3),
            "score": round(self.score, 3) if self.score is not None else None,
            "bbox": self.bbox,
            "normalized_bbox": {
                "x": self.normalized_bbox.x,
                "y": self.normalized_bbox.y,
                "width": self.normalized_bbox.width,
                "height": self.normalized_bbox.height,
            } if self.normalized_bbox else None,
            "region_name": self.region_name,
            "source": self.source,
            "model_version": self.model_version,
            "explanation": self.explanation,
            "metrics": self.metrics,
            "profile_version": self.profile_version,
        }


@dataclass
class SuspiciousRegion:
    """A localized spatial cluster of forensic anomalies on the document."""
    region_id: str
    region_name: str
    bbox: List[List[int]]
    normalized_bbox: NormalizedBBox
    signals: List[str]
    score: float
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "region_name": self.region_name,
            "bbox": self.bbox,
            "normalized_bbox": {
                "x": self.normalized_bbox.x,
                "y": self.normalized_bbox.y,
                "width": self.normalized_bbox.width,
                "height": self.normalized_bbox.height,
            },
            "signals": self.signals,
            "score": round(self.score, 3),
            "explanation": self.explanation,
        }


@dataclass
class AIModelForensicResult:
    """Evaluation telemetry from the deep-learning tampering model."""
    status: ModelStatus
    model_name: str = "Generic_Tampering_Detector"
    version: str = "1.0.0"
    weights_path: Optional[str] = None
    confidence: Optional[float] = None
    tampering_detected: Optional[bool] = None
    heatmap: Optional[List[List[float]]] = None
    explanation: str = "Model weights not configured or absent. Running in classical forensic mode."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "model_name": self.model_name,
            "version": self.version,
            "weights_path": self.weights_path,
            "confidence": round(self.confidence, 3) if self.confidence is not None else None,
            "tampering_detected": self.tampering_detected,
            "explanation": self.explanation,
        }


@dataclass
class ForensicResult:
    """Complete Module 3 Document Forensics Result."""
    document_type: str
    status: ForensicStatus
    anomaly_state: ForensicAnomalyState
    overall_explanation: str
    findings: List[ForensicFinding] = field(default_factory=list)
    suspicious_regions: List[SuspiciousRegion] = field(default_factory=list)
    quality: ImageQualityAssessment = field(
        default_factory=lambda: ImageQualityAssessment(
            is_adequate=True,
            status="adequate",
            width=0,
            height=0,
            aspect_ratio=0.0,
            blur_score=0.0,
            brightness_mean=0.0,
            contrast_std=0.0,
            noise_score=0.0,
        )
    )
    boundary: Optional[DocumentBoundaryResult] = None
    metadata_details: Dict[str, Any] = field(default_factory=dict)
    model_results: List[AIModelForensicResult] = field(default_factory=list)
    image_sha256: str = ""
    heatmap_grid: Optional[List[List[float]]] = None
    profile_version: str = "1.0.0"
    forensic_engine_version: str = "8.0.0"
    telemetry: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_type": self.document_type,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "anomaly_state": self.anomaly_state.value if isinstance(self.anomaly_state, Enum) else str(self.anomaly_state),
            "overall_explanation": self.overall_explanation,
            "findings": [f.to_dict() for f in self.findings],
            "suspicious_regions": [r.to_dict() for r in self.suspicious_regions],
            "quality": self.quality.to_dict(),
            "boundary": self.boundary.to_dict() if self.boundary else None,
            "metadata_details": self.metadata_details,
            "model_results": [m.to_dict() for m in self.model_results],
            "image_sha256": self.image_sha256,
            "heatmap_grid": self.heatmap_grid,
            "profile_version": self.profile_version,
            "forensic_engine_version": self.forensic_engine_version,
            "telemetry": self.telemetry,
        }
