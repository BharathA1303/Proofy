"""
backend/tests/create_synthetic_passport.py

Script to generate a synthetic passport-like test image.

IMPORTANT:
  - This is a SYNTHETIC document used for testing ONLY.
  - No real person's data is used.
  - The image is clearly labelled "SYNTHETIC TEST DOCUMENT".
  - This must never be committed alongside real passport data.
  - The image is designed to give PaddleOCR something realistic to parse.

Alignment with the live validation pipeline (passport_parser.py /
passport_validation_service.py):
  1. The MRZ is never hand-typed. It is BUILT from the same field data used
     for the Visual Inspection Zone, using the production ICAO 7-3-1
     check-digit algorithm (app.services.validation.icao_checkdigit), and
     is asserted to be exactly 44 characters per line before rendering.
     This guarantees the check digits are correct by construction and stay
     correct if DATA is ever edited.
  2. VIZ dates (DOB, Date of Issue, Date of Expiry) are rendered in
     DD/MM/YYYY — the one format both `_DATE_PATTERNS` (extraction) and
     `_normalize_date_to_dmy` (VIZ<->MRZ cross-consistency, in
     viz_mrz_checker.py) parse identically. A month-name format like
     "15 JUN 1985" is extractable but NOT cross-comparable against the
     MRZ-derived ISO date, so it silently fails viz_mrz_consistency.
  3. The MRZ strip is rendered at a larger font size (26pt monospace, up
     from 18pt) than the previous version. The single '<' filler between
     the 9-char document-number field and its check digit was the
     character most likely to be lost by PaddleOCR at the smaller size,
     which previously triggered a false "high-risk" mrz_auto_correction
     (filler_insert:pos8) on a genuine document. This was verified
     empirically against the real OCR engine (see tests/assets/ generation
     history) — 26pt with the font's natural glyph spacing reproduces both
     MRZ lines with zero corrections needed. Manually injecting extra
     inter-character spacing was also tried and made OCR LESS reliable, so
     it is deliberately not used here.

Run from the backend/ directory:
  python tests/create_synthetic_passport.py
"""
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")

# Make the app package importable when this script is run directly
# (`python tests/create_synthetic_passport.py` from the backend/ directory).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.validation.icao_checkdigit import calculate_icao_check_digit  # noqa: E402

# ──────────────────────────────────────────────
#  Synthetic source fields — all fictional
# ──────────────────────────────────────────────
FIELDS = {
    "country":        "REPUBLIC OF INDIA",
    "doc_type":       "PASSPORT",
    "issuing_state":  "IND",           # 3-letter MRZ issuing-state code
    "nationality_code": "IND",         # 3-letter MRZ / VIZ nationality code
    "nationality_label": "INDIAN",     # VIZ display label
    "surname":        "SYNTH",
    "given_names":    "TEST USER",
    "sex":            "M",             # 'M' | 'F' | 'X'
    "place_of_birth": "SYNTHETIC CITY",
    "authority":      "SYNTHETIC TEST AUTHORITY",
    "doc_number":     "T9876543",      # 8 chars; MRZ pads/truncates to 9 with '<'
    # Dates as (day, month, year) — single source of truth for both the
    # VIZ display strings and the MRZ YYMMDD fields, so they can never drift.
    "dob":            (15, 6, 1985),
    "date_of_issue":  (1, 1, 2020),
    "date_of_expiry": (31, 12, 2029),
}


def _viz_date(dmy: tuple[int, int, int]) -> str:
    """
    Render a (day, month, year) tuple as DD/MM/YYYY — the one VIZ date
    format both the extraction regex (_DATE_PATTERNS) and the VIZ<->MRZ
    cross-consistency normalizer (_normalize_date_to_dmy) parse identically.
    A month-name format ("15 JUN 1985") is extractable but not
    cross-comparable and must NOT be used here.
    """
    day, month, year = dmy
    return f"{day:02d}/{month:02d}/{year:04d}"


def _mrz_date(dmy: tuple[int, int, int]) -> str:
    """Render a (day, month, year) tuple as MRZ YYMMDD (6 digits)."""
    day, month, year = dmy
    return f"{year % 100:02d}{month:02d}{day:02d}"


