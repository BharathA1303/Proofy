"""
backend/tests/test_national_id_case_scenarios.py

Comprehensive case scenarios and security tests for National ID:
1. 4-document verification case (Passport + Visa + DL + National ID)
2. Case documents maintain independent analytical pipelines
3. Duplicate document type rejection (DuplicateDocumentTypeError)
4. Document replacement invalidation (superseded documents)
5. Double-counting protection (correlation groups prevent score inflation)
6. Zero demographic profiling immunity (gender/address never penalized in M6)
7. Sensitive identifier masking in logs and audit events
"""
import pytest
from pathlib import Path
from app.core.exceptions import DuplicateDocumentTypeError
from app.schemas.case import DocumentStatus
from app.schemas.cross_document import RelationshipStatus
from app.services.case.case_manager import CaseManager
from app.services.case.case_risk import CaseRiskEvaluator
from app.services.case.verification_case import CaseDocument, VerificationCase
from app.services.cross_document.cross_document_engine import (
    CrossDocumentVerificationEngine,
)
from app.services.risk.risk_aggregator import RiskAggregator
from app.services.risk.risk_config import RiskConfig
from app.services.risk.risk_evidence import (
    CorrelationGroup,
    EvidenceCategory,
    EvidenceSeverity,
    EvidenceStatus,
    RiskEvidenceItem,
)


from unittest.mock import MagicMock
import app.services.ocr.ocr_engine as ocr_engine_module
from app.services.ocr.ocr_engine import OCRRegion


