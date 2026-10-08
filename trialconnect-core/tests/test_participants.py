from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.participant import Patient


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

    async def execute(self, _query: object) -> ScalarResult:
        return ScalarResult(list(self.patients.values()))

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
def client() -> TestClient:
    session = SessionStub()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


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
