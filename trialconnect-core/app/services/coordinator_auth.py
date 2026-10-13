from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.coordinator_account import CoordinatorAccount
from app.services.patient_auth import (
    bearer_scheme,
    coordinator_id_from_token,
    validate_auth_secret,
)


async def require_coordinator(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> CoordinatorAccount:
    validate_auth_secret()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Please sign in to the coordinator workbench.")
    coordinator_id = coordinator_id_from_token(credentials.credentials)
    coordinator = await session.get(CoordinatorAccount, coordinator_id)
    if coordinator is None or not coordinator.is_active:
        raise HTTPException(status_code=401, detail="This staff account is unavailable.")
    return coordinator


async def require_admin(
    coordinator: CoordinatorAccount = Depends(require_coordinator),
) -> CoordinatorAccount:
    if coordinator.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return coordinator


def require_account_id(account: CoordinatorAccount, expected_id: UUID) -> None:
    if account.id != expected_id:
        raise HTTPException(status_code=403, detail="You cannot access another staff account.")


def utc_now() -> datetime:
    return datetime.now(UTC)
