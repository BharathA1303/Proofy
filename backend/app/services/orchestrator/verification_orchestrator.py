"""
backend/app/services/orchestrator/verification_orchestrator.py

End-to-End Production Verification Orchestrator.
Coordinates the verification lifecycle across M1–M6, structured logging with correlation IDs,
audit ledger event anchoring, and stage latency telemetry.
"""
from __future__ import annotations

import logging
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.audit import BlockchainEventType
from app.schemas.evidence import NormalizedEvidenceItem, EvidencePackage
from app.services.audit.audit_integrity_service import audit_integrity_service
from app.services.evidence.evidence_normalizer import evidence_normalizer

logger = logging.getLogger(__name__)


class PipelineStage(str, Enum):
    STANDBY = "STANDBY"
    DOCUMENT_SELECTED = "DOCUMENT_SELECTED"
    UPLOADING = "UPLOADING"
    OCR_PROCESSING = "OCR_PROCESSING"
    VALIDATING = "VALIDATING"
    FORENSICS = "FORENSICS"
    BIOMETRIC_PENDING = "BIOMETRIC_PENDING"
    BIOMETRIC_PROCESSING = "BIOMETRIC_PROCESSING"
    REGISTRY_VERIFICATION = "REGISTRY_VERIFICATION"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    OFFICER_REVIEW = "OFFICER_REVIEW"
    COMPLETED = "COMPLETED"


class StageTelemetry(BaseModel):
    stage: PipelineStage
    started_at: float
    completed_at: float
    duration_ms: float
    status: str = "completed"  # "completed" | "skipped" | "failed"
    details: Dict[str, Any] = Field(default_factory=dict)


class OrchestrationResult(BaseModel):
    verification_id: str
    correlation_id: str
    document_id: str
    document_type: str
    current_stage: PipelineStage
    stages: List[StageTelemetry] = Field(default_factory=list)
    evidence_items: List[NormalizedEvidenceItem] = Field(default_factory=list)
    anchored_events: List[str] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    officer_review_pending: bool = True
    blockchain_integrity: Dict[str, Any] = Field(default_factory=dict)


