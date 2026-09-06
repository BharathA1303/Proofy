"""
backend/app/main.py

FastAPI application factory.

Startup sequence:
  1. Configure CORS to allow the Vite dev server
  2. Register custom exception handlers
  3. Initialize the OCR engine (model loaded once, reused forever)
  4. Mount API routers
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.services.ocr import ocr_engine

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)


# ──────────────────────────────────────────────
#  Lifespan: startup / shutdown
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    On startup:
      - Initialize PaddleOCR engine (model weights downloaded on first run)

    On shutdown:
      - Log graceful shutdown (no explicit cleanup needed for PaddleOCR)
    """
    logger.info("DVS backend starting up (version=%s)", settings.APP_VERSION)

    try:
        ocr_engine.init_engine(
            lang=settings.OCR_LANG,
            use_angle_cls=settings.OCR_USE_ANGLE_CLS,
            use_gpu=settings.OCR_USE_GPU,
        )
        logger.info("OCR engine ready.")
    except Exception as exc:
        logger.critical("OCR engine failed to initialize: %s", exc)
        # Do not swallow — raise to prevent the server from accepting requests
        # with a broken OCR engine
        raise

    yield  # Application runs here

    logger.info("DVS backend shutting down.")


# ──────────────────────────────────────────────
#  Application factory
# ──────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Document Verification System — Backend API.\n\n"
        "Phase 1: Passport OCR Extraction (Module 1).\n"
        "Phase 2: Passport Document Validation (Module 2 — ICAO checksums, structure, VIZ<->MRZ binding).\n"
        "Phase 3: Tampering & Forensic Analysis (Module 3 — ELA, photo boundary, compression, metadata).\n"
        "Phase 4: Biometric Face Verification (Module 4 — SCRFD, ArcFace, MiniFASNetV2 PAD).\n"
        "Phase 5: Registry Verification Engine (Module 5 — Generic provider architecture, mock sandbox, field comparison).\n"
        "No final risk scoring or officer decision (Module 6 pending)."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)

# ── Exception handlers ────────────────────────────────────────────────────────
register_exception_handlers(app)

from app.api.v1.audit import router as audit_router  # noqa: E402
from app.api.v1.cases import router as cases_router  # noqa: E402
from app.api.v1.documents import router as documents_router  # noqa: E402
from app.api.v1.system import router as system_router  # noqa: E402
from app.api.v1.verification import router as verification_router  # noqa: E402

app.include_router(verification_router, prefix=settings.API_V1_PREFIX)
app.include_router(cases_router, prefix=settings.API_V1_PREFIX)
app.include_router(documents_router, prefix=settings.API_V1_PREFIX)
app.include_router(audit_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_router, prefix=settings.API_V1_PREFIX)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    """Returns server status and OCR engine readiness."""
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "ocr_engine_ready": ocr_engine.is_ready(),
    }
