from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AppointmentCreate(BaseModel):
    title: str = Field(default="Doctor appointment", min_length=1, max_length=160)
    location: str | None = Field(default=None, max_length=255)
    starts_at: datetime

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("appointment title cannot be blank")
        return value

    @field_validator("location")
    @classmethod
    def clean_location(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def require_future_timezone_aware_time(self) -> AppointmentCreate:
        if self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None:
            raise ValueError("appointment time must include a timezone")
        if self.starts_at <= datetime.now(self.starts_at.tzinfo):
            raise ValueError("appointment time must be in the future")
        return self


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    title: str
    location: str | None
    starts_at: datetime
    status: Literal["scheduled", "cancelled"]
    created_at: datetime


class AppointmentEmailDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email_type: Literal["confirmation", "reminder_24_hours"]
    scheduled_for: datetime
    status: Literal["pending", "sending", "sent", "failed"]
    attempts: int
    last_attempt_at: datetime | None
    sent_at: datetime | None
    last_error: str | None
    smtp_configured: bool


class CoordinatorAppointmentRead(AppointmentRead):
    email_deliveries: list[AppointmentEmailDeliveryRead] = Field(default_factory=list)


class PatientNotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    appointment_id: UUID
    reminder_type: Literal["scheduled", "48_hours", "24_hours"]
    title: str
    body: str
    scheduled_for: datetime
    created_at: datetime
    read_at: datetime | None
