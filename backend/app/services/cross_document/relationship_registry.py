"""
backend/app/services/cross_document/relationship_registry.py

Central registry for document relationship profiles.
Enforces order-independent resolution between any two document types.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from app.services.cross_document.profiles.dl_national_id_relationship import (
    build_dl_national_id_profile,
)
from app.services.cross_document.profiles.national_id_border_permit_relationship import (
    build_national_id_border_permit_profile,
)
from app.services.cross_document.profiles.passport_border_permit_relationship import (
    build_passport_border_permit_profile,
)
from app.services.cross_document.profiles.passport_dl_relationship import (
    build_passport_dl_profile,
)
from app.services.cross_document.profiles.passport_national_id_relationship import (
    build_passport_national_id_profile,
)
from app.services.cross_document.profiles.passport_visa_relationship import (
    build_passport_visa_profile,
)
from app.services.cross_document.relationship_profile import RelationshipProfile

logger = logging.getLogger(__name__)


class DocumentRelationshipRegistry:
    """
    Registry of relationship profiles between pairs of document types.
    Supports bidirectional / order-independent lookup.
    """

    def __init__(self) -> None:
        self._profiles: Dict[Tuple[str, str], RelationshipProfile] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        pv_profile = build_passport_visa_profile()
        self.register_profile(pv_profile)
        pdl_profile = build_passport_dl_profile()
        self.register_profile(pdl_profile)
        pnid_profile = build_passport_national_id_profile()
        self.register_profile(pnid_profile)
        dlnid_profile = build_dl_national_id_profile()
        self.register_profile(dlnid_profile)
        pbp_profile = build_passport_border_permit_profile()
        self.register_profile(pbp_profile)
        nidbp_profile = build_national_id_border_permit_profile()
        self.register_profile(nidbp_profile)

    def register_profile(self, profile: RelationshipProfile) -> None:
        key = (profile.source_document_type.lower(), profile.target_document_type.lower())
        self._profiles[key] = profile
        logger.info(
            "DocumentRelationshipRegistry: registered profile for %s <-> %s (%d definitions)",
            profile.source_document_type,
            profile.target_document_type,
            len(profile.definitions),
        )

    def register(self, profile: RelationshipProfile) -> None:
        """Alias for register_profile."""
        self.register_profile(profile)

    def resolve_profile(
        self,
        doc_type_a: str,
        doc_type_b: str,
    ) -> Optional[Tuple[RelationshipProfile, bool]]:
        """
        Resolve relationship profile for two document types in an order-independent way.

        Returns:
            (profile, is_reversed) where is_reversed indicates whether doc_type_a
            is the target and doc_type_b is the source.
            Returns None if no relationship profile is registered for this pair.
        """
        a = (doc_type_a or "").strip().lower()
        b = (doc_type_b or "").strip().lower()

        direct_key = (a, b)
        if direct_key in self._profiles:
            return self._profiles[direct_key], False

        reversed_key = (b, a)
        if reversed_key in self._profiles:
            return self._profiles[reversed_key], True

        return None

    def clear(self) -> None:
        self._profiles.clear()


relationship_registry = DocumentRelationshipRegistry()
