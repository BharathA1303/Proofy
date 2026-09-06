"""
backend/app/services/documents/profiles/other_profiles.py

Future document profiles marked COMING_SOON / NOT_IMPLEMENTED.
Ensures the system cleanly demarcates unsupported profiles without fake verification pipelines.
"""
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)

from app.services.documents.profiles.border_permit_profile import (
    BORDER_PERMIT_PROFILE,
)
from app.services.documents.profiles.driving_license_profile import (
    DRIVING_LICENSE_PROFILE,
)
from app.services.documents.profiles.national_id_profile import (
    NATIONAL_ID_PROFILE,
)

__all__ = [
    "BORDER_PERMIT_PROFILE",
    "DRIVING_LICENSE_PROFILE",
    "NATIONAL_ID_PROFILE",
]
