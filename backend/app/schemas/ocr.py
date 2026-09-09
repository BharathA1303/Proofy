"""
backend/app/schemas/ocr.py

Pydantic v2 request/response schemas for the OCR endpoint.

Important design notes:
- All traveler fields are Optional — we never fabricate values.
- FieldDetail preserves per-field confidence and bbox for future forensics.
- MRZData keeps raw and normalized text separately.
- Extraction ≠ validation: presence of MRZ fields does NOT imply ICAO validity.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


# ──────────────────────────────────────────────
#  Sub-models
# ──────────────────────────────────────────────

class FieldDetail(BaseModel):
    """
    A single extracted field with its source metadata.
    Preserved for future forensic evidence and explainability panels.
    """
    value: Optional[str] = None
    confidence: Optional[float] = None
    # Bounding box: list of [x, y] corner points (polygon from PaddleOCR)
    bbox: Optional[list[list[int]]] = None


class TravelerFields(BaseModel):
    """
    Traveler identity fields extracted by OCR.
    All fields are Optional — absent fields are null, never fabricated.
    Keys match the frontend VerificationContext traveler state exactly.
    """
    name: Optional[str] = None
    docNumber: Optional[str] = None
    dob: Optional[str] = None
    nationality: Optional[str] = None
    gender: Optional[str] = None
    placeOfBirth: Optional[str] = None
    authority: Optional[str] = None
    issuedDate: Optional[str] = None
    expiry: Optional[str] = None
    # Combined MRZ string for display in the MRZ strip (line1 + \n + line2)
    mrz: Optional[str] = None

    # Visa-specific fields
    visaType: Optional[str] = None
    visaCategory: Optional[str] = None
    entries: Optional[str] = None
    durationOfStay: Optional[str] = None
    passportNumber: Optional[str] = None

    # Driving License fields
    licenseNumber: Optional[str] = None
    vehicleClass: Optional[str] = None
    bloodGroup: Optional[str] = None
    validFrom: Optional[str] = None
    validTo: Optional[str] = None
    state: Optional[str] = None

    # National ID / Aadhaar fields
    identityNumber: Optional[str] = None
    maskedIdentityNumber: Optional[str] = None
    yearOfBirth: Optional[str] = None
    address: Optional[str] = None
    qrPayload: Optional[str] = None
    qrDecoded: Optional[bool] = None

    # Voter ID / EPIC fields
    epicNumber: Optional[str] = None
    fatherName: Optional[str] = None
    age: Optional[str] = None
    constituency: Optional[str] = None
    issuingState: Optional[str] = None

    # PAN Card fields
    panNumber: Optional[str] = None
    taxpayerCategory: Optional[str] = None

    # Border Permit fields
    permitNumber: Optional[str] = None
    permitType: Optional[str] = None
    borderZone: Optional[str] = None
    portOfEntry: Optional[str] = None


class MRZData(BaseModel):
    """
    Machine Readable Zone extraction result.

    IMPORTANT: presence of these fields indicates EXTRACTION only.
    MRZ structural validity / ICAO 9303 checksum validation is Module 2.
    Do NOT interpret extracted MRZ as a validated document.
    """
    line1: Optional[str] = None
    line2: Optional[str] = None
    # Raw text as returned by OCR before normalization
    raw_line1: Optional[str] = None
    raw_line2: Optional[str] = None
    # Per-line OCR confidence
    confidence_line1: Optional[float] = None
    confidence_line2: Optional[float] = None


class OCRMeta(BaseModel):
    """Aggregate OCR quality metadata."""
    overall_confidence: Optional[float] = None
    region_count: int = 0
    # Low-confidence flag: true if any field is below 0.70
    has_low_confidence_regions: bool = False
    skew_angle: Optional[float] = None


class OCRRegionRaw(BaseModel):
    """A single raw OCR detection region — stored for forensics / debugging."""
    text: str
    confidence: float
    bbox: list[list[int]]


# ──────────────────────────────────────────────
#  Top-level response
# ──────────────────────────────────────────────

from app.schemas.quality import DocumentQualityResponse

class DocumentOCRResponse(BaseModel):
    """
    Canonical response returned by POST /api/v1/verification/ocr for all documents.

    status values:
      "completed" — OCR ran, primary fields were extracted
      "partial"   — OCR ran but extracted sparse text
      "failed"    — OCR could not extract meaningful text
    """
    verification_id: str
    document_type: str
    status: str  # "completed" | "partial" | "failed"
    traveler: TravelerFields
    mrz: Optional[MRZData] = Field(default_factory=MRZData)
    ocr: OCRMeta
    quality: Optional[DocumentQualityResponse] = None
    document_face_image: Optional[str] = None


# Backward-compatible alias for existing passport tests/handlers
PassportOCRResponse = DocumentOCRResponse


# ──────────────────────────────────────────────
#  Error response (for OpenAPI docs)
# ──────────────────────────────────────────────

class ErrorResponse(BaseModel):
    detail: str = Field(..., examples=["Unable to decode the uploaded image."])
