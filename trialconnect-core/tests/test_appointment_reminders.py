from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.appointment import Appointment
from app.schemas.appointment import AppointmentCreate
from app.worker import due_reminder_values


def test_due_reminder_values_include_48_and_24_hour_notifications() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    appointment = Appointment(
        id=uuid4(),
        patient_id=uuid4(),
        title="Doctor appointment",
        location="Clinic",
        starts_at=now + timedelta(hours=48),
        status="scheduled",
    )

    reminders = due_reminder_values(appointment, now)

    assert [item["reminder_type"] for item in reminders] == ["48_hours"]
    assert reminders[0]["scheduled_for"] == now

    one_day_later = due_reminder_values(appointment, now + timedelta(hours=24))
    assert [item["reminder_type"] for item in one_day_later] == ["24_hours"]
    assert one_day_later[0]["scheduled_for"] == now + timedelta(hours=24)


def test_due_reminder_values_allow_small_scheduler_delay_only() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    appointment = Appointment(
        id=uuid4(),
        patient_id=uuid4(),
        title="Doctor appointment",
        starts_at=now + timedelta(hours=48) - timedelta(seconds=30),
        status="scheduled",
    )

    reminders = due_reminder_values(appointment, now)

    assert [item["reminder_type"] for item in reminders] == ["48_hours"]


def test_due_reminder_values_skip_future_and_cancelled_reminders() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    appointment = Appointment(
        id=uuid4(),
        patient_id=uuid4(),
        title="Doctor appointment",
        starts_at=now + timedelta(days=4),
        status="scheduled",
    )

    assert due_reminder_values(appointment, now) == []

    appointment.status = "cancelled"
    appointment.starts_at = now + timedelta(hours=12)
    assert due_reminder_values(appointment, now) == []


def test_appointment_requires_timezone_aware_future_time() -> None:
    with pytest.raises(ValidationError):
        AppointmentCreate(starts_at=datetime.now() + timedelta(days=2))

    with pytest.raises(ValidationError):
        AppointmentCreate(starts_at=datetime.now(UTC) - timedelta(minutes=1))

    appointment = AppointmentCreate(starts_at=datetime.now(UTC) + timedelta(days=2))
    assert appointment.starts_at.utcoffset() == timedelta(0)
