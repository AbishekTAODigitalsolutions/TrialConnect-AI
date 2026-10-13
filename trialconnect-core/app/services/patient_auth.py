from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.participant import Patient

bearer_scheme = HTTPBearer(auto_error=False)


def validate_auth_secret() -> str:
    secret = settings.AUTH_SECRET
    if len(secret.encode("utf-8")) < 32:
        raise HTTPException(
            status_code=503,
            detail="Session authentication is not configured. Set AUTH_SECRET to at least 32 bytes.",
        )
    return secret


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${_b64encode(salt)}${_b64encode(derived)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt_text, digest_text = stored_hash.split("$", maxsplit=2)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64decode(salt_text),
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        )
        return hmac.compare_digest(digest, _b64decode(digest_text))
    except (ValueError, TypeError):
        return False


def create_access_token(patient_id: UUID) -> str:
    return _create_access_token({"sub": str(patient_id), "typ": "patient"})


def _create_access_token(claims: dict[str, str | int]) -> str:
    secret = validate_auth_secret()
    claims["exp"] = int(time.time()) + settings.AUTH_TOKEN_TTL_SECONDS
    payload = _b64encode(
        json.dumps(claims, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return f"{payload}.{_b64encode(signature)}"


def create_coordinator_access_token(coordinator_id: UUID) -> str:
    return _create_access_token({"sub": str(coordinator_id), "typ": "coordinator"})


def _subject_from_token(token: str, expected_type: str) -> UUID:
    try:
        payload, signature_text = token.split(".", maxsplit=1)
        expected_signature = hmac.new(
            validate_auth_secret().encode("utf-8"),
            payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected_signature, _b64decode(signature_text)):
            raise ValueError("Invalid session signature")
        claims = json.loads(_b64decode(payload))
        if claims["exp"] <= int(time.time()):
            raise ValueError("Expired session")
        if claims.get("typ", "patient") != expected_type:
            raise ValueError("Unexpected session type")
        return UUID(claims["sub"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired login session.") from exc


def patient_id_from_token(token: str) -> UUID:
    return _subject_from_token(token, "patient")


def coordinator_id_from_token(token: str) -> UUID:
    return _subject_from_token(token, "coordinator")


async def require_patient(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> Patient:
    validate_auth_secret()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    patient_id = patient_id_from_token(credentials.credentials)
    patient = await session.get(Patient, patient_id)
    if patient is None or not patient.is_active:
        raise HTTPException(status_code=401, detail="This patient account is unavailable.")
    return patient
