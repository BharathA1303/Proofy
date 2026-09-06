"""
backend/app/services/face/secondary_pad.py

Secondary optical & physical Presentation Attack Detection (PAD) telemetry.
Provides explainable defensive physical indicators alongside the primary deep PAD model.

Evaluates 4 physical optical modalities:
  1. 2D FFT frequency analysis (Moiré screen refresh & pixel-grid detection)
  2. YCrCb chromaticity clustering (Paper photo print chrominance dispersion)
  3. HSV specular reflection analysis (Laminated photo & digital screen glass glare)
  4. Temporal micro-movement variance (Static 2D photo print vs live physiological micro-motion)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SecondaryPADResult:
    """
    Structured breakdown of secondary physical optical indicators.
    Provides border officers with granular explainability.
    """
    frequency_domain: str = "pass"    # 'pass' | 'suspected_spoof' | 'inconclusive'
    texture_analysis: str = "pass"    # 'pass' | 'suspected_spoof' | 'inconclusive'
    specular_glare: str = "pass"      # 'pass' | 'suspected_spoof' | 'inconclusive'
    temporal_variance: str = "pass"   # 'pass' | 'suspected_spoof' | 'inconclusive'
    signals: Dict[str, float] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "frequency_domain": self.frequency_domain,
            "texture_analysis": self.texture_analysis,
            "specular_glare": self.specular_glare,
            "temporal_variance": self.temporal_variance,
        }


class SecondaryOpticalPAD:
    """
    Analytical optical telemetry engine evaluating physical artifacts of presentation attacks.
    """

    def analyze(
        self,
        primary_crop: np.ndarray,
        sequence_crops: Optional[List[np.ndarray]] = None,
    ) -> SecondaryPADResult:
        if primary_crop is None or primary_crop.size == 0:
            return SecondaryPADResult(
                frequency_domain="inconclusive",
                texture_analysis="inconclusive",
                specular_glare="inconclusive",
                temporal_variance="inconclusive",
                summary="No image data provided for optical telemetry.",
            )

        try:
            h, w = primary_crop.shape[:2]
            gray = cv2.cvtColor(primary_crop, cv2.COLOR_BGR2GRAY)

            signals: Dict[str, float] = {}

            # ── 1. Frequency Domain: 2D FFT Moiré Analysis ───────────────
            freq_status = "pass"
            f = np.fft.fft2(gray)
            fshift = np.fft.fftshift(f)
            magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-8)
            cy, cx = h // 2, w // 2
            r = max(min(h, w) // 6, 8)
            y, x = np.ogrid[:h, :w]
            mask = ((x - cx) ** 2 + (y - cy) ** 2) <= r * r
            high_freq = magnitude_spectrum.copy()
            high_freq[mask] = 0
            hf_mean = float(np.mean(high_freq))
            total_mean = float(np.mean(magnitude_spectrum))
            hf_ratio = hf_mean / max(total_mean, 1e-6)
            signals["high_freq_ratio"] = round(hf_ratio, 4)

            # Prominent periodic spikes indicating electronic screen refresh or dot-matrix printing
            if hf_ratio > 0.82:
                freq_status = "suspected_spoof"
            elif hf_ratio > 0.76:
                freq_status = "inconclusive"

            # ── 2. Chrominance: YCrCb Color Gamut Analysis ───────────────
            color_status = "pass"
            ycrcb = cv2.cvtColor(primary_crop, cv2.COLOR_BGR2YCrCb)
            _, cr, cb = cv2.split(ycrcb)
            cr_var = float(np.var(cr))
            cb_var = float(np.var(cb))
            color_dispersion = float(np.sqrt(cr_var + cb_var))
            signals["chroma_dispersion"] = round(color_dispersion, 3)

            # Paper prints tend to have compressed or unnatural chrominance clustering
            if color_dispersion < 4.0:
                color_status = "suspected_spoof"
            elif color_dispersion < 7.0:
                color_status = "inconclusive"

            # ── 3. Glare & Specular Reflection Analysis (HSV) ────────────
            glare_status = "pass"
            hsv = cv2.cvtColor(primary_crop, cv2.COLOR_BGR2HSV)
            _, s_ch, v_ch = cv2.split(hsv)
            glare_mask = (v_ch > 235) & (s_ch < 40)
            glare_pct = float(np.sum(glare_mask) / (h * w) * 100.0)
            signals["glare_percentage"] = round(glare_pct, 2)

            if glare_pct > 14.0:
                glare_status = "suspected_spoof"
            elif glare_pct > 7.0:
                glare_status = "inconclusive"

            # ── 4. Temporal Micro-Movement Analysis ──────────────────────
            temp_status = "pass"
            if sequence_crops and len(sequence_crops) >= 2:
                diffs = []
                base_gray = cv2.resize(gray, (160, 160))
                for seq_crop in sequence_crops:
                    if seq_crop is not None and seq_crop.size > 0:
                        s_gray = cv2.resize(cv2.cvtColor(seq_crop, cv2.COLOR_BGR2GRAY), (160, 160))
                        diff = float(np.mean(np.abs(base_gray.astype(float) - s_gray.astype(float))))
                        diffs.append(diff)
                if diffs:
                    mean_diff = float(np.mean(diffs))
                    signals["temporal_mean_diff"] = round(mean_diff, 3)
                    # Completely zero motion indicates static print photograph held before camera
                    if mean_diff < 0.25:
                        temp_status = "suspected_spoof"
                    elif mean_diff > 45.0:
                        # Massive shift indicates heavy camera shaking or framing error
                        temp_status = "inconclusive"
            else:
                signals["temporal_frames"] = 1.0

            # Explanatory summary
            issues = []
            if freq_status == "suspected_spoof":
                issues.append("screen moiré detected in frequency domain")
            if color_status == "suspected_spoof":
                issues.append("restricted chrominance gamut (possible paper print)")
            if glare_status == "suspected_spoof":
                issues.append("excessive specular glass/laminate glare")
            if temp_status == "suspected_spoof":
                issues.append("near-zero temporal variance across frames (static 2D presentation)")

            summary = "All secondary optical telemetry normal." if not issues else "; ".join(issues)

            return SecondaryPADResult(
                frequency_domain=freq_status,
                texture_analysis=color_status,
                specular_glare=glare_status,
                temporal_variance=temp_status,
                signals=signals,
                summary=summary,
            )
        except Exception as exc:
            logger.warning("Secondary optical telemetry calculation failed: %s", exc)
            return SecondaryPADResult(
                frequency_domain="inconclusive",
                texture_analysis="inconclusive",
                specular_glare="inconclusive",
                temporal_variance="inconclusive",
                summary=f"Optical telemetry error: {exc}",
            )
