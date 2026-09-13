"""
backend/tests/test_machine_readable_qr.py

Comprehensive Test Suite for Generic Machine-Readable and QR Intelligence (Phase 7).
Tests all requirements across Scenarios A through AG:
  A: Clean QR code detected and decoded
  B: Blurred / corrupted QR code returns DETECTED_NOT_DECODABLE
  C: Image with no QR code returns NOT_DETECTED
  D: Multiple QR codes on image with primary selection
  E: QR on incorrect document side generates warning
  F: QR outside expected region generates warning
  G: JSON payload parsing to canonical fields
  H: Pipe-delimited key-value payload parsing
  I: Semicolon-delimited key-value payload parsing
  J: Positional pipe-delimited payload parsing
  K: XML payload parsing
  L: Malformed / unparseable payload handling without crash
  M: Binary / non-UTF8 payload handling and SHA-256 hashing
  N: Perfect OCR <-> QR match (ALL_MATCHED)
  O: License number mismatch (MISMATCH_DETECTED)
  P: Holder name mismatch
  Q: DOB mismatch
  R: Validity dates mismatch
  S: Vehicle classes (COV) mismatch
  T: Date format normalization (ISO vs DD/MM/YYYY)
  U: Name whitespace and case tolerance
  V: DL number hyphen and space formatting tolerance
  W: Field present in QR but missing in OCR
  X: Field present in OCR but missing in QR
  Y: Cryptographic verification not configured
  Z: Cryptographic verification unavailable for DL (Sarathi / MoRTH)
  AA: Genuine RSA digital signature verification PASSED
  AB: Genuine RSA digital signature verification FAILED (tampered data)
  AC: Genuine ECDSA digital signature verification PASSED
  AD: Genuine ECDSA digital signature verification FAILED
  AE: Independence of sources: OCR fields remain untouched
  AF: Profile marked not applicable returns NOT_APPLICABLE
  AG: Full end-to-end processing via MachineReadableService
"""
import copy
from datetime import datetime
import json
import numpy as np
import pytest
import cv2
import qrcode
from PIL import Image

from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
from cryptography.hazmat.primitives import hashes, serialization

from app.services.document_intelligence.schema import NormalizedBBox
from app.services.machine_readable.decoder import QRDecoder
from app.services.machine_readable.detector import QRDetector
from app.services.machine_readable.parser import GenericPayloadParser
from app.services.machine_readable.schema import (
    CryptoVerificationStatus,
    FieldComparisonStatus,
    MachineReadableResult,
    OverallMatchStatus,
    ParsedQRPayload,
    QRCandidate,
    QRDetectionStatus,
    QRPayloadType,
)
from app.services.machine_readable.service import MachineReadableService
from app.services.machine_readable.verifier import MachineReadableVerifier


# ==============================================================================
# Test Fixtures & Helpers
# ==============================================================================

