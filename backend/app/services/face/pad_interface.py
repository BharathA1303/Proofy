"""
backend/app/services/face/pad_interface.py

Interface definitions for Presentation Attack Detection (PAD) / Anti-Spoofing.
Reflects presentation attack detection concepts aligned with ISO/IEC 30107-3.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class PADAssessment:
    """
    Presentation Attack Detection evaluation result.
    
    Fields:
      status: 'pass' | 'suspected_spoof' | 'inconclusive' | 'model_unavailable'
      score: Calibrated bona fide human probability (0.0 to 1.0) or None.
      model_name: Identifier of the primary PAD architecture.
      explanation: Officer-facing deterministic summary.
      details: Diagnostic metadata.
    """
    status: str
    score: Optional[float] = None
    model_name: str = "Unknown"
    explanation: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_pass(self) -> bool:
        return self.status == "pass"

    @property
    def is_spoof(self) -> bool:
        return self.status == "suspected_spoof"


class PresentationAttackDetector(ABC):
    """
    Abstract interface for presentation attack detection models.
    """

    @abstractmethod
    def initialize(self) -> None:
        """Load pretrained model weights and prepare inference sessions."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the PAD model is loaded and ready for inference."""
        pass

    @abstractmethod
    def predict(
        self,
        face_crop: np.ndarray,
        bbox: Optional[Tuple[int, int, int, int]] = None,
        original_img: Optional[np.ndarray] = None,
    ) -> PADAssessment:
        """
        Evaluate single-frame presentation attack indicators.

        Args:
            face_crop: Cropped BGR face image.
            bbox: (x, y, w, h) bounding box in original_img pixel coordinates.
            original_img: Full uncropped capture frame (required for context scaling).

        Returns:
            PADAssessment object.
        """
        pass

    @abstractmethod
    def predict_sequence(
        self,
        sequence_items: List[Tuple[np.ndarray, Optional[Tuple[int, int, int, int]], Optional[np.ndarray]]],
    ) -> PADAssessment:
        """
        Evaluate temporal presentation attack indicators across burst frames.

        Args:
            sequence_items: List of (face_crop, bbox, original_img) tuples.

        Returns:
            PADAssessment object with multi-frame aggregation.
        """
        pass

    @abstractmethod
    def model_info(self) -> Dict[str, Any]:
        """Return non-sensitive model metadata for system auditability."""
        pass
