from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.coordinator_account import CoordinatorAccount, CoordinatorAuditEvent
from app.models.coordinator_account import CoordinatorAccessRequest
from app.schemas.coordinator_auth import (
    CoordinatorAccessDecision,
    CoordinatorAccessRequestCreate,
)
from app.api.coordinator_auth import (
    decide_coordinator_access_request,
    submit_coordinator_access_request,
)
from app.services.coordinator_auth import require_admin
from app.services.coordinator_access_email import build_access_request_email
from app.services.patient_auth import (
    coordinator_id_from_token,
    create_coordinator_access_token,
    hash_password,
    patient_id_from_token,
)


@pytest.fixture
def unauthenticated_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "AUTH_SECRET", "s" * 48)

    async def no_database():
        yield None

    async def skip_admin_bootstrap() -> None:
        return None

    app.dependency_overrides[get_db] = no_database
    from app import main

    monkeypatch.setattr(main, "bootstrap_coordinator_admin", skip_admin_bootstrap)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_coordinator_workbench_endpoints_require_staff_login(
    unauthenticated_client: TestClient,
) -> None:
    responses = [
        unauthenticated_client.get("/api/v1/patients"),
        unauthenticated_client.get("/api/v1/coordinator/messages/unread"),
        unauthenticated_client.get(
            "/api/v1/coordinator/patients/00000000-0000-0000-0000-000000000001/messages"
        ),
        unauthenticated_client.get(
            "/api/v1/coordinator/patients/00000000-0000-0000-0000-000000000001/appointments"
        ),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401]


def test_staff_session_tokens_are_not_patient_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.patient_auth.settings.AUTH_SECRET", "s" * 48)
    staff_id = UUID("00000000-0000-0000-0000-000000000002")
    token = create_coordinator_access_token(staff_id)

    assert coordinator_id_from_token(token) == staff_id
    with pytest.raises(HTTPException) as exc_info:
        patient_id_from_token(token)
    assert exc_info.value.status_code == 401


def test_coordinator_login_records_staff_identity_and_failed_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AUTH_SECRET", "s" * 48)
    account = CoordinatorAccount(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        email="admin@example.test",
        full_name="Clinical Admin",
        password_hash=hash_password("strong-demo-password"),
        role="admin",
        is_active=True,
        created_at=datetime.now(UTC),
    )

    class LoginSession:
        def __init__(self) -> None:
            self.events: list[CoordinatorAuditEvent] = []

        async def scalar(self, _query: object) -> CoordinatorAccount:
            return account

        def add(self, event: CoordinatorAuditEvent) -> None:
            self.events.append(event)

        async def commit(self) -> None:
            return None

        async def refresh(self, _account: CoordinatorAccount) -> None:
            return None

    session = LoginSession()

    async def override_get_db():
        yield session

    async def skip_admin_bootstrap() -> None:
        return None

    from app import main

    monkeypatch.setattr(main, "bootstrap_coordinator_admin", skip_admin_bootstrap)
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/coordinator-auth/login",
                json={"email": " ADMIN@example.test ", "password": "strong-demo-password"},
            )
            assert response.status_code == 200
            assert response.json()["coordinator"]["role"] == "admin"
            assert coordinator_id_from_token(response.json()["access_token"]) == account.id

            rejected = client.post(
                "/api/v1/coordinator-auth/login",
                json={"email": "admin@example.test", "password": "wrong-password"},
            )

        assert rejected.status_code == 401
        assert [event.event_type for event in session.events] == ["login", "login_failed"]
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_only_admin_role_passes_admin_dependency() -> None:
    coordinator = CoordinatorAccount(
        id=UUID("00000000-0000-0000-0000-000000000003"),
        email="coordinator@example.test",
        full_name="Coordinator",
        password_hash="unused",
        role="coordinator",
        is_active=True,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(coordinator)

    assert exc_info.value.status_code == 403


def test_access_request_email_notifies_admin_without_applicant_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "COORDINATOR_ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "notifications@example.test")
    request = CoordinatorAccessRequestCreate(
        full_name="New Coordinator",
        email="new.coordinator@example.test",
        password="private-password-123",
    )

    message = build_access_request_email(request.full_name, request.email)

    assert message["To"] == "admin@example.test"
    assert message["Reply-To"] == "new.coordinator@example.test"
    assert "New Coordinator" in message.get_content()
    assert "private-password-123" not in message.as_string()


@pytest.mark.asyncio
async def test_access_request_is_pending_and_notification_result_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: list[object] = []

    class RequestSession:
        async def scalar(self, _query: object) -> None:
            return None

        def add(self, value: object) -> None:
            stored.append(value)

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    async def notify_sent(
        _access_request: CoordinatorAccessRequest,
        _session: RequestSession,
    ) -> str:
        return "sent"

    monkeypatch.setattr(
        "app.api.coordinator_auth._notify_admin_of_access_request",
        notify_sent,
    )
    request = CoordinatorAccessRequestCreate(
        full_name="New Coordinator",
        email="NEW.COORDINATOR@example.test",
        password="private-password-123",
    )

    result = await submit_coordinator_access_request(request, RequestSession())

    access_request = next(item for item in stored if isinstance(item, CoordinatorAccessRequest))
    assert result.email_notification == "sent"
    assert access_request.email == "new.coordinator@example.test"
    assert access_request.status == "pending"
    assert access_request.password_hash != request.password
    assert any(
        isinstance(item, CoordinatorAuditEvent) and item.event_type == "access_requested"
        for item in stored
    )


@pytest.mark.asyncio
async def test_admin_approval_activates_coordinator_and_clears_pending_hash() -> None:
    access_request = CoordinatorAccessRequest(
        id=UUID("00000000-0000-0000-0000-000000000004"),
        email="new.coordinator@example.test",
        full_name="New Coordinator",
        password_hash=hash_password("private-password-123"),
        status="pending",
        notification_status="sent",
        created_at=datetime.now(UTC),
    )
    admin = CoordinatorAccount(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        email="admin@example.test",
        full_name="Admin",
        password_hash="unused",
        role="admin",
        is_active=True,
    )

    class ApprovalSession:
        def __init__(self) -> None:
            self.added: list[object] = []

        async def get(self, _model: type[CoordinatorAccessRequest], _request_id: UUID):
            return access_request

        def add(self, value: object) -> None:
            self.added.append(value)

        async def commit(self) -> None:
            return None

        async def refresh(self, _account: CoordinatorAccount) -> None:
            return None

    session = ApprovalSession()
    result = await decide_coordinator_access_request(
        access_request.id,
        CoordinatorAccessDecision(decision="approve"),
        admin,
        session,
    )

    created_account = next(item for item in session.added if isinstance(item, CoordinatorAccount))
    assert result.status == "approved"
    assert access_request.status == "approved"
    assert access_request.password_hash is None
    assert created_account.role == "coordinator"
    assert created_account.is_active
    assert created_account.password_hash is not None
