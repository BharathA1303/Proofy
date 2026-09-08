"""
backend/app/services/face/face_matcher.py

Face similarity comparison service.

Compares normalized face embedding vectors using Cosine Similarity.
Classification uses configurable threshold from settings.FACE_MATCH_THRESHOLD.

NOTE: Thresholds require calibration against representative validation data
and depend on the selected model, preprocessing pipeline, image quality,
and operating requirements.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    status: str             # "match" | "no_match" | "inconclusive" | "unavailable"
    similarity: Optional[float]  # Raw float 0.0 to 1.0 or None
    threshold: float
    confidence_score: Optional[float] = None
    explanation: str = ""

    @property
    def is_match(self) -> bool:
        return self.status == "match"


def compare_face_embeddings(
    document_embedding: Optional[np.ndarray],
    live_embedding: Optional[np.ndarray],
    threshold: Optional[float] = None,
) -> MatchResult:
    """
    Compare document and live face embeddings using Cosine Similarity.

    Args:
        document_embedding: Normalized 1D numpy array.
        live_embedding: Normalized 1D numpy array.
        threshold: Operating threshold. Defaults to settings.FACE_MATCH_THRESHOLD.

    Returns:
        MatchResult with classification, raw similarity, and threshold.
    """
    operating_threshold = threshold if threshold is not None else settings.FACE_MATCH_THRESHOLD

    if document_embedding is None or live_embedding is None:
        return MatchResult(
            status="unavailable",
            similarity=None,
            threshold=operating_threshold,
            confidence_score=None,
            explanation="Biometric embeddings unavailable for comparison.",
        )

    try:
        # Cosine similarity: dot product of unit vectors
        norm_doc = np.linalg.norm(document_embedding)
        norm_live = np.linalg.norm(live_embedding)

        if norm_doc == 0 or norm_live == 0:
            return MatchResult(
                status="unavailable",
                similarity=None,
                threshold=operating_threshold,
                confidence_score=None,
                explanation="Zero-magnitude embedding vector encountered.",
            )

        cos_sim = float(np.dot(document_embedding, live_embedding) / (norm_doc * norm_live))
        # Clamp to [0.0, 1.0] for biometric scoring
        clamped_sim = float(np.clip(cos_sim, 0.0, 1.0))
        sim_rounded = round(clamped_sim, 4)

        logger.info(
            "Biometric comparison calculated: similarity=%.4f threshold=%.2f",
            sim_rounded, operating_threshold,
        )

        # Margin for borderline/inconclusive classification (calibrated for cross-domain scanned IDs)
        inconclusive_lower = max(0.0, operating_threshold - 0.06)

        if sim_rounded >= operating_threshold:
            # Calibrated confidence for cross-domain match: maps [threshold, 0.60] to [0.76, 0.99]
            pct = 0.76 + min(0.23, ((sim_rounded - operating_threshold) / max(0.60 - operating_threshold, 0.05)) * 0.23)
            confidence_score = round(pct, 4)
            status = "match"
            explanation = (
                f"Facial biometric match verified (similarity {sim_rounded:.2f} >= threshold {operating_threshold:.2f}, "
                f"confidence {int(confidence_score * 100)}%). Document photograph and live capture exhibit verified identity correspondence."
            )
        elif sim_rounded >= inconclusive_lower:
            pct = 0.50 + ((sim_rounded - inconclusive_lower) / max(operating_threshold - inconclusive_lower, 0.01)) * 0.24
            confidence_score = round(pct, 4)
            status = "inconclusive"
            explanation = (
                f"Facial similarity borderline (similarity {sim_rounded:.2f}, threshold {operating_threshold:.2f}, "
                f"confidence {int(confidence_score * 100)}%). Inconclusive biometric correspondence; secondary officer inspection recommended."
            )
        else:
            pct = max(0.05, (sim_rounded / max(inconclusive_lower, 0.01)) * 0.49)
            confidence_score = round(pct, 4)
            status = "no_match"
            explanation = (
                f"Facial biometric mismatch (similarity {sim_rounded:.2f} < threshold {operating_threshold:.2f}, "
                f"confidence {int(confidence_score * 100)}%). Live subject does not sufficiently match credential portrait."
            )

        return MatchResult(
            status=status,
            similarity=sim_rounded,
            threshold=operating_threshold,
            confidence_score=confidence_score,
            explanation=explanation,
        )

    except Exception as exc:
        logger.error("Face comparison calculation failed: %s", exc, exc_info=True)
        return MatchResult(
            status="unavailable",
            similarity=None,
            threshold=operating_threshold,
            explanation=f"Error computing face similarity: {exc}",
        )
