from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.coordinator_account import (
    CoordinatorAccessRequest,
    CoordinatorAccount,
    CoordinatorAuditEvent,
)
from app.schemas.coordinator_auth import (
    CoordinatorAccessDecision,
    CoordinatorAccessRequestCreate,
    CoordinatorAccessRequestRead,
    CoordinatorAccessRequestResult,
    CoordinatorAccessDecisionResult,
    CoordinatorActivityRead,
    CoordinatorCreate,
    CoordinatorLogin,
    CoordinatorRead,
    CoordinatorSession,
)
from app.services.coordinator_auth import require_admin, require_coordinator
from app.services.patient_auth import (
    create_coordinator_access_token,
    hash_password,
    verify_password,
)
from app.services.appointment_email import EmailDeliveryError, send_email_message
from app.services.coordinator_access_email import build_access_request_email

router = APIRouter(prefix="/coordinator-auth", tags=["coordinator authentication"])
audit_logger = structlog.get_logger("audit")


async def _notify_admin_of_access_request(
    access_request: CoordinatorAccessRequest,
    session: AsyncSession,
) -> str:
    if not settings.COORDINATOR_ADMIN_EMAIL.strip() or not settings.smtp_configured:
        access_request.notification_status = "not_configured"
        access_request.notification_error = None
        await session.commit()
        return "not_configured"
    try:
        message = build_access_request_email(access_request.full_name, access_request.email)
        await asyncio.to_thread(send_email_message, message)
    except EmailDeliveryError as exc:
        access_request.notification_status = "failed"
        access_request.notification_error = str(exc)[:255]
        await session.commit()
        audit_logger.error(
            "coordinator_access_request_email_failed",
            request_id=str(access_request.id),
            error=str(exc),
        )
        return "failed"

    access_request.notification_status = "sent"
    access_request.notification_error = None
    await session.commit()
    return "sent"


@router.post("/login", response_model=CoordinatorSession)
async def coordinator_login(
    request: CoordinatorLogin,
    session: AsyncSession = Depends(get_db),
) -> CoordinatorSession:
    account = await session.scalar(
        select(CoordinatorAccount).where(CoordinatorAccount.email == request.email)
    )
    if account is None or not account.is_active or not verify_password(
        request.password,
        account.password_hash if account is not None else "",
    ):
        session.add(
            CoordinatorAuditEvent(
                coordinator_id=account.id if account else None,
                email=request.email,
                event_type="login_failed",
            )
        )
        await session.commit()
        audit_logger.warning("coordinator_login_failed", email=request.email)
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    account.last_login_at = datetime.now(UTC)
    session.add(
        CoordinatorAuditEvent(
            coordinator_id=account.id,
            email=account.email,
            event_type="login",
        )
    )
    await session.commit()
    await session.refresh(account)
    return CoordinatorSession(
        access_token=create_coordinator_access_token(account.id),
        coordinator=CoordinatorRead.model_validate(account),
    )


