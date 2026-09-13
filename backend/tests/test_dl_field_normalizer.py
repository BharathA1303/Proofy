"""
backend/tests/test_dl_field_normalizer.py

Comprehensive tests for Driving License field normalization hardening (Phase 3).
Tests strict separation between normalization and validation, explicit taxonomies,
raw OCR evidence preservation, and structured status reporting.
"""
import pytest
from app.services.documents.driving_license.dl_field_normalizer import (
    COVItem,
    COVNormalizationResult,
    KNOWN_VEHICLE_CLASSES,
    NormalizationResult,
    NormalizationStatus,
    STATE_CODE_REGISTRY,
    StateCodeEntry,
    StateCodeStatus,
    VALID_BLOOD_GROUPS,
    extract_state_from_license_number,
    extract_state_info_from_license_number,
    normalize_blood_group,
    normalize_blood_group_detailed,
    normalize_dl_date,
    normalize_dl_date_detailed,
    normalize_dl_text,
    normalize_dl_text_detailed,
    normalize_license_number,
    normalize_license_number_detailed,
    normalize_state_code,
    normalize_vehicle_classes,
    normalize_vehicle_classes_detailed,
)
from app.services.documents.driving_license.dl_parser import (
    DateRole,
    FieldStatus,
    parse_driving_license,
)
from app.schemas.ocr import OCRRegionRaw


# ── 1. License Number Tests ──────────────────────────────────────────────────

class TestLicenseNumberNormalization:
    def test_lowercase(self):
        assert normalize_license_number("ka0120241234567") == "KA0120241234567"
        res = normalize_license_number_detailed("ka0120241234567")
        assert res.status == NormalizationStatus.NORMALIZED
        assert res.value == "KA0120241234567"

    def test_whitespace(self):
        assert normalize_license_number("  KA 01 2024 1234567  ") == "KA0120241234567"
        res = normalize_license_number_detailed("  KA 01 2024 1234567  ")
        assert res.status == NormalizationStatus.NORMALIZED
        assert res.value == "KA0120241234567"

    def test_hyphen(self):
        assert normalize_license_number("KA-01-2024-1234567") == "KA0120241234567"
        res = normalize_license_number_detailed("KA-01-2024-1234567")
        assert res.status == NormalizationStatus.NORMALIZED
        assert res.value == "KA0120241234567"

    def test_slash(self):
        assert normalize_license_number("KA/01/2024/1234567") == "KA0120241234567"
        res = normalize_license_number_detailed("KA/01/2024/1234567")
        assert res.status == NormalizationStatus.NORMALIZED
        assert res.value == "KA0120241234567"

    def test_valid_representation_normalization_mixed(self):
        assert normalize_license_number("dl-04 2011/0012345") == "DL0420110012345"
        res = normalize_license_number_detailed("DL0420110012345")
        assert res.status == NormalizationStatus.UNCHANGED
        assert res.value == "DL0420110012345"

    def test_malformed_identifier(self):
        # Corrupt non-separator characters must not be silently stripped to invent a valid ID
        assert normalize_license_number("KA-01-2024-1234567@#") is None
        res = normalize_license_number_detailed("KA-01-2024-1234567@#")
        assert res.status == NormalizationStatus.INVALID
        assert res.value is None

        assert normalize_license_number("???") is None
        assert normalize_license_number_detailed("???").status == NormalizationStatus.INVALID

        assert normalize_license_number("--//..") is None
        assert normalize_license_number_detailed("--//..").status == NormalizationStatus.INVALID

    def test_no_character_invention(self):
        # Normalization standardizes formatting, but NEVER pads missing digits
        # or alters characters based on assumptions
        short_val = normalize_license_number("ka 01 202")
        assert short_val == "KA01202"  # Clean representation; validation decides whether 7 chars is valid
        assert len(short_val) == 7     # Never pads with zeros

        # Letter/number substitution is prohibited (e.g. 'O' is not guessed as '0')
        letter_val = normalize_license_number("KA-OI-ZOZ4-I234567")
        assert letter_val == "KAOIZOZ4I234567"

    def test_empty_or_none(self):
        assert normalize_license_number(None) is None
        assert normalize_license_number("") is None
        assert normalize_license_number("   ") is None
        res = normalize_license_number_detailed(None)
        assert res.status == NormalizationStatus.UNKNOWN
        assert res.value is None

    def test_ambiguous_license_number(self):
        res = normalize_license_number_detailed("DL0420110012345 OR TN0920201234567")
        assert res.status == NormalizationStatus.INVALID
        assert res.value is None


# ── 2. Date Normalization Tests ──────────────────────────────────────────────

