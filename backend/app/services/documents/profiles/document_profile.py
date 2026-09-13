"""
backend/app/services/documents/profiles/document_profile.py

Canonical Document Profile definitions.

A DocumentProfile encapsulates the structural, analytical, and operational
characteristics of a document category (Passport, Visa, Driving License, etc.)
allowing M1–M6 to operate dynamically without hardcoded document-type branching.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DocumentType(str, Enum):
    """Canonical document type identifiers."""
    PASSPORT = "passport"
    VISA = "visa"
    DRIVING_LICENSE = "driving_license"
    # Indian identity documents — separate profiles per issuing authority
    AADHAAR = "aadhaar"
    VOTER_ID = "voter_id"
    PAN_CARD = "pan_card"
    BORDER_PERMIT = "border_permit"


class ProfileStatus(str, Enum):
    """Operational readiness of the document profile."""
    AVAILABLE = "available"
    COMING_SOON = "coming_soon"
    NOT_IMPLEMENTED = "not_implemented"


class ModuleSupportStatus(str, Enum):
    """Module-level support declaration for this document type."""
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass
class DocumentProfile:
    """
    Metadata and operational configuration for a document type.

    Explicitly defines:
      - document category and metadata
      - which verification modules are supported vs not implemented
      - biometric and MRZ applicability
      - expected forensic regions
      - canonical field schemas
    """
    document_type: str
    display_name: str
    version: str = "0.7.0"
    status: ProfileStatus = ProfileStatus.AVAILABLE
    description: str = ""

    # Module support matrix: keys are "ocr", "validation", "forensics", "biometrics", "registry", "risk"
    modules: Dict[str, ModuleSupportStatus] = field(default_factory=dict)

    # Physical / structural characteristics
    mrz_applicable: bool = False
    mrz_standard: Optional[str] = None  # e.g., "TD3", "MRV-A", "MRV-B"
    portrait_applicable: bool = True
    portrait_required: bool = False

    # Expected regions for forensic and structural evaluation
    expected_regions: Dict[str, Any] = field(default_factory=dict)

    # Field schema
    field_schema: List[str] = field(default_factory=list)
    required_fields: List[str] = field(default_factory=list)

    # Multi-side support and jurisdiction (M1 Document Intelligence)
    jurisdiction: Optional[str] = "IN"
    sides_supported: List[str] = field(default_factory=lambda: ["front"])
    front_required: bool = True
    back_required: bool = False

    # Document classification heuristics/profile parameters
    classification_config: Dict[str, Any] = field(default_factory=dict)

    # Profile-driven semantic regions for visual/layout understanding
    expected_semantic_regions: Dict[str, Any] = field(default_factory=dict)

    # Profile-driven semantic field definitions (Phase 5)
    semantic_fields: Dict[str, Any] = field(default_factory=dict)

    # Profile-driven structural validation rules (Phase 6)
    validation_config: Dict[str, Any] = field(default_factory=dict)

    # Profile-driven machine-readable / QR capabilities (Phase 7)
    machine_readable_config: Dict[str, Any] = field(default_factory=dict)

    # Profile-driven tampering & forensic configuration (Phase 8)
    forensic_config: Dict[str, Any] = field(default_factory=dict)

    # Profile-driven biometric & face verification configuration (Phase 9)
    biometric_config: Dict[str, Any] = field(default_factory=dict)

    # Profile-driven authoritative registry & corroboration configuration (Phase 10)
    registry_config: Dict[str, Any] = field(default_factory=dict)

    # Profile-driven evidence fusion & risk engine configuration (Phase 11)
    risk_config: Dict[str, Any] = field(default_factory=dict)

    def is_module_supported(self, module_name: str) -> bool:
        """Return True if the specified module is explicitly declared SUPPORTED."""
        return self.modules.get(module_name) == ModuleSupportStatus.SUPPORTED

    def is_available(self) -> bool:
        """Return True if the profile is currently operational."""
        return self.status == ProfileStatus.AVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metadata for client discovery APIs."""
        return {
            "type": self.document_type,
            "display_name": self.display_name,
            "version": self.version,
            "status": self.status.value,
            "description": self.description,
            "modules": {k: v.value for k, v in self.modules.items()},
            "mrz_applicable": self.mrz_applicable,
            "mrz_standard": self.mrz_standard,
            "portrait_applicable": self.portrait_applicable,
            "portrait_required": self.portrait_required,
            "field_schema": self.field_schema,
            "required_fields": self.required_fields,
            "jurisdiction": self.jurisdiction,
            "sides_supported": self.sides_supported,
            "front_required": self.front_required,
            "back_required": self.back_required,
            "semantic_fields": list(self.semantic_fields.keys()),
            "validation_config": list(self.validation_config.keys()),
            "machine_readable_config": list(self.machine_readable_config.keys()),
            "forensic_config": list(self.forensic_config.keys()),
            "biometric_config": list(self.biometric_config.keys()),
            "registry_config": list(self.registry_config.keys()),
            "risk_config": list(self.risk_config.keys()),
        }


