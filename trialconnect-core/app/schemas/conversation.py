from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def trim_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message cannot be blank")
        return value


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    sender: Literal["patient", "coordinator"]
    body: str
    created_at: datetime
    read_at: datetime | None


class MessageReadRequest(BaseModel):
    message_ids: list[UUID] = Field(min_length=1, max_length=200)


class CoordinatorUnreadMessage(BaseModel):
    id: UUID
    patient_id: UUID
    patient_given_name: str
    patient_family_name: str
    body: str
    created_at: datetime


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def trim_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question cannot be blank")
        return value


class AssistantAnswer(BaseModel):
    answer: str
    category: str
    automated: bool = True
    sources: list["AssistantSource"] = Field(default_factory=list)


class AssistantSource(BaseModel):
    title: str
    url: HttpUrl
