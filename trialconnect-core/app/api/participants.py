from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.coordinator_account import CoordinatorAccount
from app.models.participant import Patient
from app.schemas.participant import PatientRead, PatientUpdate
from app.services.coordinator_auth import require_coordinator

router = APIRouter(tags=["patients"])
audit_logger = structlog.get_logger("audit")


@router.get("", response_model=list[PatientRead])
async def list_patients(
    study_id: str | None = None,
    site_id: str | None = None,
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _coordinator: CoordinatorAccount = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db),
) -> list[Patient]:
    query = select(Patient)
    if study_id:
        query = query.where(Patient.study_id == study_id)
    if site_id:
        query = query.where(Patient.site_id == site_id)
    if is_active is not None:
        query = query.where(Patient.is_active == is_active)
    query = query.order_by(Patient.family_name, Patient.given_name).limit(limit).offset(offset)
    result = await session.execute(query)
    patients = list(result.scalars().all())
    audit_logger.info("patient_listed", count=len(patients))
    return patients


@router.get("/{patient_id}", response_model=PatientRead)
async def get_patient(
    patient_id: UUID,
    _coordinator: CoordinatorAccount = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db),
) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    audit_logger.info("patient_viewed", patient_id=str(patient.id))
    return patient


@router.patch("/{patient_id}", response_model=PatientRead)
async def update_patient(
    patient_id: UUID,
    patient_data: PatientUpdate,
    _coordinator: CoordinatorAccount = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db),
) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    for field, value in patient_data.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    if "email" in patient_data.model_fields_set:
        from app.models.patient_account import PatientAccount

        account = await session.scalar(select(PatientAccount).where(PatientAccount.patient_id == patient.id))
        if account is not None:
            account.email = patient.email
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A patient with this email already exists.") from exc
    await session.refresh(patient)
    audit_logger.info("patient_updated", patient_id=str(patient.id))
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_patient(
    patient_id: UUID,
    _coordinator: CoordinatorAccount = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db),
) -> Response:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    patient.is_active = False
    await session.commit()
    audit_logger.info("patient_deactivated", patient_id=str(patient.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
