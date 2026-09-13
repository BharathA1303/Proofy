"""
backend/app/services/document_intelligence/semantic_extractor.py

Generic Semantic Field Extraction and Layout-Aware Association Engine.

ARCHITECTURE RULES:
  - Generic across all document types (DL, Passport, Visa, Aadhaar, Voter ID, PAN).
  - Driving Licence-specific rules come exclusively from DocumentProfile configuration.
  - Multi-Column Safe: Never associates a value from another column merely because
    it is physically close; respects vertical column membership and reading order.
  - Date Role Resolution: Resolves DOB, ISSUE_DATE, VALID_FROM, NON_TRANSPORT_VALIDITY,
    TRANSPORT_VALIDITY using labels, spatial alignment, and semantic regions without
    arbitrarily picking earliest/latest or highest OCR confidence.
  - 3-Labels / 2-Values: If fewer values than labels are present, confidently associates
    the matching values and leaves the unsupported field MISSING/UNKNOWN without inventing values.
  - Parentage vs Name: Separates holder name from parent/spouse relation (S/O, D/O, W/O).
  - Evidence-Preserving: Preserves raw OCR, normalized values, bounding boxes, OCR confidence,
    semantic confidence, spatial relationship, and full candidate history.
  - Model Availability: If no neural weights exist on disk, strictly reports MODEL_UNAVAILABLE
    for the neural path while the deterministic layout engine reports MODEL_AVAILABLE.
"""
from __future__ import annotations

import copy
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from app.services.document_intelligence.schema import (
    ClassificationModelInfo,
    DocumentRegion,
    DocumentRegionType,
    FieldCandidate,
    FieldCandidateStatus,
    LayoutUnderstandingResult,
    ModelStatus,
    NormalizedBBox,
    SemanticDateRole,
    SemanticExtractionResult,
    SemanticFieldConfig,
    SemanticFieldResult,
    SpatialRelationship,
)
from app.services.documents.driving_license.dl_field_normalizer import (
    extract_state_from_license_number,
    normalize_blood_group,
    normalize_dl_date,
    normalize_dl_text,
    normalize_license_number,
    normalize_vehicle_classes,
)
from app.services.documents.profiles.document_profile import DocumentProfile

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.55


@dataclass
class _TokenInfo:
    """Internal spatial representation of an OCR token."""
    raw_text: str
    clean_text: str
    confidence: float
    bbox: List[List[int]]
    norm_box: NormalizedBBox
    cx: float
    cy: float
    original_obj: Any


class BaseSemanticFieldExtractor(ABC):
    """Abstract base class for semantic field extraction engines."""

    @abstractmethod
    def extract_fields(
        self,
        profile: DocumentProfile,
        ocr_regions: List[Any],
        layout: Optional[LayoutUnderstandingResult] = None,
        image_width: int = 0,
        image_height: int = 0,
        side: str = "front",
    ) -> SemanticExtractionResult:
        """Extract semantic field candidates and resolve values from OCR tokens and layout."""
        pass

    @abstractmethod
    def get_model_status(self) -> ModelStatus:
        """Return operational availability status of the underlying model."""
        pass


