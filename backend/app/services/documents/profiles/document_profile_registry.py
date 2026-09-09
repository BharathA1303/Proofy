"""
backend/app/services/documents/profiles/document_profile_registry.py

Central Document Profile Registry.

Provides single-source resolution of document profiles, eliminating
scattered `if document_type == "passport"` conditionals across the codebase.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.exceptions import (
    DocumentProfileError,
    UnknownDocumentTypeError,
    UnsupportedDocumentTypeError,
)
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)
from app.services.documents.profiles.driving_license_profile import (
    DRIVING_LICENSE_PROFILE,
)
from app.services.documents.profiles.other_profiles import (
    BORDER_PERMIT_PROFILE,
)
from app.services.documents.profiles.aadhaar_profile import AADHAAR_PROFILE
from app.services.documents.profiles.voter_id_profile import VOTER_ID_PROFILE
from app.services.documents.profiles.pan_card_profile import PAN_CARD_PROFILE
from app.services.documents.profiles.passport_profile import PASSPORT_PROFILE
from app.services.documents.profiles.visa_profile import VISA_PROFILE

logger = logging.getLogger(__name__)

# Canonical alias mapping (e.g., frontend camelCase -> backend snake_case)
_DOC_TYPE_ALIASES: Dict[str, str] = {
    "passport": "passport",
    "visa": "visa",
    "drivinglicense": "driving_license",
    "drivingLicense": "driving_license",
    "driving_license": "driving_license",
    # Aadhaar — UIDAI 12-digit identity
    "aadhaar": "aadhaar",
    "aadhaarcard": "aadhaar",
    "aadhaarCard": "aadhaar",
    "uid": "aadhaar",
    # Voter ID / EPIC — Election Commission of India
    "voter_id": "voter_id",
    "voterid": "voter_id",
    "voterId": "voter_id",
    "voterID": "voter_id",
    "epic": "voter_id",
    "voter": "voter_id",
    # PAN Card — Income Tax Department
    "pan_card": "pan_card",
    "pancard": "pan_card",
    "panCard": "pan_card",
    "pan": "pan_card",
    # Border Permit
    "borderpermit": "border_permit",
    "borderPermit": "border_permit",
    "border_permit": "border_permit",
    # Legacy compatibility aliases — map old generic national_id to aadhaar
    "national_id": "aadhaar",
    "nationalid": "aadhaar",
    "nationalId": "aadhaar",
    "nid": "aadhaar",
}


class DocumentProfileRegistry:
    """
    Registry for all system Document Profiles.
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, DocumentProfile] = {}
        self._initialize_builtins()

    def _initialize_builtins(self) -> None:
        """Register the standard built-in profiles and run startup validation."""
        self.register(PASSPORT_PROFILE)
        self.register(VISA_PROFILE)
        self.register(DRIVING_LICENSE_PROFILE)
        # Indian identity documents — three separate profiles
        self.register(AADHAAR_PROFILE)
        self.register(VOTER_ID_PROFILE)
        self.register(PAN_CARD_PROFILE)
        self.register(BORDER_PERMIT_PROFILE)
        self.validate_registry()

    def register(self, profile: DocumentProfile) -> None:
        """Register a document profile."""
        doc_type = profile.document_type.lower()
        if doc_type in self._profiles:
            logger.warning("Overwriting document profile for '%s'", doc_type)
        self._profiles[doc_type] = profile
        logger.debug("Registered document profile: %s (status=%s)", doc_type, profile.status.value)

    def normalize_key(self, doc_type: str) -> str:
        """Normalize a document type string using aliases."""
        if not doc_type:
            return ""
        clean = doc_type.strip()
        return _DOC_TYPE_ALIASES.get(clean, _DOC_TYPE_ALIASES.get(clean.lower(), clean.lower()))

    def resolve(self, doc_type: str) -> DocumentProfile:
        """
        Resolve a document profile by type string.
        Raises UnknownDocumentTypeError if type is not registered.
        """
        norm_key = self.normalize_key(doc_type)
        profile = self._profiles.get(norm_key)
        if profile is None:
            logger.warning("DocumentProfileRegistry: Unknown document type '%s'", doc_type)
            raise UnknownDocumentTypeError(doc_type)
        return profile

    def resolve_operational(self, doc_type: str) -> DocumentProfile:
        """
        Resolve a document profile and verify it is operational (AVAILABLE).
        Raises UnsupportedDocumentTypeError if profile is COMING_SOON or NOT_IMPLEMENTED.
        """
        profile = self.resolve(doc_type)
        if not profile.is_available():
            logger.warning(
                "DocumentProfileRegistry: Document type '%s' is not operational (status=%s)",
                doc_type,
                profile.status.value,
            )
            raise UnsupportedDocumentTypeError(doc_type, profile.status.value)
        return profile

    def is_supported(self, doc_type: str) -> bool:
        """Check if a document type is registered and currently available."""
        try:
            profile = self.resolve(doc_type)
            return profile.is_available()
        except UnknownDocumentTypeError:
            return False

    def get_all_profiles(self) -> List[DocumentProfile]:
        """Return list of all registered document profiles."""
        return list(self._profiles.values())

    def list_operational(self) -> List[DocumentProfile]:
        """Return list of operational (available) document profiles."""
        return [p for p in self._profiles.values() if p.is_available()]

    def get_all_profiles_metadata(self) -> List[Dict[str, Any]]:
        """Return serialized list of profiles for client metadata endpoint."""
        return [p.to_dict() for p in self._profiles.values()]

    def validate_registry(self) -> None:
        """
        Perform startup validation on all registered profiles.
        Detects misconfigurations, missing fields, or invalid module mappings.
        """
        required_modules = ["ocr", "validation", "forensics", "biometrics", "registry", "risk"]
        for key, profile in self._profiles.items():
            # Validate document_type match
            if profile.document_type.lower() != key:
                raise DocumentProfileError(
                    f"Profile key mismatch: dictionary key '{key}' != profile type '{profile.document_type}'"
                )

            # Validate module declarations
            for m in required_modules:
                if m not in profile.modules:
                    raise DocumentProfileError(
                        f"Profile '{key}' is missing required module declaration for '{m}'"
                    )

            # Validate operational profiles
            if profile.status == ProfileStatus.AVAILABLE:
                if not profile.field_schema:
                    raise DocumentProfileError(
                        f"Operational profile '{key}' must define a non-empty field_schema"
                    )
                if not profile.required_fields:
                    raise DocumentProfileError(
                        f"Operational profile '{key}' must define at least one required_field"
                    )

        logger.info(
            "DocumentProfileRegistry: Startup validation successful for %d profiles (%s)",
            len(self._profiles),
            ", ".join(self._profiles.keys()),
        )


# Global singleton instance
document_profile_registry = DocumentProfileRegistry()
