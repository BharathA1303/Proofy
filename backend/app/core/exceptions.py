"""
backend/app/core/exceptions.py

Custom exception hierarchy and FastAPI exception handlers.
All handlers return clean JSON — no Python stack traces are ever exposed.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Domain exceptions
# ──────────────────────────────────────────────

class DVSBaseError(Exception):
    """Base class for all Document Verification System errors."""
    status_code: int = 500
    user_message: str = "An unexpected error occurred. Please try again."

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.user_message
        super().__init__(self.detail)


class DocumentIngestionError(DVSBaseError):
    """Raised when file ingestion or decoding fails."""
    status_code = 400
    user_message = "Unable to process the uploaded document. Please check your file and try again."


class UnsupportedFormatError(DVSBaseError):
    """Raised when the file type is not accepted."""
    status_code = 415
    user_message = "Unsupported file type. Please upload a JPEG, PNG, or WEBP image."


class FileTooLargeError(DVSBaseError):
    """Raised when the uploaded file exceeds the size limit."""
    status_code = 413
    user_message = "The uploaded file is too large. Please reduce the file size and try again."


class OCREngineError(DVSBaseError):
    """Raised when the OCR engine encounters a fatal error."""
    status_code = 500
    user_message = "OCR processing failed. Please try again with a different image."


class OCRNoTextError(DVSBaseError):
    """Raised when OCR returns no usable text."""
    status_code = 422
    user_message = (
        "Unable to extract text from this image. "
        "Please upload a clearer, well-lit image of the passport."
    )


class ValidationServiceError(DVSBaseError):
    """Raised when document validation service encounters an internal failure."""
    status_code = 500
    user_message = "Document validation failed unexpectedly. Please try again."


class ForensicAnalysisError(DVSBaseError):
    """Raised when the Module 3 forensic analysis pipeline encounters an internal failure."""
    status_code = 500
    user_message = "Forensic analysis failed unexpectedly. Please try again."


class BiometricVerificationError(DVSBaseError):
    """Raised when Module 4 biometric verification encounters an internal failure."""
    status_code = 500
    user_message = "Face verification failed unexpectedly. Please try again."


# ──────────────────────────────────────────────
#  Module 5 — Registry Verification exceptions
# ──────────────────────────────────────────────

class RegistryProviderUnavailable(DVSBaseError):
    """
    Raised when the configured registry provider cannot be reached.

    IMPORTANT: This is NOT equivalent to 'document invalid'.
    It means the registry simply could not be checked at this time.
    The Risk Engine must treat this as UNAVAILABLE evidence, not fraud.
    """
    status_code = 503
    user_message = (
        "Registry verification service is temporarily unavailable. "
        "The document cannot be checked against the registry at this time."
    )


class RegistryTimeout(DVSBaseError):
    """
    Raised when a registry provider call exceeds the configured timeout.

    A timeout must NOT block the entire border screening workflow.
    The registry check is recorded as TIMEOUT in the evidence trail.
    """
    status_code = 504
    user_message = (
        "Registry verification timed out. "
        "The registry could not respond within the allowed time window."
    )


class RegistryAuthenticationError(DVSBaseError):
    """
    Raised when an external registry provider rejects the authentication.

    SECURITY: Never log authentication tokens or credentials.
    Only log that authentication failed, not the credentials themselves.
    """
    status_code = 502
    user_message = (
        "Registry authentication failed. "
        "Please contact system administration to verify registry credentials."
    )


class RegistryProviderError(DVSBaseError):
    """
    Raised when the registry provider returns an unexpected error response.
    Indicates a provider-side failure, not a document authenticity finding.
    """
    status_code = 502
    user_message = (
        "Registry provider encountered an unexpected error. "
        "The registry check could not be completed."
    )


class RegistryRecordNotFound(DVSBaseError):
    """
    Raised when the provider confirms no matching record exists.

    NOT_FOUND is distinct from provider failure:
    - NOT_FOUND means the provider was reached but has no record.
    - UNAVAILABLE means the provider could not be reached.

    This exception is typically caught internally and mapped to
    RegistryStatus.NOT_FOUND in the response — it is NOT a 404 API error.
    """
    status_code = 200  # Not a server error — caller handles it
    user_message = "No matching registry record was found for this document."


class RegistryResponseInvalid(DVSBaseError):
    """
    Raised when the provider returns a response that fails schema validation.

    SECURITY: External provider responses must always be validated before use.
    Never trust provider data blindly.
    """
    status_code = 502
    user_message = (
        "Registry provider returned an invalid response. "
        "The response failed schema validation."
    )


class RegistryConfigurationError(DVSBaseError):
    """
    Raised when the registry engine or provider is misconfigured.
    Typically indicates a deployment configuration issue.
    """
    status_code = 500
    user_message = (
        "Registry service configuration error. "
        "Please contact system administration."
    )


# ───────────────────────────────────────────────
#  Module 6 — Risk Engine exceptions
# ───────────────────────────────────────────────

class RiskEngineError(DVSBaseError):
    """
    Raised when the Module 6 risk engine encounters an unexpected failure.

    This is a service-level error, not an adverse verification finding.
    A scoring failure does NOT imply the document is invalid or forged.
    """
    status_code = 500
    user_message = (
        "Risk assessment failed unexpectedly. "
        "Please try again. The document can still be reviewed manually."
    )


class RiskSessionUnavailable(DVSBaseError):
    """
    Raised when the risk session data is not found for a verification_id.

    This typically means the preceding modules (M1–M5) did not complete
    or the session has expired.
    """
    status_code = 404
    user_message = (
        "Risk assessment session not found. "
        "Please ensure all verification steps have completed before requesting risk assessment."
    )

# ──────────────────────────────────────────────
#  Document Profile exceptions
# ──────────────────────────────────────────────

class DocumentProfileError(DVSBaseError):
    """Base error for document profile resolution and validation failures."""
    status_code = 422
    user_message = "Document profile error."


class UnknownDocumentTypeError(DocumentProfileError):
    """Raised when an unknown document type string is provided."""
    status_code = 404
    user_message = "Unknown document type specified."

    def __init__(self, doc_type: str):
        self.doc_type = doc_type
        super().__init__(f"Document type '{doc_type}' is not recognized by the system.")


class UnsupportedDocumentTypeError(DocumentProfileError):
    """Raised when a document type is recognized but not yet supported or operational."""
    status_code = 422
    user_message = "This document type is not yet supported for verification."

    def __init__(self, doc_type: str, status_str: str = "coming_soon"):
        self.doc_type = doc_type
        self.status_str = status_str
        super().__init__(f"Document type '{doc_type}' is currently {status_str} and cannot be processed.")


# ──────────────────────────────────────────────
#  Verification Case exceptions
# ──────────────────────────────────────────────

class CaseError(DVSBaseError):
    """Base error for multi-document verification case failures."""
    status_code = 400
    user_message = "Verification case error."


class CaseNotFoundError(CaseError):
    """Raised when a requested case_id does not exist in the store."""
    status_code = 404
    user_message = "Verification case not found."

    def __init__(self, case_id: str):
        self.case_id = case_id
        super().__init__(f"Verification case '{case_id}' was not found.")


class DocumentNotFoundError(CaseError):
    """Raised when a document_id does not exist inside a case."""
    status_code = 404
    user_message = "Document not found in verification case."

    def __init__(self, document_id: str):
        self.document_id = document_id
        super().__init__(f"Document '{document_id}' was not found in case.")


class DuplicateDocumentTypeError(CaseError):
    """Raised when attempting to add a document type that already exists without replacement flag."""
    status_code = 409
    user_message = "A document of this type already exists in the verification case."

    def __init__(self, doc_type: str):
        self.doc_type = doc_type
        super().__init__(f"Document of type '{doc_type}' already exists in this case. Use replacement to supersede.")


class MaxDocumentsExceededError(CaseError):
    """Raised when adding a document would exceed MAX_DOCUMENTS_PER_CASE."""
    status_code = 422
    user_message = "Maximum document limit reached for this verification case."

    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"Cannot add document: case already contains maximum allowed ({limit}) documents.")


# ──────────────────────────────────────────────
#  FastAPI exception handler registration
# ──────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """Attach all custom exception handlers to the FastAPI application."""

    @app.exception_handler(DVSBaseError)
    async def dvs_exception_handler(request: Request, exc: DVSBaseError) -> JSONResponse:
        logger.warning("DVS error [%s]: %s", type(exc).__name__, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.user_message},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log the real error for debugging, never send it to the client.
        logger.error("Unhandled exception on %s %s", request.method, request.url, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected server error occurred. Please try again."},
        )
