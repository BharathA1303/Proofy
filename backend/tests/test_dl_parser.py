"""
backend/tests/test_dl_parser.py

Unit tests for Driving License field extraction, normalization, and layout handling.
"""
import pytest
from app.schemas.ocr import OCRRegionRaw, TravelerFields
from app.services.documents.driving_license.dl_field_normalizer import (
    extract_state_from_license_number,
    normalize_blood_group,
    normalize_dl_date,
    normalize_license_number,
    normalize_vehicle_classes,
)
from app.services.documents.driving_license.dl_parser import (
    DateRole,
    FieldStatus,
    parse_driving_license,
)


class TestDLFieldNormalizer:
    def test_normalize_license_number_clean(self):
        assert normalize_license_number("DL-0420110012345") == "DL0420110012345"
        assert normalize_license_number("TN09 20201234567") == "TN0920201234567"
        assert normalize_license_number("  mh-12/2018/0054321  ") == "MH1220180054321"

    def test_normalize_license_number_empty_or_none(self):
        assert normalize_license_number(None) is None
        assert normalize_license_number("") is None
        assert normalize_license_number("   ") is None

    def test_normalize_dates(self):
        assert normalize_dl_date("1992-05-15") == "1992-05-15"
        assert normalize_dl_date("15/05/1992") == "1992-05-15"
        assert normalize_dl_date("15-05-1992") == "1992-05-15"
        assert normalize_dl_date("15 MAY 1992") == "1992-05-15"
        assert normalize_dl_date("invalid") is None

    def test_normalize_blood_groups(self):
        assert normalize_blood_group("O+ve") == "O+"
        assert normalize_blood_group("B +ve") == "B+"
        assert normalize_blood_group("AB-") == "AB-"
        assert normalize_blood_group("INVALID") is None

    def test_normalize_vehicle_classes(self):
        res = normalize_vehicle_classes("COV: MCWG, LMV, TRANS")
        assert "MCWG" in res
        assert "LMV" in res
        assert "TRANS" in res

    def test_extract_state(self):
        assert extract_state_from_license_number("DL0420110012345") == "Delhi"
        assert extract_state_from_license_number("TN0920201234567") == "Tamil Nadu"
        assert extract_state_from_license_number("MH1220180054321") == "Maharashtra"
        assert extract_state_from_license_number("KA0120190001234") == "Karnataka"


class TestDLParser:
    def test_parse_valid_indian_dl(self):
        regions = [
            OCRRegionRaw(text="UNION OF INDIA", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 40], [200, 40], [200, 60], [10, 60]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="HOLDER NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 100], [250, 100], [250, 120], [10, 120]]),
            OCRRegionRaw(text="DOB: 15/05/1992", confidence=0.95, bbox=[[10, 130], [200, 130], [200, 150], [10, 150]]),
            OCRRegionRaw(text="ISSUE DATE: 15/05/2011", confidence=0.94, bbox=[[10, 160], [200, 160], [200, 180], [10, 180]]),
            OCRRegionRaw(text="VALID TILL: 14/05/2035", confidence=0.94, bbox=[[10, 190], [200, 190], [200, 210], [10, 210]]),
            OCRRegionRaw(text="BLOOD GROUP: O+", confidence=0.92, bbox=[[10, 220], [150, 220], [150, 240], [10, 240]]),
            OCRRegionRaw(text="COV: LMV, MCWG", confidence=0.93, bbox=[[10, 250], [180, 250], [180, 270], [10, 270]]),
            OCRRegionRaw(text="ISSUING AUTHORITY: RTO DELHI", confidence=0.91, bbox=[[10, 280], [250, 280], [250, 300], [10, 300]]),
        ]

        res = parse_driving_license(regions)
        assert res.unsupported_layout is False
        assert res.license_number.value == "DL0420110012345"
        assert res.name.value == "RAHUL SHARMA"
        assert res.dob.value == "1992-05-15"
        assert res.issuedDate.value == "2011-05-15"
        assert res.expiry.value == "2035-05-14"
        assert res.blood_group.value == "O+"
        assert "LMV" in res.vehicle_classes.value
        assert "MCWG" in res.vehicle_classes.value
        assert res.state.value == "Delhi"

    def test_parse_missing_optional_fields(self):
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: KA0120190001234", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: PRIYA VERMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="DOB: 10/10/1990", confidence=0.95, bbox=[[10, 100], [200, 100], [200, 120], [10, 120]]),
        ]

        res = parse_driving_license(regions)
        assert res.license_number.value == "KA0120190001234"
        assert res.name.value == "PRIYA VERMA"
        assert res.dob.value == "1990-10-10"
        assert res.blood_group.value is None
        assert res.vehicle_classes.value is None

    def test_unsupported_layout(self):
        regions = [
            OCRRegionRaw(text="GROCERY STORE RECEIPT", confidence=0.90, bbox=[[10, 10], [100, 10], [100, 20], [10, 20]]),
            OCRRegionRaw(text="TOTAL AMOUNT: $45.20", confidence=0.92, bbox=[[10, 30], [120, 30], [120, 40], [10, 40]]),
        ]
        res = parse_driving_license(regions)
        assert res.unsupported_layout is True
        assert res.license_number.value is None


