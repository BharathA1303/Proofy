"""
backend/app/services/document_intelligence/__init__.py

M1 Document Intelligence Package.
Provides generic AI document classification, resolution-independent layout
understanding, and OCR token association.
"""
from app.services.document_intelligence.classifier import (
    BaseDocumentClassifier,
    MockDocumentClassifier,
    MultiSignalDocumentClassifier,
    VisionModelClassifier,
)
from app.services.document_intelligence.layout_engine import GenericLayoutEngine
from app.services.document_intelligence.schema import (
    ClassificationDecision,
    ClassificationModelInfo,
    DocumentClassificationResult,
    DocumentIntelligenceResult,
    DocumentRegion,
    DocumentRegionType,
    DocumentSide,
    ExpectedRegionConfig,
    FieldCandidate,
    FieldCandidateStatus,
    LayoutUnderstandingResult,
    ModelStatus,
    NormalizedBBox,
    SemanticDateRole,
    SemanticExtractionResult,
    SemanticFieldConfig,
    SemanticFieldResult,
    SideStatus,
    SpatialRelationship,
)
from app.services.document_intelligence.semantic_extractor import (
    BaseSemanticFieldExtractor,
    GenericSemanticFieldExtractor,
    NeuralSemanticFieldExtractor,
)
from app.services.document_intelligence.service import (
    DocumentIntelligenceService,
    document_intelligence_service,
)

__all__ = [
    "ClassificationDecision",
    "ModelStatus",
    "DocumentSide",
    "SideStatus",
    "DocumentRegionType",
    "NormalizedBBox",
    "DocumentRegion",
    "ExpectedRegionConfig",
    "ClassificationModelInfo",
    "DocumentClassificationResult",
    "LayoutUnderstandingResult",
    "DocumentIntelligenceResult",
    "SpatialRelationship",
    "SemanticDateRole",
    "FieldCandidateStatus",
    "SemanticFieldConfig",
    "FieldCandidate",
    "SemanticFieldResult",
    "SemanticExtractionResult",
    "BaseDocumentClassifier",
    "VisionModelClassifier",
    "MultiSignalDocumentClassifier",
    "MockDocumentClassifier",
    "GenericLayoutEngine",
    "BaseSemanticFieldExtractor",
    "GenericSemanticFieldExtractor",
    "NeuralSemanticFieldExtractor",
    "DocumentIntelligenceService",
    "document_intelligence_service",
]
