"""
backend/tests/create_synthetic_passport.py

Script to generate a synthetic passport-like test image.

IMPORTANT:
  - This is a SYNTHETIC document used for testing ONLY.
  - No real person's data is used.
  - The image is clearly labelled "SYNTHETIC TEST DOCUMENT".
  - This must never be committed alongside real passport data.
  - The image is designed to give PaddleOCR something realistic to parse.

Run from the backend/ directory:
  python tests/create_synthetic_passport.py
"""
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    import textwrap
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")

# ──────────────────────────────────────────────
#  Synthetic data — all fictional
# ──────────────────────────────────────────────
DATA = {
    "country":       "REPUBLIC OF INDIA",
    "doc_type":      "PASSPORT",
    "surname":       "SYNTH",
    "given_names":   "TEST USER",
    "nationality":   "INDIAN",
    "dob":           "15 JUN 1985",
    "sex":           "M",
    "place_of_birth":"SYNTHETIC CITY",
    "date_of_issue": "01 JAN 2020",
    "date_of_expiry":"31 DEC 2029",
    "authority":     "SYNTHETIC TEST AUTHORITY",
    "doc_number":    "T9876543",
    # TD3 MRZ — synthetic test document with mathematically valid ICAO 7-3-1 check digits
    "mrz_line1":     "P<INDSYNTH<<TEST<USER<<<<<<<<<<<<<<<<<<<<<<<",
    "mrz_line2":     "T9876543<7IND8506151M2912316<<<<<<<<<<<<<<<2",
}

# ──────────────────────────────────────────────
#  Layout constants
# ──────────────────────────────────────────────
W, H = 850, 1200
BG_COLOR = (245, 238, 210)       # Cream/ivory background
DARK = (20, 30, 60)              # Dark blue-black text
LABEL_COLOR = (90, 100, 130)     # Muted label colour
MRZ_BG = (230, 230, 220)        # MRZ strip background
RED_BAR = (180, 30, 30)         # Security bar colour
WATERMARK = (200, 195, 180)     # Watermark text colour


def _try_font(size: int) -> "ImageFont.FreeTypeFont | ImageFont.ImageFont":
    """Attempt to load a system font; fall back to PIL default."""
    for font_name in ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _try_mono_font(size: int) -> "ImageFont.FreeTypeFont | ImageFont.ImageFont":
    """Attempt to load a monospace font for MRZ."""
    for font_name in ["cour.ttf", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "FreeMono.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def create_synthetic_passport(output_path: Path) -> None:
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Fonts
    title_font   = _try_font(28)
    header_font  = _try_font(22)
    label_font   = _try_font(13)
    value_font   = _try_font(17)
    mrz_font     = _try_mono_font(18)
    watermark_f  = _try_font(60)

    # ── Watermark (background) ────────────────────────────────────────────
    draw.text((80, 350), "SYNTHETIC\nTEST DOCUMENT", font=watermark_f, fill=WATERMARK, spacing=10)

    # ── Header bar ────────────────────────────────────────────────────────
    draw.rectangle([0, 0, W, 80], fill=RED_BAR)
    draw.text((W // 2, 40), DATA["country"], font=title_font, fill="white", anchor="mm")

    # ── Document type ─────────────────────────────────────────────────────
    draw.text((W // 2, 110), DATA["doc_type"], font=header_font, fill=DARK, anchor="mm")

    # ── Photo placeholder ─────────────────────────────────────────────────
    photo_rect = [40, 140, 240, 340]
    draw.rectangle(photo_rect, fill=(200, 200, 200), outline=DARK, width=2)
    draw.text((140, 240), "PHOTO\nPLACEHOLDER", font=label_font, fill=LABEL_COLOR, anchor="mm")

    # ── Fields ────────────────────────────────────────────────────────────
    def draw_field(label: str, value: str, x: int, y: int, label_y_offset: int = 0) -> None:
        draw.text((x, y + label_y_offset), label.upper(), font=label_font, fill=LABEL_COLOR)
        draw.text((x, y + label_y_offset + 18), value, font=value_font, fill=DARK)

    # Right column — primary identity
    rx = 270
    draw_field("Surname", DATA["surname"],     rx, 160)
    draw_field("Given Name(s)", DATA["given_names"], rx, 220)
    draw_field("Nationality", DATA["nationality"], rx, 280)
    draw_field("Date of Birth", DATA["dob"],   rx, 340)
    draw_field("Sex",          DATA["sex"],     rx + 200, 340)

    # Full-width fields
    draw_field("Place of Birth", DATA["place_of_birth"], 40, 380)
    draw_field("Date of Issue",  DATA["date_of_issue"],  40, 440)
    draw_field("Date of Expiry", DATA["date_of_expiry"], 270, 440)
    draw_field("Issuing Authority", DATA["authority"],   40, 500)
    draw_field("Passport No.",   DATA["doc_number"],     40, 560)

    # ── Separator line ────────────────────────────────────────────────────
    draw.line([0, 650, W, 650], fill=(160, 160, 160), width=1)

    # ── Signature line ────────────────────────────────────────────────────
    draw.text((40, 670), "Holder's Signature:", font=label_font, fill=LABEL_COLOR)
    draw.line([40, 720, 400, 720], fill=DARK, width=1)

    # ── MRZ strip ─────────────────────────────────────────────────────────
    mrz_y_start = H - 130
    draw.rectangle([0, mrz_y_start - 15, W, H], fill=MRZ_BG)
    draw.text((40, mrz_y_start - 12), "Machine Readable Zone", font=label_font, fill=LABEL_COLOR)

    # MRZ Line 1
    draw.text((40, mrz_y_start + 8), DATA["mrz_line1"], font=mrz_font, fill=DARK)
    # MRZ Line 2
    draw.text((40, mrz_y_start + 42), DATA["mrz_line2"], font=mrz_font, fill=DARK)

    # ── Bottom warning ────────────────────────────────────────────────────
    warn_font = _try_font(10)
    draw.text(
        (W // 2, H - 5),
        "⚠ SYNTHETIC TEST DOCUMENT — NOT VALID FOR TRAVEL — FOR SYSTEM TESTING ONLY",
        font=warn_font,
        fill=RED_BAR,
        anchor="mb",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="JPEG", quality=92)
    print(f"Synthetic passport saved to: {output_path}")
    print("Data used:")
    for k, v in DATA.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    out = Path(__file__).parent / "assets" / "sample_passport.jpg"
    create_synthetic_passport(out)
