from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.appointment import Appointment
from app.schemas.appointment import AppointmentCreate, PatientNotificationRead
from app.services.appointment_email import (
    EmailDeliveryError,
    appointment_email_values,
    build_appointment_email,
    send_appointment_email,
)
from app.models.appointment import AppointmentEmailDelivery
from app.config import settings
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


def test_patient_notification_schema_accepts_appointment_scheduled_event() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    notification = PatientNotificationRead(
        id=uuid4(),
        appointment_id=uuid4(),
        reminder_type="scheduled",
        title="Appointment scheduled",
        body="Your doctor appointment is scheduled.",
        scheduled_for=now,
        created_at=now,
        read_at=None,
    )

    assert notification.reminder_type == "scheduled"


def test_appointment_email_values_create_confirmation_and_one_day_reminder() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    appointment = Appointment(
        id=uuid4(),
        patient_id=uuid4(),
        title="Doctor appointment",
        starts_at=now + timedelta(days=3),
        status="scheduled",
    )

    deliveries = appointment_email_values(appointment, "patient@example.test", now)

    assert [item["email_type"] for item in deliveries] == [
        "confirmation",
        "reminder_24_hours",
    ]
    assert deliveries[0]["recipient_email"] == "patient@example.test"
    assert deliveries[0]["scheduled_for"] == now
    assert deliveries[1]["scheduled_for"] == now + timedelta(days=2)


def test_appointment_email_values_skip_past_reminder_for_near_term_appointments() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    appointment = Appointment(
        id=uuid4(),
        patient_id=uuid4(),
        title="Doctor appointment",
        starts_at=now + timedelta(hours=12),
        status="scheduled",
    )

    deliveries = appointment_email_values(appointment, "patient@example.test", now)

    assert [item["email_type"] for item in deliveries] == ["confirmation"]


def test_appointment_email_values_include_reminder_when_scheduled_exactly_one_day_ahead() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    appointment = Appointment(
        id=uuid4(),
        patient_id=uuid4(),
        title="Doctor appointment",
        starts_at=now + timedelta(hours=24),
        status="scheduled",
    )

    deliveries = appointment_email_values(appointment, "patient@example.test", now)

    assert [item["email_type"] for item in deliveries] == [
        "confirmation",
        "reminder_24_hours",
    ]
    assert deliveries[1]["scheduled_for"] == now


def test_appointment_email_contains_schedule_and_recipient() -> None:
    appointment = Appointment(
        id=uuid4(),
        patient_id=uuid4(),
        title="Doctor appointment",
        location="Clinic",
        starts_at=datetime(2026, 10, 10, 12, tzinfo=UTC),
        status="scheduled",
    )
    delivery = AppointmentEmailDelivery(
        email_type="confirmation",
        recipient_email="patient@example.test",
    )

    message = build_appointment_email(delivery, appointment)

    assert message["To"] == "patient@example.test"
    assert message["Subject"] == "Appointment scheduled"
    assert "Doctor appointment" in message.get_content()
    assert "Clinic" in message.get_content()
    assert "October 10, 2026 at 12:00 UTC" in message.get_content()


def test_appointment_email_sender_uses_configured_smtp(monkeypatch) -> None:
    calls: list[object] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def starttls(self, *, context):
            calls.append(("starttls", context))

        def login(self, username: str, password: str):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send", message))

    monkeypatch.setattr(settings, "SMTP_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "mailer")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "test-password")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "appointments@example.test")
    monkeypatch.setattr(settings, "SMTP_USE_STARTTLS", True)
    monkeypatch.setattr("app.services.appointment_email.smtplib.SMTP", FakeSMTP)

    appointment = Appointment(
        id=uuid4(),
        patient_id=uuid4(),
        title="Doctor appointment",
        starts_at=datetime(2026, 10, 10, 12, tzinfo=UTC),
        status="scheduled",
    )
    delivery = AppointmentEmailDelivery(
        email_type="confirmation",
        recipient_email="patient@example.test",
    )

    send_appointment_email(delivery, appointment)

    assert calls[0] == ("connect", "smtp.example.test", 587, 20)
    assert calls[2] == ("login", "mailer", "test-password")
    assert calls[3][0] == "send"


def test_appointment_email_sender_rejects_missing_smtp_configuration(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SMTP_ENABLED", False)
    appointment = Appointment(
        id=uuid4(),
        patient_id=uuid4(),
        title="Doctor appointment",
        starts_at=datetime(2026, 10, 10, 12, tzinfo=UTC),
        status="scheduled",
    )
    delivery = AppointmentEmailDelivery(
        email_type="confirmation",
        recipient_email="patient@example.test",
    )

    with pytest.raises(EmailDeliveryError, match="SMTP is not configured"):
        send_appointment_email(delivery, appointment)
