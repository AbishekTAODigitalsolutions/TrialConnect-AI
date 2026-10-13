from __future__ import annotations

from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.patient_account import PatientAccount
from app.models.participant import Patient
from app.schemas.patient_auth import (
    AuthenticatedPatient,
    PatientLogin,
    PatientSession,
    PatientSignup,
)
from app.services.patient_auth import (
    create_access_token,
    hash_password,
    require_patient,
    validate_auth_secret,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["patient authentication"])
audit_logger = structlog.get_logger("audit")


def _patient_response(patient: Patient) -> AuthenticatedPatient:
    return AuthenticatedPatient(
        id=str(patient.id),
        external_id=patient.external_id,
        given_name=patient.given_name,
        family_name=patient.family_name,
        email=patient.email,
        study_id=patient.study_id,
        site_id=patient.site_id,
        is_active=patient.is_active,
    )


def _create_session(patient: Patient) -> PatientSession:
    return PatientSession(
        access_token=create_access_token(patient.id),
        patient=_patient_response(patient),
    )


@router.post("/signup", response_model=PatientSession, status_code=status.HTTP_201_CREATED)
async def signup(
    request: PatientSignup,
    session: AsyncSession = Depends(get_db),
) -> PatientSession:
    validate_auth_secret()
    existing_patient = await session.scalar(
        select(Patient).where(func.lower(Patient.email) == request.email)
    )
    if existing_patient is not None:
        if not existing_patient.is_active:
            raise HTTPException(status_code=403, detail="This patient record is inactive.")
        existing_account = await session.scalar(
            select(PatientAccount).where(PatientAccount.patient_id == existing_patient.id)
        )
        if existing_account is not None:
            raise HTTPException(status_code=409, detail="An account already exists. Please log in.")
        patient = existing_patient
    else:
        if not request.given_name or not request.family_name:
            raise HTTPException(
                status_code=404,
                detail="No patient record was found for this email. Enter your name to create a new account.",
            )
        patient = Patient(
            id=uuid4(),
            external_id=f"PAT-{uuid4().hex[:12].upper()}",
            given_name=request.given_name,
            family_name=request.family_name,
            email=request.email,
            study_id=settings.DEFAULT_STUDY_ID,
            site_id=settings.DEFAULT_SITE_ID,
            timezone="UTC",
            is_active=True,
        )
        session.add(patient)
        await session.flush()

    session.add(
        PatientAccount(
            patient_id=patient.id,
            email=patient.email.lower(),
            password_hash=hash_password(request.password),
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    await session.refresh(patient)
    audit_logger.info("patient_signed_up", patient_id=str(patient.id))
    return _create_session(patient)


@router.post("/login", response_model=PatientSession)
async def login(
    request: PatientLogin,
    session: AsyncSession = Depends(get_db),
) -> PatientSession:
    validate_auth_secret()
    account = await session.scalar(select(PatientAccount).where(PatientAccount.email == request.email))
    if account is None or not verify_password(request.password, account.password_hash):
        audit_logger.warning("patient_login_failed")
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    patient = await session.get(Patient, account.patient_id)
    if patient is None or not patient.is_active:
        raise HTTPException(status_code=403, detail="This patient account is inactive.")
    audit_logger.info("patient_logged_in", patient_id=str(patient.id))
    return _create_session(patient)


@router.get("/me", response_model=AuthenticatedPatient)
async def get_my_patient_profile(
    patient: Patient = Depends(require_patient),
) -> AuthenticatedPatient:
    return _patient_response(patient)
