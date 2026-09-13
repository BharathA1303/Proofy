"""
tests/test_semantic_field_extraction.py

Comprehensive Phase 5 Test Suite for Semantic Field Extraction & Layout-Aware Association:
  - Section 21.A: Simple labelled field (NAME -> BHARATH A)
  - Section 21.B: Date of Birth (DOB role resolution)
  - Section 21.C: License Number extraction with label & pattern
  - Section 21.D: Issue Date resolution (ISSUE_DATE role)
  - Section 21.E: Validity NT resolution (NON_TRANSPORT_VALIDITY role)
  - Section 21.F: Validity TR resolution (TRANSPORT_VALIDITY role)
  - Section 21.G: Three date labels in separate columns -> associated with correct columns
  - Section 21.H: 3 labels / 2 values -> does not fabricate missing third value
  - Section 21.I: Multiple candidate dates -> AMBIGUOUS unless layout resolves them
  - Section 21.J: Multi-column document -> strictly prevents cross-column association
  - Section 21.K: Parentage (S/O) -> extracted separately without polluting holder name
  - Section 21.L: Two possible names without discriminating evidence -> AMBIGUOUS
  - Section 21.M: Unknown / invalid COV -> handles unrecognized tokens conservatively
  - Section 21.N: Multiline address -> groups consecutive address lines in reading order
  - Section 21.O: Address + neighboring authority -> authority does NOT enter address
  - Section 21.P: State derived from license number -> provenance DERIVED_FROM_LICENSE_NUMBER
  - Section 21.Q: OCR confidence preserved on candidates and results
  - Section 21.R: Normalized value remains compatible with Phase 3
  - Section 21.S: Phase 2 no-guessing behavior remains fully intact
  - Section 21.T: Phase 4 normalized-coordinate behavior remains fully intact
  - Model Availability: Neural extractor reports MODEL_UNAVAILABLE when weights absent
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import pytest

from app.services.document_intelligence.schema import (
    ClassificationModelInfo,
    DocumentRegionType,
    FieldCandidate,
    FieldCandidateStatus,
    ModelStatus,
    NormalizedBBox,
    SemanticDateRole,
    SemanticFieldConfig,
    SemanticFieldResult,
    SpatialRelationship,
)
from app.services.document_intelligence.semantic_extractor import (
    GenericSemanticFieldExtractor,
    NeuralSemanticFieldExtractor,
)
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)
from app.services.documents.profiles.driving_license_profile import DRIVING_LICENSE_PROFILE


@dataclass
class MockToken:
    """Mock OCR region with text, bbox, and confidence."""
    text: str
    bbox: List[List[int]]
    confidence: float = 0.95
    line_num: int = 1


# ── Test Suite ───────────────────────────────────────────────────────────────

class TestSemanticFieldExtraction:
    """Phase 5 Semantic Field Extraction and Layout-Aware Association Tests."""

    def setup_method(self):
        self.extractor = GenericSemanticFieldExtractor()

    # ── Test A: Simple labelled field ─────────────────────────────────────────
    def test_a_simple_labelled_field_name(self):
        tokens = [
            MockToken("NAME", [[100, 100], [180, 100], [180, 120], [100, 120]], confidence=0.98),
            MockToken("BHARATH A", [[200, 100], [380, 100], [380, 120], [200, 120]], confidence=0.96),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        name_res = result.get_field("name")
        assert name_res is not None
        assert name_res.status == FieldCandidateStatus.FOUND
        assert name_res.value == "BHARATH A"
        assert name_res.relationship == SpatialRelationship.LABEL_LEFT_VALUE
        assert name_res.matched_label == "NAME"

    # ── Test B: DOB ───────────────────────────────────────────────────────────
    def test_b_dob_role_resolution(self):
        tokens = [
            MockToken("DATE OF BIRTH", [[100, 150], [250, 150], [250, 170], [100, 170]], confidence=0.97),
            MockToken("01/01/2000", [[100, 180], [220, 180], [220, 200], [100, 200]], confidence=0.95),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        dob_res = result.get_field("dob")
        assert dob_res is not None
        assert dob_res.status == FieldCandidateStatus.FOUND
        assert dob_res.value == "2000-01-01"
        assert dob_res.best_candidate.date_role == SemanticDateRole.DOB
        assert dob_res.relationship == SpatialRelationship.LABEL_ABOVE_VALUE

    # ── Test C: License number ────────────────────────────────────────────────
    def test_c_license_number_extraction(self):
        tokens = [
            MockToken("DL NO:", [[100, 50], [180, 50], [180, 70], [100, 70]], confidence=0.98),
            MockToken("KA0120241234567", [[200, 50], [420, 50], [420, 70], [200, 70]], confidence=0.96),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        lic_res = result.get_field("license_number")
        assert lic_res is not None
        assert lic_res.status == FieldCandidateStatus.FOUND
        assert lic_res.value == "KA0120241234567"
        assert lic_res.relationship == SpatialRelationship.LABEL_LEFT_VALUE

    # ── Test D: Issue date ────────────────────────────────────────────────────
    def test_d_issue_date_resolution(self):
        tokens = [
            MockToken("ISSUE DATE", [[100, 220], [220, 220], [220, 240], [100, 240]], confidence=0.95),
            MockToken("10/01/2024", [[100, 250], [210, 250], [210, 270], [100, 270]], confidence=0.94),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        iss_res = result.get_field("issue_date")
        assert iss_res is not None
        assert iss_res.status == FieldCandidateStatus.FOUND
        assert iss_res.value == "2024-01-10"
        assert iss_res.best_candidate.date_role == SemanticDateRole.ISSUE_DATE

    # ── Test E: Validity NT ───────────────────────────────────────────────────
    def test_e_validity_nt_resolution(self):
        tokens = [
            MockToken("VALIDITY (NT)", [[400, 220], [550, 220], [550, 240], [400, 240]], confidence=0.96),
            MockToken("09/01/2034", [[400, 250], [510, 250], [510, 270], [400, 270]], confidence=0.93),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        vnt_res = result.get_field("valid_to")
        assert vnt_res is not None
        assert vnt_res.status == FieldCandidateStatus.FOUND
        assert vnt_res.value == "2034-01-09"
        assert vnt_res.best_candidate.date_role == SemanticDateRole.NON_TRANSPORT_VALIDITY

    # ── Test F: Validity TR ───────────────────────────────────────────────────
    def test_f_validity_tr_resolution(self):
        tokens = [
            MockToken("VALIDITY (TR)", [[700, 220], [850, 220], [850, 240], [700, 240]], confidence=0.96),
            MockToken("09/01/2029", [[700, 250], [810, 250], [810, 270], [700, 270]], confidence=0.92),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        vtr_res = result.get_field("transport_validity")
        assert vtr_res is not None
        assert vtr_res.status == FieldCandidateStatus.FOUND
        assert vtr_res.value == "2029-01-09"
        assert vtr_res.best_candidate.date_role == SemanticDateRole.TRANSPORT_VALIDITY

    # ── Test G: Three date labels in separate columns ─────────────────────────
    def test_g_three_date_labels_in_separate_columns(self):
        """
        Row 1 contains 3 labels across 3 horizontal columns:
          Col A: ISSUE DATE (x: 100..220)
          Col B: VALIDITY (NT) (x: 400..550)
          Col C: VALIDITY (TR) (x: 700..850)
        Row 2 contains the corresponding 3 dates in their respective columns.
        """
        tokens = [
            # Row 1: Labels
            MockToken("ISSUE DATE", [[100, 200], [220, 200], [220, 220], [100, 220]]),
            MockToken("VALIDITY (NT)", [[400, 200], [550, 200], [550, 220], [400, 220]]),
            MockToken("VALIDITY (TR)", [[700, 200], [850, 200], [850, 220], [700, 220]]),
            # Row 2: Values
            MockToken("10/01/2014", [[100, 230], [210, 230], [210, 250], [100, 250]]),
            MockToken("09/01/2034", [[400, 230], [510, 230], [510, 250], [400, 250]]),
            MockToken("09/01/2029", [[700, 230], [810, 230], [810, 250], [700, 250]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)

        iss = result.get_field("issue_date")
        vnt = result.get_field("valid_to")
        vtr = result.get_field("transport_validity")

        assert iss.status == FieldCandidateStatus.FOUND
        assert iss.value == "2014-01-10"

        assert vnt.status == FieldCandidateStatus.FOUND
        assert vnt.value == "2034-01-09"

        assert vtr.status == FieldCandidateStatus.FOUND
        assert vtr.value == "2029-01-09"

    # ── Test H: 3 labels / 2 values (Does not invent 3rd value) ───────────────
    def test_h_three_labels_two_values_does_not_fabricate(self):
        """
        3 labels exist across columns, but only 2 date values are printed.
        Validity TR is missing a value. Must NOT fabricate the missing date!
        """
        tokens = [
            MockToken("ISSUE DATE", [[100, 200], [220, 200], [220, 220], [100, 220]]),
            MockToken("VALIDITY (NT)", [[400, 200], [550, 200], [550, 220], [400, 220]]),
            MockToken("VALIDITY (TR)", [[700, 200], [850, 200], [850, 220], [700, 220]]),
            # Only 2 values: Column A and Column B
            MockToken("10/01/2014", [[100, 230], [210, 230], [210, 250], [100, 250]]),
            MockToken("09/01/2034", [[400, 230], [510, 230], [510, 250], [400, 250]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)

        iss = result.get_field("issue_date")
        vnt = result.get_field("valid_to")
        vtr = result.get_field("transport_validity")

        assert iss.status == FieldCandidateStatus.FOUND
        assert iss.value == "2014-01-10"

        assert vnt.status == FieldCandidateStatus.FOUND
        assert vnt.value == "2034-01-09"

        # Missing field must be MISSING, never fabricated or borrowed!
        assert vtr.status == FieldCandidateStatus.MISSING
        assert vtr.value is None

    # ── Test I: Multiple candidate dates without layout disambiguation ────────
    def test_i_multiple_candidate_dates_produces_ambiguity(self):
        """
        A single standalone DOB label with two equidistant dates in the same column.
        Without distinguishing evidence, must report AMBIGUOUS.
        """
        tokens = [
            MockToken("DATE OF BIRTH", [[100, 100], [250, 100], [250, 120], [100, 120]]),
            MockToken("01/01/1990", [[100, 130], [220, 130], [220, 150], [100, 150]]),
            MockToken("02/02/1995", [[100, 160], [220, 160], [220, 180], [100, 180]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        dob_res = result.get_field("dob")
        assert dob_res.status == FieldCandidateStatus.AMBIGUOUS
        assert len(dob_res.candidates) >= 2

    # ── Test J: Multi-column document (No cross-column association) ───────────
    def test_j_multi_column_no_cross_column_association(self):
        """
        Label A is at Column 1 (x: 100..200).
        Value B is at Column 2 (x: 500..600).
        Even if Value B is vertically close to Label A, it must NOT be paired!
        """
        tokens = [
            MockToken("BLOOD GROUP", [[100, 300], [220, 300], [220, 320], [100, 320]]),
            # O+ is at x=600 (far right column), while Blood Group is at x=100
            MockToken("O+", [[600, 330], [650, 330], [650, 350], [600, 350]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        bg = result.get_field("blood_group")
        # Because dx = 480px / 1000 = 0.48 > column tolerance 0.15, it must be rejected!
        assert bg.status == FieldCandidateStatus.MISSING

    # ── Test K: Parentage extraction vs Holder name ───────────────────────────
    def test_k_parentage_does_not_pollute_holder_name(self):
        """
        Document contains:
          NAME: BHARATH A
          S/O: RAMESH KUMAR
        Parentage must be extracted as RAMESH KUMAR and name as BHARATH A.
        """
        tokens = [
            MockToken("NAME: BHARATH A", [[100, 100], [350, 100], [350, 120], [100, 120]]),
            MockToken("S/O: RAMESH KUMAR", [[100, 130], [360, 130], [360, 150], [100, 150]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)

        name = result.get_field("name")
        parentage = result.get_field("parentage")

        assert name.status == FieldCandidateStatus.FOUND
        assert name.value == "BHARATH A"

        assert parentage.status == FieldCandidateStatus.FOUND
        assert parentage.value == "RAMESH KUMAR"

    # ── Test L: Two possible names without discriminating evidence ────────────
    def test_l_two_possible_names_produces_ambiguity(self):
        tokens = [
            MockToken("NAME:", [[100, 100], [160, 100], [160, 120], [100, 120]]),
            MockToken("BHARATH A", [[180, 100], [320, 100], [320, 120], [180, 120]]),
            MockToken("NAME:", [[100, 200], [160, 200], [160, 220], [100, 220]]),
            MockToken("AARAV SHARMA", [[180, 200], [350, 200], [350, 220], [180, 220]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        name = result.get_field("name")
        assert name.status == FieldCandidateStatus.AMBIGUOUS
        assert len(name.candidates) == 2

    # ── Test M: Unknown COV ───────────────────────────────────────────────────
    def test_m_unknown_cov_handled_conservatively(self):
        tokens = [
            MockToken("COV: UNKNOWN_ROCKET_99", [[100, 400], [400, 400], [400, 420], [100, 420]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        cov = result.get_field("vehicle_classes")
        assert cov.status == FieldCandidateStatus.FOUND
        # Phase 3 normalizer leaves unrecognized taxonomy out of canonical set
        assert "LMV" not in (cov.value or "")

    # ── Test N: Multiline Address Grouping ────────────────────────────────────
    def test_n_multiline_address_grouping(self):
        tokens = [
            MockToken("ADDRESS", [[100, 300], [200, 300], [200, 320], [100, 320]]),
            MockToken("123 ANNA SALAI", [[100, 330], [300, 330], [300, 350], [100, 350]]),
            MockToken("MOUNT ROAD", [[100, 355], [260, 355], [260, 375], [100, 375]]),
            MockToken("CHENNAI 600002", [[100, 380], [280, 380], [280, 400], [100, 400]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        addr = result.get_field("address")
        assert addr.status == FieldCandidateStatus.FOUND
        assert "123 ANNA SALAI" in addr.value
        assert "CHENNAI 600002" in addr.value
        assert addr.relationship == SpatialRelationship.LABEL_ABOVE_VALUE

    # ── Test O: Address + Neighboring Authority (Authority does not enter) ─────
    def test_o_address_does_not_leak_authority(self):
        tokens = [
            MockToken("ADDRESS", [[100, 300], [200, 300], [200, 320], [100, 320]]),
            MockToken("123 ANNA SALAI", [[100, 330], [300, 330], [300, 350], [100, 350]]),
            MockToken("CHENNAI 600002", [[100, 355], [280, 355], [280, 375], [100, 375]]),
            # Next line is a recognized authority header
            MockToken("ISSUING AUTHORITY: RTO CHENNAI CENTRAL", [[100, 385], [500, 385], [500, 405], [100, 405]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        addr = result.get_field("address")
        assert addr.status == FieldCandidateStatus.FOUND
        assert "CHENNAI 600002" in addr.value
        # Authority label must terminate address grouping!
        assert "ISSUING AUTHORITY" not in addr.value
        assert "RTO CHENNAI CENTRAL" not in addr.value

    # ── Test P: State derived from license number ─────────────────────────────
    def test_p_state_derived_from_license_number_provenance(self):
        tokens = [
            MockToken("DL NO: TN0520250014128", [[100, 100], [380, 100], [380, 120], [100, 120]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        state_res = result.get_field("state")
        assert state_res is not None
        assert state_res.status == FieldCandidateStatus.FOUND
        assert state_res.value == "Tamil Nadu"
        assert state_res.source == "DERIVED_FROM_LICENSE_NUMBER"
        assert state_res.relationship == SpatialRelationship.DERIVED_VALUE

    # ── Test Q: OCR confidence preserved ─────────────────────────────────────
    def test_q_ocr_confidence_preserved(self):
        tokens = [
            MockToken("NAME: BHARATH A", [[100, 100], [350, 100], [350, 120], [100, 120]], confidence=0.8765),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        name = result.get_field("name")
        assert name.ocr_confidence == pytest.approx(0.8765, rel=1e-3)
        assert name.confidence > 0.0

    # ── Test R: Normalized value remains compatible with Phase 3 ──────────────
    def test_r_normalized_values_compatible_with_phase_3(self):
        tokens = [
            MockToken("DOB: 13-MAR-2003", [[100, 100], [300, 100], [300, 120], [100, 120]]),
            MockToken("DL NO: dl - 04 2023 0012345", [[100, 130], [400, 130], [400, 150], [100, 150]]),
            MockToken("COV: lmv, mcwg, trans", [[100, 160], [350, 160], [350, 180], [100, 180]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        assert result.get_field("dob").value == "2003-03-13"
        assert result.get_field("license_number").value == "DL0420230012345"
        assert "LMV" in result.get_field("vehicle_classes").value
        assert "MCWG" in result.get_field("vehicle_classes").value

    # ── Test S: Phase 2 no-guessing contract intact ───────────────────────────
    def test_s_no_guessing_contract_intact_for_missing_fields(self):
        """When evidence is missing, field is MISSING with value=None."""
        tokens = [
            MockToken("UNION OF INDIA", [[100, 50], [300, 50], [300, 70], [100, 70]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        assert result.get_field("name").status == FieldCandidateStatus.MISSING
        assert result.get_field("name").value is None
        assert result.get_field("license_number").status == FieldCandidateStatus.MISSING
        assert result.get_field("license_number").value is None

    # ── Test T: Phase 4 normalized coordinates intact ─────────────────────────
    def test_t_normalized_coordinates_intact(self):
        tokens = [
            MockToken("NAME: BHARATH A", [[100, 60], [300, 60], [300, 120], [100, 120]]),
        ]
        result = self.extractor.extract_fields(DRIVING_LICENSE_PROFILE, tokens, image_width=1000, image_height=600)
        name = result.get_field("name")
        assert name.normalized_bbox is not None
        assert name.normalized_bbox.x == pytest.approx(0.10, rel=1e-2)
        assert name.normalized_bbox.y == pytest.approx(0.10, rel=1e-2)
        assert name.normalized_bbox.width == pytest.approx(0.20, rel=1e-2)
        assert name.normalized_bbox.height == pytest.approx(0.10, rel=1e-2)

    # ── Model Availability: Neural Extractor ──────────────────────────────────
    def test_neural_extractor_reports_model_unavailable_without_weights(self):
        neural = NeuralSemanticFieldExtractor(weights_path="/nonexistent/model.pth")
        assert neural.is_model_available() is False
        assert neural.get_model_status() == ModelStatus.MODEL_UNAVAILABLE

        tokens = [MockToken("NAME: BHARATH A", [[100, 100], [300, 100], [300, 120], [100, 120]])]
        res = neural.extract_fields(DRIVING_LICENSE_PROFILE, tokens)
        assert res.model.status == ModelStatus.MODEL_UNAVAILABLE
        assert res.get_field("name").value == "BHARATH A"
