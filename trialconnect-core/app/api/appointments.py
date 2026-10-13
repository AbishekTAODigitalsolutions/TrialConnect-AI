from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.appointment import Appointment, AppointmentEmailDelivery, PatientNotification
from app.models.participant import Patient
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentEmailDeliveryRead,
    AppointmentRead,
    CoordinatorAppointmentRead,
    PatientNotificationRead,
)
from app.services.appointment_email import appointment_email_values
from app.services.patient_auth import require_patient
from app.services.coordinator_auth import require_coordinator
from app.models.coordinator_account import CoordinatorAccount

patient_router = APIRouter(tags=["patient appointments and reminders"])
coordinator_router = APIRouter(tags=["coordinator appointments"])
audit_logger = structlog.get_logger("audit")


@coordinator_router.get(
    "/coordinator/patients/{patient_id}/appointments",
    response_model=list[CoordinatorAppointmentRead],
)
async def coordinator_patient_appointments(
    patient_id: UUID,
    _coordinator: CoordinatorAccount = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db),
) -> list[CoordinatorAppointmentRead]:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    result = await session.scalars(
        select(Appointment)
        .where(
            Appointment.patient_id == patient.id,
            Appointment.status == "scheduled",
            Appointment.starts_at >= datetime.now(UTC),
        )
        .order_by(Appointment.starts_at)
    )
    return await _coordinator_appointment_reads(session, list(result.all()))


@coordinator_router.post(
    "/coordinator/patients/{patient_id}/appointments",
    response_model=CoordinatorAppointmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def schedule_patient_appointment(
    patient_id: UUID,
    request: AppointmentCreate,
    _coordinator: CoordinatorAccount = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db),
) -> CoordinatorAppointmentRead:
    patient = await session.get(Patient, patient_id)
    if patient is None or not patient.is_active:
        raise HTTPException(status_code=404, detail="Active patient not found.")

    appointment = Appointment(
        patient_id=patient.id,
        title=request.title,
        location=request.location,
        starts_at=request.starts_at.astimezone(UTC),
        status="scheduled",
    )
    session.add(appointment)
    await session.flush()
    current_time = datetime.now(UTC)
    appointment_details = f"scheduled for {appointment.starts_at.isoformat()}"
    if appointment.location:
        appointment_details += f" at {appointment.location}"
    session.add(
        PatientNotification(
            patient_id=patient.id,
            appointment_id=appointment.id,
            reminder_type="scheduled",
            title="Appointment scheduled",
            body=f"Your {appointment.title.lower()} is {appointment_details}.",
            scheduled_for=current_time,
        )
    )
    session.add_all(
        AppointmentEmailDelivery(**values)
        for values in appointment_email_values(appointment, patient.email, current_time)
    )
    await session.commit()
    await session.refresh(appointment)
    audit_logger.info(
        "patient_appointment_scheduled",
        patient_id=str(patient.id),
        appointment_id=str(appointment.id),
        starts_at=appointment.starts_at.isoformat(),
    )
    return (await _coordinator_appointment_reads(session, [appointment]))[0]


async def _coordinator_appointment_reads(
    session: AsyncSession,
    appointments: list[Appointment],
) -> list[CoordinatorAppointmentRead]:
    if not appointments:
        return []
    deliveries_result = await session.scalars(
        select(AppointmentEmailDelivery)
        .where(AppointmentEmailDelivery.appointment_id.in_([item.id for item in appointments]))
        .order_by(AppointmentEmailDelivery.scheduled_for)
    )
    deliveries_by_appointment: dict[UUID, list[AppointmentEmailDeliveryRead]] = {}
    for delivery in deliveries_result.all():
        deliveries_by_appointment.setdefault(delivery.appointment_id, []).append(
            AppointmentEmailDeliveryRead(
                id=delivery.id,
                email_type=delivery.email_type,
                scheduled_for=delivery.scheduled_for,
                status=delivery.status,
                attempts=delivery.attempts,
                last_attempt_at=delivery.last_attempt_at,
                sent_at=delivery.sent_at,
                last_error=delivery.last_error,
                smtp_configured=settings.smtp_configured,
            )
        )

    return [
        CoordinatorAppointmentRead(
            **AppointmentRead.model_validate(appointment).model_dump(),
            email_deliveries=deliveries_by_appointment.get(appointment.id, []),
        )
        for appointment in appointments
    ]


@patient_router.get("/appointments", response_model=list[AppointmentRead])
async def patient_appointments(
    include_past: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    patient: Patient = Depends(require_patient),
    session: AsyncSession = Depends(get_db),
) -> list[Appointment]:
    query = select(Appointment).where(
        Appointment.patient_id == patient.id,
        Appointment.status == "scheduled",
    )
    if not include_past:
        query = query.where(Appointment.starts_at >= datetime.now(UTC))
    result = await session.scalars(query.order_by(Appointment.starts_at).limit(limit))
    return list(result.all())


@patient_router.get("/notifications", response_model=list[PatientNotificationRead])
async def patient_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    patient: Patient = Depends(require_patient),
    session: AsyncSession = Depends(get_db),
) -> list[PatientNotification]:
    query = select(PatientNotification).where(PatientNotification.patient_id == patient.id)
    if unread_only:
        query = query.where(PatientNotification.read_at.is_(None))
    result = await session.scalars(
        query.order_by(PatientNotification.created_at.desc()).limit(limit)
    )
    return list(result.all())


@patient_router.patch("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_read(
    notification_id: UUID,
    patient: Patient = Depends(require_patient),
    session: AsyncSession = Depends(get_db),
) -> Response:
    notification = await session.scalar(
        select(PatientNotification).where(
            PatientNotification.id == notification_id,
            PatientNotification.patient_id == patient.id,
        )
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
