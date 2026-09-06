"""
backend/tests/test_national_id_cross_document.py

Tests for Cross-Document Intelligence involving National ID:
- Passport <-> National ID relationship profile
- Driving License <-> National ID relationship profile
- Full DOB vs. Year-of-Birth comparison (CONSISTENT_YEAR vs. MISMATCH)
- Upload order independence
- Strict identifier isolation (National ID number is never compared with Passport/DL numbers)
"""
import pytest
from app.schemas.cross_document import RelationshipStatus
from app.services.case.verification_case import CaseDocument
from app.services.cross_document.cross_document_engine import (
    CrossDocumentVerificationEngine,
)
from app.services.risk.risk_evidence import EvidenceSeverity


class TestNationalIdCrossDocument:
    def test_passport_national_id_full_match(self):
        engine = CrossDocumentVerificationEngine()

        doc_passport = CaseDocument(
            document_id="DOC-PASS-01",
            document_type="passport",
            verification_id="vid-p1",
            traveler_data={
                "name": "RAHUL SHARMA",
                "date_of_birth": "1992-05-15",
                "document_number": "P1234567",
            },
        )
        doc_nid = CaseDocument(
            document_id="DOC-NID-01",
            document_type="national_id",
            verification_id="vid-n1",
            traveler_data={
                "name": "RAHUL SHARMA",
                "date_of_birth": "1992-05-15",
                "identity_number": "987654321098",
            },
        )

        evidence, m6_items = engine.evaluate_pair(doc_passport, doc_nid)

        assert len(evidence) == 2
        name_ev = next(e for e in evidence if e.source_document.field == "name")
        dob_ev = next(e for e in evidence if e.source_document.field == "date_of_birth")

        assert name_ev.status == RelationshipStatus.MATCHED
        assert dob_ev.status == RelationshipStatus.MATCHED
        # No adverse M6 risk items
        assert len(m6_items) == 0

    def test_passport_national_id_year_only_consistency(self):
        """
        Crucial requirement:
        National ID: 1995
        Passport: 1995-06-15
        This is NOT a mismatch -> CONSISTENT_YEAR (severity NONE).
        """
        engine = CrossDocumentVerificationEngine()

        doc_passport = CaseDocument(
            document_id="DOC-PASS-02",
            document_type="passport",
            verification_id="vid-p2",
            traveler_data={
                "name": "PRIYA PATEL",
                "date_of_birth": "1995-06-15",
                "document_number": "P7654321",
            },
        )
        doc_nid = CaseDocument(
            document_id="DOC-NID-02",
            document_type="national_id",
            verification_id="vid-n2",
            traveler_data={
                "name": "PRIYA PATEL",
                "year_of_birth": "1995",
                "identity_number": "234567890123",
            },
        )

        evidence, m6_items = engine.evaluate_pair(doc_passport, doc_nid)

        dob_ev = next(e for e in evidence if e.source_document.field in ("date_of_birth", "year_of_birth"))
        assert dob_ev.status == RelationshipStatus.CONSISTENT_YEAR
        assert dob_ev.severity == "NONE"
        # Zero adverse M6 risk items for year consistency!
        assert len([item for item in m6_items if "dob" in item.signal]) == 0

    def test_passport_national_id_year_mismatch(self):
        """
        National ID: 1995
        Passport: 1996-06-15
        -> MISMATCH (severity HIGH).
        """
        engine = CrossDocumentVerificationEngine()

        doc_passport = CaseDocument(
            document_id="DOC-PASS-03",
            document_type="passport",
            verification_id="vid-p3",
            traveler_data={
                "name": "PRIYA PATEL",
                "date_of_birth": "1996-06-15",
                "document_number": "P7654321",
            },
        )
        doc_nid = CaseDocument(
            document_id="DOC-NID-03",
            document_type="national_id",
            verification_id="vid-n3",
            traveler_data={
                "name": "PRIYA PATEL",
                "year_of_birth": "1995",
                "identity_number": "234567890123",
            },
        )

        evidence, m6_items = engine.evaluate_pair(doc_passport, doc_nid)

        dob_ev = next(e for e in evidence if e.source_document.field in ("date_of_birth", "year_of_birth"))
        assert dob_ev.status == RelationshipStatus.MISMATCH
        assert dob_ev.severity == "HIGH"
        assert any("cross_doc" in item.signal and item.severity == EvidenceSeverity.HIGH for item in m6_items)

    def test_upload_order_independence(self):
        engine = CrossDocumentVerificationEngine()

        doc_pass = CaseDocument(
            document_id="DOC-P",
            document_type="passport",
            verification_id="vid-p",
            traveler_data={"name": "RAHUL SHARMA", "date_of_birth": "1992-05-15"},
        )
        doc_nid = CaseDocument(
            document_id="DOC-N",
            document_type="national_id",
            verification_id="vid-n",
            traveler_data={"name": "RAHUL SHARMA", "year_of_birth": "1992"},
        )

        ev_forward, _ = engine.evaluate_pair(doc_pass, doc_nid)
        ev_reverse, _ = engine.evaluate_pair(doc_nid, doc_pass)

        assert len(ev_forward) == len(ev_reverse) == 2
        statuses_forward = {e.source_document.field: e.status for e in ev_forward}
        statuses_reverse = {e.source_document.field: e.status for e in ev_reverse}
        assert statuses_forward == statuses_reverse

    def test_driving_license_national_id_relationship(self):
        engine = CrossDocumentVerificationEngine()

        doc_dl = CaseDocument(
            document_id="DOC-DL-01",
            document_type="driving_license",
            verification_id="vid-dl",
            traveler_data={"name": "RAHUL SHARMA", "date_of_birth": "1992-05-15", "license_number": "DL0420110012345"},
        )
        doc_nid = CaseDocument(
            document_id="DOC-NID-01",
            document_type="national_id",
            verification_id="vid-nid",
            traveler_data={"name": "RAHUL SHARMA", "date_of_birth": "1992-05-15", "identity_number": "987654321098"},
        )

        evidence, m6_items = engine.evaluate_pair(doc_dl, doc_nid)
        assert len(evidence) == 2
        for ev in evidence:
            assert ev.status == RelationshipStatus.MATCHED

    def test_strict_identifier_isolation(self):
        """
        National ID number must NEVER be compared against Passport number or DL number.
        They belong to completely separate identifier namespaces.
        """
        engine = CrossDocumentVerificationEngine()

        doc_pass = CaseDocument(
            document_id="DOC-P",
            document_type="passport",
            verification_id="vid-p",
            traveler_data={"name": "RAHUL SHARMA", "document_number": "P9876543"},
        )
        doc_nid = CaseDocument(
            document_id="DOC-N",
            document_type="national_id",
            verification_id="vid-n",
            traveler_data={"name": "RAHUL SHARMA", "identity_number": "123456789012"},
        )

        evidence, _ = engine.evaluate_pair(doc_pass, doc_nid)

        # None of the relationship definitions should compare document numbers
        fields_compared = [(e.source_document.field, e.target_document.field) for e in evidence]
        assert ("identity_number", "document_number") not in fields_compared
        assert ("docNumber", "docNumber") not in fields_compared
