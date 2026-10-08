from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import Appointment, PatientNotification
from app.models.participant import Patient
from app.schemas.appointment import AppointmentCreate, AppointmentRead, PatientNotificationRead
from app.services.patient_auth import require_patient

patient_router = APIRouter(tags=["patient appointments and reminders"])
coordinator_router = APIRouter(tags=["coordinator appointments"])
audit_logger = structlog.get_logger("audit")


@coordinator_router.get(
    "/coordinator/patients/{patient_id}/appointments",
    response_model=list[AppointmentRead],
)
async def coordinator_patient_appointments(
    patient_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[Appointment]:
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
    return list(result.all())


@coordinator_router.post(
    "/coordinator/patients/{patient_id}/appointments",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def schedule_patient_appointment(
    patient_id: UUID,
    request: AppointmentCreate,
    session: AsyncSession = Depends(get_db),
) -> Appointment:
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
    await session.commit()
    await session.refresh(appointment)
    audit_logger.info(
        "patient_appointment_scheduled",
        patient_id=str(patient.id),
        appointment_id=str(appointment.id),
        starts_at=appointment.starts_at.isoformat(),
    )
    return appointment


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
