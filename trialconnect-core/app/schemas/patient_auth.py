from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class PatientSignup(BaseModel):
    given_name: str | None = Field(default=None, max_length=128)
    family_name: str | None = Field(default=None, max_length=128)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("given_name", "family_name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("must be a valid email address")
        return value


class PatientLogin(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthenticatedPatient(BaseModel):
    id: str
    external_id: str
    given_name: str
    family_name: str
    email: str
    study_id: str
    site_id: str
    is_active: bool


class PatientSession(BaseModel):
    access_token: str
    token_type: str = "bearer"
    patient: AuthenticatedPatient
