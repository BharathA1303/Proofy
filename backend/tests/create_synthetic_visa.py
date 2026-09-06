"""
backend/tests/create_synthetic_visa.py

Script to generate a synthetic Visa test image for testing and the frontend sample loader.

IMPORTANT:
  - This is a SYNTHETIC document used for testing ONLY.
  - No real person's data is used.
  - The image is clearly labelled "SYNTHETIC TEST VISA".
  - Fictional data matching deterministic mock registry records.
"""
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")

# ──────────────────────────────────────────────
#  Synthetic Visa Data
# ──────────────────────────────────────────────
DATA = {
    "title":         "ENTRY VISA",
    "country":       "DEMO BORDER JURISDICTION",
    "visa_number":   "TESTVISA001",
    "passport_num":  "T9876543",
    "name":          "TEST USER",
    "nationality":   "IND",
    "dob":           "15 JUN 1985",
    "visa_type":     "TOURIST",
    "issue_date":    "01 JAN 2020",
    "expiry_date":   "31 DEC 2029",
    "entries":       "MULTIPLE",
    "duration":      "90 DAYS",
    "authority":     "CONSULAR POST SYNTHETIC",
}

W, H = 850, 1100
BG_COLOR = (248, 246, 238)      # Pale parchment/cream
DARK = (20, 30, 60)             # High contrast dark text
LABEL_COLOR = (90, 100, 130)    # Blue-grey label text
HEADER_BG = (220, 230, 245)     # Subtle header banner
BAR_COLOR = (40, 80, 160)       # Deep blue decorative band


