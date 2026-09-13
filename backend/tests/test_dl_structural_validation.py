"""
backend/tests/test_dl_structural_validation.py

Phase 6: Structural and Eligibility Validation Test Suite for Indian Driving Licences.

Covers all 43 scenarios (A through AQ) defined in Section 18:
  - REQUIRED FIELDS: A through E
  - IDENTIFIER: F through I
  - DATES: J through Q
  - AGE: R through W
  - COV: X through Z
  - VALIDITY: AA through AD
  - STATE: AE through AH
  - SEMANTIC: AI through AK
  - OVERALL: AL through AO
  - AUTHENTICITY SEPARATION: AP through AQ
"""
import datetime
import pytest

from app.schemas.ocr import TravelerFields
from app.services.documents.driving_license.dl_validator import (
    StructuralValidationStatus,
    validate_driving_license_document,
)
from app.services.document_intelligence.schema import (
    FieldCandidate,
    FieldCandidateStatus,
    SemanticExtractionResult,
    SemanticFieldResult,
)


class TestDLStructuralValidation:
    """Test suite covering Section 18 structural validation scenarios."""

    REF_DATE = datetime.date(2025, 1, 1)

    # ── REQUIRED FIELDS (A - E) ───────────────────────────────────────────────

    def test_a_all_required_fields_present(self):
        """A. All required fields present -> structurally valid."""
        traveler = TravelerFields(
            name="PRIYA PATEL",
            docNumber="DL0420110012345",
            dob="1995-06-15",
            issuedDate="2015-06-15",
            expiry="2035-06-14",
            vehicleClass="LMV",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["status"] == "passed"
        assert res["checks"]["required_fields"]["valid"] is True
        assert res["checks"]["required_fields"]["status"] == "passed"

    def test_b_missing_name(self):
        """B. Missing name -> required field missing."""
        traveler = TravelerFields(
            name="",
            docNumber="DL0420110012345",
            dob="1995-06-15",
            issuedDate="2015-06-15",
            expiry="2035-06-14",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["status"] == "failed"
        assert res["checks"]["required_fields"]["valid"] is False
        assert any("name" in i["message"].lower() for i in res["issues"])
        assert "FORGED" not in res["summary"].upper()

    def test_c_missing_dl_number(self):
        """C. Missing DL number -> required field missing."""
        traveler = TravelerFields(
            name="PRIYA PATEL",
            docNumber="",
            dob="1995-06-15",
            issuedDate="2015-06-15",
            expiry="2035-06-14",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["status"] == "failed"
        assert res["checks"]["required_fields"]["valid"] is False
        assert res["checks"]["license_number_format"]["valid"] is False
        assert any("license number" in i["message"].lower() or "docnumber" in i["message"].lower() for i in res["issues"])

    def test_d_missing_dob(self):
        """D. Missing DOB -> required field missing."""
        traveler = TravelerFields(
            name="PRIYA PATEL",
            docNumber="DL0420110012345",
            dob="",
            issuedDate="2015-06-15",
            expiry="2035-06-14",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["status"] == "failed"
        assert res["checks"]["required_fields"]["valid"] is False
        assert any("dob" in i["message"].lower() for i in res["issues"])

    def test_e_ambiguous_required_field(self):
        """E. Ambiguous required field produces structured ambiguity status, not forged."""
        traveler = TravelerFields(
            name="AMBIGUOUS",
            docNumber="DL0420110012345",
            dob="1995-06-15",
            issuedDate="2015-06-15",
            expiry="2035-06-14",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["required_fields"]["valid"] is False
        assert res["checks"]["required_fields"]["status"] in ["warning", "ambiguous", "failed"]
        assert any("ambiguous" in i["message"].lower() for i in res["issues"])
        assert "FORGED" not in res["summary"].upper()

    # ── IDENTIFIER (F - I) ───────────────────────────────────────────────────

    def test_f_valid_current_format(self):
        """F. Valid current canonical MoRTH format."""
        traveler = TravelerFields(
            name="PRIYA PATEL",
            docNumber="DL0420110012345",
            dob="1995-06-15",
            issuedDate="2015-06-15",
            expiry="2035-06-14",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["license_number_format"]["identifier_status"] == "VALID"
        assert res["checks"]["license_number_format"]["valid"] is True
        assert res["checks"]["license_number_format"]["status"] == "passed"

    def test_g_valid_legacy_format(self):
        """G. Valid legacy format recognized with LEGACY_VALID status."""
        traveler = TravelerFields(
            name="PRIYA PATEL",
            docNumber="MH0220110001234",
            dob="1995-06-15",
            issuedDate="2015-06-15",
            expiry="2035-06-14",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["license_number_format"]["valid"] is True
        assert res["checks"]["license_number_format"]["identifier_status"] in ["VALID", "LEGACY_VALID"]

    def test_h_unusual_but_plausible_format(self):
        """H. Unusual but plausible format yields FORMAT_WARNING, never FORGED."""
        traveler = TravelerFields(
            name="PRIYA PATEL",
            docNumber="RJ-14/DL/12345/2012",
            dob="1990-06-15",
            issuedDate="2012-06-15",
            expiry="2032-06-14",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["license_number_format"]["status"] == "warning"
        assert res["checks"]["license_number_format"]["identifier_status"] in ["FORMAT_WARNING", "INVALID"]
        assert "FORGED" not in res["summary"].upper()

    def test_i_invalid_identifier(self):
        """I. Syntactically invalid identifier produces warning/failure, not forgery."""
        traveler = TravelerFields(
            name="PRIYA PATEL",
            docNumber="INVALID#123",
            dob="1990-06-15",
            issuedDate="2015-06-15",
            expiry="2035-06-14",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["license_number_format"]["status"] == "warning"
        assert "FORGED" not in res["summary"].upper()

    # ── DATES (J - Q) ────────────────────────────────────────────────────────

    def test_j_dob_before_issue_date(self):
        """J. DOB before issue date is valid."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["date_chronology"]["valid"] is True
        assert res["checks"]["date_chronology"]["status"] == "passed"

    def test_k_dob_after_issue_date(self):
        """K. DOB after issue date fails chronology."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="2015-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["date_chronology"]["valid"] is False
        assert res["checks"]["date_chronology"]["status"] == "failed"

    def test_l_issue_before_expiry(self):
        """L. Issue date before expiry date is valid."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["date_chronology"]["valid"] is True

    def test_m_expiry_before_issue(self):
        """M. Expiry before issue date fails chronology."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2030-01-01",
            expiry="2025-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["date_chronology"]["valid"] is False
        assert res["checks"]["date_chronology"]["status"] == "failed"

    def test_n_expired_dl(self):
        """N. Expired DL is classified as EXPIRED, not forged."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1980-01-01",
            issuedDate="2000-01-01",
            expiry="2020-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["expiry_date"]["expired"] is True
        assert res["checks"]["expiry_date"]["classification"] == "EXPIRED"
        assert res["checks"]["expiry_date"]["valid"] is False
        assert "FORGED" not in res["summary"].upper()

    def test_o_missing_expiry(self):
        """O. Missing expiry date classified as MISSING without guessing."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry=None,
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["expiry_date"]["classification"] == "MISSING"
        assert res["checks"]["expiry_date"]["expired"] is None

    def test_p_ambiguous_expiry(self):
        """P. Ambiguous expiry preserves AMBIGUOUS classification."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="AMBIGUOUS",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["expiry_date"]["classification"] == "AMBIGUOUS"
        assert res["checks"]["expiry_date"]["valid"] is False

    def test_q_future_dob(self):
        """Q. Future DOB fails validation."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="2035-01-01",
            issuedDate="2036-01-01",
            expiry="2040-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["date_chronology"]["valid"] is False
        assert any("future" in i["message"].lower() for i in res["issues"])

    # ── AGE ELIGIBILITY (R - W) ──────────────────────────────────────────────

    def test_r_age_16_applicable_mcwog_category(self):
        """R. Age 16 with MCWOG category satisfies Motor Vehicles Act Sec 4(1)."""
        traveler = TravelerFields(
            name="YOUTH RIDER",
            docNumber="DL0420160012345",
            dob="2000-01-01",
            issuedDate="2016-01-01",
            expiry="2036-01-01",
            vehicleClass="MCWOG",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["age_eligibility"]["valid"] is True
        assert res["checks"]["age_eligibility"]["status"] == "passed"

    def test_s_age_17_lmv_category(self):
        """S. Age 17 with LMV category fails minimum 18 requirement."""
        traveler = TravelerFields(
            name="UNDERAGE DRIVER",
            docNumber="DL0420170012345",
            dob="2000-01-01",
            issuedDate="2017-01-01",
            expiry="2037-01-01",
            vehicleClass="LMV",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["age_eligibility"]["valid"] is False
        assert res["checks"]["age_eligibility"]["status"] == "failed"
        assert any("underage" in i["message"].lower() or "minimum 18" in i["message"].lower() for i in res["issues"])

    def test_t_age_18_lmv_category(self):
        """T. Age 18 with LMV category satisfies requirement."""
        traveler = TravelerFields(
            name="LEGAL DRIVER",
            docNumber="DL0420180012345",
            dob="2000-01-01",
            issuedDate="2018-01-01",
            expiry="2038-01-01",
            vehicleClass="LMV",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["age_eligibility"]["valid"] is True
        assert res["checks"]["age_eligibility"]["status"] == "passed"

    def test_u_age_below_20_transport_category(self):
        """U. Age 19 with commercial TRANS category fails minimum 20 requirement (Sec 4(2))."""
        traveler = TravelerFields(
            name="YOUNG COMMERCIAL",
            docNumber="DL0420190012345",
            dob="2000-01-01",
            issuedDate="2019-01-01",
            expiry="2039-01-01",
            vehicleClass="TRANS",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["age_eligibility"]["valid"] is False
        assert res["checks"]["age_eligibility"]["status"] == "failed"
        assert any("underage" in i["message"].lower() or "minimum 20" in i["message"].lower() for i in res["issues"])

    def test_v_age_20_transport_category(self):
        """V. Age 20 with commercial TRANS category satisfies requirement."""
        traveler = TravelerFields(
            name="COMMERCIAL DRIVER",
            docNumber="DL0420200012345",
            dob="2000-01-01",
            issuedDate="2020-01-01",
            expiry="2040-01-01",
            vehicleClass="TRANS",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["age_eligibility"]["valid"] is True
        assert res["checks"]["age_eligibility"]["status"] == "passed"

    def test_w_unknown_cov_age_eligibility_inconclusive(self):
        """W. Unknown COV produces AGE_ELIGIBILITY_INCONCLUSIVE, no guessing."""
        traveler = TravelerFields(
            name="UNKNOWN COV DRIVER",
            docNumber="DL0420170012345",
            dob="2000-01-01",
            issuedDate="2017-01-01",
            expiry="2037-01-01",
            vehicleClass="UNKNOWN",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["age_eligibility"]["status"] == "inconclusive"
        assert res["checks"]["age_eligibility"]["valid"] is False

    # ── VEHICLE CLASS (X - Z) ────────────────────────────────────────────────

    def test_x_recognized_cov(self):
        """X. Recognized COV is valid."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
            vehicleClass="LMV, MCWG",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["vehicle_class_validation"]["valid"] is True
        assert res["checks"]["vehicle_class_validation"]["status"] == "passed"
        assert "LMV" in res["checks"]["vehicle_class_validation"]["recognized_classes"]
        assert "MCWG" in res["checks"]["vehicle_class_validation"]["recognized_classes"]

    def test_y_unknown_cov_handled_conservatively(self):
        """Y. Unknown COV produces warning without rejecting document as forged."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
            vehicleClass="EXPERIMENTAL_HOVERCRAFT",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["vehicle_class_validation"]["status"] == "warning"
        assert "EXPERIMENTAL_HOVERCRAFT" in res["checks"]["vehicle_class_validation"]["unrecognized_classes"]
        assert "FORGED" not in res["summary"].upper()

    def test_z_transport_consistency(self):
        """Z. Transport COV endorsed but TR validity absent produces warning."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
            vehicleClass="TRANS",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["transport_validity"]["status"] == "warning"
        assert any("transport" in i["message"].lower() for i in res["issues"])

    # ── VALIDITY (AA - AD) ───────────────────────────────────────────────────

    def test_aa_nt_validity_present_tr_absent(self):
        """AA. NT validity present, TR absent is completely valid for private vehicle."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
            vehicleClass="LMV",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["transport_validity"]["valid"] is True
        assert res["checks"]["transport_validity"]["status"] == "passed"

    def test_ab_tr_validity_present(self):
        """AB. TR validity present and active is valid."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
            vehicleClass="TRANS",
        )
        res = validate_driving_license_document(
            traveler=traveler,
            reference_date=self.REF_DATE,
            extracted_fields={"transport_validity": "2028-01-01"},
        )
        assert res["checks"]["transport_validity"]["valid"] is True
        assert res["checks"]["transport_validity"]["status"] == "passed"

    def test_ac_both_validity_fields_present(self):
        """AC. Both NT and TR validity fields present and active are valid."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
            vehicleClass="LMV, TRANS",
        )
        res = validate_driving_license_document(
            traveler=traveler,
            reference_date=self.REF_DATE,
            extracted_fields={"transport_validity": "2028-01-01"},
        )
        assert res["checks"]["expiry_date"]["valid"] is True
        assert res["checks"]["transport_validity"]["valid"] is True

    def test_ad_no_fabrication_between_nt_and_tr(self):
        """AD. TR validity is never borrowed or fabricated from NT validity."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2034-01-09",
            vehicleClass="LMV",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["transport_validity"]["transport_expiry"] is None

    # ── STATE (AE - AH) ──────────────────────────────────────────────────────

    def test_ae_current_state_code(self):
        """AE. Current state code recognized."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["state_validation"]["state_code"] == "DL"
        assert res["checks"]["state_validation"]["state_code_status"] == "STATE_CODE_VALID"
        assert res["checks"]["state_validation"]["valid"] is True

    def test_af_legacy_state_code(self):
        """AF. Legacy state code recognized with STATE_CODE_LEGACY status."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="OR0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["state_validation"]["state_code"] == "OR"
        assert res["checks"]["state_validation"]["state_code_status"] == "STATE_CODE_LEGACY"
        assert res["checks"]["state_validation"]["valid"] is True

    def test_ag_unknown_state_code(self):
        """AG. Unknown state code flagged as unknown, not forged."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="ZZ0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["state_validation"]["state_code_status"] == "STATE_CODE_UNKNOWN"
        assert res["checks"]["state_validation"]["valid"] is False
        assert "FORGED" not in res["summary"].upper()

    def test_ah_derived_state_provenance(self):
        """AH. Derived state retains DERIVED_FROM_LICENSE_NUMBER provenance."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="TN0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["checks"]["state_validation"]["provenance"] == "DERIVED_FROM_LICENSE_NUMBER"

    # ── SEMANTIC EXTRACTION INTEGRATION (AI - AK) ─────────────────────────────

    def test_ai_phase_5_ambiguity_preserved(self):
        """AI. Phase 5 ambiguity preserved during validation without guessing."""
        sem_res = SemanticExtractionResult(
            fields={
                "name": SemanticFieldResult(field_name="name", value="RAHUL SHARMA", status=FieldCandidateStatus.FOUND),
                "license_number": SemanticFieldResult(field_name="license_number", value="DL0420110012345", status=FieldCandidateStatus.FOUND),
                "dob": SemanticFieldResult(field_name="dob", status=FieldCandidateStatus.AMBIGUOUS),
            }
        )
        res = validate_driving_license_document(semantic_result=sem_res, reference_date=self.REF_DATE)
        assert res["checks"]["required_fields"]["valid"] is False
        assert res["structural_status"] in ["STRUCTURALLY_INVALID", "STRUCTURALLY_VALID_WITH_WARNINGS", "INCONCLUSIVE"]

    def test_aj_no_reguessing_dates(self):
        """AJ. Validator never arbitrarily picks another date candidate to force chronology."""
        sem_res = SemanticExtractionResult(
            fields={
                "name": SemanticFieldResult(field_name="name", value="RAHUL SHARMA", status=FieldCandidateStatus.FOUND),
                "license_number": SemanticFieldResult(field_name="license_number", value="DL0420110012345", status=FieldCandidateStatus.FOUND),
                "dob": SemanticFieldResult(field_name="dob", value="1990-01-01", status=FieldCandidateStatus.FOUND),
                "valid_to": SemanticFieldResult(field_name="valid_to", status=FieldCandidateStatus.MISSING),
            }
        )
        res = validate_driving_license_document(semantic_result=sem_res, reference_date=self.REF_DATE)
        assert res["checks"]["expiry_date"]["classification"] == "MISSING"

    def test_ak_semantic_field_confidence_preserved(self):
        """AK. Confidence from semantic extraction preserved."""
        sem_res = SemanticExtractionResult(
            fields={
                "name": SemanticFieldResult(field_name="name", value="RAHUL SHARMA", status=FieldCandidateStatus.LOW_CONFIDENCE, confidence=0.48),
                "license_number": SemanticFieldResult(field_name="license_number", value="DL0420110012345", status=FieldCandidateStatus.FOUND, confidence=0.96),
                "dob": SemanticFieldResult(field_name="dob", value="1990-01-01", status=FieldCandidateStatus.FOUND, confidence=0.92),
            }
        )
        res = validate_driving_license_document(semantic_result=sem_res, reference_date=self.REF_DATE)
        req_fields = res["checks"]["required_fields"]["fields"]
        assert req_fields["name"]["status"] == "LOW_CONFIDENCE"
        assert req_fields["name"]["confidence"] == 0.48

    # ── OVERALL STRUCTURAL RESULTS (AL - AO) ──────────────────────────────────

    def test_al_overall_structurally_valid(self):
        """AL. Fully valid document produces STRUCTURALLY_VALID."""
        traveler = TravelerFields(
            name="RAHUL SHARMA",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2035-01-01",
            vehicleClass="LMV",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["structural_status"] == StructuralValidationStatus.STRUCTURALLY_VALID.value
        assert res["status"] == "passed"

    def test_am_overall_valid_with_warnings(self):
        """AM. Minor warnings produce STRUCTURALLY_VALID_WITH_WARNINGS."""
        traveler = TravelerFields(
            name="RAHUL SHARMA",
            docNumber="OR0420110012345",  # Legacy state code OR
            dob="1990-01-01",
            issuedDate="2010-01-01",
            expiry="2035-01-01",
            vehicleClass="LMV",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["structural_status"] == StructuralValidationStatus.STRUCTURALLY_VALID_WITH_WARNINGS.value
        assert res["status"] == "warning"

    def test_an_overall_inconclusive(self):
        """AN. Empty or completely ambiguous inputs produce INCONCLUSIVE."""
        res = validate_driving_license_document(traveler=None)
        assert res["structural_status"] == StructuralValidationStatus.INCONCLUSIVE.value
        assert res["status"] == "insufficient_data"

    def test_ao_overall_structurally_invalid(self):
        """AO. Inverted dates or missing required fields produce STRUCTURALLY_INVALID."""
        traveler = TravelerFields(
            name="",
            docNumber="",
            dob="1990-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["structural_status"] == StructuralValidationStatus.STRUCTURALLY_INVALID.value
        assert res["status"] == "failed"

    # ── AUTHENTICITY SEPARATION (AP - AQ) ─────────────────────────────────────

    def test_ap_structural_warning_does_not_produce_forged_document(self):
        """AP. Irregularities produce FORMAT_WARNING, never FORGED_DOCUMENT."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL-IRREGULAR-999",
            dob="1990-01-01",
            issuedDate="2015-01-01",
            expiry="2035-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert "FORGED" not in res["summary"].upper()
        assert "FORGED_DOCUMENT" not in str(res)

    def test_aq_structural_invalid_does_not_produce_forensic_forgery_conclusion(self):
        """AQ. Invalid structural validity does not declare document fraudulent."""
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="DL0420110012345",
            dob="2010-01-01",
            issuedDate="2005-01-01",  # Inverted dates
            expiry="2025-01-01",
        )
        res = validate_driving_license_document(traveler=traveler, reference_date=self.REF_DATE)
        assert res["structural_status"] == StructuralValidationStatus.STRUCTURALLY_INVALID.value
        assert "FORGED" not in res["summary"].upper()
        assert "FRAUD" not in res["summary"].upper()
