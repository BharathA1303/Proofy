"""
backend/app/services/documents/profiles/national_id_profile.py

Legacy National ID Profile shim.
Re-exports AADHAAR_PROFILE for backward compatibility with older tests and components.
"""
from app.services.documents.profiles.aadhaar_profile import AADHAAR_PROFILE

# Backward compatibility alias
NATIONAL_ID_PROFILE = AADHAAR_PROFILE

__all__ = ["NATIONAL_ID_PROFILE"]
