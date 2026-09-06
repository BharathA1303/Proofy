"""
backend/app/api/v1/verification.py

FastAPI router for the verification API.

Phase 1 endpoint:
  POST /api/v1/verification/ocr
    - Accepts multipart/form-data with document image + document_type
    - Runs ingestion → preprocessing → OCR → document-specific parser
    - Returns structured PassportOCRResponse

Future endpoints (Phase 2+):
  POST /api/v1/verification/validate   — Module 2: Document Validation
  POST /api/v1/verification/forensic   — Module 3: Tampering Detection
  GET  /api/v1/verification/{id}       — Fetch session result
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import settings
from app.core.exceptions import (
    BiometricVerificationError,
    DocumentIngestionError,
    ForensicAnalysisError,
    OCREngineError,
    OCRNoTextError,
    RegistryConfigurationError,
    RegistryProviderUnavailable,
    RegistryTimeout,
    RegistryProviderError,
)
from app.schemas.ocr import (
    DocumentOCRResponse,
    MRZData,
    OCRMeta,
    PassportOCRResponse,
    TravelerFields,
)
from app.services.ingestion.document_ingestion import ingest_document
from app.services.ocr import ocr_engine
from app.services.ocr.passport_parser import parse_passport
from app.services.documents.border_permit.border_permit_parser import parse_border_permit
from app.services.documents.border_permit.border_permit_validator import (
    validate_border_permit_document,
)
from app.services.documents.driving_license.dl_parser import parse_driving_license
from app.services.documents.driving_license.dl_validator import (
    validate_driving_license_document,
)
from app.services.documents.national_id.national_id_parser import parse_national_id
from app.services.documents.national_id.national_id_validator import (
    validate_national_id_document,
)
from app.services.documents.profiles import document_profile_registry
from app.services.documents.visa.visa_parser import parse_visa
from app.services.documents.visa.visa_validator import validate_visa_document
from app.services.preprocessing.image_preprocessor import preprocess
from app.schemas.validation import (
    DocumentValidationRequest,
    DocumentValidationResponse,
    DocumentValidationSummary,
    PassportValidationRequest,
    PassportValidationResponse,
)
from app.services.validation.passport_validation_service import validate_passport_document
from app.schemas.forensics import ForensicAnalysisResponse
from app.services.forensics.forensic_service import run_forensic_analysis
from app.schemas.face_verification import FaceVerificationResponse, ModelInfoResponse
from app.services.face.face_verification_service import face_verification_service, verify_passport_biometrics
from app.services.face.session_store import session_document_store
from app.schemas.registry import RegistryVerificationResponse, RegistryVerifyRequest
from app.services.registry.engine import registry_engine
from app.services.registry.session_store import registry_session_store
from app.schemas.risk import RiskVerifyRequest, RiskAssessmentResponse
from app.services.risk.risk_engine import risk_engine
from app.services.risk.risk_session_store import risk_session_store
from app.core.exceptions import RiskEngineError, UnsupportedDocumentTypeError


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verification", tags=["Verification"])


@router.post(
    "/ocr",
    response_model=PassportOCRResponse,
    status_code=status.HTTP_200_OK,
    summary="Run OCR extraction on a document image",
    description=(
        "Accepts a passport (or other document) image via multipart upload. "
        "Returns extracted text fields and MRZ data. "
        "Module 1 only: OCR extraction. "
        "No checksum validation, no authenticity scoring."
    ),
    responses={
        400: {"description": "Image cannot be decoded"},
        413: {"description": "File too large"},
        415: {"description": "Unsupported file type"},
        500: {"description": "OCR engine error"},
    },
)
async def ocr_document(
    file: UploadFile = File(..., description="Passport or document image (JPEG/PNG/WEBP)"),
    document_type: str = Form(..., description="Document type key (e.g. 'passport')"),
) -> PassportOCRResponse:
    """
    OCR Extraction endpoint.

    Pipeline:
      1. Ingest (validate size, MIME, decode)
      2. Preprocess (correct orientation, downscale if needed, CLAHE)
      3. Run PaddleOCR (generic engine — not passport-specific)
      4. Parse (passport-specific field & MRZ extraction)
      5. Assemble response

    Returns a PassportOCRResponse with all available fields.
    Fields that could not be extracted are null — never fabricated.
    """
    verification_id = str(uuid.uuid4())
    logger.info(
        "OCR request received: id=%s doc_type=%s filename=%s",
        verification_id, document_type, file.filename,
    )

    # ── Step 0: Resolve Document Profile ─────────────────────────────────────
    profile = document_profile_registry.resolve_operational(document_type)

    # ── Step 1: Ingest ────────────────────────────────────────────────────────
    raw_bytes = await file.read()
    ingested = await ingest_document(
        raw_bytes=raw_bytes,
        declared_mime=file.content_type or "",
        filename=file.filename or "upload",
    )
    # Ephemeral session cache for downstream Module 4 biometrics
    session_document_store.set(verification_id, ingested.raw_bytes)


    # ── Step 2: Preprocess ───────────────────────────────────────────────────
    preprocessed = preprocess(ingested.image_np)
    image_height = preprocessed.image_np.shape[0]

    # ── Step 3: OCR ──────────────────────────────────────────────────────────
    if not ocr_engine.is_ready():
        logger.error("OCR engine not initialized — this should not happen at runtime.")
        raise OCREngineError("OCR service is not available. Please try again.")

    try:
        regions = ocr_engine.run_ocr(preprocessed.image_np)
    except Exception as exc:
        logger.error("OCR engine failure for id=%s: %s", verification_id, exc, exc_info=True)
        raise OCREngineError() from exc

    if not regions:
        logger.warning("OCR returned zero regions for id=%s", verification_id)
        raise OCRNoTextError()

    # ── Step 4: Document-specific parsing ────────────────────────────────────
    parsed_passport = None
    parsed_visa = None
    parsed_dl = None
    parsed_nid = None
    parsed_bp = None

    if profile.document_type == "passport":
        parsed_passport = parse_passport(regions, image_height=image_height)
        mrz_combined: str | None = None
        if parsed_passport.mrz_line1.value and parsed_passport.mrz_line2.value:
            mrz_combined = f"{parsed_passport.mrz_line1.value}\n{parsed_passport.mrz_line2.value}"
        elif parsed_passport.mrz_line1.value:
            mrz_combined = parsed_passport.mrz_line1.value

        traveler = TravelerFields(
            name=parsed_passport.name.value,
            docNumber=parsed_passport.docNumber.value,
            dob=parsed_passport.dob.value,
            nationality=parsed_passport.nationality.value,
            gender=parsed_passport.gender.value,
            placeOfBirth=parsed_passport.placeOfBirth.value,
            authority=parsed_passport.authority.value,
            issuedDate=parsed_passport.issuedDate.value,
            expiry=parsed_passport.expiry.value,
            mrz=mrz_combined,
        )

        mrz_data = MRZData(
            line1=parsed_passport.mrz_line1.value,
            line2=parsed_passport.mrz_line2.value,
            raw_line1=parsed_passport.mrz_line1.value,
            raw_line2=parsed_passport.mrz_line2.value,
            confidence_line1=parsed_passport.mrz_line1.confidence,
            confidence_line2=parsed_passport.mrz_line2.confidence,
        )

        primary_fields_found = sum(1 for v in [
            parsed_passport.name.value,
            parsed_passport.docNumber.value,
            parsed_passport.dob.value,
            parsed_passport.nationality.value,
        ] if v)

        if primary_fields_found >= 3:
            ocr_status = "completed"
        elif primary_fields_found >= 1 or parsed_passport.mrz_line1.value:
            ocr_status = "partial"
        else:
            ocr_status = "partial"

    elif profile.document_type == "visa":
        parsed_visa = parse_visa(regions, image_height=image_height)
        mrz_combined = None
        if parsed_visa.mrz_line1.value and parsed_visa.mrz_line2.value:
            mrz_combined = f"{parsed_visa.mrz_line1.value}\n{parsed_visa.mrz_line2.value}"
        elif parsed_visa.mrz_line1.value:
            mrz_combined = parsed_visa.mrz_line1.value

        traveler = TravelerFields(
            name=parsed_visa.name.value,
            docNumber=parsed_visa.docNumber.value,
            dob=parsed_visa.dob.value,
            nationality=parsed_visa.nationality.value,
            placeOfBirth=None,
            authority=parsed_visa.authority.value,
            issuedDate=parsed_visa.issuedDate.value,
            expiry=parsed_visa.expiry.value,
            mrz=mrz_combined,
            visaType=parsed_visa.visaType.value,
            visaCategory=parsed_visa.visaCategory.value,
            entries=parsed_visa.entries.value,
            durationOfStay=parsed_visa.durationOfStay.value,
            passportNumber=parsed_visa.passportNumber.value,
        )

        mrz_data = MRZData(
            line1=parsed_visa.mrz_line1.value,
            line2=parsed_visa.mrz_line2.value,
            raw_line1=parsed_visa.mrz_line1.value,
            raw_line2=parsed_visa.mrz_line2.value,
            confidence_line1=parsed_visa.mrz_line1.confidence,
            confidence_line2=parsed_visa.mrz_line2.confidence,
        )

        primary_fields_found = sum(1 for v in [
            parsed_visa.name.value,
            parsed_visa.docNumber.value,
            parsed_visa.dob.value,
            parsed_visa.nationality.value,
        ] if v)

        if primary_fields_found >= 3:
            ocr_status = "completed"
        elif primary_fields_found >= 1 or (parsed_visa.docNumber.value and parsed_visa.name.value):
            ocr_status = "partial"
        else:
            ocr_status = "partial"

    elif profile.document_type == "driving_license":
        parsed_dl = parse_driving_license(regions, image_height=image_height)
        mrz_combined = None
        traveler = TravelerFields(
            name=parsed_dl.name.value,
            docNumber=parsed_dl.license_number.value,
            dob=parsed_dl.dob.value,
            nationality=None,
            placeOfBirth=None,
            authority=parsed_dl.issuing_authority.value,
            issuedDate=parsed_dl.issuedDate.value,
            expiry=parsed_dl.expiry.value,
            mrz=None,
            licenseNumber=parsed_dl.license_number.value,
            vehicleClass=parsed_dl.vehicle_classes.value,
            bloodGroup=parsed_dl.blood_group.value,
            validFrom=parsed_dl.valid_from.value,
            validTo=parsed_dl.valid_to.value,
            state=parsed_dl.state.value,
        )
        mrz_data = MRZData()

        primary_fields_found = sum(1 for v in [
            parsed_dl.name.value,
            parsed_dl.license_number.value,
            parsed_dl.dob.value,
        ] if v)

        if primary_fields_found >= 3:
            ocr_status = "completed"
        elif primary_fields_found >= 1 or (parsed_dl.license_number.value and parsed_dl.name.value):
            ocr_status = "partial"
        else:
            ocr_status = "partial"

    elif profile.document_type in ("national_id", "nationalid", "nid", "aadhaar"):
        parsed_nid = parse_national_id(regions)
        mrz_combined = None
        traveler = TravelerFields(
            name=parsed_nid.name.value,
            docNumber=parsed_nid.identity_number.value,
            dob=parsed_nid.dob.value,
            yearOfBirth=parsed_nid.year_of_birth.value,
            gender=parsed_nid.gender.value,
            authority=parsed_nid.issuing_authority.value,
            address=parsed_nid.address.value,
            identityNumber=parsed_nid.identity_number.value,
            maskedIdentityNumber=parsed_nid.masked_identity_number,
            qrPayload=parsed_nid.qr_payload,
            qrDecoded=parsed_nid.qr_decoded,
        )
        mrz_data = MRZData()

        primary_fields_found = sum(1 for v in [
            parsed_nid.name.value,
            parsed_nid.identity_number.value,
            parsed_nid.dob.value or parsed_nid.year_of_birth.value,
        ] if v)

        if primary_fields_found >= 3:
            ocr_status = "completed"
        elif primary_fields_found >= 1 or (parsed_nid.identity_number.value and parsed_nid.name.value):
            ocr_status = "partial"
        else:
            ocr_status = "partial"

    elif profile.document_type in ("border_permit", "borderpermit"):
        parsed_bp = parse_border_permit(regions, image_height=image_height)
        traveler = TravelerFields(
            name=parsed_bp.name.value,
            docNumber=parsed_bp.permit_number.value,
            permitNumber=parsed_bp.permit_number.value,
            passportNumber=parsed_bp.passport_number.value,
            dob=parsed_bp.dob.value,
            validFrom=parsed_bp.valid_from.value,
            validTo=parsed_bp.valid_to.value,
            expiry=parsed_bp.valid_to.value,
            permitType=parsed_bp.permit_type.value,
            borderZone=parsed_bp.border_zone.value,
            portOfEntry=parsed_bp.port_of_entry.value,
            authority=parsed_bp.issuing_authority.value,
            qrPayload=parsed_bp.qr_payload,
            qrDecoded=parsed_bp.qr_decoded,
        )
        mrz_data = MRZData()

        primary_fields_found = sum(1 for v in [
            parsed_bp.name.value,
            parsed_bp.permit_number.value,
            parsed_bp.valid_to.value,
        ] if v)

        if primary_fields_found >= 3:
            ocr_status = "completed"
        elif primary_fields_found >= 1 or parsed_bp.permit_number.value:
            ocr_status = "partial"
        else:
            ocr_status = "partial"

    else:
        traveler = TravelerFields()
        mrz_data = MRZData()
        ocr_status = "partial"
        mrz_combined = None

    # ── Step 5: Assemble response ─────────────────────────────────────────────
    confidences = [r.confidence for r in regions]
    overall_conf = round(sum(confidences) / len(confidences), 4) if confidences else None
    low_conf_count = sum(1 for c in confidences if c < 0.70)
    ocr_meta = OCRMeta(
        overall_confidence=overall_conf,
        region_count=len(regions),
        has_low_confidence_regions=low_conf_count > 0,
    )

    response = PassportOCRResponse(
        verification_id=verification_id,
        document_type=profile.document_type,
        status=ocr_status,
        traveler=traveler,
        mrz=mrz_data,
        ocr=ocr_meta,
    )

    logger.info(
        "OCR complete: id=%s doc_type=%s status=%s regions=%d overall_conf=%.3f",
        verification_id, profile.document_type, ocr_status, len(regions), overall_conf or 0.0,
    )

    # ── Populate Risk Session Store for Module 6 (M1 evidence) ────────────────
    try:
        risk_session_store.update_module(
            verification_id, "m1_ocr",
            {
                "status": ocr_status,
                "overall_confidence": overall_conf,
                "region_count": len(regions),
                "low_conf_count": low_conf_count,
                "has_low_confidence_regions": low_conf_count > 0,
                "mrz_detected": bool(mrz_combined),
                "mrz_applicable": profile.mrz_applicable,
                "traveler_fields": traveler.model_dump(),
            },
        )
    except Exception as _risk_exc:
        logger.warning("Failed to update risk session M1: %s", _risk_exc)

    # ── Populate Registry Session Store for Module 5 ─────────────────────────
    _populate_registry_session(
        verification_id=verification_id,
        document_type=profile.document_type,
        parsed=parsed_passport or parsed_visa or parsed_dl or parsed_nid or parsed_bp,
        traveler=response.traveler,
        mrz=response.mrz,
    )

    return response


@router.get(
    "/sample/passport",
    summary="Serve the synthetic test passport sample",
    description=(
        "Returns the synthetic (non-real) passport test image for development testing. "
        "This image is clearly labelled 'SYNTHETIC TEST DOCUMENT'. "
        "It is intended for end-to-end UI testing of the OCR pipeline only."
    ),
    response_class=FileResponse,
    tags=["Verification"],
)
async def get_sample_passport() -> FileResponse:
    """
    Serve the synthetic test passport image for the frontend 'Load Sample' button.

    The sample image lives at: backend/tests/assets/sample_passport.jpg
    It is a generated image with fictional data — no real person's information.
    """
    sample_path = Path(__file__).parent.parent.parent.parent / "tests" / "assets" / "sample_passport.jpg"

    if not sample_path.exists():
        logger.warning("Sample passport image not found at: %s", sample_path)
        return JSONResponse(
            status_code=404,
            content={"detail": "Sample document not found. Run tests/create_synthetic_passport.py to generate it."},
        )

    return FileResponse(
        path=str(sample_path),
        media_type="image/jpeg",
        filename="Sample_Passport.jpg",
        headers={"Cache-Control": "no-cache"},
    )


@router.get(
    "/sample/visa",
    summary="Serve the synthetic test visa sample",
    description=(
        "Returns the synthetic (non-real) visa test image for development testing. "
        "This image is clearly labelled 'SYNTHETIC TEST DOCUMENT'. "
        "It is intended for end-to-end UI testing of the Visa pipeline only."
    ),
    response_class=FileResponse,
    tags=["Verification"],
)
async def get_sample_visa() -> FileResponse:
    """
    Serve the synthetic test visa image for the frontend 'Load Sample' button.

    The sample image lives at: backend/tests/assets/sample_visa.jpg
    It is a generated image with fictional data — no real person's information.
    """
    sample_path = Path(__file__).parent.parent.parent.parent / "tests" / "assets" / "sample_visa.jpg"

    if not sample_path.exists():
        logger.warning("Sample visa image not found at: %s", sample_path)
        return JSONResponse(
            status_code=404,
            content={"detail": "Sample document not found. Run tests/create_synthetic_visa.py to generate it."},
        )

    return FileResponse(
        path=str(sample_path),
        media_type="image/jpeg",
        filename="Sample_Visa.jpg",
        headers={"Cache-Control": "no-cache"},
    )


@router.get(
    "/sample/driving_license",
    summary="Serve the synthetic test driving license sample",
    description=(
        "Returns the synthetic (non-real) driving license test image for development testing. "
        "This image is clearly labelled 'SYNTHETIC TEST DOCUMENT'. "
        "It is intended for end-to-end UI testing of the Driving License pipeline only."
    ),
    response_class=FileResponse,
    tags=["Verification"],
)
async def get_sample_driving_license() -> FileResponse:
    """
    Serve the synthetic test driving license image for the frontend 'Load Sample' button.

    The sample image lives at: backend/tests/assets/sample_driving_license.jpg
    It is a generated image with fictional data — no real person's information.
    """
    sample_path = Path(__file__).parent.parent.parent.parent / "tests" / "assets" / "sample_driving_license.jpg"

    if not sample_path.exists():
        logger.warning("Sample driving license image not found at: %s", sample_path)
        return JSONResponse(
            status_code=404,
            content={"detail": "Sample document not found. Run tests/create_synthetic_driving_license.py to generate it."},
        )

    return FileResponse(
        path=str(sample_path),
        media_type="image/jpeg",
        filename="Sample_Driving_License.jpg",
        headers={"Cache-Control": "no-cache"},
    )


@router.get(
    "/sample/national_id",
    summary="Serve the synthetic test national id sample",
    description=(
        "Returns the synthetic (non-real) national id test image for development testing. "
        "This image is clearly labelled 'SYNTHETIC TEST NATIONAL ID'. "
        "It is intended for end-to-end UI testing of the National ID pipeline only."
    ),
    response_class=FileResponse,
    tags=["Verification"],
)
async def get_sample_national_id() -> FileResponse:
    """
    Serve the synthetic test national id image for the frontend 'Load Sample' button.

    The sample image lives at: backend/tests/assets/sample_national_id.jpg
    It is a generated image with fictional data — no real person's information.
    """
    sample_path = Path(__file__).parent.parent.parent.parent / "tests" / "assets" / "sample_national_id.jpg"

    if not sample_path.exists():
        logger.warning("Sample national id image not found at: %s", sample_path)
        return JSONResponse(
            status_code=404,
            content={"detail": "Sample document not found. Run tests/create_synthetic_national_id.py to generate it."},
        )

    return FileResponse(
        path=str(sample_path),
        media_type="image/jpeg",
        filename="Sample_National_ID.jpg",
        headers={"Cache-Control": "no-cache"},
    )


@router.get(
    "/sample/border_permit",
    summary="Serve the synthetic test border permit sample",
    description=(
        "Returns the synthetic (non-real) border permit test image for development testing. "
        "This image is clearly labelled 'SYNTHETIC TEST BORDER PERMIT'. "
        "It is intended for end-to-end UI testing of the Border Permit pipeline only."
    ),
    response_class=FileResponse,
    tags=["Verification"],
)
async def get_sample_border_permit() -> FileResponse:
    sample_path = Path(__file__).parent.parent.parent.parent / "tests" / "assets" / "sample_border_permit.jpg"

    if not sample_path.exists():
        logger.warning("Sample border permit image not found at: %s", sample_path)
        return JSONResponse(
            status_code=404,
            content={"detail": "Sample document not found. Run tests/create_synthetic_border_permit.py to generate it."},
        )

    return FileResponse(
        path=str(sample_path),
        media_type="image/jpeg",
        filename="Sample_Border_Permit.jpg",
        headers={"Cache-Control": "no-cache"},
    )


@router.post(
    "/validate",
    response_model=DocumentValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate document data against format rules, expiration, and cross-field binding",
    description=(
        "Module 2: Document Validation.\n"
        "Consumes structured OCR output. For passports, validates TD3 MRZ structure, "
        "ICAO 7-3-1 check digits, date validity, and executes the Passport Number Binding Trap.\n"
        "For visas, validates required fields, visa number format, date chronology, expiration, "
        "and optional cross-document passport reference.\n"
        "For national ids, validates 12-digit format, Verhoeff checksum, date/year validity, and QR consistency.\n"
        "For border permits, validates required fields, permit format, validity period, and passport binding."
    ),
    tags=["Verification"],
)
async def validate_document(payload: DocumentValidationRequest) -> DocumentValidationResponse:
    """
    Execute Module 2 Document Validation.

    Resolves document profile and delegates to the appropriate document validator.
    Takes structured traveler fields and MRZ lines (from Module 1 OCR),
    runs deterministic checksums or format/chronology checks,
    and returns a structured, explainable DocumentValidationSummary.
    """
    logger.info(
        "Validation request received: id=%s doc_type=%s",
        payload.verification_id,
        payload.document_type,
    )

    profile = document_profile_registry.resolve_operational(payload.document_type)

    if profile.document_type == "passport":
        validation_summary = validate_passport_document(
            mrz_data=payload.mrz,
            traveler=payload.traveler,
        )
    elif profile.document_type == "visa":
        summary_dict = validate_visa_document(
            traveler=payload.traveler,
            related_passport_number=payload.related_passport_number,
        )
        validation_summary = DocumentValidationSummary(**summary_dict)
    elif profile.document_type == "driving_license":
        summary_dict = validate_driving_license_document(
            traveler=payload.traveler,
        )
        validation_summary = DocumentValidationSummary(**summary_dict)
    elif profile.document_type in ("national_id", "nationalid", "nid", "aadhaar"):
        summary_dict = validate_national_id_document(
            traveler=payload.traveler,
        )
        validation_summary = DocumentValidationSummary(**summary_dict)
    elif profile.document_type in ("border_permit", "borderpermit"):
        summary_dict = validate_border_permit_document(
            traveler=payload.traveler,
        )
        validation_summary = DocumentValidationSummary(**summary_dict)
    else:
        raise UnsupportedDocumentTypeError(profile.document_type)

    # ── Populate Risk Session Store for Module 6 (M2 evidence) ────────────────────
    try:
        if hasattr(validation_summary.checks, "__dict__"):
            checks_dict = {
                k: {"valid": getattr(v, "valid", None),
                    "status": getattr(v, "status", None),
                    "message": getattr(v, "message", None),
                    **{fk: getattr(v, fk, None)
                       for fk in ("computed", "actual", "expired", "expiry_date",
                                  "match", "viz_value", "mrz_value", "fields")}}
                for k, v in validation_summary.checks.__dict__.items()
                if v is not None
            }
        elif isinstance(validation_summary.checks, dict):
            checks_dict = validation_summary.checks
        else:
            checks_dict = {}

        risk_session_store.update_module(
            payload.verification_id, "m2_validation",
            {
                "status": validation_summary.status,
                "summary": validation_summary.summary,
                "checks": checks_dict,
            },
        )
    except Exception as _risk_exc:
        logger.warning("Failed to update risk session M2: %s", _risk_exc)

    return DocumentValidationResponse(
        verification_id=payload.verification_id,
        document_type=profile.document_type,
        document_validation=validation_summary,
    )


@router.post(
    "/forensic",
    response_model=ForensicAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Run tampering & forensic analysis on the original document image",
    description=(
        "Module 3: Tampering & Forensic Analysis.\n"
        "Operates on the ORIGINAL uploaded image (not the OCR-preprocessed copy). "
        "Runs image quality assessment, Error Level Analysis, photo boundary/edge "
        "analysis, local compression consistency analysis, and metadata analysis. "
        "Produces a conservative, explainable, evidence-based assessment — "
        "never a final fraud determination."
    ),
    responses={
        400: {"description": "Image cannot be decoded"},
        413: {"description": "File too large"},
        415: {"description": "Unsupported file type"},
        500: {"description": "Forensic analysis engine error"},
    },
)
async def forensic_analysis(
    file: UploadFile = File(..., description="The ORIGINAL passport image (same file submitted to /ocr)"),
    document_type: str = Form(..., description="Document type key (e.g. 'passport')"),
    verification_id: str = Form(..., description="verification_id returned by the /ocr call for this session"),
) -> ForensicAnalysisResponse:
    """
    Module 3 endpoint.

    Re-ingests the original image bytes (same ingestion path as /ocr — no
    second upload pipeline is created) so forensic techniques run on the
    unmodified original rather than any downstream OCR-preprocessed copy.
    """
    profile = document_profile_registry.resolve_operational(document_type)

    logger.info(
        "Forensic analysis request received: id=%s doc_type=%s filename=%s",
        verification_id, profile.document_type, file.filename,
    )

    raw_bytes = await file.read()
    ingested = await ingest_document(
        raw_bytes=raw_bytes,
        declared_mime=file.content_type or "",
        filename=file.filename or "upload",
    )
    # Refresh ephemeral session store for downstream Module 4 biometrics
    session_document_store.set(verification_id, ingested.raw_bytes)

    try:
        forensic_summary = run_forensic_analysis(
            ingested.raw_bytes,
            ingested.image_np,
            document_type=profile.document_type,
        )
    except Exception as exc:
        logger.error("Forensic analysis failure for id=%s: %s", verification_id, exc, exc_info=True)
        raise ForensicAnalysisError() from exc

    logger.info(
        "Forensic analysis complete: id=%s status=%s overall=%s",
        verification_id, forensic_summary.status, forensic_summary.overall_assessment,
    )

    # ── Populate Risk Session Store for Module 6 (M3 evidence) ────────────────────
    try:
        risk_session_store.update_module(
            verification_id, "m3_forensics",
            {
                "status":             forensic_summary.status,
                "overall_assessment": forensic_summary.overall_assessment,
                "signals": [
                    {
                        "type":        s.type,
                        "status":      s.status,
                        "severity":    s.severity,
                        "confidence":  s.confidence,
                        "description": s.description,
                    }
                    for s in forensic_summary.signals
                ],
            },
        )
    except Exception as _risk_exc:
        logger.warning("Failed to update risk session M3: %s", _risk_exc)

    return ForensicAnalysisResponse(
        verification_id=verification_id,
        document_type=profile.document_type,
        forensic_analysis=forensic_summary,
    )


@router.post(
    "/face",
    response_model=FaceVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute biometric face verification and presentation attack detection",
    description=(
        "Module 4: Face Verification & Anti-Spoofing.\n"
        "Compares live camera frame against document photograph. "
        "Produces independent telemetry for Document Face Quality, Live Face Quality, "
        "Presentation Attack Detection (anti-spoof), and Facial Match Similarity. "
        "Biometric raw data is never persisted or logged."
    ),
    responses={
        400: {"description": "Document or live image cannot be decoded / session expired"},
        413: {"description": "Uploaded image file exceeds size limit"},
        415: {"description": "Unsupported image format"},
        500: {"description": "Biometric verification execution failure"},
    },
)
async def face_verification(
    verification_id: str = Form(..., description="Unique verification session ID from Module 1/2/3"),
    document_type: str = Form(..., description="Document type key (e.g. 'passport')"),
    live_frame: UploadFile = File(..., description="Primary live camera frame capture"),
    live_frames: list[UploadFile] = File(None, description="Optional consecutive frames for multi-frame analysis"),
    document_image: UploadFile = File(None, description="Optional document image fallback if session cache expired"),
) -> FaceVerificationResponse:
    """
    Module 4 endpoint: Biometric Face Verification & Anti-Spoofing.

    Retrieves the document image from ephemeral memory using verification_id.
    Ingests live camera frame, performs face detection, quality gate evaluation,
    presentation attack detection, and normalized vector cosine matching.
    """
    profile = document_profile_registry.resolve_operational(document_type)

    logger.info(
        "Face verification request received: id=%s doc_type=%s live_filename=%s",
        verification_id, profile.document_type, live_frame.filename,
    )

    # ── Step 1: Decode Live Camera Frame ──────────────────────────────────────
    live_raw_bytes = await live_frame.read()
    live_ingested = await ingest_document(
        raw_bytes=live_raw_bytes,
        declared_mime=live_frame.content_type or "",
        filename=live_frame.filename or "live_capture.jpg",
    )

    # ── Step 2: Retrieve or Ingest Document Image ─────────────────────────────
    doc_raw_bytes = session_document_store.get(verification_id)

    if doc_raw_bytes is None:
        if document_image is not None:
            logger.info("Document not found in session cache; consuming fallback document_image upload.")
            doc_raw_bytes = await document_image.read()
            # Store in session store for any subsequent calls
            session_document_store.set(verification_id, doc_raw_bytes)
        else:
            logger.warning("Session %s not found in session store and no document fallback supplied.", verification_id)
            raise DocumentIngestionError(
                "Verification session has expired or original document is not available. "
                "Please re-upload the document."
            )

    doc_ingested = await ingest_document(
        raw_bytes=doc_raw_bytes,
        declared_mime="image/jpeg",
        filename="session_document.jpg",
    )

    # ── Step 3: Decode Optional Sequence Frames (for multi-frame liveness) ───
    sequence_np_list = []
    if live_frames:
        for sf in live_frames:
            try:
                sf_bytes = await sf.read()
                if sf_bytes:
                    sf_ingested = await ingest_document(
                        raw_bytes=sf_bytes,
                        declared_mime=sf.content_type or "",
                        filename=sf.filename or "seq.jpg",
                    )
                    sequence_np_list.append(sf_ingested.image_np)
            except Exception as e:
                logger.debug("Sequence frame decode ignored: %s", e)

    # ── Step 4: Run Module 4 Biometric Verification Pipeline ─────────────────
    try:
        response = verify_passport_biometrics(
            verification_id=verification_id,
            document_type=profile.document_type,
            document_image_bgr=doc_ingested.image_np,
            live_frame_bgr=live_ingested.image_np,
            sequence_frames_bgr=sequence_np_list if sequence_np_list else None,
        )
    except Exception as exc:
        logger.error("Unexpected biometric verification failure for id=%s: %s", verification_id, exc, exc_info=True)
        raise BiometricVerificationError() from exc

    logger.info(
        "Face verification complete: id=%s overall=%s match=%s pad=%s",
        verification_id, response.overall_assessment, response.face_match.status, response.anti_spoof.status,
    )

    # ── Populate Risk Session Store for Module 6 (M4 evidence) ────────────────────
    try:
        secondary_pad = response.secondary_pad
        risk_session_store.update_module(
            verification_id, "m4_biometrics",
            {
                "overall_assessment": response.overall_assessment,
                "document_face": {
                    "detected": response.document_face.detected,
                    "quality":   response.document_face.quality,
                },
                "live_face": {
                    "detected": response.live_face.detected,
                    "quality":   response.live_face.quality,
                },
                "anti_spoof": {
                    "status":      response.anti_spoof.status,
                    "score":       response.anti_spoof.score,
                    "model":       response.anti_spoof.model,
                    "explanation": response.anti_spoof.explanation,
                },
                "secondary_pad": {
                    "frequency_domain":  secondary_pad.frequency_domain,
                    "texture_analysis":  secondary_pad.texture_analysis,
                    "specular_glare":    secondary_pad.specular_glare,
                    "temporal_variance": secondary_pad.temporal_variance,
                } if secondary_pad else {},
                "face_match": {
                    "status":      response.face_match.status,
                    "similarity":  response.face_match.similarity,
                    "threshold":   response.face_match.threshold,
                    "explanation": response.face_match.explanation,
                },
            },
        )
    except Exception as _risk_exc:
        logger.warning("Failed to update risk session M4: %s", _risk_exc)

    return response


@router.get(
    "/face/models",
    response_model=ModelInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get biometric model metadata and operational thresholds",
    description="Returns non-sensitive metadata on loaded face detection, embedding, and PAD models.",
)
async def get_biometric_model_info() -> ModelInfoResponse:
    return face_verification_service.get_model_info()


# ── Module 5: Registry Verification ───────────────────────────────────────────

@router.post(
    "/registry",
    response_model=RegistryVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify document identity against configured registry provider",
    description=(
        "Module 5: Registry Verification Engine.\n"
        "Accepts verification_id and document_type only. "
        "All identity data is retrieved server-side from the session store "
        "populated during the /ocr step — the client NEVER re-submits identity fields.\n\n"
        "DEVELOPMENT MODE: Uses a clearly-labeled development mock registry. "
        "Not connected to any real government database. "
        "source_type='development_mock' is always visible in the response.\n\n"
        "This endpoint produces registry EVIDENCE only. "
        "It does NOT produce risk_score, final_decision, or any fraud verdict. "
        "Those belong to Module 6 (Risk Engine)."
    ),
    responses={
        400: {"description": "Missing or invalid verification_id"},
        404: {"description": "Verification session not found or expired"},
        422: {"description": "Unsupported document type"},
        503: {"description": "Registry provider unavailable"},
        504: {"description": "Registry provider timeout"},
    },
)
async def registry_verification(
    payload: RegistryVerifyRequest,
) -> RegistryVerificationResponse:
    """
    Module 5 endpoint: Registry Verification.

    The server retrieves normalized session data using verification_id.
    The client must only provide the session reference — never raw identity fields.

    Returns structured registry evidence including:
      - Overall registry status (MATCHED/NOT_FOUND/MISMATCH/REVOKED/etc.)
      - Per-field comparison results
      - Provider metadata (source_type is always visible)
      - Audit trail

    Does NOT return: risk_score, final_decision, CLEARED/DENIED verdicts.
    """
    profile = document_profile_registry.resolve_operational(payload.document_type)

    logger.info(
        "Registry verification request received: id=%s doc_type=%s",
        payload.verification_id,
        profile.document_type,
    )

    response = registry_engine.verify(
        verification_id=payload.verification_id,
        document_type=profile.document_type,
    )

    logger.info(
        "Registry verification complete: id=%s doc_type=%s status=%s",
        payload.verification_id,
        profile.document_type,
        response.registry.get("status", "UNKNOWN"),
    )

    # ── Populate Risk Session Store for Module 6 (M5 evidence) ────────────────────
    try:
        risk_session_store.update_module(
            payload.verification_id, "m5_registry",
            {
                "registry":      response.registry,
                "field_results": [
                    (
                        fr.model_dump() if hasattr(fr, "model_dump")
                        else fr.dict() if hasattr(fr, "dict")
                        else {
                            "field": getattr(fr, "field", None) or (fr.get("field") if isinstance(fr, dict) else None),
                            "document_value": getattr(fr, "document_value", None) or (fr.get("document_value") if isinstance(fr, dict) else None),
                            "registry_value": getattr(fr, "registry_value", None) or (fr.get("registry_value") if isinstance(fr, dict) else None),
                            "status": getattr(fr, "status", None) or (fr.get("status") if isinstance(fr, dict) else None),
                            "is_critical": getattr(fr, "is_critical", False) or (fr.get("is_critical", False) if isinstance(fr, dict) else False),
                        }
                    )
                    for fr in (response.field_results or [])
                ],
                "provider_metadata": response.provider_metadata or {},
            },
        )
    except Exception as _risk_exc:
        logger.warning("Failed to update risk session M5: %s", _risk_exc)

    return response


# ── Module 6: Risk Engine ────────────────────────────────────────────────────────

@router.post(
    "/risk",
    response_model=RiskAssessmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Compute deterministic risk score and officer decision support",
    description=(
        "Module 6: Risk Engine & Officer Decision Support.\n\n"
        "Aggregates normalized evidence from Modules 1–5 into a transparent, "
        "evidence-based risk assessment (0–100 score + officer review guidance).\n\n"
        "SECURITY: The client provides ONLY verification_id + document_type. "
        "All evidence is retrieved server-side. "
        "Client-submitted scores, levels, or reasons are IGNORED.\n\n"
        "IMPORTANT: The risk score is NOT a fraud probability. "
        "The officer_recommendation is ADVISORY ONLY. "
        "M6 NEVER makes admission, denial, arrest, or blacklist decisions. "
        "The final decision belongs to the authorized officer."
    ),
    responses={
        404: {"description": "Verification session not found or expired"},
        500: {"description": "Risk engine failure"},
    },
)
async def risk_assessment(
    payload: RiskVerifyRequest,
) -> RiskAssessmentResponse:
    """
    Module 6 endpoint: Risk Engine & Officer Decision Support.

    The engine reads accumulated M1–5 evidence from the risk session store
    (populated by each preceding endpoint) and produces a deterministic risk
    assessment. The result is explainable, auditable, and officer-facing.
    """
    profile = document_profile_registry.resolve_operational(payload.document_type)

    logger.info(
        "Risk assessment request received: id=%s doc_type=%s",
        payload.verification_id,
        profile.document_type,
    )

    try:
        result_dict = risk_engine.assess(
            verification_id=payload.verification_id,
            document_type=profile.document_type,
        )
    except Exception as exc:
        logger.error(
            "Risk engine failure for id=%s: %s",
            payload.verification_id, exc, exc_info=True
        )
        raise RiskEngineError() from exc

    logger.info(
        "Risk assessment complete: id=%s score=%d level=%s recommendation=%s",
        payload.verification_id,
        result_dict["risk_assessment"]["risk_score"],
        result_dict["risk_assessment"]["risk_level"],
        result_dict["risk_assessment"]["officer_recommendation"],
    )

    return RiskAssessmentResponse(**result_dict)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _populate_registry_session(
    verification_id: str,
    document_type: str,
    parsed,
    traveler: "TravelerFields",
    mrz: "MRZData",
) -> None:
    """
    Populate the RegistrySessionStore with normalized identity fields.

    Called at /ocr time so the /registry endpoint can retrieve data
    server-side without requiring the client to re-submit identity fields.

    Field provenance:
      - MRZ fields: more reliable (checksum-validated by Module 2)
      - VIZ fields: used as fallback where MRZ unavailable

    SECURITY: Only normalized field values are stored — no raw images,
    biometric data, or sensitive intermediate artifacts.
    """
    session_data = {
        "document_type": document_type,
    }

    # For passport: extract fields with provenance tracking
    if document_type == "passport" and parsed is not None:
        _set_field(session_data, "document_number", getattr(parsed.docNumber, "value", None), "mrz")
        _set_field(session_data, "document_number_source", "mrz")
        _set_field(session_data, "date_of_birth", getattr(parsed.dob, "value", None), "mrz")
        _set_field(session_data, "dob_source", "mrz")
        _set_field(session_data, "name", getattr(parsed.name, "value", None), "viz")
        _set_field(session_data, "name_source", "viz")
        _set_field(session_data, "nationality", getattr(parsed.nationality, "value", None), "mrz")
        _set_field(session_data, "nationality_source", "mrz")
        _set_field(session_data, "expiry_date", getattr(parsed.expiry, "value", None), "mrz")
        _set_field(session_data, "expiry_source", "mrz")
        _set_field(session_data, "issuing_authority", getattr(parsed.authority, "value", None), "viz")
        _set_field(session_data, "authority_source", "viz")
        _set_field(session_data, "gender", getattr(parsed.gender, "value", None), "mrz")
        if mrz:
            _set_field(session_data, "mrz_line1", mrz.line1)
            _set_field(session_data, "mrz_line2", mrz.line2)

    elif document_type == "visa" and parsed is not None:
        # Visa fields
        _set_field(session_data, "document_number", getattr(parsed.docNumber, "value", None), "viz")
        _set_field(session_data, "document_number_source", "viz")
        _set_field(session_data, "passport_number", getattr(parsed.passportNumber, "value", None), "viz")
        _set_field(session_data, "passport_number_source", "viz")
        _set_field(session_data, "name", getattr(parsed.name, "value", None), "viz")
        _set_field(session_data, "name_source", "viz")
        _set_field(session_data, "date_of_birth", getattr(parsed.dob, "value", None), "viz")
        _set_field(session_data, "dob_source", "viz")
        _set_field(session_data, "nationality", getattr(parsed.nationality, "value", None), "viz")
        _set_field(session_data, "nationality_source", "viz")
        _set_field(session_data, "visa_type", getattr(parsed.visaType, "value", None), "viz")
        _set_field(session_data, "issue_date", getattr(parsed.issuedDate, "value", None), "viz")
        _set_field(session_data, "expiry_date", getattr(parsed.expiry, "value", None), "viz")
        _set_field(session_data, "expiry_source", "viz")
        _set_field(session_data, "issuing_authority", getattr(parsed.authority, "value", None), "viz")
        _set_field(session_data, "authority_source", "viz")
        _set_field(session_data, "entries", getattr(parsed.entries, "value", None), "viz")
        _set_field(session_data, "duration_of_stay", getattr(parsed.durationOfStay, "value", None), "viz")
        if mrz:
            _set_field(session_data, "mrz_line1", mrz.line1)
            _set_field(session_data, "mrz_line2", mrz.line2)

    elif document_type == "driving_license" and parsed is not None:
        # Driving license fields
        _set_field(session_data, "document_number", getattr(parsed.license_number, "value", None), "viz")
        _set_field(session_data, "document_number_source", "viz")
        _set_field(session_data, "name", getattr(parsed.name, "value", None), "viz")
        _set_field(session_data, "name_source", "viz")
        _set_field(session_data, "date_of_birth", getattr(parsed.dob, "value", None), "viz")
        _set_field(session_data, "dob_source", "viz")
        _set_field(session_data, "expiry_date", getattr(parsed.expiry, "value", None), "viz")
        _set_field(session_data, "expiry_source", "viz")
        _set_field(session_data, "issuing_authority", getattr(parsed.issuing_authority, "value", None), "viz")
        _set_field(session_data, "authority_source", "viz")
        _set_field(session_data, "blood_group", getattr(parsed.blood_group, "value", None), "viz")
        _set_field(session_data, "vehicle_classes", getattr(parsed.vehicle_classes, "value", None), "viz")
        _set_field(session_data, "state", getattr(parsed.state, "value", None), "viz")
        _set_field(session_data, "valid_from", getattr(parsed.valid_from, "value", None), "viz")
        if mrz:
            _set_field(session_data, "mrz_line1", mrz.line1)
            _set_field(session_data, "mrz_line2", mrz.line2)

    elif document_type in ("national_id", "nationalid", "nid", "aadhaar") and parsed is not None:
        # National ID fields
        _set_field(session_data, "document_number", getattr(parsed.identity_number, "value", None), "viz")
        _set_field(session_data, "document_number_source", "viz")
        _set_field(session_data, "identity_number", getattr(parsed.identity_number, "value", None), "viz")
        _set_field(session_data, "identity_number_source", "viz")
        _set_field(session_data, "name", getattr(parsed.name, "value", None), "viz")
        _set_field(session_data, "name_source", "viz")
        _set_field(session_data, "date_of_birth", getattr(parsed.dob, "value", None) or getattr(parsed.year_of_birth, "value", None), "viz")
        _set_field(session_data, "dob_source", "viz")
        _set_field(session_data, "year_of_birth", getattr(parsed.year_of_birth, "value", None), "viz")
        _set_field(session_data, "gender", getattr(parsed.gender, "value", None), "viz")
        _set_field(session_data, "issuing_authority", getattr(parsed.issuing_authority, "value", None), "viz")
        _set_field(session_data, "authority_source", "viz")
        _set_field(session_data, "address", getattr(parsed.address, "value", None), "viz")

    elif document_type in ("border_permit", "borderpermit") and parsed is not None:
        # Border permit fields
        _set_field(session_data, "document_number", getattr(parsed.permit_number, "value", None), "viz")
        _set_field(session_data, "document_number_source", "viz")
        _set_field(session_data, "permit_number", getattr(parsed.permit_number, "value", None), "viz")
        _set_field(session_data, "name", getattr(parsed.name, "value", None), "viz")
        _set_field(session_data, "name_source", "viz")
        _set_field(session_data, "date_of_birth", getattr(parsed.dob, "value", None), "viz")
        _set_field(session_data, "dob_source", "viz")
        _set_field(session_data, "expiry_date", getattr(parsed.valid_to, "value", None), "viz")
        _set_field(session_data, "expiry_source", "viz")
        _set_field(session_data, "valid_from", getattr(parsed.valid_from, "value", None), "viz")
        _set_field(session_data, "valid_to", getattr(parsed.valid_to, "value", None), "viz")
        _set_field(session_data, "passport_number", getattr(parsed.passport_number, "value", None), "viz")
        _set_field(session_data, "passport_number_source", "viz")
        _set_field(session_data, "issuing_authority", getattr(parsed.issuing_authority, "value", None), "viz")
        _set_field(session_data, "authority_source", "viz")
        _set_field(session_data, "permit_type", getattr(parsed.permit_type, "value", None), "viz")
        _set_field(session_data, "border_zone", getattr(parsed.border_zone, "value", None), "viz")
        _set_field(session_data, "port_of_entry", getattr(parsed.port_of_entry, "value", None), "viz")

    elif traveler is not None:
        # Fallback: use traveler fields without specific provenance
        _set_field(session_data, "document_number", traveler.docNumber)
        _set_field(session_data, "date_of_birth", traveler.dob)
        _set_field(session_data, "name", traveler.name)
        _set_field(session_data, "nationality", traveler.nationality)
        _set_field(session_data, "expiry_date", traveler.expiry)
        _set_field(session_data, "issuing_authority", traveler.authority)
        if traveler.passportNumber:
            _set_field(session_data, "passport_number", traveler.passportNumber)

    registry_session_store.set(verification_id, session_data)
    logger.debug(
        "Registry session populated: id=%s fields=%s",
        verification_id,
        [k for k in session_data if not k.endswith("_source") and session_data[k]],
    )


def _set_field(session_data: dict, key: str, value=None, source: str = None) -> None:
    """Set a field in session_data only if value is non-null and non-empty."""
    if value is not None and str(value).strip():
        session_data[key] = str(value).strip()
    elif source is not None:
        # Always set source keys even if value is empty (for provenance tracking)
        session_data[key] = source


@router.post(
    "/orchestrate",
    status_code=status.HTTP_200_OK,
    summary="Run full end-to-end orchestrated verification on a document",
)
async def orchestrate_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    live_face: Optional[UploadFile] = File(None),
    case_id: Optional[str] = Form(None),
) -> Dict[str, Any]:
    from app.services.orchestrator.verification_orchestrator import verification_orchestrator

    file_bytes = await file.read()
    live_bytes = await live_face.read() if live_face else None
    vid = f"vid-{uuid.uuid4()}"
    doc_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"

    res = await verification_orchestrator.orchestrate_document(
        verification_id=vid,
        document_id=doc_id,
        document_type=document_type,
        file_bytes=file_bytes,
        filename=file.filename or "document.jpg",
        live_face_bytes=live_bytes,
        case_id=case_id,
    )
    return res.model_dump()

