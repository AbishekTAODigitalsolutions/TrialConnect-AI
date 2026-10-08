from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.conversation import ConversationMessage
from app.models.participant import Patient
from app.schemas.conversation import (
    AssistantAnswer,
    AssistantQuestion,
    MessageCreate,
    MessageRead,
)
from app.services.patient_auth import require_patient
from app.services.study_faq import (
    AssistantConfigurationError,
    AssistantProviderError,
    generate_study_answer,
)

patient_router = APIRouter(prefix="/messages", tags=["patient conversations"])
coordinator_router = APIRouter(prefix="/coordinator/patients", tags=["coordinator conversations"])
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
    session: AsyncSession = Depends(get_db),
) -> list[ConversationMessage]:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return await _get_messages(patient.id, session, limit)


@coordinator_router.post("/{patient_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def coordinator_send_message(
    patient_id: UUID,
    request: MessageCreate,
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