def _build_mrz_lines(data: dict) -> tuple[str, str]:
    """
    Build TD3 MRZ line 1 and line 2 from field data, computing every ICAO
    7-3-1 check digit with the production algorithm rather than hand-typing
    a string. Both lines are asserted to be exactly 44 characters before
    being returned, so a malformed field (e.g. a name too long) fails loudly
    at generation time instead of silently producing an invalid MRZ image.
    """
    # ── Line 1: P<ISS<SURNAME<<GIVEN<NAMES<<<<<<<<<<<<<<<<<<<<<<< (44 chars) ──
    issuing_state = data["issuing_state"].ljust(3, "<")[:3]
    surname = data["surname"].upper().replace(" ", "<")
    given = data["given_names"].upper().replace(" ", "<")
    name_field = f"{surname}<<{given}"
    line1 = f"P<{issuing_state}{name_field}"
    line1 = (line1 + "<" * 44)[:44]

    # ── Line 2: DOCNUM<CHK ISS DOB<CHK SEX EXP<CHK OPTIONAL<<CHK COMPOSITE ──
    doc_number = data["doc_number"].upper().ljust(9, "<")[:9]
    doc_number_chk = calculate_icao_check_digit(doc_number)

    nationality = data["nationality_code"].ljust(3, "<")[:3]

    dob_yymmdd = _mrz_date(data["dob"])
    dob_chk = calculate_icao_check_digit(dob_yymmdd)

    sex = data["sex"].upper()

    expiry_yymmdd = _mrz_date(data["date_of_expiry"])
    expiry_chk = calculate_icao_check_digit(expiry_yymmdd)

    optional_data = "<" * 14  # positions 28-41: unused personal-number field
    optional_chk = "<"        # position 42: '<' is valid when optional data is all filler

    composite_input = (
        f"{doc_number}{doc_number_chk}"
        f"{dob_yymmdd}{dob_chk}"
        f"{expiry_yymmdd}{expiry_chk}"
        f"{optional_data}{optional_chk}"
    )
    composite_chk = calculate_icao_check_digit(composite_input)

    line2 = (
        f"{doc_number}{doc_number_chk}"
        f"{nationality}"
        f"{dob_yymmdd}{dob_chk}"
        f"{sex}"
        f"{expiry_yymmdd}{expiry_chk}"
        f"{optional_data}{optional_chk}"
        f"{composite_chk}"
    )

    assert len(line1) == 44, f"MRZ line 1 is {len(line1)} chars, expected 44: {line1!r}"
    assert len(line2) == 44, f"MRZ line 2 is {len(line2)} chars, expected 44: {line2!r}"
    assert re.fullmatch(r"[A-Z0-9<]{44}", line1), f"MRZ line 1 has invalid characters: {line1!r}"
    assert re.fullmatch(r"[A-Z0-9<]{44}", line2), f"MRZ line 2 has invalid characters: {line2!r}"

    return line1, line2


