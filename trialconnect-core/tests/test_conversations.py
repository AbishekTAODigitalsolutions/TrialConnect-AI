from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.conversation import ConversationMessage
from app.models.participant import Patient
from app.services.patient_auth import require_patient
from app.services.study_faq import answer_study_question


PATIENT_ID = UUID("00000000-0000-0000-0000-000000000001")


class MessageResults:
    def __init__(self, messages: list[ConversationMessage]) -> None:
        self.messages = messages

    def all(self) -> list[ConversationMessage]:
        return self.messages


class ConversationSessionStub:
    def __init__(self) -> None:
        self.patient = Patient(
            id=PATIENT_ID,
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
        self.messages: list[ConversationMessage] = []

    async def get(self, _model: type[Patient], patient_id: UUID) -> Patient | None:
        return self.patient if patient_id == PATIENT_ID else None

    async def scalars(self, _query: object) -> MessageResults:
        return MessageResults(self.messages)

    def add(self, message: ConversationMessage) -> None:
        message.id = uuid4()
        self.messages.append(message)

    async def commit(self) -> None:
        now = datetime.now(UTC)
        for message in self.messages:
            message.created_at = message.created_at or now

    async def refresh(self, _message: ConversationMessage) -> None:
        return None


@pytest.fixture
def conversation_client():
    session = ConversationSessionStub()

    async def override_get_db():
        yield session

    async def override_require_patient() -> Patient:
        return session.patient

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_patient] = override_require_patient
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_patient, None)


def test_patient_and_coordinator_can_exchange_messages(conversation_client: TestClient) -> None:
    patient_send = conversation_client.post(
        "/api/v1/messages",
        json={"body": "Can you tell me when my next study visit is?"},
    )
    assert patient_send.status_code == 201
    assert patient_send.json()["sender"] == "patient"

    coordinator_reply = conversation_client.post(
        f"/api/v1/coordinator/patients/{PATIENT_ID}/messages",
        json={"body": "Please contact the study office to confirm your visit."},
    )
    assert coordinator_reply.status_code == 201
    assert coordinator_reply.json()["sender"] == "coordinator"

    history = conversation_client.get("/api/v1/messages")
    assert history.status_code == 200
    assert [message["sender"] for message in history.json()] == ["patient", "coordinator"]

    coordinator_history = conversation_client.get(
        f"/api/v1/coordinator/patients/{PATIENT_ID}/messages"
    )
    assert coordinator_history.status_code == 200
    assert len(coordinator_history.json()) == 2


def test_patient_message_rejects_blank_body(conversation_client: TestClient) -> None:
    response = conversation_client.post("/api/v1/messages", json={"body": "   "})
    assert response.status_code == 422


def test_patient_messages_require_login() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/messages")
    assert response.status_code == 401


def test_study_faq_redirects_medical_questions() -> None:
    response = answer_study_question("Should I change my medication dose?")
    assert response.category == "medical_redirect"
    assert "medical questions" in response.answer


def test_study_faq_answers_only_bounded_study_information() -> None:
    response = answer_study_question("How can I contact the coordinator?")
    assert response.category == "coordinator"
    assert response.automated is True


def test_study_faq_api_reports_missing_openai_configuration(
    conversation_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "")

    response = conversation_client.post(
        "/api/v1/assistant/faq",
        json={"question": "What is a clinical study?"},
    )

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]