def _try_font(size: int) -> "ImageFont.FreeTypeFont | ImageFont.ImageFont":
    for font_name in ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def create_synthetic_visa(output_path: Path) -> Path:
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    f_large = _try_font(28)
    f_title = _try_font(22)
    f_bold  = _try_font(18)
    f_label = _try_font(13)
    f_val   = _try_font(17)
    f_mono  = _try_font(19)

    # 1. Outer Border & Security Guilloche Pattern Simulation
    draw.rectangle([15, 15, W - 15, H - 15], outline=(180, 190, 210), width=3)
    draw.rectangle([22, 22, W - 22, H - 22], outline=(210, 220, 235), width=1)

    # 2. Header Banner
    draw.rectangle([25, 25, W - 25, 120], fill=HEADER_BG)
    draw.rectangle([25, 120, W - 25, 126], fill=BAR_COLOR)
    draw.text((W // 2, 45), DATA["country"], font=f_title, fill=DARK, anchor="mm")
    draw.text((W // 2, 85), DATA["title"], font=f_large, fill=BAR_COLOR, anchor="mm")

    # Watermark / Notice
    draw.text((W // 2, 145), "— SYNTHETIC TEST VISA (OFFICIAL SPECIMEN) —", font=f_label, fill=(160, 60, 60), anchor="mm")

    # 3. Portrait Placeholder Frame (Left side)
    px0, py0, px1, py1 = 50, 180, 260, 440
    draw.rectangle([px0, py0, px1, py1], fill=(230, 235, 240), outline=(160, 170, 190), width=2)
    draw.ellipse([px0 + 50, py0 + 40, px1 - 50, py0 + 150], fill=(190, 200, 215))  # Head
    draw.ellipse([px0 + 20, py0 + 140, px1 - 20, py1 + 80], fill=(170, 180, 200))  # Shoulders
    draw.text(((px0 + px1) // 2, py1 - 25), "PHOTO SPECIMEN", font=f_label, fill=(100, 110, 130), anchor="mm")

    # 4. Visa Number Highlight Box (Top right)
    draw.rectangle([300, 180, W - 50, 240], fill=(240, 245, 255), outline=BAR_COLOR, width=2)
    draw.text((315, 190), "VISA NUMBER / CONTROL NO", font=f_label, fill=LABEL_COLOR)
    draw.text((315, 210), DATA["visa_number"], font=f_large, fill=(180, 30, 30))

    # 5. Core Identity & Travel Document Fields
    y = 260
    fields_left = [
        ("PASSPORT NO / PPT NO", DATA["passport_num"]),
        ("BEARER NAME / FULL NAME", DATA["name"]),
        ("DATE OF BIRTH / DOB", DATA["dob"]),
        ("NATIONALITY", DATA["nationality"]),
    ]

    for lbl, val in fields_left:
        draw.text((300, y), lbl, font=f_label, fill=LABEL_COLOR)
        draw.text((300, y + 20), val, font=f_val, fill=DARK)
        draw.line([300, y + 45, W - 50, y + 45], fill=(225, 230, 240), width=1)
        y += 55

    # 6. Visa Grant & Validity Parameters Grid
    y_grid = 480
    grid_items = [
        ("VISA TYPE", DATA["visa_type"], 50),
        ("ENTRIES", DATA["entries"], 300),
        ("DURATION OF STAY", DATA["duration"], 550),
        ("ISSUE DATE / VALID FROM", DATA["issue_date"], 50),
        ("EXPIRY DATE / VALID UNTIL", DATA["expiry_date"], 300),
        ("ISSUING POST / AUTHORITY", DATA["authority"], 50),
    ]

    draw.text((50, y_grid), "VISA TYPE / CLASS", font=f_label, fill=LABEL_COLOR)
    draw.text((50, y_grid + 20), DATA["visa_type"], font=f_bold, fill=DARK)

    draw.text((320, y_grid), "NO OF ENTRIES", font=f_label, fill=LABEL_COLOR)
    draw.text((320, y_grid + 20), DATA["entries"], font=f_bold, fill=DARK)

    draw.text((560, y_grid), "DURATION OF STAY", font=f_label, fill=LABEL_COLOR)
    draw.text((560, y_grid + 20), DATA["duration"], font=f_bold, fill=DARK)

    y_grid += 65
    draw.text((50, y_grid), "ISSUE DATE / VALID FROM", font=f_label, fill=LABEL_COLOR)
    draw.text((50, y_grid + 20), DATA["issue_date"], font=f_bold, fill=DARK)

    draw.text((320, y_grid), "EXPIRY DATE / VALID UNTIL", font=f_label, fill=LABEL_COLOR)
    draw.text((320, y_grid + 20), DATA["expiry_date"], font=f_bold, fill=(180, 20, 20))

    y_grid += 65
    draw.text((50, y_grid), "ISSUING AUTHORITY", font=f_label, fill=LABEL_COLOR)
    draw.text((50, y_grid + 20), DATA["authority"], font=f_val, fill=DARK)

    # 7. Security Notice & Footer
    draw.rectangle([50, 700, W - 50, 770], fill=(240, 240, 240), outline=(200, 200, 200), width=1)
    draw.text((70, 715), "SECURITY NOTICE:", font=f_bold, fill=DARK)
    draw.text((70, 738), "Credential issued strictly under reference travel document authority. Holder must present matching passport.", font=f_label, fill=(80, 80, 80))

    # 8. Optional MRV Optical Strip at bottom
    draw.rectangle([30, 840, W - 30, 1020], fill=(235, 235, 225), outline=(190, 190, 180), width=1)
    draw.text((45, 850), "MACHINE READABLE VISA STRIP (MRV-A)", font=f_label, fill=LABEL_COLOR)

    mrv_line1 = "V<INDTEST<<USER<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    mrv_line2 = "TESTVISA01<7IND8506151M2912316T9876543<<<<<<0"
    draw.text((45, 885), mrv_line1, font=f_mono, fill=DARK)
    draw.text((45, 935), mrv_line2, font=f_mono, fill=DARK)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "JPEG", quality=95)
    return output_path


if __name__ == "__main__":
    out = Path(__file__).parent / "assets" / "sample_visa.jpg"
    create_synthetic_visa(out)
    print(f"Synthetic test visa saved to: {out}")