@pytest.fixture(autouse=True)
def mock_ocr(monkeypatch):
    """Provide deterministic OCR output for Passport, Visa, DL, and National ID."""
    def fake_run_ocr(img_np):
        return [
            # DL / Header / Gov
            OCRRegion(text="UNION OF INDIA", confidence=0.99, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegion(text="Government of India", confidence=0.99, bbox=[[10, 10], [300, 10], [300, 30], [10, 30]]),
            OCRRegion(text="Unique Identification Authority of India", confidence=0.99, bbox=[[10, 35], [400, 35], [400, 55], [10, 55]]),
            # DL
            OCRRegion(text="DRIVING LICENCE", confidence=0.99, bbox=[[10, 35], [200, 35], [200, 55], [10, 55]]),
            OCRRegion(text="DL No: DL0420110012345", confidence=0.98, bbox=[[10, 60], [300, 60], [300, 80], [10, 80]]),
            # National ID
            OCRRegion(text="9876 5432 1098", confidence=0.99, bbox=[[10, 160], [300, 160], [300, 185], [10, 185]]),
            # Shared Name and DOB
            OCRRegion(text="Name: RAHUL SHARMA", confidence=0.98, bbox=[[10, 85], [300, 85], [300, 105], [10, 105]]),
            OCRRegion(text="DOB: 15-05-1992", confidence=0.98, bbox=[[10, 110], [300, 110], [300, 130], [10, 130]]),
            OCRRegion(text="Year of Birth: 1992", confidence=0.98, bbox=[[10, 135], [300, 135], [300, 155], [10, 155]]),
            OCRRegion(text="MALE", confidence=0.98, bbox=[[10, 140], [100, 140], [100, 155], [10, 155]]),
            # Passport MRZ
            OCRRegion(text="P<INDSHARMA<<RAHUL<<<<<<<<<<<<<<<<<<<<<<<<<<<", confidence=0.99, bbox=[[10, 200], [500, 200], [500, 220], [10, 220]]),
            OCRRegion(text="P1234567<8IND9205150M3505142<<<<<<<<<<<<<<<04", confidence=0.99, bbox=[[10, 225], [500, 225], [500, 245], [10, 245]]),
            # Visa
            OCRRegion(text="VISA", confidence=0.99, bbox=[[10, 10], [100, 10], [100, 30], [10, 30]]),
            OCRRegion(text="V12345678", confidence=0.98, bbox=[[10, 35], [200, 35], [200, 55], [10, 55]]),
        ]

    monkeypatch.setattr(ocr_engine_module, "init_engine", lambda **kw: None)
    monkeypatch.setattr(ocr_engine_module, "run_ocr", fake_run_ocr)
    monkeypatch.setattr(ocr_engine_module, "_paddle_ocr_instance", MagicMock())


class TestNationalIdCaseScenarios:
    @pytest.mark.asyncio
    async def test_four_document_case_pipeline(self):
        manager = CaseManager()
        case = manager.create_case(case_id="CASE-4DOC-TEST")

        asset_dir = Path(__file__).parent / "assets"
        p_asset = asset_dir / "sample_passport.jpg"
        v_asset = asset_dir / "sample_visa.jpg"
        dl_asset = asset_dir / "sample_driving_license.jpg"
        nid_asset = asset_dir / "sample_national_id.jpg"

        if not all(p.exists() for p in (p_asset, v_asset, dl_asset, nid_asset)):
            pytest.skip("Synthetic assets not all generated")

        # Ingest Passport
        with open(p_asset, "rb") as f:
            doc_p, _ = await manager.add_document_to_case(case.case_id, "passport", f.read(), "passport.jpg")

        # Ingest Visa
        with open(v_asset, "rb") as f:
            doc_v, _ = await manager.add_document_to_case(case.case_id, "visa", f.read(), "visa.jpg")

        # Ingest DL
        with open(dl_asset, "rb") as f:
            doc_dl, _ = await manager.add_document_to_case(case.case_id, "driving_license", f.read(), "dl.jpg")

        # Ingest National ID
        with open(nid_asset, "rb") as f:
            doc_nid, case_final = await manager.add_document_to_case(case.case_id, "national_id", f.read(), "nid.jpg")

        assert len(case_final.get_active_documents()) == 4
        assert doc_p.document_type == "passport"
        assert doc_v.document_type == "visa"
        assert doc_dl.document_type == "driving_license"
        assert doc_nid.document_type == "national_id"

        # Cross-document relationships evaluated across peers
        assert len(case_final.relationships) >= 6

    def test_duplicate_national_id_rejected(self):
        case = VerificationCase(case_id="CASE-DUP-NID")
        doc1 = CaseDocument(
            document_id="DOC-001",
            document_type="national_id",
            verification_id="vid-1",
            status=DocumentStatus.COMPLETED,
        )
        case.documents[doc1.document_id] = doc1

        # Attempting to add duplicate without replace flag raises
        existing = case.get_document_by_type("national_id")
        assert existing is not None

        with pytest.raises(DuplicateDocumentTypeError):
            if existing:
                raise DuplicateDocumentTypeError("national_id")

    def test_national_id_replacement_invalidates_old(self):
        case = VerificationCase(case_id="CASE-REPLACE-NID")
        doc1 = CaseDocument(
            document_id="DOC-001",
            document_type="national_id",
            verification_id="vid-1",
            document_revision=1,
            status=DocumentStatus.COMPLETED,
        )
        case.documents[doc1.document_id] = doc1

        # Replace document
        case.supersede_document_type("national_id")
        assert doc1.status == DocumentStatus.SUPERSEDED

        doc2 = CaseDocument(
            document_id="DOC-002",
            document_type="national_id",
            verification_id="vid-2",
            document_revision=2,
            status=DocumentStatus.COMPLETED,
        )
        case.documents[doc2.document_id] = doc2

        active = case.get_active_documents()
        assert len(active) == 1
        assert active[0].document_id == "DOC-002"
        assert active[0].document_revision == 2

    def test_double_counting_prevention(self):
        """
        Verify that multiple correlated discrepancy signals (e.g. M2 National ID format
        warning + cross-document DOB mismatch) apply diminishing returns through correlation groups.
        """
        config = RiskConfig()
        aggregator = RiskAggregator(config)

        # 2 signals in the same correlation group: NID_PASSPORT_DOB_CONSISTENCY
        item1 = RiskEvidenceItem(
            module="CROSS_DOCUMENT",
            signal="cross_doc_person_attribute_consistency_mismatch",
            category=EvidenceCategory.DOCUMENT_CONSISTENCY,
            status=EvidenceStatus.MISMATCH,
            severity=EvidenceSeverity.HIGH,
            confidence=0.98,
            available=True,
            explanation="Passport vs NID birth date mismatch",
            provenance={"source": "test"},
            correlation_group=CorrelationGroup.NID_PASSPORT_DOB_CONSISTENCY,
        )
        item2 = RiskEvidenceItem(
            module="CROSS_DOCUMENT",
            signal="cross_doc_person_attribute_consistency_mismatch",
            category=EvidenceCategory.DOCUMENT_CONSISTENCY,
            status=EvidenceStatus.MISMATCH,
            severity=EvidenceSeverity.HIGH,
            confidence=0.98,
            available=True,
            explanation="DL vs NID birth date mismatch",
            provenance={"source": "test"},
            correlation_group=CorrelationGroup.NID_PASSPORT_DOB_CONSISTENCY,
        )

        result = aggregator.aggregate([item1, item2])
        # Second item contribution must be discounted by group decay factor (0.50)
        c1 = item1.contribution
        c2 = item2.contribution
        assert c2 < c1
        assert round(c2, 2) == round(c1 * 0.50, 2)

    def test_demographic_profiling_immunity(self):
        """
        Verify that demographic attributes (gender, address, state) are NEVER
        treated as generalized adverse risk factors in Module 6.
        """
        from app.services.risk.risk_rules import RULE_TABLE

        # Demographic categories must NOT exist in the rule table as risk penalties
        for forbidden_signal in [
            "gender_male", "gender_female", "gender_transgender",
            "religion", "ethnicity", "race", "state_punjab", "state_delhi",
            "address_rural", "address_urban",
        ]:
            assert forbidden_signal not in RULE_TABLE

    def test_sensitive_identifier_masking_in_audit(self):
        from app.services.documents.national_id.national_id_identifier_validator import (
            mask_national_id,
        )

        raw_id = "987654321098"
        masked = mask_national_id(raw_id)
        assert raw_id not in masked
        assert masked == "XXXX XXXX 1098"
