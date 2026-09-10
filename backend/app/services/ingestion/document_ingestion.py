"""
backend/app/services/ingestion/document_ingestion.py

Validates and decodes an uploaded document file.

Responsibilities:
  1. Check file size against configured limit
  2. Verify MIME type against allow-list (checks magic bytes, not just extension)
  3. Decode image bytes to confirm it is a valid, readable image
  4. Return both raw bytes (for storage/forensics) and decoded numpy array

This layer does NOT perform OCR — it only ensures the data is safe to pass
to the OCR pipeline.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

# Security Hardening: Decompression bomb protection
# Limit maximum pixel count to prevent denial-of-service via decompression bombs.
Image.MAX_IMAGE_PIXELS = 50_000_000

from app.core.config import settings
from app.core.exceptions import (
    DocumentIngestionError,
    FileTooLargeError,
    UnsupportedFormatError,
)

logger = logging.getLogger(__name__)

# Magic-byte signatures for accepted image types
# We check the actual file content, not just the filename or Content-Type header.
_MAGIC_BYTES: dict[bytes, str] = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    # WEBP: 'RIFF' at offset 0 and 'WEBP' at offset 8
}


def _detect_mime_from_bytes(raw: bytes) -> str | None:
    """Return detected MIME type from magic bytes, or None if unrecognised."""
    for magic, mime in _MAGIC_BYTES.items():
        if raw.startswith(magic):
            return mime
    # WEBP: special check
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


class IngestedDocument:
    """Container for the result of successful document ingestion."""

    __slots__ = ("raw_bytes", "image_np", "detected_mime", "filename")

    def __init__(
        self,
        raw_bytes: bytes,
        image_np: np.ndarray,
        detected_mime: str,
        filename: str,
    ) -> None:
        self.raw_bytes = raw_bytes
        self.image_np = image_np          # BGR numpy array (OpenCV convention)
        self.detected_mime = detected_mime
        self.filename = filename


async def ingest_document(
    raw_bytes: bytes,
    declared_mime: str,
    filename: str,
) -> IngestedDocument:
    """
    Validate and decode an uploaded document file.

    Args:
        raw_bytes:      Raw file content from the HTTP multipart upload.
        declared_mime:  Content-Type header value declared by the client.
        filename:       Original filename (for logging only — NOT trusted for type).

    Returns:
        IngestedDocument with raw bytes and decoded numpy image array.

    Raises:
        FileTooLargeError:      File exceeds MAX_FILE_SIZE_MB.
        UnsupportedFormatError: MIME type not in allow-list.
        DocumentIngestionError: Image cannot be decoded.
    """
    # 1. File size check
    size_mb = len(raw_bytes) / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        logger.warning(
            "Rejected oversized upload: %.2f MB (limit %d MB) — %s",
            size_mb, settings.MAX_FILE_SIZE_MB, filename,
        )
        raise FileTooLargeError(
            f"File size {size_mb:.1f} MB exceeds the {settings.MAX_FILE_SIZE_MB} MB limit."
        )

    # 2. Detect MIME from magic bytes (do not trust client declaration alone)
    detected_mime = _detect_mime_from_bytes(raw_bytes)
    if detected_mime is None:
        logger.warning("Unrecognised magic bytes for file: %s", filename)
        raise UnsupportedFormatError(
            f"Unrecognised file format. Accepted types: "
            f"{', '.join(sorted(settings.ALLOWED_MIME_TYPES))}."
        )

    if detected_mime not in settings.ALLOWED_MIME_TYPES:
        logger.warning("Rejected MIME type %s for file: %s", detected_mime, filename)
        raise UnsupportedFormatError(
            f"File type '{detected_mime}' is not accepted. "
            f"Please upload a JPEG, PNG, or WEBP image."
        )

    # 3. Decode image with PIL first (handles EXIF, WEBP, etc.)
    try:
        pil_image = Image.open(io.BytesIO(raw_bytes))
        pil_image.verify()  # Verify without loading pixel data
        # Re-open after verify (verify() consumes the file pointer)
        pil_image = Image.open(io.BytesIO(raw_bytes))
        # Apply EXIF orientation (phone cameras store rotation as metadata,
        # not as pixel data) before any downstream processing sees the array.
        pil_image = ImageOps.exif_transpose(pil_image)
        pil_image = pil_image.convert("RGB")
    except Exception as exc:
        logger.warning("PIL failed to decode image '%s': %s", filename, exc)
        raise DocumentIngestionError(
            "Unable to decode the uploaded image. "
            "Please upload a clear, uncorrupted JPEG, PNG, or WEBP file."
        ) from exc

    # 4. Convert to OpenCV BGR numpy array for the preprocessing/OCR pipeline
    try:
        image_np = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    except Exception as exc:
        logger.error("OpenCV conversion failed for '%s': %s", filename, exc)
        raise DocumentIngestionError(
            "Image conversion failed. Please try a different file."
        ) from exc

    logger.info(
        "Document ingested: %s | detected=%s | size=%.2f MB | shape=%s",
        filename, detected_mime, size_mb, image_np.shape,
    )

    return IngestedDocument(
        raw_bytes=raw_bytes,
        image_np=image_np,
        detected_mime=detected_mime,
        filename=filename,
    )
