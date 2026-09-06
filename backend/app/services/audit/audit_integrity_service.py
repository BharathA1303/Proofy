"""
backend/app/services/audit/audit_integrity_service.py

Audit Integrity Service — Coordinates canonical evidence hashing, event anchoring,
and cryptographic integrity verification against the immutable BlockchainLedger.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.schemas.audit import (
    BlockchainBlock,
    BlockchainEventType,
    IntegrityVerificationResponse,
    OfficerDecisionRequest,
    OfficerDecisionResponse,
)
from app.schemas.evidence import EvidencePackage, NormalizedEvidenceItem
from app.services.audit.ledger import BlockchainLedger, blockchain_ledger

logger = logging.getLogger(__name__)


def compute_evidence_hash(evidence_data: Any) -> str:
    """
    Computes a canonical SHA-256 hash of evidence items.
    Accepts EvidencePackage, list of NormalizedEvidenceItem, or serialized dict.
    Strictly sorts keys and eliminates extraneous whitespace.
    """
    if isinstance(evidence_data, EvidencePackage):
        canonical_dict = evidence_data.to_canonical_dict()
    elif isinstance(evidence_data, list) and all(isinstance(x, NormalizedEvidenceItem) for x in evidence_data):
        pkg = EvidencePackage(
            target_id="BATCH",
            items=evidence_data,
        )
        canonical_dict = pkg.to_canonical_dict()
    elif isinstance(evidence_data, dict):
        canonical_dict = evidence_data
    elif isinstance(evidence_data, str):
        return hashlib.sha256(evidence_data.encode("utf-8")).hexdigest()
    else:
        canonical_dict = {"raw": str(evidence_data)}

    canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class AuditIntegrityService:
    """
    Orchestrates the immutable audit layer between the verification pipeline
    and the BlockchainLedger.
    """

    def __init__(self, ledger: Optional[BlockchainLedger] = None) -> None:
        self._ledger = ledger or blockchain_ledger
        self._pending_queue: List[Dict[str, Any]] = []

    @property
    def ledger(self) -> BlockchainLedger:
        return self._ledger

    def anchor_event(
        self,
        target_id: str,
        event_type: BlockchainEventType | str,
        evidence: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[BlockchainBlock]:
        """
        Anchor a lifecycle milestone or evidence package on the blockchain.
        Failure resilience: if the ledger encounters an error, the event is queued
        as PENDING and verification is never interrupted.
        """
        ev_type = event_type.value if hasattr(event_type, "value") else str(event_type)
        evidence_hash = compute_evidence_hash(evidence) if evidence is not None else "0" * 64
        meta = metadata or {}
        meta.setdefault("timestamp_iso", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

        try:
            block = self._ledger.append_block(
                target_id=target_id,
                event_type=ev_type,
                evidence_hash=evidence_hash,
                metadata=meta,
            )
            return block
        except Exception as exc:
            logger.error(
                "AuditIntegrityService: ledger append failure for target=%s event=%s: %s. Enqueueing as PENDING.",
                target_id, ev_type, exc,
            )
            self._pending_queue.append({
                "target_id": target_id,
                "event_type": ev_type,
                "evidence_hash": evidence_hash,
                "metadata": meta,
                "queued_at": time.time(),
                "error": str(exc),
            })
            return None

    def record_officer_decision(
        self,
        target_id: str,
        request: Optional[OfficerDecisionRequest] = None,
        officer_id: Optional[str] = None,
        decision: Optional[str] = None,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> OfficerDecisionResponse:
        """Anchor an authorized officer's official determination on the blockchain."""
        if request is not None:
            off_id = request.officer_id
            dec_val = request.decision.value if hasattr(request.decision, "value") else str(request.decision)
            not_val = request.notes or ""
            rsn_val = getattr(request, "reason", "") or ""
        else:
            off_id = officer_id or "OFFICER-BORDER-01"
            dec_val = str(decision) if decision else "REFER_TO_SECONDARY"
            not_val = notes or ""
            rsn_val = reason or ""

        meta = {
            "officer_id": off_id,
            "decision": dec_val,
            "reason": rsn_val,
            "notes": not_val,
            "action": "OFFICER_DETERMINATION",
        }
        evidence_hash = hashlib.sha256(
            json.dumps({"officer_id": off_id, "decision": dec_val, "reason": rsn_val, "notes": not_val}, sort_keys=True).encode()
        ).hexdigest()

        block = self.anchor_event(
            target_id=target_id,
            event_type=BlockchainEventType.OFFICER_REVIEWED,
            evidence=evidence_hash,
            metadata=meta,
        )

        b_idx = block.block_index if block else -1
        b_hash = block.block_hash if block else "PENDING_BLOCKCHAIN_COMMIT"

        logger.info(
            "AuditIntegrityService: recorded officer decision '%s' for target=%s by officer=%s block=#%d",
            dec_val, target_id, off_id, b_idx,
        )

        return OfficerDecisionResponse(
            target_id=target_id,
            decision=dec_val,
            officer_id=off_id,
            reason=rsn_val,
            notes=not_val,
            timestamp=time.time(),
            block_index=b_idx,
            block_hash=b_hash,
            event_type=BlockchainEventType.OFFICER_REVIEWED.value,
            status="RECORDED",
            payload=meta,
        )

    def get_pending_events(self) -> List[Dict[str, Any]]:
        return list(self._pending_queue)

    def get_target_audit_chain(self, target_id: str) -> List[BlockchainBlock]:
        return [b for b in self._ledger.get_chain(target_id) if b.block_index > 0]

    def anchor_evidence_package(self, package: EvidencePackage) -> Optional[BlockchainBlock]:
        return self.anchor_event(
            target_id=package.target_id,
            event_type=BlockchainEventType.EVIDENCE_ANCHORED,
            evidence=package,
            metadata={"system_version": package.system_version, "items_count": len(package.items)},
        )

    def verify_target_integrity(
        self,
        target_id: str,
        current_evidence_package: Optional[Any] = None,
    ) -> IntegrityVerificationResponse:
        res = self.verify_integrity(target_id=target_id, current_evidence=current_evidence_package)
        if res.integrity_status == "INTEGRITY_FAILURE" and not res.details:
            res.details = "Evidence hash mismatch"
        return res

    def verify_integrity(
        self,
        target_id: str,
        current_evidence: Optional[Any] = None,
    ) -> IntegrityVerificationResponse:
        """
        Verify the cryptographic chain integrity and optionally compare current evidence
        against the latest anchored hash.
        """
        chain_valid, chain_msg = self._ledger.verify_chain()
        target_blocks = [b for b in self._ledger.get_chain(target_id) if b.block_index > 0]

        if not chain_valid:
            return IntegrityVerificationResponse(
                target_id=target_id,
                integrity_status="INTEGRITY_FAILURE",
                chain_valid=False,
                events_verified=len(target_blocks),
                chain_length=len(target_blocks),
                details=f"Blockchain hash-chain verification failed: {chain_msg}",
            )

        if not target_blocks:
            return IntegrityVerificationResponse(
                target_id=target_id,
                integrity_status="VALID",
                chain_valid=True,
                events_verified=0,
                chain_length=0,
                details="No anchored blocks found for target, but ledger chain is healthy.",
            )

        # If current evidence is provided, verify against latest anchored evidence hash
        calc_hash = None
        anchored_hash = None

        if current_evidence is not None:
            calc_hash = compute_evidence_hash(current_evidence)
            # Find the most recent block that contains an evidence hash
            for block in reversed(target_blocks):
                if block.evidence_hash and block.evidence_hash != "0" * 64:
                    anchored_hash = block.evidence_hash
                    break

            if anchored_hash and calc_hash != anchored_hash:
                logger.warning(
                    "AuditIntegrityService: evidence mismatch for target=%s (calc=%s != anchored=%s)",
                    target_id, calc_hash[:12], anchored_hash[:12],
                )
                return IntegrityVerificationResponse(
                    target_id=target_id,
                    integrity_status="INTEGRITY_FAILURE",
                    chain_valid=True,
                    events_verified=len(target_blocks),
                    chain_length=len(target_blocks),
                    calculated_evidence_hash=calc_hash,
                    anchored_evidence_hash=anchored_hash,
                    details="Evidence hash mismatch: Current evidence has been modified or corrupted since ledger anchoring.",
                )

        return IntegrityVerificationResponse(
            target_id=target_id,
            integrity_status="VALID",
            chain_valid=True,
            events_verified=len(target_blocks),
            chain_length=len(target_blocks),
            calculated_evidence_hash=calc_hash,
            anchored_evidence_hash=anchored_hash,
            details=f"All {len(target_blocks)} audit events and cryptographic chain verified successfully.",
        )


audit_integrity_service = AuditIntegrityService()
