from __future__ import annotations

import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from app.config import settings
from app.models.appointment import Appointment, AppointmentEmailDelivery


class EmailDeliveryError(Exception):
    pass


def appointment_email_values(
    appointment: Appointment,
    recipient_email: str,
    current_time: datetime,
) -> list[dict[str, object]]:
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("Email scheduling time must be timezone-aware.")
    if appointment.starts_at.tzinfo is None or appointment.starts_at.utcoffset() is None:
        raise ValueError("Appointment time must be timezone-aware.")
    if appointment.status != "scheduled":
        return []

    now = current_time.astimezone(UTC)
    starts_at = appointment.starts_at.astimezone(UTC)
    if starts_at <= now:
        return []

    deliveries: list[dict[str, object]] = [
        {
            "patient_id": appointment.patient_id,
            "appointment_id": appointment.id,
            "email_type": "confirmation",
            "recipient_email": recipient_email,
            "scheduled_for": now,
        }
    ]
    reminder_time = starts_at - timedelta(hours=24)
    if reminder_time >= now:
        deliveries.append(
            {
                "patient_id": appointment.patient_id,
                "appointment_id": appointment.id,
                "email_type": "reminder_24_hours",
                "recipient_email": recipient_email,
                "scheduled_for": reminder_time,
            }
        )
    return deliveries


def build_appointment_email(
    delivery: AppointmentEmailDelivery,
    appointment: Appointment,
) -> EmailMessage:
    starts_at = appointment.starts_at.astimezone(UTC)
    appointment_time = starts_at.strftime("%A, %B %d, %Y at %H:%M UTC")
    location = f"\nLocation: {appointment.location}" if appointment.location else ""
    message = EmailMessage()
    if delivery.email_type == "confirmation":
        message["Subject"] = "Appointment scheduled"
        intro = "Your appointment has been scheduled."
    else:
        message["Subject"] = "Appointment reminder: tomorrow"
        intro = "This is a reminder about your appointment scheduled for approximately 24 hours from now."
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = delivery.recipient_email
    message.set_content(
        f"{intro}\n\n"
        f"Appointment: {appointment.title}\n"
        f"Date and time: {appointment_time}"
        f"{location}\n\n"
        "Please contact your study coordinator if you need assistance."
    )
    return message


def send_appointment_email(
    delivery: AppointmentEmailDelivery,
    appointment: Appointment,
) -> None:
    message = build_appointment_email(delivery, appointment)
    send_email_message(message)


def send_email_message(message: EmailMessage) -> None:
    if not settings.smtp_configured:
        raise EmailDeliveryError("SMTP is not configured or enabled.")

    try:
        with smtplib.SMTP(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=20,
        ) as smtp:
            if settings.SMTP_USE_STARTTLS:
                smtp.starttls(context=ssl.create_default_context())
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except ValueError as exc:
        raise EmailDeliveryError("Invalid email data.") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailDeliveryError(
            f"SMTP delivery failed ({type(exc).__name__})."
        ) from exc
