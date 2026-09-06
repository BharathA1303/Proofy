"""
backend/app/services/face/face_aligner.py

Standardized 5-point facial landmark alignment engine.
Implements similarity transformation (Umeyama / partial affine) mapping detected facial landmarks
to the canonical ArcFace 112x112 coordinate reference template.

ArcFace 112x112 Reference Coordinates:
  - Left Eye:    (38.2946, 51.6963)   [subject's right eye, camera left]
  - Right Eye:   (73.5318, 51.5014)   [subject's left eye, camera right]
  - Nose Tip:    (56.0252, 71.7366)
  - Left Mouth:  (41.5493, 92.3655)
  - Right Mouth: (70.7299, 92.2041)
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Canonical ArcFace 112x112 alignment reference points
ARCFACE_REFERENCE_POINTS = np.array([
    [38.2946, 51.6963],  # left eye
    [73.5318, 51.5014],  # right eye
    [56.0252, 71.7366],  # nose tip
    [41.5493, 92.3655],  # left mouth corner
    [70.7299, 92.2041],  # right mouth corner
], dtype=np.float32)


class FaceAligner:
    """
    Geometrically aligns face crops using 5-point facial landmarks.
    Ensures identical spatial normalization for document photographs and live camera frames.
    """

    @staticmethod
    def align_face_5point(
        image_bgr: np.ndarray,
        landmarks: List[Tuple[float, float]],
        target_size: Tuple[int, int] = (112, 112),
    ) -> np.ndarray:
        """
        Warp face to canonical coordinates using a similarity transformation.

        Args:
            image_bgr: Full image in BGR format.
            landmarks: 5 (x, y) coordinates: [left_eye, right_eye, nose, left_mouth, right_mouth].
            target_size: Output spatial resolution (width, height), default (112, 112).

        Returns:
            112x112 aligned BGR face crop.
        """
        if landmarks is None or len(landmarks) != 5:
            raise ValueError("Exactly 5 facial landmarks required for ArcFace alignment.")

        src_pts = np.array(landmarks, dtype=np.float32)
        dst_pts = ARCFACE_REFERENCE_POINTS

        if target_size != (112, 112):
            scale_x = target_size[0] / 112.0
            scale_y = target_size[1] / 112.0
            dst_pts = dst_pts * np.array([scale_x, scale_y], dtype=np.float32)

        # Estimate optimal 2D similarity transform (rotation + uniform scale + translation)
        matrix, inliers = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.LMEDS)

        if matrix is None:
            logger.warning("Similarity transform estimation failed; falling back to bounding box alignment.")
            x1, y1 = np.min(src_pts, axis=0)
            x2, y2 = np.max(src_pts, axis=0)
            crop = image_bgr[max(0, int(y1)):int(y2), max(0, int(x1)):int(x2)]
            return cv2.resize(crop, target_size, interpolation=cv2.INTER_LINEAR)

        aligned = cv2.warpAffine(
            image_bgr,
            matrix,
            target_size,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0.0,
        )
        return aligned

    @staticmethod
    def align_bbox_fallback(
        image_bgr: np.ndarray,
        bbox: Tuple[int, int, int, int],
        margin_pct: float = 0.15,
        target_size: Tuple[int, int] = (112, 112),
    ) -> np.ndarray:
        """
        Crop face bounding box with contextual margin expansion and resize to target dimension.
        Used when 5 landmarks are unavailable (e.g. Haar Cascade fallback detector).
        """
        img_h, img_w = image_bgr.shape[:2]
        x, y, w, h = bbox

        mx = int(w * margin_pct)
        my = int(h * margin_pct)

        x1 = max(0, x - mx)
        y1 = max(0, y - my)
        x2 = min(img_w, x + w + mx)
        y2 = min(img_h, y + h + my)

        crop = image_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            crop = image_bgr[max(0, y):min(img_h, y + h), max(0, x):min(img_w, x + w)]

        return cv2.resize(crop, target_size, interpolation=cv2.INTER_LINEAR)
