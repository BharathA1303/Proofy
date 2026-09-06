"""
backend/app/services/case/case_manager.py

Orchestrates multi-document verification cases, managing document intake,
independent pipeline execution, relationship evaluation, and case-level risk.
"""
from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings
from app.core.exceptions import (
    CaseNotFoundError,
    DocumentNotFoundError,
    DuplicateDocumentTypeError,
    MaxDocumentsExceededError,
)
from app.schemas.case import CaseStatus, DocumentStatus
from app.schemas.ocr import MRZData, TravelerFields
from app.services.case.case_audit import CaseEventType
from app.services.case.case_risk import case_risk_evaluator
from app.services.case.case_store import case_store
from app.services.case.verification_case import CaseDocument, VerificationCase
from app.services.cross_document.cross_document_engine import cross_document_engine
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
from app.services.face.session_store import session_document_store
from app.services.forensics.forensic_service import run_forensic_analysis
from app.services.ingestion.document_ingestion import ingest_document
from app.services.ocr import ocr_engine
from app.services.ocr.passport_parser import parse_passport
from app.services.preprocessing.image_preprocessor import preprocess
from app.services.registry.engine import registry_engine
from app.services.registry.session_store import registry_session_store
from app.services.risk.risk_session_store import risk_session_store
from app.services.validation.passport_validation_service import validate_passport_document
from app.schemas.audit import BlockchainEventType
from app.services.audit.audit_integrity_service import audit_integrity_service
from app.services.evidence.evidence_normalizer import evidence_normalizer

logger = logging.getLogger(__name__)


