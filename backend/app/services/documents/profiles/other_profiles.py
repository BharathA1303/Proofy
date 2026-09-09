"""
backend/app/services/documents/profiles/other_profiles.py

Convenience re-exports for document profiles not imported directly elsewhere.
"""
from app.services.documents.profiles.border_permit_profile import (
    BORDER_PERMIT_PROFILE,
)
from app.services.documents.profiles.driving_license_profile import (
    DRIVING_LICENSE_PROFILE,
)

__all__ = [
    "BORDER_PERMIT_PROFILE",
    "DRIVING_LICENSE_PROFILE",
]
