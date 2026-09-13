"""
backend/app/services/document_intelligence/schema.py

Generic Document Intelligence (M1) Data Models and Enums.
Defines canonical representations for:
  - Document Classification decisions, model telemetry, and evidence
  - Semantic Document Regions (resolution-independent NormalizedBBox)
  - Multi-side document handling (front / back)
  - Layout Understanding results and telemetry
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ClassificationDecision(str, Enum):
    """Operational decision from document classification."""
    SUPPORTED = "SUPPORTED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


class ModelStatus(str, Enum):
    """Operational state of an ML/AI model."""
    MODEL_AVAILABLE = "MODEL_AVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_LOW_CONFIDENCE = "MODEL_LOW_CONFIDENCE"


class DocumentSide(str, Enum):
    """Physical face of a document credential."""
    FRONT = "front"
    BACK = "back"


class SideStatus(str, Enum):
    """Presence status of a document side."""
    PROVIDED = "PROVIDED"
    SIDE_NOT_PROVIDED = "SIDE_NOT_PROVIDED"
    OPTIONAL_OMITTED = "OPTIONAL_OMITTED"


class DocumentRegionType(str, Enum):
    """
    Generic semantic region categories across all document types.
    Strictly generic: no document-type-specific classes.
    """
    CARD_BOUNDARY = "CARD_BOUNDARY"
    PORTRAIT = "PORTRAIT"
    IDENTITY = "IDENTITY"
    LICENSE_NUMBER = "LICENSE_NUMBER"
    DATE_SECTION = "DATE_SECTION"
    VALIDITY = "VALIDITY"
    VEHICLE_CLASS = "VEHICLE_CLASS"
    AUTHORITY = "AUTHORITY"
    ADDRESS = "ADDRESS"
    SECURITY = "SECURITY"
    QR = "QR"
    MACHINE_READABLE = "MACHINE_READABLE"
    UNKNOWN = "UNKNOWN"


class SpatialRelationship(str, Enum):
    """Spatial relationship between a label and candidate value."""
    LABEL_LEFT_VALUE = "LABEL_LEFT_VALUE"          # Value is horizontally to the right of label
    LABEL_ABOVE_VALUE = "LABEL_ABOVE_VALUE"        # Value is vertically directly below label
    LABEL_SAME_ROW_VALUE = "LABEL_SAME_ROW_VALUE"  # Value shares same horizontal band as label
    LABEL_SAME_COLUMN_VALUE = "LABEL_SAME_COLUMN_VALUE" # Value shares same vertical column as label
    REGION_CONSTRAINED_VALUE = "REGION_CONSTRAINED_VALUE" # Value found inside expected semantic region
    DERIVED_VALUE = "DERIVED_VALUE"                # Value derived from another field (e.g. state from DL prefix)
    INLINE_MATCH = "INLINE_MATCH"                  # Value extracted from the same line/token as label


class SemanticDateRole(str, Enum):
    """Semantic role of a date extracted from a document credential."""
    DOB = "DOB"
    ISSUE_DATE = "ISSUE_DATE"
    VALID_FROM = "VALID_FROM"
    NON_TRANSPORT_VALIDITY = "NON_TRANSPORT_VALIDITY"
    TRANSPORT_VALIDITY = "TRANSPORT_VALIDITY"
    EXPIRY_DATE = "EXPIRY_DATE"
    UNKNOWN_DATE = "UNKNOWN_DATE"


class FieldCandidateStatus(str, Enum):
    """Information-quality status of an extracted field candidate."""
    FOUND = "FOUND"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


@dataclass(frozen=True)
class NormalizedBBox:
    """
    Resolution-independent bounding box with coordinates normalized to [0.0, 1.0].
    Preserves exact geometric ratios across downscaling, upscaling, or sensor changes.
    """
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        # Clamp coordinates to [0.0, 1.0]
        object.__setattr__(self, "x", max(0.0, min(1.0, float(self.x))))
        object.__setattr__(self, "y", max(0.0, min(1.0, float(self.y))))
        object.__setattr__(self, "width", max(0.0, min(1.0 - self.x, float(self.width))))
        object.__setattr__(self, "height", max(0.0, min(1.0 - self.y, float(self.height))))

    def to_pixel_bbox(self, image_width: int, image_height: int) -> List[List[int]]:
        """
        Convert normalized coordinates to standard 4-point pixel polygon:
        [[x1, y1], [x2, y1], [x2, y2], [x1, y2]].
        """
        px1 = int(round(self.x * image_width))
        py1 = int(round(self.y * image_height))
        px2 = int(round((self.x + self.width) * image_width))
        py2 = int(round((self.y + self.height) * image_height))
        return [[px1, py1], [px2, py1], [px2, py2], [px1, py2]]

    @classmethod
    def from_pixel_bbox(cls, bbox: List[List[int]], image_width: int, image_height: int) -> NormalizedBBox:
        """Create NormalizedBBox from pixel polygon or rect corner list."""
        if not bbox or image_width <= 0 or image_height <= 0:
            return cls(0.0, 0.0, 0.0, 0.0)
        xs = [pt[0] for pt in bbox]
        ys = [pt[1] for pt in bbox]
        min_x, max_x = max(0, min(xs)), min(image_width, max(xs))
        min_y, max_y = max(0, min(ys)), min(image_height, max(ys))
        return cls(
            x=round(min_x / image_width, 4),
            y=round(min_y / image_height, 4),
            width=round((max_x - min_x) / image_width, 4),
            height=round((max_y - min_y) / image_height, 4),
        )

    def intersects(self, other: NormalizedBBox) -> bool:
        """Return True if this bounding box overlaps with another bounding box."""
        if self.x + self.width <= other.x or other.x + other.width <= self.x:
            return False
        if self.y + self.height <= other.y or other.y + other.height <= self.y:
            return False
        return True

    def overlap_ratio(self, other: NormalizedBBox) -> float:
        """Compute intersection over other area ratio (0.0–1.0)."""
        if not self.intersects(other):
            return 0.0
        inter_x = max(self.x, other.x)
        inter_y = max(self.y, other.y)
        inter_w = min(self.x + self.width, other.x + other.width) - inter_x
        inter_h = min(self.y + self.height, other.y + other.height) - inter_y
        inter_area = max(0.0, inter_w) * max(0.0, inter_h)
        other_area = other.width * other.height
        return (inter_area / other_area) if other_area > 0 else 0.0


@dataclass
class DocumentRegion:
    """A generic semantic document region detected by visual or profile layout understanding."""
    region_type: DocumentRegionType
    normalized_bbox: Optional[NormalizedBBox] = None
    pixel_bbox: Optional[List[List[int]]] = None
    confidence: float = 0.0
    source: str = "LAYOUT_DETECTION"
    side: str = "front"  # "front" | "back"
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    associated_text: Optional[str] = None
    associated_ocr_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExpectedRegionConfig:
    """Expected semantic region declaration in a DocumentProfile."""
    region_type: DocumentRegionType
    expected: bool = True
    side: str = "front"  # "front" | "back" | "any"
    relative_box: Optional[NormalizedBBox] = None
    required: bool = False
    description: Optional[str] = None


@dataclass
class ClassificationModelInfo:
    """Model provenance and metadata."""
    name: str = "generic_document_classifier"
    version: str = "1.0.0"
    status: ModelStatus = ModelStatus.MODEL_UNAVAILABLE
    weights_path: Optional[str] = None


@dataclass
class DocumentClassificationResult:
    """
    Canonical result of document type classification.
    Maintains backward compatibility with legacy guard properties.
    """
    document_type: str = "unknown"
    confidence: float = 0.0
    decision: ClassificationDecision = ClassificationDecision.UNKNOWN
    model: ClassificationModelInfo = field(default_factory=ClassificationModelInfo)
    evidence: List[str] = field(default_factory=list)
    declared_type: Optional[str] = None
    is_mismatch: bool = False
    error_message: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def __init__(
        self,
        document_type: Optional[str] = None,
        confidence: float = 0.0,
        decision: Optional[ClassificationDecision] = None,
        model: Optional[ClassificationModelInfo] = None,
        evidence: Optional[List[str]] = None,
        declared_type: Optional[str] = None,
        is_mismatch: bool = False,
        error_message: Optional[str] = None,
        reasons: Optional[List[str]] = None,
        latency_ms: float = 0.0,
        detected_type: Optional[str] = None,
        **kwargs: Any,
    ):
        self.document_type = document_type or detected_type or "unknown"
        self.confidence = confidence
        self.decision = decision or (
            ClassificationDecision.UNSUPPORTED if is_mismatch else ClassificationDecision.SUPPORTED
        )
        self.model = model or ClassificationModelInfo(
            name="document_classifier",
            version="1.0.0",
            status=ModelStatus.MODEL_AVAILABLE,
        )
        self.evidence = evidence or []
        self.declared_type = declared_type
        self.is_mismatch = is_mismatch
        self.error_message = error_message
        self.reasons = reasons or []
        self.latency_ms = latency_ms

    @property
    def detected_type(self) -> str:
        """Backward-compatible alias for existing verification guard callers."""
        return self.document_type

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for telemetry and API responses."""
        return {
            "document_type": self.document_type,
            "confidence": round(self.confidence, 4),
            "decision": self.decision.value,
            "model": {
                "name": self.model.name,
                "version": self.model.version,
                "status": self.model.status.value,
            },
            "evidence": self.evidence,
            "declared_type": self.declared_type,
            "is_mismatch": self.is_mismatch,
            "latency_ms": round(self.latency_ms, 2),
        }


