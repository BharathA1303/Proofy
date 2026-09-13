"""
backend/app/services/document_intelligence/service.py

M1 Document Intelligence Facade Service.

Coordinates:
  1. Document Classification (decision, confidence, model telemetry)
  2. Visual / Semantic Layout Understanding (resolution-independent normalized regions)
  3. Common OCR Engine execution
  4. Layout-to-OCR token associative linkage
  5. Multi-side orchestration (Front / Back)
  6. Strict stage latency telemetry and PII-safe logging
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import numpy as np

from app.services.document_intelligence.classifier import (
    BaseDocumentClassifier,
    MultiSignalDocumentClassifier,
)
from app.services.document_intelligence.layout_engine import GenericLayoutEngine
from app.services.document_intelligence.schema import (
    ClassificationDecision,
    DocumentClassificationResult,
    DocumentIntelligenceResult,
    DocumentRegion,
    DocumentSide,
    LayoutUnderstandingResult,
    SemanticExtractionResult,
    SideStatus,
)
from app.services.document_intelligence.semantic_extractor import (
    BaseSemanticFieldExtractor,
    GenericSemanticFieldExtractor,
)
from app.services.documents.profiles.document_profile import DocumentProfile
from app.services.ocr.ocr_engine import is_ready, run_ocr

logger = logging.getLogger(__name__)


class DocumentIntelligenceService:
    """
    Unified M1 Document Intelligence Service coordinating classification,
    layout understanding, semantic field extraction, and optical character recognition.
    """

    def __init__(
        self,
        classifier: Optional[BaseDocumentClassifier] = None,
        layout_engine: Optional[GenericLayoutEngine] = None,
        semantic_extractor: Optional[BaseSemanticFieldExtractor] = None,
    ) -> None:
        self._classifier = classifier or MultiSignalDocumentClassifier()
        self._layout_engine = layout_engine or GenericLayoutEngine()
        self._semantic_extractor = semantic_extractor or GenericSemanticFieldExtractor()

    @property
    def classifier(self) -> BaseDocumentClassifier:
        return self._classifier

    @property
    def layout_engine(self) -> GenericLayoutEngine:
        return self._layout_engine

    @property
    def semantic_extractor(self) -> BaseSemanticFieldExtractor:
        return self._semantic_extractor

    def analyze_document(
        self,
        front_image: Optional[np.ndarray] = None,
        back_image: Optional[np.ndarray] = None,
        declared_type: Optional[str] = None,
        target_profile: Optional[DocumentProfile] = None,
        run_ocr_scan: bool = True,
        raw_ocr_regions: Optional[List[Any]] = None,
    ) -> DocumentIntelligenceResult:
        """
        Execute full M1 Document Intelligence pipeline on document images.

        Pipeline:
          1. Run common OCR (if enabled and engine initialized, or use provided raw_ocr_regions)
          2. Classify document type using multi-signal evidence
          3. Perform resolution-independent layout understanding
          4. Correlate OCR tokens to semantic regions
          5. Synthesize timing telemetry and result

        Security / Privacy Rule:
          No raw PII, full addresses, or face crops are logged or exposed in telemetry.
        """
        total_start = time.perf_counter()

        # Step 1: Run OCR on Front Image or adopt pre-computed OCR regions
        ocr_start = time.perf_counter()
        ocr_regions: List[Any] = list(raw_ocr_regions) if raw_ocr_regions else []
        if not ocr_regions and run_ocr_scan and front_image is not None and front_image.size > 0:
            if is_ready():
                try:
                    ocr_regions = run_ocr(front_image)
                except Exception as exc:
                    logger.warning("DocumentIntelligence: OCR execution error: %s", exc)
            else:
                logger.debug("DocumentIntelligence: OCR engine not initialized — skipping OCR pass.")
        ocr_latency_ms = (time.perf_counter() - ocr_start) * 1000.0

        # Step 2: Document Classification
        cls_start = time.perf_counter()
        classification = self._classifier.classify(
            image_np=front_image,
            side="front",
            ocr_regions=ocr_regions,
            declared_type=declared_type,
        )
        classifier_latency_ms = (time.perf_counter() - cls_start) * 1000.0

        # Resolve target profile
        effective_type = classification.document_type if classification.decision == ClassificationDecision.SUPPORTED else (declared_type or "driving_license")
        if target_profile:
            profile = target_profile
        else:
            try:
                from app.services.documents.profiles.document_profile_registry import document_profile_registry
                profile = document_profile_registry.resolve(effective_type)
            except Exception:
                profile = None

        # Step 3: Layout Understanding
        layout_start = time.perf_counter()
        if profile is not None:
            layout = self._layout_engine.understand_layout(
                image_np=front_image,
                profile=profile,
                side="front",
                ocr_regions=ocr_regions,
            )
        else:
            layout = LayoutUnderstandingResult(
                regions=[],
                side="front",
                side_status=SideStatus.PROVIDED if front_image is not None else SideStatus.SIDE_NOT_PROVIDED,
            )
        layout_latency_ms = (time.perf_counter() - layout_start) * 1000.0

        # Step 4: Semantic Field Extraction (Phase 5)
        semantic_start = time.perf_counter()
        semantic_extraction: Optional[SemanticExtractionResult] = None
        if profile is not None and self._semantic_extractor is not None:
            img_w = front_image.shape[1] if front_image is not None and front_image.size > 0 else 0
            img_h = front_image.shape[0] if front_image is not None and front_image.size > 0 else 0
            semantic_extraction = self._semantic_extractor.extract_fields(
                profile=profile,
                ocr_regions=ocr_regions,
                layout=layout,
                image_width=img_w,
                image_height=img_h,
                side="front",
            )
        semantic_latency_ms = (time.perf_counter() - semantic_start) * 1000.0

        total_latency_ms = (time.perf_counter() - total_start) * 1000.0

        # Privacy-safe audit log: only document type and decision are recorded, no PII
        logger.info(
            "DocumentIntelligence M1 complete: type=%s decision=%s confidence=%.2f regions=%d fields=%d total_ms=%.1f",
            classification.document_type,
            classification.decision.value,
            classification.confidence,
            len(layout.regions),
            len(semantic_extraction.fields) if semantic_extraction else 0,
            total_latency_ms,
        )

        return DocumentIntelligenceResult(
            classification=classification,
            layout=layout,
            ocr_regions=ocr_regions,
            semantic_extraction=semantic_extraction,
            classifier_latency_ms=classifier_latency_ms,
            layout_latency_ms=layout_latency_ms,
            ocr_latency_ms=ocr_latency_ms,
            semantic_latency_ms=semantic_latency_ms,
            total_latency_ms=total_latency_ms,
        )

    def process_document(
        self,
        front_image: Optional[np.ndarray] = None,
        back_image: Optional[np.ndarray] = None,
        declared_type: Optional[str] = None,
        target_profile: Optional[DocumentProfile] = None,
        run_ocr_scan: bool = True,
        raw_ocr_regions: Optional[List[Any]] = None,
    ) -> DocumentIntelligenceResult:
        """Convenience alias for analyze_document."""
        return self.analyze_document(
            front_image=front_image,
            back_image=back_image,
            declared_type=declared_type,
            target_profile=target_profile,
            run_ocr_scan=run_ocr_scan,
            raw_ocr_regions=raw_ocr_regions,
        )


# Singleton instance
document_intelligence_service = DocumentIntelligenceService()