class CaseManager:
    """Master orchestrator for Multi-Document Screening Cases."""

    def __init__(self) -> None:
        self._store = case_store
        self._cross_doc_engine = cross_document_engine
        self._risk_evaluator = case_risk_evaluator

    def create_case(
        self,
        case_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> VerificationCase:
        """Initialize and store a new verification case."""
        cid = case_id or f"CASE-{datetime.date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        case = VerificationCase(case_id=cid, status=CaseStatus.ACTIVE, notes=notes)
        case.record_event(CaseEventType.CASE_CREATED, details={"notes": notes} if notes else {})
        self._store.set(cid, case)
        audit_integrity_service.anchor_event(
            target_id=cid,
            event_type=BlockchainEventType.CASE_CREATED,
            metadata={"notes": notes, "case_id": cid},
        )
        logger.info("CaseManager: created verification case id=%s", cid)
        return case

    def get_case(self, case_id: str) -> VerificationCase:
        """Retrieve an existing verification case or raise CaseNotFoundError."""
        case = self._store.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        return case

    async def add_document_to_case(
        self,
        case_id: str,
        document_type: str,
        file_bytes: bytes,
        filename: str,
        declared_mime: str = "image/jpeg",
        replace: bool = False,
    ) -> Tuple[CaseDocument, VerificationCase]:
        """
        Add a document to an existing case, run its individual analytical pipeline,
        evaluate cross-document consistency with peers, and refresh case risk.
        """
        case = self.get_case(case_id)

        # 1. Validate document type is registered and operational
        profile = document_profile_registry.resolve_operational(document_type)

        # 2. Check document limit
        active_docs = case.get_active_documents()
        if len(active_docs) >= settings.MAX_DOCUMENTS_PER_CASE:
            raise MaxDocumentsExceededError(settings.MAX_DOCUMENTS_PER_CASE)

        # 3. Check duplicate document type
        existing = case.get_document_by_type(profile.document_type)
        revision = 1
        if existing:
            if not replace:
                raise DuplicateDocumentTypeError(profile.document_type)
            case.supersede_document_type(profile.document_type)
            revision = existing.document_revision + 1

        # 4. Generate document identifiers
        doc_id = f"DOC-{len(case.documents) + 1:03d}"
        verification_id = f"vid-{uuid.uuid4()}"

        # 5. Execute M1: Ingestion, Preprocessing, OCR
        ingested = await ingest_document(
            raw_bytes=file_bytes,
            declared_mime=declared_mime or "image/jpeg",
            filename=filename or "document.jpg",
        )
        preprocessed = preprocess(ingested.image_np)
        session_document_store.set(verification_id, ingested.raw_bytes)

        ocr_regions = ocr_engine.run_ocr(preprocessed.image_np)

        # Parse document fields based on profile
        mrz_data = None
        if profile.document_type == "visa":
            parsed_visa = parse_visa(ocr_regions)
            traveler_dict = {
                "name": getattr(parsed_visa.name, "value", None),
                "docNumber": getattr(parsed_visa.docNumber, "value", None),
                "document_number": getattr(parsed_visa.docNumber, "value", None),
                "dob": getattr(parsed_visa.dob, "value", None),
                "date_of_birth": getattr(parsed_visa.dob, "value", None),
                "nationality": getattr(parsed_visa.nationality, "value", None),
                "authority": getattr(parsed_visa.authority, "value", None),
                "issuedDate": getattr(parsed_visa.issuedDate, "value", None),
                "expiry": getattr(parsed_visa.expiry, "value", None),
                "passportNumber": getattr(parsed_visa.passportNumber, "value", None),
                "passport_number": getattr(parsed_visa.passportNumber, "value", None),
                "visaType": getattr(parsed_visa.visaType, "value", None),
                "visaCategory": getattr(parsed_visa.visaCategory, "value", None),
            }
            if hasattr(parsed_visa, "mrz_line1") and parsed_visa.mrz_line1.value:
                mrz_data = MRZData(
                    line1=parsed_visa.mrz_line1.value,
                    line2=getattr(parsed_visa.mrz_line2, "value", None),
                    raw_line1=parsed_visa.mrz_line1.value,
                    raw_line2=getattr(parsed_visa.mrz_line2, "value", None),
                    confidence_line1=getattr(parsed_visa.mrz_line1, "confidence", 0.95),
                    confidence_line2=getattr(parsed_visa.mrz_line2, "confidence", 0.95),
                )
        elif profile.document_type == "driving_license":
            parsed_dl = parse_driving_license(ocr_regions)
            traveler_dict = {
                "name": getattr(parsed_dl.name, "value", None),
                "docNumber": getattr(parsed_dl.license_number, "value", None),
                "document_number": getattr(parsed_dl.license_number, "value", None),
                "licenseNumber": getattr(parsed_dl.license_number, "value", None),
                "dob": getattr(parsed_dl.dob, "value", None),
                "date_of_birth": getattr(parsed_dl.dob, "value", None),
                "issuedDate": getattr(parsed_dl.issuedDate, "value", None),
                "validFrom": getattr(parsed_dl.valid_from, "value", None),
                "expiry": getattr(parsed_dl.expiry, "value", None),
                "validTo": getattr(parsed_dl.valid_to, "value", None),
                "authority": getattr(parsed_dl.issuing_authority, "value", None),
                "issuing_authority": getattr(parsed_dl.issuing_authority, "value", None),
                "vehicleClass": getattr(parsed_dl.vehicle_classes, "value", None),
                "bloodGroup": getattr(parsed_dl.blood_group, "value", None),
                "state": getattr(parsed_dl.state, "value", None),
            }
        elif profile.document_type in ("national_id", "nationalid", "nid", "aadhaar"):
            parsed_nid = parse_national_id(ocr_regions)
            traveler_dict = {
                "name": getattr(parsed_nid.name, "value", None),
                "docNumber": getattr(parsed_nid.identity_number, "value", None),
                "document_number": getattr(parsed_nid.identity_number, "value", None),
                "identityNumber": getattr(parsed_nid.identity_number, "value", None),
                "maskedIdentityNumber": parsed_nid.masked_identity_number,
                "dob": getattr(parsed_nid.dob, "value", None),
                "date_of_birth": getattr(parsed_nid.dob, "value", None),
                "yearOfBirth": getattr(parsed_nid.year_of_birth, "value", None),
                "year_of_birth": getattr(parsed_nid.year_of_birth, "value", None),
                "gender": getattr(parsed_nid.gender, "value", None),
                "authority": getattr(parsed_nid.issuing_authority, "value", None),
                "issuing_authority": getattr(parsed_nid.issuing_authority, "value", None),
                "address": getattr(parsed_nid.address, "value", None),
                "qrPayload": parsed_nid.qr_payload,
                "qrDecoded": parsed_nid.qr_decoded,
            }
        elif profile.document_type in ("border_permit", "borderpermit"):
            parsed_bp = parse_border_permit(ocr_regions)
            traveler_dict = {
                "name": getattr(parsed_bp.name, "value", None),
                "docNumber": getattr(parsed_bp.permit_number, "value", None),
                "document_number": getattr(parsed_bp.permit_number, "value", None),
                "permitNumber": getattr(parsed_bp.permit_number, "value", None),
                "passportNumber": getattr(parsed_bp.passport_number, "value", None),
                "passport_number": getattr(parsed_bp.passport_number, "value", None),
                "dob": getattr(parsed_bp.dob, "value", None),
                "date_of_birth": getattr(parsed_bp.dob, "value", None),
                "nationality": getattr(parsed_bp.nationality, "value", None),
                "validFrom": getattr(parsed_bp.valid_from, "value", None),
                "valid_from": getattr(parsed_bp.valid_from, "value", None),
                "issuedDate": getattr(parsed_bp.valid_from, "value", None),
                "validTo": getattr(parsed_bp.valid_to, "value", None),
                "valid_to": getattr(parsed_bp.valid_to, "value", None),
                "expiry": getattr(parsed_bp.valid_to, "value", None),
                "permitType": getattr(parsed_bp.permit_type, "value", None),
                "borderZone": getattr(parsed_bp.border_zone, "value", None),
                "portOfEntry": getattr(parsed_bp.port_of_entry, "value", None),
                "authority": getattr(parsed_bp.issuing_authority, "value", None),
                "issuing_authority": getattr(parsed_bp.issuing_authority, "value", None),
                "qrPayload": parsed_bp.qr_payload,
                "qrDecoded": parsed_bp.qr_decoded,
            }
        else:
            parsed_passport = parse_passport(ocr_regions)
            traveler_dict = {
                "name": getattr(parsed_passport.name, "value", None),
                "docNumber": getattr(parsed_passport.docNumber, "value", None),
                "document_number": getattr(parsed_passport.docNumber, "value", None),
                "dob": getattr(parsed_passport.dob, "value", None),
                "date_of_birth": getattr(parsed_passport.dob, "value", None),
                "nationality": getattr(parsed_passport.nationality, "value", None),
                "gender": getattr(parsed_passport.gender, "value", None),
                "placeOfBirth": getattr(parsed_passport.placeOfBirth, "value", None),
                "authority": getattr(parsed_passport.authority, "value", None),
                "issuedDate": getattr(parsed_passport.issuedDate, "value", None),
                "expiry": getattr(parsed_passport.expiry, "value", None),
            }
            if hasattr(parsed_passport, "mrz_line1") and parsed_passport.mrz_line1.value:
                mrz_data = MRZData(
                    line1=parsed_passport.mrz_line1.value,
                    line2=getattr(parsed_passport.mrz_line2, "value", None),
                    raw_line1=parsed_passport.mrz_line1.value,
                    raw_line2=getattr(parsed_passport.mrz_line2, "value", None),
                    confidence_line1=getattr(parsed_passport.mrz_line1, "confidence", 0.95),
                    confidence_line2=getattr(parsed_passport.mrz_line2, "confidence", 0.95),
                )

        # 6. Populate M1 in risk and registry session stores
        risk_session_store.update_module(
            verification_id, "m1_ocr",
            {
                "status": "completed",
                "overall_confidence": 0.95,
                "has_low_confidence_regions": False,
                "mrz_available": bool(mrz_data and getattr(mrz_data, "raw_line1", None)),
                "mrz_detected": bool(mrz_data and getattr(mrz_data, "raw_line1", None)),
                "mrz_applicable": profile.mrz_applicable,
                "critical_fields_missing": [],
                "document_type": profile.document_type,
            },
        )

        registry_session_store.set(verification_id, {
            "document_type": profile.document_type,
            "document_number": traveler_dict.get("docNumber") or traveler_dict.get("document_number"),
            "identity_number": traveler_dict.get("identityNumber") or traveler_dict.get("docNumber"),
            "permit_number": traveler_dict.get("permitNumber") or traveler_dict.get("docNumber"),
            "name": traveler_dict.get("name"),
            "date_of_birth": traveler_dict.get("dob") or traveler_dict.get("date_of_birth"),
            "year_of_birth": traveler_dict.get("yearOfBirth") or traveler_dict.get("year_of_birth"),
            "gender": traveler_dict.get("gender"),
            "nationality": traveler_dict.get("nationality"),
            "expiry_date": traveler_dict.get("expiry") or traveler_dict.get("expiry_date"),
            "valid_from": traveler_dict.get("validFrom") or traveler_dict.get("valid_from"),
            "valid_to": traveler_dict.get("validTo") or traveler_dict.get("valid_to"),
            "issuing_authority": traveler_dict.get("authority") or traveler_dict.get("issuing_authority"),
            "passport_number": traveler_dict.get("passportNumber") or traveler_dict.get("passport_number"),
        })

        module_statuses: Dict[str, str] = {"ocr": "completed"}

        # 7. Execute M2: Validation
        traveler_fields = TravelerFields(**{k: v for k, v in traveler_dict.items() if k in TravelerFields.model_fields})
        try:
            if profile.document_type == "visa":
                val_res = validate_visa_document(traveler_fields, None)
            elif profile.document_type == "driving_license":
                val_res = validate_driving_license_document(traveler_fields, None)
            elif profile.document_type in ("national_id", "nationalid", "nid", "aadhaar"):
                val_res = validate_national_id_document(traveler_fields, None)
            elif profile.document_type in ("border_permit", "borderpermit"):
                val_res = validate_border_permit_document(traveler_fields, None)
            else:
                val_res = validate_passport_document(mrz_data=mrz_data, traveler=traveler_fields)

            val_dict = (
                val_res.model_dump() if hasattr(val_res, "model_dump")
                else (val_res.to_dict() if hasattr(val_res, "to_dict") else val_res)
            )
            module_statuses["validation"] = val_dict.get("status", "completed")
            risk_session_store.update_module(verification_id, "m2_validation", val_dict)
        except Exception as exc:
            logger.warning("CaseManager: M2 validation error id=%s: %s", verification_id, exc)
            module_statuses["validation"] = "failed"

        # 8. Execute M3: Forensics
        try:
            forensic_res = run_forensic_analysis(
                raw_bytes=file_bytes,
                image_np_bgr=ingested.image_np,
                document_type=profile.document_type,
            )
            for_dict = (
                forensic_res.model_dump() if hasattr(forensic_res, "model_dump")
                else (forensic_res.to_dict() if hasattr(forensic_res, "to_dict") else forensic_res)
            )
            module_statuses["forensics"] = for_dict.get("status", "completed")
            risk_session_store.update_module(verification_id, "m3_forensics", for_dict)
        except Exception as exc:
            logger.warning("CaseManager: M3 forensics error id=%s: %s", verification_id, exc)
            module_statuses["forensics"] = "failed"

        # 9. Execute M5: Registry Verification
        try:
            reg_res = registry_engine.verify(verification_id, profile.document_type)
            module_statuses["registry"] = reg_res.registry.get("status", "UNKNOWN")
            prov_meta = (
                reg_res.provider_metadata.model_dump()
                if hasattr(reg_res.provider_metadata, "model_dump")
                else (reg_res.provider_metadata or {})
            )
            risk_session_store.update_module(
                verification_id, "m5_registry",
                {
                    "registry": reg_res.registry,
                    "field_results": [
                        fr.model_dump() if hasattr(fr, "model_dump") else fr
                        for fr in (reg_res.field_results or [])
                    ],
                    "provider_metadata": prov_meta,
                },
            )
        except Exception as exc:
            logger.warning("CaseManager: M5 registry error id=%s: %s", verification_id, exc)
            module_statuses["registry"] = "failed"

        # 10. Assemble CaseDocument and add to case
        case_doc = CaseDocument(
            document_id=doc_id,
            document_type=profile.document_type,
            verification_id=verification_id,
            status=DocumentStatus.COMPLETED,
            document_revision=revision,
            filename=filename,
            traveler_data=traveler_dict,
            module_statuses=module_statuses,
        )
        case.add_document(case_doc)

        # 11. Run Cross-Document Analysis if 2+ documents are present
        if len(case.get_active_documents()) >= 2:
            self._cross_doc_engine.evaluate_case(case)

        # 12. Evaluate case-level composite risk
        self._risk_evaluator.evaluate_case_risk(case)

        # 13. Persist and return
        self._store.set(case.case_id, case)

        # 14. Anchor document addition & updated case evidence package
        pkg = evidence_normalizer.normalize_case_evidence(case)
        audit_integrity_service.anchor_event(
            target_id=case.case_id,
            event_type=BlockchainEventType.DOCUMENT_UPLOADED,
            evidence=pkg,
            metadata={
                "document_id": doc_id,
                "document_type": profile.document_type,
                "filename": filename,
                "revision": revision,
            },
        )

        logger.info(
            "CaseManager: added %s doc=%s rev=%d to case=%s",
            profile.document_type, doc_id, revision, case.case_id,
        )
        return case_doc, case

    def remove_document_from_case(
        self,
        case_id: str,
        document_id: str,
    ) -> VerificationCase:
        """Remove a document from the case and recalculate dependent evidence and risk."""
        case = self.get_case(case_id)
        doc = case.remove_document(document_id)
        if not doc:
            raise DocumentNotFoundError(document_id)

        # Re-evaluate cross-document analysis
        if len(case.get_active_documents()) >= 2:
            self._cross_doc_engine.evaluate_case(case)
        else:
            case.relationships = []
            case.cross_document_evidence = []

        # Recalculate case risk
        self._risk_evaluator.evaluate_case_risk(case)

        self._store.set(case.case_id, case)

        # Anchor removal event on blockchain
        pkg = evidence_normalizer.normalize_case_evidence(case)
        audit_integrity_service.anchor_event(
            target_id=case.case_id,
            event_type="DOCUMENT_REMOVED",
            evidence=pkg,
            metadata={"document_id": document_id},
        )

        logger.info("CaseManager: removed doc=%s from case=%s", document_id, case_id)
        return case


case_manager = CaseManager()
