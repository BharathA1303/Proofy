"""
backend/tests/forensic_test_utils.py

Synthetic image generators shared by Module 3 forensic tests.

IMPORTANT: All images here are procedurally generated. No real person's
document, photograph, or passport number is used anywhere in these tests.
"""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def make_textured_image(width: int = 900, height: int = 1200, seed: int = 42) -> np.ndarray:
    """A deterministic, textured (non-uniform) BGR image resembling a document page."""
    rng = _rng(seed)
    base = np.full((height, width, 3), 235, dtype=np.uint8)
    noise = rng.normal(0, 8, (height, width, 3))
    img = np.clip(base.astype(np.float64) + noise, 0, 255).astype(np.uint8)

    # A few horizontal "text-like" bands to add high-frequency content.
    for y in range(180, height - 150, 60):
        cv2.line(img, (60, y), (width - 60, y), (30, 30, 30), 2)

    return img


def add_passport_photo_rect(img: np.ndarray, x=60, y=160, w=220, h=220) -> np.ndarray:
    """Draw a solid rectangular 'photo' with a clear border, like a passport bio-page photo."""
    out = img.copy()
    cv2.rectangle(out, (x, y), (x + w, y + h), (150, 150, 150), thickness=-1)
    cv2.rectangle(out, (x, y), (x + w, y + h), (20, 20, 20), thickness=2)
    return out


def add_altered_photo_boundary(img: np.ndarray, x=60, y=160, w=220, h=220) -> np.ndarray:
    """
    A photo region whose interior is perfectly flat (no texture) but whose
    immediate surroundings carry heavy artificial edge noise — simulating a
    replaced/pasted photo with a visible splice boundary.
    """
    out = img.copy()
    # Flat interior (near-zero local variance)
    cv2.rectangle(out, (x, y), (x + w, y + h), (150, 150, 150), thickness=-1)

    # Heavy checkerboard noise in a ring immediately outside the rectangle
    ring = 18
    x0, y0 = max(x - ring, 0), max(y - ring, 0)
    x1, y1 = min(x + w + ring, out.shape[1]), min(y + h + ring, out.shape[0])
    rng = _rng(7)
    checker = (rng.integers(0, 2, (y1 - y0, x1 - x0)) * 255).astype(np.uint8)
    checker_bgr = cv2.cvtColor(checker, cv2.COLOR_GRAY2BGR)
    out[y0:y1, x0:x1] = checker_bgr

    # Re-draw the flat interior on top so only the boundary ring is noisy.
    cv2.rectangle(out, (x, y), (x + w, y + h), (150, 150, 150), thickness=-1)
    return out


def encode_jpeg(img_bgr: np.ndarray, quality: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return buf.tobytes()


def decode_jpeg(jpeg_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def recompress_region(img_bgr: np.ndarray, box: tuple[int, int, int, int], quality: int) -> np.ndarray:
    """Recompress only the given (x, y, w, h) region at a different JPEG quality and paste it back."""
    x, y, w, h = box
    out = img_bgr.copy()
    crop = out[y:y + h, x:x + w]
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    recompressed_crop = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    out[y:y + h, x:x + w] = recompressed_crop
    return out


def make_blurred(img_bgr: np.ndarray, ksize: int = 25) -> np.ndarray:
    return cv2.GaussianBlur(img_bgr, (ksize, ksize), 0)


def make_dark(img_bgr: np.ndarray, factor: float = 0.08) -> np.ndarray:
    return np.clip(img_bgr.astype(np.float64) * factor, 0, 255).astype(np.uint8)


def make_tiny(img_bgr: np.ndarray, size=(80, 100)) -> np.ndarray:
    return cv2.resize(img_bgr, size, interpolation=cv2.INTER_AREA)


def pil_jpeg_bytes_with_exif(img_bgr: np.ndarray, software: str | None = None) -> bytes:
    """Build JPEG bytes carrying a minimal EXIF block (optionally with a Software tag)."""
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    buf = io.BytesIO()

    exif = pil_img.getexif()
    if software is not None:
        # 0x0131 == Software tag
        exif[0x0131] = software
    else:
        # 0x0132 == DateTime tag, just to guarantee a non-empty EXIF block
        exif[0x0132] = "2024:01:01 10:00:00"

    pil_img.save(buf, format="JPEG", quality=90, exif=exif)
    return buf.getvalue()


def pil_jpeg_bytes_no_exif(img_bgr: np.ndarray) -> bytes:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