@dataclass
class LayoutUnderstandingResult:
    """Structured result from layout analysis for one document face."""
    regions: List[DocumentRegion] = field(default_factory=list)
    side: str = "front"
    side_status: SideStatus = SideStatus.PROVIDED
    image_width: int = 0
    image_height: int = 0
    model: ClassificationModelInfo = field(default_factory=ClassificationModelInfo)
    latency_ms: float = 0.0

    def get_region(self, region_type: DocumentRegionType) -> Optional[DocumentRegion]:
        """Retrieve the primary region of a given semantic type."""
        for r in self.regions:
            if r.region_type == region_type:
                return r
        return None

    def get_regions(self, region_type: DocumentRegionType) -> List[DocumentRegion]:
        """Retrieve all regions matching a semantic type."""
        return [r for r in self.regions if r.region_type == region_type]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "side": self.side,
            "side_status": self.side_status.value,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "region_count": len(self.regions),
            "regions": [
                {
                    "type": r.region_type.value,
                    "confidence": round(r.confidence, 4),
                    "source": r.source,
                    "normalized_bbox": {
                        "x": r.normalized_bbox.x,
                        "y": r.normalized_bbox.y,
                        "width": r.normalized_bbox.width,
                        "height": r.normalized_bbox.height,
                    } if r.normalized_bbox else None,
                    "pixel_bbox": r.pixel_bbox,
                    "associated_text": r.associated_text,
                }
                for r in self.regions
            ],
            "latency_ms": round(self.latency_ms, 2),
        }


