"""
backend/app/services/registry/base.py

Abstract base class for all Registry Providers.

ARCHITECTURAL PRINCIPLE:
  The Registry Engine must not know implementation details of individual providers.
  All providers implement this interface. The engine calls only these methods.

FUTURE PROVIDER INTEGRATION:
  To plug in an authorized government/institutional registry:
  1. Create a new class in providers/ that inherits RegistryProvider.
  2. Implement all abstract methods.
  3. Update the ProviderResolver to map the document type to the new class.
  4. Set REGISTRY_PROVIDER_PASSPORT=authorized_api in environment config.
  5. The core engine and risk engine require zero changes.

SECURITY REMINDER:
  Future production providers MUST:
  - Read credentials from environment variables or secret manager.
  - Never commit API keys, certificates, or tokens.
  - Never log Authorization headers.
  - Validate all provider responses against schema before use.
  - Implement strict timeouts using REGISTRY_CONNECT_TIMEOUT / REGISTRY_READ_TIMEOUT.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.registry import (
        RegistryVerificationRequest,
        RegistryVerificationResponse,
        RegistryProviderStatus,
    )


class RegistryProvider(ABC):
    """
    Abstract interface for all registry providers.

    Each document type has its own provider implementation.
    Providers are resolved at runtime by ProviderResolver.

    Implementations:
      - MockPassportRegistryProvider   (development/testing)
      - [Future] AuthorizedPassportRegistryProvider
      - [Future] AuthorizedVisaRegistryProvider
      - etc.
    """

    @abstractmethod
    def initialize(self) -> None:
        """
        Initialize the provider (load config, establish connection pools, etc.).
        Called once at application startup by the resolver.
        Must not raise for mock providers.
        For external providers, should raise RegistryConfigurationError
        if required credentials are missing.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return True if the provider is currently available for requests.
        Must return quickly (no network calls for mock providers).
        For external providers, this may check a circuit breaker state.
        """

    @abstractmethod
    def supports(self, document_type: str) -> bool:
        """
        Return True if this provider can handle the given document type.
        Used by the resolver to validate routing decisions.

        Args:
            document_type: e.g. 'passport', 'visa', 'driving_license',
                           'national_id', 'border_permit'
        """

    @abstractmethod
    def verify(
        self,
        request: "RegistryVerificationRequest",
    ) -> "RegistryVerificationResponse":
        """
        Execute a registry verification request.

        Args:
            request: Normalized RegistryVerificationRequest built by the adapter.

        Returns:
            RegistryVerificationResponse with evidence, field_results, and
            provider_metadata. NEVER returns risk scores or final decisions.

        Raises:
            RegistryProviderUnavailable: Provider cannot be reached.
            RegistryTimeout: Call exceeded timeout budget.
            RegistryAuthenticationError: Authentication failure (external providers).
            RegistryProviderError: Unexpected provider-side error.
            RegistryResponseInvalid: Provider response failed schema validation.
        """

    @abstractmethod
    def health_check(self) -> "RegistryProviderStatus":
        """
        Return the current health and availability status.
        Used for monitoring and admin endpoints.
        Must not raise — always returns a status object.
        """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """
        Unique identifier for this provider instance.
        Used in audit trails and response metadata.
        Example: 'mock-passport-registry', 'authorized-passport-api-v1'
        """
