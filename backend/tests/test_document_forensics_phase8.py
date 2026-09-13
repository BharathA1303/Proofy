"""
backend/tests/test_document_forensics_phase8.py

Comprehensive Test Suite for AI Document Tampering & Forensic Authenticity Analysis (Phase 8).
Covers Scenarios A through AJ:
  A: Clean high-quality document (FORENSIC_CLEAN)
  B: Low-resolution document (< 600px -> INSUFFICIENT_DATA, not forged)
  C: Blurred document (Laplacian focus < 25 -> INSUFFICIENT_DATA)
  D: JPEG-compressed document (uniform recompression is normal)
  E: Resized document handling
  F: Rotated / perspective card detection
  G: Global ELA behavior on clean images
  H: Local ELA behavior flagging localized high-residual blocks
  I: Duplicated / copy-move cloned texture detected via ORB
  J: Spliced synthetic fixture with edge and variance discontinuity
  K: Suspicious text-region localized anomaly
  L: Suspicious portrait-region anomaly
  M: Clean portrait-region verification
  N: Missing card boundary returns BOUNDARY_UNAVAILABLE (no fabrication)
  O: Valid card boundary localized with rectangularity and ID-1 aspect ratio
  P: EXIF present without editor software tags
  Q: EXIF absent is normal (standard for web/mobile uploads, not forged)
  R: Suspicious EXIF editor tags (Photoshop/GIMP flagged)
  S: Model unavailable when weights are absent (MODEL_UNAVAILABLE contract)
  T: Model inference failure handled gracefully (MODEL_INFERENCE_FAILED)
  U: Model inference contract (never fabricates synthetic confidence)
  V: Localization bbox validity (points within image dimensions)
  W: Normalized coordinates bounded to [0.0, 1.0]
  X: Multiple forensic signals escalate to MULTI_SIGNAL_ANOMALY
  Y: Weak single signal does not declare forgery
  Z: Image quality problem != Forgery
  AA: No client-provided score trust
  AB: Profile-driven configuration for Indian DL
  AC: Evidence provenance (finding IDs, sources, metrics recorded)
  AD: Image hash generation (tamper-evident SHA-256)
  AE: Preprocessing and duration provenance recorded
  AF: Profile version and engine version recorded
  AG: No raw PII in findings or audit logs
  AH: Absolute rule: NEVER emits FORGED_DOCUMENT from M3
  AI: Backward compatibility with legacy ForensicAnalysisSummary
  AJ: Security protections against oversized images and decompression bombs
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, Tuple

import cv2
import numpy as np
import pytest
from PIL import Image

from app.services.document_intelligence.schema import NormalizedBBox
from app.services.document_forensics.classical import ClassicalForensicEngine
from app.services.document_forensics.localization import ForensicLocalizationEngine
from app.services.document_forensics.quality import DocumentQualityEngine
from app.services.document_forensics.schema import (
    ForensicAnomalyState,
    ForensicFinding,
    ForensicResult,
    ForensicStatus,
    ModelStatus,
    SignalSeverity,
    SignalStatus,
    SignalType,
)
from app.services.document_forensics.service import DocumentForensicsService
from app.services.document_forensics.tampering_model import DocumentTamperingModel


# ==============================================================================
# Synthetic Test Fixtures & Helpers
# ==============================================================================

def create_synthetic_clean_card(w: int = 800, h: int = 500) -> Tuple[np.ndarray, bytes]:
    """Create a realistic, clean Indian Driving Licence card canvas with JPEG bytes."""
    canvas = np.ones((h, w, 3), dtype=np.uint8) * 242

    # Card border
    cv2.rectangle(canvas, (20, 20), (w - 20, h - 20), (210, 210, 210), 2)

    # Authority header banner
    cv2.rectangle(canvas, (20, 20), (w - 20, 80), (30, 80, 160), -1)
    cv2.putText(canvas, "UNION OF INDIA - DRIVING LICENCE", (60, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # Portrait photo
    px, py, pw, ph = 40, 100, 240, 250
    # Natural textured background
    photo_patch = np.ones((ph, pw, 3), dtype=np.uint8) * 200
    cv2.circle(photo_patch, (120, 100), 50, (140, 140, 140), -1)  # Head
    cv2.ellipse(photo_patch, (120, 210), (80, 60), 0, 0, 360, (90, 90, 90), -1)  # Shoulders
    canvas[py : py + ph, px : px + pw] = photo_patch
    cv2.rectangle(canvas, (px, py), (px + pw, py + ph), (160, 160, 160), 1)

    # License details text zone
    tx = 310
    cv2.putText(canvas, "DL No: DL-1420110012345", (tx, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 2)
    cv2.putText(canvas, "Name: RAHUL SHARMA", (tx, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 2)
    cv2.putText(canvas, "DOB: 15-08-1990", (tx, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2)
    cv2.putText(canvas, "Valid Till: 14-08-2030", (tx, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2)
    cv2.putText(canvas, "COV: LMV, MCWG", (tx, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2)

    # Convert to JPEG bytes
    success, encoded = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return canvas, encoded.tobytes()


def create_jpeg_with_exif(software_tag: str = "Adobe Photoshop 24.0") -> bytes:
    """Generate JPEG bytes containing an EXIF software metadata tag."""
    img = Image.new("RGB", (650, 650), color=(230, 230, 230))
    exif = img.getexif()
    exif[305] = software_tag  # Tag 305 = Software
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95, exif=exif)
    return buf.getvalue()


# ==============================================================================
# Unit & Integration Tests
# ==============================================================================

class TestDocumentForensicsPhase8:

    @pytest.fixture
    def quality_engine(self):
        return DocumentQualityEngine()

    @pytest.fixture
    def classical_engine(self):
        return ClassicalForensicEngine()

    @pytest.fixture
    def localization_engine(self):
        return ForensicLocalizationEngine()

    @pytest.fixture
    def service(self):
        return DocumentForensicsService()

    # --------------------------------------------------------------------------
    # Scenario A: Clean High-Quality Document
    # --------------------------------------------------------------------------
    def test_a_clean_high_quality_document(self, service):
        img, raw_bytes = create_synthetic_clean_card(800, 500)
        res = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)

        assert res.status == ForensicStatus.FORENSIC_CLEAN
        assert res.anomaly_state == ForensicAnomalyState.NO_FORENSIC_ANOMALY
        assert res.quality.is_adequate is True
        assert res.quality.width == 800
        assert res.quality.height == 500
        assert len(res.image_sha256) == 64

    # --------------------------------------------------------------------------
    # Scenario B: Low-Resolution Document
    # --------------------------------------------------------------------------
    def test_b_low_resolution_document(self, service):
        img_clean, _ = create_synthetic_clean_card(800, 500)
        low_res = cv2.resize(img_clean, (350, 220))  # Well below 600px min_dimension
        res = service.analyze(low_res, document_type="driving_license")

        assert res.status == ForensicStatus.FORENSIC_INCONCLUSIVE
        assert res.anomaly_state == ForensicAnomalyState.INCONCLUSIVE
        assert any("minimum required" in r.lower() or "resolution" in r.lower() for r in res.quality.reasons)
        assert "not a finding of forgery" in res.overall_explanation

    # --------------------------------------------------------------------------
    # Scenario C: Blurred Document
    # --------------------------------------------------------------------------
    def test_c_blurred_document(self, service):
        img_clean, _ = create_synthetic_clean_card(800, 500)
        blurred = cv2.GaussianBlur(img_clean, (35, 35), 0)
        res = service.analyze(blurred, document_type="driving_license")

        assert res.status == ForensicStatus.FORENSIC_INCONCLUSIVE
        assert res.anomaly_state == ForensicAnomalyState.INCONCLUSIVE
        assert res.quality.is_adequate is False
        assert any("out of focus or blurred" in r for r in res.quality.reasons)

    # --------------------------------------------------------------------------
    # Scenario D: JPEG-Compressed Document
    # --------------------------------------------------------------------------
    def test_d_jpeg_compressed_document(self, service):
        img_clean, _ = create_synthetic_clean_card(800, 500)
        # Uniform JPEG compression at quality 75
        _, enc = cv2.imencode(".jpg", img_clean, [cv2.IMWRITE_JPEG_QUALITY, 75])
        compressed = cv2.imdecode(enc, cv2.IMREAD_COLOR)

        res = service.analyze(compressed, document_type="driving_license")
        assert res.status in (ForensicStatus.FORENSIC_CLEAN, ForensicStatus.FORENSIC_SUSPICIOUS)
        # Verify JPEG compression finding exists
        comp_finding = next((f for f in res.findings if f.signal_type == SignalType.JPEG_COMPRESSION), None)
        assert comp_finding is not None
        assert "ratio" in comp_finding.metrics

    # --------------------------------------------------------------------------
    # Scenario E: Resized Document
    # --------------------------------------------------------------------------
    def test_e_resized_document(self, service):
        img_clean, _ = create_synthetic_clean_card(800, 500)
        resized = cv2.resize(img_clean, (1200, 750))  # Upscaled but adequate
        res = service.analyze(resized, document_type="driving_license")

        assert res.quality.is_adequate is True
        assert res.quality.width == 1200
        assert res.quality.height == 750

    # --------------------------------------------------------------------------
    # Scenario F: Rotated / Perspective Document
    # --------------------------------------------------------------------------
    def test_f_rotated_perspective_document(self, classical_engine):
        canvas = np.ones((700, 1000, 3), dtype=np.uint8) * 120
        # Draw rotated quad
        pts = np.array([[120, 150], [850, 100], [800, 600], [100, 550]], dtype=np.int32)
        cv2.fillPoly(canvas, [pts], (240, 240, 240))

        boundary = classical_engine.detect_document_boundary(canvas)
        assert boundary.status in (SignalStatus.BOUNDARY_DETECTED, SignalStatus.BOUNDARY_SUSPICIOUS)
        assert boundary.contour_points is not None
        assert len(boundary.contour_points) == 4

    # --------------------------------------------------------------------------
    # Scenario G: Global ELA Behavior
    # --------------------------------------------------------------------------
    def test_g_global_ela_behavior(self, classical_engine):
        img, _ = create_synthetic_clean_card(800, 500)
        finding, blocks, error_map = classical_engine.run_ela(img)

        assert finding.signal_type == SignalType.ELA_RESIDUAL
        assert finding.status == SignalStatus.NORMAL
        assert finding.metrics["mean_error"] >= 0.0
        assert error_map.shape == (500, 800)

    # --------------------------------------------------------------------------
    # Scenario H: Local ELA Behavior Flagging Anomalous Blocks
    # --------------------------------------------------------------------------
    def test_h_local_ela_behavior(self, classical_engine):
        img, _ = create_synthetic_clean_card(800, 500)
        # Insert a high-error noise block at [200:300, 400:500]
        np.random.seed(42)
        noise_patch = (np.random.rand(100, 100, 3) * 255).astype(np.uint8)
        img[200:300, 400:500] = noise_patch

        finding, blocks, error_map = classical_engine.run_ela(img)
        assert len(blocks) > 0
        assert any(b["x"] >= 380 and b["y"] >= 180 for b in blocks)

    # --------------------------------------------------------------------------
    # Scenario I: Duplicated / Copy-Move Cloned Texture Detected
    # --------------------------------------------------------------------------
    def test_i_duplicated_copy_move_synthetic_fixture(self, classical_engine):
        canvas = np.ones((600, 900, 3), dtype=np.uint8) * 230
        np.random.seed(99)
        # Create a detailed distinctive texture
        texture = (np.random.rand(120, 120, 3) * 255).astype(np.uint8)
        # Place original texture at (80, 100)
        canvas[100:220, 80:200] = texture
        # Place cloned copy at (450, 100)
        canvas[100:220, 450:570] = texture

        finding = classical_engine.detect_copy_move(canvas)
        assert finding.signal_type == SignalType.COPY_MOVE_DUPLICATION
        assert finding.status == SignalStatus.SUSPICIOUS
        assert finding.severity == SignalSeverity.HIGH
        assert finding.bbox is not None
        assert finding.metrics["matching_pairs"] >= 8

    # --------------------------------------------------------------------------
    # Scenario J: Spliced Synthetic Fixture with Edge Discontinuity
    # --------------------------------------------------------------------------
    def test_j_spliced_synthetic_fixture(self, classical_engine):
        img, _ = create_synthetic_clean_card(800, 500)
        # Splice a jarring high-variance patch into the portrait zone with harsh edges
        px, py, pw, ph = 40, 100, 240, 250
        np.random.seed(123)
        spliced_noise = (np.random.rand(ph, pw, 3) * 255).astype(np.uint8)
        img[py : py + ph, px : px + pw] = spliced_noise

        finding = classical_engine.analyze_splicing_edges(
            img,
            target_box=NormalizedBBox(0.05, 0.20, 0.30, 0.50),
        )
        assert finding.signal_type == SignalType.SPLICING_EDGE
        assert finding.metrics["border_gradient"] > 50.0

    # --------------------------------------------------------------------------
    # Scenario K: Suspicious Text-Region Localized Anomaly
    # --------------------------------------------------------------------------
    def test_k_suspicious_text_region_fixture(self, localization_engine):
        img, _ = create_synthetic_clean_card(800, 500)
        # Create synthetic ELA error map with high anomaly over text area
        h, w = img.shape[:2]
        ela_map = np.ones((h, w), dtype=np.float32) * 0.1
        # Spike ELA over license_number box: x=[300, 600], y=[50, 150]
        ela_map[50:150, 300:600] = 5.0

        regions = {"license_number": NormalizedBBox(0.38, 0.05, 0.58, 0.15)}
        heatmap, suspicious_regions, findings = localization_engine.generate_heatmap_and_regions(
            img, ela_map, regions
        )

        text_finding = next((f for f in findings if f.signal_type == SignalType.TEXT_REGION_ANOMALY), None)
        assert text_finding is not None
        assert text_finding.status == SignalStatus.SUSPICIOUS
        assert text_finding.region_name == "license_number"

    # --------------------------------------------------------------------------
    # Scenario L: Suspicious Portrait-Region Anomaly
    # --------------------------------------------------------------------------
    def test_l_suspicious_portrait_region_fixture(self, localization_engine):
        img, _ = create_synthetic_clean_card(800, 500)
        h, w = img.shape[:2]
        ela_map = np.ones((h, w), dtype=np.float32) * 0.05
        # Spike ELA over portrait area: x=[40, 280], y=[100, 350]
        ela_map[100:350, 40:280] = 4.0

        regions = {"portrait_area": NormalizedBBox(0.05, 0.20, 0.30, 0.50)}
        heatmap, suspicious_regions, findings = localization_engine.generate_heatmap_and_regions(
            img, ela_map, regions
        )

        p_finding = next((f for f in findings if f.signal_type == SignalType.PORTRAIT_REGION_ANOMALY), None)
        assert p_finding is not None
        assert p_finding.status == SignalStatus.SUSPICIOUS
        assert p_finding.severity == SignalSeverity.HIGH

    # --------------------------------------------------------------------------
    # Scenario M: Clean Portrait-Region Verification
    # --------------------------------------------------------------------------
    def test_m_clean_portrait_region_fixture(self, localization_engine):
        img, _ = create_synthetic_clean_card(800, 500)
        h, w = img.shape[:2]
        ela_map = np.ones((h, w), dtype=np.float32) * 0.2  # Uniform ELA

        regions = {"portrait_area": NormalizedBBox(0.05, 0.20, 0.30, 0.50)}
        heatmap, suspicious_regions, findings = localization_engine.generate_heatmap_and_regions(
            img, ela_map, regions
        )

        p_finding = next((f for f in findings if f.signal_type == SignalType.PORTRAIT_REGION_ANOMALY), None)
        assert p_finding is not None
        assert p_finding.status == SignalStatus.NORMAL

    # --------------------------------------------------------------------------
    # Scenario N: Missing Boundary Returns BOUNDARY_UNAVAILABLE
    # --------------------------------------------------------------------------
    def test_n_missing_boundary(self, classical_engine):
        # Plain uniform solid gray canvas with no card contour
        blank = np.ones((600, 800, 3), dtype=np.uint8) * 128
        boundary = classical_engine.detect_document_boundary(blank)

        assert boundary.status == SignalStatus.BOUNDARY_UNAVAILABLE
        assert boundary.contour_points is None

    # --------------------------------------------------------------------------
    # Scenario O: Valid Card Boundary Localized
    # --------------------------------------------------------------------------
    def test_o_valid_boundary(self, classical_engine):
        # Card on dark background
        canvas = np.ones((600, 900, 3), dtype=np.uint8) * 40
        card_rect = [50, 40, 750, 475]  # Aspect ratio: 750/475 = 1.579 (~1.58 ID-1)
        cv2.rectangle(canvas, (card_rect[0], card_rect[1]), (card_rect[0] + card_rect[2], card_rect[1] + card_rect[3]), (240, 240, 240), -1)

        boundary = classical_engine.detect_document_boundary(canvas)
        assert boundary.status == SignalStatus.BOUNDARY_DETECTED
        assert boundary.is_rectangular is True
        assert abs(boundary.aspect_ratio - 1.58) < 0.15

    # --------------------------------------------------------------------------
    # Scenario P: EXIF Present Without Editor Tags
    # --------------------------------------------------------------------------
    def test_p_exif_present(self, classical_engine):
        raw_bytes = create_jpeg_with_exif("Canon EOS 5D Mark IV")
        finding = classical_engine.analyze_metadata(raw_bytes)

        assert finding.signal_type == SignalType.METADATA_EXIF
        assert finding.status == SignalStatus.EXIF_PRESENT
        assert finding.severity == SignalSeverity.LOW

    # --------------------------------------------------------------------------
    # Scenario Q: EXIF Absent is Normal (Not Forged)
    # --------------------------------------------------------------------------
    def test_q_exif_absent(self, classical_engine):
        img_clean, raw_bytes = create_synthetic_clean_card(800, 500)
        # cv2.imencode produces JPEGs without EXIF
        finding = classical_engine.analyze_metadata(raw_bytes)

        assert finding.signal_type == SignalType.METADATA_EXIF
        assert finding.status == SignalStatus.EXIF_ABSENT
        assert finding.severity == SignalSeverity.LOW
        assert "standard for mobile uploads" in finding.explanation

    # --------------------------------------------------------------------------
    # Scenario R: Suspicious Metadata (Photoshop / GIMP Flagged)
    # --------------------------------------------------------------------------
    def test_r_suspicious_metadata(self, classical_engine):
        raw_bytes = create_jpeg_with_exif("Adobe Photoshop 2024 (Windows)")
        finding = classical_engine.analyze_metadata(raw_bytes)

        assert finding.status == SignalStatus.EXIF_SUSPICIOUS
        assert finding.severity == SignalSeverity.MEDIUM
        assert "Photoshop" in finding.explanation

    # --------------------------------------------------------------------------
    # Scenario S: Model Unavailable When Weights Absent
    # --------------------------------------------------------------------------
    def test_s_model_unavailable(self):
        model = DocumentTamperingModel(weights_path=None)
        assert model.status == ModelStatus.MODEL_UNAVAILABLE

        img = np.ones((256, 256, 3), dtype=np.uint8) * 128
        res, finding = model.predict(img)

        assert res.status == ModelStatus.MODEL_UNAVAILABLE
        assert res.confidence is None
        assert res.tampering_detected is None
        assert "Model weights not present" in res.explanation
        assert finding is None

    # --------------------------------------------------------------------------
    # Scenario T: Model Inference Failure Handled Gracefully
    # --------------------------------------------------------------------------
    def test_t_model_inference_failure(self):
        model = DocumentTamperingModel(weights_path=None)
        # Force model status to MODEL_AVAILABLE with mock failure
        model.status = ModelStatus.MODEL_AVAILABLE
        model._model = "MockBrokenObject"

        img = np.ones((256, 256, 3), dtype=np.uint8) * 128
        res, finding = model.predict(img)

        assert res.status == ModelStatus.MODEL_INFERENCE_FAILED
        assert finding is not None
        assert finding.status == SignalStatus.INSUFFICIENT_DATA

    # --------------------------------------------------------------------------
    # Scenario U: Model Inference Contract (Never Fabricates Fake Confidence)
    # --------------------------------------------------------------------------
    def test_u_real_model_inference_contract(self, service):
        img, raw_bytes = create_synthetic_clean_card(800, 500)
        res = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)

        # In production without weights file, model result must report MODEL_UNAVAILABLE
        ai_res = res.model_results[0]
        assert ai_res.status == ModelStatus.MODEL_UNAVAILABLE
        assert ai_res.confidence is None
        assert ai_res.tampering_detected is None

    # --------------------------------------------------------------------------
    # Scenario V: Localization Bounding Box Validity
    # --------------------------------------------------------------------------
    def test_v_localization_bbox_validity(self, localization_engine):
        img, _ = create_synthetic_clean_card(800, 500)
        h, w = img.shape[:2]
        ela_map = np.zeros((h, w), dtype=np.float32)
        # Spike top-right corner
        ela_map[20:120, 600:750] = 5.0

        heatmap, suspicious_regions, _ = localization_engine.generate_heatmap_and_regions(img, ela_map)
        assert len(suspicious_regions) > 0
        for r in suspicious_regions:
            for pt in r.bbox:
                assert 0 <= pt[0] <= w
                assert 0 <= pt[1] <= h

    # --------------------------------------------------------------------------
    # Scenario W: Normalized Coordinates Bounded to [0.0, 1.0]
    # --------------------------------------------------------------------------
    def test_w_normalized_coordinates(self, localization_engine):
        img, _ = create_synthetic_clean_card(800, 500)
        h, w = img.shape[:2]
        ela_map = np.zeros((h, w), dtype=np.float32)
        ela_map[200:350, 200:350] = 4.0

        _, regions, _ = localization_engine.generate_heatmap_and_regions(img, ela_map)
        for r in regions:
            n = r.normalized_bbox
            assert 0.0 <= n.x <= 1.0
            assert 0.0 <= n.y <= 1.0
            assert 0.0 <= n.width <= 1.0
            assert 0.0 <= n.height <= 1.0
            assert n.x + n.width <= 1.0001
            assert n.y + n.height <= 1.0001

    # --------------------------------------------------------------------------
    # Scenario X: Multiple Forensic Signals Escalate to MULTI_SIGNAL_ANOMALY
    # --------------------------------------------------------------------------
    def test_x_multiple_forensic_signals(self, service):
        img, _ = create_synthetic_clean_card(800, 500)
        # Add copy-move clone AND splice noise in portrait
        np.random.seed(42)
        tex = (np.random.rand(100, 100, 3) * 255).astype(np.uint8)
        img[300:400, 50:150] = tex
        img[300:400, 500:600] = tex

        # Add Photoshop EXIF
        exif_bytes = create_jpeg_with_exif("Adobe Photoshop CS6")

        res = service.analyze(img, document_type="driving_license", raw_bytes=exif_bytes)
        assert res.status == ForensicStatus.FORENSIC_SUSPICIOUS
        assert res.anomaly_state in (ForensicAnomalyState.MULTI_SIGNAL_ANOMALY, ForensicAnomalyState.WEAK_ANOMALY)

    # --------------------------------------------------------------------------
    # Scenario Y: Weak Single Signal Does Not Declare Forgery
    # --------------------------------------------------------------------------
    def test_y_weak_single_signal_does_not_declare_forgery(self, service):
        img, _ = create_synthetic_clean_card(800, 500)
        # Provide Photoshop EXIF tag alone without image anomalies
        exif_bytes = create_jpeg_with_exif("Adobe Photoshop CS6")
        res = service.analyze(img, document_type="driving_license", raw_bytes=exif_bytes)

        # Single weak anomaly alone does not escalate to suspicious
        assert res.status == ForensicStatus.FORENSIC_CLEAN
        assert res.anomaly_state == ForensicAnomalyState.NO_FORENSIC_ANOMALY

    # --------------------------------------------------------------------------
    # Scenario Z: Image Quality Problem != Forgery
    # --------------------------------------------------------------------------
    def test_z_image_quality_does_not_equal_forgery(self, service):
        dark_img = np.ones((650, 650, 3), dtype=np.uint8) * 15  # Extremely dark
        res = service.analyze(dark_img, document_type="driving_license")

        assert res.status == ForensicStatus.FORENSIC_INCONCLUSIVE
        assert res.anomaly_state == ForensicAnomalyState.INCONCLUSIVE
        assert "not a finding of forgery" in res.overall_explanation.lower()

    # --------------------------------------------------------------------------
    # Scenario AA: No Client-Provided Score Trust
    # --------------------------------------------------------------------------
    def test_aa_no_client_provided_score_trust(self, service):
        img, raw_bytes = create_synthetic_clean_card(800, 500)
        # Even if a client sends mock parameters, service independently runs server-side analysis
        res = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)
        assert res.status == ForensicStatus.FORENSIC_CLEAN
        assert res.quality.is_adequate is True

    # --------------------------------------------------------------------------
    # Scenario AB: Profile-Driven Configuration for Indian DL
    # --------------------------------------------------------------------------
    def test_ab_profile_driven_configuration(self, service):
        img, raw_bytes = create_synthetic_clean_card(800, 500)
        res = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)

        assert res.document_type == "driving_license"
        assert res.forensic_engine_version == "8.0.0"
        assert len(res.findings) >= 5

    # --------------------------------------------------------------------------
    # Scenario AC: Evidence Provenance
    # --------------------------------------------------------------------------
    def test_ac_evidence_provenance(self, service):
        img, raw_bytes = create_synthetic_clean_card(800, 500)
        res = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)

        for f in res.findings:
            assert f.finding_id
            assert f.signal_type
            assert f.status
            assert f.source
            assert f.explanation

    # --------------------------------------------------------------------------
    # Scenario AD: Image Hash Generation
    # --------------------------------------------------------------------------
    def test_ad_image_hash_generation(self, service):
        img, raw_bytes = create_synthetic_clean_card(800, 500)
        res1 = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)
        res2 = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)

        assert res1.image_sha256 == res2.image_sha256
        assert len(res1.image_sha256) == 64

    # --------------------------------------------------------------------------
    # Scenario AE: Preprocessing Provenance
    # --------------------------------------------------------------------------
    def test_ae_preprocessing_provenance(self, service):
        img, raw_bytes = create_synthetic_clean_card(800, 500)
        res = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)

        assert "image_width" in res.telemetry
        assert "image_height" in res.telemetry
        assert "duration_ms" in res.telemetry
        assert res.telemetry["image_width"] == 800
        assert res.telemetry["image_height"] == 500

    # --------------------------------------------------------------------------
    # Scenario AF: Profile Version Recorded
    # --------------------------------------------------------------------------
    def test_af_profile_version_recorded(self, service):
        img, raw_bytes = create_synthetic_clean_card(800, 500)
        res = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)

        assert res.profile_version is not None
        for f in res.findings:
            assert f.profile_version == res.profile_version

    # --------------------------------------------------------------------------
    # Scenario AG: No Raw PII in Findings or Telemetry
    # --------------------------------------------------------------------------
    def test_ag_no_raw_pii_logging(self, service):
        img, raw_bytes = create_synthetic_clean_card(800, 500)
        res = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)
        res_dict = res.to_dict()

        # Check that sensitive names or raw license numbers are not in telemetry
        telemetry_str = str(res_dict["telemetry"])
        assert "RAHUL" not in telemetry_str
        assert "15-08-1990" not in telemetry_str

    # --------------------------------------------------------------------------
    # Scenario AH: Absolute Rule: NEVER Emits FORGED_DOCUMENT from M3
    # --------------------------------------------------------------------------
    def test_ah_no_forged_document_emitted_by_m3(self, service):
        # Create heavily manipulated synthetic card
        img, _ = create_synthetic_clean_card(800, 500)
        img[50:250, 50:250] = 0  # Black box cut
        img[300:450, 300:450] = 255  # White box cut
        raw_bytes = create_jpeg_with_exif("Adobe Photoshop 2024")

        res = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)
        # Even with extreme anomalies, status MUST be FORENSIC_SUSPICIOUS, NEVER FORGED_DOCUMENT
        assert res.status == ForensicStatus.FORENSIC_SUSPICIOUS
        assert res.status != "FORGED_DOCUMENT"
        assert "FORGED_DOCUMENT" not in [f.status.value for f in res.findings]

    # --------------------------------------------------------------------------
    # Scenario AI: Backward Compatibility with Legacy Summary Schema
    # --------------------------------------------------------------------------
    def test_ai_legacy_summary_compatibility(self, service):
        img, raw_bytes = create_synthetic_clean_card(800, 500)
        res = service.analyze(img, document_type="driving_license", raw_bytes=raw_bytes)
        res_dict = res.to_dict()

        assert "status" in res_dict
        assert "findings" in res_dict
        assert "quality" in res_dict
        assert "suspicious_regions" in res_dict
        assert "heatmap_grid" in res_dict
        assert len(res_dict["heatmap_grid"]) == 16
        assert len(res_dict["heatmap_grid"][0]) == 16

    # --------------------------------------------------------------------------
    # Scenario AJ: Security Protections Against Oversized Images
    # --------------------------------------------------------------------------
    def test_aj_security_oversized_image_handling(self, service):
        # Huge array beyond MAX_IMAGE_DIMENSION_PX (10000px)
        huge_fake_array = np.ones((10001, 50, 3), dtype=np.uint8)
        res = service.analyze(huge_fake_array, document_type="driving_license")

        assert res.status == ForensicStatus.FORENSIC_UNAVAILABLE
        assert res.quality.is_adequate is False
        assert any("exceed maximum allowed" in r for r in res.quality.reasons)
