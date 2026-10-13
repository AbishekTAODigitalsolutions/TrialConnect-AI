from __future__ import annotations

from typing import Any

import httpx
import pytest

import app.services.study_faq as study_faq
from app.config import settings
from app.services.study_faq import (
    AssistantConfigurationError,
    AssistantProviderError,
    generate_study_answer,
)


class FakeOllamaResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FakeOllamaClient:
    def __init__(self, response: FakeOllamaResponse) -> None:
        self.response = response
        self.request_url: str | None = None
        self.request_json: dict[str, Any] | None = None

    async def __aenter__(self) -> FakeOllamaClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, url: str, *, json: dict[str, Any]) -> FakeOllamaResponse:
        self.request_url = url
        self.request_json = json
        return self.response


@pytest.mark.asyncio
async def test_ollama_answer_uses_local_chat_api(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeOllamaClient(
        FakeOllamaResponse({"message": {"content": "{\"category\":\"study\",\"explanation\":\"\"}"}})
    )
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama.test/")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "test-model")
    monkeypatch.setattr(study_faq.httpx, "AsyncClient", lambda **_kwargs: fake_client)

    answer = await generate_study_answer("What does the portal's teal color represent?")

    assert answer.category == "study"
    assert "approved study plan" in answer.answer
    assert answer.sources == []
    assert fake_client.request_url == "http://ollama.test/api/chat"
    assert fake_client.request_json is not None
    assert fake_client.request_json["model"] == "test-model"
    assert fake_client.request_json["stream"] is False
    assert fake_client.request_json["think"] is False
    assert fake_client.request_json["options"] == {"temperature": 0, "num_predict": 128}
    assert fake_client.request_json["format"]["properties"]["category"]["enum"] == [
        "coordinator",
        "appointments",
        "study",
        "privacy",
        "account",
        "medical_education",
        "coordinator_redirect",
    ]
    assert [item["role"] for item in fake_client.request_json["messages"]] == ["system", "user"]


@pytest.mark.asyncio
async def test_known_faq_answer_does_not_wait_for_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_ollama_call(**_kwargs: object) -> None:
        raise AssertionError("known FAQ answers must not call Ollama")

    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(study_faq.httpx, "AsyncClient", unexpected_ollama_call)

    answer = await generate_study_answer("How can I contact my study coordinator?")

    assert answer.category == "coordinator"
    assert "coordinator conversation" in answer.answer


@pytest.mark.asyncio
async def test_medical_questions_never_call_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_ollama_call(**_kwargs: object) -> None:
        raise AssertionError("medical questions must not be sent to Ollama")

    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(study_faq.httpx, "AsyncClient", unexpected_ollama_call)

    answer = await generate_study_answer("Should I change my medication dose?")

    assert answer.category == "medical_redirect"


@pytest.mark.asyncio
async def test_general_medical_definition_returns_brief_explanation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOllamaClient(
        FakeOllamaResponse(
            {
                "message": {
                    "content": (
                        '{"category":"medical_education",'
                        '"explanation":"A migraine is a type of headache disorder that can involve recurring head pain."}'
                    )
                }
            }
        )
    )
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "test-model")
    monkeypatch.setattr(study_faq.httpx, "AsyncClient", lambda **_kwargs: fake_client)

    answer = await generate_study_answer("What is a migraine?")

    assert answer.category == "medical_education"
    assert answer.answer.startswith("A migraine is a type of headache disorder")
    assert "not a diagnosis or recommendation" in answer.answer
    assert fake_client.request_json is not None
    assert "Do not assess an individual" in fake_client.request_json["messages"][0]["content"]


@pytest.mark.asyncio
async def test_personal_medical_question_is_redirected_without_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_ollama_call(**_kwargs: object) -> None:
        raise AssertionError("personal medical questions must not be sent to Ollama")

    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(study_faq.httpx, "AsyncClient", unexpected_ollama_call)

    answer = await generate_study_answer("What does my headache mean?")

    assert answer.category == "medical_redirect"
    assert "interpret personal symptoms" in answer.answer


@pytest.mark.asyncio
async def test_enabled_ollama_requires_url_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "")

    with pytest.raises(AssistantConfigurationError, match="OLLAMA_BASE_URL"):
        await generate_study_answer("What does the portal's teal color represent?")


@pytest.mark.asyncio
async def test_empty_ollama_response_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeOllamaClient(FakeOllamaResponse({"message": {"content": "  "}}))
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "test-model")
    monkeypatch.setattr(study_faq.httpx, "AsyncClient", lambda **_kwargs: fake_client)

    with pytest.raises(AssistantProviderError, match="empty response"):
        await generate_study_answer("What does the portal's teal color represent?")


@pytest.mark.asyncio
async def test_ollama_unmatched_question_uses_safe_coordinator_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOllamaClient(
        FakeOllamaResponse(
            {"message": {"content": "{\"category\":\"coordinator_redirect\",\"explanation\":\"\"}"}}
        )
    )
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "test-model")
    monkeypatch.setattr(study_faq.httpx, "AsyncClient", lambda **_kwargs: fake_client)

    answer = await generate_study_answer("What does teal represent?")

    assert answer.category == "coordinator_redirect"
    assert "approved answer" in answer.answer


@pytest.mark.asyncio
async def test_ollama_connection_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_connection_error(**_kwargs: object) -> None:
        raise httpx.ConnectError(
            "connection refused",
            request=httpx.Request("POST", "http://ollama.test/api/chat"),
        )

    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "test-model")
    monkeypatch.setattr(study_faq.httpx, "AsyncClient", raise_connection_error)

    with pytest.raises(AssistantProviderError, match="Could not connect to local Ollama"):
        await generate_study_answer("What does the portal's teal color represent?")
