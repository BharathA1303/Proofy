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

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import settings
from app.services.documents.classifier import classify_and_guard_document_type
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
from app.services.documents.aadhaar.aadhaar_parser import parse_aadhaar
from app.services.documents.aadhaar.aadhaar_validator import (
    validate_aadhaar_document,
)
from app.services.documents.voter_id.voter_id_parser import parse_voter_id
from app.services.documents.voter_id.voter_id_validator import (
    validate_voter_id_document,
)
from app.services.documents.pan_card.pan_card_parser import parse_pan_card
from app.services.documents.pan_card.pan_card_validator import (
    validate_pan_card_document,
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
from app.schemas.quality import DocumentQualityResponse, DocumentQualityMetrics
from app.services.quality.document_quality import evaluate_document_quality


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verification", tags=["Verification"])


@router.post(
    "/quality-check",
    response_model=DocumentQualityResponse,
    status_code=status.HTTP_200_OK,
    summary="Pre-flight document optical quality gate",
    description="Evaluates blur, glare, lighting, contrast, and resolution before OCR.",
)
async def check_quality(
    file: UploadFile = File(..., description="Document image to inspect"),
    document_type: str = Form("passport", description="Declared credential type"),
) -> DocumentQualityResponse:
    """
    Fast pre-flight optical quality gate endpoint (< 20ms).
    Returns granular metrics and actionable capture guidance before OCR.
    """
    raw_bytes = await file.read()
    ingested = await ingest_document(
        raw_bytes=raw_bytes,
        declared_mime=file.content_type or "",
        filename=file.filename or "upload",
    )
    res = evaluate_document_quality(ingested.image_np, document_type=document_type)
    return DocumentQualityResponse(
        status=res.status,
        is_acceptable=res.is_acceptable,
        overall_score=res.overall_score,
        metrics=DocumentQualityMetrics(
            resolution=res.resolution_score,
            sharpness=res.sharpness_score,
            brightness=res.brightness_score,
            contrast=res.contrast_score,
            glare=res.glare_score,
        ),
        width=res.width,
        height=res.height,
        reasons=res.reasons,
        guidance=res.guidance,
        error_code=res.error_code,
    )


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

    # ── Fast-path: Check Extraction Cache ─────────────────────────────────────
    from app.services.ocr.ocr_cache import get_cached_ocr, set_cached_ocr
    cached_entry = get_cached_ocr(ingested.raw_bytes, profile.document_type)
    if cached_entry is not None:
        cached_resp, cached_parsed = cached_entry
        fast_resp = cached_resp.model_copy(update={"verification_id": verification_id})
        try:
            risk_session_store.update_module(
                verification_id, "m1_ocr",
                {
                    "status": fast_resp.status,
                    "overall_confidence": fast_resp.ocr.overall_confidence if fast_resp.ocr else 0.95,
                    "region_count": fast_resp.ocr.region_count if fast_resp.ocr else 10,
                    "low_conf_count": 0,
                    "has_low_confidence_regions": False,
                    "mrz_detected": bool(fast_resp.mrz and (fast_resp.mrz.line1 or fast_resp.mrz.raw_line1)),
                    "mrz_applicable": profile.mrz_applicable,
                    "traveler_fields": fast_resp.traveler.model_dump() if fast_resp.traveler else {},
                },
            )
        except Exception as _r_exc:
            logger.debug("Fast risk session update: %s", _r_exc)

        _populate_registry_session(
            verification_id=verification_id,
            document_type=profile.document_type,
            parsed=cached_parsed,
            traveler=fast_resp.traveler,
            mrz=fast_resp.mrz,
        )
        logger.info("Deterministic OCR cache hit for id=%s (doc_type=%s, file=%s)", verification_id, profile.document_type, file.filename)
        return fast_resp

    # ── Step 1.5: Pre-OCR Document Quality Gate ──────────────────────────────
    quality_res = evaluate_document_quality(ingested.image_np, document_type=profile.document_type)
    if not quality_res.is_acceptable:
        logger.warning(
            "Document quality gate rejected image for id=%s (reasons=%s): %s",
            verification_id, quality_res.reasons, quality_res.guidance,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{quality_res.guidance} Please re-upload or recapture a clearer document image.",
        )

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

    # ── Step 3.5: Strict Document Type Isolation Guard ───────────────────
    type_guard = classify_and_guard_document_type(regions, profile.document_type)
    if type_guard.is_mismatch:
        logger.warning(
            "STRICT REJECTION - Document type mismatch for id=%s: declared=%s detected=%s",
            verification_id, profile.document_type, type_guard.detected_type,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=type_guard.error_message,
        )

    # ── Step 4: Document-specific parsing ────────────────────────────────────
    parsed_passport = None
    parsed_visa = None
    parsed_dl = None
    parsed_aadhaar = None
    parsed_voter = None
    parsed_pan = None
    parsed_nid = None
    parsed_bp = None
    mrz_combined: str | None = None

    if profile.document_type == "passport":
        parsed_passport = parse_passport(regions, image_height=image_height)
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

    elif profile.document_type in ("aadhaar", "aadhaarcard", "uid", "national_id", "nationalid", "nid"):
        parsed_aadhaar = parse_aadhaar(regions)
        parsed_nid = parsed_aadhaar
        mrz_combined = None
        traveler = TravelerFields(
            name=parsed_aadhaar.name.value,
            docNumber=parsed_aadhaar.identity_number.value,
            dob=parsed_aadhaar.dob.value,
            yearOfBirth=parsed_aadhaar.year_of_birth.value,
            gender=parsed_aadhaar.gender.value,
            authority=parsed_aadhaar.issuing_authority.value,
            address=parsed_aadhaar.address.value,
            identityNumber=parsed_aadhaar.identity_number.value,
            maskedIdentityNumber=parsed_aadhaar.masked_identity_number,
            qrPayload=parsed_aadhaar.qr_payload,
            qrDecoded=parsed_aadhaar.qr_decoded,
        )
        mrz_data = MRZData()

        primary_fields_found = sum(1 for v in [
            parsed_aadhaar.name.value,
            parsed_aadhaar.identity_number.value,
            parsed_aadhaar.dob.value or parsed_aadhaar.year_of_birth.value,
        ] if v)

        if primary_fields_found >= 3:
            ocr_status = "completed"
        elif primary_fields_found >= 1 or (parsed_aadhaar.identity_number.value and parsed_aadhaar.name.value):
            ocr_status = "partial"
        else:
            ocr_status = "partial"

    elif profile.document_type in ("voter_id", "voterid", "voterId", "voterID", "epic", "voter"):
        parsed_voter = parse_voter_id(regions)
        mrz_combined = None
        traveler = TravelerFields(
            name=parsed_voter.name.value,
            docNumber=parsed_voter.epic_number.value,
            epicNumber=parsed_voter.epic_number.value,
            fatherName=parsed_voter.father_name.value,
            dob=parsed_voter.dob.value,
            age=parsed_voter.age.value,
            gender=parsed_voter.gender.value,
            constituency=parsed_voter.constituency.value,
            authority=parsed_voter.issuing_authority.value,
            issuingState=parsed_voter.issuing_state.value,
            state=parsed_voter.issuing_state.value,
        )
        mrz_data = MRZData()

        primary_fields_found = sum(1 for v in [
            parsed_voter.name.value,
            parsed_voter.epic_number.value,
        ] if v)

        if primary_fields_found >= 2:
            ocr_status = "completed"
        elif primary_fields_found >= 1:
            ocr_status = "partial"
        else:
            ocr_status = "partial"

    elif profile.document_type in ("pan_card", "pancard", "panCard", "pan"):
        parsed_pan = parse_pan_card(regions)
        mrz_combined = None
        traveler = TravelerFields(
            name=parsed_pan.name.value,
            docNumber=parsed_pan.pan_number.value,
            panNumber=parsed_pan.pan_number.value,
            fatherName=parsed_pan.father_name.value,
            dob=parsed_pan.dob.value,
            taxpayerCategory=parsed_pan.taxpayer_category,
            authority=parsed_pan.issuing_authority.value,
        )
        mrz_data = MRZData()

        primary_fields_found = sum(1 for v in [
            parsed_pan.name.value,
            parsed_pan.pan_number.value,
        ] if v)

        if primary_fields_found >= 2:
            ocr_status = "completed"
        elif primary_fields_found >= 1:
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
        skew_angle=round(preprocessed.skew_angle, 2) if abs(preprocessed.skew_angle) > 0.0 else None,
    )

    quality_report = DocumentQualityResponse(
        status=quality_res.status,
        is_acceptable=quality_res.is_acceptable,
        overall_score=quality_res.overall_score,
        metrics=DocumentQualityMetrics(
            resolution=quality_res.resolution_score,
            sharpness=quality_res.sharpness_score,
            brightness=quality_res.brightness_score,
            contrast=quality_res.contrast_score,
            glare=quality_res.glare_score,
        ),
        width=quality_res.width,
        height=quality_res.height,
        reasons=quality_res.reasons,
        guidance=quality_res.guidance,
        error_code=quality_res.error_code,
    )

    # ── Pre-extract & cache Document Face for instant Stage 3 biometrics ─────
    doc_face_b64: Optional[str] = None
    try:
        from app.services.face.face_detector import face_detector
        from app.services.face.face_enhancer import DocumentFaceEnhancer
        from app.services.face.face_verification_service import _crop_to_b64, face_verification_service
        from app.services.face.face_aligner import FaceAligner

        doc_detect = face_detector.detect_faces(ingested.image_np, is_document=True)
        if doc_detect.face_count == 1:
            d_box = doc_detect.faces[0]
            d_crop_raw = face_detector.crop_portrait(ingested.image_np, d_box)
            d_crop = DocumentFaceEnhancer.enhance_portrait_crop(d_crop_raw)
            if d_crop is not None:
                doc_face_b64 = _crop_to_b64(d_crop)
                aligner = FaceAligner()
                if d_box.landmarks and len(d_box.landmarks) == 5:
                    d_aligned = aligner.align_face_5point(ingested.image_np, d_box.landmarks, (112, 112))
                else:
                    d_aligned = aligner.align_bbox_fallback(ingested.image_np, d_box.bbox, target_size=(112, 112))
                d_aligned_enh = aligner.enhance_document_face(d_aligned)
                arc_model = face_verification_service.embedding_model
                d_emb = arc_model.get_embedding(d_aligned_enh) if arc_model.is_available() else None
                session_document_store.set_face_cache(
                    verification_id=verification_id,
                    doc_box=d_box,
                    doc_crop=d_crop,
                    doc_aligned=d_aligned,
                    doc_embedding=d_emb,
                    detector_used=doc_detect.detector_used,
                )
                logger.info("Pre-warmed document face & ArcFace embedding cache for id=%s", verification_id)
    except Exception as _face_exc:
        logger.debug("Face pre-extraction in OCR skipped: %s", _face_exc)

    response = PassportOCRResponse(
        verification_id=verification_id,
        document_type=profile.document_type,
        status=ocr_status,
        traveler=traveler,
        mrz=mrz_data,
        ocr=ocr_meta,
        quality=quality_report,
        document_face_image=doc_face_b64,
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
    active_parsed = parsed_passport or parsed_visa or parsed_dl or parsed_aadhaar or parsed_voter or parsed_pan or parsed_nid or parsed_bp
    _populate_registry_session(
        verification_id=verification_id,
        document_type=profile.document_type,
        parsed=active_parsed,
        traveler=response.traveler,
        mrz=response.mrz,
    )

    set_cached_ocr(
        ingested.raw_bytes,
        profile.document_type,
        (response, active_parsed),
    )

    return response


@router.get(
    "/sample/passport",
    summary="Serve synthetic passport sample by variant (official, blacklist, defective)",
    response_class=FileResponse,
    tags=["Verification"],
)
async def get_sample_passport(variant: str = "official") -> FileResponse:
    """Serve synthetic test passport image (official, blacklist, or defective)."""
    assets_dir = Path(__file__).parent.parent.parent.parent / "tests" / "assets"
    var = variant.lower().strip() if variant else "official"
    variant_map = {
        "official": ("passport_official.jpg", "Passport_Aarav_Sharma_Official.jpg"),
        "genuine": ("passport_official.jpg", "Passport_Aarav_Sharma_Official.jpg"),
        "blacklist": ("passport_blacklist.jpg", "Passport_Vikram_Malhotra_Blacklisted.jpg"),
        "blacklisted": ("passport_blacklist.jpg", "Passport_Vikram_Malhotra_Blacklisted.jpg"),
        "defective": ("passport_defective.jpg", "Passport_Rohit_Verma_Defective.jpg"),
        "fake": ("passport_defective.jpg", "Passport_Rohit_Verma_Defective.jpg"),
    }
    asset_file, out_file = variant_map.get(var, ("passport_official.jpg", "Passport_Official.jpg"))
    target = assets_dir / asset_file
    if not target.exists():
        target = assets_dir / "sample_passport.jpg"
    if not target.exists():
        return JSONResponse(status_code=404, content={"detail": f"Passport sample '{variant}' not found."})

    return FileResponse(path=str(target), media_type="image/jpeg", filename=out_file, headers={"Cache-Control": "no-cache"})


@router.get(
    "/sample/visa",
    summary="Serve synthetic visa sample by variant (official, blacklist, defective)",
    response_class=FileResponse,
    tags=["Verification"],
)
async def get_sample_visa(variant: str = "official") -> FileResponse:
    """Serve synthetic test visa image (official, blacklist, or defective)."""
    assets_dir = Path(__file__).parent.parent.parent.parent / "tests" / "assets"
    var = variant.lower().strip() if variant else "official"
    variant_map = {
        "official": ("visa_official.jpg", "Visa_Aarav_Sharma_Official.jpg"),
        "genuine": ("visa_official.jpg", "Visa_Aarav_Sharma_Official.jpg"),
        "blacklist": ("visa_blacklist.jpg", "Visa_Vikram_Malhotra_Blacklisted.jpg"),
        "blacklisted": ("visa_blacklist.jpg", "Visa_Vikram_Malhotra_Blacklisted.jpg"),
        "defective": ("visa_defective.jpg", "Visa_Rohit_Verma_Defective.jpg"),
        "fake": ("visa_defective.jpg", "Visa_Rohit_Verma_Defective.jpg"),
    }
    asset_file, out_file = variant_map.get(var, ("visa_official.jpg", "Visa_Official.jpg"))
    target = assets_dir / asset_file
    if not target.exists():
        target = assets_dir / "sample_visa.jpg"
    if not target.exists():
        return JSONResponse(status_code=404, content={"detail": f"Visa sample '{variant}' not found."})

    return FileResponse(path=str(target), media_type="image/jpeg", filename=out_file, headers={"Cache-Control": "no-cache"})


@router.get(
    "/sample/driving_license",
    summary="Serve synthetic driving license sample by variant",
    tags=["Verification"],
)
@router.get(
    "/sample/drivingLicense",
    summary="Serve synthetic driving license sample (camelCase alias)",
    tags=["Verification"],
)
async def get_sample_driving_license(variant: str = "official") -> FileResponse:
    """Serve synthetic test driving license image (official, blacklist, or defective)."""
    assets_dir = Path(__file__).parent.parent.parent.parent / "tests" / "assets"
    var = variant.lower().strip() if variant else "official"
    variant_map = {
        "official": ("dl_official.jpg", "DL_Priya_Sundar_Official.jpg"),
        "genuine": ("dl_official.jpg", "DL_Priya_Sundar_Official.jpg"),
        "bharath": ("dl_bharath_a_genuine.jpg", "DL_Bharath_A_TamilNadu_Genuine.jpg"),
        "blacklist": ("dl_blacklist.jpg", "DL_Kabir_Mehta_Blacklisted.jpg"),
        "blacklisted": ("dl_blacklist.jpg", "DL_Kabir_Mehta_Blacklisted.jpg"),
        "defective": ("dl_defective.jpg", "DL_Anil_Kumar_Defective.jpg"),
        "fake": ("dl_defective.jpg", "DL_Anil_Kumar_Defective.jpg"),
    }
    asset_file, out_file = variant_map.get(var, ("dl_official.jpg", "DL_Official.jpg"))
    target = assets_dir / asset_file
    if not target.exists():
        target = assets_dir / "sample_driving_license.jpg"
    if not target.exists():
        return JSONResponse(status_code=404, content={"detail": f"Driving license sample '{variant}' not found."})

    return FileResponse(path=str(target), media_type="image/jpeg", filename=out_file, headers={"Cache-Control": "no-cache"})


@router.get(
    "/sample/aadhaar",
    summary="Serve synthetic Aadhaar card sample by variant",
    tags=["Verification"],
)
@router.get(
    "/sample/aadhaarCard",
    summary="Serve synthetic Aadhaar sample (camelCase alias)",
    tags=["Verification"],
)
@router.get(
    "/sample/national_id",
    summary="Serve synthetic national id sample (legacy alias)",
    tags=["Verification"],
)
@router.get(
    "/sample/nationalId",
    summary="Serve synthetic national id sample (legacy camelCase alias)",
    tags=["Verification"],
)
async def get_sample_aadhaar(variant: str = "official") -> FileResponse:
    """Serve synthetic test Aadhaar image (official, blacklist, or defective)."""
    assets_dir = Path(__file__).parent.parent.parent.parent / "tests" / "assets"
    var = variant.lower().strip() if variant else "official"
    variant_map = {
        "official": ("aadhaar_official.jpg", "Aadhaar_Sneha_Patel_Official.jpg"),
        "genuine": ("aadhaar_official.jpg", "Aadhaar_Sneha_Patel_Official.jpg"),
        "blacklist": ("aadhaar_blacklist.jpg", "Aadhaar_Tariq_Ahmed_Blacklisted.jpg"),
        "blacklisted": ("aadhaar_blacklist.jpg", "Aadhaar_Tariq_Ahmed_Blacklisted.jpg"),
        "defective": ("aadhaar_defective.jpg", "Aadhaar_Devraj_Singh_Defective.jpg"),
        "fake": ("aadhaar_defective.jpg", "Aadhaar_Devraj_Singh_Defective.jpg"),
    }
    asset_file, out_file = variant_map.get(var, ("aadhaar_official.jpg", "Aadhaar_Official.jpg"))
    target = assets_dir / asset_file
    if not target.exists():
        fallback_file = asset_file.replace("aadhaar_", "national_id_")
        target = assets_dir / fallback_file
    if not target.exists():
        target = assets_dir / "sample_national_id.jpg"
    if not target.exists():
        return JSONResponse(status_code=404, content={"detail": f"Aadhaar sample '{variant}' not found."})

    return FileResponse(path=str(target), media_type="image/jpeg", filename=out_file, headers={"Cache-Control": "no-cache"})


@router.get(
    "/sample/voter_id",
    summary="Serve synthetic Voter ID / EPIC sample by variant",
    tags=["Verification"],
)
@router.get(
    "/sample/voterId",
    summary="Serve synthetic Voter ID sample (camelCase alias)",
    tags=["Verification"],
)
@router.get(
    "/sample/epic",
    summary="Serve synthetic EPIC card sample",
    tags=["Verification"],
)
async def get_sample_voter_id(variant: str = "official") -> FileResponse:
    """Serve synthetic test Voter ID image (official, blacklist, or defective)."""
    assets_dir = Path(__file__).parent.parent.parent.parent / "tests" / "assets"
    var = variant.lower().strip() if variant else "official"
    variant_map = {
        "official": ("voter_id_official.jpg", "VoterID_Priya_Krishnamurthy_Official.jpg"),
        "genuine": ("voter_id_official.jpg", "VoterID_Priya_Krishnamurthy_Official.jpg"),
        "blacklist": ("voter_id_blacklist.jpg", "VoterID_Rahul_Devanand_Blacklisted.jpg"),
        "blacklisted": ("voter_id_blacklist.jpg", "VoterID_Rahul_Devanand_Blacklisted.jpg"),
        "defective": ("voter_id_defective.jpg", "VoterID_Invalid_Defective.jpg"),
        "fake": ("voter_id_defective.jpg", "VoterID_Invalid_Defective.jpg"),
    }
    asset_file, out_file = variant_map.get(var, ("voter_id_official.jpg", "VoterID_Official.jpg"))
    target = assets_dir / asset_file
    if not target.exists():
        target = assets_dir / "sample_voter_id.jpg"
    if not target.exists():
        target = assets_dir / "national_id_official.jpg"
    if not target.exists():
        return JSONResponse(status_code=404, content={"detail": f"Voter ID sample '{variant}' not found."})

    return FileResponse(path=str(target), media_type="image/jpeg", filename=out_file, headers={"Cache-Control": "no-cache"})


@router.get(
    "/sample/pan_card",
    summary="Serve synthetic PAN Card sample by variant",
    tags=["Verification"],
)
@router.get(
    "/sample/panCard",
    summary="Serve synthetic PAN Card sample (camelCase alias)",
    tags=["Verification"],
)
@router.get(
    "/sample/pan",
    summary="Serve synthetic PAN Card sample (short alias)",
    tags=["Verification"],
)
async def get_sample_pan_card(variant: str = "official") -> FileResponse:
    """Serve synthetic test PAN Card image (official, blacklist, or defective)."""
    assets_dir = Path(__file__).parent.parent.parent.parent / "tests" / "assets"
    var = variant.lower().strip() if variant else "official"
    variant_map = {
        "official": ("pan_card_official.jpg", "PAN_Kavitha_Prabhakar_Official.jpg"),
        "genuine": ("pan_card_official.jpg", "PAN_Kavitha_Prabhakar_Official.jpg"),
        "blacklist": ("pan_card_blacklist.jpg", "PAN_Suresh_Fraudwala_Blacklisted.jpg"),
        "blacklisted": ("pan_card_blacklist.jpg", "PAN_Suresh_Fraudwala_Blacklisted.jpg"),
        "defective": ("pan_card_defective.jpg", "PAN_Invalid_Defective.jpg"),
        "fake": ("pan_card_defective.jpg", "PAN_Invalid_Defective.jpg"),
    }
    asset_file, out_file = variant_map.get(var, ("pan_card_official.jpg", "PAN_Official.jpg"))
    target = assets_dir / asset_file
    if not target.exists():
        target = assets_dir / "sample_pan_card.jpg"
    if not target.exists():
        target = assets_dir / "national_id_official.jpg"
    if not target.exists():
        return JSONResponse(status_code=404, content={"detail": f"PAN Card sample '{variant}' not found."})

    return FileResponse(path=str(target), media_type="image/jpeg", filename=out_file, headers={"Cache-Control": "no-cache"})


@router.get(
    "/sample/border_permit",
    summary="Serve synthetic border / work permit sample by variant",
    tags=["Verification"],
)
@router.get(
    "/sample/borderPermit",
    summary="Serve synthetic border permit sample (camelCase alias)",
    tags=["Verification"],
)
async def get_sample_border_permit(variant: str = "official") -> FileResponse:
    """Serve synthetic test border permit image (official, blacklist, or defective)."""
    assets_dir = Path(__file__).parent.parent.parent.parent / "tests" / "assets"
    var = variant.lower().strip() if variant else "official"
    variant_map = {
        "official": ("border_permit_official.jpg", "Permit_Elena_Rostova_Official.jpg"),
        "genuine": ("border_permit_official.jpg", "Permit_Elena_Rostova_Official.jpg"),
        "blacklist": ("border_permit_blacklist.jpg", "Permit_Marcus_Vance_Blacklisted.jpg"),
        "blacklisted": ("border_permit_blacklist.jpg", "Permit_Marcus_Vance_Blacklisted.jpg"),
        "defective": ("border_permit_defective.jpg", "Permit_John_Doe_Defective.jpg"),
        "fake": ("border_permit_defective.jpg", "Permit_John_Doe_Defective.jpg"),
    }
    asset_file, out_file = variant_map.get(var, ("border_permit_official.jpg", "Permit_Official.jpg"))
    target = assets_dir / asset_file
    if not target.exists():
        target = assets_dir / "sample_border_permit.jpg"
    if not target.exists():
        return JSONResponse(status_code=404, content={"detail": f"Border permit sample '{variant}' not found."})

    return FileResponse(path=str(target), media_type="image/jpeg", filename=out_file, headers={"Cache-Control": "no-cache"})


@router.get(
    "/sample/options",
    summary="List available sample documents from the backend",
    tags=["Verification"],
)
async def get_sample_options() -> JSONResponse:
    """Returns 3 pre-populated test vectors (Official, Blacklist, Defective) for all 5 document categories."""
    passport_samples = [
        {
            "id": "passport_official",
            "label": "Official Passport (Genuine)",
            "badge": "OFFICIAL / ACTIVE",
            "variant": "official",
            "filename": "Passport_Aarav_Sharma_Official.jpg",
            "url": "/api/v1/verification/sample/passport?variant=official",
            "description": "Authentic passport: Aarav Sharma (Z1234567). Status: ACTIVE in official registry with valid ICAO TD3 MRZ.",
        },
        {
            "id": "passport_blacklist",
            "label": "Blacklisted Passport (Watchlist)",
            "badge": "BLACKLISTED",
            "variant": "blacklist",
            "filename": "Passport_Vikram_Malhotra_Blacklisted.jpg",
            "url": "/api/v1/verification/sample/passport?variant=blacklist",
            "description": "Passport for Vikram Malhotra (Z7654321). Status: REVOKED on national fraud & border watchlist.",
        },
        {
            "id": "passport_defective",
            "label": "Defective / Fake Passport",
            "badge": "DEFECT / FAKE",
            "variant": "defective",
            "filename": "Passport_Rohit_Verma_Defective.jpg",
            "url": "/api/v1/verification/sample/passport?variant=defective",
            "description": "Tampered passport for Rohit Verma (Z9999999). Failed check digits & expiry precedes issue date.",
        },
    ]

    visa_samples = [
        {
            "id": "visa_official",
            "label": "Official Entry Visa (Genuine)",
            "badge": "OFFICIAL / ACTIVE",
            "variant": "official",
            "filename": "Visa_Aarav_Sharma_Official.jpg",
            "url": "/api/v1/verification/sample/visa?variant=official",
            "description": "Consular entry visa for Aarav Sharma (V1002003). Valid multi-entry bound to passport Z1234567.",
        },
        {
            "id": "visa_blacklist",
            "label": "Blacklisted Visa (Revoked)",
            "badge": "BLACKLISTED",
            "variant": "blacklist",
            "filename": "Visa_Vikram_Malhotra_Blacklisted.jpg",
            "url": "/api/v1/verification/sample/visa?variant=blacklist",
            "description": "Consular visa for Vikram Malhotra (V7008009). Status: REVOKED in immigration registry.",
        },
        {
            "id": "visa_defective",
            "label": "Defective / Fake Visa",
            "badge": "DEFECT / FAKE",
            "variant": "defective",
            "filename": "Visa_Rohit_Verma_Defective.jpg",
            "url": "/api/v1/verification/sample/visa?variant=defective",
            "description": "Defective visa (V999) with missed details (passport reference missing, issue date missing).",
        },
    ]

    dl_samples = [
        {
            "id": "dl_bharath",
            "label": "Bharath A - Tamil Nadu DL (Genuine Original)",
            "badge": "OFFICIAL / ACTIVE",
            "variant": "bharath",
            "filename": "DL_Bharath_A_TamilNadu_Genuine.jpg",
            "url": "/api/v1/verification/sample/driving_license?variant=bharath",
            "description": "Original Indian Driving Licence: BHARATH A (TN05 20250014128). Issued by Govt of Tamil Nadu. Status: ACTIVE in transport registry.",
        },
        {
            "id": "dl_official",
            "label": "Official Driving License (Priya Sundar)",
            "badge": "OFFICIAL / ACTIVE",
            "variant": "official",
            "filename": "DL_Priya_Sundar_Official.jpg",
            "url": "/api/v1/verification/sample/driving_license?variant=official",
            "description": "Original driving license: Priya Sundar (DL-0420230012345). Active and verified in official government registry.",
        },
        {
            "id": "dl_blacklist",
            "label": "Blacklisted DL (Revoked)",
            "badge": "BLACKLISTED",
            "variant": "blacklist",
            "filename": "DL_Kabir_Mehta_Blacklisted.jpg",
            "url": "/api/v1/verification/sample/driving_license?variant=blacklist",
            "description": "Driving license for Kabir Mehta (DL-0120180099887). Status: REVOKED for fraudulent documentation.",
        },
        {
            "id": "dl_defective",
            "label": "Defective / Fake DL",
            "badge": "DEFECT / FAKE",
            "variant": "defective",
            "filename": "DL_Anil_Kumar_Defective.jpg",
            "url": "/api/v1/verification/sample/driving_license?variant=defective",
            "description": "Tampered DL (INVALID-DL-12): Issue date 2005 precedes DOB 2012; missing vehicle classes & authority.",
        },
    ]

    aadhaar_samples = [
        {
            "id": "aadhaar_official",
            "label": "Official Aadhaar Card (Genuine)",
            "badge": "OFFICIAL / ACTIVE",
            "variant": "official",
            "filename": "Aadhaar_Sneha_Patel_Official.jpg",
            "url": "/api/v1/verification/sample/aadhaar?variant=official",
            "description": "Official 12-digit UIDAI Aadhaar Card for Sneha Patel (8472 9103 8473). Valid Verhoeff check digit & registered.",
        },
        {
            "id": "aadhaar_blacklist",
            "label": "Blacklisted Aadhaar (Suspended)",
            "badge": "BLACKLISTED",
            "variant": "blacklist",
            "filename": "Aadhaar_Tariq_Ahmed_Blacklisted.jpg",
            "url": "/api/v1/verification/sample/aadhaar?variant=blacklist",
            "description": "Aadhaar Card for Tariq Ahmed (6541 2398 7101). Status: SUSPENDED / REVOKED on duplicate watchlist.",
        },
        {
            "id": "aadhaar_defective",
            "label": "Defective / Fake Aadhaar",
            "badge": "DEFECT / FAKE",
            "variant": "defective",
            "filename": "Aadhaar_Devraj_Singh_Defective.jpg",
            "url": "/api/v1/verification/sample/aadhaar?variant=defective",
            "description": "Defective Aadhaar (1234 5678 9999): Fails Verhoeff checksum algorithm with missing demographic fields.",
        },
    ]

    voter_id_samples = [
        {
            "id": "voter_id_official",
            "label": "Official Voter ID / EPIC (Genuine)",
            "badge": "OFFICIAL / ACTIVE",
            "variant": "official",
            "filename": "VoterID_Priya_Krishnamurthy_Official.jpg",
            "url": "/api/v1/verification/sample/voter_id?variant=official",
            "description": "Official Electors Photo Identity Card: Priya Krishnamurthy (ABC1234567). Active in ECI electoral roll.",
        },
        {
            "id": "voter_id_blacklist",
            "label": "Blacklisted Voter ID (Revoked)",
            "badge": "BLACKLISTED",
            "variant": "blacklist",
            "filename": "VoterID_Rahul_Devanand_Blacklisted.jpg",
            "url": "/api/v1/verification/sample/voter_id?variant=blacklist",
            "description": "Voter ID for Rahul Devanand (XYZ7654321). Status: REVOKED for electoral roll duplicate registration.",
        },
        {
            "id": "voter_id_defective",
            "label": "Defective / Fake Voter ID",
            "badge": "DEFECT / FAKE",
            "variant": "defective",
            "filename": "VoterID_Invalid_Defective.jpg",
            "url": "/api/v1/verification/sample/voter_id?variant=defective",
            "description": "Defective Voter ID (INVALID-EPIC-99): Malformed EPIC format and missing constituency metadata.",
        },
    ]

    pan_card_samples = [
        {
            "id": "pan_card_official",
            "label": "Official PAN Card (Genuine)",
            "badge": "OFFICIAL / ACTIVE",
            "variant": "official",
            "filename": "PAN_Kavitha_Prabhakar_Official.jpg",
            "url": "/api/v1/verification/sample/pan_card?variant=official",
            "description": "Official Income Tax Dept PAN Card: Kavitha Prabhakar (AABCP1234C). Active taxpayer credential.",
        },
        {
            "id": "pan_card_blacklist",
            "label": "Blacklisted PAN Card (Revoked)",
            "badge": "BLACKLISTED",
            "variant": "blacklist",
            "filename": "PAN_Suresh_Fraudwala_Blacklisted.jpg",
            "url": "/api/v1/verification/sample/pan_card?variant=blacklist",
            "description": "PAN Card for Suresh Fraudwala (AAAFT9999Z). Status: REVOKED for tax evasion fraud and impersonation.",
        },
        {
            "id": "pan_card_defective",
            "label": "Defective / Fake PAN Card",
            "badge": "DEFECT / FAKE",
            "variant": "defective",
            "filename": "PAN_Invalid_Defective.jpg",
            "url": "/api/v1/verification/sample/pan_card?variant=defective",
            "description": "Defective PAN Card (PAN-123-INVALID): Non-standard alphanumeric structure and missing taxpayer category.",
        },
    ]

    bp_samples = [
        {
            "id": "border_permit_official",
            "label": "Official Work/Border Permit (Genuine)",
            "badge": "OFFICIAL / ACTIVE",
            "variant": "official",
            "filename": "Permit_Elena_Rostova_Official.jpg",
            "url": "/api/v1/verification/sample/border_permit?variant=official",
            "description": "Official cross-border entry & work permit: Elena Rostova (BP-2026-880011) bound to passport Z1234567.",
        },
        {
            "id": "border_permit_blacklist",
            "label": "Blacklisted Permit (Revoked)",
            "badge": "BLACKLISTED",
            "variant": "blacklist",
            "filename": "Permit_Marcus_Vance_Blacklisted.jpg",
            "url": "/api/v1/verification/sample/border_permit?variant=blacklist",
            "description": "Border permit for Marcus Vance (BP-2025-443322). Status: REVOKED in border management registry.",
        },
        {
            "id": "border_permit_defective",
            "label": "Defective / Fake Work Permit",
            "badge": "DEFECT / FAKE",
            "variant": "defective",
            "filename": "Permit_John_Doe_Defective.jpg",
            "url": "/api/v1/verification/sample/border_permit?variant=defective",
            "description": "Tampered permit (PERMIT-XYZ): Valid To date precedes Valid From date; unbound passport field.",
        },
    ]

    return JSONResponse(
        content={
            "driving_license": dl_samples,
            "drivingLicense": dl_samples,
            "passport": passport_samples,
            "visa": visa_samples,
            "aadhaar": aadhaar_samples,
            "aadhaarCard": aadhaar_samples,
            "voter_id": voter_id_samples,
            "voterId": voter_id_samples,
            "pan_card": pan_card_samples,
            "panCard": pan_card_samples,
            "national_id": aadhaar_samples,
            "nationalId": aadhaar_samples,
            "border_permit": bp_samples,
            "borderPermit": bp_samples,
            "work_permit": bp_samples,
            "workpermit": bp_samples,
        }
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
    elif profile.document_type in ("aadhaar", "aadhaarcard", "uid", "national_id", "nationalid", "nid"):
        summary_dict = validate_aadhaar_document(
            traveler=payload.traveler,
        )
        validation_summary = DocumentValidationSummary(**summary_dict)
    elif profile.document_type in ("voter_id", "voterid", "voterId", "voterID", "epic", "voter"):
        summary_dict = validate_voter_id_document(
            traveler=payload.traveler,
        )
        validation_summary = DocumentValidationSummary(**summary_dict)
    elif profile.document_type in ("pan_card", "pancard", "panCard", "pan"):
        summary_dict = validate_pan_card_document(
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
        if hasattr(validation_summary.checks, "model_dump"):
            checks_dict = validation_summary.checks.model_dump()
        elif hasattr(validation_summary.checks, "__dict__"):
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
        forensic_summary = await asyncio.to_thread(
            run_forensic_analysis,
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
                "registry": (
                    response.registry.model_dump() if hasattr(response.registry, "model_dump")
                    else response.registry.dict() if hasattr(response.registry, "dict")
                    else (response.registry if isinstance(response.registry, dict) else {})
                ) if response.registry else {},
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
                "provider_metadata": (
                    response.provider_metadata.model_dump() if hasattr(response.provider_metadata, "model_dump")
                    else response.provider_metadata.dict() if hasattr(response.provider_metadata, "dict")
                    else (response.provider_metadata if isinstance(response.provider_metadata, dict) else {})
                ) if response.provider_metadata else {},
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

    elif document_type in ("aadhaar", "aadhaarcard", "uid", "national_id", "nationalid", "nid") and parsed is not None:
        # Aadhaar fields
        doc_num = getattr(getattr(parsed, "identity_number", None), "value", None) or getattr(getattr(parsed, "docNumber", None), "value", None)
        _set_field(session_data, "document_number", doc_num, "viz")
        _set_field(session_data, "document_number_source", "viz")
        _set_field(session_data, "identity_number", doc_num, "viz")
        _set_field(session_data, "identity_number_source", "viz")
        _set_field(session_data, "name", getattr(getattr(parsed, "name", None), "value", None), "viz")
        _set_field(session_data, "name_source", "viz")
        _set_field(session_data, "date_of_birth", getattr(getattr(parsed, "dob", None), "value", None) or getattr(getattr(parsed, "year_of_birth", None), "value", None), "viz")
        _set_field(session_data, "dob_source", "viz")
        _set_field(session_data, "year_of_birth", getattr(getattr(parsed, "year_of_birth", None), "value", None), "viz")
        _set_field(session_data, "gender", getattr(getattr(parsed, "gender", None), "value", None), "viz")
        _set_field(session_data, "issuing_authority", getattr(getattr(parsed, "issuing_authority", None), "value", None), "viz")
        _set_field(session_data, "authority_source", "viz")
        _set_field(session_data, "address", getattr(getattr(parsed, "address", None), "value", None), "viz")

    elif document_type in ("voter_id", "voterid", "voterId", "voterID", "epic", "voter") and parsed is not None:
        # Voter ID / EPIC fields
        epic_num = getattr(getattr(parsed, "epic_number", None), "value", None) or getattr(getattr(parsed, "docNumber", None), "value", None)
        _set_field(session_data, "document_number", epic_num, "viz")
        _set_field(session_data, "document_number_source", "viz")
        _set_field(session_data, "epic_number", epic_num, "viz")
        _set_field(session_data, "epic_number_source", "viz")
        _set_field(session_data, "name", getattr(getattr(parsed, "name", None), "value", None), "viz")
        _set_field(session_data, "name_source", "viz")
        _set_field(session_data, "father_name", getattr(getattr(parsed, "father_name", None), "value", None), "viz")
        _set_field(session_data, "date_of_birth", getattr(getattr(parsed, "dob", None), "value", None), "viz")
        _set_field(session_data, "dob_source", "viz")
        _set_field(session_data, "age", getattr(getattr(parsed, "age", None), "value", None), "viz")
        _set_field(session_data, "gender", getattr(getattr(parsed, "gender", None), "value", None), "viz")
        _set_field(session_data, "constituency", getattr(getattr(parsed, "constituency", None), "value", None), "viz")
        _set_field(session_data, "issuing_authority", getattr(getattr(parsed, "issuing_authority", None), "value", None), "viz")
        _set_field(session_data, "authority_source", "viz")
        _set_field(session_data, "state", getattr(getattr(parsed, "issuing_state", None), "value", None), "viz")

    elif document_type in ("pan_card", "pancard", "panCard", "pan") and parsed is not None:
        # PAN Card fields
        pan_num = getattr(getattr(parsed, "pan_number", None), "value", None) or getattr(getattr(parsed, "docNumber", None), "value", None)
        _set_field(session_data, "document_number", pan_num, "viz")
        _set_field(session_data, "document_number_source", "viz")
        _set_field(session_data, "pan_number", pan_num, "viz")
        _set_field(session_data, "pan_number_source", "viz")
        _set_field(session_data, "name", getattr(getattr(parsed, "name", None), "value", None), "viz")
        _set_field(session_data, "name_source", "viz")
        _set_field(session_data, "father_name", getattr(getattr(parsed, "father_name", None), "value", None), "viz")
        _set_field(session_data, "date_of_birth", getattr(getattr(parsed, "dob", None), "value", None), "viz")
        _set_field(session_data, "dob_source", "viz")
        _set_field(session_data, "taxpayer_category", getattr(parsed, "taxpayer_category", None), "viz")
        _set_field(session_data, "issuing_authority", getattr(getattr(parsed, "issuing_authority", None), "value", None), "viz")
        _set_field(session_data, "authority_source", "viz")

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
    """
    Set a field in session_data only if value is non-null and non-empty.

    `source` is provenance metadata (e.g. "mrz"/"viz") for *_source keys —
    it must never be written into a data field's value when the extracted
    value is missing, or a literal "viz"/"mrz" string leaks through as the
    document's name/DOB/etc. and corrupts the registry field comparison.
    """
    is_source_key = key.endswith("_source")
    if value is not None and str(value).strip():
        session_data[key] = str(value).strip()
    elif is_source_key and source is not None:
        # *_source keys track provenance and may be set even when the
        # corresponding data field extraction failed.
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