class TestDateNormalization:
    def test_dd_mm_yyyy_hyphen(self):
        assert normalize_dl_date("15-05-1992") == "1992-05-15"
        res = normalize_dl_date_detailed("15-05-1992")
        assert res.status == NormalizationStatus.NORMALIZED
        assert res.value == "1992-05-15"

    def test_dd_mm_yyyy_slash(self):
        assert normalize_dl_date("15/05/1992") == "1992-05-15"
        res = normalize_dl_date_detailed("15/05/1992")
        assert res.status == NormalizationStatus.NORMALIZED
        assert res.value == "1992-05-15"

    def test_dd_mm_yyyy_dot(self):
        assert normalize_dl_date("15.05.1992") == "1992-05-15"
        res = normalize_dl_date_detailed("15.05.1992")
        assert res.status == NormalizationStatus.NORMALIZED
        assert res.value == "1992-05-15"

    def test_dd_mm_yyyy_space(self):
        assert normalize_dl_date("15 05 1992") == "1992-05-15"
        res = normalize_dl_date_detailed("15 05 1992")
        assert res.status == NormalizationStatus.NORMALIZED
        assert res.value == "1992-05-15"

    def test_dd_mmm_yyyy(self):
        assert normalize_dl_date("15 MAY 1992") == "1992-05-15"
        assert normalize_dl_date("15-MAY-1992") == "1992-05-15"
        assert normalize_dl_date("15/May/1992") == "1992-05-15"
        assert normalize_dl_date("15.MAY.1992") == "1992-05-15"
        assert normalize_dl_date("01 Jan 2020") == "2020-01-01"
        assert normalize_dl_date("31 December 2025") == "2025-12-31"

    def test_iso_formats(self):
        assert normalize_dl_date("1992-05-15") == "1992-05-15"
        assert normalize_dl_date("1992/05/15") == "1992-05-15"
        assert normalize_dl_date("1992.05.15") == "1992-05-15"
        res = normalize_dl_date_detailed("1992-05-15")
        assert res.status == NormalizationStatus.UNCHANGED
        assert res.value == "1992-05-15"

    def test_invalid_calendar_dates(self):
        # Feb 31 does not exist
        assert normalize_dl_date("31-02-2021") is None
        res = normalize_dl_date_detailed("31-02-2021")
        assert res.status == NormalizationStatus.INVALID

        # Feb 29 on non-leap year (2021)
        assert normalize_dl_date("29/02/2021") is None
        assert normalize_dl_date_detailed("29/02/2021").status == NormalizationStatus.INVALID

        # Feb 29 on leap year (2024) is valid
        assert normalize_dl_date("29/02/2024") == "2024-02-29"

        # Apr 31 does not exist
        assert normalize_dl_date("31.04.2023") is None

        # Month 13
        assert normalize_dl_date("15/13/2020") is None

        # Day 00 or Month 00
        assert normalize_dl_date("00/05/2020") is None
        assert normalize_dl_date("15/00/2020") is None

    def test_missing_component(self):
        # Missing year
        assert normalize_dl_date("15/05") is None
        # Missing day
        assert normalize_dl_date("05/1992") is None
        # 2-digit year (must NOT be inferred or guessed)
        assert normalize_dl_date("15/05/92") is None

    def test_ambiguous_input(self):
        # Date range string must not silently resolve to one date
        assert normalize_dl_date("15/05/1992 TO 14/05/2035") is None
        res = normalize_dl_date_detailed("15/05/1992 TO 14/05/2035")
        assert res.status == NormalizationStatus.INVALID

    def test_no_semantic_role_assignment(self):
        # Normalization only transforms the string representation;
        # it never attaches semantic meaning like "expiry" or "dob".
        res = normalize_dl_date_detailed("14/05/2035")
        assert res.value == "2035-05-14"
        assert not hasattr(res, "role")  # Normalizer does not decide semantic role


# ── 3. Blood Group Tests ─────────────────────────────────────────────────────

