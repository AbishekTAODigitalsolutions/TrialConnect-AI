from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.coordinator_account import CoordinatorAccount, CoordinatorAuditEvent
from app.models.conversation import ConversationMessage, CoordinatorMessageRead
from app.models.participant import Patient
from app.schemas.conversation import (
    AssistantAnswer,
    AssistantQuestion,
    CoordinatorUnreadMessage,
    MessageCreate,
    MessageRead,
    MessageReadRequest,
)
from app.services.patient_auth import require_patient
from app.services.coordinator_auth import require_coordinator
from app.services.study_faq import (
    AssistantConfigurationError,
    AssistantProviderError,
    generate_study_answer,
)

patient_router = APIRouter(prefix="/messages", tags=["patient conversations"])
coordinator_router = APIRouter(prefix="/coordinator/patients", tags=["coordinator conversations"])
coordinator_notification_router = APIRouter(prefix="/coordinator", tags=["coordinator notifications"])
faq_router = APIRouter(prefix="/assistant", tags=["study FAQ"])
audit_logger = structlog.get_logger("audit")


async def _get_messages(
    patient_id: UUID,
    session: AsyncSession,
    limit: int,
) -> list[ConversationMessage]:
    result = await session.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.patient_id == patient_id)
        .order_by(ConversationMessage.created_at, ConversationMessage.id)
        .limit(limit)
    )
    return list(result.all())


@patient_router.get("", response_model=list[MessageRead])
async def patient_messages(
    limit: int = Query(default=100, ge=1, le=200),
    patient: Patient = Depends(require_patient),
    session: AsyncSession = Depends(get_db),
) -> list[ConversationMessage]:
    return await _get_messages(patient.id, session, limit)


@patient_router.get("/unread", response_model=list[MessageRead])
async def patient_unread_messages(
    patient: Patient = Depends(require_patient),
    session: AsyncSession = Depends(get_db),
) -> list[ConversationMessage]:
    result = await session.scalars(
        select(ConversationMessage)
        .where(
            ConversationMessage.patient_id == patient.id,
            ConversationMessage.sender == "coordinator",
            ConversationMessage.read_at.is_(None),
        )
        .order_by(ConversationMessage.created_at.desc())
        .limit(100)
    )
    return list(result.all())


@patient_router.patch("/read", status_code=status.HTTP_204_NO_CONTENT)
async def patient_mark_messages_read(
    request: MessageReadRequest,
    patient: Patient = Depends(require_patient),
    session: AsyncSession = Depends(get_db),
) -> Response:
    result = await session.scalars(
        select(ConversationMessage).where(
            ConversationMessage.patient_id == patient.id,
            ConversationMessage.id.in_(request.message_ids),
            ConversationMessage.sender == "coordinator",
            ConversationMessage.read_at.is_(None),
        )
    )
    now = datetime.now(UTC)
    for message in result.all():
        message.read_at = now
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@patient_router.post("", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def patient_send_message(
    request: MessageCreate,
    patient: Patient = Depends(require_patient),
    session: AsyncSession = Depends(get_db),
) -> ConversationMessage:
    message = ConversationMessage(patient_id=patient.id, sender="patient", body=request.body)
    session.add(message)
    await session.commit()
    await session.refresh(message)
    audit_logger.info("patient_message_sent", patient_id=str(patient.id), message_id=str(message.id))
    return message


@coordinator_router.get("/{patient_id}/messages", response_model=list[MessageRead])
async def coordinator_messages(
    patient_id: UUID,
    limit: int = Query(default=100, ge=1, le=200),
    _coordinator: CoordinatorAccount = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db),
) -> list[ConversationMessage]:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return await _get_messages(patient.id, session, limit)


@coordinator_notification_router.get(
    "/messages/unread",
    response_model=list[CoordinatorUnreadMessage],
)
async def coordinator_unread_messages(
    coordinator: CoordinatorAccount = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db),
) -> list[CoordinatorUnreadMessage]:
    result = await session.execute(
        select(ConversationMessage, Patient)
        .join(Patient, ConversationMessage.patient_id == Patient.id)
        .outerjoin(
            CoordinatorMessageRead,
            (CoordinatorMessageRead.message_id == ConversationMessage.id)
            & (CoordinatorMessageRead.coordinator_id == coordinator.id),
        )
        .where(
            ConversationMessage.sender == "patient",
            CoordinatorMessageRead.id.is_(None),
        )
        .order_by(ConversationMessage.created_at.desc())
        .limit(200)
    )
    return [
        CoordinatorUnreadMessage(
            id=message.id,
            patient_id=patient.id,
            patient_given_name=patient.given_name,
            patient_family_name=patient.family_name,
            body=message.body,
            created_at=message.created_at,
        )
        for message, patient in result.all()
    ]


@coordinator_router.patch("/{patient_id}/messages/read", status_code=status.HTTP_204_NO_CONTENT)
async def coordinator_mark_messages_read(
    patient_id: UUID,
    request: MessageReadRequest,
    coordinator: CoordinatorAccount = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db),
) -> Response:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    result = await session.scalars(
        select(ConversationMessage).where(
            ConversationMessage.patient_id == patient.id,
            ConversationMessage.id.in_(request.message_ids),
            ConversationMessage.sender == "patient",
        )
    )
    now = datetime.now(UTC)
    messages = list(result.all())
    if messages:
        receipt_result = await session.execute(
            insert(CoordinatorMessageRead)
            .values(
                [
                    {
                        "message_id": message.id,
                        "coordinator_id": coordinator.id,
                        "read_at": now,
                    }
                    for message in messages
                ]
            )
            .on_conflict_do_nothing(
                index_elements=[
                    CoordinatorMessageRead.message_id,
                    CoordinatorMessageRead.coordinator_id,
                ]
            )
            .returning(CoordinatorMessageRead.message_id)
        )
        newly_read_ids = list(receipt_result.scalars().all())
        session.add_all(
            CoordinatorAuditEvent(
                coordinator_id=coordinator.id,
                email=coordinator.email,
                event_type="message_read",
                patient_id=patient.id,
                message_id=message_id,
            )
            for message_id in newly_read_ids
        )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@coordinator_router.post("/{patient_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def coordinator_send_message(
    patient_id: UUID,
    request: MessageCreate,
    coordinator: CoordinatorAccount = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db),
) -> ConversationMessage:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    message = ConversationMessage(patient_id=patient.id, sender="coordinator", body=request.body)
    session.add(message)
    await session.commit()
    await session.refresh(message)
    audit_logger.info("coordinator_message_sent", patient_id=str(patient.id), message_id=str(message.id))
    return message


@faq_router.post("/faq", response_model=AssistantAnswer)
async def ask_study_faq(
    request: AssistantQuestion,
    _patient: Patient = Depends(require_patient),
) -> AssistantAnswer:
    try:
        answer = await generate_study_answer(request.question)
    except AssistantConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AssistantProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    audit_logger.info(
        "study_faq_answered",
        category=answer.category,
        source_count=len(answer.sources),
    )
    return answer
