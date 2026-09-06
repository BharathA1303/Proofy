"""
backend/app/services/evidence/evidence_normalizer.py

Evidence Normalizer — Transforms heterogeneous outputs from M1–M6 and Cross-Document engines
into unified, standardized NormalizedEvidenceItem records.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.schemas.evidence import (
    EvidenceModule,
    EvidenceSeverity,
    EvidenceStatus,
    NormalizedEvidenceItem,
    EvidencePackage,
)

logger = logging.getLogger(__name__)


class EvidenceNormalizer:
    """Canonical transformer producing NormalizedEvidenceItem records."""

    @staticmethod
    def normalize_ocr_evidence(
        document_id: str,
        document_type: str,
        ocr_result: Dict[str, Any],
        case_id: Optional[str] = None,
    ) -> List[NormalizedEvidenceItem]:
        items: List[NormalizedEvidenceItem] = []
        raw_text = ocr_result.get("raw_text", "")
        fields = ocr_result.get("fields", {}) or ocr_result.get("traveler_data", {})
        meta = ocr_result.get("meta", {})
        avg_conf = meta.get("confidence", 0.95) if isinstance(meta, dict) else 0.95

        items.append(NormalizedEvidenceItem(
            case_id=case_id,
            document_id=document_id,
            document_type=document_type,
            module=EvidenceModule.OCR,
            signal_type="ocr_text_extraction",
            status=EvidenceStatus.VALID if raw_text or fields else EvidenceStatus.WARNING,
            severity=EvidenceSeverity.INFO if raw_text or fields else EvidenceSeverity.LOW,
            confidence=float(avg_conf),
            description=f"OCR completed with {len(fields)} structured fields extracted.",
            source="paddleocr",
            module_version="1.0.0",
            model_version="PP-OCRv4",
            provenance={"extracted_field_count": len(fields)},
        ))
        return items

    @staticmethod
    def normalize_validation_evidence(
        document_id: str,
        document_type: str,
        val_result: Dict[str, Any],
        case_id: Optional[str] = None,
    ) -> List[NormalizedEvidenceItem]:
        items: List[NormalizedEvidenceItem] = []
        issues = val_result.get("issues", [])
        status_str = str(val_result.get("status", "valid")).lower()

        status_map = {
            "valid": EvidenceStatus.VALID,
            "passed": EvidenceStatus.VALID,
            "warning": EvidenceStatus.WARNING,
            "failed": EvidenceStatus.SUSPICIOUS,
            "critical": EvidenceStatus.SUSPICIOUS,
        }
        overall_status = status_map.get(status_str, EvidenceStatus.WARNING)

        items.append(NormalizedEvidenceItem(
            case_id=case_id,
            document_id=document_id,
            document_type=document_type,
            module=EvidenceModule.VALIDATION,
            signal_type="structural_validation",
            status=overall_status,
            severity=EvidenceSeverity.HIGH if overall_status == EvidenceStatus.SUSPICIOUS else (
                EvidenceSeverity.MEDIUM if overall_status == EvidenceStatus.WARNING else EvidenceSeverity.INFO
            ),
            confidence=1.0,
            description=f"Document structural validation finished with status: {status_str.upper()}",
            source="rule_engine",
            module_version="2.0.0",
            provenance={"issue_count": len(issues)},
        ))

        # Individual validation issues
        for issue in issues:
            desc = issue.get("description", str(issue)) if isinstance(issue, dict) else str(issue)
            sev = issue.get("severity", "medium") if isinstance(issue, dict) else "medium"
            sev_map = {
                "critical": EvidenceSeverity.CRITICAL,
                "high": EvidenceSeverity.HIGH,
                "medium": EvidenceSeverity.MEDIUM,
                "low": EvidenceSeverity.LOW,
                "info": EvidenceSeverity.INFO,
            }
            items.append(NormalizedEvidenceItem(
                case_id=case_id,
                document_id=document_id,
                document_type=document_type,
                module=EvidenceModule.VALIDATION,
                signal_type="validation_issue",
                status=EvidenceStatus.WARNING if sev == "medium" else EvidenceStatus.SUSPICIOUS,
                severity=sev_map.get(str(sev).lower(), EvidenceSeverity.MEDIUM),
                confidence=1.0,
                description=desc,
                source="rule_engine",
                module_version="2.0.0",
                provenance={"raw_issue": issue},
            ))

        return items

    @staticmethod
    def normalize_forensics_evidence(
        document_id: str,
        document_type: str,
        forensic_result: Dict[str, Any],
        case_id: Optional[str] = None,
    ) -> List[NormalizedEvidenceItem]:
        items: List[NormalizedEvidenceItem] = []
        status_str = str(forensic_result.get("status", "pass")).lower()
        anomalies = forensic_result.get("anomalies", [])

        status_map = {
            "pass": EvidenceStatus.VALID,
            "clean": EvidenceStatus.VALID,
            "suspicious": EvidenceStatus.SUSPICIOUS,
            "warning": EvidenceStatus.WARNING,
            "tampered": EvidenceStatus.SUSPICIOUS,
            "insufficient": EvidenceStatus.UNAVAILABLE,
        }
        overall_status = status_map.get(status_str, EvidenceStatus.INFO)

        items.append(NormalizedEvidenceItem(
            case_id=case_id,
            document_id=document_id,
            document_type=document_type,
            module=EvidenceModule.FORENSICS,
            signal_type="forensic_tampering_analysis",
            status=overall_status,
            severity=EvidenceSeverity.HIGH if overall_status == EvidenceStatus.SUSPICIOUS else (
                EvidenceSeverity.MEDIUM if overall_status == EvidenceStatus.WARNING else EvidenceSeverity.INFO
            ),
            confidence=float(forensic_result.get("confidence", 0.90)),
            description=f"Forensic analysis finished with verdict: {status_str.upper()}",
            source="forensic_pipeline",
            module_version="3.0.0",
            model_version="ELA+GradCAM",
            provenance={"anomaly_count": len(anomalies)},
        ))
        return items

    @staticmethod
    def normalize_biometrics_evidence(
        document_id: str,
        document_type: str,
        bio_result: Dict[str, Any],
        case_id: Optional[str] = None,
    ) -> List[NormalizedEvidenceItem]:
        items: List[NormalizedEvidenceItem] = []
        match_status = str(bio_result.get("status", "pass")).lower()
        pad_result = bio_result.get("pad_result", {})
        pad_verdict = pad_result.get("verdict", "PASS") if isinstance(pad_result, dict) else "PASS"

        is_match = match_status in ("pass", "match", "matched")
        items.append(NormalizedEvidenceItem(
            case_id=case_id,
            document_id=document_id,
            document_type=document_type,
            module=EvidenceModule.BIOMETRICS,
            signal_type="face_verification",
            status=EvidenceStatus.VALID if is_match else EvidenceStatus.MISMATCH,
            severity=EvidenceSeverity.INFO if is_match else EvidenceSeverity.CRITICAL,
            confidence=float(bio_result.get("match_score", 0.92)),
            description=f"Facial biometrics match outcome: {'MATCH' if is_match else 'MISMATCH'} (PAD: {pad_verdict})",
            source="arcface_minifasnet",
            module_version="4.0.0",
            model_version="w600k_r50+MiniFASNetV2",
            provenance={"pad_verdict": pad_verdict},
        ))
        return items

    @staticmethod
    def normalize_registry_evidence(
        document_id: str,
        document_type: str,
        reg_result: Dict[str, Any],
        case_id: Optional[str] = None,
    ) -> List[NormalizedEvidenceItem]:
        items: List[NormalizedEvidenceItem] = []
        reg_summary = reg_result.get("registry", {}) if isinstance(reg_result.get("registry"), dict) else reg_result
        status_str = str(reg_summary.get("status", "MATCHED")).upper()

        sev_map = {
            "MATCHED": EvidenceSeverity.INFO,
            "NOT_FOUND": EvidenceSeverity.MEDIUM,
            "EXPIRED": EvidenceSeverity.MEDIUM,
            "REVOKED": EvidenceSeverity.CRITICAL,
            "SUSPENDED": EvidenceSeverity.HIGH,
            "MISMATCH": EvidenceSeverity.HIGH,
            "TIMEOUT": EvidenceSeverity.LOW,
            "UNAVAILABLE": EvidenceSeverity.LOW,
        }
        status_map = {
            "MATCHED": EvidenceStatus.VALID,
            "NOT_FOUND": EvidenceStatus.WARNING,
            "EXPIRED": EvidenceStatus.WARNING,
            "REVOKED": EvidenceStatus.SUSPICIOUS,
            "SUSPENDED": EvidenceStatus.SUSPICIOUS,
            "MISMATCH": EvidenceStatus.MISMATCH,
            "TIMEOUT": EvidenceStatus.UNAVAILABLE,
            "UNAVAILABLE": EvidenceStatus.UNAVAILABLE,
        }

        items.append(NormalizedEvidenceItem(
            case_id=case_id,
            document_id=document_id,
            document_type=document_type,
            module=EvidenceModule.REGISTRY,
            signal_type=f"registry_{status_str.lower()}",
            status=status_map.get(status_str, EvidenceStatus.INFO),
            severity=sev_map.get(status_str, EvidenceSeverity.INFO),
            confidence=1.0,
            description=f"Registry query returned status: {status_str}",
            source="development_mock_registry",
            module_version="5.0.0",
            provenance={"provider": reg_summary.get("provider", "mock_registry")},
        ))
        return items

    @staticmethod
    def normalize_case_evidence(case: Any) -> EvidencePackage:
        """Assembles a full EvidencePackage for a VerificationCase."""
        all_items: List[NormalizedEvidenceItem] = []
        case_id = getattr(case, "case_id", "UNKNOWN_CASE")

        # Extract items from active documents
        docs = case.get_active_documents() if hasattr(case, "get_active_documents") else list(getattr(case, "documents", {}).values())
        for doc in docs:
            doc_id = getattr(doc, "document_id", "DOC")
            doc_type = getattr(doc, "document_type", "unknown")
            module_statuses = getattr(doc, "module_statuses", {})
            traveler_data = getattr(doc, "traveler_data", {})

            # Document entry item
            all_items.append(NormalizedEvidenceItem(
                case_id=case_id,
                document_id=doc_id,
                document_type=doc_type,
                module=EvidenceModule.CASE,
                signal_type="document_intake",
                status=EvidenceStatus.VALID,
                severity=EvidenceSeverity.INFO,
                confidence=1.0,
                description=f"Document {doc_id} ({doc_type.upper()}) intake completed.",
                source="case_manager",
                module_version="1.0.0",
                provenance={"module_statuses": module_statuses},
            ))

        # Extract items from cross-document relationships
        relationships = getattr(case, "relationships", [])
        for rel in relationships:
            rel_dict = rel.model_dump() if hasattr(rel, "model_dump") else (rel if isinstance(rel, dict) else {})
            status_val = str(rel_dict.get("status", "MATCHED")).upper()
            src_doc = rel_dict.get("source_document", {})
            tgt_doc = rel_dict.get("target_document", {})

            rel_status_map = {
                "MATCHED": EvidenceStatus.VALID,
                "PARTIAL_MATCH": EvidenceStatus.WARNING,
                "MISMATCH": EvidenceStatus.MISMATCH,
                "NOT_APPLICABLE": EvidenceStatus.INFO,
            }
            rel_sev_map = {
                "MATCHED": EvidenceSeverity.INFO,
                "PARTIAL_MATCH": EvidenceSeverity.MEDIUM,
                "MISMATCH": EvidenceSeverity.HIGH,
                "NOT_APPLICABLE": EvidenceSeverity.INFO,
            }

            all_items.append(NormalizedEvidenceItem(
                case_id=case_id,
                document_id=src_doc.get("document_id", "SRC"),
                document_type=src_doc.get("document_type", "unknown"),
                module=EvidenceModule.CROSS_DOCUMENT,
                signal_type="cross_doc_consistency",
                status=rel_status_map.get(status_val, EvidenceStatus.INFO),
                severity=rel_sev_map.get(status_val, EvidenceSeverity.INFO),
                confidence=float(rel_dict.get("confidence", 0.95)),
                description=rel_dict.get("explanation", f"Cross-document evaluation: {status_val}"),
                source="cross_document_engine",
                module_version="8.0.0",
                provenance={
                    "source_field": src_doc.get("field"),
                    "target_document_id": tgt_doc.get("document_id"),
                    "target_field": tgt_doc.get("field"),
                },
            ))

        return EvidencePackage(
            target_id=case_id,
            target_type="case",
            timestamp=time.time(),
            items=all_items,
        )


evidence_normalizer = EvidenceNormalizer()