@dataclass
class SemanticFieldConfig:
    """Profile configuration defining a logical semantic document field."""
    field_name: str
    display_name: str
    region_type: Optional[DocumentRegionType] = None
    labels: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    negative_patterns: List[str] = field(default_factory=list)
    allowed_relationships: List[SpatialRelationship] = field(default_factory=lambda: [
        SpatialRelationship.LABEL_LEFT_VALUE,
        SpatialRelationship.LABEL_ABOVE_VALUE,
        SpatialRelationship.LABEL_SAME_ROW_VALUE,
        SpatialRelationship.REGION_CONSTRAINED_VALUE,
        SpatialRelationship.INLINE_MATCH,
    ])
    multiline: bool = False
    normalizer_type: Optional[str] = None  # "date", "license_number", "cov", "blood_group", "state", "text"
    required: bool = False
    side: str = "any"  # "front", "back", "any"
    date_role: Optional[SemanticDateRole] = None
    max_horizontal_distance: float = 0.60
    max_vertical_distance: float = 0.25
    column_alignment_tolerance: float = 0.15


@dataclass
class FieldCandidate:
    """A single candidate value for a semantic field with evidence and spatial context."""
    value: Optional[str] = None
    normalized_value: Optional[str] = None
    raw: Optional[str] = None
    confidence: float = 0.0
    ocr_confidence: float = 0.0
    semantic_confidence: float = 0.0
    bbox: Optional[List[List[int]]] = None
    normalized_bbox: Optional[NormalizedBBox] = None
    source: str = "SPATIAL_ASSOCIATION"
    relationship: Optional[SpatialRelationship] = None
    label_bbox: Optional[List[List[int]]] = None
    label_normalized_bbox: Optional[NormalizedBBox] = None
    matched_label: Optional[str] = None
    region_type: Optional[DocumentRegionType] = None
    date_role: Optional[SemanticDateRole] = None
    evidence: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "normalized_value": self.normalized_value,
            "raw": self.raw,
            "confidence": round(self.confidence, 4),
            "ocr_confidence": round(self.ocr_confidence, 4),
            "semantic_confidence": round(self.semantic_confidence, 4),
            "bbox": self.bbox,
            "source": self.source,
            "relationship": self.relationship.value if self.relationship else None,
            "matched_label": self.matched_label,
            "region_type": self.region_type.value if self.region_type else None,
            "date_role": self.date_role.value if self.date_role else None,
            "evidence": self.evidence,
        }


