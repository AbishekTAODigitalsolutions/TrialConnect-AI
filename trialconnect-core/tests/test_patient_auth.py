from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.patient_auth import (
    create_access_token,
    hash_password,
    patient_id_from_token,
    verify_password,
)


def test_password_hashing_and_verification() -> None:
    password = "synthetic-demo-password-123"
    stored_hash = hash_password(password)

    assert stored_hash != password
    assert verify_password(password, stored_hash)
    assert not verify_password("incorrect-password", stored_hash)


def test_patient_session_token_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.patient_auth.settings.AUTH_SECRET", "s" * 48)
    patient_id = uuid4()

    token = create_access_token(patient_id)

    assert patient_id_from_token(token) == patient_id


def test_patient_session_token_rejects_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.patient_auth.settings.AUTH_SECRET", "s" * 48)
    token = create_access_token(uuid4())

    with pytest.raises(HTTPException) as exc_info:
        patient_id_from_token(f"{token}tampered")

    assert exc_info.value.status_code == 401


def test_patient_session_requires_a_configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.patient_auth.settings.AUTH_SECRET", "")

    with pytest.raises(HTTPException) as exc_info:
        create_access_token(uuid4())

    assert exc_info.value.status_code == 503
