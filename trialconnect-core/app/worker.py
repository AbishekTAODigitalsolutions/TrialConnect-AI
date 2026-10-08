from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from celery import Celery
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.appointment import Appointment, PatientNotification

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
        }
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


@celery_app.task(name="app.worker.dispatch_appointment_reminders")
def dispatch_appointment_reminders() -> int:
    count = asyncio.run(_dispatch_due_reminders())
    if count:
        logger.info("appointment_reminders_created", count=count)
    return count
