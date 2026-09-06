"""
backend/tests/create_synthetic_driving_license.py

Script to generate a synthetic Driving License test image for testing and the frontend sample loader.

IMPORTANT:
  - This is a SYNTHETIC document used for testing ONLY.
  - No real person's data is used.
  - The image is clearly labelled "SYNTHETIC TEST DRIVING LICENCE".
  - Fictional data matching deterministic mock registry records.
"""
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")

# ──────────────────────────────────────────────
#  Synthetic Driving License Data
# ──────────────────────────────────────────────
DATA = {
    "country":       "UNION OF INDIA",
    "state":         "DELHI TRANSPORT DEPARTMENT",
    "title":         "DRIVING LICENCE",
    "dl_number":     "TESTDL001",
    "name":          "RAHUL SHARMA",
    "dob":           "15/05/1992",
    "issue_date":    "15/05/2011",
    "valid_till":    "14/05/2035",
    "blood_group":   "O+",
    "cov":           "MCWG, LMV",
    "authority":     "RTO DELHI",
}

W, H = 850, 540  # Standard card ratio ~ 1.58
BG_COLOR = (245, 248, 252)       # Card background (very light cyan-tinted grey)
DARK = (15, 23, 42)              # High contrast dark text
LABEL_COLOR = (71, 85, 105)      # Slate label text
HEADER_BG = (30, 58, 138)        # Dark blue header
BORDER_COLOR = (203, 213, 225)   # Border color


def _try_font(size: int):
    for font_name in ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def create_synthetic_driving_license(output_path: Path) -> Path:
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    f_large = _try_font(24)
    f_title = _try_font(18)
    f_val = _try_font(16)
    f_lbl = _try_font(12)
    f_small = _try_font(11)

    # 1. Outer border
    draw.rectangle([(8, 8), (W - 8, H - 8)], outline=BORDER_COLOR, width=2)

    # 2. Header Band
    draw.rectangle([(8, 8), (W - 8, 85)], fill=HEADER_BG)
    draw.text((W // 2, 22), DATA["country"], fill=(255, 255, 255), font=f_large, anchor="mm")
    draw.text((W // 2, 48), DATA["state"], fill=(224, 231, 255), font=f_title, anchor="mm")
    draw.text((W // 2, 70), DATA["title"], fill=(253, 224, 71), font=f_small, anchor="mm")

    # 3. Photo area (Left)
    px, py, pw, ph = 35, 120, 160, 200
    draw.rectangle([(px, py), (px + pw, py + ph)], fill=(226, 232, 240), outline=(148, 163, 184), width=2)
    # Draw simple stylized portrait placeholder
    draw.ellipse([(px + 45, py + 30), (px + 115, py + 100)], fill=(148, 163, 184))
    draw.ellipse([(px + 20, py + 110), (px + 140, py + 220)], fill=(148, 163, 184))
    draw.text((px + pw // 2, py + ph - 25), "PHOTO", fill=(71, 85, 105), font=f_lbl, anchor="mm")

    # 4. Fields layout (Right)
    fx = 230
    y = 105
    spacing = 42

    def draw_field(lbl: str, val: str, cur_y: int, x_off: int = fx):
        draw.text((x_off, cur_y), lbl, fill=LABEL_COLOR, font=f_lbl)
        draw.text((x_off, cur_y + 15), val, fill=DARK, font=f_val)

    # DL No
    draw_field("DL NO / LICENCE NO:", DATA["dl_number"], y)
    draw_field("DOI / ISSUE DATE:", DATA["issue_date"], y, x_off=550)

    # Name
    draw_field("HOLDER NAME:", DATA["name"], y + spacing)
    draw_field("VALID TILL / EXPIRY:", DATA["valid_till"], y + spacing, x_off=550)

    # DOB & Blood Group
    draw_field("DATE OF BIRTH (DOB):", DATA["dob"], y + spacing * 2)
    draw_field("BLOOD GROUP:", DATA["blood_group"], y + spacing * 2, x_off=550)

    # COV & Authority
    draw_field("CLASS OF VEHICLE (COV):", DATA["cov"], y + spacing * 3)
    draw_field("ISSUING AUTHORITY:", DATA["authority"], y + spacing * 3, x_off=550)

    # Watermark / Disclaimers
    draw.line([(8, H - 70), (W - 8, H - 70)], fill=BORDER_COLOR, width=1)
    draw.text(
        (W // 2, H - 45),
        "*** SYNTHETIC TEST DRIVING LICENCE — NOT A REAL DOCUMENT — DEVELOPMENT ONLY ***",
        fill=(185, 28, 28),
        font=f_small,
        anchor="mm",
    )
    draw.text(
        (W // 2, H - 25),
        "Indian Driving Licence Reference Profile (MoRTH / Sarathi format v0.9.0)",
        fill=(100, 116, 139),
        font=f_small,
        anchor="mm",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "JPEG", quality=95)
    return output_path


if __name__ == "__main__":
    out = Path(__file__).parent / "assets" / "sample_driving_license.jpg"
    res = create_synthetic_driving_license(out)
    print(f"Created synthetic driving license test image: {res}")
