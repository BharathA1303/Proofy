"""
backend/app/services/registry/providers/external_provider.py

Generic Authorized External Registry Provider.

Provides an authoritative external integration interface with:
- Strict SSRF protection (loopback/private IP blocking, cloud metadata blocking, allowed host validation).
- Response schema validation (never collapses malformed responses to NOT_FOUND).
- Bounded retries with exponential backoff on transient errors (429, 502, 503, 504, connection timeouts).
- Immediate terminal failure for permanent errors (400, 401, 403).
- Clean fallback to LIVE_PROVIDER_NOT_CONFIGURED when endpoints/credentials are unconfigured.
- Redaction of sensitive credentials, auth headers, and plain-text PII in all logs.
- Evidence-only emission (never declares FORGED or AUTHENTIC).
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import socket
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from app.core.exceptions import (
    RegistryAuthenticationError,
    RegistryConfigurationError,
    RegistryProviderError,
    RegistryProviderUnavailable,
    RegistryResponseInvalid,
    RegistryTimeout,
)
from app.schemas.registry import (
    ProviderSourceType,
    RegistryEvidence,
    RegistryFieldResult,
    RegistryProviderMetadata,
    RegistryProviderStatus,
    RegistryRecord,
    RegistryStatus,
    RegistryVerificationRequest,
    RegistryVerificationResponse,
)
from app.services.registry.base import RegistryProvider
from app.services.registry.comparator import compare_fields

logger = logging.getLogger(__name__)

# Cloud metadata and loopback addresses that must always be blocked
FORBIDDEN_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
    "instance-data",
}


def validate_endpoint_url(
    url: Optional[str],
    allowed_hosts: Optional[List[str]] = None,
    allow_insecure_http: bool = False,
) -> None:
    """
    Validate an external endpoint URL against SSRF attacks.
    Ensures safe schemes, prevents requests to private/loopback/cloud-metadata IPs.
    """
    if not url:
        raise RegistryConfigurationError("Registry endpoint URL cannot be empty")

    parsed = urlparse(url)
    if not parsed.scheme or parsed.scheme.lower() not in ("http", "https"):
        raise RegistryConfigurationError(f"Invalid URL scheme '{parsed.scheme}'. Only HTTPS is permitted.")

    if not allow_insecure_http and parsed.scheme.lower() == "http":
        raise RegistryConfigurationError("Insecure HTTP scheme is prohibited for external registry providers.")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise RegistryConfigurationError("Missing hostname in registry endpoint URL.")

    if hostname in FORBIDDEN_HOSTNAMES:
        raise RegistryConfigurationError(f"SSRF protection: prohibited hostname '{hostname}'.")

    # Check allowed hosts if specified
    if allowed_hosts:
        matched = False
        for allowed in allowed_hosts:
            allowed = allowed.strip().lower()
            if allowed.startswith("*."):
                suffix = allowed[1:]
                if hostname.endswith(suffix):
                    matched = True
                    break
            elif hostname == allowed:
                matched = True
                break
        if not matched:
            raise RegistryConfigurationError(
                f"SSRF protection: hostname '{hostname}' is not in allowed hosts {allowed_hosts}."
            )

    # Resolve IP and check for private / loopback / link-local addresses
    try:
        ip = ipaddress.ip_address(hostname)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise RegistryConfigurationError(
                f"SSRF protection: IP address {ip} is private, loopback, or reserved."
            )
    except ValueError:
        # hostname is not a numeric IP address, resolve via DNS
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for family, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                resolved_ip = ipaddress.ip_address(ip_str)
                # Loopback and link-local (cloud metadata) are unconditionally prohibited
                if (
                    resolved_ip.is_loopback
                    or resolved_ip.is_link_local
                    or str(resolved_ip) in ("169.254.169.254", "0.0.0.0")
                ):
                    raise RegistryConfigurationError(
                        f"SSRF protection: resolved IP {resolved_ip} for {hostname} is loopback or link-local."
                    )
                # Private IP is prohibited UNLESS domain was explicitly whitelisted in allowed_hosts
                if not (allowed_hosts and matched) and (
                    resolved_ip.is_private
                    or resolved_ip.is_multicast
                    or resolved_ip.is_reserved
                    or resolved_ip.is_unspecified
                ):
                    raise RegistryConfigurationError(
                        f"SSRF protection: resolved IP {resolved_ip} for {hostname} is private or reserved."
                    )
        except (socket.gaierror, socket.herror):
            logger.warning("Could not resolve hostname '%s' during SSRF pre-check", hostname)


class AuthorizedExternalRegistryProvider(RegistryProvider):
    """
    Generic authoritative external registry provider.

    Adheres strictly to the Non-Adjudication Principle and Zero Client Trust.
    Provides robust retry behavior, SSRF defense, and schema validation.
    """

    def __init__(
        self,
        provider_id: str = "authorized_external_registry",
        endpoint_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: float = 5.0,
        allowed_hosts: Optional[List[str]] = None,
        retry_policy: Optional[Dict[str, Any]] = None,
        document_type: str = "driving_license",
        profile_version: Optional[str] = "0.9.0",
        allow_insecure_http: bool = False,
    ) -> None:
        self._provider_id = provider_id
        self._endpoint_url = endpoint_url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._allowed_hosts = allowed_hosts
        self._document_type = document_type
        self._profile_version = profile_version
        self._allow_insecure_http = allow_insecure_http

        self._retry_policy = retry_policy or {
            "max_retries": 2,
            "backoff_factor": 0.5,
            "retryable_statuses": [429, 502, 503, 504],
        }

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def source_type(self) -> ProviderSourceType:
        if not self.is_configured:
            return ProviderSourceType.NOT_CONFIGURED
        return ProviderSourceType.AUTHORIZED_EXTERNAL_PROVIDER

    @property
    def is_configured(self) -> bool:
        return bool(self._endpoint_url and self._api_key)

    def initialize(self) -> None:
        """Validate configuration and run SSRF check if endpoint is configured."""
        if self._endpoint_url:
            validate_endpoint_url(
                self._endpoint_url,
                allowed_hosts=self._allowed_hosts,
                allow_insecure_http=self._allow_insecure_http,
            )
            logger.info(
                "AuthorizedExternalRegistryProvider initialized: provider_id=%s endpoint=%s",
                self.provider_id,
                urlparse(self._endpoint_url).netloc,
            )
        else:
            logger.info(
                "AuthorizedExternalRegistryProvider initialized without endpoint (NOT_CONFIGURED): provider_id=%s",
                self.provider_id,
            )

    def is_available(self) -> bool:
        """Available only if endpoint and credentials are configured."""
        return self.is_configured

    def supports(self, document_type: str) -> bool:
        return (document_type or "").strip().lower() == self._document_type.lower()

    def health_check(self) -> RegistryProviderStatus:
        return RegistryProviderStatus(
            provider_id=self.provider_id,
            source_type=self.source_type,
            available=self.is_available(),
            supported_document_types=[self._document_type],
            details=(
                "Configured and available"
                if self.is_configured
                else "Live provider credentials/endpoint not configured"
            ),
        )

    def verify(self, request: RegistryVerificationRequest) -> RegistryVerificationResponse:
        t_start = time.perf_counter()

        doc_num_prov = request.document_number
        doc_num = doc_num_prov.value if doc_num_prov else None
        lookup_key = (doc_num or "").strip().upper()

        q_ref = f"{self._document_type}:{lookup_key}"
        query_hash = hashlib.sha256(q_ref.encode("utf-8")).hexdigest()

        # Handle unconfigured state cleanly
        if not self.is_configured:
            t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            return self._build_not_configured_response(
                request=request,
                query_hash=query_hash,
                elapsed_ms=t_elapsed_ms,
            )

        # Validate SSRF before making outbound call
        validate_endpoint_url(
            self._endpoint_url,
            allowed_hosts=self._allowed_hosts,
            allow_insecure_http=self._allow_insecure_http,
        )

        # Execute outbound HTTP call with bounded retries
        http_response = self._execute_request_with_retries(request, lookup_key)
        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        # Handle HTTP status codes
        status_code = http_response.status_code
        if status_code == 404:
            return self._build_response(
                request=request,
                query_hash=query_hash,
                registry_status=RegistryStatus.NOT_FOUND,
                record=None,
                field_results=[],
                evidence=[
                    RegistryEvidence(
                        type="registry_lookup",
                        severity="info",
                        description=f"Authoritative registry returned no record for query hash {query_hash[:8]}.",
                    )
                ],
                response_time_ms=t_elapsed_ms,
            )
        elif status_code in (401, 403):
            logger.error("Authoritative external registry authentication failed: status=%d", status_code)
            raise RegistryAuthenticationError(f"External registry rejected authentication credentials (HTTP {status_code})")
        elif status_code == 400:
            logger.warning("Authoritative external registry rejected query as invalid: status=400")
            return self._build_response(
                request=request,
                query_hash=query_hash,
                registry_status=RegistryStatus.INVALID_REQUEST,
                record=None,
                field_results=[],
                evidence=[
                    RegistryEvidence(
                        type="registry_request_error",
                        severity="warning",
                        description="External registry rejected request parameters as structurally invalid.",
                    )
                ],
                response_time_ms=t_elapsed_ms,
            )
        elif status_code == 429:
            logger.warning("Authoritative external registry rate limit exceeded: status=429")
            return self._build_response(
                request=request,
                query_hash=query_hash,
                registry_status=RegistryStatus.RATE_LIMITED,
                record=None,
                field_results=[],
                evidence=[
                    RegistryEvidence(
                        type="registry_rate_limit",
                        severity="warning",
                        description="External registry rate limit exceeded. Retry later.",
                    )
                ],
                response_time_ms=t_elapsed_ms,
            )
        elif status_code >= 500:
            logger.error("Authoritative external registry returned server error: status=%d", status_code)
            raise RegistryProviderUnavailable(f"External registry service unavailable (HTTP {status_code})")
        elif status_code != 200:
            logger.error("Authoritative external registry returned unexpected status: status=%d", status_code)
            raise RegistryProviderError(f"Unexpected HTTP status {status_code} from external registry")

        # Response Schema Validation
        try:
            payload = http_response.json()
        except Exception as exc:
            logger.error("Authoritative external registry returned invalid non-JSON payload: %s", exc)
            raise RegistryResponseInvalid("External registry response failed JSON parsing.") from exc

        if not isinstance(payload, dict):
            logger.error("Authoritative external registry returned non-dictionary payload")
            raise RegistryResponseInvalid("External registry response must be a JSON dictionary.")

        raw_record = payload.get("record") if "record" in payload else payload
        if not isinstance(raw_record, dict) or not raw_record.get("document_number"):
            logger.error("Authoritative external registry payload missing required 'document_number'")
            raise RegistryResponseInvalid("External registry response missing mandatory document_number.")

        reg_record = RegistryRecord(
            document_number=raw_record.get("document_number"),
            registry_document_status=raw_record.get("registry_document_status") or raw_record.get("status", "ACTIVE"),
            name=raw_record.get("name"),
            date_of_birth=raw_record.get("date_of_birth"),
            expiry_date=raw_record.get("expiry_date"),
            valid_from=raw_record.get("valid_from") or raw_record.get("issued_date"),
            issuing_authority=raw_record.get("issuing_authority"),
            vehicle_classes=raw_record.get("vehicle_classes") or raw_record.get("cov"),
            state=raw_record.get("state") or raw_record.get("jurisdiction"),
            blood_group=raw_record.get("blood_group"),
            metadata={k: v for k, v in raw_record.items() if k not in ("token", "api_key", "secret")},
        )

        field_results, status = compare_fields(request, reg_record)

        # Check document-level status reported by registry
        reported_doc_status = (reg_record.registry_document_status or "").upper()
        if reported_doc_status == "REVOKED":
            status = RegistryStatus.REVOKED
        elif reported_doc_status == "SUSPENDED":
            status = RegistryStatus.SUSPENDED
        elif reported_doc_status == "EXPIRED":
            status = RegistryStatus.EXPIRED
        elif reported_doc_status == "INVALID":
            status = RegistryStatus.INVALID

        evidence = [
            RegistryEvidence(
                type="registry_corroboration",
                severity="info" if status == RegistryStatus.MATCHED else "warning",
                description=(
                    f"Authoritative external registry corroboration status: {status.value}. "
                    f"Reported document status: {reported_doc_status}."
                ),
            )
        ]

        return self._build_response(
            request=request,
            query_hash=query_hash,
            registry_status=status,
            record=reg_record,
            field_results=field_results,
            evidence=evidence,
            response_time_ms=t_elapsed_ms,
        )

    def _execute_request_with_retries(
        self,
        request: RegistryVerificationRequest,
        lookup_key: str,
    ) -> requests.Response:
        """Send HTTP query to external registry with bounded retries and backoff."""
        max_retries = int(self._retry_policy.get("max_retries", 2))
        backoff_factor = float(self._retry_policy.get("backoff_factor", 0.5))
        retryable_statuses = set(self._retry_policy.get("retryable_statuses", [429, 502, 503, 504]))

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Proofy-Identity-Verification/1.0",
        }
        body = {
            "verification_id": request.verification_id,
            "document_type": self._document_type,
            "document_number": lookup_key,
        }

        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                logger.debug(
                    "Outbound registry query attempt %d/%d to %s",
                    attempt + 1, max_retries + 1, self.provider_id,
                )
                resp = requests.post(
                    self._endpoint_url,
                    json=body,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
                if resp.status_code in retryable_statuses and attempt < max_retries:
                    sleep_time = backoff_factor * (2 ** attempt)
                    logger.warning(
                        "External registry returned retryable status %d on attempt %d; retrying in %.2fs",
                        resp.status_code, attempt + 1, sleep_time,
                    )
                    time.sleep(sleep_time)
                    continue
                return resp
            except (requests.Timeout, TimeoutError) as exc:
                last_exc = exc
                if attempt < max_retries:
                    sleep_time = backoff_factor * (2 ** attempt)
                    logger.warning("External registry timeout on attempt %d; retrying in %.2fs", attempt + 1, sleep_time)
                    time.sleep(sleep_time)
                else:
                    raise RegistryTimeout(f"External registry timed out after {max_retries + 1} attempts") from exc
            except (requests.ConnectionError, ConnectionResetError) as exc:
                last_exc = exc
                if attempt < max_retries:
                    sleep_time = backoff_factor * (2 ** attempt)
                    logger.warning("External registry connection error on attempt %d; retrying in %.2fs", attempt + 1, sleep_time)
                    time.sleep(sleep_time)
                else:
                    raise RegistryProviderUnavailable(f"External registry connection failed after {max_retries + 1} attempts") from exc
            except Exception as exc:
                logger.error("External registry unexpected request error: %s", exc)
                raise RegistryProviderError(f"Outbound request failed: {exc}") from exc

        if last_exc:
            raise RegistryProviderError(f"Outbound request failed after retries: {last_exc}") from last_exc
        raise RegistryProviderUnavailable("External registry query exhausted retries without response.")

    def _build_not_configured_response(
        self,
        request: RegistryVerificationRequest,
        query_hash: str,
        elapsed_ms: float,
    ) -> RegistryVerificationResponse:
        """Response emitted when external provider is requested but credentials/endpoints are absent."""
        status_val = RegistryStatus.LIVE_PROVIDER_NOT_CONFIGURED
        return RegistryVerificationResponse(
            verification_id=request.verification_id,
            document_type=self._document_type,
            registry={
                "provider": self.provider_id,
                "status": status_val.value,
                "record_found": False,
                "registry_document_status": None,
            },
            field_results=[],
            evidence=[
                RegistryEvidence(
                    type="registry_not_configured",
                    severity="warning",
                    description=(
                        "Authoritative live registry provider is not configured with external credentials/endpoint. "
                        "No external corroboration was performed. This document was NOT checked against a live authority."
                    ),
                )
            ],
            provider_metadata=RegistryProviderMetadata(
                provider_id=self.provider_id,
                source_type=ProviderSourceType.NOT_CONFIGURED,
                response_time_ms=round(elapsed_ms, 2),
            ),
            audit={
                "verification_id": request.verification_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "provider_id": self.provider_id,
                "query_hash": query_hash,
                "status": status_val.value,
                "note": "Authoritative live provider not configured",
            },
            provider_type=ProviderSourceType.NOT_CONFIGURED.value,
            query_hash=query_hash,
            freshness={
                "cached": False,
                "is_fresh": False,
                "retrieved_at": None,
                "source": "unconfigured",
            },
            profile_version=self._profile_version,
            field_comparisons=[],
        )

    def _build_response(
        self,
        request: RegistryVerificationRequest,
        query_hash: str,
        registry_status: RegistryStatus,
        record: Optional[RegistryRecord],
        field_results: List[RegistryFieldResult],
        evidence: List[RegistryEvidence],
        response_time_ms: float,
    ) -> RegistryVerificationResponse:
        field_comparisons = [
            {
                "field": fr.field,
                "status": fr.status.value,
                "document_value": fr.document_value,
                "registry_value": fr.registry_value,
                "is_critical": fr.is_critical,
                "comparison_method": fr.comparison_method,
                "note": fr.note,
            }
            for fr in field_results
        ]
        now_iso = datetime.now(timezone.utc).isoformat()
        return RegistryVerificationResponse(
            verification_id=request.verification_id,
            document_type=self._document_type,
            registry={
                "provider": self.provider_id,
                "status": registry_status.value,
                "record_found": record is not None,
                "registry_document_status": record.registry_document_status if record else None,
            },
            field_results=field_results,
            evidence=evidence,
            provider_metadata=RegistryProviderMetadata(
                provider_id=self.provider_id,
                source_type=self.source_type,
                response_time_ms=round(response_time_ms, 2),
            ),
            audit={
                "verification_id": request.verification_id,
                "timestamp": now_iso,
                "provider_id": self.provider_id,
                "query_hash": query_hash,
                "status": registry_status.value,
                "response_time_ms": round(response_time_ms, 2),
            },
            provider_type=self.source_type.value,
            query_hash=query_hash,
            freshness={
                "cached": False,
                "is_fresh": True,
                "retrieved_at": now_iso,
                "ttl_seconds": 300.0,
                "source": "live_provider",
            },
            profile_version=self._profile_version,
            field_comparisons=field_comparisons,
        )
