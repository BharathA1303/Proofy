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
            flags=cv2.INTER_LANCZOS4,
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

        return cv2.resize(crop, target_size, interpolation=cv2.INTER_LANCZOS4)

    @staticmethod
    def enhance_document_face(face_bgr: np.ndarray) -> np.ndarray:
        """
        Normalize illumination, boost edge contrast, and suppress print halftone/scanning raster
        from low-resolution or aged printed credential portraits.
        """
        if face_bgr is None or face_bgr.size == 0:
            return face_bgr

        try:
            # 1. Bilateral filter: smooths scanning halftone print noise while preserving facial edges
            denoised = cv2.bilateralFilter(face_bgr, d=5, sigmaColor=35, sigmaSpace=35)

            # 2. CLAHE on L-channel in LAB color space: local contrast equalization
            lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
            clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
            lab[:, :, 0] = clahe.apply(lab[:, :, 0])
            enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

            # 3. Unsharp masking: restores crisp facial landmark contours (eyes, nose, mouth)
            blurred = cv2.GaussianBlur(enhanced, (0, 0), sigmaX=1.5)
            sharpened = cv2.addWeighted(enhanced, 1.35, blurred, -0.35, 0)
            return sharpened
        except Exception:
            return face_bgr

    @staticmethod
    def get_canonical_rigid_bone_mask(
        shape: Tuple[int, int] = (112, 112),
        feather_radius: int = 7,
    ) -> np.ndarray:
        """
        Construct a smooth 2D anatomical mask for canonical 112x112 ArcFace coordinate space.
        Isolates rigid cranial bone structure (orbits, nasal bridge, maxilla, zygomatic cheekbones,
        and mandibular chin) while suppressing non-rigid peripheral zones (hair, bangs, ears, neck).

        Returns:
            Float32 mask of shape (H, W, 1) normalized to [0.0, 1.0].
        """
        h, w = shape
        mask = np.zeros((h, w), dtype=np.uint8)

        # Anatomical rigid bone ellipse in canonical 112x112 space:
        # Center at (56, 63), horizontal radius 36px (x: 20..92), vertical radius 43px (y: 20..106)
        center = (int(w * 0.50), int(h * 0.56))
        axes = (int(w * 0.33), int(h * 0.40))
        cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)

        # Apply smooth Gaussian feathering to prevent artificial sharp border gradients
        blurred = cv2.GaussianBlur(mask, (feather_radius * 2 + 1, feather_radius * 2 + 1), 0)
        norm_mask = (blurred.astype(np.float32) / 255.0)[:, :, np.newaxis]
        return norm_mask

    @staticmethod
    def apply_rigid_bone_mask(
        aligned_bgr: np.ndarray,
        background_fill: int = 128,
    ) -> np.ndarray:
        """
        Applies canonical rigid bone structural mask to an aligned 112x112 face image.
        Attenuates hairstyles, bangs, hats, and peripheral ears towards a neutral background,
        enabling hair-invariant feature extraction.

        Args:
            aligned_bgr: Aligned 112x112 face crop.
            background_fill: Neutral intensity value (default 128 neutral gray).

        Returns:
            112x112 BGR face image with hair and peripheral non-rigid zones masked.
        """
        if aligned_bgr is None or aligned_bgr.size == 0:
            return aligned_bgr

        h, w = aligned_bgr.shape[:2]
        mask = FaceAligner.get_canonical_rigid_bone_mask((h, w))

        # Smooth alpha blend with neutral gray background
        img_f = aligned_bgr.astype(np.float32)
        bg = np.full_like(img_f, float(background_fill))
        blended = img_f * mask + bg * (1.0 - mask)
        return np.clip(blended, 0, 255).astype(np.uint8)

    @staticmethod
    def compute_cranial_bone_ratios(
        landmarks: List[Tuple[float, float]],
    ) -> dict:
        """
        Compute invariant cranial bone geometric ratios from 5 canonical landmarks.
        Human skull geometry remains invariant to hairstyles, facial hair, makeup, or age:
          1. Interocular distance (left pupil to right pupil)
          2. Facial triangle aspect ratio (interocular / vertical mid-eye to mid-mouth)
          3. Nasal-orbital bilateral symmetry (ratio of left/right eye to nose tip distance)

        Args:
            landmarks: 5 (x, y) tuples [left_eye, right_eye, nose, left_mouth, right_mouth].

        Returns:
            Dictionary with cranial invariant measurements and quality sanity.
        """
        if landmarks is None or len(landmarks) < 5:
            return {
                "valid": False,
                "interocular_dist": 0.0,
                "facial_height": 0.0,
                "cranial_triangle_ratio": 0.0,
                "bilateral_symmetry": 0.0,
            }

        pts = np.array(landmarks, dtype=np.float32)
        le, re, nose, lm, rm = pts[0], pts[1], pts[2], pts[3], pts[4]

        # 1. Interocular distance
        interocular = float(np.linalg.norm(re - le))

        # 2. Midpoints for vertical skull axis
        mid_eyes = (le + re) * 0.5
        mid_mouth = (lm + rm) * 0.5
        facial_height = float(np.linalg.norm(mid_mouth - mid_eyes))

        # 3. Rigid cranial triangle ratio (interocular / vertical height)
        triangle_ratio = interocular / max(facial_height, 1e-4)

        # 4. Nasal-orbital bilateral symmetry
        d_left = float(np.linalg.norm(nose - le))
        d_right = float(np.linalg.norm(nose - re))
        symmetry = min(d_left, d_right) / max(d_left, d_right, 1e-4)

        return {
            "valid": True,
            "interocular_dist": round(interocular, 2),
            "facial_height": round(facial_height, 2),
            "cranial_triangle_ratio": round(triangle_ratio, 4),
            "bilateral_symmetry": round(symmetry, 4),
        }

    @staticmethod
    def compare_cranial_structures(
        ratios_a: dict,
        ratios_b: dict,
        tolerance: float = 0.18,
    ) -> Tuple[float, bool]:
        """
        Compares two cranial bone structures for geometric consistency.

        Returns:
            (cranial_score 0.0..1.0, is_consistent bool)
        """
        if not ratios_a.get("valid") or not ratios_b.get("valid"):
            return (0.85, True)  # Neutral fallback when landmarks unavailable

        r1 = ratios_a.get("cranial_triangle_ratio", 0.0)
        r2 = ratios_b.get("cranial_triangle_ratio", 0.0)
        if r1 <= 0 or r2 <= 0:
            return (0.85, True)

        rel_diff = abs(r1 - r2) / max(r1, r2)
        score = max(0.0, min(1.0, 1.0 - (rel_diff / tolerance)))
        is_consistent = rel_diff <= tolerance
        return (round(score, 4), is_consistent)
