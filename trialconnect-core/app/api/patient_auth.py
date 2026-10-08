from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import secrets
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.patient_account import PatientAccount, PatientInvite
from app.models.participant import Patient
from app.schemas.patient_auth import (
    AuthenticatedPatient,
    PatientActivation,
    PatientInviteCreated,
    PatientLogin,
    PatientSession,
    PatientSignup,
)
from app.services.patient_auth import (
    create_access_token,
    hash_invite_code,
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
    existing_patient = await session.scalar(select(Patient).where(Patient.email == request.email))
    if existing_patient is not None:
        raise HTTPException(
            status_code=409,
            detail="A patient record already exists for this email. Ask your coordinator for an activation code.",
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
            email=request.email,
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


@router.post("/activate", response_model=PatientSession)
async def activate_existing_patient(
    request: PatientActivation,
    session: AsyncSession = Depends(get_db),
) -> PatientSession:
    validate_auth_secret()
    code_hash = hash_invite_code(request.invite_code)
    invite = await session.scalar(select(PatientInvite).where(PatientInvite.code_hash == code_hash))
    now = datetime.now(UTC)
    if invite is None or invite.used_at is not None or invite.expires_at <= now:
        raise HTTPException(status_code=400, detail="The activation code is invalid or expired.")

    patient = await session.get(Patient, invite.patient_id)
    if patient is None or not patient.is_active or patient.email.lower() != request.email:
        raise HTTPException(status_code=400, detail="The activation details do not match an active patient.")
    existing_account = await session.scalar(
        select(PatientAccount).where(PatientAccount.patient_id == patient.id)
    )
    if existing_account is not None:
        raise HTTPException(status_code=409, detail="This patient account has already been activated.")

    session.add(
        PatientAccount(
            patient_id=patient.id,
            email=patient.email,
            password_hash=hash_password(request.password),
        )
    )
    invite.used_at = now
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="This patient account has already been activated.") from exc
    audit_logger.info("patient_account_activated", patient_id=str(patient.id))
    return _create_session(patient)


@router.get("/me", response_model=AuthenticatedPatient)
async def get_my_patient_profile(
    patient: Patient = Depends(require_patient),
) -> AuthenticatedPatient:
    return _patient_response(patient)


@router.post(
    "/patients/{patient_id}/invite",
    response_model=PatientInviteCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_patient_invite(
    patient_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> PatientInviteCreated:
    patient = await session.get(Patient, patient_id)
    if patient is None or not patient.is_active:
        raise HTTPException(status_code=404, detail="Active patient not found.")
    account = await session.scalar(select(PatientAccount).where(PatientAccount.patient_id == patient.id))
    if account is not None:
        raise HTTPException(status_code=409, detail="This patient already has a portal account.")

    now = datetime.now(UTC)
    outstanding_invites = await session.scalars(
        select(PatientInvite).where(
            PatientInvite.patient_id == patient.id,
            PatientInvite.used_at.is_(None),
        )
    )
    for outstanding_invite in outstanding_invites:
        outstanding_invite.used_at = now
    code = secrets.token_urlsafe(32)
    expires_at = now + timedelta(hours=settings.PATIENT_INVITE_TTL_HOURS)
    session.add(
        PatientInvite(
            patient_id=patient.id,
            code_hash=hash_invite_code(code),
            expires_at=expires_at,
        )
    )
    await session.commit()
    audit_logger.info("patient_invite_created", patient_id=str(patient.id))
    return PatientInviteCreated(invite_code=code, expires_at=expires_at.isoformat())