class TestDLToDictTravelerFieldsContract:
    """
    Regression coverage for the orchestrator's generic traveler-dict contract.

    verification_orchestrator.py builds TravelerFields by filtering
    parsed.to_dict() down to TravelerFields.model_fields:
        t_fields = TravelerFields(**{k: v for k, v in traveler_dict.items()
                                      if k in TravelerFields.model_fields})

    ParsedDrivingLicenseData.to_dict() must therefore expose every
    officer-relevant field under a key TravelerFields actually declares
    (mirroring the alias convention in aadhaar_parser.to_dict()), or that
    field is silently dropped before validation/evidence normalization
    ever sees it — with no error, since the field is simply absent from
    the resulting TravelerFields instance.
    """

    def _fully_populated_result(self):
        regions = [
            OCRRegionRaw(text="UNION OF INDIA", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 40], [200, 40], [200, 60], [10, 60]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="HOLDER NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 100], [250, 100], [250, 120], [10, 120]]),
            OCRRegionRaw(text="DOB: 15/05/1992", confidence=0.95, bbox=[[10, 130], [200, 130], [200, 150], [10, 150]]),
            OCRRegionRaw(text="ISSUE DATE: 15/05/2011", confidence=0.94, bbox=[[10, 160], [200, 160], [200, 180], [10, 180]]),
            OCRRegionRaw(text="VALID TILL: 14/05/2035", confidence=0.94, bbox=[[10, 190], [200, 190], [200, 210], [10, 210]]),
            OCRRegionRaw(text="BLOOD GROUP: O+", confidence=0.92, bbox=[[10, 220], [150, 220], [150, 240], [10, 240]]),
            OCRRegionRaw(text="COV: LMV, MCWG", confidence=0.93, bbox=[[10, 250], [180, 250], [180, 270], [10, 270]]),
            OCRRegionRaw(text="ISSUING AUTHORITY: RTO DELHI", confidence=0.91, bbox=[[10, 280], [250, 280], [250, 300], [10, 300]]),
        ]
        return parse_driving_license(regions)

    def test_to_dict_exposes_travelerfields_aligned_aliases(self):
        res = self._fully_populated_result()
        d = res.to_dict()

        # TravelerFields-aligned aliases must be present alongside the
        # DL-native snake_case keys, matching aadhaar_parser's convention.
        assert d["licenseNumber"] == res.license_number.value
        assert d["bloodGroup"] == res.blood_group.value
        assert d["vehicleClass"] == res.vehicle_classes.value
        assert d["authority"] == res.issuing_authority.value

    def test_populated_fields_survive_orchestrator_style_filter(self):
        """
        Reproduces verification_orchestrator.py's exact filtering step and
        asserts no populated, officer-relevant field is silently lost.
        """
        res = self._fully_populated_result()
        d = res.to_dict()
        filtered = {k: v for k, v in d.items() if k in TravelerFields.model_fields}
        t_fields = TravelerFields(**filtered)

        assert t_fields.docNumber == res.license_number.value
        assert t_fields.name == res.name.value
        assert t_fields.dob == res.dob.value
        assert t_fields.issuedDate == res.valid_from.value
        assert t_fields.expiry == res.valid_to.value
        assert t_fields.bloodGroup == res.blood_group.value
        assert t_fields.vehicleClass == res.vehicle_classes.value
        assert t_fields.authority == res.issuing_authority.value
        assert t_fields.state == res.state.value


