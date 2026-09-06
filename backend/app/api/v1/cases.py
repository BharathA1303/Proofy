"""
backend/app/api/v1/cases.py

FastAPI router for Multi-Document Verification Cases & Cross-Document Intelligence.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, File, Form, UploadFile, status

from app.schemas.case import (
    CaseRiskRequest,
    CreateCaseRequest,
    VerificationCaseResponse,
)
from app.services.case.case_manager import case_manager
from app.services.case.case_risk import case_risk_evaluator
from app.services.cross_document.cross_document_engine import cross_document_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verification/case", tags=["Multi-Document Verification Cases"])


@router.post(
    "",
    response_model=VerificationCaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new multi-document verification case",
)
def create_case(payload: CreateCaseRequest) -> Dict[str, Any]:
    case = case_manager.create_case(case_id=payload.case_id, notes=payload.notes)
    return case.to_response_dict()


@router.get(
    "/{case_id}",
    response_model=VerificationCaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve verification case summary, documents, and relationships",
)
def get_case(case_id: str) -> Dict[str, Any]:
    case = case_manager.get_case(case_id)
    return case.to_response_dict()


@router.post(
    "/{case_id}/documents",
    response_model=VerificationCaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a document to a verification case and evaluate cross-document consistency",
)
async def add_document(
    case_id: str,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    replace: bool = Form(False),
) -> Dict[str, Any]:
    file_bytes = await file.read()
    _, case = await case_manager.add_document_to_case(
        case_id=case_id,
        document_type=document_type,
        file_bytes=file_bytes,
        filename=file.filename or "document.jpg",
        declared_mime=file.content_type or "image/jpeg",
        replace=replace,
    )
    return case.to_response_dict()


@router.delete(
    "/{case_id}/documents/{document_id}",
    response_model=VerificationCaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove a document from a case and invalidate dependent evidence",
)
def remove_document(case_id: str, document_id: str) -> Dict[str, Any]:
    case = case_manager.remove_document_from_case(case_id, document_id)
    return case.to_response_dict()


@router.post(
    "/{case_id}/evaluate",
    response_model=VerificationCaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Re-evaluate cross-document relationships across all active case documents",
)
def evaluate_relationships(case_id: str) -> Dict[str, Any]:
    case = case_manager.get_case(case_id)
    cross_document_engine.evaluate_case(case)
    case_risk_evaluator.evaluate_case_risk(case)
    return case.to_response_dict()


@router.post(
    "/risk",
    status_code=status.HTTP_200_OK,
    summary="Compute or refresh case-level composite risk assessment",
)
def compute_case_risk(payload: CaseRiskRequest) -> Dict[str, Any]:
    case = case_manager.get_case(payload.case_id)
    assessment = case_risk_evaluator.evaluate_case_risk(case)
    return {
        "case_id": payload.case_id,
        "risk_assessment": assessment,
    }
