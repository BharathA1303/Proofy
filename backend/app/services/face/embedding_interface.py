"""
backend/app/services/face/embedding_interface.py

Abstract base interface for deep face recognition embedding models.
Complies with ArcFace / InsightFace 512-dimensional normalized vector standards.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

import numpy as np


class FaceEmbeddingModel(ABC):
    """
    Abstract interface for biometric face feature representation.
    """

    @abstractmethod
    def initialize(self) -> None:
        """Load pretrained model weights and prepare inference sessions."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if model weights are loaded and ready for inference."""
        pass

    @abstractmethod
    def get_embedding(self, aligned_face: np.ndarray) -> np.ndarray:
        """
        Extract a unit-normalized facial embedding vector.

        Args:
            aligned_face: 112x112 BGR facial crop, geometrically aligned.

        Returns:
            1D float32 NumPy array representing the normalized face vector.
            For ArcFace, dimension must equal 512 and norm must equal 1.0.
        """
        pass

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """Return dimensionality of the embedding vector (e.g. 512)."""
        pass

    @abstractmethod
    def model_info(self) -> Dict[str, Any]:
        """Return non-sensitive model metadata for system auditability."""
        pass