class TestDLParserNoGuessingContract:
    """
    Phase 2 — safety/no-guessing hardening regression coverage.

    Each test below pins down one dangerous fallback that existed before
    Phase 2 and asserts the parser now reports FieldStatus.MISSING or
    FieldStatus.AMBIGUOUS (with candidates preserved) instead of guessing.
    """

    # ── A/B/C/D/E: date extraction ───────────────────────────────────────

    def test_A_multiple_unlabeled_dates_leave_expiry_unresolved(self):
        """
        Multiple date-shaped OCR lines exist but none is labeled as expiry.
        The old "pick the latest future date" fallback would have promoted
        one into `expiry`. It must now stay unresolved, with every
        observed date preserved only as an UNKNOWN_DATE candidate.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="10/01/2024", confidence=0.90, bbox=[[10, 130], [200, 130], [200, 150], [10, 150]]),
            OCRRegionRaw(text="09/01/2044", confidence=0.90, bbox=[[10, 160], [200, 160], [200, 180], [10, 180]]),
        ]
        res = parse_driving_license(regions)
        assert res.expiry.value is None
        assert res.expiry.status == FieldStatus.MISSING
        assert res.valid_to.value is None
        unknown_roles = [dc.role for dc in res.date_candidates]
        assert unknown_roles.count(DateRole.UNKNOWN_DATE) == 2

    def test_B_dob_as_latest_date_never_becomes_expiry(self):
        """
        DOB happens to be later than the (labeled) issue date once both are
        interpreted purely as calendar values out of context — the parser
        must not "helpfully" reassign the DOB-labeled value to expiry.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="ISSUE DATE: 10/01/2000", confidence=0.94, bbox=[[10, 100], [250, 100], [250, 120], [10, 120]]),
            OCRRegionRaw(text="DOB: 12/08/2020", confidence=0.95, bbox=[[10, 130], [200, 130], [200, 150], [10, 150]]),
        ]
        res = parse_driving_license(regions)
        assert res.dob.value == "2020-08-12"
        assert res.expiry.value != res.dob.value
        assert res.expiry.value is None
        assert res.expiry.status == FieldStatus.MISSING

    def test_C_issue_date_as_latest_date_never_becomes_expiry(self):
        """
        The labeled issue date is chronologically later than nothing else
        useful is present — the old fallback's guard
        (`valid_from and valid_to <= valid_from`) could still promote an
        unrelated OCR date into expiry. It must not do so here either.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="DOB: 12/08/1995", confidence=0.95, bbox=[[10, 100], [200, 100], [200, 120], [10, 120]]),
            OCRRegionRaw(text="ISSUE DATE: 10/01/2024", confidence=0.94, bbox=[[10, 130], [200, 130], [200, 150], [10, 150]]),
            OCRRegionRaw(text="PRINTED ON 09/01/2044", confidence=0.80, bbox=[[10, 400], [200, 400], [200, 420], [10, 420]]),
        ]
        res = parse_driving_license(regions)
        assert res.valid_from.value == "2024-01-10"
        assert res.expiry.value is None
        assert res.expiry.status == FieldStatus.MISSING
        # The unrelated printed date must still be visible as an UNKNOWN_DATE
        # candidate rather than silently discarded.
        assert any(
            dc.normalized_value == "2044-01-09" and dc.role == DateRole.UNKNOWN_DATE
            for dc in res.date_candidates
        )

    def test_D_correctly_labelled_expiry_is_extracted(self):
        """Deterministic parsing with explicit evidence must still work — Phase 2 removes guessing, not legitimate labeled extraction."""
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="DOB: 15/05/1992", confidence=0.95, bbox=[[10, 100], [200, 100], [200, 120], [10, 120]]),
            OCRRegionRaw(text="VALID TILL: 14/05/2035", confidence=0.94, bbox=[[10, 190], [200, 190], [200, 210], [10, 210]]),
        ]
        res = parse_driving_license(regions)
        assert res.expiry.value == "2035-05-14"
        assert res.expiry.status == FieldStatus.FOUND
        assert any(
            dc.role == DateRole.EXPIRY_DATE and dc.normalized_value == "2035-05-14"
            for dc in res.date_candidates
        )

    def test_E_missing_expiry_is_missing_not_guessed(self):
        """No expiry label and no ambiguous candidates at all: status must be MISSING, not a fabricated value."""
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="DOB: 15/05/1992", confidence=0.95, bbox=[[10, 100], [200, 100], [200, 120], [10, 120]]),
        ]
        res = parse_driving_license(regions)
        assert res.expiry.value is None
        assert res.expiry.status == FieldStatus.MISSING
        assert res.date_candidates == [] or all(dc.role != DateRole.EXPIRY_DATE for dc in res.date_candidates)

    # ── F: license number ────────────────────────────────────────────────

    def test_F_multiple_license_number_candidates_produce_ambiguity(self):
        """
        Two distinct, independently pattern-matching license-number-shaped
        strings appear on the document (e.g. a genuine DL No and an
        unrelated reference/permit number in the same format). The parser
        must not silently pick whichever appears first in reading order.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            # Unrelated but pattern-matching identifier elsewhere on the card.
            OCRRegionRaw(text="REF TN0920201234567", confidence=0.85, bbox=[[10, 400], [250, 400], [250, 420], [10, 420]]),
        ]
        res = parse_driving_license(regions)
        assert res.license_number.value is None
        assert res.license_number.status == FieldStatus.AMBIGUOUS
        assert set(res.license_number.candidates) == {"DL0420110012345", "TN0920201234567"}
        # docNumber must mirror the same ambiguity, not silently resolve.
        assert res.docNumber.value is None
        assert res.docNumber.status == FieldStatus.AMBIGUOUS

    # ── G: name ───────────────────────────────────────────────────────────

    def test_G_random_uppercase_text_does_not_become_name(self):
        """
        An uppercase OCR line with no NAME label and no positional evidence
        (not directly above a parentage line) must not be interpreted as
        the bearer's name.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="TRANSPORT DEPARTMENT NOTICE", confidence=0.90, bbox=[[10, 300], [250, 300], [250, 320], [10, 320]]),
            OCRRegionRaw(text="DOB: 15/05/1992", confidence=0.95, bbox=[[10, 130], [200, 130], [200, 150], [10, 150]]),
        ]
        res = parse_driving_license(regions)
        assert res.name.value is None
        assert res.name.status == FieldStatus.MISSING

    def test_name_label_and_positional_conflict_is_ambiguous(self):
        """
        CORRECTED after real-world validation: an explicit NAME label is
        stronger evidence than the "line above a parentage marker"
        heuristic, which real Indian DL layouts routinely violate — e.g. an
        unrelated field like "Organ Donor: N" can sit directly above the
        "Son/Daughter/Wife of" line with no name anywhere nearby. Treating
        the two as equally-weighted competing votes turned a clean labeled
        match into a false AMBIGUOUS on an actual production document
        (see backend/app/services/documents/driving_license/dl_parser.py
        name-extraction section). The positional heuristic is therefore
        only ever consulted when no labeled name exists, and a labeled
        match is never second-guessed by it.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="AMIT KUMAR", confidence=0.90, bbox=[[10, 100], [250, 100], [250, 120], [10, 120]]),
            OCRRegionRaw(text="S/O SURESH KUMAR", confidence=0.92, bbox=[[10, 130], [250, 130], [250, 150], [10, 150]]),
        ]
        res = parse_driving_license(regions)
        assert res.name.value == "RAHUL SHARMA"
        assert res.name.status == FieldStatus.FOUND

    def test_positional_fallback_used_only_when_no_label_present(self):
        """
        Reproduces the real production layout that exposed the bug above:
        Name: / <name line> / Blood Group: ... / DOB / Organ Donor: N /
        Son/Daughter/Wife of / <father's name>. The labeled name must win,
        and "Organ Donor: N" — the line directly above the parentage
        marker — must never be treated as a name candidate at all.
        """
        regions = [
            OCRRegionRaw(text="Indian Union Driving Licence", confidence=0.97, bbox=[[10, 10], [300, 10], [300, 30], [10, 30]]),
            OCRRegionRaw(text="Name:", confidence=0.98, bbox=[[10, 40], [100, 40], [100, 60], [10, 60]]),
            OCRRegionRaw(text="BHARATH A", confidence=0.97, bbox=[[10, 70], [200, 70], [200, 90], [10, 90]]),
            OCRRegionRaw(text="Blood Group:A1B+", confidence=0.93, bbox=[[10, 100], [200, 100], [200, 120], [10, 120]]),
            OCRRegionRaw(text="Dateof Birth:13-03-2007", confidence=0.96, bbox=[[10, 130], [250, 130], [250, 150], [10, 150]]),
            OCRRegionRaw(text="Organ Donor: N", confidence=0.89, bbox=[[10, 160], [200, 160], [200, 180], [10, 180]]),
            OCRRegionRaw(text="Son/Daughter/Wife of", confidence=0.98, bbox=[[10, 190], [250, 190], [250, 210], [10, 210]]),
            OCRRegionRaw(text="ASHOK", confidence=1.0, bbox=[[10, 220], [150, 220], [150, 240], [10, 240]]),
        ]
        res = parse_driving_license(regions)
        assert res.name.value == "BHARATH A"
        assert res.name.status == FieldStatus.FOUND

    def test_positional_fallback_rejects_non_name_lines(self):
        """When no NAME label exists, the positional fallback must still refuse an obviously non-name line (e.g. an "Organ Donor" field) directly above the parentage marker."""
        regions = [
            OCRRegionRaw(text="Indian Union Driving Licence", confidence=0.97, bbox=[[10, 10], [300, 10], [300, 30], [10, 30]]),
            OCRRegionRaw(text="Organ Donor: N", confidence=0.89, bbox=[[10, 160], [200, 160], [200, 180], [10, 180]]),
            OCRRegionRaw(text="Son/Daughter/Wife of", confidence=0.98, bbox=[[10, 190], [250, 190], [250, 210], [10, 210]]),
            OCRRegionRaw(text="ASHOK", confidence=1.0, bbox=[[10, 220], [150, 220], [150, 240], [10, 240]]),
        ]
        res = parse_driving_license(regions)
        assert res.name.value is None
        assert res.name.status == FieldStatus.MISSING

    # ── H: vehicle classes ───────────────────────────────────────────────

    def test_H_unknown_vehicle_class_token_is_not_silently_accepted(self):
        """
        A COV-labeled token that is not in the known class taxonomy (e.g.
        an OCR-garbled or unfamiliar 4-char code) must not be treated as a
        confidently-recognized vehicle class.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="COV: ZXQW", confidence=0.90, bbox=[[10, 250], [180, 250], [180, 270], [10, 270]]),
        ]
        res = parse_driving_license(regions)
        assert res.vehicle_classes.value is None
        assert res.vehicle_classes.status == FieldStatus.UNKNOWN
        assert "ZXQW" in res.vehicle_classes.candidates

    def test_known_vehicle_class_still_recognized(self):
        """Deterministic recognition of a known COV code must still work."""
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="COV: LMV, MCWG", confidence=0.93, bbox=[[10, 250], [180, 250], [180, 270], [10, 270]]),
        ]
        res = parse_driving_license(regions)
        assert res.vehicle_classes.status == FieldStatus.FOUND
        assert "LMV" in res.vehicle_classes.value
        assert "MCWG" in res.vehicle_classes.value

    # ── I: blood group ───────────────────────────────────────────────────

    def test_I_unsupported_blood_group_is_not_guessed(self):
        """
        A blood-group-labeled value that does not match any recognized
        ABO/Rh group must be surfaced as UNKNOWN with the raw candidate
        preserved, never silently mapped to the "closest" valid group.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="BLOOD GROUP: XYZ", confidence=0.90, bbox=[[10, 220], [150, 220], [150, 240], [10, 240]]),
        ]
        res = parse_driving_license(regions)
        assert res.blood_group.value is None
        assert res.blood_group.status == FieldStatus.UNKNOWN
        assert "XYZ" in res.blood_group.candidates

    # ── J: state provenance ──────────────────────────────────────────────

    def test_J_state_provenance_marks_derivation_from_license_number(self):
        """State inferred from the license-number prefix must explicitly record its derivation, not read as if extracted directly from the card."""
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
        ]
        res = parse_driving_license(regions)
        assert res.state.value == "Delhi"
        assert res.state.source == "DERIVED_FROM_LICENSE_NUMBER"

    # ── K: address ────────────────────────────────────────────────────────

    def test_K_address_is_not_fabricated_from_unrelated_ocr(self):
        """
        The parser does not currently extract address at all — this test
        pins that absence down as MISSING rather than allowing a future
        change to start concatenating unrelated OCR lines into a
        plausible-looking but fabricated address.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="123 MG ROAD BANGALORE", confidence=0.88, bbox=[[10, 300], [250, 300], [250, 320], [10, 320]]),
            OCRRegionRaw(text="KARNATAKA 560001", confidence=0.87, bbox=[[10, 330], [250, 330], [250, 350], [10, 350]]),
        ]
        res = parse_driving_license(regions)
        assert res.address.value is None
        assert res.address.status == FieldStatus.MISSING

    # ── L: low OCR confidence ────────────────────────────────────────────

    def test_L_low_confidence_candidate_is_preserved_with_status(self):
        """
        A single, unambiguous license-number candidate below the OCR
        confidence floor must still be surfaced (not discarded) but flagged
        LOW_CONFIDENCE rather than a clean FOUND result.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.30, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
        ]
        res = parse_driving_license(regions)
        assert res.license_number.value == "DL0420110012345"
        assert res.license_number.status == FieldStatus.LOW_CONFIDENCE
        assert res.license_number.confidence == 0.30

    # ── M: Phase 1 contract preserved ────────────────────────────────────

    def test_M_ambiguous_and_missing_fields_still_satisfy_travelerfields_contract(self):
        """
        Even when several fields are AMBIGUOUS/MISSING/UNKNOWN (value=None),
        to_dict() must still produce a dict that survives the orchestrator's
        TravelerFields filter without raising and without smuggling a
        placeholder/status string into a data field's value.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="REF TN0920201234567", confidence=0.85, bbox=[[10, 400], [250, 400], [250, 420], [10, 420]]),
            OCRRegionRaw(text="BLOOD GROUP: XYZ", confidence=0.90, bbox=[[10, 220], [150, 220], [150, 240], [10, 240]]),
            OCRRegionRaw(text="COV: ZXQW", confidence=0.90, bbox=[[10, 250], [180, 250], [180, 270], [10, 270]]),
        ]
        res = parse_driving_license(regions)
        # License number is ambiguous in this fixture — confirm the ambiguity exists.
        assert res.license_number.status == FieldStatus.AMBIGUOUS

        d = res.to_dict()
        filtered = {k: v for k, v in d.items() if k in TravelerFields.model_fields}
        t_fields = TravelerFields(**filtered)  # must not raise

        assert t_fields.docNumber is None
        assert t_fields.bloodGroup is None
        assert t_fields.vehicleClass is None
        # No status/placeholder string ever leaks into a value field.
        for v in filtered.values():
            if isinstance(v, str):
                assert v not in ("AMBIGUOUS", "UNKNOWN", "MISSING", "LOW_CONFIDENCE")

    def test_ambiguous_status_never_escalates_to_forged(self):
        """
        Structural/parsing ambiguity is an information-quality state, not
        an authenticity verdict — it must never appear as or be conflated
        with a forgery/tampering conclusion anywhere in the parser output.
        """
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="REF TN0920201234567", confidence=0.85, bbox=[[10, 400], [250, 400], [250, 420], [10, 420]]),
        ]
        res = parse_driving_license(regions)
        assert res.license_number.status == FieldStatus.AMBIGUOUS
        assert "FORGED" not in res.license_number.status.value
        assert res.unsupported_layout is False  # ambiguity != unsupported layout, and never a forgery flag