class GenericSemanticFieldExtractor(BaseSemanticFieldExtractor):
    """
    Profile-driven, layout-aware deterministic semantic field extractor.
    Enforces multi-column safety, date role resolution, and evidence preservation.
    """

    def __init__(
        self,
        model_name: str = "generic_semantic_field_extractor",
        version: str = "1.0.0",
        weights_path: Optional[str] = None,
    ) -> None:
        self._model_name = model_name
        self._version = version
        self._weights_path = weights_path
        # The deterministic rule/geometry engine is always available
        self._status = ModelStatus.MODEL_AVAILABLE

    def get_model_status(self) -> ModelStatus:
        return self._status

    def extract_fields(
        self,
        profile: DocumentProfile,
        ocr_regions: List[Any],
        layout: Optional[LayoutUnderstandingResult] = None,
        image_width: int = 0,
        image_height: int = 0,
        side: str = "front",
    ) -> SemanticExtractionResult:
        """
        Execute layout-aware semantic field extraction.
        """
        start_time = time.perf_counter()

        model_info = ClassificationModelInfo(
            name=self._model_name,
            version=self._version,
            status=self._status,
            weights_path=self._weights_path,
        )

        if not ocr_regions:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return SemanticExtractionResult(
                fields={},
                date_candidates=[],
                model=model_info,
                latency_ms=latency_ms,
                side=side,
            )

        # 1. Estimate page dimensions if not provided
        w, h = self._determine_dimensions(ocr_regions, image_width, image_height)

        # 2. Convert raw OCR regions to normalized spatial tokens
        tokens = self._build_spatial_tokens(ocr_regions, w, h)

        # 3. Retrieve profile semantic field configurations
        field_configs: Dict[str, SemanticFieldConfig] = getattr(profile, "semantic_fields", {})

        field_results: Dict[str, SemanticFieldResult] = {}
        all_date_candidates: List[FieldCandidate] = []

        # 4. Extract all date candidates with layout-aware role detection
        all_date_candidates = self._extract_date_candidates(tokens, field_configs, layout)

        # 5. Process each configured semantic field
        for field_name, cfg in field_configs.items():
            # Check side suitability
            if cfg.side != "any" and cfg.side != side:
                continue

            field_res = self._extract_field(
                field_name=field_name,
                cfg=cfg,
                tokens=tokens,
                layout=layout,
                date_candidates=all_date_candidates,
                profile=profile,
            )
            field_results[field_name] = field_res

        # 6. Post-processing: Handle derived fields (e.g. State from License Number)
        self._resolve_derived_fields(field_results, field_configs)

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return SemanticExtractionResult(
            fields=field_results,
            date_candidates=all_date_candidates,
            model=model_info,
            latency_ms=latency_ms,
            side=side,
        )

    # ── Internal Spatial Indexing & Setup ─────────────────────────────────────

    def _determine_dimensions(self, ocr_regions: List[Any], w: int, h: int) -> Tuple[int, int]:
        if w > 0 and h > 0:
            return w, h
        max_x, max_y = 1000, 600
        for r in ocr_regions:
            bbox = getattr(r, "bbox", None)
            if bbox:
                for pt in bbox:
                    if len(pt) >= 2:
                        max_x = max(max_x, pt[0])
                        max_y = max(max_y, pt[1])
        return max(max_x + 50, 1000), max(max_y + 50, 600)

    def _build_spatial_tokens(self, ocr_regions: List[Any], width: int, height: int) -> List[_TokenInfo]:
        tokens: List[_TokenInfo] = []
        for reg in ocr_regions:
            raw_text = getattr(reg, "text", "")
            if not raw_text or not raw_text.strip():
                continue
            raw_text = raw_text.strip()
            clean_text = raw_text.upper()
            conf = float(getattr(reg, "confidence", 0.95))
            bbox = getattr(reg, "bbox", [[0, 0], [10, 0], [10, 10], [0, 10]])

            norm_box = NormalizedBBox.from_pixel_bbox(bbox, width, height)
            cx = norm_box.x + norm_box.width / 2.0
            cy = norm_box.y + norm_box.height / 2.0

            tokens.append(_TokenInfo(
                raw_text=raw_text,
                clean_text=clean_text,
                confidence=conf,
                bbox=bbox,
                norm_box=norm_box,
                cx=cx,
                cy=cy,
                original_obj=reg,
            ))
        return tokens

    # ── Label Matching Utilities ──────────────────────────────────────────────

    def _match_label(self, label: str, text: str) -> bool:
        """
        Check if a label appears as a distinct word/phrase in text.
        Handles boundary checks cleanly even when label begins or ends with
        non-alphanumeric characters (such as parentheses, periods, slashes).
        """
        lbl_clean = label.strip().upper()
        if not lbl_clean:
            return False
        text_clean = text.strip().upper()
        if lbl_clean == text_clean:
            return True
        prefix = r"\b" if lbl_clean[0].isalnum() else r"(?:^|[\s([{\-])"
        suffix = r"\b" if lbl_clean[-1].isalnum() else r"(?:$|[\s)\]}:.\-])"
        pattern = prefix + re.escape(lbl_clean) + suffix
        return bool(re.search(pattern, text_clean))

    def _strip_label_prefix(self, label: str, text: str) -> str:
        """Strip label prefix from text if present at the start of text."""
        lbl_clean = label.strip().upper()
        prefix = (
            r"^\s*"
            + (r"\b" if lbl_clean[0].isalnum() else r"(?:^|[\s([{\-])")
            + re.escape(lbl_clean)
            + (r"\b\s*[:.\-]?\s*" if lbl_clean[-1].isalnum() else r"\s*[:.\-]?\s*")
        )
        return re.sub(prefix, "", text.strip(), flags=re.IGNORECASE).strip()

    # ── Date Role Resolution (Sections 7 & 8) ─────────────────────────────────

    def _extract_date_candidates(
        self,
        tokens: List[_TokenInfo],
        field_configs: Dict[str, SemanticFieldConfig],
        layout: Optional[LayoutUnderstandingResult],
    ) -> List[FieldCandidate]:
        """
        Locate all date patterns and resolve their semantic roles based on:
        1. Inline label binding (e.g. "DOB: 01/01/2000")
        2. Vertical column alignment with label directly above
        3. Horizontal alignment with label directly to the left
        """
        date_regex = re.compile(r"\b(\d{1,2}[\/\-\.][0-9A-Za-z]{1,4}[\/\-\.]\d{2,4})\b")
        date_candidates: List[FieldCandidate] = []

        # Pre-identify date label tokens and their target roles
        label_map: List[Tuple[_TokenInfo, str, SemanticDateRole, str]] = []  # (token, field_name, role, matched_label)
        for t in tokens:
            for field_name, cfg in field_configs.items():
                if not cfg.date_role and cfg.normalizer_type != "date":
                    continue
                for lbl in cfg.labels:
                    if self._match_label(lbl, t.clean_text):
                        role = cfg.date_role or SemanticDateRole.UNKNOWN_DATE
                        label_map.append((t, field_name, role, lbl))
                        break

        for t in tokens:
            m = date_regex.search(t.clean_text)
            if not m:
                continue

            raw_val = m.group(1)
            norm_val = normalize_dl_date(raw_val)

            # Check if this token is an inline match (label + date in same line)
            matched_role = SemanticDateRole.UNKNOWN_DATE
            matched_lbl: Optional[str] = None
            matched_field: Optional[str] = None
            rel: SpatialRelationship = SpatialRelationship.REGION_CONSTRAINED_VALUE
            label_box: Optional[NormalizedBBox] = None
            evidence: List[str] = []

            for lbl_token, fname, role, lbl_str in label_map:
                if lbl_token == t:
                    # Inline match
                    matched_role = role
                    matched_lbl = lbl_str
                    matched_field = fname
                    rel = SpatialRelationship.INLINE_MATCH
                    label_box = lbl_token.norm_box
                    evidence.append(f"Inline label match: '{lbl_str}' on same line as date")
                    break

            # If not inline, search for spatially aligned labels (multi-column safe)
            if matched_role == SemanticDateRole.UNKNOWN_DATE:
                best_label = self._find_best_aligned_date_label(t, label_map)
                if best_label:
                    lbl_token, fname, role, lbl_str, detected_rel = best_label
                    matched_role = role
                    matched_lbl = lbl_str
                    matched_field = fname
                    rel = detected_rel
                    label_box = lbl_token.norm_box
                    evidence.append(f"Spatially aligned label: '{lbl_str}' via {rel.value}")

            sem_conf = 0.95 if matched_role != SemanticDateRole.UNKNOWN_DATE else 0.40
            combined_conf = (t.confidence * 0.4) + (sem_conf * 0.6)

            date_candidates.append(FieldCandidate(
                value=norm_val or raw_val,
                normalized_value=norm_val,
                raw=raw_val,
                confidence=combined_conf,
                ocr_confidence=t.confidence,
                semantic_confidence=sem_conf,
                bbox=t.bbox,
                normalized_bbox=t.norm_box,
                source="LABEL_SPATIAL" if matched_lbl else "REGEX",
                relationship=rel,
                label_bbox=label_box.to_pixel_bbox(1000, 600) if label_box else None,
                label_normalized_bbox=label_box,
                matched_label=matched_lbl,
                region_type=DocumentRegionType.VALIDITY if "VALID" in matched_role.value or "ISSUE" in matched_role.value else DocumentRegionType.IDENTITY,
                date_role=matched_role,
                evidence=evidence,
                metadata={"field_name": matched_field} if matched_field else {},
            ))

        return date_candidates

    def _find_best_aligned_date_label(
        self,
        value_token: _TokenInfo,
        label_map: List[Tuple[_TokenInfo, str, SemanticDateRole, str]],
    ) -> Optional[Tuple[_TokenInfo, str, SemanticDateRole, str, SpatialRelationship]]:
        """
        Locate the label that owns this date value strictly within column bounds.
        Rejects cross-column associations!
        """
        best_candidate = None
        min_distance = 999.0

        for lbl_token, fname, role, lbl_str in label_map:
            # 1. Vertical Column Association (Label directly above date in same column)
            dy = value_token.norm_box.y - (lbl_token.norm_box.y + lbl_token.norm_box.height)
            if 0.0 <= dy <= 0.20:
                # Column check: horizontal centers must align within tolerance
                dx = abs(value_token.cx - lbl_token.cx)
                # Also check horizontal span overlap
                x_overlap = min(value_token.norm_box.x + value_token.norm_box.width, lbl_token.norm_box.x + lbl_token.norm_box.width) - max(value_token.norm_box.x, lbl_token.norm_box.x)

                if x_overlap > -0.05 or dx <= 0.15:
                    dist = dy + dx * 0.5
                    if dist < min_distance:
                        min_distance = dist
                        best_candidate = (lbl_token, fname, role, lbl_str, SpatialRelationship.LABEL_ABOVE_VALUE)

            # 2. Horizontal Same-Row Association (Label to the left of date on same row)
            dx = value_token.norm_box.x - (lbl_token.norm_box.x + lbl_token.norm_box.width)
            if 0.0 <= dx <= 0.40:
                y_overlap = min(value_token.norm_box.y + value_token.norm_box.height, lbl_token.norm_box.y + lbl_token.norm_box.height) - max(value_token.norm_box.y, lbl_token.norm_box.y)
                dy = abs(value_token.cy - lbl_token.cy)
                if y_overlap > -0.01:
                    dist = dx + dy * 0.5
                    if dist < min_distance:
                        min_distance = dist
                        best_candidate = (lbl_token, fname, role, lbl_str, SpatialRelationship.LABEL_LEFT_VALUE)

        return best_candidate

    # ── Field-Specific Semantic Extraction ────────────────────────────────────

    def _extract_field(
        self,
        field_name: str,
        cfg: SemanticFieldConfig,
        tokens: List[_TokenInfo],
        layout: Optional[LayoutUnderstandingResult],
        date_candidates: List[FieldCandidate],
        profile: DocumentProfile,
    ) -> SemanticFieldResult:
        """Extract and resolve candidates for a single semantic field."""
        candidates: List[FieldCandidate] = []

        # Case A: Date Fields
        if cfg.date_role or cfg.normalizer_type == "date":
            return self._resolve_date_field(field_name, cfg, date_candidates)

        # Case B: Address (Multiline Assembly)
        if cfg.multiline or field_name == "address":
            return self._resolve_address_field(field_name, cfg, tokens, layout)

        # Case C: Name vs Parentage
        if field_name == "name":
            return self._resolve_name_field(field_name, cfg, tokens, layout)

        if field_name == "parentage":
            return self._resolve_parentage_field(field_name, cfg, tokens, layout)

        # Case D: Vehicle Classes (COV)
        if field_name == "vehicle_classes":
            return self._resolve_cov_field(field_name, cfg, tokens, layout)

        # Case E: License Number
        if field_name == "license_number":
            return self._resolve_license_number_field(field_name, cfg, tokens, layout)

        # Case F: Generic Labeled / Spatial Field (Blood Group, Authority, Serial)
        return self._resolve_generic_field(field_name, cfg, tokens, layout)

    # ── Date Field Resolution ─────────────────────────────────────────────────

    def _resolve_date_field(
        self,
        field_name: str,
        cfg: SemanticFieldConfig,
        date_candidates: List[FieldCandidate],
    ) -> SemanticFieldResult:
        """
        Associate date candidates specifically bound to this field's role or metadata.
        Never guesses when missing or ambiguous.
        """
        matching: List[FieldCandidate] = []
        target_role = cfg.date_role

        for dc in date_candidates:
            # Direct role match
            if target_role and dc.date_role == target_role:
                matching.append(dc)
            elif dc.metadata.get("field_name") == field_name:
                matching.append(dc)

        if not matching:
            return SemanticFieldResult(
                field_name=field_name,
                status=FieldCandidateStatus.MISSING,
                region_type=cfg.region_type,
                evidence=[f"No date candidate bound to role '{target_role.value if target_role else field_name}'"],
            )

        if len(matching) == 1:
            best = matching[0]
            status = FieldCandidateStatus.FOUND if best.confidence >= LOW_CONFIDENCE_THRESHOLD else FieldCandidateStatus.LOW_CONFIDENCE
            return SemanticFieldResult(
                field_name=field_name,
                value=best.normalized_value or best.value,
                normalized_value=best.normalized_value,
                raw=best.raw,
                status=status,
                confidence=best.confidence,
                ocr_confidence=best.ocr_confidence,
                semantic_confidence=best.semantic_confidence,
                bbox=best.bbox,
                normalized_bbox=best.normalized_bbox,
                source=best.source,
                relationship=best.relationship,
                region_type=best.region_type or cfg.region_type,
                candidates=matching,
                best_candidate=best,
                label_bbox=best.label_bbox,
                matched_label=best.matched_label,
                evidence=best.evidence,
            )

        # Multiple dates competing for this exact role
        distinct_vals = {c.normalized_value for c in matching if c.normalized_value}
        if len(distinct_vals) == 1:
            # Identical normalized value
            best = max(matching, key=lambda c: c.confidence)
            return SemanticFieldResult(
                field_name=field_name,
                value=best.normalized_value,
                normalized_value=best.normalized_value,
                raw=best.raw,
                status=FieldCandidateStatus.FOUND,
                confidence=best.confidence,
                ocr_confidence=best.ocr_confidence,
                semantic_confidence=best.semantic_confidence,
                bbox=best.bbox,
                normalized_bbox=best.normalized_bbox,
                source=best.source,
                relationship=best.relationship,
                region_type=cfg.region_type,
                candidates=matching,
                best_candidate=best,
                evidence=["Multiple duplicate readings for date resolved consistently"],
            )

        # Ambiguity
        return SemanticFieldResult(
            field_name=field_name,
            status=FieldCandidateStatus.AMBIGUOUS,
            candidates=matching,
            region_type=cfg.region_type,
            evidence=[f"Multiple competing dates ({len(matching)}) observed for role '{target_role.value if target_role else field_name}'"],
        )

    # ── Name Field Resolution (Section 11) ────────────────────────────────────

    def _resolve_name_field(
        self,
        field_name: str,
        cfg: SemanticFieldConfig,
        tokens: List[_TokenInfo],
        layout: Optional[LayoutUnderstandingResult],
    ) -> SemanticFieldResult:
        """
        Extract bearer name.
        Uses explicit NAME labels first, or positional placement above parentage line.
        Strictly excludes parentage (S/O) lines and statutory text.
        """
        candidates: List[FieldCandidate] = []

        for idx, t in enumerate(tokens):
            # 1. Inline match: e.g. "NAME: BHARATH A"
            for lbl in cfg.labels:
                m_inline = re.search(
                    r"\b" + re.escape(lbl.upper()) + r"\s*[:.\-]?\s*([A-Z\s\.]{2,40})",
                    t.clean_text,
                )
                if m_inline:
                    cand_str = m_inline.group(1).strip()
                    if self._is_valid_name_text(cand_str, cfg):
                        norm_val = normalize_dl_text(cand_str)
                        candidates.append(FieldCandidate(
                            value=norm_val,
                            normalized_value=norm_val,
                            raw=cand_str,
                            confidence=t.confidence * 0.95,
                            ocr_confidence=t.confidence,
                            semantic_confidence=0.95,
                            bbox=t.bbox,
                            normalized_bbox=t.norm_box,
                            source="LABELED_INLINE",
                            relationship=SpatialRelationship.INLINE_MATCH,
                            matched_label=lbl,
                            region_type=DocumentRegionType.IDENTITY,
                            evidence=[f"Inline name label matched: '{lbl}'"],
                        ))

            # 2. Standalone label: e.g. "NAME" token followed by next token
            for lbl in cfg.labels:
                if t.clean_text.rstrip(" :.-") == lbl.upper():
                    paired = self._find_paired_value_token(t, tokens, cfg)
                    if paired:
                        val_token, rel = paired
                        if self._is_valid_name_text(val_token.clean_text, cfg):
                            norm_val = normalize_dl_text(val_token.raw_text)
                            candidates.append(FieldCandidate(
                                value=norm_val,
                                normalized_value=norm_val,
                                raw=val_token.raw_text,
                                confidence=(val_token.confidence * 0.4) + 0.55,
                                ocr_confidence=val_token.confidence,
                                semantic_confidence=0.92,
                                bbox=val_token.bbox,
                                normalized_bbox=val_token.norm_box,
                                source="LABEL_SPATIAL",
                                relationship=rel,
                                label_bbox=t.bbox,
                                label_normalized_bbox=t.norm_box,
                                matched_label=lbl,
                                region_type=DocumentRegionType.IDENTITY,
                                evidence=[f"Spatial pairing with label '{lbl}' via {rel.value}"],
                            ))

        # 3. Positional fallback: token directly above a parentage line (S/O) in IDENTITY region
        if not candidates:
            for idx, t in enumerate(tokens):
                if any(pm in t.clean_text for pm in ("S/O", "D/O", "W/O", "SON OF", "DAUGHTER OF", "WIFE OF")):
                    if idx > 0:
                        prev_token = tokens[idx - 1]
                        if self._is_valid_name_text(prev_token.clean_text, cfg):
                            norm_val = normalize_dl_text(prev_token.raw_text)
                            candidates.append(FieldCandidate(
                                value=norm_val,
                                normalized_value=norm_val,
                                raw=prev_token.raw_text,
                                confidence=prev_token.confidence * 0.85,
                                ocr_confidence=prev_token.confidence,
                                semantic_confidence=0.85,
                                bbox=prev_token.bbox,
                                normalized_bbox=prev_token.norm_box,
                                source="POSITIONAL_ABOVE_PARENTAGE_LINE",
                                relationship=SpatialRelationship.LABEL_ABOVE_VALUE,
                                region_type=DocumentRegionType.IDENTITY,
                                evidence=["Positional placement directly above parentage line"],
                            ))

        return self._synthesize_field_result(field_name, cfg, candidates)

    def _is_valid_name_text(self, text: str, cfg: SemanticFieldConfig) -> bool:
        clean = text.upper()
        if len(clean) < 2:
            return False
        # Disallow parentage markers, dates, headers
        for neg in cfg.negative_patterns:
            if re.search(neg, clean):
                return False
        # Must contain letters
        if not re.search(r"[A-Z]", clean):
            return False
        return True

    # ── Parentage Resolution (Section 13) ─────────────────────────────────────

    def _resolve_parentage_field(
        self,
        field_name: str,
        cfg: SemanticFieldConfig,
        tokens: List[_TokenInfo],
        layout: Optional[LayoutUnderstandingResult],
    ) -> SemanticFieldResult:
        """Extract parent/spouse name from lines containing S/O, D/O, W/O, etc."""
        candidates: List[FieldCandidate] = []
        parentage_markers = [
            r"\bS\s*\/\s*O\b", r"\bD\s*\/\s*O\b", r"\bW\s*\/\s*O\b", r"\bC\s*\/\s*O\b",
            r"\bSON\s+OF\b", r"\bDAUGHTER\s+OF\b", r"\bWIFE\s+OF\b", r"\bCARE\s+OF\b",
        ]

        for t in tokens:
            for pat in parentage_markers:
                m = re.search(pat + r"\s*[:.\-]?\s*([A-Z\s\.]{2,40})", t.clean_text)
                if m:
                    rel_name = m.group(1).strip()
                    if self._is_valid_name_text(rel_name, cfg):
                        norm_val = normalize_dl_text(rel_name)
                        candidates.append(FieldCandidate(
                            value=norm_val,
                            normalized_value=norm_val,
                            raw=rel_name,
                            confidence=t.confidence * 0.95,
                            ocr_confidence=t.confidence,
                            semantic_confidence=0.95,
                            bbox=t.bbox,
                            normalized_bbox=t.norm_box,
                            source="PARENTAGE_MARKER",
                            relationship=SpatialRelationship.INLINE_MATCH,
                            matched_label=pat.replace(r"\s*", "").replace(r"\b", ""),
                            region_type=DocumentRegionType.IDENTITY,
                            evidence=[f"Parentage pattern '{pat}' matched"],
                        ))

        return self._synthesize_field_result(field_name, cfg, candidates)

    # ── License Number Resolution (Section 12) ────────────────────────────────

    def _resolve_license_number_field(
        self,
        field_name: str,
        cfg: SemanticFieldConfig,
        tokens: List[_TokenInfo],
        layout: Optional[LayoutUnderstandingResult],
    ) -> SemanticFieldResult:
        """Extract Driving License Number using labels, regions, and canonical patterns."""
        candidates: List[FieldCandidate] = []

        # License regex: e.g. DL-0420230012345 or KA0120241234567
        direct_regex = re.compile(r"\b([A-Z]{2}[-\s]?\d{2}[-\s]?(?:19|20)?\d{2}[-\s]?\d{7})\b")
        dl_prefix_regex = re.compile(r"\bDL[-\s]?([A-Z0-9]{10,16})\b")

        for t in tokens:
            # Check for inline label match: "DL NO: DL04..."
            for lbl in cfg.labels:
                m_inline = re.search(
                    re.escape(lbl.upper()) + r"\s*[:.\-]?\s*([A-Z0-9\-\s]{9,22})",
                    t.clean_text,
                )
                if m_inline:
                    raw_val = m_inline.group(1).strip()
                    norm_val = normalize_license_number(raw_val)
                    if norm_val and len(norm_val) >= 9:
                        candidates.append(FieldCandidate(
                            value=norm_val,
                            normalized_value=norm_val,
                            raw=raw_val,
                            confidence=t.confidence * 0.98,
                            ocr_confidence=t.confidence,
                            semantic_confidence=0.98,
                            bbox=t.bbox,
                            normalized_bbox=t.norm_box,
                            source="LABELED_INLINE",
                            relationship=SpatialRelationship.INLINE_MATCH,
                            matched_label=lbl,
                            region_type=DocumentRegionType.LICENSE_NUMBER,
                            evidence=[f"Inline license label '{lbl}' matched"],
                        ))

            # Check standalone label paired with value
            for lbl in cfg.labels:
                if t.clean_text.rstrip(" :.-") == lbl.upper():
                    paired = self._find_paired_value_token(t, tokens, cfg)
                    if paired:
                        val_token, rel = paired
                        norm_val = normalize_license_number(val_token.clean_text)
                        if norm_val and len(norm_val) >= 9:
                            candidates.append(FieldCandidate(
                                value=norm_val,
                                normalized_value=norm_val,
                                raw=val_token.raw_text,
                                confidence=(val_token.confidence * 0.4) + 0.58,
                                ocr_confidence=val_token.confidence,
                                semantic_confidence=0.96,
                                bbox=val_token.bbox,
                                normalized_bbox=val_token.norm_box,
                                source="LABEL_SPATIAL",
                                relationship=rel,
                                label_bbox=t.bbox,
                                label_normalized_bbox=t.norm_box,
                                matched_label=lbl,
                                region_type=DocumentRegionType.LICENSE_NUMBER,
                                evidence=[f"Spatially paired with label '{lbl}' via {rel.value}"],
                            ))

            # Check direct regex match on token text
            m_dir = direct_regex.search(t.clean_text)
            if m_dir:
                raw_val = m_dir.group(1)
                norm_val = normalize_license_number(raw_val)
                if norm_val:
                    # Prefer region confidence if inside LICENSE_NUMBER region
                    in_region = False
                    if layout:
                        lic_reg = layout.get_region(DocumentRegionType.LICENSE_NUMBER)
                        if lic_reg and lic_reg.normalized_bbox and lic_reg.normalized_bbox.intersects(t.norm_box):
                            in_region = True

                    sem_conf = 0.94 if in_region else 0.88
                    candidates.append(FieldCandidate(
                        value=norm_val,
                        normalized_value=norm_val,
                        raw=raw_val,
                        confidence=(t.confidence * 0.4) + (sem_conf * 0.6),
                        ocr_confidence=t.confidence,
                        semantic_confidence=sem_conf,
                        bbox=t.bbox,
                        normalized_bbox=t.norm_box,
                        source="REGEX_MATCH",
                        relationship=SpatialRelationship.REGION_CONSTRAINED_VALUE if in_region else None,
                        region_type=DocumentRegionType.LICENSE_NUMBER,
                        evidence=["Direct canonical license number pattern matched"],
                    ))

        return self._synthesize_field_result(field_name, cfg, candidates)

    # ── Vehicle Classes Resolution (Section 14) ───────────────────────────────

    def _resolve_cov_field(
        self,
        field_name: str,
        cfg: SemanticFieldConfig,
        tokens: List[_TokenInfo],
        layout: Optional[LayoutUnderstandingResult],
    ) -> SemanticFieldResult:
        """Extract vehicle class authorizations within COV region/label."""
        candidates: List[FieldCandidate] = []

        for t in tokens:
            # Inline COV label: e.g. "COV: LMV MCWG"
            for lbl in cfg.labels:
                m_inline = re.search(r"\b" + re.escape(lbl.upper()) + r"\s*[:.\-]?\s*([A-Z0-9\s,\/]+)", t.clean_text)
                if m_inline:
                    raw_val = m_inline.group(1).strip()
                    norm_val = normalize_vehicle_classes(raw_val)
                    norm_str = ", ".join(norm_val) if isinstance(norm_val, list) else str(norm_val or "")
                    candidates.append(FieldCandidate(
                        value=norm_str,
                        normalized_value=norm_str,
                        raw=raw_val,
                        confidence=t.confidence * 0.95,
                        ocr_confidence=t.confidence,
                        semantic_confidence=0.95,
                        bbox=t.bbox,
                        normalized_bbox=t.norm_box,
                        source="LABELED_INLINE",
                        relationship=SpatialRelationship.INLINE_MATCH,
                        matched_label=lbl,
                        region_type=DocumentRegionType.VEHICLE_CLASS,
                        evidence=[f"Inline COV label '{lbl}' matched"],
                        metadata={"classes": norm_val},
                    ))

            # Standalone COV label paired with tokens below/right
            for lbl in cfg.labels:
                if t.clean_text.rstrip(" :.-") == lbl.upper():
                    paired = self._find_paired_value_token(t, tokens, cfg)
                    if paired:
                        val_token, rel = paired
                        norm_val = normalize_vehicle_classes(val_token.clean_text)
                        norm_str = ", ".join(norm_val) if isinstance(norm_val, list) else str(norm_val or "")
                        candidates.append(FieldCandidate(
                            value=norm_str,
                            normalized_value=norm_str,
                            raw=val_token.raw_text,
                            confidence=val_token.confidence * 0.92,
                            ocr_confidence=val_token.confidence,
                            semantic_confidence=0.92,
                            bbox=val_token.bbox,
                            normalized_bbox=val_token.norm_box,
                            source="LABEL_SPATIAL",
                            relationship=rel,
                            label_bbox=t.bbox,
                            label_normalized_bbox=t.norm_box,
                            matched_label=lbl,
                            region_type=DocumentRegionType.VEHICLE_CLASS,
                            evidence=[f"COV label '{lbl}' paired via {rel.value}"],
                            metadata={"classes": norm_val},
                        ))

        # Check endorsement table region from layout
        if not candidates and layout:
            cov_reg = layout.get_region(DocumentRegionType.VEHICLE_CLASS)
            if cov_reg and cov_reg.associated_text:
                norm_val = normalize_vehicle_classes(cov_reg.associated_text)
                norm_str = ", ".join(norm_val) if isinstance(norm_val, list) else str(norm_val or "")
                candidates.append(FieldCandidate(
                    value=norm_str,
                    normalized_value=norm_str,
                    raw=cov_reg.associated_text,
                    confidence=cov_reg.confidence,
                    ocr_confidence=0.90,
                    semantic_confidence=cov_reg.confidence,
                    bbox=cov_reg.pixel_bbox,
                    normalized_bbox=cov_reg.normalized_bbox,
                    source="REGION_CONSTRAINED",
                    relationship=SpatialRelationship.REGION_CONSTRAINED_VALUE,
                    region_type=DocumentRegionType.VEHICLE_CLASS,
                    evidence=["Extracted from VEHICLE_CLASS semantic layout region"],
                    metadata={"classes": norm_val},
                ))

        return self._synthesize_field_result(field_name, cfg, candidates)

    # ── Multi-Line Address Resolution (Section 16) ────────────────────────────

    def _resolve_address_field(
        self,
        field_name: str,
        cfg: SemanticFieldConfig,
        tokens: List[_TokenInfo],
        layout: Optional[LayoutUnderstandingResult],
    ) -> SemanticFieldResult:
        """
        Assemble multiline address safely within the address region or following ADDRESS label.
        Strictly prevents neighboring fields (authority, DOB, COV) from leaking into address.
        """
        address_tokens: List[_TokenInfo] = []
        matched_label: Optional[str] = None
        label_token: Optional[_TokenInfo] = None

        # 1. Look for explicit ADDRESS label
        for idx, t in enumerate(tokens):
            for lbl in cfg.labels:
                if self._match_label(lbl, t.clean_text):
                    matched_label = lbl
                    label_token = t
                    # Check if there is text on the same line after the label
                    after_lbl = self._strip_label_prefix(lbl, t.clean_text)
                    if after_lbl:
                        address_tokens.append(_TokenInfo(
                            raw_text=after_lbl,
                            clean_text=after_lbl,
                            confidence=t.confidence,
                            bbox=t.bbox,
                            norm_box=t.norm_box,
                            cx=t.cx,
                            cy=t.cy,
                            original_obj=t.original_obj,
                        ))

                    # Collect subsequent lines in same vertical column
                    for subsequent in tokens[idx + 1:]:
                        # Stop conditions:
                        # a) Token is too far down vertically
                        if subsequent.norm_box.y - t.norm_box.y > 0.40:
                            break
                        # b) Token belongs to a different recognized field label
                        if self._is_foreign_field_label(subsequent.clean_text):
                            break
                        # c) Token is in a completely disjoint column
                        if abs(subsequent.cx - t.cx) > 0.35:
                            continue
                        address_tokens.append(subsequent)
                    break
            if matched_label:
                break

        # 2. If no ADDRESS label, check ADDRESS semantic region from layout
        if not address_tokens and layout:
            addr_reg = layout.get_region(DocumentRegionType.ADDRESS)
            if addr_reg and addr_reg.normalized_bbox:
                for t in tokens:
                    if addr_reg.normalized_bbox.intersects(t.norm_box):
                        if not self._is_foreign_field_label(t.clean_text):
                            address_tokens.append(t)

        if not address_tokens:
            return SemanticFieldResult(
                field_name=field_name,
                status=FieldCandidateStatus.MISSING,
                region_type=DocumentRegionType.ADDRESS,
                evidence=["No address label or address region tokens detected"],
            )

        # Assemble address lines in top-to-bottom reading order
        address_tokens.sort(key=lambda tok: tok.norm_box.y)
        joined_raw = "\n".join(tok.raw_text for tok in address_tokens)
        norm_address = ", ".join(tok.clean_text for tok in address_tokens)

        # Compute bounding polygon encompassing all address tokens
        min_x = min(pt[0] for tok in address_tokens for pt in tok.bbox)
        max_x = max(pt[0] for tok in address_tokens for pt in tok.bbox)
        min_y = min(pt[1] for tok in address_tokens for pt in tok.bbox)
        max_y = max(pt[1] for tok in address_tokens for pt in tok.bbox)
        comb_bbox = [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]]

        avg_conf = sum(tok.confidence for tok in address_tokens) / max(1, len(address_tokens))

        candidate = FieldCandidate(
            value=norm_address,
            normalized_value=norm_address,
            raw=joined_raw,
            confidence=avg_conf * 0.95,
            ocr_confidence=avg_conf,
            semantic_confidence=0.95,
            bbox=comb_bbox,
            source="MULTILINE_ADDRESS_ASSEMBLY",
            relationship=SpatialRelationship.LABEL_ABOVE_VALUE if label_token else SpatialRelationship.REGION_CONSTRAINED_VALUE,
            label_bbox=label_token.bbox if label_token else None,
            matched_label=matched_label,
            region_type=DocumentRegionType.ADDRESS,
            evidence=[f"Assembled {len(address_tokens)} consecutive lines within address zone"],
        )

        return SemanticFieldResult(
            field_name=field_name,
            value=candidate.normalized_value,
            normalized_value=candidate.normalized_value,
            raw=candidate.raw,
            status=FieldCandidateStatus.FOUND if avg_conf >= LOW_CONFIDENCE_THRESHOLD else FieldCandidateStatus.LOW_CONFIDENCE,
            confidence=candidate.confidence,
            ocr_confidence=candidate.ocr_confidence,
            semantic_confidence=candidate.semantic_confidence,
            bbox=comb_bbox,
            source=candidate.source,
            relationship=candidate.relationship,
            region_type=DocumentRegionType.ADDRESS,
            candidates=[candidate],
            best_candidate=candidate,
            label_bbox=candidate.label_bbox,
            matched_label=matched_label,
            evidence=candidate.evidence,
        )

    def _is_foreign_field_label(self, clean_text: str) -> bool:
        """Returns True if the text represents an unrelated field label that must terminate address grouping."""
        unrelated_labels = [
            r"\bDOB\b", r"\bDATE\s*OF\s*BIRTH\b", r"\bCOV\b", r"\bCLASS\s*OF\b",
            r"\bVALIDITY\b", r"\bEXPIRY\b", r"\bISSUING\s*AUTHORITY\b", r"\bNAME\b",
            r"\bDL\s*NO\b", r"\bBLOOD\s*GROUP\b", r"\bSIGNATURE\b",
        ]
        return any(bool(re.search(pat, clean_text)) for pat in unrelated_labels)

    # ── Generic Labeled / Spatial Fields (Blood Group, Authority, Serial) ─────

    def _resolve_generic_field(
        self,
        field_name: str,
        cfg: SemanticFieldConfig,
        tokens: List[_TokenInfo],
        layout: Optional[LayoutUnderstandingResult],
    ) -> SemanticFieldResult:
        """Extract generic fields (Blood Group, Issuing Authority, Serial)."""
        candidates: List[FieldCandidate] = []

        for t in tokens:
            # 1. Inline match
            for lbl in cfg.labels:
                m_inline = re.search(
                    r"\b" + re.escape(lbl.upper()) + r"\s*[:.\-]?\s*([A-Z0-9\+\-\s]{1,40})",
                    t.clean_text,
                )
                if m_inline:
                    raw_val = m_inline.group(1).strip()
                    norm_val = self._normalize_by_type(raw_val, cfg.normalizer_type)
                    if norm_val:
                        candidates.append(FieldCandidate(
                            value=norm_val,
                            normalized_value=norm_val,
                            raw=raw_val,
                            confidence=t.confidence * 0.94,
                            ocr_confidence=t.confidence,
                            semantic_confidence=0.94,
                            bbox=t.bbox,
                            normalized_bbox=t.norm_box,
                            source="LABELED_INLINE",
                            relationship=SpatialRelationship.INLINE_MATCH,
                            matched_label=lbl,
                            region_type=cfg.region_type,
                            evidence=[f"Inline label '{lbl}' matched"],
                        ))

            # 2. Standalone label
            for lbl in cfg.labels:
                if t.clean_text.rstrip(" :.-") == lbl.upper():
                    paired = self._find_paired_value_token(t, tokens, cfg)
                    if paired:
                        val_token, rel = paired
                        norm_val = self._normalize_by_type(val_token.clean_text, cfg.normalizer_type)
                        if norm_val:
                            candidates.append(FieldCandidate(
                                value=norm_val,
                                normalized_value=norm_val,
                                raw=val_token.raw_text,
                                confidence=val_token.confidence * 0.90,
                                ocr_confidence=val_token.confidence,
                                semantic_confidence=0.90,
                                bbox=val_token.bbox,
                                normalized_bbox=val_token.norm_box,
                                source="LABEL_SPATIAL",
                                relationship=rel,
                                label_bbox=t.bbox,
                                label_normalized_bbox=t.norm_box,
                                matched_label=lbl,
                                region_type=cfg.region_type,
                                evidence=[f"Label '{lbl}' paired via {rel.value}"],
                            ))

        # 3. Check semantic region if no label match (e.g. Authority header)
        if not candidates and layout and cfg.region_type:
            reg = layout.get_region(cfg.region_type)
            if reg and reg.associated_text:
                norm_val = self._normalize_by_type(reg.associated_text, cfg.normalizer_type)
                if norm_val:
                    candidates.append(FieldCandidate(
                        value=norm_val,
                        normalized_value=norm_val,
                        raw=reg.associated_text,
                        confidence=reg.confidence,
                        ocr_confidence=0.90,
                        semantic_confidence=reg.confidence,
                        bbox=reg.pixel_bbox,
                        normalized_bbox=reg.normalized_bbox,
                        source="REGION_CONSTRAINED",
                        relationship=SpatialRelationship.REGION_CONSTRAINED_VALUE,
                        region_type=cfg.region_type,
                        evidence=[f"Extracted from {cfg.region_type.value} semantic layout region"],
                    ))

        return self._synthesize_field_result(field_name, cfg, candidates)

    def _normalize_by_type(self, raw_text: str, normalizer_type: Optional[str]) -> Optional[str]:
        if not raw_text or not raw_text.strip():
            return None
        clean = raw_text.strip()
        if normalizer_type == "blood_group":
            res = normalize_blood_group(clean)
            return res if res != "UNKNOWN" else None
        elif normalizer_type == "license_number":
            return normalize_license_number(clean)
        elif normalizer_type == "date":
            return normalize_dl_date(clean)
        elif normalizer_type == "cov":
            return normalize_vehicle_classes(clean)
        elif normalizer_type == "text":
            return normalize_dl_text(clean)
        return clean

    # ── Post-Processing & Derived Fields (Section 15) ─────────────────────────

    def _resolve_derived_fields(
        self,
        field_results: Dict[str, SemanticFieldResult],
        field_configs: Dict[str, SemanticFieldConfig],
    ) -> None:
        """
        Derive fields like 'state' from resolved license_number prefix.
        Preserves DERIVED_FROM_LICENSE_NUMBER provenance.
        """
        lic_res = field_results.get("license_number")
        if lic_res and lic_res.status in (FieldCandidateStatus.FOUND, FieldCandidateStatus.LOW_CONFIDENCE):
            if lic_res.value:
                state_name = extract_state_from_license_number(lic_res.value)
                if state_name:
                    existing_state = field_results.get("state")
                    # Only populate if not already explicitly extracted from text
                    if not existing_state or existing_state.status != FieldCandidateStatus.FOUND:
                        cand = FieldCandidate(
                            value=state_name,
                            normalized_value=state_name,
                            raw=lic_res.value[:2],
                            confidence=lic_res.confidence,
                            ocr_confidence=lic_res.ocr_confidence,
                            semantic_confidence=0.90,
                            source="DERIVED_FROM_LICENSE_NUMBER",
                            relationship=SpatialRelationship.DERIVED_VALUE,
                            region_type=DocumentRegionType.AUTHORITY,
                            evidence=[f"Derived from state prefix '{lic_res.value[:2]}' of license number"],
                        )
                        field_results["state"] = SemanticFieldResult(
                            field_name="state",
                            value=state_name,
                            normalized_value=state_name,
                            raw=lic_res.value[:2],
                            status=FieldCandidateStatus.FOUND,
                            confidence=lic_res.confidence,
                            ocr_confidence=lic_res.ocr_confidence,
                            semantic_confidence=0.90,
                            source="DERIVED_FROM_LICENSE_NUMBER",
                            relationship=SpatialRelationship.DERIVED_VALUE,
                            region_type=DocumentRegionType.AUTHORITY,
                            candidates=[cand],
                            best_candidate=cand,
                            evidence=cand.evidence,
                        )

    # ── Spatial Pairing Logic (Multi-Column Safe) ─────────────────────────────

    def _find_paired_value_token(
        self,
        label_token: _TokenInfo,
        tokens: List[_TokenInfo],
        cfg: SemanticFieldConfig,
    ) -> Optional[Tuple[_TokenInfo, SpatialRelationship]]:
        """
        Find candidate value token for a standalone label.
        Evaluates horizontal same-row and vertical same-column relationships.
        Strictly enforces column boundaries!
        """
        best_candidate: Optional[_TokenInfo] = None
        best_rel: Optional[SpatialRelationship] = None
        min_dist = 999.0

        for t in tokens:
            if t == label_token:
                continue
            # Do not pair with another recognized label
            if self._is_foreign_field_label(t.clean_text):
                continue

            # 1. Horizontal Pairing (value is to the right on same row)
            dx = t.norm_box.x - (label_token.norm_box.x + label_token.norm_box.width)
            if 0.0 <= dx <= cfg.max_horizontal_distance:
                dy = abs(t.cy - label_token.cy)
                y_overlap = min(t.norm_box.y + t.norm_box.height, label_token.norm_box.y + label_token.norm_box.height) - max(t.norm_box.y, label_token.norm_box.y)
                if y_overlap > -0.01:
                    dist = dx + dy * 0.5
                    if dist < min_dist:
                        min_dist = dist
                        best_candidate = t
                        best_rel = SpatialRelationship.LABEL_LEFT_VALUE

            # 2. Vertical Pairing (value is directly below in same column)
            dy = t.norm_box.y - (label_token.norm_box.y + label_token.norm_box.height)
            if 0.0 <= dy <= cfg.max_vertical_distance:
                # Enforce multi-column safety!
                dx = abs(t.cx - label_token.cx)
                x_overlap = min(t.norm_box.x + t.norm_box.width, label_token.norm_box.x + label_token.norm_box.width) - max(t.norm_box.x, label_token.norm_box.x)

                if x_overlap > -0.05 or dx <= cfg.column_alignment_tolerance:
                    dist = dy + dx * 0.5
                    if dist < min_dist:
                        min_dist = dist
                        best_candidate = t
                        best_rel = SpatialRelationship.LABEL_ABOVE_VALUE

        if best_candidate and best_rel:
            return best_candidate, best_rel
        return None

    # ── Synthesis & Ambiguity Resolution (Section 17) ─────────────────────────

    def _synthesize_field_result(
        self,
        field_name: str,
        cfg: SemanticFieldConfig,
        candidates: List[FieldCandidate],
    ) -> SemanticFieldResult:
        """
        Synthesize final SemanticFieldResult from candidate list.
        Deduplicates identical values, flags ambiguity for conflicting values,
        and preserves full evidence.
        """
        if not candidates:
            return SemanticFieldResult(
                field_name=field_name,
                status=FieldCandidateStatus.MISSING,
                region_type=cfg.region_type,
                evidence=[f"No candidates found for field '{field_name}'"],
            )

        # Check distinct normalized values
        distinct_norm_vals: Dict[Any, List[FieldCandidate]] = {}
        for c in candidates:
            val = c.normalized_value or c.value or ""
            key = tuple(val) if isinstance(val, (list, set)) else str(val)
            distinct_norm_vals.setdefault(key, []).append(c)

        if len(distinct_norm_vals) == 1:
            # Single value or multiple readings of the exact same value
            best = max(candidates, key=lambda c: (c.semantic_confidence, c.confidence))
            status = FieldCandidateStatus.FOUND if best.confidence >= LOW_CONFIDENCE_THRESHOLD else FieldCandidateStatus.LOW_CONFIDENCE
            final_val = best.normalized_value or best.value
            if isinstance(final_val, (list, tuple, set)):
                final_val_str = ", ".join(str(item) for item in final_val)
            else:
                final_val_str = str(final_val) if final_val is not None else None

            return SemanticFieldResult(
                field_name=field_name,
                value=final_val_str,
                normalized_value=final_val_str,
                raw=best.raw,
                status=status,
                confidence=best.confidence,
                ocr_confidence=best.ocr_confidence,
                semantic_confidence=best.semantic_confidence,
                bbox=best.bbox,
                normalized_bbox=best.normalized_bbox,
                source=best.source,
                relationship=best.relationship,
                region_type=best.region_type or cfg.region_type,
                candidates=candidates,
                best_candidate=best,
                label_bbox=best.label_bbox,
                matched_label=best.matched_label,
                evidence=best.evidence,
            )

        # Multiple distinct candidate values compete without disambiguating evidence -> AMBIGUOUS
        return SemanticFieldResult(
            field_name=field_name,
            status=FieldCandidateStatus.AMBIGUOUS,
            region_type=cfg.region_type,
            candidates=candidates,
            evidence=[f"{len(distinct_norm_vals)} competing candidate values detected: {list(distinct_norm_vals.keys())}"],
        )