def create_synthetic_qr(payload: str) -> np.ndarray:
    """Create a clean BGR numpy image containing the encoded QR payload."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    rgb = np.array(img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def create_card_with_qr(
    qr_img: np.ndarray,
    x_norm: float = 0.60,
    y_norm: float = 0.30,
    card_w: int = 800,
    card_h: int = 500,
) -> np.ndarray:
    """Embed a QR code into a synthetic credential card canvas."""
    canvas = np.ones((card_h, card_w, 3), dtype=np.uint8) * 245  # Off-white card
    target_w = int(card_w * 0.30)
    target_h = int(card_h * 0.45)
    qr_resized = cv2.resize(qr_img, (target_w, target_h))

    x_start = int(card_w * x_norm)
    y_start = int(card_h * y_norm)
    canvas[y_start : y_start + target_h, x_start : x_start + target_w] = qr_resized
    return canvas


def generate_rsa_keypair():
    priv = rsa.generate_private_key(65537, 2048)
    pub = priv.public_key()
    pub_pem = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return priv, pub_pem


def generate_ecdsa_keypair():
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = priv.public_key()
    pub_pem = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return priv, pub_pem


# ==============================================================================
# Unit & Integration Tests
# ==============================================================================

class TestMachineReadableQR:

    @pytest.fixture
    def detector(self):
        return QRDetector()

    @pytest.fixture
    def decoder(self):
        return QRDecoder()

    @pytest.fixture
    def parser(self):
        return GenericPayloadParser()

    @pytest.fixture
    def verifier(self):
        return MachineReadableVerifier()

    @pytest.fixture
    def service(self):
        return MachineReadableService()

    # --------------------------------------------------------------------------
    # Scenario A: Clean QR Code Detected and Decoded
    # --------------------------------------------------------------------------
    def test_a_clean_qr_detected_and_decoded(self, detector):
        payload = "DLNO: DL-1420110012345|NAME: RAHUL SHARMA|DOB: 15-08-1990"
        qr_img = create_synthetic_qr(payload)
        card = create_card_with_qr(qr_img, x_norm=0.60, y_norm=0.30)

        status, candidates, primary, warnings = detector.detect_and_decode(
            image_input=card,
            expected_region=NormalizedBBox(0.60, 0.30, 0.35, 0.50),
            side="back",
            expected_side="back",
        )

        assert status == QRDetectionStatus.DECODED
        assert len(candidates) >= 1
        assert primary is not None
        assert primary.status == QRDetectionStatus.DECODED
        assert primary.raw_payload == payload
        assert primary.is_primary is True
        assert primary.bbox.width > 0.15

    # --------------------------------------------------------------------------
    # Scenario B: Blurred / Corrupted QR Returns DETECTED_NOT_DECODABLE
    # --------------------------------------------------------------------------
    def test_b_blurred_corrupted_qr_detected_not_decodable(self, detector):
        payload = "DLNO: DL-1420110012345|NAME: RAHUL SHARMA|DOB: 15-08-1990|VALID_TO: 14-08-2030"
        qr_img = create_synthetic_qr(payload)
        # Apply substantial Gaussian blur to destroy error correction while keeping finder patterns
        blurred = cv2.GaussianBlur(qr_img, (31, 31), 0)

        status, candidates, primary, warnings = detector.detect_and_decode(blurred)

        # Either detected but undecodable, or completely destroyed
        assert status in (QRDetectionStatus.DETECTED_NOT_DECODABLE, QRDetectionStatus.NOT_DETECTED)
        if status == QRDetectionStatus.DETECTED_NOT_DECODABLE:
            assert primary is not None
            assert primary.status == QRDetectionStatus.DETECTED_NOT_DECODABLE
            assert primary.raw_payload is None
            assert "decoding failed" in primary.error_message.lower()

    # --------------------------------------------------------------------------
    # Scenario C: Image with No QR Code Returns NOT_DETECTED
    # --------------------------------------------------------------------------
    def test_c_no_qr_present_not_detected(self, detector):
        blank_card = np.ones((500, 800, 3), dtype=np.uint8) * 240
        status, candidates, primary, warnings = detector.detect_and_decode(blank_card)

        assert status == QRDetectionStatus.NOT_DETECTED
        assert len(candidates) == 0
        assert primary is None

    # --------------------------------------------------------------------------
    # Scenario D: Multiple QR Codes with Primary Selection
    # --------------------------------------------------------------------------
    def test_d_multiple_qr_codes_on_image(self, detector):
        q1 = create_synthetic_qr("CODE_ONE_PRIMARY")
        q2 = create_synthetic_qr("CODE_TWO_SECONDARY")

        canvas = np.ones((600, 1000, 3), dtype=np.uint8) * 255
        # Place Q1 in bottom right (near expected DL region)
        q1_res = cv2.resize(q1, (250, 250))
        canvas[300:550, 650:900] = q1_res

        # Place Q2 in top left
        q2_res = cv2.resize(q2, (200, 200))
        canvas[50:250, 50:250] = q2_res

        status, candidates, primary, warnings = detector.detect_and_decode(
            image_input=canvas,
            expected_region=NormalizedBBox(0.60, 0.30, 0.35, 0.50),
        )

        assert status == QRDetectionStatus.DECODED
        assert len(candidates) >= 2
        assert any("Multiple QR codes detected" in w for w in warnings)
        assert primary is not None
        # Primary should be the one in the expected region
        assert primary.raw_payload == "CODE_ONE_PRIMARY"

    # --------------------------------------------------------------------------
    # Scenario E: QR on Incorrect Side Generates Warning
    # --------------------------------------------------------------------------
    def test_e_qr_wrong_side_warning(self, detector):
        qr_img = create_synthetic_qr("DL-1420110012345")
        status, candidates, primary, warnings = detector.detect_and_decode(
            image_input=qr_img,
            side="front",
            expected_side="back",
        )
        assert status == QRDetectionStatus.DECODED
        assert any("document face is 'front', but expected side is 'back'" in w for w in warnings)

    # --------------------------------------------------------------------------
    # Scenario F: QR Outside Expected Region Generates Warning
    # --------------------------------------------------------------------------
    def test_f_qr_outside_expected_region_warning(self, detector):
        qr_img = create_synthetic_qr("DL-1420110012345")
        # Place QR in top-left: x=0.05, y=0.05
        card = create_card_with_qr(qr_img, x_norm=0.05, y_norm=0.05)

        status, candidates, primary, warnings = detector.detect_and_decode(
            image_input=card,
            expected_region=NormalizedBBox(0.60, 0.30, 0.35, 0.50),
        )
        assert status == QRDetectionStatus.DECODED
        assert any("detected outside expected profile region" in w for w in warnings)

    # --------------------------------------------------------------------------
    # Scenario G: JSON Payload Parsing
    # --------------------------------------------------------------------------
    def test_g_json_payload_parsing(self, parser):
        payload = json.dumps({
            "dl_no": "DL-1420110012345",
            "name": "Rahul Sharma",
            "dob": "1990-08-15",
            "valid_from": "2011-05-10",
            "valid_to": "2031-05-09",
            "cov": "LMV, MCWG",
            "blood_group": "B+",
        })
        parsed = parser.parse(payload, "hash123")

        assert parsed.payload_type == QRPayloadType.JSON
        assert parsed.canonical_fields["license_number"] == "DL-1420110012345"
        assert parsed.canonical_fields["name"] == "Rahul Sharma"
        assert parsed.canonical_fields["dob"] == "1990-08-15"
        assert parsed.canonical_fields["valid_from"] == "2011-05-10"
        assert parsed.canonical_fields["valid_to"] == "2031-05-09"
        assert parsed.canonical_fields["cov"] == "LMV, MCWG"
        assert parsed.canonical_fields["blood_group"] == "B+"

    # --------------------------------------------------------------------------
    # Scenario H: Pipe-Delimited Key-Value Parsing
    # --------------------------------------------------------------------------
    def test_h_pipe_delimited_key_value_parsing(self, parser):
        payload = "DLNO: DL-1420110012345|NAME: RAHUL SHARMA|DOB: 15-08-1990|VALID_TO: 14-08-2030|COV: LMV"
        parsed = parser.parse(payload, "hash123")

        assert parsed.payload_type == QRPayloadType.DELIMITED_KEY_VALUE
        assert parsed.canonical_fields["license_number"] == "DL-1420110012345"
        assert parsed.canonical_fields["name"] == "RAHUL SHARMA"
        assert parsed.canonical_fields["dob"] == "15-08-1990"
        assert parsed.canonical_fields["valid_to"] == "14-08-2030"
        assert parsed.canonical_fields["cov"] == "LMV"

    # --------------------------------------------------------------------------
    # Scenario I: Semicolon-Delimited Key-Value Parsing
    # --------------------------------------------------------------------------
    def test_i_semicolon_delimited_key_value_parsing(self, parser):
        payload = "dl_number=DL1420110012345;holder_name=Rahul Sharma;dob=15/08/1990;expiry=2030-08-14"
        parsed = parser.parse(payload, "hash123")

        assert parsed.payload_type == QRPayloadType.DELIMITED_KEY_VALUE
        assert parsed.canonical_fields["license_number"] == "DL1420110012345"
        assert parsed.canonical_fields["name"] == "Rahul Sharma"
        assert parsed.canonical_fields["dob"] == "15/08/1990"
        assert parsed.canonical_fields["valid_to"] == "2030-08-14"

    # --------------------------------------------------------------------------
    # Scenario J: Positional Pipe Payload Parsing
    # --------------------------------------------------------------------------
    def test_j_positional_pipe_payload_parsing(self, parser):
        payload = "DL-1420110012345|RAHUL SHARMA|15-08-1990|10-05-2011|09-05-2031|LMV, MCWG"
        parsed = parser.parse(payload, "hash123")

        assert parsed.payload_type == QRPayloadType.POSITIONAL_DELIMITED
        assert parsed.canonical_fields["license_number"] == "DL-1420110012345"
        assert parsed.canonical_fields["name"] == "RAHUL SHARMA"
        assert parsed.canonical_fields["dob"] == "15-08-1990"
        assert parsed.canonical_fields["valid_from"] == "10-05-2011"
        assert parsed.canonical_fields["valid_to"] == "09-05-2031"
        assert parsed.canonical_fields["cov"] == "LMV, MCWG"

    # --------------------------------------------------------------------------
    # Scenario K: XML Payload Parsing
    # --------------------------------------------------------------------------
    def test_k_xml_payload_parsing(self, parser):
        payload = '<DLData license_no="DL-1420110012345" name="Rahul Sharma" dob="15-08-1990" cov="LMV"/>'
        parsed = parser.parse(payload, "hash123")

        assert parsed.payload_type == QRPayloadType.XML
        assert parsed.canonical_fields["license_number"] == "DL-1420110012345"
        assert parsed.canonical_fields["name"] == "Rahul Sharma"
        assert parsed.canonical_fields["dob"] == "15-08-1990"
        assert parsed.canonical_fields["cov"] == "LMV"

    # --------------------------------------------------------------------------
    # Scenario L: Malformed / Unparseable Payload
    # --------------------------------------------------------------------------
    def test_l_malformed_unparseable_payload(self, parser):
        payload = "???Random-Garbage-String-12345!@#$"
        parsed = parser.parse(payload, "hash123")

        assert parsed.payload_type == QRPayloadType.PLAIN_TEXT
        assert parsed.canonical_fields == {}
        assert parsed.raw_fields["raw"] == payload

    # --------------------------------------------------------------------------
    # Scenario M: Binary / Non-UTF8 Payload Handling
    # --------------------------------------------------------------------------
    def test_m_binary_non_utf8_payload_handling(self, decoder):
        # Non-UTF-8 binary bytes
        bad_bytes = b"\x80\x81\xFF\xFE\x00\x01BinaryData"
        text, sha256_hash, ptype, err = decoder.decode_raw(raw_bytes=bad_bytes)

        assert ptype == QRPayloadType.BINARY
        assert text is None
        assert len(sha256_hash) == 64
        assert "non-utf8 binary" in err.lower()

    # --------------------------------------------------------------------------
    # Scenario N: Perfect OCR <-> QR Match (ALL_MATCHED)
    # --------------------------------------------------------------------------
    def test_n_perfect_ocr_qr_match(self, verifier):
        ocr_data = {
            "license_number": "DL-14 20110012345",
            "name": "RAHUL SHARMA",
            "dob": "15-08-1990",
            "valid_from": "10-05-2011",
            "valid_to": "09-05-2031",
            "cov": "LMV, MCWG",
        }
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="...",
            payload_sha256="hash",
            canonical_fields={
                "license_number": "DL-1420110012345",
                "name": "Rahul Sharma",
                "dob": "1990-08-15",
                "valid_from": "2011-05-10",
                "valid_to": "2031-05-09",
                "cov": "MCWG, LMV",
            },
        )
        results, overall, warnings = verifier.cross_check(ocr_data, parsed_qr)

        assert overall == OverallMatchStatus.ALL_MATCHED
        assert len(warnings) == 0
        for f, res in results.items():
            assert res.status == FieldComparisonStatus.QR_FIELD_MATCH
            assert res.is_match is True

    # --------------------------------------------------------------------------
    # Scenario O: Mismatch in License Number
    # --------------------------------------------------------------------------
    def test_o_mismatch_license_number(self, verifier):
        ocr_data = {"license_number": "DL-1420110012345", "name": "Rahul Sharma"}
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="...",
            payload_sha256="hash",
            canonical_fields={"license_number": "DL-1420110099999", "name": "Rahul Sharma"},
        )
        results, overall, warnings = verifier.cross_check(ocr_data, parsed_qr, ["license_number", "name"])

        assert overall == OverallMatchStatus.MISMATCH_DETECTED
        assert results["license_number"].status == FieldComparisonStatus.QR_FIELD_MISMATCH
        assert results["license_number"].is_match is False
        assert results["name"].status == FieldComparisonStatus.QR_FIELD_MATCH

    # --------------------------------------------------------------------------
    # Scenario P: Mismatch in Holder Name
    # --------------------------------------------------------------------------
    def test_p_mismatch_holder_name(self, verifier):
        ocr_data = {"name": "RAHUL SHARMA"}
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="...",
            payload_sha256="hash",
            canonical_fields={"name": "AMIT VERMA"},
        )
        results, overall, warnings = verifier.cross_check(ocr_data, parsed_qr, ["name"])

        assert results["name"].status == FieldComparisonStatus.QR_FIELD_MISMATCH
        assert overall == OverallMatchStatus.MISMATCH_DETECTED

    # --------------------------------------------------------------------------
    # Scenario Q: Mismatch in DOB
    # --------------------------------------------------------------------------
    def test_q_mismatch_dob(self, verifier):
        ocr_data = {"dob": "15/08/1990"}
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="...",
            payload_sha256="hash",
            canonical_fields={"dob": "20/12/1992"},
        )
        results, overall, warnings = verifier.cross_check(ocr_data, parsed_qr, ["dob"])

        assert results["dob"].status == FieldComparisonStatus.QR_FIELD_MISMATCH

    # --------------------------------------------------------------------------
    # Scenario R: Mismatch in Validity Dates
    # --------------------------------------------------------------------------
    def test_r_mismatch_validity_dates(self, verifier):
        ocr_data = {"valid_to": "2031-05-09"}
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="...",
            payload_sha256="hash",
            canonical_fields={"valid_to": "2025-05-09"},
        )
        results, overall, warnings = verifier.cross_check(ocr_data, parsed_qr, ["valid_to"])

        assert results["valid_to"].status == FieldComparisonStatus.QR_FIELD_MISMATCH

    # --------------------------------------------------------------------------
    # Scenario S: Mismatch in COV
    # --------------------------------------------------------------------------
    def test_s_mismatch_cov(self, verifier):
        ocr_data = {"cov": "LMV"}
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="...",
            payload_sha256="hash",
            canonical_fields={"cov": "TRANS, HGMV"},
        )
        results, overall, warnings = verifier.cross_check(ocr_data, parsed_qr, ["cov"])

        assert results["cov"].status == FieldComparisonStatus.QR_FIELD_MISMATCH

    # --------------------------------------------------------------------------
    # Scenario T: Date Format Normalization
    # --------------------------------------------------------------------------
    def test_t_date_format_normalization(self, verifier):
        ocr_data = {"dob": "15/08/1990"}
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="...",
            payload_sha256="hash",
            canonical_fields={"dob": "1990-08-15"},
        )
        results, overall, warnings = verifier.cross_check(ocr_data, parsed_qr, ["dob"])

        assert results["dob"].status == FieldComparisonStatus.QR_FIELD_MATCH
        assert results["dob"].is_match is True

    # --------------------------------------------------------------------------
    # Scenario U: Name Whitespace and Case Tolerance
    # --------------------------------------------------------------------------
    def test_u_name_formatting_tolerance(self, verifier):
        ocr_data = {"name": "rahul    sharma  "}
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="...",
            payload_sha256="hash",
            canonical_fields={"name": "RAHUL SHARMA"},
        )
        results, overall, warnings = verifier.cross_check(ocr_data, parsed_qr, ["name"])

        assert results["name"].status == FieldComparisonStatus.QR_FIELD_MATCH

    # --------------------------------------------------------------------------
    # Scenario V: DL Number Formatting Tolerance
    # --------------------------------------------------------------------------
    def test_v_dl_number_formatting_tolerance(self, verifier):
        ocr_data = {"license_number": "DL-14  2011-0012345"}
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="...",
            payload_sha256="hash",
            canonical_fields={"license_number": "DL1420110012345"},
        )
        results, overall, warnings = verifier.cross_check(ocr_data, parsed_qr, ["license_number"])

        assert results["license_number"].status == FieldComparisonStatus.QR_FIELD_MATCH

    # --------------------------------------------------------------------------
    # Scenario W: Field Present in QR Missing in OCR
    # --------------------------------------------------------------------------
    def test_w_field_present_in_qr_missing_in_ocr(self, verifier):
        ocr_data = {"license_number": "DL-1420110012345"}
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="...",
            payload_sha256="hash",
            canonical_fields={"license_number": "DL-1420110012345", "blood_group": "O+"},
        )
        results, overall, warnings = verifier.cross_check(ocr_data, parsed_qr, ["license_number", "blood_group"])

        assert results["blood_group"].status == FieldComparisonStatus.QR_FIELD_MISSING
        assert "absent in OCR" in results["blood_group"].details

    # --------------------------------------------------------------------------
    # Scenario X: Field Present in OCR Missing in QR
    # --------------------------------------------------------------------------
    def test_x_field_present_in_ocr_missing_in_qr(self, verifier):
        ocr_data = {"license_number": "DL-1420110012345", "cov": "LMV"}
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="...",
            payload_sha256="hash",
            canonical_fields={"license_number": "DL-1420110012345"},
        )
        results, overall, warnings = verifier.cross_check(ocr_data, parsed_qr, ["license_number", "cov"])

        assert results["cov"].status == FieldComparisonStatus.QR_FIELD_MISSING
        assert "absent in QR" in results["cov"].details

    # --------------------------------------------------------------------------
    # Scenario Y: Cryptographic Verification Not Configured
    # --------------------------------------------------------------------------
    def test_y_crypto_verification_not_configured(self, verifier):
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="{}",
            payload_sha256="hash",
        )
        crypto_config = {
            "supported": False,
            "status": "CRYPTO_VERIFICATION_NOT_CONFIGURED",
            "reason": "No cryptographic verification configured for this credential",
        }
        res = verifier.verify_cryptographic_signature(parsed_qr, crypto_config)

        assert res.status == CryptoVerificationStatus.CRYPTO_VERIFICATION_NOT_CONFIGURED

    # --------------------------------------------------------------------------
    # Scenario Z: Cryptographic Verification Unavailable for Indian DL
    # --------------------------------------------------------------------------
    def test_z_crypto_verification_unavailable_for_dl(self, verifier):
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text="{}",
            payload_sha256="hash",
        )
        dl_crypto_config = {
            "supported": False,
            "status": "CRYPTO_VERIFICATION_UNAVAILABLE",
            "reason": "No public key infrastructure published by MoRTH/Sarathi for offline QR verification",
        }
        res = verifier.verify_cryptographic_signature(parsed_qr, dl_crypto_config)

        assert res.status == CryptoVerificationStatus.CRYPTO_VERIFICATION_UNAVAILABLE
        assert "MoRTH/Sarathi" in res.details

    # --------------------------------------------------------------------------
    # Scenario AA: Genuine RSA Signature Verification PASSED
    # --------------------------------------------------------------------------
    def test_aa_genuine_rsa_signature_passed(self, verifier):
        priv_key, pub_pem = generate_rsa_keypair()
        payload_text = '{"dl_no":"DL-1420110012345","name":"Rahul Sharma"}'
        sig = priv_key.sign(payload_text.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        sig_hex = sig.hex()

        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text=payload_text,
            payload_sha256="hash",
            signature_data={"signature": sig_hex},
        )
        res = verifier.verify_cryptographic_signature(
            parsed_qr,
            crypto_config={"supported": True, "public_key": pub_pem},
        )

        assert res.status == CryptoVerificationStatus.CRYPTO_VERIFICATION_PASSED
        assert res.signature_present is True
        assert "RSA" in res.algorithm

    # --------------------------------------------------------------------------
    # Scenario AB: Genuine RSA Signature Verification FAILED (Tampered Data)
    # --------------------------------------------------------------------------
    def test_ab_genuine_rsa_signature_failed(self, verifier):
        priv_key, pub_pem = generate_rsa_keypair()
        payload_text = '{"dl_no":"DL-1420110012345","name":"Rahul Sharma"}'
        sig = priv_key.sign(payload_text.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        sig_hex = sig.hex()

        # Tamper with text after signing!
        tampered_text = '{"dl_no":"DL-1420110099999","name":"Rahul Sharma"}'
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text=tampered_text,
            payload_sha256="hash",
            signature_data={"signature": sig_hex},
        )
        res = verifier.verify_cryptographic_signature(
            parsed_qr,
            crypto_config={"supported": True, "public_key": pub_pem},
        )

        assert res.status == CryptoVerificationStatus.CRYPTO_VERIFICATION_FAILED
        assert res.signature_present is True

    # --------------------------------------------------------------------------
    # Scenario AC: Genuine ECDSA Signature Verification PASSED
    # --------------------------------------------------------------------------
    def test_ac_genuine_ecdsa_signature_passed(self, verifier):
        priv_key, pub_pem = generate_ecdsa_keypair()
        payload_text = '{"dl_no":"DL-1420110012345"}'
        sig = priv_key.sign(payload_text.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        sig_hex = sig.hex()

        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text=payload_text,
            payload_sha256="hash",
            signature_data={"signature": sig_hex},
        )
        res = verifier.verify_cryptographic_signature(
            parsed_qr,
            crypto_config={"supported": True, "public_key": pub_pem},
        )

        assert res.status == CryptoVerificationStatus.CRYPTO_VERIFICATION_PASSED
        assert res.signature_present is True
        assert "ECDSA" in res.algorithm

    # --------------------------------------------------------------------------
    # Scenario AD: Genuine ECDSA Signature Verification FAILED
    # --------------------------------------------------------------------------
    def test_ad_genuine_ecdsa_signature_failed(self, verifier):
        priv_key, pub_pem = generate_ecdsa_keypair()
        payload_text = '{"dl_no":"DL-1420110012345"}'
        sig = priv_key.sign(payload_text.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        sig_hex = sig.hex()

        # Tampered text
        tampered_text = '{"dl_no":"DL-9999999999999"}'
        parsed_qr = ParsedQRPayload(
            payload_type=QRPayloadType.JSON,
            raw_text=tampered_text,
            payload_sha256="hash",
            signature_data={"signature": sig_hex},
        )
        res = verifier.verify_cryptographic_signature(
            parsed_qr,
            crypto_config={"supported": True, "public_key": pub_pem},
        )

        assert res.status == CryptoVerificationStatus.CRYPTO_VERIFICATION_FAILED

    # --------------------------------------------------------------------------
    # Scenario AE: Independence of Sources: OCR Fields Preserved
    # --------------------------------------------------------------------------
    def test_ae_independence_check_ocr_preserved(self, service):
        original_ocr = {
            "license_number": "DL-1420110012345",
            "name": "ORIGINAL OCR NAME",
            "dob": "1990-08-15",
        }
        ocr_copy = copy.deepcopy(original_ocr)

        # Process with mismatched QR payload
        res = service.process(
            raw_payload_text='{"dl_no":"DL-1420110099999","name":"DIFFERENT QR NAME"}',
            document_type="driving_license",
            ocr_data=ocr_copy,
        )

        # Verify OCR dictionary was NOT mutated
        assert ocr_copy == original_ocr
        # Verify discrepancy was recorded as evidence, not overwritten
        assert res.field_cross_checks["license_number"].status == FieldComparisonStatus.QR_FIELD_MISMATCH
        assert res.field_cross_checks["name"].status == FieldComparisonStatus.QR_FIELD_MISMATCH
        assert res.overall_match_status == OverallMatchStatus.MISMATCH_DETECTED

    # --------------------------------------------------------------------------
    # Scenario AF: Profile Marked Not Applicable Returns NOT_APPLICABLE
    # --------------------------------------------------------------------------
    def test_af_profile_disabled_not_applicable(self, service):
        res = service.process(
            raw_payload_text="SOME_PAYLOAD",
            profile_override={"applicable": False},
        )
        assert res.applicable is False
        assert res.detection_status == QRDetectionStatus.NOT_APPLICABLE
        assert res.overall_match_status == OverallMatchStatus.NOT_APPLICABLE

    # --------------------------------------------------------------------------
    # Scenario AG: Full End-to-End Processing via MachineReadableService
    # --------------------------------------------------------------------------
    def test_ag_full_end_to_end_machine_readable_service(self, service):
        payload = "DLNO: DL-1420110012345|NAME: RAHUL SHARMA|DOB: 15-08-1990|VALID_TO: 14-08-2030|COV: LMV"
        qr_img = create_synthetic_qr(payload)
        card = create_card_with_qr(qr_img, x_norm=0.65, y_norm=0.35)

        ocr_data = {
            "license_number": "DL1420110012345",
            "name": "Rahul Sharma",
            "dob": "1990-08-15",
            "valid_to": "2030-08-14",
            "cov": "LMV",
        }

        res = service.process(
            image_input=card,
            document_type="driving_license",
            ocr_data=ocr_data,
            side="back",
        )

        assert res.applicable is True
        assert res.detection_status == QRDetectionStatus.DECODED
        assert res.primary_qr is not None
        assert res.primary_qr.is_primary is True
        assert res.parsed_payload is not None
        assert res.parsed_payload.canonical_fields["license_number"] == "DL-1420110012345"
        assert res.overall_match_status == OverallMatchStatus.ALL_MATCHED
        assert res.crypto_verification.status == CryptoVerificationStatus.CRYPTO_VERIFICATION_UNAVAILABLE

        # Check serialization works
        as_dict = res.to_dict()
        assert as_dict["detection_status"] == "DECODED"
        assert as_dict["overall_match_status"] == "ALL_MATCHED"
        assert "license_number" in as_dict["field_cross_checks"]
