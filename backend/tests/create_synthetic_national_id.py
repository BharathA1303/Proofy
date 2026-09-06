"""
backend/tests/create_synthetic_national_id.py

Script to generate a synthetic National ID test image for testing and the frontend sample loader.

IMPORTANT:
  - This is a SYNTHETIC document used for testing ONLY.
  - No real person's data is used.
  - The image is clearly labelled "SYNTHETIC TEST NATIONAL ID".
  - Fictional data matching deterministic mock registry records.
"""
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")

# Dihedral group D5 multiplication table
VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

# Permutation table
VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def compute_check_digit(num11: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(num11)):
        c = VERHOEFF_D[c][VERHOEFF_P[(i + 1) % 8][int(ch)]]
    return str(VERHOEFF_INV[c])


# 11-digit prefix: 98765432109 -> check digit
_prefix = "98765432109"
_chk = compute_check_digit(_prefix)
VALID_12_DIGIT_ID = _prefix + _chk
FORMATTED_ID = f"{VALID_12_DIGIT_ID[:4]} {VALID_12_DIGIT_ID[4:8]} {VALID_12_DIGIT_ID[8:]}"

DATA = {
    "header_en":     "GOVERNMENT OF INDIA",
    "header_hi":     "BHARAT SARKAR",
    "authority":     "Unique Identification Authority of India",
    "name":          "RAHUL SHARMA",
    "dob":           "15/05/1992",
    "gender":        "MALE",
    "id_number":     FORMATTED_ID,
    "address":       "123 CONNAUGHT PLACE, NEW DELHI, 110001",
}

W, H = 850, 540
BG_COLOR = (255, 255, 255)
DARK = (15, 23, 42)
LABEL_COLOR = (71, 85, 105)
SAFFRON = (255, 153, 51)
NAVY = (0, 0, 128)
GREEN = (19, 136, 8)
BORDER_COLOR = (203, 213, 225)


def _try_font(size: int):
    for font_name in ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def create_synthetic_national_id(output_path: Path) -> Path:
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    f_large = _try_font(22)
    f_title = _try_font(18)
    f_val = _try_font(16)
    f_lbl = _try_font(12)
    f_id = _try_font(26)
    f_small = _try_font(11)

    # 1. Outer border
    draw.rectangle([(8, 8), (W - 8, H - 8)], outline=BORDER_COLOR, width=2)

    # 2. Header Band: Saffron-White-Green tricolor top accent lines
    draw.rectangle([(8, 8), (W - 8, 16)], fill=SAFFRON)
    draw.rectangle([(8, 16), (W - 8, 24)], fill=(255, 255, 255))
    draw.rectangle([(8, 24), (W - 8, 32)], fill=GREEN)

    # Header text
    draw.text((W // 2, 50), DATA["header_en"], fill=DARK, font=f_large, anchor="mm")
    draw.text((W // 2, 75), DATA["authority"], fill=NAVY, font=f_lbl, anchor="mm")
    draw.line([(30, 95), (W - 30, 95)], fill=(226, 232, 240), width=1)

    # 3. Photo area (Left)
    px, py, pw, ph = 40, 115, 150, 190
    draw.rectangle([(px, py), (px + pw, py + ph)], fill=(241, 245, 249), outline=(148, 163, 184), width=2)
    draw.ellipse([(px + 40, py + 25), (px + 110, py + 95)], fill=(148, 163, 184))
    draw.ellipse([(px + 15, py + 105), (px + 135, py + 215)], fill=(148, 163, 184))
    draw.text((px + pw // 2, py + ph - 20), "PHOTO", fill=(71, 85, 105), font=f_lbl, anchor="mm")

    # 4. Text Fields (Center)
    fx = 220
    y = 120
    spacing = 45

    # Name
    draw.text((fx, y), "Name:", fill=LABEL_COLOR, font=f_lbl)
    draw.text((fx, y + 15), DATA["name"], fill=DARK, font=f_val)

    # DOB
    draw.text((fx, y + spacing), "DOB: " + DATA["dob"], fill=DARK, font=f_val)

    # Gender
    draw.text((fx, y + spacing * 2), "Gender: " + DATA["gender"], fill=DARK, font=f_val)

    # Address snippet
    draw.text((fx, y + spacing * 3), "Address: " + DATA["address"], fill=LABEL_COLOR, font=f_lbl)

    # 5. QR Code Placeholder (Right)
    qx, qy, qw, qh = 620, 115, 170, 170
    draw.rectangle([(qx, qy), (qx + qw, qy + qh)], fill=(248, 250, 252), outline=(100, 116, 139), width=2)
    # Draw simple grid pattern representing QR
    for i in range(qx + 15, qx + qw - 15, 20):
        for j in range(qy + 15, qy + qh - 15, 20):
            if (i + j) % 40 == 0:
                draw.rectangle([(i, j), (i + 12, j + 12)], fill=(30, 41, 59))
    draw.rectangle([(qx + 10, qy + 10), (qx + 35, qy + 35)], outline=(30, 41, 59), width=3)
    draw.rectangle([(qx + qw - 35, qy + 10), (qx + qw - 10, qy + 35)], outline=(30, 41, 59), width=3)
    draw.rectangle([(qx + 10, qy + qh - 35), (qx + 35, qy + qh - 10)], outline=(30, 41, 59), width=3)
    draw.text((qx + qw // 2, qy + qh + 12), "SECURE QR CODE", fill=LABEL_COLOR, font=f_small, anchor="mm")

    # 6. Big Identity Number at bottom center (Aadhaar style)
    draw.line([(30, 370), (W - 30, 370)], fill=(226, 232, 240), width=1)
    draw.text((W // 2, 410), DATA["id_number"], fill=NAVY, font=f_id, anchor="mm")
    draw.text((W // 2, 440), "Mera Aadhaar, Meri Pehchan", fill=SAFFRON, font=f_lbl, anchor="mm")

    # 7. Disclaimers at bottom
    draw.line([(8, H - 55), (W - 8, H - 55)], fill=BORDER_COLOR, width=1)
    draw.text(
        (W // 2, H - 35),
        "*** SYNTHETIC TEST NATIONAL ID — NOT A REAL DOCUMENT — DEVELOPMENT ONLY ***",
        fill=(185, 28, 28),
        font=f_small,
        anchor="mm",
    )
    draw.text(
        (W // 2, H - 18),
        "Indian National ID Reference Profile (UIDAI Aadhaar format v0.10.0)",
        fill=(100, 116, 139),
        font=f_small,
        anchor="mm",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "JPEG", quality=95)
    return output_path


if __name__ == "__main__":
    out = Path(__file__).parent / "assets" / "sample_national_id.jpg"
    res = create_synthetic_national_id(out)
    print(f"Created synthetic National ID test image: {res}")
