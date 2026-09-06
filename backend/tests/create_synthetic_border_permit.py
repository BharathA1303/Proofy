"""
backend/tests/create_synthetic_border_permit.py

Script to generate a synthetic Border Permit test image for testing and the frontend sample loader.

IMPORTANT:
  - This is a SYNTHETIC document used for testing ONLY.
  - No real person's data is used.
  - The image is clearly labelled "SYNTHETIC TEST BORDER PERMIT".
  - Fictional data matching deterministic mock registry records.
"""
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")

PERMIT_NUMBER = "BP-2026-000123"
HOLDER_NAME = "ALEX DUPONT"
PASSPORT_NUMBER = "P1234567"
DOB = "12-08-1990"
VALID_FROM = "01-01-2026"
VALID_TO = "31-12-2026"
PERMIT_TYPE = "ENTRY"
PORT_OF_ENTRY = "NORTH GATE TERMINAL"
ISSUING_AUTHORITY = "Border Management Authority"


def create_synthetic_border_permit_image(output_path: Path) -> Path:
    """
    Generate a high-resolution synthetic Border Permit card.
    Dimensions: 850 x 540 (standard ID-1 card aspect ratio).
    """
    width = 850
    height = 540

    img = Image.new("RGB", (width, height), color=(242, 246, 250))
    draw = ImageDraw.Draw(img)

    # 1. Background borders and card design
    # Header background band (deep blue/teal border authority color)
    draw.rectangle([(0, 0), (width, 85)], fill=(20, 55, 90))

    # Warning banner (top ribbon)
    draw.rectangle([(0, 0), (width, 22)], fill=(210, 50, 45))
    draw.text((width // 2 - 130, 4), "SYNTHETIC TEST BORDER PERMIT", fill=(255, 255, 255))

    # Header titles
    draw.text((30, 28), "REGIONAL BORDER CONTROL", fill=(220, 235, 250))
    draw.text((30, 50), "OFFICIAL ENTRY & CROSSING PERMIT", fill=(255, 255, 255))

    # 2. Portrait placeholder (left side)
    photo_box = [(40, 115), (250, 395)]
    draw.rectangle(photo_box, fill=(215, 225, 235), outline=(100, 130, 160), width=2)
    draw.text((65, 240), "[ PHOTO / PORTRAIT ]", fill=(90, 110, 130))
    draw.text((80, 265), "SYNTHETIC", fill=(120, 140, 160))

    # 3. Main Data Fields (center & right)
    start_x = 285
    start_y = 110
    line_h = 42

    fields = [
        ("PERMIT NO:", PERMIT_NUMBER),
        ("HOLDER NAME:", HOLDER_NAME),
        ("DATE OF BIRTH:", DOB),
        ("LINKED PASSPORT NO:", PASSPORT_NUMBER),
        ("PERMIT TYPE:", PERMIT_TYPE),
        ("PORT OF ENTRY:", PORT_OF_ENTRY),
        ("VALID FROM:", VALID_FROM),
        ("VALID TO:", VALID_TO),
        ("ISSUING AUTHORITY:", ISSUING_AUTHORITY),
    ]

    for idx, (lbl, val) in enumerate(fields):
        y = start_y + (idx * line_h)
        if idx >= 6:  # lower fields shifted or compressed slightly
            y = start_y + (idx * 38)
        draw.text((start_x, y), lbl, fill=(70, 90, 110))
        draw.text((start_x + 185, y), val, fill=(15, 25, 35))

    # 4. QR Code simulated pattern (bottom right)
    qr_box = [(670, 375), (820, 515)]
    draw.rectangle(qr_box, fill=(255, 255, 255), outline=(50, 70, 90), width=2)
    # Draw simulated finder patterns (3 corner squares)
    draw.rectangle([(680, 385), (715, 420)], fill=(0, 0, 0))
    draw.rectangle([(687, 392), (708, 413)], fill=(255, 255, 255))
    draw.rectangle([(692, 397), (703, 408)], fill=(0, 0, 0))

    draw.rectangle([(775, 385), (810, 420)], fill=(0, 0, 0))
    draw.rectangle([(782, 392), (803, 413)], fill=(255, 255, 255))
    draw.rectangle([(787, 397), (798, 408)], fill=(0, 0, 0))

    draw.rectangle([(680, 470), (715, 505)], fill=(0, 0, 0))
    draw.rectangle([(687, 477), (708, 498)], fill=(255, 255, 255))
    draw.rectangle([(692, 482), (703, 493)], fill=(0, 0, 0))

    # Center label in QR
    draw.text((725, 440), "QR", fill=(0, 0, 0))

    # 5. Security guilloche / microprint lines along bottom
    draw.line([(0, height - 35), (width, height - 35)], fill=(180, 200, 220), width=1)
    draw.line([(0, height - 30), (width, height - 30)], fill=(180, 200, 220), width=1)
    draw.text(
        (40, height - 24),
        "SECURE BORDER ENTRY DOCUMENT — FOR TESTING & DEMONSTRATION PURPOSES ONLY",
        fill=(120, 140, 160),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=95)
    return output_path


if __name__ == "__main__":
    out = Path(__file__).parent / "assets" / "sample_border_permit.jpg"
    create_synthetic_border_permit_image(out)
    print(f"Generated synthetic Border Permit asset at: {out}")
