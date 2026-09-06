"""
backend/app/services/documents/profiles/__init__.py

Document profile definitions and registry.
"""
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)
from app.services.documents.profiles.document_profile_registry import (
    DocumentProfileRegistry,
    document_profile_registry,
)

__all__ = [
    "DocumentProfile",
    "DocumentType",
    "ModuleSupportStatus",
    "ProfileStatus",
    "DocumentProfileRegistry",
    "document_profile_registry",
]
