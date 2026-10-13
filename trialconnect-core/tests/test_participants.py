from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.patient_account import PatientAccount
from app.models.participant import Patient
from app.models.coordinator_account import CoordinatorAccount
from app.services.coordinator_auth import require_coordinator
from app.services.patient_auth import verify_password


class ScalarResult:
    def __init__(self, items: list[Patient]) -> None:
        self.items = items

    def scalars(self) -> ScalarResult:
        return self

    def all(self) -> list[Patient]:
        return self.items


class SessionStub:
    def __init__(self) -> None:
        patient_id = UUID("00000000-0000-0000-0000-000000000001")
        self.patients: dict[UUID, Patient] = {
            patient_id: Patient(
                id=patient_id,
                external_id="PAT-TEST-001",
                given_name="Alex",
                family_name="Example",
                email="alex@example.test",
                study_id="STUDY-001",
                site_id="SITE-001",
                timezone="UTC",
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        }
        self.accounts: list[PatientAccount] = []

    async def execute(self, _query: object) -> ScalarResult:
        return ScalarResult(list(self.patients.values()))

    async def scalar(self, query: object) -> Patient | PatientAccount | None:
        entity = query.column_descriptions[0]["entity"]
        values = query.compile().params.values()
        if entity is Patient:
            email = next(value for value in values if isinstance(value, str))
            return next(
                (patient for patient in self.patients.values() if patient.email.lower() == email),
                None,
            )
        if entity is PatientAccount:
            patient_id = next(value for value in values if isinstance(value, UUID))
            return next((account for account in self.accounts if account.patient_id == patient_id), None)
        raise AssertionError(f"Unexpected scalar query for {entity}")

    def add(self, value: PatientAccount | Patient) -> None:
        if isinstance(value, PatientAccount):
            self.accounts.append(value)
        else:
            self.patients[value.id] = value

    async def flush(self) -> None:
        return None

    async def get(self, _model: type[Patient], patient_id: UUID) -> Patient | None:
        return self.patients.get(patient_id)

    async def commit(self) -> None:
        now = datetime.now(UTC)
        for patient in self.patients.values():
            patient.created_at = patient.created_at or now
            patient.updated_at = now

    async def refresh(self, _patient: Patient) -> None:
        return None

    async def rollback(self) -> None:
        return None


@pytest.fixture
def session_stub() -> SessionStub:
    return SessionStub()


@pytest.fixture
def client(session_stub: SessionStub) -> TestClient:
    async def override_get_db():
        yield session_stub

    async def override_require_coordinator() -> CoordinatorAccount:
        return CoordinatorAccount(
            id=UUID("00000000-0000-0000-0000-000000000002"),
            email="coordinator@example.test",
            full_name="Test Coordinator",
            password_hash="unused",
            role="coordinator",
            is_active=True,
        )

    async def skip_admin_bootstrap() -> None:
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_coordinator] = override_require_coordinator
    from app import main

    original_bootstrap = main.bootstrap_coordinator_admin
    main.bootstrap_coordinator_admin = skip_admin_bootstrap
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        main.bootstrap_coordinator_admin = original_bootstrap
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_coordinator, None)


def test_patient_management(client: TestClient) -> None:
    patient_id = "00000000-0000-0000-0000-000000000001"
    update_response = client.patch(
        f"/api/v1/patients/{patient_id}",
        json={"is_active": False},
    )
    assert update_response.status_code == 200
    assert update_response.json()["is_active"] is False

    list_response = client.get("/api/v1/patients", params={"is_active": False})
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [patient_id]


def test_patient_management_has_legacy_route_alias(client: TestClient) -> None:
    response = client.get("/api/v1/participants")
    assert response.status_code == 200
    assert response.json()[0]["external_id"] == "PAT-TEST-001"


def test_patient_signup_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "given_name": "Alex",
            "family_name": "Example",
            "email": "not-an-email",
            "password": "long-enough-password",
        },
    )
    assert response.status_code == 422


def test_existing_patient_can_sign_up_without_activation_code(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.settings.AUTH_SECRET", "s" * 48)
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "alex@example.test", "password": "long-enough-password"},
    )

    assert response.status_code == 201
    assert response.json()["patient"]["id"] == "00000000-0000-0000-0000-000000000001"
    assert response.json()["patient"]["given_name"] == "Alex"


def test_existing_patient_signup_stores_password_hash(
    client: TestClient,
    session_stub: SessionStub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.settings.AUTH_SECRET", "s" * 48)
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": " ALEX@EXAMPLE.TEST ", "password": "long-enough-password"},
    )

    assert response.status_code == 201
    assert len(session_stub.accounts) == 1
    account = session_stub.accounts[0]
    assert account.email == "alex@example.test"
    assert verify_password("long-enough-password", account.password_hash)


def test_new_patient_can_sign_up_with_name_and_email(
    client: TestClient,
    session_stub: SessionStub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.settings.AUTH_SECRET", "s" * 48)
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "given_name": "Jamie",
            "family_name": "Patient",
            "email": "jamie@example.test",
            "password": "long-enough-password",
        },
    )

    assert response.status_code == 201
    assert response.json()["patient"]["given_name"] == "Jamie"
    assert len(session_stub.patients) == 2


def test_new_signup_without_patient_record_or_names_gets_helpful_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.settings.AUTH_SECRET", "s" * 48)
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "new@example.test", "password": "long-enough-password"},
    )

    assert response.status_code == 404
    assert "Enter your name" in response.json()["detail"]


def test_existing_patient_with_account_is_directed_to_login(
    client: TestClient,
    session_stub: SessionStub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.settings.AUTH_SECRET", "s" * 48)
    session_stub.accounts.append(
        PatientAccount(
            patient_id=UUID("00000000-0000-0000-0000-000000000001"),
            email="alex@example.test",
            password_hash="unused",
        )
    )
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "alex@example.test", "password": "long-enough-password"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "An account already exists. Please log in."
