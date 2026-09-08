"""
backend/app/services/face/face_enhancer.py

Inbuilt Super-Resolution & Quality Enhancement Layer for Extracted Document Portraits.

Solves degradation common in physical ID cards, passports, and driving licenses:
  1. Low-Resolution & Pixelation: Upscales tiny crops using sub-pixel Lanczos-4 interpolation.
  2. Color Cast & Fading: Neutralizes cyan/blue scan casts and yellowed aged paper via Gray World white balancing.
  3. Lamination & Halftone Print Raster: Denoises print dots using bilateral edge-preserving smoothing.
  4. Washed-Out Exposure & Shadows: Restores facial depth and contrast via LAB CLAHE.
  5. Soft Edges: Reconstructs crisp feature contours (eyes, pupils, nose, mouth) with adaptive unsharp masking.
"""
from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class DocumentFaceEnhancer:
    """
    Dedicated super-resolution, de-quantization, and detail restoration engine
    for low-resolution, scanned, aged, or laminated document credential portraits.
    """

    @staticmethod
    def enhance_portrait_crop(
        crop_bgr: Optional[np.ndarray],
        target_min_dim: int = 360,
    ) -> Optional[np.ndarray]:
        """
        Enhance extracted document portrait crop:
        Progressively upscales pixels, removes printer raster grain, balances skin tones,
        and reconstructs sharp facial micro-features (eyes, pupils, eyebrows, mustache, lips).

        Args:
            crop_bgr: Raw cropped face image in BGR format.
            target_min_dim: Minimum resolution for width or height (default 360px).

        Returns:
            Enhanced high-resolution, color-normalized BGR image.
        """
        if crop_bgr is None or not isinstance(crop_bgr, np.ndarray) or crop_bgr.size == 0:
            return crop_bgr

        try:
            img = crop_bgr.copy()
            h, w = img.shape[:2]

            # ── 1. Halftone Denoising on native resolution first ──────────
            # Suppress printer halftone dots and raster grain BEFORE upscaling to prevent enlarging noise
            denoised_native = cv2.bilateralFilter(img, d=5, sigmaColor=15, sigmaSpace=15)

            # ── 2. Progressive 2-Stage Super-Resolution Pixel Upscaling ──
            min_dim = min(h, w)
            if min_dim < target_min_dim and min_dim > 0:
                scale = target_min_dim / float(min_dim)
                scale = min(6.0, max(1.0, scale))
                mid_scale = scale ** 0.5
                mid_w = int(round(w * mid_scale))
                mid_h = int(round(h * mid_scale))
                target_w = int(round(w * scale))
                target_h = int(round(h * scale))

                step1 = cv2.resize(denoised_native, (mid_w, mid_h), interpolation=cv2.INTER_CUBIC)
                upscaled = cv2.resize(step1, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
            else:
                upscaled = denoised_native

            # ── 3. Gentle Color Cast Neutralization ────────────────────────
            color_balanced = DocumentFaceEnhancer._balance_color_cast(upscaled)

            # ── 4. Natural Contrast & Luminance Detail Restoration (LAB) ───
            lab = cv2.cvtColor(color_balanced, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)

            # High-fidelity CLAHE on L channel
            clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(6, 6))
            l_enhanced = clahe.apply(l_channel)

            # Subtle gamma boost if portrait is underexposed
            mean_l = float(np.mean(l_enhanced))
            if mean_l < 95.0:
                gamma = 1.18
                inv_gamma = 1.0 / gamma
                table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype(np.uint8)
                l_enhanced = cv2.LUT(l_enhanced, table)

            # ── 5. Multi-Frequency Micro-Feature Sharpness (L channel only) ─
            # Decomposes luminance into fine details (eyes, mustache) and medium contours (jaw, nose)
            # Operating exclusively on L channel prevents color fringing and harsh gray halos
            l_float = l_enhanced.astype(np.float32)
            blur_fine = cv2.GaussianBlur(l_float, (0, 0), sigmaX=0.8)
            fine_detail = l_float - blur_fine

            blur_med = cv2.GaussianBlur(l_float, (0, 0), sigmaX=2.0)
            med_detail = l_float - blur_med

            l_sharp = l_float + 1.25 * fine_detail + 0.30 * med_detail
            l_final = np.clip(l_sharp, 0, 255).astype(np.uint8)

            lab_merged = cv2.merge([l_final, a_channel, b_channel])
            enhanced_bgr = cv2.cvtColor(lab_merged, cv2.COLOR_LAB2BGR)

            return enhanced_bgr

        except Exception as exc:
            logger.warning("Document face enhancement skipped due to error: %s", exc)
            return crop_bgr

    @staticmethod
    def _balance_color_cast(img_bgr: np.ndarray) -> np.ndarray:
        """
        Applies Gray World white-balance algorithm with bounded gains
        to eliminate cyan, blue, or yellow scanner color casts while preserving skin tones.
        """
        try:
            b, g, r = cv2.split(img_bgr.astype(np.float32))
            mean_b = float(np.mean(b))
            mean_g = float(np.mean(g))
            mean_r = float(np.mean(r))

            if mean_b <= 0 or mean_g <= 0 or mean_r <= 0:
                return img_bgr

            # Gray baseline
            gray = (mean_b + mean_g + mean_r) / 3.0

            # Bounded channel gains to prevent oversaturation
            kb = np.clip(gray / mean_b, 0.82, 1.22)
            kg = np.clip(gray / mean_g, 0.88, 1.15)
            kr = np.clip(gray / mean_r, 0.82, 1.22)

            b_bal = np.clip(b * kb, 0, 255).astype(np.uint8)
            g_bal = np.clip(g * kg, 0, 255).astype(np.uint8)
            r_bal = np.clip(r * kr, 0, 255).astype(np.uint8)

            return cv2.merge([b_bal, g_bal, r_bal])
        except Exception:
            return img_bgr


document_face_enhancer = DocumentFaceEnhancer()
