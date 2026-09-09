"""
backend/tests/generate_aadhaar_voter_pan_samples.py

Generates synthetic image test assets for:
1. Aadhaar Card (Official, Blacklist, Defective, Sample)
2. Voter ID / EPIC (Official, Blacklist, Defective, Sample)
3. PAN Card (Official, Blacklist, Defective, Sample)

Saves to:
- backend/tests/assets/
- public/samples/<doc_type>/
- dist/samples/<doc_type>/
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

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
# 1. AADHAAR GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def create_aadhaar_image(
    id_formatted: str,
    name: str,
    dob: str,
    gender: str,
    address: str,
    authority: str = "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
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

    # Header - Government of India / UIDAI
    draw.rectangle([0, 0, W, 70], fill=(235, 230, 220))
    draw.text((W // 2, 22), "GOVERNMENT OF INDIA", font=f_title, fill=(30, 40, 60), anchor="mm")
    draw.text((W // 2, 46), authority, font=f_sub, fill=(100, 40, 40), anchor="mm")

    # Tricolor stripe
    draw.rectangle([0, 68, W, 72], fill=(234, 88, 12))   # Saffron
    draw.rectangle([0, 72, W, 76], fill=(255, 255, 255)) # White
    draw.rectangle([0, 76, W, 80], fill=(22, 101, 52))   # Green

    # Photo Box
    draw.rectangle([35, 110, 205, 320], fill=(225, 225, 235), outline=(70, 80, 100), width=2)
    draw.text((120, 215), "[ AADHAAR PHOTO ]", font=f_lbl, fill=(80, 90, 110), anchor="mm")

    def fld(label, val, x, y):
        draw.text((x, y), label, font=f_lbl, fill=(90, 100, 120))
        draw.text((x, y + 16), str(val), font=f_val, fill=(15, 23, 42))

    rx = 230
    fld("Name", name, rx, 110)
    fld("Date of Birth / DOB", dob, rx, 160)
    fld("Gender / Sex", gender, rx, 210)
    fld("Address", address, rx, 260)

    # QR Code placeholder box
    draw.rectangle([W - 175, 110, W - 35, 250], fill=(240, 240, 240), outline=(120, 120, 120), width=1)
    draw.text((W - 105, 180), "[ QR CODE ]", font=f_lbl, fill=(100, 100, 100), anchor="mm")

    # Large 12-Digit UID at Bottom
    uid_bg = (240, 243, 248)
    draw.rectangle([35, 375, W - 35, 455], fill=uid_bg, outline=(180, 190, 210), width=1)
    draw.text((W // 2, 415), id_formatted, font=f_uid, fill=(180, 40, 40) if is_blacklist else (20, 40, 90), anchor="mm")

    # Bottom Tagline
    draw.text((W // 2, 495), "AADHAAR - MERA AADHAAR, MERI PEHCHAN", font=try_font(12), fill=(100, 110, 130), anchor="mm")

    return img

# ─────────────────────────────────────────────────────────────────────────────
# 2. VOTER ID / EPIC GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def create_voter_id_image(
    epic_num: str,
    name: str,
    father_name: str,
    dob: str,
    gender: str,
    constituency: str,
    authority: str = "ELECTION COMMISSION OF INDIA",
    is_blacklist: bool = False,
    is_defective: bool = False,
) -> Image.Image:
    W, H = 850, 540
    img = Image.new("RGB", (W, H), (248, 250, 252))
    draw = ImageDraw.Draw(img)

    f_title = try_font(18)
    f_sub = try_font(14)
    f_lbl = try_font(12)
    f_val = try_font(15)
    f_epic = try_font(20, mono=True)

    # Header - Election Commission of India
    hdr_fill = (180, 30, 30) if is_blacklist else (20, 60, 120)
    draw.rectangle([0, 0, W, 75], fill=hdr_fill)
    draw.text((W // 2, 24), "ELECTION COMMISSION OF INDIA", font=f_title, fill="white", anchor="mm")
    draw.text((W // 2, 50), "ELECTORS PHOTO IDENTITY CARD", font=f_sub, fill=(220, 235, 255), anchor="mm")

    # Photo Box
    draw.rectangle([35, 100, 215, 310], fill=(220, 225, 235), outline=(70, 80, 100), width=2)
    draw.text((125, 205), "[ ELECTOR PHOTO ]", font=f_lbl, fill=(80, 90, 110), anchor="mm")

    # EPIC Number Badge
    draw.rectangle([35, 330, 215, 380], fill=(235, 240, 250), outline=(50, 80, 150), width=2)
    draw.text((125, 355), epic_num, font=f_epic, fill=(180, 30, 30) if is_blacklist else (15, 30, 80), anchor="mm")

    def fld(label, val, x, y):
        draw.text((x, y), label.upper(), font=f_lbl, fill=(90, 100, 120))
        draw.text((x, y + 16), str(val), font=f_val, fill=(15, 23, 42))

    rx = 250
    fld("Elector Name", name, rx, 105)
    fld("Father's / Husband's Name", father_name, rx, 155)
    fld("Gender", gender, rx, 205)
    fld("Date of Birth / Age", dob, rx + 200, 205)
    fld("Assembly Constituency", constituency, rx, 255)
    fld("Issuing Authority", authority, rx, 305)

    # Footer
    draw.line([20, 460, W - 20, 460], fill=(190, 200, 215), width=1)
    draw.text((W // 2, 490), "BHARAT NIRVACHAN AAYOG - ELECTORAL ROLL CREDENTIAL", font=try_font(12), fill=(100, 110, 130), anchor="mm")

    return img

# ─────────────────────────────────────────────────────────────────────────────
# 3. PAN CARD GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def create_pan_card_image(
    pan_num: str,
    name: str,
    father_name: str,
    dob: str,
    authority: str = "INCOME TAX DEPARTMENT, GOVT. OF INDIA",
    is_blacklist: bool = False,
    is_defective: bool = False,
) -> Image.Image:
    W, H = 850, 540
    img = Image.new("RGB", (W, H), (230, 245, 250))
    draw = ImageDraw.Draw(img)

    f_title = try_font(18)
    f_sub = try_font(13)
    f_lbl = try_font(12)
    f_val = try_font(15)
    f_pan = try_font(24, mono=True)

    # Header - Income Tax Department / Govt of India
    draw.rectangle([0, 0, W, 75], fill=(30, 60, 90))
    draw.text((W // 2, 24), "INCOME TAX DEPARTMENT", font=f_title, fill="white", anchor="mm")
    draw.text((W // 2, 50), "GOVT. OF INDIA / PERMANENT ACCOUNT NUMBER CARD", font=f_sub, fill=(200, 230, 255), anchor="mm")

    # Emblem placeholder
    draw.rectangle([35, 100, 110, 190], fill=(210, 225, 235), outline=(100, 130, 160), width=1)
    draw.text((72, 145), "[ EMBLEM ]", font=try_font(10), fill=(80, 100, 120), anchor="mm")

    # Hologram box
    draw.rectangle([W - 130, 100, W - 35, 190], fill=(220, 230, 210), outline=(140, 160, 120), width=1)
    draw.text((W - 82, 145), "[ HOLO ]", font=try_font(10), fill=(90, 110, 80), anchor="mm")

    def fld(label, val, x, y):
        draw.text((x, y), label.upper(), font=f_lbl, fill=(80, 100, 120))
        draw.text((x, y + 16), str(val), font=f_val, fill=(15, 25, 45))

    rx = 135
    fld("Permanent Account Number", "", rx, 100)
    # Highlighted PAN Number
    pan_fill = (180, 30, 30) if is_blacklist else (20, 40, 80)
    draw.text((rx, 118), pan_num, font=f_pan, fill=pan_fill)

    fld("Name", name, rx, 165)
    fld("Father's Name", father_name, rx, 215)
    fld("Date of Birth", dob, rx, 265)

    # Signature line
    draw.rectangle([W - 250, 310, W - 35, 370], fill=(245, 245, 245), outline=(150, 150, 150), width=1)
    draw.text((W - 142, 340), "[ SIGNATURE ]", font=f_lbl, fill=(120, 120, 120), anchor="mm")

    # Footer
    draw.line([20, 460, W - 20, 460], fill=(170, 195, 210), width=1)
    draw.text((W // 2, 490), "INCOME TAX DEPARTMENT - NATIONAL TAXPAYER IDENTIFICATION", font=try_font(11), fill=(80, 100, 120), anchor="mm")

    return img

def main():
    print("Generating synthetic assets for Aadhaar, Voter ID, and PAN Card...")

    # 1. AADHAAR
    a1 = create_aadhaar_image(
        id_formatted="8472 9103 8473",
        name="SNEHA PATEL",
        dob="18/09/1992",
        gender="FEMALE",
        address="42 BAKER STREET, NEW DELHI 110001",
    )
    save_to_destinations(a1, "aadhaar_official.jpg", "aadhaar")
    save_to_destinations(a1, "sample_aadhaar.jpg", "aadhaar")

    a2 = create_aadhaar_image(
        id_formatted="6541 2398 7101",
        name="TARIQ AHMED",
        dob="05/04/1980",
        gender="MALE",
        address="15 MARINE DRIVE, MUMBAI 400020",
        is_blacklist=True,
    )
    save_to_destinations(a2, "aadhaar_blacklist.jpg", "aadhaar")

    a3 = create_aadhaar_image(
        id_formatted="1234 5678 9999",
        name="DEVRAJ SINGH",
        dob="[MISSING DOB]",
        gender="MALE",
        address="[ADDRESS OMITTED]",
        is_defective=True,
    )
    save_to_destinations(a3, "aadhaar_defective.jpg", "aadhaar")

    # 2. VOTER ID
    v1 = create_voter_id_image(
        epic_num="ABC1234567",
        name="PRIYA KRISHNAMURTHY",
        father_name="KRISHNAMURTHY S",
        dob="15/04/1990",
        gender="FEMALE",
        constituency="120 - CHENNAI CENTRAL",
    )
    save_to_destinations(v1, "voter_id_official.jpg", "voter_id")
    save_to_destinations(v1, "sample_voter_id.jpg", "voter_id")

    v2 = create_voter_id_image(
        epic_num="XYZ7654321",
        name="RAHUL DEVANAND",
        father_name="DEVANAND R",
        dob="22/07/1985",
        gender="MALE",
        constituency="031 - MUMBAI SOUTH",
        is_blacklist=True,
    )
    save_to_destinations(v2, "voter_id_blacklist.jpg", "voter_id")

    v3 = create_voter_id_image(
        epic_num="INVALID-EPIC-99",
        name="UNKNOWN CITIZEN",
        father_name="[MISSING]",
        dob="[MISSING]",
        gender="MALE",
        constituency="[UNKNOWN CONSTITUENCY]",
        is_defective=True,
    )
    save_to_destinations(v3, "voter_id_defective.jpg", "voter_id")

    # 3. PAN CARD
    p1 = create_pan_card_image(
        pan_num="AABCP1234C",
        name="KAVITHA PRABHAKAR",
        father_name="PRABHAKAR N",
        dob="12/03/1988",
    )
    save_to_destinations(p1, "pan_card_official.jpg", "pan_card")
    save_to_destinations(p1, "sample_pan_card.jpg", "pan_card")

    p2 = create_pan_card_image(
        pan_num="AAAFT9999Z",
        name="SURESH FRAUDWALA",
        father_name="FAKE FATHER",
        dob="01/01/1975",
        is_blacklist=True,
    )
    save_to_destinations(p2, "pan_card_blacklist.jpg", "pan_card")

    p3 = create_pan_card_image(
        pan_num="PAN-123-INVALID",
        name="INVALID TAXPAYER",
        father_name="[MISSING]",
        dob="[MISSING]",
        is_defective=True,
    )
    save_to_destinations(p3, "pan_card_defective.jpg", "pan_card")

    print("\nAll Aadhaar, Voter ID, and PAN Card synthetic assets generated successfully!")

if __name__ == "__main__":
    main()
