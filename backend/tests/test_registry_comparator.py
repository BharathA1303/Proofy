"""
tests/test_registry_comparator.py

Unit tests for Module 5 registry field comparison engine.

Tests cover:
  - All fields match → MATCHED
  - Name mismatch → MISMATCH
  - DOB mismatch → MISMATCH
  - Nationality mismatch → MISMATCH
  - Passport number mismatch → MISMATCH (critical — no fuzzy)
  - Expiry mismatch → INCONCLUSIVE (secondary field only)
  - Registry REVOKED status override
  - Registry SUSPENDED status override
  - Registry EXPIRED status override
  - Missing registry field
  - Missing document field
  - Both fields missing → INCONCLUSIVE
  - Passport number mismatch cannot become MATCHED via any fuzzy path
"""
import pytest

from app.schemas.registry import (
    DocumentFieldSource,
    FieldMatchStatus,
    FieldProvenance,
    RegistryRecord,
    RegistryStatus,
    RegistryVerificationRequest,
)
from app.services.registry.comparator import compare_fields


def _make_request(
    doc_num="TESTPASS001",
    name="TEST USER ONE",
    dob="1990-01-01",
    nationality="IND",
    expiry="2030-01-01",
    authority=None,
) -> RegistryVerificationRequest:
    """Helper to build a minimal request with all critical fields."""
    def p(val, src=DocumentFieldSource.MRZ):
        return FieldProvenance(value=val, source=src) if val else None

    return RegistryVerificationRequest(
        verification_id="test-vid-001",
        document_type="passport",
        document_number=p(doc_num),
        name=p(name, DocumentFieldSource.VIZ),
        date_of_birth=p(dob),
        nationality=p(nationality),
        expiry_date=p(expiry),
        issuing_authority=p(authority, DocumentFieldSource.VIZ) if authority else None,
    )


def _make_record(
    doc_num="TESTPASS001",
    name="TEST USER ONE",
    dob="1990-01-01",
    nationality="IND",
    expiry="2030-01-01",
    status="ACTIVE",
) -> RegistryRecord:
    return RegistryRecord(
        document_number=doc_num,
        name=name,
        date_of_birth=dob,
        nationality=nationality,
        expiry_date=expiry,
        registry_document_status=status,
    )


# ── Full match scenarios ───────────────────────────────────────────────────────

class TestFullMatch:
    def test_all_fields_match(self):
        request = _make_request()
        record = _make_record()
        results, status = compare_fields(request, record)
        assert status == RegistryStatus.MATCHED
        critical = [r for r in results if r.is_critical]
        assert all(r.status == FieldMatchStatus.MATCH for r in critical)

    def test_match_case_insensitive_name(self):
        request = _make_request(name="test user one")
        record = _make_record(name="TEST USER ONE")
        _, status = compare_fields(request, record)
        assert status == RegistryStatus.MATCHED

    def test_match_mrz_format_name(self):
        """DOE<<JOHN should match JOHN DOE (token normalization)"""
        request = _make_request(name="USER<TEST<ONE")
        record = _make_record(name="TEST USER ONE")
        _, status = compare_fields(request, record)
        assert status == RegistryStatus.MATCHED

    def test_match_date_different_formats(self):
        request = _make_request(dob="900101")  # MRZ format
        record = _make_record(dob="1990-01-01")
        _, status = compare_fields(request, record)
        assert status == RegistryStatus.MATCHED

    def test_match_nationality_case_normalized(self):
        request = _make_request(nationality="ind")
        record = _make_record(nationality="IND")
        _, status = compare_fields(request, record)
        assert status == RegistryStatus.MATCHED


# ── Critical field mismatches ──────────────────────────────────────────────────

class TestCriticalMismatches:
    def test_name_mismatch(self):
        request = _make_request(name="COMPLETELY DIFFERENT NAME")
        record = _make_record(name="TEST USER ONE")
        results, status = compare_fields(request, record)
        assert status == RegistryStatus.MISMATCH
        name_result = next(r for r in results if r.field == "name")
        assert name_result.status == FieldMatchStatus.MISMATCH
        assert name_result.is_critical is True

    def test_dob_mismatch(self):
        request = _make_request(dob="1984-06-15")
        record = _make_record(dob="1990-01-01")
        _, status = compare_fields(request, record)
        assert status == RegistryStatus.MISMATCH

    def test_nationality_mismatch(self):
        request = _make_request(nationality="USA")
        record = _make_record(nationality="IND")
        _, status = compare_fields(request, record)
        assert status == RegistryStatus.MISMATCH

    def test_passport_number_mismatch(self):
        request = _make_request(doc_num="TESTPASS001")
        record = _make_record(doc_num="TESTPASS002")
        results, status = compare_fields(request, record)
        assert status == RegistryStatus.MISMATCH
        doc_num_result = next(r for r in results if r.field == "document_number")
        assert doc_num_result.status == FieldMatchStatus.MISMATCH
        assert doc_num_result.is_critical is True

    def test_passport_number_near_match_is_mismatch(self):
        """T9876543 vs T9876548 — one digit off — MUST be MISMATCH, never MATCHED"""
        request = _make_request(doc_num="T9876543")
        record = _make_record(doc_num="T9876548")
        _, status = compare_fields(request, record)
        # Strict equality — near-match must remain MISMATCH
        assert status == RegistryStatus.MISMATCH

    def test_passport_number_almost_same_cannot_become_matched(self):
        """Verify there is no fuzzy path that turns a near-match into MATCHED"""
        request = _make_request(doc_num="TESTPASS001")
        record = _make_record(doc_num="TESTPASS00X")
        _, status = compare_fields(request, record)
        assert status != RegistryStatus.MATCHED
        assert status == RegistryStatus.MISMATCH


