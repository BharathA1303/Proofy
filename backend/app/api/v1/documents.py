"""
backend/app/api/v1/documents.py

Document Profile discovery and metadata API.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.services.documents.profiles import document_profile_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


class DocumentProfileMetadata(BaseModel):
    """Metadata for a single document profile."""
    type: str
    display_name: str
    version: str
    status: str
    description: str
    modules: Dict[str, str]
    mrz_applicable: bool
    mrz_standard: str | None = None
    portrait_applicable: bool
    portrait_required: bool
    field_schema: List[str]
    required_fields: List[str]


class DocumentProfilesResponse(BaseModel):
    """Response payload for GET /api/v1/documents/profiles."""
    documents: List[DocumentProfileMetadata]
    total_count: int = 0


@router.get(
    "/profiles",
    response_model=DocumentProfilesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get metadata and operational status of all supported document types",
    description="Returns configuration profiles for all registered documents (Passport, Visa, Driving License, etc.).",
)
async def get_document_profiles() -> DocumentProfilesResponse:
    """Return all document profiles and their operational availability."""
    meta = document_profile_registry.get_all_profiles_metadata()
    profiles = [DocumentProfileMetadata(**d) for d in meta]
    return DocumentProfilesResponse(
        documents=profiles,
        total_count=len(profiles),
    )
