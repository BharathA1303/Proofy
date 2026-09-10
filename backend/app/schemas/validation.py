"""
backend/app/schemas/validation.py

Pydantic v2 schemas for Module 2: Document Validation.

Exposes explainable, structured evidence for each check:
- MRZ TD3 structure and length
- ICAO 7-3-1 check digits (Doc Number, DOB, Expiry, Composite)
- Date and expiry validation
- Passport number binding trap
- VIZ <-> MRZ field consistency
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from app.schemas.ocr import MRZData, TravelerFields


class CheckItem(BaseModel):
    """Generic check result item."""
    status: str = Field(..., description="'passed' | 'failed' | 'warning' | 'insufficient_data' | 'unknown'")
    valid: bool
    message: str


class CheckDigitEvidence(BaseModel):
    """Detailed evidence for an ICAO modulo-10 7-3-1 check digit check."""
    status: str = Field(..., description="'passed' | 'failed' | 'unknown'")
    valid: bool
    computed: int
    actual: Optional[int] = None
    message: str


class ExpiryCheckEvidence(BaseModel):
    """Evidence for passport expiration check."""
    status: str = Field(..., description="'passed' | 'failed' | 'unknown'")
    valid: bool
    expired: Optional[bool] = None
    expiry_date: Optional[str] = None
    message: str


class ValidityPeriodEvidence(BaseModel):
    """Evidence for the issue-to-expiry validity window check."""
    status: str = Field(..., description="'passed' | 'warning' | 'unknown'")
    valid: bool
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    validity_years: Optional[float] = None
    exceeds_standard_term: bool = False
    message: str


class PassportBindingEvidence(BaseModel):
    """Evidence for the Passport Number Binding Trap (VIZ <-> MRZ)."""
    status: str = Field(..., description="'passed' | 'failed' | 'unknown'")
    valid: bool
    viz_value: Optional[str] = None
    mrz_value: Optional[str] = None
    match: Optional[bool] = None
    message: str


class FieldConsistencyItem(BaseModel):
    """Evidence for a single field cross-check between VIZ and MRZ."""
    viz: Optional[str] = None
    mrz: Optional[str] = None
    match: Optional[bool] = None
    status: str = Field(..., description="'match' | 'mismatch' | 'unknown'")
    message: str


class VizMrzConsistencyReport(BaseModel):
    """Summary of all cross-zone field consistency checks."""
    status: str = Field(..., description="'passed' | 'failed' | 'warning' | 'unknown'")
    fields: dict[str, FieldConsistencyItem]
    message: str


class ValidationChecks(BaseModel):
    """The full collection of Module 2 document validation checks."""
    mrz_structure: CheckItem
    document_number_checksum: CheckDigitEvidence
    dob_checksum: CheckDigitEvidence
    expiry_checksum: CheckDigitEvidence
    composite_checksum: CheckDigitEvidence
    expiry_date: ExpiryCheckEvidence
    validity_period: Optional[ValidityPeriodEvidence] = None
    passport_number_binding: PassportBindingEvidence
    viz_mrz_consistency: VizMrzConsistencyReport


from typing import Any, Optional, Union
from pydantic import BaseModel, Field, model_validator


class ValidationIssue(BaseModel):
    """An individual warning or failure issue found during validation."""
    severity: str = Field("warning", description="'critical' | 'failure' | 'warning' | 'info'")
    check: str = Field("validation_check", description="Key of the check that produced this issue")
    message: str = Field("", description="Human-readable explanation of the issue")


class DocumentValidationSummary(BaseModel):
    """The complete result and evidence collection from Module 2."""
    status: str = Field(
        ...,
        description="'passed' | 'failed' | 'warning' | 'insufficient_data'",
    )
    summary: str
    checks: Union[ValidationChecks, dict[str, Any]]
    issues: list[ValidationIssue] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_issues(cls, data: Any) -> Any:
        if isinstance(data, dict) and "issues" in data and isinstance(data["issues"], list):
            normalized = []
            for item in data["issues"]:
                if isinstance(item, dict):
                    chk = item.get("check") or item.get("issue_type") or item.get("field") or "validation_check"
                    msg = item.get("message") or item.get("description") or item.get("details") or str(chk)
                    sev = item.get("severity", "warning")
                    normalized.append({"severity": sev, "check": str(chk), "message": str(msg)})
                else:
                    normalized.append(item)
            data["issues"] = normalized
        return data


class DocumentValidationRequest(BaseModel):
    """Request payload for POST /api/v1/verification/validate."""
    verification_id: str
    document_type: str = "passport"
    mrz: Optional[MRZData] = None
    traveler: Optional[TravelerFields] = None
    related_passport_number: Optional[str] = None



class DocumentValidationResponse(BaseModel):
    """Response payload returned by POST /api/v1/verification/validate."""
    verification_id: str
    document_type: str
    document_validation: DocumentValidationSummary


PassportValidationRequest = DocumentValidationRequest
PassportValidationResponse = DocumentValidationResponse
