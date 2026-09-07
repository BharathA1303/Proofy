"""
backend/tests/generate_all_synthetic_samples.py

Generates 15 high-fidelity synthetic document test images covering 5 document profiles:
1. Passport (Official, Blacklist, Defective)
2. Visa (Official, Blacklist, Defective)
3. Driving License (Official, Blacklist, Defective)
4. National ID (Official, Blacklist, Defective)
5. Border / Work Permit (Official, Blacklist, Defective)

Output directories:
- backend/tests/assets/
- public/samples/<doc_type>/
- dist/samples/<doc_type>/
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Dihedral group D5 multiplication table & permutation for Verhoeff check digit
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

def compute_verhoeff(num_str: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(num_str)):
        c = VERHOEFF_D[c][VERHOEFF_P[(i + 1) % 8][int(ch)]]
    return str(VERHOEFF_INV[c])

def icao_char_val(ch: str) -> int:
    if "0" <= ch <= "9": return ord(ch) - ord("0")
    if "A" <= ch <= "Z": return ord(ch) - ord("A") + 10
    return 0

def compute_icao_check_digit(s: str) -> str:
    weights = (7, 3, 1)
    tot = sum(icao_char_val(c.upper()) * weights[i % 3] for i, c in enumerate(s))
    return str(tot % 10)

def try_font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    font_names = ["cour.ttf", "consola.ttf", "courbd.ttf"] if mono else ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf"]
    for fn in font_names:
        for prefix in ["C:/Windows/Fonts/", "/usr/share/fonts/", ""]:
            try:
                return ImageFont.truetype(prefix + fn, size)
            except Exception:
                continue
    return ImageFont.load_default()

def save_to_destinations(img: Image.Image, filename: str, doc_category: str):
    root = Path(__file__).parent.parent.parent
    destinations = [
        root / "backend" / "tests" / "assets" / filename,
        root / "public" / "samples" / doc_category / filename,
        root / "dist" / "samples" / doc_category / filename,
    ]
    for p in destinations:
        p.parent.mkdir(parents=True, exist_ok=True)
        img.save(p, format="JPEG", quality=95)
    print(f"Saved {filename} to {len(destinations)} destinations.")

# ─────────────────────────────────────────────────────────────────────────────
# 1. PASSPORT GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def create_passport_image(
    doc_number: str,
    name: str,
    dob_dmy: str,
    dob_yymmdd: str,
    sex: str,
    exp_dmy: str,
    exp_yymmdd: str,
    authority: str,
    is_blacklist: bool = False,
    is_defective: bool = False,
) -> Image.Image:
    W, H = 850, 1200
    img = Image.new("RGB", (W, H), (246, 242, 228))
    draw = ImageDraw.Draw(img)

    f_title = try_font(28)
    f_hdr = try_font(20)
    f_lbl = try_font(13)
    f_val = try_font(17)
    f_mono = try_font(18, mono=True)
    f_badge = try_font(14)

    # Top Banner
    bar_color = (180, 40, 40) if is_blacklist else (20, 60, 110)
    draw.rectangle([0, 0, W, 75], fill=bar_color)
    draw.text((W // 2, 38), "REPUBLIC OF INDIA", font=f_title, fill="white", anchor="mm")

    # Document Type Header
    draw.text((W // 2, 105), "PASSPORT / PASSEPORT", font=f_hdr, fill=(30, 40, 60), anchor="mm")

    # Sub-status watermark / ribbon
    if is_blacklist:
        draw.rectangle([W - 240, 85, W - 20, 115], fill=(220, 38, 38))
        draw.text((W - 130, 100), "STATUS: REVOKED / WATCHLIST", font=f_badge, fill="white", anchor="mm")
    elif is_defective:
        draw.rectangle([W - 240, 85, W - 20, 115], fill=(217, 119, 6))
        draw.text((W - 130, 100), "TAMPERED / DEFECTIVE VECTOR", font=f_badge, fill="white", anchor="mm")
    else:
        draw.rectangle([W - 240, 85, W - 20, 115], fill=(22, 101, 52))
        draw.text((W - 130, 100), "OFFICIAL REGISTERED VECTOR", font=f_badge, fill="white", anchor="mm")

    # Photo Box
    draw.rectangle([40, 140, 240, 360], fill=(210, 215, 225), outline=(60, 70, 90), width=2)
    draw.text((140, 250), "[ BEARER PORTRAIT ]\nICAO TD3 SPEC", font=f_lbl, fill=(80, 90, 110), anchor="mm", align="center")

    # Fields
    def fld(label, val, x, y):
        draw.text((x, y), label.upper(), font=f_lbl, fill=(100, 110, 130))
        draw.text((x, y + 18), str(val), font=f_val, fill=(15, 25, 45))

    rx = 270
    surname = name.split()[-1]
    given = " ".join(name.split()[:-1]) if len(name.split()) > 1 else name

    fld("Type / Type", "P", rx, 145)
    fld("Country Code", "IND", rx + 120, 145)
    fld("Passport No.", doc_number, rx + 260, 145)

    fld("Surname / Nom", surname, rx, 205)
    fld("Given Name(s) / Prénoms", given, rx, 260)
    fld("Nationality / Nationalité", "INDIAN", rx, 315)
    fld("Date of Birth", dob_dmy, rx, 370)
    fld("Sex", sex, rx + 240, 370)

    fld("Place of Birth", "NEW DELHI, INDIA", 40, 425)
    fld("Date of Issue", "10 JAN 2020", 40, 480)
    fld("Date of Expiry", exp_dmy, 270, 480)
    fld("Issuing Authority", authority, 40, 535)

    # Separator
    draw.line([30, 620, W - 30, 620], fill=(180, 185, 195), width=1)
    draw.text((40, 635), "Holder's Signature:", font=f_lbl, fill=(100, 110, 130))
    draw.line([40, 690, 320, 690], fill=(30, 40, 60), width=2)

    # MRZ Strip (bottom)
    mrz_y = H - 150
    draw.rectangle([0, mrz_y - 20, W, H], fill=(232, 230, 220))
    draw.text((40, mrz_y - 14), "P < I N D  MACHINE READABLE ZONE  (ICAO DOC 9303)", font=f_lbl, fill=(100, 110, 130))

    # Calculate exact MRZ lines
    # Line 1: P<IND + surname + << + given + padded to 44
    l1 = f"P<IND{surname}<<{given.replace(' ', '<')}"
    l1 = (l1 + "<" * 44)[:44]

    # Line 2: doc9 + cd_doc + IND + dob + cd_dob + sex + exp + cd_exp + 14*< + opt_cd + comp_cd
    doc9 = (doc_number + "<" * 9)[:9]
    cd_doc = compute_icao_check_digit(doc9)
    cd_dob = compute_icao_check_digit(dob_yymmdd)
    cd_exp = compute_icao_check_digit(exp_yymmdd)

    if is_defective:
        # Deliberately invalidate check digits for defect sample
        cd_doc = "9" if cd_doc != "9" else "0"
        cd_exp = "8" if cd_exp != "8" else "1"

    opt14 = "<" * 14
    opt_cd = "<"
    comp_data = f"{doc9}{cd_doc}{dob_yymmdd}{cd_dob}{exp_yymmdd}{cd_exp}{opt14}{opt_cd}"
    comp_cd = compute_icao_check_digit(comp_data)

    if is_defective:
        comp_cd = "5" if comp_cd != "5" else "2"

    l2 = f"{doc9}{cd_doc}IND{dob_yymmdd}{cd_dob}{sex}{exp_yymmdd}{cd_exp}{opt14}{opt_cd}{comp_cd}"

    draw.text((40, mrz_y + 15), l1, font=f_mono, fill=(15, 25, 45))
    draw.text((40, mrz_y + 55), l2, font=f_mono, fill=(15, 25, 45))

    return img

# ─────────────────────────────────────────────────────────────────────────────
# 2. VISA GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def create_visa_image(
    visa_number: str,
    passport_num: str,
    name: str,
    dob_dmy: str,
    visa_type: str,
    issue_dmy: str,
    exp_dmy: str,
    authority: str,
    is_blacklist: bool = False,
    is_defective: bool = False,
) -> Image.Image:
    W, H = 850, 1100
    img = Image.new("RGB", (W, H), (248, 246, 238))
    draw = ImageDraw.Draw(img)

    f_title = try_font(26)
    f_sub = try_font(18)
    f_lbl = try_font(13)
    f_val = try_font(17)
    f_mono = try_font(18, mono=True)
    f_badge = try_font(14)

    # Banner
    bar_color = (180, 30, 30) if is_blacklist else (30, 70, 140)
    draw.rectangle([0, 0, W, 70], fill=bar_color)
    draw.text((W // 2, 25), "OFFICIAL ENTRY VISA", font=f_title, fill="white", anchor="mm")
    draw.text((W // 2, 52), "DEMO BORDER CONTROL IMMIGRATION SERVICE", font=try_font(13), fill=(210, 230, 255), anchor="mm")

    # Status badge
    if is_blacklist:
        draw.rectangle([W - 240, 80, W - 20, 110], fill=(220, 38, 38))
        draw.text((W - 130, 95), "REVOKED / BLACKLIST", font=f_badge, fill="white", anchor="mm")
    elif is_defective:
        draw.rectangle([W - 240, 80, W - 20, 110], fill=(217, 119, 6))
        draw.text((W - 130, 95), "DEFECTIVE / MISSING DATA", font=f_badge, fill="white", anchor="mm")
    else:
        draw.rectangle([W - 240, 80, W - 20, 110], fill=(22, 101, 52))
        draw.text((W - 130, 95), "OFFICIAL / ACTIVE VISA", font=f_badge, fill="white", anchor="mm")

    # Photo Box
    draw.rectangle([40, 130, 230, 340], fill=(220, 225, 235), outline=(70, 80, 100), width=2)
    draw.text((135, 235), "[ VISA PHOTO ]", font=f_lbl, fill=(80, 90, 110), anchor="mm")

    def fld(label, val, x, y):
        draw.text((x, y), label.upper(), font=f_lbl, fill=(100, 110, 130))
        draw.text((x, y + 18), str(val), font=f_val, fill=(15, 25, 45))

    rx = 260
    fld("Visa Number", visa_number, rx, 130)
    fld("Passport Number", passport_num, rx + 240, 130)
    fld("Bearer Full Name", name, rx, 190)
    fld("Nationality", "IND", rx, 250)
    fld("Date of Birth", dob_dmy, rx + 160, 250)
    fld("Visa Type / Class", visa_type, rx, 310)
    fld("Number of Entries", "MULTIPLE", rx + 160, 310)

    fld("Date of Issue", issue_dmy, 40, 370)
    fld("Valid Until / Expiry", exp_dmy, 260, 370)
    fld("Duration of Stay", "90 DAYS", 520, 370)
    fld("Issuing Authority", authority, 40, 430)

    # Security Stamp / Seal
    draw.ellipse([580, 440, 720, 580], outline=(150, 40, 40), width=2)
    draw.text((650, 510), "OFFICIAL\nVISA SEAL", font=try_font(12), fill=(150, 40, 40), anchor="mm", align="center")

    # MRZ (ICAO Doc 9303 MRVA/B, starts with V<)
    mrz_y = H - 140
    draw.rectangle([0, mrz_y - 20, W, H], fill=(235, 233, 222))
    draw.text((40, mrz_y - 12), "V < I N D  MACHINE READABLE VISA ZONE", font=f_lbl, fill=(100, 110, 130))

    surname = name.split()[-1]
    given = " ".join(name.split()[:-1]) if len(name.split()) > 1 else name
    vl1 = f"VNIND{surname}<<{given.replace(' ', '<')}"
    vl1 = (vl1 + "<" * 44)[:44]

    v_num9 = (visa_number + "<" * 9)[:9]
    cd_vnum = compute_icao_check_digit(v_num9)
    vl2 = f"{v_num9}{cd_vnum}IND9005156M2801311<<<<<<<<<<<<<<<0"
    vl2 = (vl2 + "<" * 44)[:44]

    draw.text((40, mrz_y + 15), vl1, font=f_mono, fill=(15, 25, 45))
    draw.text((40, mrz_y + 55), vl2, font=f_mono, fill=(15, 25, 45))

    return img

# ─────────────────────────────────────────────────────────────────────────────
# 3. DRIVING LICENSE GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def create_dl_image(
    dl_number: str,
    name: str,
    dob: str,
    issue_date: str,
    valid_till: str,
    cov: str,
    authority: str,
    state_title: str,
    is_blacklist: bool = False,
    is_defective: bool = False,
) -> Image.Image:
    W, H = 850, 540
    img = Image.new("RGB", (W, H), (245, 248, 252))
    draw = ImageDraw.Draw(img)

    f_title = try_font(20)
    f_sub = try_font(15)
    f_lbl = try_font(12)
    f_val = try_font(15)
    f_badge = try_font(13)

    # Header
    hdr_color = (180, 30, 30) if is_blacklist else (20, 50, 110)
    draw.rectangle([0, 0, W, 75], fill=hdr_color)
    draw.text((W // 2, 22), "UNION OF INDIA - DRIVING LICENCE", font=f_title, fill="white", anchor="mm")
    draw.text((W // 2, 48), state_title.upper(), font=f_sub, fill=(210, 230, 255), anchor="mm")

    # Status badge
    if is_blacklist:
        draw.rectangle([W - 220, 10, W - 15, 38], fill=(220, 38, 38))
        draw.text((W - 117, 24), "STATUS: REVOKED", font=f_badge, fill="white", anchor="mm")
    elif is_defective:
        draw.rectangle([W - 220, 10, W - 15, 38], fill=(217, 119, 6))
        draw.text((W - 117, 24), "TAMPERED / DEFECT", font=f_badge, fill="white", anchor="mm")
    else:
        draw.rectangle([W - 220, 10, W - 15, 38], fill=(22, 101, 52))
        draw.text((W - 117, 24), "GENUINE / ACTIVE", font=f_badge, fill="white", anchor="mm")

    # Photo Box
    draw.rectangle([35, 100, 215, 310], fill=(220, 225, 235), outline=(70, 80, 100), width=2)
    draw.text((125, 205), "[ DL PHOTO ]", font=f_lbl, fill=(80, 90, 110), anchor="mm")

    def fld(label, val, x, y):
        draw.text((x, y), label.upper(), font=f_lbl, fill=(90, 100, 120))
        draw.text((x, y + 16), str(val), font=f_val, fill=(15, 23, 42))

    rx = 240
    fld("DL No.", dl_number, rx, 100)
    fld("Holder Name", name, rx, 150)
    fld("Date of Birth", dob, rx, 200)
    fld("Blood Group", "B+" if not is_defective else "O-", rx + 220, 200)
    fld("Issue Date", issue_date, rx, 250)
    fld("Valid Till", valid_till, rx + 220, 250)
    fld("Class of Vehicles (COV)", cov, rx, 300)

    # Authority & Chip
    draw.rectangle([35, 335, 130, 415], fill=(218, 165, 32), outline=(139, 69, 19), width=1)
    draw.text((82, 375), "SMART\nCHIP", font=try_font(11), fill=(50, 30, 10), anchor="mm", align="center")

    fld("Issuing Authority", authority, 155, 355)

    # Security microprint footer
    draw.line([20, 480, W - 20, 480], fill=(180, 190, 205), width=1)
    draw.text((W // 2, 505), "MINISTRY OF ROAD TRANSPORT & HIGHWAYS - SARATHI VERIFIED", font=try_font(11), fill=(100, 110, 130), anchor="mm")

    return img

# ─────────────────────────────────────────────────────────────────────────────
# 4. NATIONAL ID (AADHAAR) GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def create_national_id_image(
    id_formatted: str,
    name: str,
    dob: str,
    gender: str,
    address: str,
    authority: str,
    is_blacklist: bool = False,
    is_defective: bool = False,
) -> Image.Image:
    W, H = 850, 540
    img = Image.new("RGB", (W, H), (252, 250, 245))
    draw = ImageDraw.Draw(img)

    f_title = try_font(18)
    f_sub = try_font(13)
    f_lbl = try_font(12)
    f_val = try_font(15)
    f_uid = try_font(24)

    # Header - Government of India / Unique Identification Authority of India
    draw.rectangle([0, 0, W, 70], fill=(235, 230, 220))
    draw.text((W // 2, 22), "GOVERNMENT OF INDIA", font=f_title, fill=(30, 40, 60), anchor="mm")
    draw.text((W // 2, 46), "UNIQUE IDENTIFICATION AUTHORITY OF INDIA", font=f_sub, fill=(100, 40, 40), anchor="mm")

    # Tricolor stripe
    draw.rectangle([0, 68, W, 72], fill=(234, 88, 12))   # Saffron
    draw.rectangle([0, 72, W, 76], fill=(255, 255, 255)) # White
    draw.rectangle([0, 76, W, 80], fill=(22, 101, 52))   # Green

    # Photo Box
    draw.rectangle([35, 110, 205, 320], fill=(225, 225, 235), outline=(70, 80, 100), width=2)
    draw.text((120, 215), "[ NID PHOTO ]", font=f_lbl, fill=(80, 90, 110), anchor="mm")

    def fld(label, val, x, y):
        draw.text((x, y), label, font=f_lbl, fill=(90, 100, 120))
        draw.text((x, y + 16), str(val), font=f_val, fill=(15, 23, 42))

    rx = 230
    fld("Name", name, rx, 110)
    fld("Date of Birth / DOB", dob, rx, 160)
    fld("Gender / Sex", gender, rx, 210)
    fld("Address", address, rx, 260)

    # Large 12-Digit UID at Bottom
    uid_bg = (240, 243, 248)
    draw.rectangle([35, 375, W - 35, 455], fill=uid_bg, outline=(180, 190, 210), width=1)
    draw.text((W // 2, 415), id_formatted, font=f_uid, fill=(180, 40, 40) if is_blacklist else (20, 40, 90), anchor="mm")

    # Bottom Tagline
    draw.text((W // 2, 495), "AADHAAR - IDENTITY ATTESTATION CREDENTIAL", font=try_font(12), fill=(100, 110, 130), anchor="mm")

    return img

# ─────────────────────────────────────────────────────────────────────────────
# 5. BORDER / WORK PERMIT GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def create_border_permit_image(
    permit_num: str,
    passport_num: str,
    name: str,
    dob: str,
    valid_from: str,
    valid_to: str,
    permit_type: str,
    port: str,
    authority: str,
    is_blacklist: bool = False,
    is_defective: bool = False,
) -> Image.Image:
    W, H = 850, 540
    img = Image.new("RGB", (W, H), (242, 246, 250))
    draw = ImageDraw.Draw(img)

    f_title = try_font(20)
    f_sub = try_font(14)
    f_lbl = try_font(12)
    f_val = try_font(15)
    f_badge = try_font(13)

    # Header
    hdr_color = (180, 30, 30) if is_blacklist else (20, 55, 90)
    draw.rectangle([0, 0, W, 75], fill=hdr_color)
    draw.text((W // 2, 24), "REGIONAL BORDER CONTROL & LABOUR AUTHORITY", font=f_title, fill="white", anchor="mm")
    draw.text((W // 2, 50), "OFFICIAL ENTRY & WORK PERMIT", font=f_sub, fill=(210, 235, 255), anchor="mm")

    if is_blacklist:
        draw.rectangle([W - 220, 10, W - 15, 38], fill=(220, 38, 38))
        draw.text((W - 117, 24), "REVOKED PERMIT", font=f_badge, fill="white", anchor="mm")
    elif is_defective:
        draw.rectangle([W - 220, 10, W - 15, 38], fill=(217, 119, 6))
        draw.text((W - 117, 24), "DEFECTIVE PERMIT", font=f_badge, fill="white", anchor="mm")
    else:
        draw.rectangle([W - 220, 10, W - 15, 38], fill=(22, 101, 52))
        draw.text((W - 117, 24), "VALIDATED / ACTIVE", font=f_badge, fill="white", anchor="mm")

    # Photo Box
    draw.rectangle([35, 100, 215, 310], fill=(215, 225, 235), outline=(100, 130, 160), width=2)
    draw.text((125, 205), "[ PERMIT PHOTO ]", font=f_lbl, fill=(80, 100, 120), anchor="mm")

    def fld(label, val, x, y):
        draw.text((x, y), label.upper(), font=f_lbl, fill=(80, 100, 120))
        draw.text((x, y + 16), str(val), font=f_val, fill=(15, 25, 45))

    rx = 240
    fld("Permit Number", permit_num, rx, 100)
    fld("Passport Number", passport_num, rx + 240, 100)
    fld("Holder Name", name, rx, 150)
    fld("Date of Birth", dob, rx + 240, 150)
    fld("Valid From", valid_from, rx, 200)
    fld("Valid To", valid_to, rx + 240, 200)
    fld("Permit Type", permit_type, rx, 250)
    fld("Port of Entry / Zone", port, rx + 240, 250)

    fld("Issuing Authority", authority, 240, 310)

    # Footer
    draw.line([20, 460, W - 20, 460], fill=(180, 195, 210), width=1)
    draw.text((W // 2, 490), "BORDER MANAGEMENT IMMIGRATION SYSTEM - OFFICIAL WORK CREDENTIAL", font=try_font(11), fill=(90, 110, 130), anchor="mm")

    return img


# ─────────────────────────────────────────────────────────────────────────────
# MAIN GENERATION ROUTINE
# ─────────────────────────────────────────────────────────────────────────────

def generate_all():
    print("Beginning generation of 15 synthetic sample document images...")

    # 1. PASSPORTS
    p1 = create_passport_image(
        doc_number="Z1234567",
        name="AARAV SHARMA",
        dob_dmy="15 MAY 1990",
        dob_yymmdd="900515",
        sex="M",
        exp_dmy="09 JAN 2030",
        exp_yymmdd="300109",
        authority="REGIONAL PASSPORT OFFICE DELHI",
    )
    save_to_destinations(p1, "passport_official.jpg", "passport")

    p2 = create_passport_image(
        doc_number="Z7654321",
        name="VIKRAM MALHOTRA",
        dob_dmy="20 NOV 1982",
        dob_yymmdd="821120",
        sex="M",
        exp_dmy="11 APR 2028",
        exp_yymmdd="280411",
        authority="REGIONAL PASSPORT OFFICE MUMBAI",
        is_blacklist=True,
    )
    save_to_destinations(p2, "passport_blacklist.jpg", "passport")

    p3 = create_passport_image(
        doc_number="Z9999999",
        name="ROHIT VERMA",
        dob_dmy="25 AUG 1995",
        dob_yymmdd="950825",
        sex="M",
        exp_dmy="01 JUN 2019", # Expired / preceding issue date
        exp_yymmdd="190601",
        authority="[AUTHORITY OMITTED]",
        is_defective=True,
    )
    save_to_destinations(p3, "passport_defective.jpg", "passport")

    # 2. VISAS
    v1 = create_visa_image(
        visa_number="V1002003",
        passport_num="Z1234567",
        name="AARAV SHARMA",
        dob_dmy="15 MAY 1990",
        visa_type="BUSINESS",
        issue_dmy="01 FEB 2023",
        exp_dmy="31 JAN 2028",
        authority="CONSULAR SECTION DELHI",
    )
    save_to_destinations(v1, "visa_official.jpg", "visa")

    v2 = create_visa_image(
        visa_number="V7008009",
        passport_num="Z7654321",
        name="VIKRAM MALHOTRA",
        dob_dmy="20 NOV 1982",
        visa_type="TOURIST",
        issue_dmy="10 MAY 2022",
        exp_dmy="09 MAY 2027",
        authority="CONSULAR SECTION MUMBAI",
        is_blacklist=True,
    )
    save_to_destinations(v2, "visa_blacklist.jpg", "visa")

    v3 = create_visa_image(
        visa_number="V999", # Invalid format (too short)
        passport_num="[UNBOUND / MISSING]",
        name="ROHIT VERMA",
        dob_dmy="25 AUG 1995",
        visa_type="VISIT",
        issue_dmy="[MISSING]",
        exp_dmy="01 JAN 2020",
        authority="DEMO CONSULAR POST",
        is_defective=True,
    )
    save_to_destinations(v3, "visa_defective.jpg", "visa")

    # 3. DRIVING LICENSES
    d1 = create_dl_image(
        dl_number="DL-0420230012345",
        name="PRIYA SUNDAR",
        dob="22/03/1994",
        issue_date="22/03/2014",
        valid_till="21/03/2034",
        cov="MCWG, LMV",
        authority="RTO DELHI CENTRAL",
        state_title="DELHI TRANSPORT DEPARTMENT",
    )
    save_to_destinations(d1, "dl_official.jpg", "dl")

    d2 = create_dl_image(
        dl_number="DL-0120180099887",
        name="KABIR MEHTA",
        dob="14/07/1986",
        issue_date="14/07/2018",
        valid_till="13/07/2038",
        cov="MCWG, LMV",
        authority="RTO MUMBAI WEST",
        state_title="MAHARASHTRA MOTOR VEHICLES DEPT",
        is_blacklist=True,
    )
    save_to_destinations(d2, "dl_blacklist.jpg", "dl")

    d3 = create_dl_image(
        dl_number="INVALID-DL-12",
        name="ANIL KUMAR",
        dob="10/08/2012",
        issue_date="15/05/2005", # Issue date before DOB!
        valid_till="14/05/2025",
        cov="[MISSING COV CLASS]",
        authority="[MISSING AUTHORITY]",
        state_title="TRANSPORT DEPARTMENT",
        is_defective=True,
    )
    save_to_destinations(d3, "dl_defective.jpg", "dl")

    # 4. NATIONAL ID (AADHAAR)
    # Valid Verhoeff for Sneha Patel
    nid_p1 = "84729103847"
    nid_c1 = compute_verhoeff(nid_p1)
    nid1_full = f"{nid_p1}{nid_c1}"
    n1 = create_national_id_image(
        id_formatted=f"{nid1_full[:4]} {nid1_full[4:8]} {nid1_full[8:]}",
        name="SNEHA PATEL",
        dob="18/09/1992",
        gender="FEMALE",
        address="42 BAKER STREET, NEW DELHI 110001",
        authority="UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
    )
    save_to_destinations(n1, "national_id_official.jpg", "national_id")

    # Valid Verhoeff for Tariq Ahmed (Blacklist)
    nid_p2 = "65412398710"
    nid_c2 = compute_verhoeff(nid_p2)
    nid2_full = f"{nid_p2}{nid_c2}"
    n2 = create_national_id_image(
        id_formatted=f"{nid2_full[:4]} {nid2_full[4:8]} {nid2_full[8:]}",
        name="TARIQ AHMED",
        dob="05/04/1980",
        gender="MALE",
        address="15 MARINE DRIVE, MUMBAI 400020",
        authority="UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
        is_blacklist=True,
    )
    save_to_destinations(n2, "national_id_blacklist.jpg", "national_id")

    # Invalid Verhoeff checksum & missing demographic details
    n3 = create_national_id_image(
        id_formatted="1234 5678 9999", # Invalid Verhoeff
        name="DEVRAJ SINGH",
        dob="[MISSING DOB]",
        gender="MALE",
        address="[ADDRESS OMITTED]",
        authority="GOVERNMENT OF INDIA",
        is_defective=True,
    )
    save_to_destinations(n3, "national_id_defective.jpg", "national_id")

    # 5. BORDER / WORK PERMIT
    bp1 = create_border_permit_image(
        permit_num="BP-2026-880011",
        passport_num="Z1234567",
        name="ELENA ROSTOVA",
        dob="12-10-1991",
        valid_from="01-01-2026",
        valid_to="31-12-2026",
        permit_type="WORK & ENTRY PERMIT",
        port="NORTH GATE TERMINAL",
        authority="BORDER IMMIGRATION & LABOUR AUTHORITY",
    )
    save_to_destinations(bp1, "border_permit_official.jpg", "border_permit")

    bp2 = create_border_permit_image(
        permit_num="BP-2025-443322",
        passport_num="Z7654321",
        name="MARCUS VANCE",
        dob="20-06-1983",
        valid_from="01-06-2025",
        valid_to="01-06-2026",
        permit_type="WORK & ENTRY PERMIT",
        port="WEST HARBOR TERMINAL",
        authority="BORDER IMMIGRATION & LABOUR AUTHORITY",
        is_blacklist=True,
    )
    save_to_destinations(bp2, "border_permit_blacklist.jpg", "border_permit")

    bp3 = create_border_permit_image(
        permit_num="PERMIT-XYZ", # Invalid format
        passport_num="[UNBOUND]",
        name="JOHN DOE",
        dob="15-05-1990",
        valid_from="01-12-2026",
        valid_to="01-01-2026", # Valid To precedes Valid From!
        permit_type="BORDER ENTRY",
        port="[MISSING PORT]",
        authority="REGIONAL PERMIT OFFICE",
        is_defective=True,
    )
    save_to_destinations(bp3, "border_permit_defective.jpg", "border_permit")

    print("\nAll 15 synthetic sample document images created successfully!")

if __name__ == "__main__":
    generate_all()
