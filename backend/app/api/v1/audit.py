"""
backend/app/api/v1/audit.py

FastAPI router for Blockchain / Immutable Audit Ledger and Officer Decision recording.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status

from app.schemas.audit import (
    AuditChainResponse,
    IntegrityVerificationResponse,
    OfficerDecisionRequest,
    OfficerDecisionResponse,
)
from app.services.audit.audit_integrity_service import audit_integrity_service
from app.services.audit.ledger import blockchain_ledger
from app.services.case.case_manager import case_manager
from app.services.evidence.evidence_normalizer import evidence_normalizer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["Blockchain & Immutable Audit"])


@router.get(
    "/{target_id}/chain",
    response_model=AuditChainResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve the immutable blockchain audit chain for a document or case",
)
def get_audit_chain(target_id: str) -> Dict[str, Any]:
    chain = blockchain_ledger.get_chain(target_id)
    chain_valid, _ = blockchain_ledger.verify_chain(target_id)

    return {
        "target_id": target_id,
        "ledger_name": blockchain_ledger.ledger_name,
        "source_type": blockchain_ledger.source_type,
        "chain_valid": chain_valid,
        "total_blocks": len(chain),
        "blocks": [b.model_dump() for b in chain],
    }


@router.post(
    "/{target_id}/verify",
    response_model=IntegrityVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify cryptographic integrity of stored evidence against the blockchain ledger",
)
def verify_integrity(target_id: str) -> Dict[str, Any]:
    # Check if target_id corresponds to a VerificationCase
    current_evidence = None
    try:
        case = case_manager.get_case(target_id)
        current_evidence = evidence_normalizer.normalize_case_evidence(case)
    except Exception:
        # Standalone verification session check
        pass

    verification_result = audit_integrity_service.verify_integrity(
        target_id=target_id,
        current_evidence=current_evidence,
    )
    return verification_result.model_dump()


@router.post(
    "/{target_id}/officer-decision",
    response_model=OfficerDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an authorized human officer's official determination on the blockchain",
)
def record_officer_decision(
    target_id: str,
    payload: OfficerDecisionRequest,
) -> Dict[str, Any]:
    if not payload.officer_id or len(payload.officer_id.strip()) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid officer_id is required to anchor official determination.",
        )

    # If target_id is a case, record note in case object as well
    try:
        case = case_manager.get_case(target_id)
        case.notes = f"Officer {payload.officer_id} Decision: {payload.decision.value}. {payload.notes or ''}".strip()
    except Exception:
        pass

    resp = audit_integrity_service.record_officer_decision(
        target_id=target_id,
        request=payload,
    )
    return resp.model_dump()