class VerificationOrchestrator:
    """
    State machine orchestrator managing the screening pipeline end-to-end.
    Guarantees that pipeline termination marks automated execution complete,
    leaving official legal determinations strictly to authorized human officers.
    """

    def __init__(
        self,
        audit_service: Optional[Any] = None,
        normalizer: Optional[Any] = None,
    ) -> None:
        self._audit = audit_service or audit_integrity_service
        self._normalizer = normalizer or evidence_normalizer
        self._stage_latencies: Dict[str, List[float]] = {
            "ocr": [],
            "validation": [],
            "forensics": [],
            "biometrics": [],
            "registry": [],
            "risk": [],
            "blockchain": [],
            "total": [],
        }

    @property
    def stage_latencies(self) -> Dict[str, List[float]]:
        return self._stage_latencies

    def record_latency(self, stage_key: str, latency_ms: float) -> None:
        if stage_key in self._stage_latencies:
            self._stage_latencies[stage_key].append(round(latency_ms, 2))

    async def orchestrate_document(
        self,
        verification_id: str,
        document_id: str,
        document_type: str,
        file_bytes: bytes,
        filename: str,
        live_face_bytes: Optional[bytes] = None,
        case_id: Optional[str] = None,
    ) -> OrchestrationResult:
        correlation_id = f"CORR-{uuid.uuid4().hex[:12].upper()}"
        t_pipeline_start = time.perf_counter()

        stages: List[StageTelemetry] = []
        evidence_items: List[NormalizedEvidenceItem] = []
        anchored_events: List[str] = []

        logger.info(
            "Orchestrator START [corr=%s vid=%s doc=%s type=%s]",
            correlation_id, verification_id, document_id, document_type,
        )

        def _record_stage(stage: PipelineStage, t0: float, status: str = "completed", details: dict = None):
            t1 = time.perf_counter()
            duration_ms = (t1 - t0) * 1000.0
            stages.append(StageTelemetry(
                stage=stage,
                started_at=t0,
                completed_at=t1,
                duration_ms=round(duration_ms, 2),
                status=status,
                details=details or {},
            ))
            logger.info("Orchestrator Stage: %s completed in %.2fms (corr=%s)", stage.value, duration_ms, correlation_id)

        # ── 1. UPLOADING & INGESTION ───────────────────────────────────────
        t0 = time.perf_counter()
        t_bc0 = time.perf_counter()
        self._audit.anchor_event(
            target_id=verification_id,
            event_type=BlockchainEventType.DOCUMENT_UPLOADED,
            metadata={"filename": filename, "document_type": document_type, "correlation_id": correlation_id},
        )
        self.record_latency("blockchain", (time.perf_counter() - t_bc0) * 1000.0)
        anchored_events.append("DOCUMENT_UPLOADED")
        _record_stage(PipelineStage.UPLOADING, t0)

        # ── 2. OCR PROCESSING (M1) ─────────────────────────────────────────
        t0 = time.perf_counter()
        ocr_res_dict = {}
        try:
            from app.services.ingestion.document_ingestion import ingest_document
            from app.services.ocr import ocr_engine
            from app.services.documents.profiles import document_profile_registry
            from app.schemas.ocr import TravelerFields

            ingested = ingest_document(file_bytes=file_bytes, filename=filename, declared_mime="image/jpeg")
            ocr_text, ocr_conf, ocr_regions = ocr_engine.run_ocr(ingested.image_np)

            profile = document_profile_registry.resolve(document_type)
            traveler_dict = {}

            if profile.document_type == "passport":
                from app.services.ocr.passport_parser import parse_passport
                parsed = parse_passport(ocr_regions)
                traveler_dict = parsed.traveler.model_dump()
            elif profile.document_type == "visa":
                from app.services.documents.visa.visa_parser import parse_visa
                parsed = parse_visa(ocr_regions)
                traveler_dict = {f.name: f.value for f in parsed.fields.values() if f.value}
            elif profile.document_type == "driving_license":
                from app.services.documents.driving_license.dl_parser import parse_driving_license
                parsed = parse_driving_license(ocr_regions)
                traveler_dict = parsed.to_dict()
            elif profile.document_type in ("national_id", "nationalid", "nid", "aadhaar", "aadhaarcard", "uid"):
                from app.services.documents.aadhaar.aadhaar_parser import parse_aadhaar
                parsed = parse_aadhaar(ocr_regions)
                traveler_dict = parsed.to_dict()
            elif profile.document_type in ("voter_id", "voterid", "epic", "voter"):
                from app.services.documents.voter_id.voter_id_parser import parse_voter_id
                parsed = parse_voter_id(ocr_regions)
                traveler_dict = parsed.to_dict()
            elif profile.document_type in ("pan_card", "pancard", "pan"):
                from app.services.documents.pan_card.pan_card_parser import parse_pan_card
                parsed = parse_pan_card(ocr_regions)
                traveler_dict = parsed.to_dict()
            elif profile.document_type in ("border_permit", "borderpermit"):
                from app.services.documents.border_permit.border_permit_parser import parse_border_permit
                parsed = parse_border_permit(ocr_regions)
                traveler_dict = parsed.to_dict()

            ocr_res_dict = {"raw_text": ocr_text, "fields": traveler_dict, "meta": {"confidence": ocr_conf}}
            ocr_ev = self._normalizer.normalize_ocr_evidence(document_id, document_type, ocr_res_dict, case_id)
            evidence_items.extend(ocr_ev)
            self.record_latency("ocr", (time.perf_counter() - t0) * 1000.0)

            t_bc = time.perf_counter()
            self._audit.anchor_event(
                target_id=verification_id,
                event_type=BlockchainEventType.OCR_COMPLETED,
                evidence=ocr_ev,
                metadata={"field_count": len(traveler_dict), "correlation_id": correlation_id},
            )
            self.record_latency("blockchain", (time.perf_counter() - t_bc) * 1000.0)
            anchored_events.append("OCR_COMPLETED")
            _record_stage(PipelineStage.OCR_PROCESSING, t0, status="completed")
        except Exception as exc:
            logger.error("Orchestrator: OCR stage failed: %s", exc)
            _record_stage(PipelineStage.OCR_PROCESSING, t0, status="failed", details={"error": str(exc)})

        # ── 3. VALIDATION (M2) ─────────────────────────────────────────────
        t0 = time.perf_counter()
        val_res_dict = {}
        try:
            from app.services.documents.profiles import document_profile_registry
            profile = document_profile_registry.resolve(document_type)
            from app.schemas.ocr import TravelerFields
            t_fields = TravelerFields(**{k: v for k, v in traveler_dict.items() if k in TravelerFields.model_fields})

            if profile.document_type == "visa":
                from app.services.documents.visa.visa_validator import validate_visa_document
                val_res = validate_visa_document(t_fields, None)
            elif profile.document_type == "driving_license":
                from app.services.documents.driving_license.dl_validator import validate_driving_license_document
                val_res = validate_driving_license_document(t_fields, None)
            elif profile.document_type in ("national_id", "nationalid", "nid", "aadhaar", "aadhaarcard", "uid"):
                from app.services.documents.aadhaar.aadhaar_validator import validate_aadhaar_document
                val_res = validate_aadhaar_document(t_fields, None)
            elif profile.document_type in ("voter_id", "voterid", "epic", "voter"):
                from app.services.documents.voter_id.voter_id_validator import validate_voter_id_document
                val_res = validate_voter_id_document(t_fields, None)
            elif profile.document_type in ("pan_card", "pancard", "pan"):
                from app.services.documents.pan_card.pan_card_validator import validate_pan_card_document
                val_res = validate_pan_card_document(t_fields, None)
            elif profile.document_type in ("border_permit", "borderpermit"):
                from app.services.documents.border_permit.border_permit_validator import validate_border_permit_document
                val_res = validate_border_permit_document(t_fields, None)
            else:
                from app.services.validation.passport_validation_service import validate_passport_document
                val_res = validate_passport_document(traveler=t_fields)

            val_res_dict = val_res.model_dump() if hasattr(val_res, "model_dump") else val_res.to_dict()
            val_ev = self._normalizer.normalize_validation_evidence(document_id, document_type, val_res_dict, case_id)
            evidence_items.extend(val_ev)
            self.record_latency("validation", (time.perf_counter() - t0) * 1000.0)

            t_bc = time.perf_counter()
            self._audit.anchor_event(
                target_id=verification_id,
                event_type=BlockchainEventType.VALIDATION_COMPLETED,
                evidence=val_ev,
                metadata={"status": val_res_dict.get("status"), "correlation_id": correlation_id},
            )
            self.record_latency("blockchain", (time.perf_counter() - t_bc) * 1000.0)
            anchored_events.append("VALIDATION_COMPLETED")
            _record_stage(PipelineStage.VALIDATING, t0, status="completed")
        except Exception as exc:
            logger.error("Orchestrator: Validation stage failed: %s", exc)
            _record_stage(PipelineStage.VALIDATING, t0, status="failed", details={"error": str(exc)})

        # ── 4. FORENSICS (M3) ──────────────────────────────────────────────
        t0 = time.perf_counter()
        try:
            from app.services.forensics.forensic_service import run_forensic_analysis
            forensic_res = run_forensic_analysis(
                raw_bytes=file_bytes,
                image_np_bgr=ingested.image_np,
                document_type=document_type,
            )
            for_dict = forensic_res.model_dump() if hasattr(forensic_res, "model_dump") else forensic_res.to_dict()
            for_ev = self._normalizer.normalize_forensics_evidence(document_id, document_type, for_dict, case_id)
            evidence_items.extend(for_ev)
            self.record_latency("forensics", (time.perf_counter() - t0) * 1000.0)

            t_bc = time.perf_counter()
            self._audit.anchor_event(
                target_id=verification_id,
                event_type=BlockchainEventType.FORENSICS_COMPLETED,
                evidence=for_ev,
                metadata={"status": for_dict.get("status"), "correlation_id": correlation_id},
            )
            self.record_latency("blockchain", (time.perf_counter() - t_bc) * 1000.0)
            anchored_events.append("FORENSICS_COMPLETED")
            _record_stage(PipelineStage.FORENSICS, t0, status="completed")
        except Exception as exc:
            logger.error("Orchestrator: Forensics stage failed: %s", exc)
            _record_stage(PipelineStage.FORENSICS, t0, status="failed", details={"error": str(exc)})

        # ── 5. BIOMETRICS (M4) ─────────────────────────────────────────────
        t0 = time.perf_counter()
        if live_face_bytes:
            try:
                from app.services.face.face_verification_service import verify_passport_biometrics
                bio_res = verify_passport_biometrics(doc_image_bytes=file_bytes, live_face_bytes=live_face_bytes)
                bio_dict = bio_res.model_dump() if hasattr(bio_res, "model_dump") else bio_res.to_dict()
                bio_ev = self._normalizer.normalize_biometrics_evidence(document_id, document_type, bio_dict, case_id)
                evidence_items.extend(bio_ev)
                self.record_latency("biometrics", (time.perf_counter() - t0) * 1000.0)

                t_bc = time.perf_counter()
                self._audit.anchor_event(
                    target_id=verification_id,
                    event_type=BlockchainEventType.BIOMETRIC_COMPLETED,
                    evidence=bio_ev,
                    metadata={"status": bio_dict.get("status"), "correlation_id": correlation_id},
                )
                self.record_latency("blockchain", (time.perf_counter() - t_bc) * 1000.0)
                anchored_events.append("BIOMETRIC_COMPLETED")
                _record_stage(PipelineStage.BIOMETRIC_PROCESSING, t0, status="completed")
            except Exception as exc:
                logger.warning("Orchestrator: Biometrics failed: %s", exc)
                _record_stage(PipelineStage.BIOMETRIC_PROCESSING, t0, status="failed", details={"error": str(exc)})
        else:
            _record_stage(PipelineStage.BIOMETRIC_PENDING, t0, status="skipped", details={"reason": "no_live_face_provided"})

        # ── 6. REGISTRY VERIFICATION (M5) ───────────────────────────────────
        t0 = time.perf_counter()
        try:
            from app.services.registry.session_store import registry_session_store
            from app.services.registry.engine import registry_engine

            reg_session = {"document_type": document_type, **traveler_dict}
            registry_session_store.set(verification_id, reg_session)

            reg_res = registry_engine.verify(verification_id, document_type)
            reg_dict = reg_res.model_dump() if hasattr(reg_res, "model_dump") else reg_res.to_dict()
            reg_ev = self._normalizer.normalize_registry_evidence(document_id, document_type, reg_dict, case_id)
            evidence_items.extend(reg_ev)
            self.record_latency("registry", (time.perf_counter() - t0) * 1000.0)

            t_bc = time.perf_counter()
            self._audit.anchor_event(
                target_id=verification_id,
                event_type=BlockchainEventType.REGISTRY_COMPLETED,
                evidence=reg_ev,
                metadata={"status": reg_dict.get("registry", {}).get("status"), "correlation_id": correlation_id},
            )
            self.record_latency("blockchain", (time.perf_counter() - t_bc) * 1000.0)
            anchored_events.append("REGISTRY_COMPLETED")
            _record_stage(PipelineStage.REGISTRY_VERIFICATION, t0, status="completed")
        except Exception as exc:
            logger.warning("Orchestrator: Registry check failed: %s", exc)
            _record_stage(PipelineStage.REGISTRY_VERIFICATION, t0, status="failed", details={"error": str(exc)})

        # ── 7. RISK ASSESSMENT (M6) ────────────────────────────────────────
        t0 = time.perf_counter()
        try:
            from app.services.risk.risk_session_store import risk_session_store
            from app.services.risk.risk_engine import risk_engine

            risk_session_store.update_module(verification_id, "m2_validation", val_res_dict)
            risk_session_store.update_module(verification_id, "m3_forensics", for_dict)
            risk_session_store.update_module(verification_id, "m5_registry", reg_dict)

            risk_assessment = risk_engine.evaluate(verification_id)
            self.record_latency("risk", (time.perf_counter() - t0) * 1000.0)

            t_bc = time.perf_counter()
            self._audit.anchor_event(
                target_id=verification_id,
                event_type=BlockchainEventType.RISK_ASSESSMENT_COMPLETED,
                evidence=risk_assessment.model_dump() if hasattr(risk_assessment, "model_dump") else risk_assessment,
                metadata={
                    "risk_score": getattr(risk_assessment, "risk_score", 0),
                    "risk_level": getattr(risk_assessment, "risk_level", "LOW"),
                    "correlation_id": correlation_id,
                },
            )
            self.record_latency("blockchain", (time.perf_counter() - t_bc) * 1000.0)
            anchored_events.append("RISK_ASSESSMENT_COMPLETED")
            _record_stage(PipelineStage.RISK_ASSESSMENT, t0, status="completed")
        except Exception as exc:
            logger.warning("Orchestrator: Risk assessment failed: %s", exc)
            _record_stage(PipelineStage.RISK_ASSESSMENT, t0, status="failed", details={"error": str(exc)})

        # ── 8. COMPLETED (OFFICER REVIEW READY) ─────────────────────────────
        t0 = time.perf_counter()
        pkg = EvidencePackage(target_id=verification_id, items=evidence_items)
        t_bc = time.perf_counter()
        self._audit.anchor_event(
            target_id=verification_id,
            event_type=BlockchainEventType.EVIDENCE_ANCHORED,
            evidence=pkg,
            metadata={"evidence_items_count": len(evidence_items), "correlation_id": correlation_id},
        )
        self.record_latency("blockchain", (time.perf_counter() - t_bc) * 1000.0)
        anchored_events.append("EVIDENCE_ANCHORED")

        _record_stage(PipelineStage.OFFICER_REVIEW, t0, status="completed")
        _record_stage(PipelineStage.COMPLETED, t0, status="completed")

        t_total_ms = (time.perf_counter() - t_pipeline_start) * 1000.0
        self.record_latency("total", t_total_ms)

        integrity = self._audit.verify_integrity(verification_id, pkg)

        logger.info(
            "Orchestrator COMPLETED [corr=%s vid=%s total=%.2fms events=%d integrity=%s]",
            correlation_id, verification_id, t_total_ms, len(anchored_events), integrity.integrity_status,
        )

        return OrchestrationResult(
            verification_id=verification_id,
            correlation_id=correlation_id,
            document_id=document_id,
            document_type=document_type,
            current_stage=PipelineStage.COMPLETED,
            stages=stages,
            evidence_items=evidence_items,
            anchored_events=anchored_events,
            total_duration_ms=round(t_total_ms, 2),
            officer_review_pending=True,
            blockchain_integrity=integrity.model_dump(),
        )


verification_orchestrator = VerificationOrchestrator()
