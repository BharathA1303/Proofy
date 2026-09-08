"""
backend/app/services/quality/__init__.py
"""
from app.services.quality.document_quality import (
    DocumentQualityResult,
    evaluate_document_quality,
)

__all__ = ["DocumentQualityResult", "evaluate_document_quality"]
