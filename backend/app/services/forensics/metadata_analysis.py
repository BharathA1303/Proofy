"""
backend/app/services/forensics/metadata_analysis.py

Module 3: Image Metadata Analysis.

Inspects EXIF metadata where present (software/encoder tag, dimensions,
timestamps). Absence of metadata is explicitly NOT treated as evidence of
tampering — metadata is routinely stripped by messaging apps, screenshot
tools, and legitimate re-encoding pipelines.

status values:
  "available"    — EXIF metadata was found and looks internally consistent
  "absent"       — no EXIF metadata found (common and NOT suspicious alone)
  "suspicious"   — metadata is present but internally inconsistent
                    (e.g. modify time before create time) or names a known
                    general-purpose image editor
  "inconclusive" — metadata could not be parsed
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ExifTags

logger = logging.getLogger(__name__)

# General-purpose raster editors. Presence alone is a very weak signal —
# scans and phone photos are also routinely reprocessed by legitimate
# document-management software.
_EDITOR_SOFTWARE_MARKERS = ("photoshop", "gimp", "paint.net")

_TAG_NAMES = {v: k for k, v in ExifTags.TAGS.items()}


@dataclass
class MetadataResult:
    status: str  # "available" | "absent" | "suspicious" | "inconclusive"
    severity: str  # "low" | "medium"
    confidence: float
    fields_present: list[str] = field(default_factory=list)
    description: str = ""


def analyze_metadata(raw_bytes: bytes) -> MetadataResult:
    try:
        pil_image = Image.open(io.BytesIO(raw_bytes))
        exif = pil_image.getexif()
    except Exception as exc:
        logger.warning("Metadata parsing failed (non-fatal): %s", exc)
        return MetadataResult(
            status="inconclusive",
            severity="low",
            confidence=0.3,
            description="Image metadata could not be parsed.",
        )

    if not exif or len(exif) == 0:
        return MetadataResult(
            status="absent",
            severity="low",
            confidence=0.6,
            description=(
                "No EXIF metadata was found. This is common for screenshots, "
                "messaging-app transfers, and re-encoded images, and is NOT by "
                "itself an indicator of tampering."
            ),
        )

    fields_present = [ExifTags.TAGS.get(tag_id, str(tag_id)) for tag_id in exif.keys()]
    software_tag = exif.get(_TAG_NAMES.get("Software"), "") if _TAG_NAMES.get("Software") else ""
    software_tag = str(software_tag).lower()

    datetime_original = exif.get(_TAG_NAMES.get("DateTimeOriginal"))
    datetime_modified = exif.get(_TAG_NAMES.get("DateTime"))

    suspicious_reasons: list[str] = []

    if any(marker in software_tag for marker in _EDITOR_SOFTWARE_MARKERS):
        suspicious_reasons.append(
            f"Software tag references a general-purpose image editor ('{software_tag}')."
        )

    if datetime_original and datetime_modified and datetime_modified < datetime_original:
        suspicious_reasons.append(
            "Modification timestamp precedes the original capture timestamp."
        )

    if suspicious_reasons:
        return MetadataResult(
            status="suspicious",
            severity="medium",
            confidence=0.55,
            fields_present=fields_present,
            description=(
                "Metadata is present but shows characteristics worth reviewing: "
                + " ".join(suspicious_reasons)
                + " This does not by itself prove tampering."
            ),
        )

    return MetadataResult(
        status="available",
        severity="low",
        confidence=0.6,
        fields_present=fields_present,
        description="EXIF metadata is present and shows no internal inconsistencies.",
    )
