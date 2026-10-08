from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PatientFields(BaseModel):
    external_id: str = Field(min_length=1, max_length=64)
    given_name: str = Field(min_length=1, max_length=128)
    family_name: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=255)
    study_id: str = Field(min_length=1, max_length=64)
    site_id: str = Field(min_length=1, max_length=64)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)

    @field_validator("external_id", "given_name", "family_name", "study_id", "site_id", "timezone")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("must be a valid email address")
        return value


class PatientCreate(PatientFields):
    pass


class PatientUpdate(BaseModel):
    given_name: str | None = Field(default=None, min_length=1, max_length=128)
    family_name: str | None = Field(default=None, min_length=1, max_length=128)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    study_id: str | None = Field(default=None, min_length=1, max_length=64)
    site_id: str | None = Field(default=None, min_length=1, max_length=64)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    is_active: bool | None = None

    @field_validator("given_name", "family_name", "study_id", "site_id", "timezone")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("must be a valid email address")
        return value

    @model_validator(mode="after")
    def require_at_least_one_change(self) -> PatientUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if any(value is None for value in self.model_dump(exclude_unset=True).values()):
            raise ValueError("updated fields must not be null")
        return self


class PatientRead(PatientFields):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


ParticipantFields = PatientFields
ParticipantCreate = PatientCreate
ParticipantUpdate = PatientUpdate
ParticipantRead = PatientRead
