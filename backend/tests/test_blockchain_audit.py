"""
backend/tests/test_blockchain_audit.py

Unit and integration tests for Phase 12 Blockchain Audit & Cryptographic Integrity.
Tests:
  - Genesis block initialization
  - Cryptographic hash chaining
  - Canonical evidence serialization & SHA-256 hashing
  - Immutability and tampering detection
  - Evidence integrity verification (match vs. tampering)
  - Officer decision anchoring
  - Failure resilience (ledger fault tolerance)
  - API endpoint integration
"""
import copy
import json
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.schemas.evidence import (
    EvidenceModule,
    EvidencePackage,
    EvidenceSeverity,
    EvidenceStatus,
    NormalizedEvidenceItem,
)
from app.schemas.audit import BlockchainEventType
from app.services.audit.ledger import (
    BlockchainBlock,
    DevelopmentBlockchainLedger,
    compute_block_hash,
)
from app.services.audit.audit_integrity_service import (
    AuditIntegrityService,
    compute_evidence_hash,
)


@pytest.fixture
def temp_ledger():
    """Create a temporary ledger instance backed by an isolated temp directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = os.path.join(tmpdir, "test_ledger.json")
        ledger = DevelopmentBlockchainLedger(storage_path=storage_path)
        yield ledger


@pytest.fixture
def sample_evidence_package():
    """Build a realistic multi-module evidence package for testing."""
    items = [
        NormalizedEvidenceItem(
            evidence_id="EV-001",
            case_id="CASE-TEST-001",
            document_id="DOC-PASSPORT-01",
            document_type="passport",
            module=EvidenceModule.OCR,
            signal_type="mrz_extraction",
            status=EvidenceStatus.VALID,
            severity=EvidenceSeverity.INFO,
            confidence=0.98,
            description="MRZ successfully parsed and checksums valid",
            source="PaddleOCR + MRZ Parser",
            timestamp=1788700000.0,
        ),
        NormalizedEvidenceItem(
            evidence_id="EV-002",
            case_id="CASE-TEST-001",
            document_id="DOC-PASSPORT-01",
            document_type="passport",
            module=EvidenceModule.FORENSICS,
            signal_type="ela_compression",
            status=EvidenceStatus.VALID,
            severity=EvidenceSeverity.INFO,
            confidence=0.92,
            description="No compression anomalies detected in photo region",
            source="Forensic ELA Engine",
            timestamp=1788700001.0,
        ),
    ]
    return EvidencePackage(
        target_id="CASE-TEST-001",
        target_type="case",
        items=items,
    )


class TestCryptographicLedger:
    """Tests for the underlying hash-chained ledger implementation."""

    def test_genesis_block_initialization(self, temp_ledger):
        assert temp_ledger.get_block_count() == 1
        genesis = temp_ledger.get_block(0)
        assert genesis is not None
        assert genesis.block_index == 0
        assert genesis.previous_hash == "0" * 64
        assert genesis.event_type == BlockchainEventType.GENESIS.value
        assert len(genesis.block_hash) == 64

    def test_block_chaining_and_previous_hash(self, temp_ledger):
        block1 = temp_ledger.append_event(
            event_type="DOCUMENT_UPLOADED",
            target_id="CASE-001",
            payload={"doc_type": "passport"},
            event_hash="a" * 64,
        )
        assert block1.block_index == 1
        assert block1.previous_hash == temp_ledger.get_block(0).block_hash

        block2 = temp_ledger.append_event(
            event_type="EVIDENCE_ANCHORED",
            target_id="CASE-001",
            payload={"signals": 2},
            event_hash="b" * 64,
        )
        assert block2.block_index == 2
        assert block2.previous_hash == block1.block_hash

        assert temp_ledger.get_block_count() == 3
        is_valid, msg = temp_ledger.verify_chain_integrity()
        assert is_valid is True

    def test_tampering_detection_on_block_data(self, temp_ledger):
        temp_ledger.append_event(
            event_type="TEST_EVENT_1",
            target_id="CASE-001",
            payload={"key": "val1"},
            event_hash="1" * 64,
        )
        temp_ledger.append_event(
            event_type="TEST_EVENT_2",
            target_id="CASE-001",
            payload={"key": "val2"},
            event_hash="2" * 64,
        )

        # Confirm chain is initially valid
        is_valid, _ = temp_ledger.verify_chain_integrity()
        assert is_valid is True

        # Tamper with block 1 payload directly
        temp_ledger._chain[1].payload["key"] = "tampered_value"
        is_valid, error_msg = temp_ledger.verify_chain_integrity()
        assert is_valid is False
        assert "tampered at index 1" in error_msg.lower() or "mismatch" in error_msg.lower()

    def test_tampering_detection_on_hash_break(self, temp_ledger):
        temp_ledger.append_event(
            event_type="EVENT_A",
            target_id="CASE-X",
            payload={},
            event_hash="3" * 64,
        )
        temp_ledger.append_event(
            event_type="EVENT_B",
            target_id="CASE-X",
            payload={},
            event_hash="4" * 64,
        )

        # Mutate block 2's previous_hash
        temp_ledger._chain[2].previous_hash = "f" * 64
        is_valid, error_msg = temp_ledger.verify_chain_integrity()
        assert is_valid is False
        assert "broken" in error_msg.lower()

    def test_persistence_and_reload(self, temp_ledger):
        temp_ledger.append_event(
            event_type="PERSIST_TEST",
            target_id="CASE-PERSIST",
            payload={"test": True},
            event_hash="5" * 64,
        )
        storage_path = temp_ledger._storage_path

        # Re-initialize ledger from existing storage file
        reloaded_ledger = DevelopmentBlockchainLedger(storage_path=storage_path)
        assert reloaded_ledger.get_block_count() == temp_ledger.get_block_count()
        is_valid, msg = reloaded_ledger.verify_chain_integrity()
        assert is_valid is True


class TestAuditIntegrityService:
    """Tests for the higher-level AuditIntegrityService."""

    def test_canonical_json_hashing_determinism(self):
        dict_a = {"z": 1, "a": {"sub_b": 2, "sub_a": 1}}
        dict_b = {"a": {"sub_a": 1, "sub_b": 2}, "z": 1}
        hash_a = compute_evidence_hash(dict_a)
        hash_b = compute_evidence_hash(dict_b)
        assert hash_a == hash_b
        assert len(hash_a) == 64

    def test_anchor_and_verify_evidence_success(self, temp_ledger, sample_evidence_package):
        service = AuditIntegrityService(ledger=temp_ledger)
        block = service.anchor_evidence_package(sample_evidence_package)

        assert block is not None
        assert block.event_type == BlockchainEventType.EVIDENCE_ANCHORED.value
        assert block.target_id == sample_evidence_package.target_id

        # Live verification against unmodified package
        verify_res = service.verify_target_integrity(
            target_id=sample_evidence_package.target_id,
            current_evidence_package=sample_evidence_package,
        )
        assert verify_res.integrity_status == "VALID"
        assert verify_res.chain_valid is True
        assert verify_res.events_verified >= 1

    def test_tampering_detection_in_evidence_package(self, temp_ledger, sample_evidence_package):
        service = AuditIntegrityService(ledger=temp_ledger)
        service.anchor_evidence_package(sample_evidence_package)

        # Create tampered copy of evidence package
        tampered_package = copy.deepcopy(sample_evidence_package)
        tampered_package.items[0].status = EvidenceStatus.SUSPICIOUS
        tampered_package.items[0].confidence = 0.40

        verify_res = service.verify_target_integrity(
            target_id=sample_evidence_package.target_id,
            current_evidence_package=tampered_package,
        )
        assert verify_res.integrity_status == "INTEGRITY_FAILURE"
        assert "mismatch" in verify_res.message.lower()

    def test_officer_decision_anchoring(self, temp_ledger):
        service = AuditIntegrityService(ledger=temp_ledger)
        block = service.record_officer_decision(
            target_id="CASE-DECISION-01",
            officer_id="OFFICER-4421",
            decision="REFER_TO_SECONDARY",
            reason="Forensic anomaly in ghost photo requires secondary examination",
            notes="Traveler routed to secondary inspection lane 2",
        )
        assert block is not None
        assert block.event_type == BlockchainEventType.OFFICER_REVIEWED.value
        assert block.payload["decision"] == "REFER_TO_SECONDARY"
        assert block.payload["officer_id"] == "OFFICER-4421"

        # Verify chain includes officer review block
        chain_blocks = service.get_target_audit_chain("CASE-DECISION-01")
        assert len(chain_blocks) == 1
        assert chain_blocks[0].event_type == BlockchainEventType.OFFICER_REVIEWED.value

    def test_ledger_failure_resilience(self, monkeypatch, sample_evidence_package):
        """Simulate unexpected ledger storage failure: screening pipeline must not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = DevelopmentBlockchainLedger(storage_path=os.path.join(tmpdir, "resilience.json"))
            service = AuditIntegrityService(ledger=ledger)

            # Force append_block to raise an exception
            def broken_append(*args, **kwargs):
                raise IOError("Simulated disk write failure / ledger offline")

            monkeypatch.setattr(ledger, "append_block", broken_append)

            # Must not raise an unhandled exception
            result = service.anchor_evidence_package(sample_evidence_package)
            assert result is None
            # Event should be safely queued
            assert len(service.get_pending_events()) == 1


