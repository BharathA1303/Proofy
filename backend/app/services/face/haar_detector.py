"""
backend/app/services/face/haar_detector.py

OpenCV Haar Cascade Face Detector.
Maintained as a defensive fallback detector for offline or lightweight environments.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import cv2
import numpy as np

from app.services.face.detector_interface import FaceDetectionResult, FaceDetector

logger = logging.getLogger(__name__)


class OpenCVHaarDetector(FaceDetector):
    """
    OpenCV Haar feature-based cascade classifier.
    Fast CPU detection baseline without requiring external ONNX model files.
    """

    def __init__(self, cascade_path: Optional[str] = None) -> None:
        self._cascade_path = cascade_path or (cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self._cascade = None
        self._initialized = False
        self.initialize()

    def initialize(self) -> None:
        """Load Haar Cascade classifier."""
        try:
            self._cascade = cv2.CascadeClassifier(self._cascade_path)
            self._initialized = not self._cascade.empty()
            if self._initialized:
                logger.info("OpenCVHaarDetector initialized successfully.")
            else:
                logger.warning("Failed to load Haar Cascade from '%s'.", self._cascade_path)
        except Exception as exc:
            logger.error("Error initializing OpenCVHaarDetector: %s", exc)
            self._initialized = False

    def is_available(self) -> bool:
        return self._initialized and self._cascade is not None and not self._cascade.empty()

    @property
    def model_name(self) -> str:
        return "OpenCV-Haar-Cascade"

    def detect_faces(self, image_bgr: np.ndarray) -> List[FaceDetectionResult]:
        """
        Detect faces using multiscale Haar cascades.
        """
        if not self.is_available() or image_bgr is None or image_bgr.size == 0:
            return []

        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        try:
            rects = self._cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(60, 60),
                flags=cv2.CASCADE_SCALE_IMAGE,
            )
        except Exception as exc:
            logger.error("Haar detection failed: %s", exc)
            return []

        if len(rects) == 0:
            return []

        img_h, img_w = image_bgr.shape[:2]
        results: List[FaceDetectionResult] = []
        for x, y, w, h in rects:
            # Clamp bounds
            x = max(0, min(int(x), img_w - 1))
            y = max(0, min(int(y), img_h - 1))
            w = max(1, min(int(w), img_w - x))
            h = max(1, min(int(h), img_h - y))
            results.append(
                FaceDetectionResult(
                    bbox=(x, y, w, h),
                    confidence=0.85,
                    landmarks=None,
                )
            )

        return results