@dataclass
class SemanticFieldResult:
    """Result of semantic field extraction for one logical document field."""
    field_name: str
    value: Optional[str] = None
    normalized_value: Optional[str] = None
    raw: Optional[str] = None
    status: FieldCandidateStatus = FieldCandidateStatus.MISSING
    confidence: float = 0.0
    ocr_confidence: float = 0.0
    semantic_confidence: float = 0.0
    bbox: Optional[List[List[int]]] = None
    normalized_bbox: Optional[NormalizedBBox] = None
    source: Optional[str] = None
    relationship: Optional[SpatialRelationship] = None
    region_type: Optional[DocumentRegionType] = None
    candidates: List[FieldCandidate] = field(default_factory=list)
    best_candidate: Optional[FieldCandidate] = None
    label_bbox: Optional[List[List[int]]] = None
    matched_label: Optional[str] = None
    evidence: List[str] = field(default_factory=list)
    profile_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "value": self.value,
            "normalized_value": self.normalized_value,
            "raw": self.raw,
            "status": self.status.value,
            "confidence": round(self.confidence, 4),
            "ocr_confidence": round(self.ocr_confidence, 4),
            "semantic_confidence": round(self.semantic_confidence, 4),
            "bbox": self.bbox,
            "source": self.source,
            "relationship": self.relationship.value if self.relationship else None,
            "region_type": self.region_type.value if self.region_type else None,
            "matched_label": self.matched_label,
            "candidate_count": len(self.candidates),
            "candidates": [c.to_dict() for c in self.candidates],
            "evidence": self.evidence,
        }


@dataclass
class SemanticExtractionResult:
    """Structured result of semantic field extraction across all configured document fields."""
    fields: Dict[str, SemanticFieldResult] = field(default_factory=dict)
    date_candidates: List[FieldCandidate] = field(default_factory=list)
    model: ClassificationModelInfo = field(default_factory=ClassificationModelInfo)
    latency_ms: float = 0.0
    side: str = "front"

    def get_field(self, name: str) -> Optional[SemanticFieldResult]:
        return self.fields.get(name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "side": self.side,
            "field_count": len(self.fields),
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "date_candidates_count": len(self.date_candidates),
            "date_candidates": [d.to_dict() for d in self.date_candidates],
            "latency_ms": round(self.latency_ms, 2),
        }


@dataclass
class DocumentIntelligenceResult:
    """Comprehensive M1 document intelligence execution output."""
    classification: DocumentClassificationResult
    layout: LayoutUnderstandingResult
    ocr_regions: List[Any] = field(default_factory=list)
    semantic_extraction: Optional[SemanticExtractionResult] = None
    classifier_latency_ms: float = 0.0
    layout_latency_ms: float = 0.0
    ocr_latency_ms: float = 0.0
    semantic_latency_ms: float = 0.0
    total_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "classification": self.classification.to_dict(),
            "layout": self.layout.to_dict(),
            "ocr_region_count": len(self.ocr_regions),
            "telemetry": {
                "classifier_latency_ms": round(self.classifier_latency_ms, 2),
                "layout_latency_ms": round(self.layout_latency_ms, 2),
                "ocr_latency_ms": round(self.ocr_latency_ms, 2),
                "semantic_latency_ms": round(self.semantic_latency_ms, 2),
                "total_latency_ms": round(self.total_latency_ms, 2),
            },
        }
        if self.semantic_extraction is not None:
            res["semantic_extraction"] = self.semantic_extraction.to_dict()
        return res