class TestBloodGroupNormalization:
    def test_all_standard_groups(self):
        assert normalize_blood_group("A+") == "A+"
        assert normalize_blood_group("A-") == "A-"
        assert normalize_blood_group("B+") == "B+"
        assert normalize_blood_group("B-") == "B-"
        assert normalize_blood_group("AB+") == "AB+"
        assert normalize_blood_group("AB-") == "AB-"
        assert normalize_blood_group("O+") == "O+"
        assert normalize_blood_group("O-") == "O-"

    def test_subgroups(self):
        assert normalize_blood_group("A1+") == "A1+"
        assert normalize_blood_group("A1-") == "A1-"
        assert normalize_blood_group("A1B+") == "A1B+"
        assert normalize_blood_group("A1B-") == "A1B-"
        assert normalize_blood_group("A2+") == "A2+"
        assert normalize_blood_group("A2-") == "A2-"
        assert normalize_blood_group("A2B+") == "A2B+"
        assert normalize_blood_group("A2B-") == "A2B-"

    def test_textual_positive_and_negative(self):
        assert normalize_blood_group("O POSITIVE") == "O+"
        assert normalize_blood_group("B POSITIVE") == "B+"
        assert normalize_blood_group("A NEGATIVE") == "A-"
        assert normalize_blood_group("AB POSITIVE") == "AB+"
        assert normalize_blood_group("B NEGATIVE") == "B-"

    def test_ocr_ve_suffix(self):
        assert normalize_blood_group("O+ve") == "O+"
        assert normalize_blood_group("B +ve") == "B+"
        assert normalize_blood_group("A-ve") == "A-"
        assert normalize_blood_group("B - ve") == "B-"
        assert normalize_blood_group("AB + VE") == "AB+"

    def test_negative_ve_order_bug_regression(self):
        # CRITICAL REGRESSION TEST:
        # Previously, naive "VE" removal corrupted "NEGATIVE" into "NEGATI",
        # preventing "B NEGATIVE" from normalizing to "B-".
        assert normalize_blood_group("B NEGATIVE") == "B-"
        assert normalize_blood_group("O NEGATIVE") == "O-"
        assert normalize_blood_group("A NEGATIVE") == "A-"
        assert normalize_blood_group("AB NEGATIVE") == "AB-"

    def test_invalid_blood_groups(self):
        assert normalize_blood_group("XYZ") is None
        assert normalize_blood_group("C+") is None
        assert normalize_blood_group("123") is None
        assert normalize_blood_group_detailed("XYZ").status == NormalizationStatus.INVALID

    def test_ab_without_sign_not_invented(self):
        # 'AB' without +/- must NOT be guessed as AB+ or AB-
        assert normalize_blood_group("AB") is None
        res = normalize_blood_group_detailed("AB")
        assert res.status == NormalizationStatus.INVALID


# ── 4. Vehicle Classes (COV) Tests ───────────────────────────────────────────

class TestVehicleClassesNormalization:
    def test_known_class(self):
        assert normalize_vehicle_classes("LMV") == ["LMV"]
        assert normalize_vehicle_classes("MCWG") == ["MCWG"]
        assert normalize_vehicle_classes("TRANS") == ["TRANS"]

    def test_multiple_known_classes(self):
        res = normalize_vehicle_classes("COV: MCWG, LMV, TRANS")
        assert res == ["LMV", "MCWG", "TRANS"]

    def test_unknown_class_not_silently_accepted(self):
        # Unrecognized token must NOT be returned as a valid vehicle class
        assert normalize_vehicle_classes("COV: ZXQW") == []
        res = normalize_vehicle_classes_detailed("COV: ZXQW")
        assert res.recognized == []
        assert "ZXQW" in res.unrecognized
        assert res.status == NormalizationStatus.UNRECOGNIZED

    def test_arbitrary_3_char_alphanumeric_not_accepted(self):
        # Replaces old unsafe rule: 'any 3-5 char alphanumeric is probably a COV'
        assert normalize_vehicle_classes("ABC") == []
        res = normalize_vehicle_classes_detailed("ABC")
        assert res.recognized == []
        assert "ABC" in res.unrecognized

    def test_arbitrary_5_char_alphanumeric_not_accepted(self):
        assert normalize_vehicle_classes("12345") == []
        assert normalize_vehicle_classes("XYZAB") == []
        res = normalize_vehicle_classes_detailed("12345")
        assert res.recognized == []
        assert "12345" in res.unrecognized

    def test_preserve_raw_unknown_tokens(self):
        res = normalize_vehicle_classes_detailed("COV: LMV, UNK99, MCWG")
        assert "LMV" in res.recognized
        assert "MCWG" in res.recognized
        assert "UNK99" in res.unrecognized
        assert any(item.code == "UNK99" and item.status == "UNRECOGNIZED_COV" for item in res.items)

    def test_phrase_class_recognition(self):
        res = normalize_vehicle_classes("MC WITH GEAR, LMV-NT")
        assert "MCWG" in res
        assert "LMV-NT" in res


# ── 5. State Code Normalization Tests ─────────────────────────────────────────

