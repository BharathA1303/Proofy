"""
backend/tests/test_border_permit_cross_document.py

Tests for Cross-Document Intelligence involving Border Permits:
1. Passport <-> Border Permit (Linked passport binding, Name, DOB)
2. National ID <-> Border Permit (Name, DOB / Year of Birth)
3. Upload order independence
"""
from app.schemas.cross_document import RelationshipStatus, RelationshipType
from app.services.case.verification_case import CaseDocument
from app.services.cross_document.cross_document_engine import (
    CrossDocumentVerificationEngine,
)


class TestBorderPermitCrossDocument:
    def test_passport_border_permit_all_matched(self):
        engine = CrossDocumentVerificationEngine()

        doc_p = CaseDocument(
            document_id="DOC-PASSPORT",
            document_type="passport",
            verification_id="vid-p",
            traveler_data={
                "name": "ALEX DUPONT",
                "document_number": "P1234567",
                "date_of_birth": "1990-08-12",
            },
        )
        doc_bp = CaseDocument(
            document_id="DOC-BP",
            document_type="border_permit",
            verification_id="vid-bp",
            traveler_data={
                "name": "ALEX DUPONT",
                "permit_number": "BP2026000123",
                "passport_number": "P1234567",
                "date_of_birth": "1990-08-12",
            },
        )

        evidence, m6_items = engine.evaluate_pair(doc_p, doc_bp)

        assert len(evidence) == 3

        # 1. Identifier binding (passport number)
        binding_ev = next(e for e in evidence if e.relationship_type == RelationshipType.IDENTIFIER_BINDING)
        assert binding_ev.status == RelationshipStatus.MATCHED

        # 2. Name consistency
        name_ev = next(e for e in evidence if e.relationship_type == RelationshipType.PERSON_NAME_CONSISTENCY)
        assert name_ev.status == RelationshipStatus.MATCHED

        # 3. DOB consistency
        dob_ev = next(e for e in evidence if e.relationship_type == RelationshipType.PERSON_ATTRIBUTE_CONSISTENCY)
        assert dob_ev.status == RelationshipStatus.MATCHED

    def test_passport_border_permit_passport_number_mismatch(self):
        engine = CrossDocumentVerificationEngine()

        doc_p = CaseDocument(
            document_id="DOC-PASSPORT",
            document_type="passport",
            verification_id="vid-p",
            traveler_data={
                "name": "ALEX DUPONT",
                "document_number": "P1234567",
                "date_of_birth": "1990-08-12",
            },
        )
        # Border permit claims passport P9999999
        doc_bp = CaseDocument(
            document_id="DOC-BP",
            document_type="border_permit",
            verification_id="vid-bp",
            traveler_data={
                "name": "ALEX DUPONT",
                "permit_number": "BP2026000123",
                "passport_number": "P9999999",
                "date_of_birth": "1990-08-12",
            },
        )

        evidence, m6_items = engine.evaluate_pair(doc_p, doc_bp)
        binding_ev = next(e for e in evidence if e.relationship_type == RelationshipType.IDENTIFIER_BINDING)
        assert binding_ev.status == RelationshipStatus.MISMATCH

    def test_passport_border_permit_dob_mismatch(self):
        engine = CrossDocumentVerificationEngine()

        doc_p = CaseDocument(
            document_id="DOC-PASSPORT",
            document_type="passport",
            verification_id="vid-p",
            traveler_data={
                "name": "ALEX DUPONT",
                "document_number": "P1234567",
                "date_of_birth": "1990-08-12",
            },
        )
        # Border permit has different birth date
        doc_bp = CaseDocument(
            document_id="DOC-BP",
            document_type="border_permit",
            verification_id="vid-bp",
            traveler_data={
                "name": "ALEX DUPONT",
                "permit_number": "BP2026000123",
                "passport_number": "P1234567",
                "date_of_birth": "1995-05-15",
            },
        )

        evidence, m6_items = engine.evaluate_pair(doc_p, doc_bp)
        dob_ev = next(e for e in evidence if e.relationship_type == RelationshipType.PERSON_ATTRIBUTE_CONSISTENCY)
        assert dob_ev.status == RelationshipStatus.MISMATCH

    def test_national_id_border_permit_relationship(self):
        engine = CrossDocumentVerificationEngine()

        doc_nid = CaseDocument(
            document_id="DOC-NID",
            document_type="national_id",
            verification_id="vid-nid",
            traveler_data={
                "name": "ALEX DUPONT",
                "identity_number": "987654321098",
                "year_of_birth": "1990",
            },
        )
        doc_bp = CaseDocument(
            document_id="DOC-BP",
            document_type="border_permit",
            verification_id="vid-bp",
            traveler_data={
                "name": "ALEX DUPONT",
                "permit_number": "BP2026000123",
                "date_of_birth": "1990-08-12",
            },
        )

        evidence, m6_items = engine.evaluate_pair(doc_nid, doc_bp)
        assert len(evidence) == 2

        name_ev = next(e for e in evidence if e.relationship_type == RelationshipType.PERSON_NAME_CONSISTENCY)
        assert name_ev.status == RelationshipStatus.MATCHED

        dob_ev = next(e for e in evidence if e.relationship_type == RelationshipType.PERSON_ATTRIBUTE_CONSISTENCY)
        assert dob_ev.status in (RelationshipStatus.MATCHED, RelationshipStatus.CONSISTENT_YEAR)

    def test_upload_order_independence(self):
        engine = CrossDocumentVerificationEngine()

        doc_p = CaseDocument(
            document_id="DOC-P",
            document_type="passport",
            verification_id="vid-p",
            traveler_data={"name": "ALEX DUPONT", "document_number": "P1234567", "dob": "1990-08-12"},
        )
        doc_bp = CaseDocument(
            document_id="DOC-BP",
            document_type="border_permit",
            verification_id="vid-bp",
            traveler_data={"name": "ALEX DUPONT", "passport_number": "P1234567", "dob": "1990-08-12"},
        )

        ev_forward, _ = engine.evaluate_pair(doc_p, doc_bp)
        ev_reverse, _ = engine.evaluate_pair(doc_bp, doc_p)

        assert len(ev_forward) == len(ev_reverse)
        for f, r in zip(ev_forward, ev_reverse):
            assert f.status == r.status
            assert f.relationship_type == r.relationship_type
