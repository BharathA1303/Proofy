"""
backend/app/services/document_intelligence/layout_engine.py

Generic Visual & Semantic Layout Understanding Engine.

ARCHITECTURE RULES:
  - Generic across all document types; document-specific regions are defined in DocumentProfile.
  - Generates resolution-independent NormalizedBBox representations and scales pixel polygons.
  - Multi-side awareness: Front vs. Back sides are tracked; missing sides return SIDE_NOT_PROVIDED.
  - Associative OCR Provenance: links intersecting OCR tokens to semantic regions without
    destroying or altering the raw OCR token coordinates, confidence, or source.
  - Strictly non-semantic: detects regions (e.g. VALIDITY, PORTRAIT) but does NOT perform
    field extraction (Phase 5) or biometric face matching (M4).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import numpy as np

from app.services.document_intelligence.schema import (
    ClassificationModelInfo,
    DocumentRegion,
    DocumentRegionType,
    DocumentSide,
    ExpectedRegionConfig,
    LayoutUnderstandingResult,
    ModelStatus,
    NormalizedBBox,
    SideStatus,
)
from app.services.documents.profiles.document_profile import DocumentProfile

logger = logging.getLogger(__name__)


class GenericLayoutEngine:
    """
    Resolution-independent, profile-driven visual and geometric layout understanding engine.
    """

    def __init__(
        self,
        model_name: str = "generic_document_layout_net",
        version: str = "1.0.0",
        weights_path: Optional[str] = None,
    ) -> None:
        self._model_name = model_name
        self._version = version
        self._weights_path = weights_path or os.getenv("DOCUMENT_LAYOUT_WEIGHTS_PATH")
        self._model_available = False
        self._check_weights()

    def _check_weights(self) -> None:
        if self._weights_path and os.path.exists(self._weights_path):
            self._model_available = True
            logger.info("GenericLayoutEngine: Weights available at %s", self._weights_path)
        else:
            self._model_available = False
            logger.info("GenericLayoutEngine: No weights file found. Model status is MODEL_UNAVAILABLE.")

    def is_model_available(self) -> bool:
        return self._model_available

    def get_model_status(self) -> ModelStatus:
        return ModelStatus.MODEL_AVAILABLE if self._model_available else ModelStatus.MODEL_UNAVAILABLE

    def understand_layout(
        self,
        image_np: Optional[np.ndarray],
        profile: DocumentProfile,
        side: str = "front",
        ocr_regions: Optional[List[Any]] = None,
    ) -> LayoutUnderstandingResult:
        """
        Analyze document layout and extract semantic regions for the specified face.

        Args:
            image_np: BGR numpy image of the document face (or None if not provided).
            profile: Target DocumentProfile declaring expected semantic regions.
            side: 'front' or 'back'.
            ocr_regions: Optional detected OCRRegion objects to associate with semantic regions.

        Returns:
            LayoutUnderstandingResult with semantic DocumentRegion items, normalized/pixel bboxes,
            and associated OCR tokens.
        """
        start_time = time.perf_counter()

        model_info = ClassificationModelInfo(
            name=self._model_name,
            version=self._version,
            status=self.get_model_status(),
            weights_path=self._weights_path,
        )

        # Multi-side check: if image is missing for this side
        if image_np is None or image_np.size == 0:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return LayoutUnderstandingResult(
                regions=[],
                side=side,
                side_status=SideStatus.SIDE_NOT_PROVIDED,
                image_width=0,
                image_height=0,
                model=model_info,
                latency_ms=latency_ms,
            )

        h, w = image_np.shape[:2]
        detected_regions: List[DocumentRegion] = []

        # 1. Whole Document Card Boundary
        detected_regions.append(DocumentRegion(
            region_type=DocumentRegionType.CARD_BOUNDARY,
            normalized_bbox=NormalizedBBox(x=0.0, y=0.0, width=1.0, height=1.0),
            pixel_bbox=[[0, 0], [w, 0], [w, h], [0, h]],
            confidence=0.99,
            source="IMAGE_BOUNDS",
            side=side,
            model_name=self._model_name,
            model_version=self._version,
        ))

        # 2. Profile-Driven Expected Semantic Regions
        expected_configs: Dict[str, Any] = getattr(profile, "expected_semantic_regions", {})

        # Also support legacy expected_regions dict if expected_semantic_regions is empty
        if not expected_configs and getattr(profile, "expected_regions", None):
            expected_configs = self._adapt_legacy_regions(profile.expected_regions)

        for name, config in expected_configs.items():
            if isinstance(config, ExpectedRegionConfig):
                # Verify side suitability ('front', 'back', or 'any')
                if config.side != "any" and config.side != side:
                    continue

                if not config.expected or not config.relative_box:
                    continue

                norm_box = config.relative_box
                pixel_box = norm_box.to_pixel_bbox(w, h)

                # Associate intersecting OCR text tokens without altering original OCR data
                associated_texts: List[str] = []
                assoc_count = 0

                if ocr_regions:
                    for ocr_reg in ocr_regions:
                        raw_bbox = getattr(ocr_reg, "bbox", None)
                        text = getattr(ocr_reg, "text", "")
                        if not raw_bbox or not text:
                            continue

                        ocr_norm = NormalizedBBox.from_pixel_bbox(raw_bbox, w, h)
                        if norm_box.overlap_ratio(ocr_norm) >= 0.35 or ocr_norm.overlap_ratio(norm_box) >= 0.35:
                            associated_texts.append(text)
                            assoc_count += 1

                joined_text = " ".join(associated_texts) if associated_texts else None

                detected_regions.append(DocumentRegion(
                    region_type=config.region_type,
                    normalized_bbox=norm_box,
                    pixel_bbox=pixel_box,
                    confidence=0.92 if config.required else 0.85,
                    source="PROFILE_GEOMETRY",
                    side=side,
                    model_name=self._model_name,
                    model_version=self._version,
                    associated_text=joined_text,
                    associated_ocr_count=assoc_count,
                    metadata={"config_name": name, "required": config.required},
                ))

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return LayoutUnderstandingResult(
            regions=detected_regions,
            side=side,
            side_status=SideStatus.PROVIDED,
            image_width=w,
            image_height=h,
            model=model_info,
            latency_ms=latency_ms,
        )

    def _adapt_legacy_regions(self, legacy_dict: Dict[str, Any]) -> Dict[str, ExpectedRegionConfig]:
        """Convert legacy profile expected_regions dictionary to ExpectedRegionConfig objects."""
        adapted: Dict[str, ExpectedRegionConfig] = {}
        for name, spec in legacy_dict.items():
            if not isinstance(spec, dict):
                continue
            rx = spec.get("relative_x", 0.0)
            ry = spec.get("relative_y", 0.0)
            rw = spec.get("relative_w", 1.0)
            rh = spec.get("relative_h", 1.0)
            norm_box = NormalizedBBox(x=rx, y=ry, width=rw, height=rh)

            region_type = DocumentRegionType.UNKNOWN
            if "photo" in name or "portrait" in name:
                region_type = DocumentRegionType.PORTRAIT
            elif "mrz" in name:
                region_type = DocumentRegionType.MACHINE_READABLE
            elif "text" in name:
                region_type = DocumentRegionType.IDENTITY

            adapted[name] = ExpectedRegionConfig(
                region_type=region_type,
                expected=True,
                side="front",
                relative_box=norm_box,
            )
        return adapted