class TestStateCodeNormalization:
    def test_current_code(self):
        entry = normalize_state_code("DL")
        assert entry is not None
        assert entry.canonical_state == "Delhi"
        assert entry.code_status == StateCodeStatus.CURRENT

        entry_ka = normalize_state_code("KA")
        assert entry_ka.canonical_state == "Karnataka"
        assert entry_ka.code_status == StateCodeStatus.CURRENT

    def test_legacy_code(self):
        entry_dd = normalize_state_code("DD")
        assert entry_dd is not None
        assert entry_dd.code_status == StateCodeStatus.LEGACY

        entry_dn = normalize_state_code("DN")
        assert entry_dn is not None
        assert entry_dn.code_status == StateCodeStatus.LEGACY

    def test_or_od_odisha(self):
        # Both OR and OD map to Odisha, with OD current and OR legacy
        od = normalize_state_code("OD")
        assert od is not None
        assert od.canonical_state == "Odisha"
        assert od.code_status == StateCodeStatus.CURRENT

        o_r = normalize_state_code("OR")
        assert o_r is not None
        assert o_r.canonical_state == "Odisha"
        assert o_r.code_status == StateCodeStatus.LEGACY

        assert extract_state_from_license_number("OD0120201234567") == "Odisha"
        assert extract_state_from_license_number("OR0120201234567") == "Odisha"

    def test_uk_ua_uttarakhand(self):
        # Both UK and UA map to Uttarakhand, with UK current and UA legacy
        uk = normalize_state_code("UK")
        assert uk is not None
        assert uk.canonical_state == "Uttarakhand"
        assert uk.code_status == StateCodeStatus.CURRENT

        ua = normalize_state_code("UA")
        assert ua is not None
        assert ua.canonical_state == "Uttarakhand"
        assert ua.code_status == StateCodeStatus.LEGACY

        assert extract_state_from_license_number("UK0120201234567") == "Uttarakhand"
        assert extract_state_from_license_number("UA0120201234567") == "Uttarakhand"

    def test_unknown_code(self):
        assert normalize_state_code("ZZ") is None
        assert extract_state_from_license_number("ZZ0120201234567") is None

    def test_provenance_remains_derived_in_parser(self):
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: OD0220180012345", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
        ]
        res = parse_driving_license(regions)
        assert res.state.value == "Odisha"
        assert res.state.source == "DERIVED_FROM_LICENSE_NUMBER"


# ── 6. General Text Normalization Tests ───────────────────────────────────────

class TestGeneralTextNormalization:
    def test_whitespace_normalization(self):
        assert normalize_dl_text("  RAHUL    SHARMA   ") == "RAHUL SHARMA"
        assert normalize_dl_text("\tANITA\n\nKUMARI\t") == "ANITA KUMARI"

    def test_uppercase_controlled(self):
        assert normalize_dl_text("rahul sharma") == "RAHUL SHARMA"
        assert normalize_dl_text("Rahul Sharma") == "RAHUL SHARMA"

    def test_parentage_prefixes_stripped_at_start(self):
        assert normalize_dl_text("S/O RAMESH SHARMA") == "RAMESH SHARMA"
        assert normalize_dl_text("D/O PRIYA VERMA") == "PRIYA VERMA"
        assert normalize_dl_text("W/O ANIL KUMAR") == "ANIL KUMAR"
        assert normalize_dl_text("C/O RAJESH") == "RAJESH"
        assert normalize_dl_text("S/O: MOHAN DAS") == "MOHAN DAS"
        assert normalize_dl_text("SON OF RAMESH") == "RAMESH"
        assert normalize_dl_text("DAUGHTER OF SURESH") == "SURESH"
        assert normalize_dl_text("WIFE OF ANIL") == "ANIL"
        assert normalize_dl_text("CARE OF RAJESH") == "RAJESH"

    def test_parentage_letters_preserved_when_part_of_identity(self):
        # Letters S, D, W, C followed by O in names must NOT be stripped!
        assert normalize_dl_text("SOBHA") == "SOBHA"
        assert normalize_dl_text("DORAIRAJ") == "DORAIRAJ"
        assert normalize_dl_text("WARREN") == "WARREN"
        assert normalize_dl_text("COLIN") == "COLIN"
        assert normalize_dl_text("SOBHA RAM") == "SOBHA RAM"

    def test_identity_text_not_aggressively_fuzzy_corrected(self):
        # Evidence preserving: NEVER alter spelling based on fuzzy phonetic similarity
        assert normalize_dl_text("BHARATH") == "BHARATH"
        assert normalize_dl_text("BHARAT") == "BHARAT"
        assert normalize_dl_text("KUMAR") == "KUMAR"
        assert normalize_dl_text("KUMARH") == "KUMARH"
        assert normalize_dl_text("VIKRAM") == "VIKRAM"
        assert normalize_dl_text("VICKRAM") == "VICKRAM"

    def test_empty_parentage_prefix_only(self):
        assert normalize_dl_text("S/O") is None
        assert normalize_dl_text("D/O:") is None
        assert normalize_dl_text("C/O -") is None
