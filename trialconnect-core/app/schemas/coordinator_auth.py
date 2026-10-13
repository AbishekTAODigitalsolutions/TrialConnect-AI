from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CoordinatorLogin(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class CoordinatorCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["admin", "coordinator"] = "coordinator"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("must be a valid email address")
        return value

    @field_validator("full_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class CoordinatorAccessRequestCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("must be a valid email address")
        return value

    @field_validator("full_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class CoordinatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: Literal["admin", "coordinator"]
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class CoordinatorSession(BaseModel):
    access_token: str
    token_type: str = "bearer"
    coordinator: CoordinatorRead


class CoordinatorAccessRequestRead(BaseModel):
    id: UUID
    email: str
    full_name: str
    status: Literal["pending"]
    notification_status: Literal["sent", "failed", "not_configured", "pending"]
    notification_error: str | None
    created_at: datetime


class CoordinatorAccessRequestResult(BaseModel):
    message: str
    email_notification: Literal["sent", "failed", "not_configured"]


class CoordinatorAccessDecisionResult(BaseModel):
    id: UUID
    email: str
    full_name: str
    status: Literal["approved", "rejected"]
    reviewed_at: datetime


class CoordinatorAccessDecision(BaseModel):
    decision: Literal["approve", "reject"]


class CoordinatorActivityRead(BaseModel):
    id: UUID
    coordinator_id: UUID | None
    full_name: str | None
    email: str | None
    event_type: Literal[
        "login",
        "login_failed",
        "logout",
        "message_read",
        "access_requested",
        "access_approved",
        "access_rejected",
    ]
    patient_id: UUID | None
    message_id: UUID | None
    details: dict[str, str] | None
    created_at: datetime
