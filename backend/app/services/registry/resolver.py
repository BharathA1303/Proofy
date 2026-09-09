"""
backend/app/services/registry/resolver.py

Registry Provider Resolver.

Maps document_type → RegistryProvider instance.

CONFIGURATION:
  Provider selection is controlled by settings:
    REGISTRY_PROVIDER_PASSPORT     = 'mock' | 'sandbox' | 'external'
    REGISTRY_PROVIDER_VISA         = 'mock' | ...
    REGISTRY_PROVIDER_DL           = 'mock' | ...
    REGISTRY_PROVIDER_NATIONAL_ID  = 'mock' | ...
    REGISTRY_PROVIDER_BORDER_PERMIT= 'mock' | ...

FUTURE EXTENSIBILITY:
  To add a new provider:
    1. Add provider class in providers/
    2. Register it in _PROVIDER_REGISTRY below
    3. Set the environment variable to point to the new provider key
    4. Zero changes to engine, API, or frontend

  To add a new document type:
    1. Add config key in settings
    2. Add mapping in _TYPE_TO_SETTING
    3. Ensure an adapter and provider exist for that type
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from app.core.config import settings
from app.core.exceptions import RegistryConfigurationError
from app.services.registry.base import RegistryProvider

logger = logging.getLogger(__name__)


# ── Document type → config setting mapping ────────────────────────────────────

_TYPE_TO_SETTING: Dict[str, str] = {
    "passport":       settings.REGISTRY_PROVIDER_PASSPORT,
    "visa":           settings.REGISTRY_PROVIDER_VISA,
    "driving_license": settings.REGISTRY_PROVIDER_DL,
    "drivingLicense": settings.REGISTRY_PROVIDER_DL,
    # Indian identity documents
    "aadhaar":        settings.REGISTRY_PROVIDER_AADHAAR,
    "aadhaarCard":    settings.REGISTRY_PROVIDER_AADHAAR,
    "voter_id":       settings.REGISTRY_PROVIDER_VOTER_ID,
    "voterId":        settings.REGISTRY_PROVIDER_VOTER_ID,
    "voterID":        settings.REGISTRY_PROVIDER_VOTER_ID,
    "epic":           settings.REGISTRY_PROVIDER_VOTER_ID,
    "pan_card":       settings.REGISTRY_PROVIDER_PAN_CARD,
    "panCard":        settings.REGISTRY_PROVIDER_PAN_CARD,
    "pan":            settings.REGISTRY_PROVIDER_PAN_CARD,
    "border_permit":  settings.REGISTRY_PROVIDER_BORDER_PERMIT,
    "borderPermit":   settings.REGISTRY_PROVIDER_BORDER_PERMIT,
    # Legacy compatibility aliases — map old generic national_id to Aadhaar setting
    "national_id":    settings.REGISTRY_PROVIDER_AADHAAR,
    "nationalId":     settings.REGISTRY_PROVIDER_AADHAAR,
    "nid":            settings.REGISTRY_PROVIDER_AADHAAR,
}


class ProviderResolver:
    """
    Resolves the appropriate RegistryProvider for a given document type.

    Providers are lazily initialized on first request and then cached.
    This ensures initialization only happens once per provider type.
    """

    def __init__(self) -> None:
        # Cache of initialized providers: provider_mode_key → RegistryProvider
        self._provider_cache: Dict[str, RegistryProvider] = {}

    def resolve(self, document_type: str) -> RegistryProvider:
        """
        Return an initialized RegistryProvider for the given document type.

        Args:
            document_type: e.g. 'passport', 'visa', 'driving_license'

        Returns:
            An initialized RegistryProvider instance.

        Raises:
            RegistryConfigurationError: document type not supported or provider misconfigured.
        """
        provider_mode = _TYPE_TO_SETTING.get(document_type)

        if provider_mode is None:
            logger.warning("ProviderResolver: unsupported document_type=%s", document_type)
            raise RegistryConfigurationError(
                f"No registry provider configured for document type '{document_type}'. "
                f"Supported types: {list(_TYPE_TO_SETTING.keys())}"
            )

        # Use normalized document type for provider lookup
        normalized_type = _normalize_doc_type(document_type)
        cache_key = f"{normalized_type}:{provider_mode}"

        if cache_key not in self._provider_cache:
            provider = self._create_provider(normalized_type, provider_mode)
            provider.initialize()
            self._provider_cache[cache_key] = provider
            logger.info(
                "ProviderResolver initialized provider: doc_type=%s mode=%s provider=%s",
                normalized_type, provider_mode, provider.provider_id,
            )

        return self._provider_cache[cache_key]

    def _create_provider(self, document_type: str, provider_mode: str) -> RegistryProvider:
        """
        Instantiate the appropriate provider based on mode.
        Raises RegistryConfigurationError for unknown modes.
        """
        if provider_mode == "mock":
            return self._create_mock_provider(document_type)
        elif provider_mode == "sandbox":
            # Future: sandbox providers with read-only test instances
            logger.warning(
                "Sandbox provider not yet implemented for %s — falling back to mock",
                document_type,
            )
            return self._create_mock_provider(document_type)
        elif provider_mode == "external":
            # Future: real authorized external providers
            raise RegistryConfigurationError(
                f"External registry provider for '{document_type}' is not yet implemented. "
                "Set REGISTRY_PROVIDER_* to 'mock' for development. "
                "Contact system administration to configure an authorized external provider."
            )
        else:
            raise RegistryConfigurationError(
                f"Unknown registry provider mode '{provider_mode}' for '{document_type}'. "
                "Valid modes: 'mock', 'sandbox', 'external'."
            )

    def _create_mock_provider(self, document_type: str) -> RegistryProvider:
        """Create the appropriate mock provider for a document type."""
        norm_type = document_type.lower()
        if norm_type == "passport":
            from app.services.registry.providers.mock_passport import (
                MockPassportRegistryProvider,
            )
            return MockPassportRegistryProvider()
        elif norm_type == "visa":
            from app.services.registry.providers.mock_visa import (
                MockVisaRegistryProvider,
            )
            return MockVisaRegistryProvider()
        elif norm_type in ("driving_license", "drivinglicense"):
            from app.services.registry.providers.mock_driving_license import (
                MockDrivingLicenseRegistryProvider,
            )
            return MockDrivingLicenseRegistryProvider()
        elif norm_type in ("national_id", "nationalid", "nid"):
            from app.services.registry.providers.mock_national_id import MockNationalIdRegistryProvider
            return MockNationalIdRegistryProvider()
        elif norm_type in ("aadhaar", "aadhaarcard", "uid"):
            from app.services.registry.providers.mock_aadhaar import MockAadhaarRegistryProvider
            return MockAadhaarRegistryProvider()
        elif norm_type in ("voter_id", "voterid", "epic", "voter"):
            from app.services.registry.providers.mock_voter_id import MockVoterIdRegistryProvider
            return MockVoterIdRegistryProvider()
        elif norm_type in ("pan_card", "pancard", "pan"):
            from app.services.registry.providers.mock_pan_card import MockPanCardRegistryProvider
            return MockPanCardRegistryProvider()
        elif norm_type in ("border_permit", "borderpermit"):
            from app.services.registry.providers.mock_border_permit import (
                MockBorderPermitRegistryProvider,
            )
            return MockBorderPermitRegistryProvider()
        else:
            # For other document types: return a generic unavailable stub
            # until their providers are implemented
            logger.info(
                "No specific mock provider for doc_type=%s — using generic unavailable stub",
                document_type,
            )
            return _GenericUnavailableProvider(document_type)

    def health_check_all(self) -> Dict[str, dict]:
        """Return health status for all initialized providers."""
        results = {}
        for cache_key, provider in self._provider_cache.items():
            try:
                status = provider.health_check()
                results[cache_key] = {
                    "provider_id": status.provider_id,
                    "available": status.available,
                    "source_type": status.source_type,
                }
            except Exception as e:
                results[cache_key] = {"available": False, "error": str(e)}
        return results


def _normalize_doc_type(document_type: str) -> str:
    """Normalize frontend camelCase document type keys to snake_case."""
    mapping = {
        "drivingLicense":  "driving_license",
        "nationalId":      "national_id",   # legacy alias — maps to aadhaar provider
        "aadhaarCard":     "aadhaar",
        "voterId":         "voter_id",
        "voterID":         "voter_id",
        "panCard":         "pan_card",
        "borderPermit":    "border_permit",
    }
    return mapping.get(document_type, document_type)


class _GenericUnavailableProvider(RegistryProvider):
    """
    Stub provider returned for document types without a specific implementation.
    Always reports UNAVAILABLE — does not claim to have verified or rejected a document.
    """

    def __init__(self, document_type: str) -> None:
        self._doc_type = document_type
        self._pid = f"stub-{document_type}-registry"

    @property
    def provider_id(self) -> str:
        return self._pid

    def initialize(self) -> None:
        logger.info("GenericUnavailableProvider initialized for doc_type=%s", self._doc_type)

    def is_available(self) -> bool:
        return False

    def supports(self, document_type: str) -> bool:
        return document_type == self._doc_type

    def health_check(self):
        from app.schemas.registry import ProviderSourceType, RegistryProviderStatus
        return RegistryProviderStatus(
            provider_id=self._pid,
            source_type=ProviderSourceType.DEVELOPMENT_MOCK,
            available=False,
            supported_document_types=[self._doc_type],
            details=f"No registry provider implemented for '{self._doc_type}' yet.",
        )

    def verify(self, request) -> "RegistryVerificationResponse":
        """Returns an UNAVAILABLE response — does not claim document is invalid."""
        import datetime
        from app.schemas.registry import (
            ProviderSourceType,
            RegistryEvidence,
            RegistryProviderMetadata,
            RegistryStatus,
            RegistryVerificationResponse,
        )
        return RegistryVerificationResponse(
            verification_id=request.verification_id,
            document_type=request.document_type,
            registry={
                "provider": self._pid,
                "status": RegistryStatus.UNAVAILABLE.value,
                "record_found": False,
                "registry_document_status": None,
            },
            field_results=[],
            evidence=[
                RegistryEvidence(
                    type="provider_unavailable",
                    severity="warning",
                    description=(
                        f"No registry provider is configured for document type "
                        f"'{self._doc_type}'. Registry verification is UNAVAILABLE. "
                        "This does NOT indicate an invalid document."
                    ),
                )
            ],
            provider_metadata=RegistryProviderMetadata(
                provider_id=self._pid,
                source_type=ProviderSourceType.DEVELOPMENT_MOCK,
                response_time_ms=0.0,
            ),
            audit={
                "verification_id": request.verification_id,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "document_type": request.document_type,
                "provider_id": self._pid,
                "registry_status": RegistryStatus.UNAVAILABLE.value,
                "reason": "No provider implemented for this document type",
            },
        )


# Singleton instance
provider_resolver = ProviderResolver()
