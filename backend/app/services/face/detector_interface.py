"""
backend/app/services/face/detector_interface.py

Abstract base interfaces and data structures for modular face detection.
Supports both primary neural detectors (YuNet / SCRFD) and fallback detectors (Haar Cascade).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class FaceDetectionResult:
    """
    Structured result of a detected face instance.
    
    Coordinates:
      bbox: (x, y, w, h) bounding box in original image pixel space.
      landmarks: Optional list of 5 (x, y) coordinates for facial alignment:
                 [left_eye, right_eye, nose, left_mouth_corner, right_mouth_corner]
      confidence: Detection confidence score (0.0 to 1.0).
    """
    bbox: Tuple[int, int, int, int]
    confidence: float = 1.0
    landmarks: Optional[List[Tuple[float, float]]] = None

    @property
    def x(self) -> int:
        return self.bbox[0]

    @property
    def y(self) -> int:
        return self.bbox[1]

    @property
    def width(self) -> int:
        return self.bbox[2]

    @property
    def height(self) -> int:
        return self.bbox[3]


class FaceDetector(ABC):
    """
    Abstract interface for face detection algorithms.
    """

    @abstractmethod
    def detect_faces(self, image_bgr: np.ndarray) -> List[FaceDetectionResult]:
        """
        Locate all face candidates in a BGR image.

        Args:
            image_bgr: Image as a uint8 NumPy array in BGR format.

        Returns:
            List of FaceDetectionResult instances (length 0, 1, or >1).
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if model weights and runtimes are successfully initialized."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable identifier of the detector model."""
        pass
