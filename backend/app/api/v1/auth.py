"""
backend/app/api/v1/auth.py

Meiyari Officer Account Authentication API.

Replaces the previous browser-only auth (plaintext credentials in
localStorage) with server-side encrypted storage:
  - Passwords: PBKDF2-HMAC-SHA256 salted hash (one-way).
  - Names / emails / usernames / TOTP secrets: Fernet field encryption at rest.
  - Officer accounts live in their own `meiyari_users` table, fully separate
    from the government registry tables.

Flow:
  POST /auth/register/start     -> generates TOTP secret + QR URI (not yet persisted)
  POST /auth/register/complete  -> verifies TOTP code, persists the account
  POST /auth/login              -> verifies username/email + password
  POST /auth/login/verify-mfa   -> verifies TOTP code, returns officer session
"""
from __future__ import annotations

import logging
import secrets
import time
import uuid
from typing import Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.exceptions import (
    AccountAlreadyExistsError,
    InvalidCredentialsError,
    InvalidMfaCodeError,
    RegistrationSessionExpiredError,
)
from app.services.auth.totp import verify_totp
from app.services.auth.users_db import meiyari_users_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ──────────────────────────────────────────────
#  Pending registration store (server-side, short-lived, in-memory)
#
#  Holds the freshly generated TOTP secret between "start" and "complete"
#  so it never has to be round-tripped to the client or written to
#  localStorage before the account is actually confirmed.
# ──────────────────────────────────────────────
_PENDING_REGISTRATIONS: Dict[str, dict] = {}
_PENDING_TTL_SECONDS = 600


def _prune_expired_registrations() -> None:
    now = time.time()
    expired = [token for token, entry in _PENDING_REGISTRATIONS.items() if now - entry["created_at"] > _PENDING_TTL_SECONDS]
    for token in expired:
        _PENDING_REGISTRATIONS.pop(token, None)


# ──────────────────────────────────────────────
#  Base32 secret generation (server-side, cryptographically secure)
# ──────────────────────────────────────────────
_BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def _generate_base32_secret(length: int = 16) -> str:
    return "".join(secrets.choice(_BASE32_ALPHABET) for _ in range(length))


def _build_otpauth_uri(account_name: str, secret: str, issuer: str = "Meiyari") -> str:
    from urllib.parse import quote

    clean_account = quote(account_name.strip() or "user")
    clean_issuer = quote(issuer.strip() or "Meiyari")
    return f"otpauth://totp/{clean_issuer}:{clean_account}?secret={secret}&issuer={clean_issuer}&algorithm=SHA1&digits=6&period=30"


# ──────────────────────────────────────────────
#  Request / response schemas
# ──────────────────────────────────────────────

class RegisterStartRequest(BaseModel):
    fullName: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=6)


class RegisterStartResponse(BaseModel):
    registrationToken: str
    secret: str
    qrUri: str


class RegisterCompleteRequest(BaseModel):
    registrationToken: str
    code: str


class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    mfaRequired: bool = True
    loginToken: str


class VerifyMfaRequest(BaseModel):
    loginToken: str
    code: str


class OfficerProfile(BaseModel):
    id: str
    name: str
    username: str
    email: str
    role: str
    station: str
    clearanceLevel: str
    mfaEnabled: bool


# ──────────────────────────────────────────────
#  Registration
# ──────────────────────────────────────────────

@router.post("/register/start", response_model=RegisterStartResponse, status_code=status.HTTP_200_OK)
async def register_start(payload: RegisterStartRequest) -> RegisterStartResponse:
    """Step 1: validate new-account fields and issue a TOTP secret + QR code."""
    _prune_expired_registrations()

    clean_username = payload.username.strip().lower()
    clean_email = payload.email.strip().lower()

    if meiyari_users_db.find_by_identifier(clean_username) or meiyari_users_db.find_by_identifier(clean_email):
        raise AccountAlreadyExistsError()

    secret = _generate_base32_secret(16)
    qr_uri = _build_otpauth_uri(clean_username, secret, "Meiyari")

    registration_token = uuid.uuid4().hex
    _PENDING_REGISTRATIONS[registration_token] = {
        "created_at": time.time(),
        "full_name": payload.fullName.strip(),
        "username": clean_username,
        "email": clean_email,
        "password": payload.password,
        "secret": secret,
    }

    return RegisterStartResponse(registrationToken=registration_token, secret=secret, qrUri=qr_uri)


@router.post("/register/complete", response_model=OfficerProfile, status_code=status.HTTP_201_CREATED)
async def register_complete(payload: RegisterCompleteRequest) -> OfficerProfile:
    """Step 2: verify the 6-digit TOTP code and persist the encrypted officer account."""
    _prune_expired_registrations()

    entry = _PENDING_REGISTRATIONS.get(payload.registrationToken)
    if not entry:
        raise RegistrationSessionExpiredError()

    if not verify_totp(payload.code, entry["secret"]):
        raise InvalidMfaCodeError()

    try:
        officer = meiyari_users_db.create_user(
            public_id=f"USR-{secrets.randbelow(900) + 100}",
            full_name=entry["full_name"],
            username=entry["username"],
            email=entry["email"],
            plain_password=entry["password"],
            mfa_secret=entry["secret"],
        )
    except ValueError:
        raise AccountAlreadyExistsError()
    finally:
        _PENDING_REGISTRATIONS.pop(payload.registrationToken, None)

    return OfficerProfile(**officer)


# ──────────────────────────────────────────────
#  Login
# ──────────────────────────────────────────────

# Pending MFA logins: loginToken -> identifier, short-lived in-memory.
_PENDING_LOGINS: Dict[str, dict] = {}
_LOGIN_TTL_SECONDS = 300


def _prune_expired_logins() -> None:
    now = time.time()
    expired = [token for token, entry in _PENDING_LOGINS.items() if now - entry["created_at"] > _LOGIN_TTL_SECONDS]
    for token in expired:
        _PENDING_LOGINS.pop(token, None)


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest) -> LoginResponse:
    """Step 1: verify username/email + password credentials."""
    _prune_expired_logins()

    officer = meiyari_users_db.verify_credentials(payload.identifier, payload.password)
    if not officer:
        raise InvalidCredentialsError()

    login_token = uuid.uuid4().hex
    _PENDING_LOGINS[login_token] = {
        "created_at": time.time(),
        "identifier": payload.identifier.strip().lower(),
    }

    return LoginResponse(mfaRequired=True, loginToken=login_token)


@router.post("/login/verify-mfa", response_model=OfficerProfile, status_code=status.HTTP_200_OK)
async def login_verify_mfa(payload: VerifyMfaRequest) -> OfficerProfile:
    """Step 2: verify the 6-digit TOTP code and return the officer session profile."""
    _prune_expired_logins()

    entry = _PENDING_LOGINS.get(payload.loginToken)
    if not entry:
        raise HTTPException(status_code=410, detail="Your session has expired. Please sign in again.")

    secret = meiyari_users_db.get_mfa_secret(entry["identifier"])
    if not secret or not verify_totp(payload.code, secret):
        raise InvalidMfaCodeError()

    officer = meiyari_users_db.get_public_profile(entry["identifier"])
    _PENDING_LOGINS.pop(payload.loginToken, None)

    if not officer:
        raise InvalidCredentialsError()

    return OfficerProfile(**officer)
