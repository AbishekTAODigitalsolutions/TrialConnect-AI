from __future__ import annotations

import re

import structlog
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.coordinator_account import CoordinatorAccount
from app.services.patient_auth import hash_password

logger = structlog.get_logger("coordinator_bootstrap")


async def bootstrap_coordinator_admin() -> None:
    email = settings.COORDINATOR_ADMIN_EMAIL.strip().lower()
    password = settings.COORDINATOR_ADMIN_PASSWORD
    if not email and not password:
        logger.warning(
            "coordinator_admin_not_configured",
            message="Set COORDINATOR_ADMIN_EMAIL and COORDINATOR_ADMIN_PASSWORD to enable coordinator login.",
        )
        return
    if not email or not password:
        raise RuntimeError(
            "COORDINATOR_ADMIN_EMAIL and COORDINATOR_ADMIN_PASSWORD must both be configured."
        )
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise RuntimeError("COORDINATOR_ADMIN_EMAIL must be a valid email address.")
    if len(password) < 12:
        raise RuntimeError("COORDINATOR_ADMIN_PASSWORD must be at least 12 characters.")

    async with AsyncSessionLocal() as session:
        existing_admin = await session.scalar(
            select(CoordinatorAccount.id).where(CoordinatorAccount.role == "admin").limit(1)
        )
        if existing_admin is not None:
            return
        existing_email = await session.scalar(
            select(CoordinatorAccount.id).where(CoordinatorAccount.email == email)
        )
        if existing_email is not None:
            raise RuntimeError(
                "The configured bootstrap admin email already belongs to a staff account, "
                "but no administrator exists. Resolve the account manually before startup."
            )
        session.add(
            CoordinatorAccount(
                email=email,
                full_name=settings.COORDINATOR_ADMIN_NAME.strip()
                or "Clinical Connect Administrator",
                password_hash=hash_password(password),
                role="admin",
                is_active=True,
            )
        )
        await session.commit()
        logger.info("coordinator_admin_bootstrapped", email=email)
