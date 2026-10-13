from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from celery import Celery
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.appointment import Appointment, AppointmentEmailDelivery, PatientNotification
from app.services.appointment_email import EmailDeliveryError, send_appointment_email

celery_app = Celery(
    "clinical_connect",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    timezone="UTC",
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "dispatch-appointment-reminders": {
            "task": "app.worker.dispatch_appointment_reminders",
            "schedule": settings.APPOINTMENT_REMINDER_POLL_SECONDS,
        },
        "dispatch-appointment-emails": {
            "task": "app.worker.dispatch_appointment_emails",
            "schedule": settings.APPOINTMENT_REMINDER_POLL_SECONDS,
        },
    },
)
logger = structlog.get_logger("appointment_reminders")

REMINDER_OFFSETS = {
    "48_hours": timedelta(hours=48),
    "24_hours": timedelta(hours=24),
}


def due_reminder_values(appointment: Appointment, current_time: datetime) -> list[dict[str, object]]:
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("Reminder dispatch time must be timezone-aware.")
    current_time = current_time.astimezone(UTC)
    starts_at = appointment.starts_at
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise ValueError("Appointment time must be timezone-aware.")
    starts_at = starts_at.astimezone(UTC)
    if appointment.status != "scheduled" or starts_at <= current_time:
        return []

    lateness_limit = timedelta(seconds=settings.APPOINTMENT_REMINDER_POLL_SECONDS * 2)
    reminders: list[dict[str, object]] = []
    for reminder_type, offset in REMINDER_OFFSETS.items():
        scheduled_for = starts_at - offset
        if scheduled_for > current_time or current_time - scheduled_for > lateness_limit:
            continue
        hours_until = int(offset.total_seconds() // 3600)
        reminders.append(
            {
                "patient_id": appointment.patient_id,
                "appointment_id": appointment.id,
                "reminder_type": reminder_type,
                "title": f"Appointment reminder: {hours_until} hours",
                "body": (
                    f"You have a {appointment.title.lower()} in {hours_until} hours, "
                    f"scheduled for {starts_at.isoformat()}."
                ),
                "scheduled_for": scheduled_for,
            }
        )
    return reminders


async def _dispatch_due_reminders(now: datetime | None = None) -> int:
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("Reminder dispatch time must be timezone-aware.")
    current_time = current_time.astimezone(UTC)
    dispatched = 0

    async with AsyncSessionLocal() as session:
        result = await session.scalars(
            select(Appointment).where(
                Appointment.status == "scheduled",
                Appointment.starts_at > current_time,
                Appointment.starts_at <= current_time + REMINDER_OFFSETS["48_hours"],
            )
        )
        appointments = list(result.all())
        for appointment in appointments:
            for reminder_values in due_reminder_values(appointment, current_time):
                statement = (
                    insert(PatientNotification)
                    .values(**reminder_values)
                    .on_conflict_do_nothing(
                        constraint="uq_notification_appointment_reminder"
                    )
                    .returning(PatientNotification.id)
                )
                result = await session.execute(statement)
                dispatched += len(result.scalars().all())
        await session.commit()

    return dispatched


async def _dispatch_due_emails(now: datetime | None = None) -> int:
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("Email dispatch time must be timezone-aware.")
    current_time = current_time.astimezone(UTC)
    if not settings.smtp_configured:
        return 0

    stale_sending_before = current_time - timedelta(minutes=10)
    async with AsyncSessionLocal() as session:
        result = await session.scalars(
            select(AppointmentEmailDelivery)
            .join(Appointment, Appointment.id == AppointmentEmailDelivery.appointment_id)
            .where(
                Appointment.status == "scheduled",
                Appointment.starts_at > current_time,
                AppointmentEmailDelivery.scheduled_for <= current_time,
                or_(
                    and_(
                        AppointmentEmailDelivery.status == "pending",
                        or_(
                            AppointmentEmailDelivery.next_attempt_at.is_(None),
                            AppointmentEmailDelivery.next_attempt_at <= current_time,
                        ),
                    ),
                    and_(
                        AppointmentEmailDelivery.status == "sending",
                        AppointmentEmailDelivery.last_attempt_at <= stale_sending_before,
                    ),
                ),
            )
            .order_by(AppointmentEmailDelivery.scheduled_for)
            .limit(10)
            .with_for_update(skip_locked=True, of=AppointmentEmailDelivery)
        )
        deliveries = list(result.all())
        if not deliveries:
            return 0

        for delivery in deliveries:
            delivery.status = "sending"
            delivery.attempts += 1
            delivery.last_attempt_at = current_time
            delivery.next_attempt_at = None
            delivery.last_error = None
        await session.commit()

        sent_count = 0
        for delivery in deliveries:
            appointment = await session.get(Appointment, delivery.appointment_id)
            if appointment is None:
                continue
            try:
                await asyncio.to_thread(send_appointment_email, delivery, appointment)
            except EmailDeliveryError as exc:
                delivery.last_error = str(exc)
                if delivery.attempts >= 5:
                    delivery.status = "failed"
                else:
                    delay_seconds = min(60 * (2 ** (delivery.attempts - 1)), 1800)
                    delivery.status = "pending"
                    delivery.next_attempt_at = current_time + timedelta(seconds=delay_seconds)
                logger.warning(
                    "appointment_email_delivery_failed",
                    delivery_id=str(delivery.id),
                    appointment_id=str(delivery.appointment_id),
                    attempt=delivery.attempts,
                    status=delivery.status,
                    error=str(exc),
                )
            else:
                delivery.status = "sent"
                delivery.sent_at = datetime.now(UTC)
                delivery.last_error = None
                sent_count += 1
            await session.commit()
        return sent_count


@celery_app.task(name="app.worker.dispatch_appointment_reminders")
def dispatch_appointment_reminders() -> int:
    count = asyncio.run(_dispatch_due_reminders())
    if count:
        logger.info("appointment_reminders_created", count=count)
    return count


@celery_app.task(name="app.worker.dispatch_appointment_emails")
def dispatch_appointment_emails() -> int:
    count = asyncio.run(_dispatch_due_emails())
    if count:
        logger.info("appointment_emails_sent", count=count)
    return count