@router.post(
    "/access-requests",
    response_model=CoordinatorAccessRequestResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_coordinator_access_request(
    request: CoordinatorAccessRequestCreate,
    session: AsyncSession = Depends(get_db),
) -> CoordinatorAccessRequestResult:
    existing_account = await session.scalar(
        select(CoordinatorAccount.id).where(CoordinatorAccount.email == request.email)
    )
    if existing_account is not None:
        raise HTTPException(status_code=409, detail="A staff account already exists for this email.")

    access_request = await session.scalar(
        select(CoordinatorAccessRequest).where(CoordinatorAccessRequest.email == request.email)
    )
    if access_request is not None and access_request.status == "pending":
        raise HTTPException(
            status_code=409,
            detail="An access request for this email is already awaiting admin review.",
        )

    now = datetime.now(UTC)
    if access_request is None:
        access_request = CoordinatorAccessRequest(
            email=request.email,
            full_name=request.full_name,
            password_hash=hash_password(request.password),
            status="pending",
            notification_status="pending",
            created_at=now,
        )
        session.add(access_request)
    else:
        access_request.full_name = request.full_name
        access_request.password_hash = hash_password(request.password)
        access_request.status = "pending"
        access_request.notification_status = "pending"
        access_request.notification_error = None
        access_request.created_at = now
        access_request.reviewed_at = None
        access_request.reviewed_by = None

    session.add(
        CoordinatorAuditEvent(
            email=request.email,
            event_type="access_requested",
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="An access request for this email is already being processed.",
        ) from exc

    notification_status = await _notify_admin_of_access_request(access_request, session)
    if notification_status == "sent":
        message = "Access request submitted. The administrator was emailed for approval."
    elif notification_status == "failed":
        message = "Access request saved, but the admin email could not be delivered."
    else:
        message = "Access request saved, but admin email notifications are not configured."
    return CoordinatorAccessRequestResult(
        message=message,
        email_notification=notification_status,
    )


@router.get("/me", response_model=CoordinatorRead)
async def coordinator_me(
    coordinator: CoordinatorAccount = Depends(require_coordinator),
) -> CoordinatorAccount:
    return coordinator


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def coordinator_logout(
    coordinator: CoordinatorAccount = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db),
) -> Response:
    session.add(
        CoordinatorAuditEvent(
            coordinator_id=coordinator.id,
            email=coordinator.email,
            event_type="logout",
        )
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/team", response_model=list[CoordinatorRead])
async def list_team(
    _admin: CoordinatorAccount = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> list[CoordinatorAccount]:
    result = await session.scalars(
        select(CoordinatorAccount).order_by(CoordinatorAccount.created_at, CoordinatorAccount.email)
    )
    return list(result.all())


@router.get("/access-requests", response_model=list[CoordinatorAccessRequestRead])
async def list_coordinator_access_requests(
    _admin: CoordinatorAccount = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> list[CoordinatorAccessRequest]:
    result = await session.scalars(
        select(CoordinatorAccessRequest)
        .where(CoordinatorAccessRequest.status == "pending")
        .order_by(CoordinatorAccessRequest.created_at)
    )
    return list(result.all())


@router.post(
    "/access-requests/{request_id}/decision",
    response_model=CoordinatorAccessDecisionResult,
)
async def decide_coordinator_access_request(
    request_id: UUID,
    decision: CoordinatorAccessDecision,
    admin: CoordinatorAccount = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> CoordinatorAccessDecisionResult:
    access_request = await session.get(CoordinatorAccessRequest, request_id)
    if access_request is None:
        raise HTTPException(status_code=404, detail="Coordinator access request not found.")
    if access_request.status != "pending":
        raise HTTPException(status_code=409, detail="This access request has already been reviewed.")

    now = datetime.now(UTC)
    access_request.reviewed_at = now
    access_request.reviewed_by = admin.id
    if decision.decision == "approve":
        if access_request.password_hash is None:
            raise HTTPException(status_code=409, detail="The request has no valid password to activate.")
        account = CoordinatorAccount(
            email=access_request.email,
            full_name=access_request.full_name,
            password_hash=access_request.password_hash,
            role="coordinator",
            is_active=True,
        )
        session.add(account)
        access_request.status = "approved"
        access_request.password_hash = None
        session.add(
            CoordinatorAuditEvent(
                coordinator_id=admin.id,
                email=access_request.email,
                event_type="access_approved",
            )
        )
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="A staff account with this email already exists.",
            ) from exc
        await session.refresh(account)
        return CoordinatorAccessDecisionResult(
            id=access_request.id,
            email=access_request.email,
            full_name=access_request.full_name,
            status="approved",
            reviewed_at=now,
        )

    access_request.status = "rejected"
    access_request.password_hash = None
    session.add(
        CoordinatorAuditEvent(
            coordinator_id=admin.id,
            email=access_request.email,
            event_type="access_rejected",
        )
    )
    await session.commit()
    return CoordinatorAccessDecisionResult(
        id=access_request.id,
        email=access_request.email,
        full_name=access_request.full_name,
        status="rejected",
        reviewed_at=now,
    )


@router.post(
    "/access-requests/{request_id}/notify",
    response_model=CoordinatorAccessRequestRead,
)
async def retry_access_request_notification(
    request_id: UUID,
    admin: CoordinatorAccount = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> CoordinatorAccessRequest:
    access_request = await session.get(CoordinatorAccessRequest, request_id)
    if access_request is None or access_request.status != "pending":
        raise HTTPException(status_code=404, detail="Pending coordinator access request not found.")
    if not settings.COORDINATOR_ADMIN_EMAIL.strip() or not settings.smtp_configured:
        access_request.notification_status = "not_configured"
        await session.commit()
        return access_request

    await _notify_admin_of_access_request(access_request, session)
    return access_request


@router.post("/team", response_model=CoordinatorRead, status_code=status.HTTP_201_CREATED)
async def create_team_member(
    request: CoordinatorCreate,
    _admin: CoordinatorAccount = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> CoordinatorAccount:
    account = CoordinatorAccount(
        email=request.email,
        full_name=request.full_name,
        password_hash=hash_password(request.password),
        role=request.role,
        is_active=True,
    )
    session.add(account)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A staff account with this email already exists.") from exc
    await session.refresh(account)
    return account


@router.patch("/team/{coordinator_id}", response_model=CoordinatorRead)
async def set_team_member_active(
    coordinator_id: UUID,
    is_active: bool,
    admin: CoordinatorAccount = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> CoordinatorAccount:
    account = await session.get(CoordinatorAccount, coordinator_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Staff account not found.")
    if account.id == admin.id and not is_active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
    account.is_active = is_active
    await session.commit()
    await session.refresh(account)
    return account


@router.get("/activity", response_model=list[CoordinatorActivityRead])
async def coordinator_activity(
    _admin: CoordinatorAccount = Depends(require_admin),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[CoordinatorActivityRead]:
    result = await session.execute(
        select(CoordinatorAuditEvent, CoordinatorAccount.full_name)
        .outerjoin(CoordinatorAccount, CoordinatorAuditEvent.coordinator_id == CoordinatorAccount.id)
        .order_by(CoordinatorAuditEvent.created_at.desc())
        .limit(limit)
    )
    return [
        CoordinatorActivityRead(
            id=event.id,
            coordinator_id=event.coordinator_id,
            full_name=full_name,
            email=event.email,
            event_type=event.event_type,
            patient_id=event.patient_id,
            message_id=event.message_id,
            details=event.details,
            created_at=event.created_at,
        )
        for event, full_name in result.all()
    ]
