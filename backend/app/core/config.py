"""
backend/app/core/config.py

Application configuration via Pydantic Settings.
Values can be overridden with environment variables or a .env file.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Guarantee Protobuf compatibility for PaddleOCR before any proto modules load
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # .../Product/backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Service identity
    APP_NAME: str = "Document Verification System — Backend"
    APP_VERSION: str = "1.0.0-phase12"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "demonstration"  # "development" | "demonstration" | "production"

    # Blockchain / Immutable Audit Ledger
    BLOCKCHAIN_ENABLED: bool = True
    BLOCKCHAIN_LEDGER_TYPE: str = "development"  # "development" | "permissioned" | "mock"
    BLOCKCHAIN_CHAIN_STORAGE_PATH: str = str(BASE_DIR / "app" / "data" / "blockchain_ledger.json")
    BLOCKCHAIN_AUTO_ANCHOR: bool = True

    # Multi-Document Case limits
    MAX_DOCUMENTS_PER_CASE: int = 10
    CASE_SESSION_TTL_SECONDS: int = 3600

    # Security / CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ]

    # File ingestion limits
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_MIME_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}
    ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}
    MAX_CAMERA_FRAME_SIZE_MB: int = 5

    # OCR engine
    OCR_USE_ANGLE_CLS: bool = True
    OCR_LANG: str = "en"
    OCR_USE_GPU: bool = False

    # Module 4 — Biometric Verification Configuration
    # NOTE: Biometric operating thresholds require calibration against representative
    # operational test cohorts for the target FAR/FRR profile.
    FACE_MATCH_THRESHOLD: float = 0.40
    FACE_DETECTION_CONFIDENCE_THRESHOLD: float = 0.50
    FACE_MIN_SIZE: int = 60
    FACE_MIN_LAPLACIAN_VAR: float = 35.0
    FACE_MIN_BRIGHTNESS: float = 35.0
    FACE_MAX_BRIGHTNESS: float = 230.0
    FACE_MIN_CONTRAST: float = 18.0

    # Presentation Attack Detection (Anti-Spoof) thresholds
    ANTI_SPOOF_THRESHOLD: float = 0.70
    ANTI_SPOOF_SUSPECT_THRESHOLD: float = 0.40

    # Pluggable Architecture & Model Paths
    BASE_DIR_PATH: str = str(BASE_DIR)
    FACE_DETECTOR_BACKEND: str = "scrfd"  # "scrfd" | "haar"
    SCRFD_MODEL_PATH: str = str(BASE_DIR / "app" / "models_weights" / "det_10g.onnx")
    YUNET_MODEL_PATH: str = str(BASE_DIR / "app" / "models_weights" / "face_detection_yunet_2023mar.onnx")
    
    FACE_EMBEDDING_MODEL: str = "arcface"  # "arcface"
    ARCFACE_MODEL_PATH: str = str(BASE_DIR / "app" / "models_weights" / "w600k_r50.onnx")

    ANTI_SPOOF_MODEL_NAME: str = "MiniFASNetV2"
    MINIFASNET_MODEL_PATH: str = str(BASE_DIR / "app" / "models_weights" / "2.7_80x80_MiniFASNetV2.pth")
    ANTI_SPOOF_MODEL_PATH: str = str(BASE_DIR / "app" / "models_weights" / "2.7_80x80_MiniFASNetV2.pth")
    MINIFASNET_SCALE: float = 2.7

    # Biometric in-memory session lifetime (seconds)
    BIOMETRIC_SESSION_TTL_SECONDS: int = 900

    # Module 5 — Registry Verification Configuration
    # Provider mode per document type.
    # Values: 'mock' | 'sandbox' | 'external'
    # Default: 'mock' for all types (never requires a real government API for local dev).
    REGISTRY_PROVIDER_MODE: str = "mock"
    REGISTRY_PROVIDER_PASSPORT: str = "mock"
    REGISTRY_PROVIDER_VISA: str = "mock"
    REGISTRY_PROVIDER_DL: str = "mock"
    REGISTRY_PROVIDER_NATIONAL_ID: str = "mock"
    REGISTRY_PROVIDER_BORDER_PERMIT: str = "mock"

    # Registry provider timeout settings (seconds).
    # A registry outage must NOT hang the entire border screening workflow.
    REGISTRY_CONNECT_TIMEOUT: float = 5.0
    REGISTRY_READ_TIMEOUT: float = 10.0
    REGISTRY_TOTAL_TIMEOUT: float = 15.0

    # Retry policy.
    # Do NOT blindly retry identity verification requests against external services.
    # Only safe transient failures qualify for retry.
    REGISTRY_MAX_RETRIES: int = 1

    # Registry session TTL (seconds) — same lifetime as biometric session.
    REGISTRY_SESSION_TTL_SECONDS: int = 900

    # Module 6 — Risk Engine Configuration
    # All thresholds and caps configurable via environment variables.
    RISK_CONFIG_VERSION: str = "0.6.0"

    # Risk level thresholds (score → level)
    RISK_THRESHOLD_MEDIUM:   int = 25
    RISK_THRESHOLD_HIGH:     int = 50
    RISK_THRESHOLD_CRITICAL: int = 75

    # Risk session TTL (seconds) — same lifetime as other session stores.
    RISK_SESSION_TTL_SECONDS: int = 900

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()

