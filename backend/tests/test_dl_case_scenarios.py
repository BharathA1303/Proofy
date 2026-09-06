"""
backend/tests/test_dl_case_scenarios.py

End-to-end multi-document Case scenarios involving Driving Licenses.
Tests 3-document cases (Passport + Visa + DL), duplicate prevention,
replacement invalidation, double-counting protection, and privacy constraints.
"""
from pathlib import Path
import pytest
from app.core.exceptions import DuplicateDocumentTypeError
from app.schemas.case import CaseStatus, DocumentStatus
from app.services.case.case_manager import CaseManager
from app.services.case.case_risk import case_risk_evaluator
from app.services.case.case_store import case_store
from app.services.case.verification_case import CaseDocument, VerificationCase


from unittest.mock import MagicMock
import app.services.ocr.ocr_engine as ocr_engine_module
from app.services.ocr.ocr_engine import OCRRegion


@pytest.fixture(autouse=True)
def mock_ocr(monkeypatch):
    """Prevent loading neural OCR models and provide deterministic test OCR output."""
    def fake_run_ocr(img_np):
        return [
            OCRRegion(text="UNION OF INDIA", confidence=0.99, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegion(text="DRIVING LICENCE", confidence=0.99, bbox=[[10, 35], [200, 35], [200, 55], [10, 55]]),
            OCRRegion(text="DL No: DL0420110012345", confidence=0.98, bbox=[[10, 60], [300, 60], [300, 80], [10, 80]]),
            OCRRegion(text="Name: RAHUL SHARMA", confidence=0.98, bbox=[[10, 85], [300, 85], [300, 105], [10, 105]]),
            OCRRegion(text="DOB: 15-05-1992", confidence=0.98, bbox=[[10, 110], [300, 110], [300, 130], [10, 130]]),
            OCRRegion(text="Issued: 15-05-2011", confidence=0.98, bbox=[[10, 135], [300, 135], [300, 155], [10, 155]]),
            OCRRegion(text="Valid Till: 14-05-2035", confidence=0.98, bbox=[[10, 160], [300, 160], [300, 180], [10, 180]]),
            OCRRegion(text="P<INDSHARMA<<RAHUL<<<<<<<<<<<<<<<<<<<<<<<<<<<", confidence=0.99, bbox=[[10, 200], [500, 200], [500, 220], [10, 220]]),
            OCRRegion(text="P1234567<8IND9205150M3505142<<<<<<<<<<<<<<<04", confidence=0.99, bbox=[[10, 225], [500, 225], [500, 245], [10, 245]]),
            OCRRegion(text="VISA", confidence=0.99, bbox=[[10, 10], [100, 10], [100, 30], [10, 30]]),
            OCRRegion(text="V12345678", confidence=0.98, bbox=[[10, 35], [200, 35], [200, 55], [10, 55]]),
        ]

    monkeypatch.setattr(ocr_engine_module, "init_engine", lambda **kw: None)
    monkeypatch.setattr(ocr_engine_module, "run_ocr", fake_run_ocr)
    monkeypatch.setattr(ocr_engine_module, "_paddle_ocr_instance", MagicMock())


@pytest.fixture
def case_manager():
    return CaseManager()


@pytest.fixture
def sample_dl_bytes():
    asset_path = Path(__file__).parent / "assets" / "sample_driving_license.jpg"
    assert asset_path.exists(), "sample_driving_license.jpg must exist"
    return asset_path.read_bytes()


@pytest.fixture
def sample_passport_bytes():
    asset_path = Path(__file__).parent / "assets" / "sample_passport.jpg"
    assert asset_path.exists(), "sample_passport.jpg must exist"
    return asset_path.read_bytes()


@pytest.fixture
def sample_visa_bytes():
    asset_path = Path(__file__).parent / "assets" / "sample_visa.jpg"
    assert asset_path.exists(), "sample_visa.jpg must exist"
    return asset_path.read_bytes()


class TestDrivingLicenseCaseScenarios:
    @pytest.mark.asyncio
    async def test_scenario_dl_only_in_case(self, case_manager, sample_dl_bytes):
        case = case_manager.create_case()
        doc, updated_case = await case_manager.add_document_to_case(
            case_id=case.case_id,
            document_type="driving_license",
            file_bytes=sample_dl_bytes,
            filename="dl.jpg",
        )

        assert doc.document_type == "driving_license"
        assert doc.status == DocumentStatus.COMPLETED
        assert len(updated_case.documents) == 1
        # No peer documents, so cross-document evidence remains empty
        assert len(updated_case.cross_document_evidence) == 0

    @pytest.mark.asyncio
    async def test_scenario_passport_and_dl_case(self, case_manager, sample_passport_bytes, sample_dl_bytes):
        case = case_manager.create_case()
        doc1, _ = await case_manager.add_document_to_case(
            case_id=case.case_id,
            document_type="passport",
            file_bytes=sample_passport_bytes,
            filename="passport.jpg",
        )
        doc2, updated_case = await case_manager.add_document_to_case(
            case_id=case.case_id,
            document_type="driving_license",
            file_bytes=sample_dl_bytes,
            filename="dl.jpg",
        )

        assert len(updated_case.get_active_documents()) == 2
        # Cross-document relationships evaluated between Passport and DL
        assert len(updated_case.cross_document_evidence) >= 1
        assert updated_case.risk_assessment is not None
        assert "DOC-001" in updated_case.risk_assessment["documents_considered"]
        assert "DOC-002" in updated_case.risk_assessment["documents_considered"]

    @pytest.mark.asyncio
    async def test_scenario_passport_visa_and_dl_three_documents(
        self, case_manager, sample_passport_bytes, sample_visa_bytes, sample_dl_bytes
    ):
        case = case_manager.create_case()
        # Add Passport
        await case_manager.add_document_to_case(
            case_id=case.case_id,
            document_type="passport",
            file_bytes=sample_passport_bytes,
            filename="passport.jpg",
        )
        # Add Visa
        await case_manager.add_document_to_case(
            case_id=case.case_id,
            document_type="visa",
            file_bytes=sample_visa_bytes,
            filename="visa.jpg",
        )
        # Add Driving License
        doc3, updated_case = await case_manager.add_document_to_case(
            case_id=case.case_id,
            document_type="driving_license",
            file_bytes=sample_dl_bytes,
            filename="dl.jpg",
        )

        active_docs = updated_case.get_active_documents()
        assert len(active_docs) == 3
        types = [d.document_type for d in active_docs]
        assert "passport" in types
        assert "visa" in types
        assert "driving_license" in types

        # Risk assessment considers all 3 documents
        risk = updated_case.risk_assessment
        assert risk is not None
        assert len(risk["documents_considered"]) == 3

    @pytest.mark.asyncio
    async def test_scenario_duplicate_dl_prevention(self, case_manager, sample_dl_bytes):
        case = case_manager.create_case()
        await case_manager.add_document_to_case(
            case_id=case.case_id,
            document_type="driving_license",
            file_bytes=sample_dl_bytes,
            filename="dl1.jpg",
        )

        with pytest.raises(DuplicateDocumentTypeError):
            await case_manager.add_document_to_case(
                case_id=case.case_id,
                document_type="driving_license",
                file_bytes=sample_dl_bytes,
                filename="dl2.jpg",
                replace=False,
            )

    @pytest.mark.asyncio
    async def test_scenario_dl_replacement_supersedes_and_invalidates(
        self, case_manager, sample_passport_bytes, sample_dl_bytes
    ):
        case = case_manager.create_case()
        await case_manager.add_document_to_case(
            case_id=case.case_id,
            document_type="passport",
            file_bytes=sample_passport_bytes,
            filename="passport.jpg",
        )
        doc_dl1, _ = await case_manager.add_document_to_case(
            case_id=case.case_id,
            document_type="driving_license",
            file_bytes=sample_dl_bytes,
            filename="dl1.jpg",
        )

        # Replace DL
        doc_dl2, updated_case = await case_manager.add_document_to_case(
            case_id=case.case_id,
            document_type="driving_license",
            file_bytes=sample_dl_bytes,
            filename="dl2.jpg",
            replace=True,
        )

        assert doc_dl2.document_revision == 2
        # Prior DL must be SUPERSEDED
        assert doc_dl1.status == DocumentStatus.SUPERSEDED
        assert doc_dl2.status == DocumentStatus.COMPLETED

        # Evidence referencing the old revision was purged
        for rel in updated_case.relationships:
            assert rel.source_document.document_id != doc_dl1.document_id
            assert rel.target_document.document_id != doc_dl1.document_id
        for ev in updated_case.cross_document_evidence:
            if ev.provenance:
                assert ev.provenance.get("source_document_id") != doc_dl1.document_id
                assert ev.provenance.get("target_document_id") != doc_dl1.document_id

    def test_scenario_double_counting_protection_for_dob(self):
        # Construct case with both M2 DOB check fail and Cross-document DOB mismatch
        case = VerificationCase(case_id="CASE-DOUBLETEST", status=CaseStatus.ACTIVE)
        doc1 = CaseDocument(
            document_id="DOC-001",
            document_type="passport",
            verification_id="vid-test-p1",
            status=DocumentStatus.COMPLETED,
            traveler_data={"name": "RAHUL SHARMA", "dob": "1992-05-15"},
        )
        doc2 = CaseDocument(
            document_id="DOC-002",
            document_type="driving_license",
            verification_id="vid-test-dl1",
            status=DocumentStatus.COMPLETED,
            traveler_data={"name": "RAHUL SHARMA", "dob": "1995-01-01"},
        )
        case.documents = {doc1.document_id: doc1, doc2.document_id: doc2}

        risk_assessment = case_risk_evaluator.evaluate_case_risk(case)
        # Verify score is bounded and doesn't double count
        assert risk_assessment is not None
        assert risk_assessment["risk_score"] <= 50

    def test_scenario_no_demographic_profiling(self):
        # Prove that presence of blood_group, state, address, or vehicle classes does not alter risk
        case1 = VerificationCase(case_id="CASE-NO-DEMO-1", status=CaseStatus.ACTIVE)
        doc1 = CaseDocument(
            document_id="DOC-001",
            document_type="driving_license",
            verification_id="vid-demo-1",
            status=DocumentStatus.COMPLETED,
            traveler_data={
                "name": "RAHUL SHARMA",
                "docNumber": "TESTDL001",
                "dob": "1992-05-15",
                "blood_group": "O+",
                "state": "Delhi",
            },
        )
        case1.documents = {doc1.document_id: doc1}
        risk1 = case_risk_evaluator.evaluate_case_risk(case1)

        case2 = VerificationCase(case_id="CASE-NO-DEMO-2", status=CaseStatus.ACTIVE)
        doc2 = CaseDocument(
            document_id="DOC-001",
            document_type="driving_license",
            verification_id="vid-demo-2",
            status=DocumentStatus.COMPLETED,
            traveler_data={
                "name": "RAHUL SHARMA",
                "docNumber": "TESTDL001",
                "dob": "1992-05-15",
                "blood_group": "AB-",
                "state": "Kerala",
            },
        )
        case2.documents = {doc2.document_id: doc2}
        risk2 = case_risk_evaluator.evaluate_case_risk(case2)

        # Risk score must be completely identical regardless of demographic fields
        assert risk1["risk_score"] == risk2["risk_score"]
