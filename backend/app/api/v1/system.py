"""
backend/app/api/v1/system.py

FastAPI router for system health, model diagnostics, and performance benchmarks.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, status

from app.services.system.system_service import system_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["System Diagnostics & Health"])


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Retrieve system operational health, version, and ledger state",
)
def get_health() -> Dict[str, Any]:
    return system_service.get_system_health()


@router.get(
    "/diagnostics",
    status_code=status.HTTP_200_OK,
    summary="Inspect status of ML models (SCRFD, ArcFace, MiniFASNet, PaddleOCR)",
)
def get_diagnostics() -> Dict[str, Any]:
    return system_service.get_model_diagnostics()


@router.get(
    "/benchmarks",
    status_code=status.HTTP_200_OK,
    summary="Retrieve measured execution latencies across all screening stages",
)
def get_benchmarks() -> Dict[str, Any]:
    return system_service.get_benchmarks()
