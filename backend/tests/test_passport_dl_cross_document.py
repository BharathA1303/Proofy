"""
backend/tests/test_passport_dl_cross_document.py

Unit and integration tests for Passport ↔ Driving License cross-document intelligence.
"""
import pytest
from app.schemas.cross_document import RelationshipStatus
from app.services.case.verification_case import CaseDocument
from app.services.cross_document.cross_document_engine import cross_document_engine
from app.services.cross_document.relationship_registry import relationship_registry


def _make_case_doc(doc_id: str, doc_type: str, data: dict) -> CaseDocument:
    return CaseDocument(
        document_id=doc_id,
        document_type=doc_type,
        verification_id=f"vid-{doc_id}",
        traveler_data=data,
    )


class TestPassportDLCrossDocument:
    def test_relationship_profile_resolution_order_independence(self):
        # Forward: DL (source) -> Passport (target)
        res_direct = relationship_registry.resolve_profile("driving_license", "passport")
        assert res_direct is not None
        prof_direct, is_rev_direct = res_direct
        assert is_rev_direct is False
        assert prof_direct.source_document_type == "driving_license"
        assert prof_direct.target_document_type == "passport"

        # Reverse: Passport -> DL
        res_rev = relationship_registry.resolve_profile("passport", "driving_license")
        assert res_rev is not None
        prof_rev, is_rev = res_rev
        assert is_rev is True
        assert prof_rev.source_document_type == "driving_license"
        assert prof_rev.target_document_type == "passport"

    def test_passport_number_is_not_compared_to_license_number(self):
        profile, _ = relationship_registry.resolve_profile("driving_license", "passport")
        fields = [(d.source_field, d.target_field) for d in profile.definitions]
        assert ("license_number", "document_number") not in fields
        assert ("docNumber", "docNumber") not in fields
        assert ("docNumber", "document_number") not in fields
        # Only name and dob are compared
        assert ("name", "name") in fields
        assert ("date_of_birth", "date_of_birth") in fields

    def test_matching_passport_and_dl(self):
        doc_p = _make_case_doc(
            "DOC-001",
            "passport",
            {
                "name": "RAHUL SHARMA",
                "date_of_birth": "1992-05-15",
                "document_number": "P1234567",
            },
        )
        doc_dl = _make_case_doc(
            "DOC-002",
            "driving_license",
            {
                "name": "RAHUL SHARMA",
                "date_of_birth": "1992-05-15",
                "license_number": "DL0420110012345",
            },
        )

        evidence, m6_items = cross_document_engine.evaluate_pair(doc_p, doc_dl)

        assert len(evidence) == 2
        statuses = {e.relationship_type.value: e.status for e in evidence}
        assert statuses["PERSON_NAME_CONSISTENCY"] == RelationshipStatus.MATCHED
        assert statuses["PERSON_ATTRIBUTE_CONSISTENCY"] == RelationshipStatus.MATCHED
        # Positive / matched relationships emit zero risk items to M6
        assert len(m6_items) == 0

    def test_dob_mismatch_produces_high_severity_evidence(self):
        doc_p = _make_case_doc(
            "DOC-001",
            "passport",
            {
                "name": "RAHUL SHARMA",
                "date_of_birth": "1992-05-15",
                "document_number": "P1234567",
            },
        )
        doc_dl = _make_case_doc(
            "DOC-002",
            "driving_license",
            {
                "name": "RAHUL SHARMA",
                "date_of_birth": "1993-06-20",  # Mismatched DOB
                "license_number": "DL0420110012345",
            },
        )

        evidence, m6_items = cross_document_engine.evaluate_pair(doc_p, doc_dl)

        dob_ev = [e for e in evidence if e.relationship_type.value == "PERSON_ATTRIBUTE_CONSISTENCY"][0]
        assert dob_ev.status == RelationshipStatus.MISMATCH
        assert str(dob_ev.severity).upper() == "HIGH"
        assert len(m6_items) >= 1

    def test_name_formatting_difference_returns_partial_match(self):
        doc_p = _make_case_doc(
            "DOC-001",
            "passport",
            {
                "name": "RAHUL KUMAR SHARMA",
                "date_of_birth": "1992-05-15",
            },
        )
        doc_dl = _make_case_doc(
            "DOC-002",
            "driving_license",
            {
                "name": "RAHUL SHARMA",  # Token subset
                "date_of_birth": "1992-05-15",
            },
        )

        evidence, m6_items = cross_document_engine.evaluate_pair(doc_p, doc_dl)

        name_ev = [e for e in evidence if e.relationship_type.value == "PERSON_NAME_CONSISTENCY"][0]
        assert name_ev.status == RelationshipStatus.PARTIAL_MATCH

    def test_order_independence_evaluation(self):
        p_data = {"name": "RAHUL SHARMA", "date_of_birth": "1992-05-15"}
        dl_data = {"name": "RAHUL SHARMA", "date_of_birth": "1992-05-15"}

        doc_p = _make_case_doc("DOC-001", "passport", p_data)
        doc_dl = _make_case_doc("DOC-002", "driving_license", dl_data)

        ev_forward, _ = cross_document_engine.evaluate_pair(doc_p, doc_dl)
        ev_reverse, _ = cross_document_engine.evaluate_pair(doc_dl, doc_p)

        assert len(ev_forward) == len(ev_reverse)
        for ef, er in zip(ev_forward, ev_reverse):
            assert ef.status == er.status
            assert ef.relationship_type == er.relationship_type