class TestAuditAPIEndpoints:
    """Integration tests for Audit API routes."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        self.client = TestClient(app)

    def test_get_audit_chain_endpoint(self):
        response = self.client.get("/api/v1/audit/CASE-SYSTEM-TEST/chain")
        assert response.status_code == 200
        data = response.json()
        assert "target_id" in data
        assert "blocks" in data
        assert "chain_valid" in data
        assert data["ledger_type"] == "development_sandbox"

    def test_post_officer_decision_endpoint(self):
        payload = {
            "officer_id": "OFFICER-BORDER-99",
            "decision": "CLEAR_ADMIT",
            "reason": "All documents verified and biometric match confirmed",
            "notes": "Standard clearance granted",
        }
        response = self.client.post(
            "/api/v1/audit/CASE-API-TEST/officer-decision",
            json=payload,
        )
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["status"] == "RECORDED"
        assert data["decision"] == "CLEAR_ADMIT"
        assert data["officer_id"] == "OFFICER-BORDER-99"
        assert data["block_index"] >= 1

    def test_system_diagnostics_and_benchmarks_endpoints(self):
        diag_resp = self.client.get("/api/v1/system/diagnostics")
        assert diag_resp.status_code == 200
        diag_data = diag_resp.json()
        assert diag_data["app_version"] == "1.0.0-phase12"
        assert diag_data["environment"] == "demonstration"
        assert "models" in diag_data

        bench_resp = self.client.get("/api/v1/system/benchmarks")
        assert bench_resp.status_code == 200
        bench_data = bench_resp.json()
        assert "benchmarks" in bench_data
        assert "ocr" in bench_data["benchmarks"]