def _build_data() -> dict:
    """Derive all rendered VIZ strings and the MRZ lines from FIELDS."""
    mrz_line1, mrz_line2 = _build_mrz_lines(FIELDS)
    return {
        "country": FIELDS["country"],
        "doc_type": FIELDS["doc_type"],
        "surname": FIELDS["surname"],
        "given_names": FIELDS["given_names"],
        "nationality": FIELDS["nationality_label"],
        "dob": _viz_date(FIELDS["dob"]),
        "sex": FIELDS["sex"],
        "place_of_birth": FIELDS["place_of_birth"],
        "date_of_issue": _viz_date(FIELDS["date_of_issue"]),
        "date_of_expiry": _viz_date(FIELDS["date_of_expiry"]),
        "authority": FIELDS["authority"],
        "doc_number": FIELDS["doc_number"],
        "mrz_line1": mrz_line1,
        "mrz_line2": mrz_line2,
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

# MRZ rendering: deliberately larger than the rest of the document (26pt
# vs. the original 18pt). A TD3 MRZ line is 44 characters across the page
# width — every glyph, especially the sparse '<' filler characters, must
# have enough pixel footprint that a text recognizer doesn't drop it.
# Font size 18 was too small for the '<' between the document number and
# its check digit to reliably survive OCR at this image resolution; see
# the note above `draw.text(... data["mrz_line1"] ...)` below for why this
# uses the font's natural glyph spacing rather than manual spacing.
MRZ_FONT_SIZE = 26


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
    for font_name in ["cour.ttf", "consola.ttf", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "FreeMono.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def create_synthetic_passport(output_path: Path) -> None:
    data = _build_data()

    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Fonts
    title_font   = _try_font(28)
    header_font  = _try_font(22)
    label_font   = _try_font(13)
    value_font   = _try_font(17)
    mrz_font     = _try_mono_font(MRZ_FONT_SIZE)
    watermark_f  = _try_font(60)

    # ── Watermark (background) ────────────────────────────────────────────
    # Placed in the empty band between the signature line (~y=720) and the
    # MRZ strip (~y=1050) — NOT over any field label/value. The watermark
    # previously overlapped "Place of Birth", "Date of Issue", and "Date of
    # Expiry" (all drawn around y=380-460), which corrupted their OCR
    # reads badly enough that the label keywords never matched and
    # extraction fell through to a short, collision-prone abbreviation.
    draw.text((80, 780), "SYNTHETIC\nTEST DOCUMENT", font=watermark_f, fill=WATERMARK, spacing=10)

    # ── Header bar ────────────────────────────────────────────────────────
    draw.rectangle([0, 0, W, 80], fill=RED_BAR)
    draw.text((W // 2, 40), data["country"], font=title_font, fill="white", anchor="mm")

    # ── Document type ─────────────────────────────────────────────────────
    draw.text((W // 2, 110), data["doc_type"], font=header_font, fill=DARK, anchor="mm")

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
    draw_field("Surname", data["surname"],     rx, 160)
    draw_field("Given Name(s)", data["given_names"], rx, 220)
    draw_field("Nationality", data["nationality"], rx, 280)
    draw_field("Date of Birth", data["dob"],   rx, 340)
    draw_field("Sex",          data["sex"],     rx + 200, 340)

    # Full-width fields
    draw_field("Place of Birth", data["place_of_birth"], 40, 380)
    draw_field("Date of Issue",  data["date_of_issue"],  40, 440)
    draw_field("Date of Expiry", data["date_of_expiry"], 270, 440)
    draw_field("Issuing Authority", data["authority"],   40, 500)
    draw_field("Passport No.",   data["doc_number"],     40, 560)

    # ── Separator line ────────────────────────────────────────────────────
    draw.line([0, 650, W, 650], fill=(160, 160, 160), width=1)

    # ── Signature line ────────────────────────────────────────────────────
    draw.text((40, 670), "Holder's Signature:", font=label_font, fill=LABEL_COLOR)
    draw.line([40, 720, 400, 720], fill=DARK, width=1)

    # ── MRZ strip ─────────────────────────────────────────────────────────
    mrz_y_start = H - 150
    draw.rectangle([0, mrz_y_start - 15, W, H], fill=MRZ_BG)
    draw.text((40, mrz_y_start - 12), "Machine Readable Zone", font=label_font, fill=LABEL_COLOR)

    # MRZ Line 1 / Line 2 — rendered at MRZ_FONT_SIZE (26pt monospace) using
    # the font's own natural glyph advance. Empirically verified against the
    # real OCR engine: this size reproduces every character exactly,
    # including the single '<' filler between the document number and its
    # check digit, with zero corrections needed. Manually injecting extra
    # inter-character spacing was tried and made OCR LESS reliable — it
    # disrupted PaddleOCR's line-grouping and caused adjacent fillers to be
    # merged or dropped instead. Do not reintroduce manual spacing without
    # re-verifying against the real OCR engine first.
    draw.text((30, mrz_y_start + 10), data["mrz_line1"], font=mrz_font, fill=DARK)
    draw.text((30, mrz_y_start + 50), data["mrz_line2"], font=mrz_font, fill=DARK)

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
    img.save(output_path, format="JPEG", quality=95)
    print(f"Synthetic passport saved to: {output_path}")
    print("Data used:")
    for k, v in data.items():
        print(f"  {k}: {v}")
    print()
    print(f"MRZ line 1 ({len(data['mrz_line1'])} chars): {data['mrz_line1']}")
    print(f"MRZ line 2 ({len(data['mrz_line2'])} chars): {data['mrz_line2']}")


if __name__ == "__main__":
    out = Path(__file__).parent / "assets" / "sample_passport.jpg"
    create_synthetic_passport(out)
