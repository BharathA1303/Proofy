"""
backend/app/services/cross_document/relationship_comparator.py

Deterministic field comparator engine for cross-document consistency verification.
Implements strict identifier comparison, normalized date matching, token-based name matching,
and code normalization without aggressive fuzzy matching.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

from app.schemas.cross_document import ComparisonMode, RelationshipStatus
from app.services.registry.normalizers import (
    dates_match,
    document_numbers_match,
    nationalities_match,
    normalize_date,
    normalize_document_number,
    normalize_name_tokens,
    normalize_nationality,
)
from app.services.risk.risk_evidence import EvidenceSeverity

logger = logging.getLogger(__name__)


class RelationshipComparator:
    """Evaluates field-level consistency across documents."""

    @staticmethod
    def compare(
        source_val: Optional[str],
        target_val: Optional[str],
        mode: ComparisonMode,
        base_severity: EvidenceSeverity = EvidenceSeverity.HIGH,
    ) -> Tuple[RelationshipStatus, EvidenceSeverity, str]:
        """
        Compare source_val with target_val according to comparison mode.

        Returns:
            (RelationshipStatus, EvidenceSeverity, explanation)
        """
        s_raw = str(source_val).strip() if source_val is not None else ""
        t_raw = str(target_val).strip() if target_val is not None else ""

        if not s_raw and not t_raw:
            return (
                RelationshipStatus.UNAVAILABLE,
                EvidenceSeverity.NONE,
                "Both source and target document fields are missing or empty.",
            )
        if not s_raw:
            return (
                RelationshipStatus.MISSING_SOURCE_FIELD,
                EvidenceSeverity.NONE,
                "Source document field was not extracted.",
            )
        if not t_raw:
            return (
                RelationshipStatus.MISSING_TARGET_FIELD,
                EvidenceSeverity.NONE,
                "Target document field is not available in session.",
            )

        # ── 1. STRICT IDENTIFIER COMPARISON ─────────────────────────────────
        if mode == ComparisonMode.STRICT:
            s_norm = re.sub(r"[^A-Z0-9]", "", s_raw.upper())
            t_norm = re.sub(r"[^A-Z0-9]", "", t_raw.upper())
            if s_norm == t_norm:
                return (
                    RelationshipStatus.MATCHED,
                    EvidenceSeverity.NONE,
                    f"Identifier match confirmed: '{s_raw}' == '{t_raw}'.",
                )
            return (
                RelationshipStatus.MISMATCH,
                base_severity,
                f"Identifier mismatch: source '{s_raw}' does not match target '{t_raw}'.",
            )

        # ── 2. NORMALIZED DATE COMPARISON ───────────────────────────────────
        if mode == ComparisonMode.NORMALIZED_DATE:
            is_s_year_only = bool(re.match(r"^\d{4}$", s_raw))
            is_t_year_only = bool(re.match(r"^\d{4}$", t_raw))

            s_norm_date = normalize_date(s_raw)
            t_norm_date = normalize_date(t_raw)

            s_year = s_raw if is_s_year_only else (s_norm_date[:4] if s_norm_date else None)
            t_year = t_raw if is_t_year_only else (t_norm_date[:4] if t_norm_date else None)

            # If either source or target is year-only
            if is_s_year_only or is_t_year_only:
                if s_year is None or t_year is None:
                    return (
                        RelationshipStatus.INCONCLUSIVE,
                        EvidenceSeverity.LOW,
                        f"Year/Date values could not be parsed canonically (source='{s_raw}', target='{t_raw}').",
                    )
                if s_year == t_year:
                    return (
                        RelationshipStatus.CONSISTENT_YEAR,
                        EvidenceSeverity.NONE,
                        f"Birth year consistency confirmed: '{s_year}' (source='{s_raw}', target='{t_raw}').",
                    )
                return (
                    RelationshipStatus.MISMATCH,
                    base_severity,
                    f"Birth year mismatch: source '{s_year}' differs from target '{t_year}'.",
                )

            # Both are full dates
            if s_norm_date is None or t_norm_date is None:
                return (
                    RelationshipStatus.INCONCLUSIVE,
                    EvidenceSeverity.LOW,
                    f"Date values could not be parsed canonically (source='{s_raw}', target='{t_raw}').",
                )
            if s_norm_date == t_norm_date:
                return (
                    RelationshipStatus.MATCHED,
                    EvidenceSeverity.NONE,
                    f"Date consistency confirmed: '{s_norm_date}'.",
                )
            return (
                RelationshipStatus.MISMATCH,
                base_severity,
                f"Date mismatch: source '{s_norm_date}' differs from target '{t_norm_date}'.",
            )

        # ── 3. NORMALIZED TOKEN SET (NAME COMPARISON) ───────────────────────
        if mode == ComparisonMode.NORMALIZED_TOKEN_SET:
            s_tokens = normalize_name_tokens(s_raw)
            t_tokens = normalize_name_tokens(t_raw)
            if s_tokens is None or t_tokens is None:
                return (
                    RelationshipStatus.INCONCLUSIVE,
                    EvidenceSeverity.LOW,
                    f"Name values could not be tokenized (source='{s_raw}', target='{t_raw}').",
                )
            if s_tokens == t_tokens:
                return (
                    RelationshipStatus.MATCHED,
                    EvidenceSeverity.NONE,
                    f"Name match confirmed across documents: '{s_raw}'.",
                )
            if s_tokens.issubset(t_tokens) or t_tokens.issubset(s_tokens):
                return (
                    RelationshipStatus.PARTIAL_MATCH,
                    EvidenceSeverity.LOW,
                    f"Name token subset overlap (formatting/middle name variant): source '{s_raw}' vs target '{t_raw}'.",
                )
            return (
                RelationshipStatus.MISMATCH,
                base_severity,
                f"Name mismatch: source '{s_raw}' differs significantly from target '{t_raw}'.",
            )

        # ── 4. NORMALIZED CODE (NATIONALITY/COUNTRY) ─────────────────────────
        if mode == ComparisonMode.NORMALIZED_CODE:
            s_code = normalize_nationality(s_raw)
            t_code = normalize_nationality(t_raw)
            if nationalities_match(s_raw, t_raw):
                return (
                    RelationshipStatus.MATCHED,
                    EvidenceSeverity.NONE,
                    f"Code match confirmed: '{s_code or s_raw}'.",
                )
            return (
                RelationshipStatus.MISMATCH,
                base_severity,
                f"Nationality code mismatch: source '{s_raw}' vs target '{t_raw}'.",
            )

        # Default fallback: exact string equality
        if s_raw.upper() == t_raw.upper():
            return (
                RelationshipStatus.MATCHED,
                EvidenceSeverity.NONE,
                f"Field match confirmed: '{s_raw}'.",
            )
        return (
            RelationshipStatus.MISMATCH,
            base_severity,
            f"Field mismatch: source '{s_raw}' vs target '{t_raw}'.",
        )
