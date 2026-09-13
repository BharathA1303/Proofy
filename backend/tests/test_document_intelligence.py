"""
tests/test_document_intelligence.py

Comprehensive Phase 4 Test Suite for M1 Document Intelligence:
  - Section 15.A: High-confidence DL classification (SUPPORTED)
  - Section 15.B: Non-DL document / type mismatch guard (UNSUPPORTED / is_mismatch)
  - Section 15.C: Low classifier confidence (LOW_CONFIDENCE on isolated signals)
  - Section 15.D: Model availability handling (MODEL_UNAVAILABLE on missing weights)
  - Section 15.E: Semantic layout regions returned with normalized bbox and confidence
  - Section 15.F: Profile-defined regions are strictly respected
  - Section 15.G: Pixel resolution changes -> normalized coordinates remain consistent
  - Section 15.H: Front-only DL -> front processed, back reports SIDE_NOT_PROVIDED
  - Section 15.I: Back-only DL -> back processed, front reports SIDE_NOT_PROVIDED
  - Section 15.J: OCR provenance remains intact and unmutated
  - Section 15.K: Existing DL parser works seamlessly with M1 outputs
  - Section 15.L: Existing Phase 2 ambiguity contract remains intact
  - Section 15.M: Existing Phase 3 normalization behavior remains intact
  - Security & Privacy: No raw image bytes or raw biometric embeddings in telemetry
  - Latency Telemetry: Tracks classifier, layout, OCR, and total latencies
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, List, Optional
import numpy as np
import pytest

from app.services.document_intelligence.schema import (
    ClassificationDecision,
    ClassificationModelInfo,
    DocumentClassificationResult,
    DocumentIntelligenceResult,
    DocumentRegion,
    DocumentRegionType,
    DocumentSide,
    ExpectedRegionConfig,
    LayoutUnderstandingResult,
    ModelStatus,
    NormalizedBBox,
    SideStatus,
)
from app.services.document_intelligence.classifier import (
    BaseDocumentClassifier,
    MockDocumentClassifier,
    MultiSignalDocumentClassifier,
    VisionModelClassifier,
)
from app.services.document_intelligence.layout_engine import GenericLayoutEngine
from app.services.document_intelligence.service import DocumentIntelligenceService
from app.services.documents.driving_license.dl_field_normalizer import (
    normalize_dl_date,
    normalize_license_number,
    normalize_vehicle_classes,
)
from app.services.documents.driving_license.dl_parser import (
    FieldStatus,
    parse_driving_license,
)
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)
from app.services.documents.profiles.driving_license_profile import DRIVING_LICENSE_PROFILE


# ── Test Helpers & Mocks ─────────────────────────────────────────────────────

@dataclass
class DummyOCRToken:
    """Mock OCR region mimicking paddleocr/surrogate OCR outputs."""
    text: str
    bbox: List[List[int]]
    confidence: float = 0.95
    line_num: int = 1
    page_num: int = 1


def create_mock_dl_image(width: int = 950, height: int = 600) -> np.ndarray:
    """Create a dummy BGR image representing standard CR80 driving license geometry (1.58 aspect ratio)."""
    return np.zeros((height, width, 3), dtype=np.uint8)


def get_typical_dl_ocr_tokens(w: int = 950, h: int = 600) -> List[DummyOCRToken]:
    """Generate realistic DL OCR tokens positioned within their canonical spatial zones."""
    return [
        DummyOCRToken(
            text="UNION OF INDIA DRIVING LICENCE",
            bbox=[[int(w * 0.10), int(h * 0.05)], [int(w * 0.85), int(h * 0.05)], [int(w * 0.85), int(h * 0.12)], [int(w * 0.10), int(h * 0.12)]],
            confidence=0.98,
        ),
        DummyOCRToken(
            text="DL NO: DL-0420230012345",
            bbox=[[int(w * 0.35), int(h * 0.15)], [int(w * 0.85), int(h * 0.15)], [int(w * 0.85), int(h * 0.22)], [int(w * 0.35), int(h * 0.22)]],
            confidence=0.97,
        ),
        DummyOCRToken(
            text="NAME: BHARATH A",
            bbox=[[int(w * 0.35), int(h * 0.28)], [int(w * 0.75), int(h * 0.28)], [int(w * 0.75), int(h * 0.34)], [int(w * 0.35), int(h * 0.34)]],
            confidence=0.96,
        ),
        DummyOCRToken(
            text="DOB: 13/03/2003",
            bbox=[[int(w * 0.35), int(h * 0.36)], [int(w * 0.65), int(h * 0.36)], [int(w * 0.65), int(h * 0.42)], [int(w * 0.35), int(h * 0.42)]],
            confidence=0.95,
        ),
        DummyOCRToken(
            text="COV: LMV MCWG",
            bbox=[[int(w * 0.10), int(h * 0.72)], [int(w * 0.50), int(h * 0.72)], [int(w * 0.50), int(h * 0.82)], [int(w * 0.10), int(h * 0.82)]],
            confidence=0.94,
        ),
    ]


# ── Section 15.A: High-Confidence DL Classification ──────────────────────────

class TestHighConfidenceDLClassification:
    """Verify high-confidence classification when genuine DL signals are present."""

    def test_high_confidence_dl_supported(self):
        classifier = MultiSignalDocumentClassifier()
        img = create_mock_dl_image(950, 600)  # Aspect ratio 1.583
        tokens = get_typical_dl_ocr_tokens(950, 600)

        result = classifier.classify(
            image_np=img,
            side="front",
            ocr_regions=tokens,
            declared_type="driving_license",
        )

        assert result.decision == ClassificationDecision.SUPPORTED
        assert result.document_type == "driving_license"
        assert result.confidence >= 0.75
        assert result.is_mismatch is False
        assert len(result.evidence) >= 2
        assert any("aspect ratio" in ev.lower() for ev in result.evidence)
        assert any("title pattern" in ev.lower() for ev in result.evidence)

    def test_mock_classifier_returns_specified_result(self):
        mock_cls = MockDocumentClassifier(
            default_type="driving_license",
            default_confidence=0.94,
            default_decision=ClassificationDecision.SUPPORTED,
        )
        res = mock_cls.classify(image_np=None)
        assert res.document_type == "driving_license"
        assert res.confidence == 0.94
        assert res.decision == ClassificationDecision.SUPPORTED


# ── Section 15.B: Non-DL Document Rejection (Type Mismatch) ───────────────────

class TestNonDLDocumentMismatch:
    """Verify that foreign documents (Passport, Visa) in DL section are rejected with mismatch."""

    def test_passport_in_dl_section_rejected(self):
        classifier = MultiSignalDocumentClassifier()
        passport_tokens = [
            DummyOCRToken(text="REPUBLIC OF INDIA PASSPORT", bbox=[[50, 50], [400, 50], [400, 100], [50, 100]]),
            DummyOCRToken(text="P<INDSHARMA<<AARAV<<<<<<<<<<<<<<<<<<<", bbox=[[50, 500], [800, 500], [800, 550], [50, 550]]),
        ]

        result = classifier.classify(
            image_np=None,
            side="front",
            ocr_regions=passport_tokens,
            declared_type="driving_license",
        )

        assert result.decision == ClassificationDecision.UNSUPPORTED
        assert result.document_type == "passport"
        assert result.is_mismatch is True
        assert result.error_message is not None
        assert "DOCUMENT TYPE MISMATCH" in result.error_message
        assert "Passport" in result.error_message

    def test_visa_in_dl_section_rejected(self):
        classifier = MultiSignalDocumentClassifier()
        visa_tokens = [
            DummyOCRToken(text="OFFICIAL ENTRY VISA BORDER CONTROL IMMIGRATION", bbox=[[50, 50], [400, 50], [400, 100], [50, 100]]),
            DummyOCRToken(text="VISA NUMBER: V1002003", bbox=[[50, 150], [300, 150], [300, 200], [50, 200]]),
        ]

        result = classifier.classify(
            image_np=None,
            side="front",
            ocr_regions=visa_tokens,
            declared_type="driving_license",
        )

        assert result.decision == ClassificationDecision.UNSUPPORTED
        assert result.document_type == "visa"
        assert result.is_mismatch is True
        assert result.error_message is not None
        assert "DOCUMENT TYPE MISMATCH" in result.error_message


# ── Section 15.C: Low Classifier Confidence & No Single Word Triggers ─────────

class TestLowConfidenceClassification:
    """Verify that ambiguous or single bare-word inputs produce LOW_CONFIDENCE, not false positive."""

    def test_single_bare_word_driving_is_insufficient(self):
        classifier = MultiSignalDocumentClassifier()
        # Only single isolated word "DRIVING" with square non-card aspect ratio
        square_img = np.zeros((500, 500, 3), dtype=np.uint8)  # aspect ratio 1.0 (not CR80)
        sparse_tokens = [DummyOCRToken(text="DRIVING ONLY", bbox=[[10, 10], [100, 10], [100, 30], [10, 30]])]

        result = classifier.classify(
            image_np=square_img,
            side="front",
            ocr_regions=sparse_tokens,
            declared_type="driving_license",
        )

        # Single ambiguous trigger cannot reach SUPPORTED
        assert result.decision in (ClassificationDecision.LOW_CONFIDENCE, ClassificationDecision.UNKNOWN)
        assert result.confidence < 0.70

    def test_completely_irrelevant_document_returns_unknown(self):
        classifier = MultiSignalDocumentClassifier()
        tokens = [DummyOCRToken(text="SUPERMARKET GROCERY RECEIPT TOTAL $45.00", bbox=[[10, 10], [200, 10], [200, 50], [10, 50]])]

        result = classifier.classify(
            image_np=None,
            side="front",
            ocr_regions=tokens,
            declared_type="driving_license",
        )

        assert result.decision == ClassificationDecision.UNKNOWN
        assert result.confidence <= 0.20


# ── Section 15.D: Model Availability Handling ─────────────────────────────────

class TestModelAvailabilityHandling:
    """Verify that missing model weights strictly yield MODEL_UNAVAILABLE without fabricating numbers."""

    def test_vision_model_reports_unavailable_when_weights_missing(self):
        vm = VisionModelClassifier(weights_path="/nonexistent/path/weights.onnx")
        assert vm.is_model_available() is False
        assert vm.get_model_status() == ModelStatus.MODEL_UNAVAILABLE

        res = vm.classify(image_np=None)
        assert res.model.status == ModelStatus.MODEL_UNAVAILABLE
        assert res.confidence == 0.0
        assert res.decision == ClassificationDecision.UNKNOWN

    def test_generic_layout_engine_reports_unavailable_when_weights_missing(self):
        le = GenericLayoutEngine(weights_path="/nonexistent/path/layout.onnx")
        assert le.is_model_available() is False
        assert le.get_model_status() == ModelStatus.MODEL_UNAVAILABLE


# ── Section 15.E & 15.F: Semantic Document Regions & Profile Respect ─────────

class TestSemanticDocumentRegions:
    """Verify semantic layout region extraction and strict respect for DocumentProfile."""

    def test_dl_layout_regions_extracted(self):
        layout_engine = GenericLayoutEngine()
        img = create_mock_dl_image(950, 600)
        tokens = get_typical_dl_ocr_tokens(950, 600)

        result = layout_engine.understand_layout(
            image_np=img,
            profile=DRIVING_LICENSE_PROFILE,
            side="front",
            ocr_regions=tokens,
        )

        assert result.side == "front"
        assert result.side_status == SideStatus.PROVIDED
        assert len(result.regions) >= 6

        # Check for essential semantic region types
        reg_types = {r.region_type for r in result.regions}
        assert DocumentRegionType.CARD_BOUNDARY in reg_types
        assert DocumentRegionType.LICENSE_NUMBER in reg_types
        assert DocumentRegionType.IDENTITY in reg_types
        assert DocumentRegionType.VALIDITY in reg_types
        assert DocumentRegionType.AUTHORITY in reg_types
        assert DocumentRegionType.VEHICLE_CLASS in reg_types

        # Verify all regions have valid resolution-independent NormalizedBBox
        for reg in result.regions:
            assert reg.normalized_bbox is not None
            assert 0.0 <= reg.normalized_bbox.x <= 1.0
            assert 0.0 <= reg.normalized_bbox.y <= 1.0
            assert 0.0 <= reg.normalized_bbox.width <= 1.0
            assert 0.0 <= reg.normalized_bbox.height <= 1.0
            assert reg.confidence > 0.0
            assert reg.side == "front"

    def test_custom_profile_regions_are_respected(self):
        custom_profile = DocumentProfile(
            document_type="custom_card",
            display_name="Custom Card",
            expected_semantic_regions={
                "custom_sec": ExpectedRegionConfig(
                    region_type=DocumentRegionType.SECURITY,
                    side="front",
                    relative_box=NormalizedBBox(0.80, 0.10, 0.15, 0.20),
                    required=True,
                )
            }
        )
        layout_engine = GenericLayoutEngine()
        img = create_mock_dl_image(800, 500)

        result = layout_engine.understand_layout(
            image_np=img,
            profile=custom_profile,
            side="front",
        )

        reg_types = {r.region_type for r in result.regions}
        assert DocumentRegionType.SECURITY in reg_types
        # Regions not declared in custom_profile should NOT be present
        assert DocumentRegionType.LICENSE_NUMBER not in reg_types


# ── Section 15.G: Pixel Resolution Invariance ────────────────────────────────

class TestResolutionInvariance:
    """Verify that changing image resolution keeps NormalizedBBox coordinates identical."""

    def test_normalized_bbox_invariant_across_resolutions(self):
        layout_engine = GenericLayoutEngine()

        img_std = create_mock_dl_image(950, 600)
        img_2x = create_mock_dl_image(1900, 1200)

        res_std = layout_engine.understand_layout(img_std, profile=DRIVING_LICENSE_PROFILE, side="front")
        res_2x = layout_engine.understand_layout(img_2x, profile=DRIVING_LICENSE_PROFILE, side="front")

        # Compare regions
        std_dict = {r.region_type: r.normalized_bbox for r in res_std.regions}
        hi_dict = {r.region_type: r.normalized_bbox for r in res_2x.regions}

        assert set(std_dict.keys()) == set(hi_dict.keys())
        for rtype, bbox_std in std_dict.items():
            bbox_hi = hi_dict[rtype]
            assert bbox_std.x == bbox_hi.x
            assert bbox_std.y == bbox_hi.y
            assert bbox_std.width == bbox_hi.width
            assert bbox_std.height == bbox_hi.height

        # Verify pixel bbox scales proportionally
        std_card = res_std.get_region(DocumentRegionType.CARD_BOUNDARY)
        hi_card = res_2x.get_region(DocumentRegionType.CARD_BOUNDARY)
        assert std_card.pixel_bbox == [[0, 0], [950, 0], [950, 600], [0, 600]]
        assert hi_card.pixel_bbox == [[0, 0], [1900, 0], [1900, 1200], [0, 1200]]


# ── Section 15.H & 15.I: Multi-Side Handling (Front vs Back) ─────────────────

class TestMultiSideHandling:
    """Verify front vs back side handling and SIDE_NOT_PROVIDED behavior."""

    def test_front_only_dl_leaves_back_side_not_provided(self):
        layout_engine = GenericLayoutEngine()
        img_front = create_mock_dl_image(950, 600)

        # Front processed
        res_front = layout_engine.understand_layout(img_front, DRIVING_LICENSE_PROFILE, side="front")
        assert res_front.side_status == SideStatus.PROVIDED
        assert len(res_front.regions) > 0

        # Back missing
        res_back = layout_engine.understand_layout(None, DRIVING_LICENSE_PROFILE, side="back")
        assert res_back.side_status == SideStatus.SIDE_NOT_PROVIDED
        assert len(res_back.regions) == 0

    def test_back_only_dl_extracts_back_regions_and_leaves_front_not_provided(self):
        layout_engine = GenericLayoutEngine()
        img_back = create_mock_dl_image(950, 600)

        # Front missing
        res_front = layout_engine.understand_layout(None, DRIVING_LICENSE_PROFILE, side="front")
        assert res_front.side_status == SideStatus.SIDE_NOT_PROVIDED
        assert len(res_front.regions) == 0

        # Back provided -> QR region (side="back") and ADDRESS (side="any") should appear
        res_back = layout_engine.understand_layout(img_back, DRIVING_LICENSE_PROFILE, side="back")
        assert res_back.side_status == SideStatus.PROVIDED
        back_types = {r.region_type for r in res_back.regions}
        assert DocumentRegionType.QR in back_types
        assert DocumentRegionType.ADDRESS in back_types
        # Front-only regions like PORTRAIT or LICENSE_NUMBER must not appear on back
        assert DocumentRegionType.PORTRAIT not in back_types
        assert DocumentRegionType.LICENSE_NUMBER not in back_types


# ── Section 15.J: OCR Provenance Preservation ────────────────────────────────

class TestOCRProvenancePreservation:
    """Verify that associating OCR tokens with semantic regions does not mutate raw OCR objects."""

    def test_raw_ocr_tokens_remain_unmutated(self):
        layout_engine = GenericLayoutEngine()
        img = create_mock_dl_image(950, 600)
        original_tokens = get_typical_dl_ocr_tokens(950, 600)
        tokens_copy = copy.deepcopy(original_tokens)

        result = layout_engine.understand_layout(
            image_np=img,
            profile=DRIVING_LICENSE_PROFILE,
            side="front",
            ocr_regions=original_tokens,
        )

        # Confirm tokens were linked
        lic_region = result.get_region(DocumentRegionType.LICENSE_NUMBER)
        assert lic_region is not None
        assert lic_region.associated_text is not None
        assert "DL-0420230012345" in lic_region.associated_text
        assert lic_region.associated_ocr_count >= 1

        # Confirm original tokens were NOT mutated
        for orig, cloned in zip(original_tokens, tokens_copy):
            assert orig.text == cloned.text
            assert orig.bbox == cloned.bbox
            assert orig.confidence == cloned.confidence
            assert orig.line_num == cloned.line_num


# ── Section 15.K, 15.L & 15.M: Regressions (Parser, Ambiguity, Normalizer) ────

class TestDownstreamRegressions:
    """Verify DL Parser (Phase 2) and DL Normalizer (Phase 3) work seamlessly with M1 outputs."""

    def test_dl_parser_works_with_intelligence_service_output(self):
        service = DocumentIntelligenceService()
        tokens = get_typical_dl_ocr_tokens(950, 600)
        img = create_mock_dl_image(950, 600)

        # Run M1 Document Intelligence
        m1_result = service.process_document(
            front_image=img,
            raw_ocr_regions=tokens,
            declared_type="driving_license",
            target_profile=DRIVING_LICENSE_PROFILE,
        )

        assert m1_result.classification.decision == ClassificationDecision.SUPPORTED
        assert m1_result.layout.side_status == SideStatus.PROVIDED

        # Pass M1 OCR regions to Phase 2 parse_driving_license
        parsed = parse_driving_license(m1_result.ocr_regions)

        assert parsed.license_number.value == "DL0420230012345"
        assert parsed.name.value == "BHARATH A"
        assert parsed.dob.value == "2003-03-13"

    def test_phase_2_ambiguity_behavior_intact(self):
        """Phase 2 ambiguity flagging should still trigger when competing candidates exist."""
        ambiguous_tokens = [
            DummyOCRToken(text="DL NO: DL-0420230012345", bbox=[[0, 0], [100, 0], [100, 20], [0, 20]]),
            DummyOCRToken(text="OLD DL: DL-0520210099999", bbox=[[0, 30], [100, 30], [100, 50], [0, 50]]),
            DummyOCRToken(text="NAME: BHARATH A", bbox=[[0, 60], [100, 60], [100, 80], [0, 80]]),
        ]
        parsed = parse_driving_license(ambiguous_tokens)
        assert parsed.license_number.status == FieldStatus.AMBIGUOUS
        assert len(parsed.license_number.candidates) >= 2

    def test_phase_3_normalization_behavior_intact(self):
        """Phase 3 normalization rules must remain completely intact."""
        # License number
        res_dl = normalize_license_number("dl - 04 2023 0012345")
        assert res_dl == "DL0420230012345"

        # Date normalization
        res_dob = normalize_dl_date("13-MAR-2003")
        assert res_dob == "2003-03-13"

        # Vehicle classes
        res_cov = normalize_vehicle_classes("LMV, MCWG, TRANS")
        assert "LMV" in res_cov
        assert "MCWG" in res_cov
        assert "TRANS" in res_cov


# ── Security & Privacy Guarantees ─────────────────────────────────────────────

class TestSecurityAndPrivacy:
    """Verify no raw image bytes, embeddings, or unredacted PII leaks in serialization/telemetry."""

    def test_serialization_contains_no_raw_images_or_embeddings(self):
        service = DocumentIntelligenceService()
        tokens = get_typical_dl_ocr_tokens(950, 600)
        img = create_mock_dl_image(950, 600)

        m1_result = service.process_document(
            front_image=img,
            raw_ocr_regions=tokens,
            declared_type="driving_license",
            target_profile=DRIVING_LICENSE_PROFILE,
        )

        data = m1_result.to_dict()

        # Convert entire serialized dictionary to string
        dump = str(data)

        # Must not contain large binary or raw numpy representation
        assert "ndarray" not in dump
        assert "data:image" not in dump
        assert "embedding" not in dump
        assert "vector" not in dump

        # Telemetry must contain latency numbers
        assert "telemetry" in data
        assert "classifier_latency_ms" in data["telemetry"]
        assert "layout_latency_ms" in data["telemetry"]
        assert "total_latency_ms" in data["telemetry"]
        assert data["telemetry"]["total_latency_ms"] >= 0.0