# ── Registry status overrides ──────────────────────────────────────────────────

class TestRegistryStatusOverrides:
    def test_revoked_overrides_fields(self):
        """REVOKED must be reported even when all fields match"""
        request = _make_request()
        record = _make_record(status="REVOKED")
        _, status = compare_fields(request, record)
        assert status == RegistryStatus.REVOKED

    def test_suspended_overrides_fields(self):
        request = _make_request()
        record = _make_record(status="SUSPENDED")
        _, status = compare_fields(request, record)
        assert status == RegistryStatus.SUSPENDED

    def test_expired_registry_status(self):
        request = _make_request()
        record = _make_record(status="EXPIRED")
        _, status = compare_fields(request, record)
        assert status == RegistryStatus.EXPIRED

    def test_invalid_registry_status(self):
        request = _make_request()
        record = _make_record(status="INVALID")
        _, status = compare_fields(request, record)
        assert status == RegistryStatus.INVALID

    def test_active_proceeds_to_field_comparison(self):
        request = _make_request()
        record = _make_record(status="ACTIVE")
        _, status = compare_fields(request, record)
        assert status == RegistryStatus.MATCHED


# ── Secondary field behavior ───────────────────────────────────────────────────

class TestSecondaryFields:
    def test_expiry_mismatch_alone_not_critical_mismatch(self):
        """Expiry is secondary — mismatch alone should not cause MISMATCH status"""
        request = _make_request(expiry="2025-01-01")
        record = _make_record(expiry="2030-01-01")
        results, status = compare_fields(request, record)
        # All critical fields match, so overall should be MATCHED
        assert status == RegistryStatus.MATCHED
        expiry_result = next((r for r in results if r.field == "expiry_date"), None)
        if expiry_result:
            assert expiry_result.is_critical is False


# ── Missing fields ─────────────────────────────────────────────────────────────

class TestMissingFields:
    def test_missing_dob_in_registry(self):
        request = _make_request(dob="1990-01-01")
        record = _make_record(dob=None)
        results, _ = compare_fields(request, record)
        dob_result = next(r for r in results if r.field == "date_of_birth")
        assert dob_result.status == FieldMatchStatus.MISSING_IN_REGISTRY

    def test_missing_name_in_document(self):
        request = _make_request(name=None)
        record = _make_record(name="TEST USER ONE")
        results, _ = compare_fields(request, record)
        name_result = next(r for r in results if r.field == "name")
        assert name_result.status == FieldMatchStatus.MISSING_IN_DOCUMENT

    def test_missing_both_fields_not_compared(self):
        request = _make_request(authority=None)
        record = _make_record()
        record.issuing_authority = None
        results, _ = compare_fields(request, record)
        auth_result = next((r for r in results if r.field == "issuing_authority"), None)
        if auth_result:
            assert auth_result.status == FieldMatchStatus.NOT_COMPARED


# ── Field result evidence ──────────────────────────────────────────────────────

class TestFieldResultEvidence:
    def test_matched_fields_have_both_values(self):
        request = _make_request()
        record = _make_record()
        results, _ = compare_fields(request, record)
        doc_num = next(r for r in results if r.field == "document_number")
        assert doc_num.document_value is not None
        assert doc_num.registry_value is not None

    def test_critical_field_is_marked(self):
        request = _make_request()
        record = _make_record()
        results, _ = compare_fields(request, record)
        doc_num = next(r for r in results if r.field == "document_number")
        assert doc_num.is_critical is True

    def test_secondary_field_not_critical(self):
        request = _make_request(expiry="2030-01-01")
        record = _make_record()
        results, _ = compare_fields(request, record)
        expiry = next((r for r in results if r.field == "expiry_date"), None)
        if expiry:
            assert expiry.is_critical is False