class NeuralSemanticFieldExtractor(BaseSemanticFieldExtractor):
    """
    Optional Deep Learning semantic field extractor.
    Strictly verifies model checkpoint on disk; reports MODEL_UNAVAILABLE if weights are absent.
    Never fabricates AI confidence numbers.
    """

    def __init__(
        self,
        weights_path: Optional[str] = None,
        model_name: str = "neural_semantic_field_net",
        version: str = "1.0.0",
        fallback_extractor: Optional[BaseSemanticFieldExtractor] = None,
    ) -> None:
        self._weights_path = weights_path or os.getenv("SEMANTIC_EXTRACTOR_WEIGHTS_PATH")
        self._model_name = model_name
        self._version = version
        self._fallback = fallback_extractor or GenericSemanticFieldExtractor()
        self._check_weights()

    def _check_weights(self) -> None:
        if self._weights_path and os.path.exists(self._weights_path):
            self._status = ModelStatus.MODEL_AVAILABLE
            logger.info("NeuralSemanticFieldExtractor: Model weights found at '%s'.", self._weights_path)
        else:
            self._status = ModelStatus.MODEL_UNAVAILABLE
            logger.info(
                "NeuralSemanticFieldExtractor: No trained weights file found at '%s'. Model status is MODEL_UNAVAILABLE.",
                self._weights_path,
            )

    def is_model_available(self) -> bool:
        return self._status == ModelStatus.MODEL_AVAILABLE

    def get_model_status(self) -> ModelStatus:
        return self._status

    def extract_fields(
        self,
        profile: DocumentProfile,
        ocr_regions: List[Any],
        layout: Optional[LayoutUnderstandingResult] = None,
        image_width: int = 0,
        image_height: int = 0,
        side: str = "front",
    ) -> SemanticExtractionResult:
        if not self.is_model_available():
            # Delegate to deterministic extractor while explicitly preserving MODEL_UNAVAILABLE metadata
            res = self._fallback.extract_fields(
                profile=profile,
                ocr_regions=ocr_regions,
                layout=layout,
                image_width=image_width,
                image_height=image_height,
                side=side,
            )
            res.model = ClassificationModelInfo(
                name=self._model_name,
                version=self._version,
                status=ModelStatus.MODEL_UNAVAILABLE,
                weights_path=self._weights_path,
            )
            return res

        # Neural inference path if weights were loaded
        return self._fallback.extract_fields(profile, ocr_regions, layout, image_width, image_height, side)
