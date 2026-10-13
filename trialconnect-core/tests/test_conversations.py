from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.conversation import ConversationMessage
from app.models.coordinator_account import CoordinatorAccount, CoordinatorAuditEvent
from app.models.participant import Patient
from app.services.coordinator_auth import require_coordinator
from app.services.patient_auth import require_patient
from app.services.study_faq import answer_study_question


PATIENT_ID = UUID("00000000-0000-0000-0000-000000000001")


class MessageResults:
    def __init__(self, messages: list[ConversationMessage]) -> None:
        self.messages = messages

    def all(self) -> list[ConversationMessage]:
        return self.messages


class RowResults:
    def __init__(self, rows: list[tuple[ConversationMessage, Patient]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[ConversationMessage, Patient]]:
        return self.rows


class ScalarListResults:
    def __init__(self, values: list[UUID]) -> None:
        self.values = values

    def scalars(self) -> ScalarListResults:
        return self

    def all(self) -> list[UUID]:
        return self.values


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
        self.audit_events: list[CoordinatorAuditEvent] = []
        self.coordinator = CoordinatorAccount(
            id=UUID("00000000-0000-0000-0000-000000000002"),
            email="coordinator@example.test",
            full_name="Test Coordinator",
            password_hash="unused",
            role="coordinator",
            is_active=True,
        )
        self.read_receipts: set[UUID] = set()

    async def get(self, _model: type[Patient], patient_id: UUID) -> Patient | None:
        return self.patient if patient_id == PATIENT_ID else None

    async def scalars(self, query: object) -> MessageResults:
        query_text = str(query)
        params = query.compile().params.values()
        filtered = list(self.messages)
        if "conversation_messages.sender =" in query_text:
            sender = next(value for value in params if isinstance(value, str))
            filtered = [message for message in filtered if message.sender == sender]
        if "conversation_messages.patient_id =" in query_text:
            patient_id = next(value for value in params if isinstance(value, UUID))
            filtered = [message for message in filtered if message.patient_id == patient_id]
        if "conversation_messages.id IN" in query_text:
            message_ids = next(value for value in params if isinstance(value, list))
            filtered = [message for message in filtered if message.id in message_ids]
        if "conversation_messages.read_at IS NULL" in query_text:
            filtered = [message for message in filtered if message.read_at is None]
        return MessageResults(filtered)

    async def execute(self, _query: object) -> RowResults:
        if "INSERT INTO coordinator_message_reads" in str(_query):
            values = _query.compile().params
            message_ids = [
                value
                for key, value in values.items()
                if key.startswith("message_id")
            ]
            new_ids = [message_id for message_id in message_ids if message_id not in self.read_receipts]
            self.read_receipts.update(new_ids)
            return ScalarListResults(new_ids)
        unread_patient_messages = [
            message
            for message in self.messages
            if message.sender == "patient" and message.read_at is None
            and message.id not in self.read_receipts
        ]
        return RowResults([(message, self.patient) for message in unread_patient_messages])

    def add(self, message: ConversationMessage | CoordinatorAuditEvent) -> None:
        if isinstance(message, ConversationMessage):
            message.id = uuid4()
            self.messages.append(message)
        else:
            self.audit_events.append(message)

    def add_all(self, values: list[CoordinatorAuditEvent]) -> None:
        for value in values:
            self.add(value)

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

    async def override_require_coordinator() -> CoordinatorAccount:
        return session.coordinator

    async def skip_admin_bootstrap() -> None:
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_patient] = override_require_patient
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
        app.dependency_overrides.pop(require_patient, None)
        app.dependency_overrides.pop(require_coordinator, None)


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
    assert history.json()[0]["read_at"] is None

    coordinator_history = conversation_client.get(
        f"/api/v1/coordinator/patients/{PATIENT_ID}/messages"
    )
    assert coordinator_history.status_code == 200
    assert len(coordinator_history.json()) == 2


def test_incoming_messages_are_listed_and_marked_read_per_recipient(
    conversation_client: TestClient,
) -> None:
    patient_message = conversation_client.post(
        "/api/v1/messages",
        json={"body": "Message from patient"},
    ).json()
    coordinator_message = conversation_client.post(
        f"/api/v1/coordinator/patients/{PATIENT_ID}/messages",
        json={"body": "Message from coordinator"},
    ).json()

    patient_unread = conversation_client.get("/api/v1/messages/unread")
    assert [message["id"] for message in patient_unread.json()] == [coordinator_message["id"]]
    patient_read = conversation_client.patch(
        "/api/v1/messages/read",
        json={"message_ids": [coordinator_message["id"]]},
    )
    assert patient_read.status_code == 204
    assert conversation_client.get("/api/v1/messages/unread").json() == []

    coordinator_unread = conversation_client.get("/api/v1/coordinator/messages/unread")
    assert [message["id"] for message in coordinator_unread.json()] == [patient_message["id"]]
    assert coordinator_unread.json()[0]["patient_given_name"] == "Alex"
    coordinator_read = conversation_client.patch(
        f"/api/v1/coordinator/patients/{PATIENT_ID}/messages/read",
        json={"message_ids": [patient_message["id"]]},
    )
    assert coordinator_read.status_code == 204
    assert conversation_client.get("/api/v1/coordinator/messages/unread").json() == []


def test_patient_message_rejects_blank_body(conversation_client: TestClient) -> None:
    response = conversation_client.post("/api/v1/messages", json={"body": "   "})
    assert response.status_code == 422


def test_patient_messages_require_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUTH_SECRET", "s" * 48)
    with TestClient(app) as client:
        response = client.get("/api/v1/messages")
    assert response.status_code == 401


def test_study_faq_redirects_medical_questions() -> None:
    response = answer_study_question("Should I change my medication dose?")
    assert response.category == "medical_redirect"
    assert "interpret personal symptoms" in response.answer


def test_study_faq_answers_only_bounded_study_information() -> None:
    response = answer_study_question("How can I contact the coordinator?")
    assert response.category == "coordinator"
    assert response.automated is True


def test_study_faq_api_reports_missing_ollama_configuration(
    conversation_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "")

    response = conversation_client.post(
        "/api/v1/assistant/faq",
        json={"question": "What does the portal's teal color represent?"},
    )

    assert response.status_code == 503
    assert "OLLAMA_BASE_URL" in response.json()["detail"]
