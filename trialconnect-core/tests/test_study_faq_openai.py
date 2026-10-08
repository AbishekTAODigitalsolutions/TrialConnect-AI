from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from openai import RateLimitError

import app.services.study_faq as study_faq
from app.config import settings
from app.services.study_faq import (
    AssistantConfigurationError,
    AssistantProviderError,
    generate_study_answer,
)


class FakeResponses:
    def __init__(self, result: SimpleNamespace) -> None:
        self.result = result
        self.request: dict[str, object] = {}
        self.error: Exception | None = None

    async def create(self, **request: object) -> SimpleNamespace:
        self.request = request
        if self.error is not None:
            raise self.error
        return self.result


class FakeOpenAIClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses

    async def __aenter__(self) -> FakeOpenAIClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_openai_web_search_answer_returns_cited_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    annotation = SimpleNamespace(
        type="url_citation",
        url="https://example.test/study-process",
        title="Study process guidance",
    )
    response = SimpleNamespace(
        output_text="A clinical trial follows an approved plan [1].",
        output=[
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(
                        type="output_text",
                        annotations=[annotation, annotation],
                    )
                ],
            )
        ],
    )
    fake_responses = FakeResponses(response)
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "test-model")
    monkeypatch.setattr(
        study_faq,
        "AsyncOpenAI",
        lambda api_key: FakeOpenAIClient(fake_responses),
    )

    answer = await generate_study_answer("What is a clinical study?")

    assert answer.answer == response.output_text
    assert answer.category == "web_search"
    assert len(answer.sources) == 1
    assert str(answer.sources[0].url) == annotation.url
    assert fake_responses.request["tools"] == [
        {"type": "web_search", "search_context_size": "low"}
    ]
    assert fake_responses.request["tool_choice"] == "required"


@pytest.mark.asyncio
async def test_medical_questions_never_call_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_openai_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("medical questions must not be sent to OpenAI")

    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(study_faq, "AsyncOpenAI", unexpected_openai_call)

    answer = await generate_study_answer("Should I change my medication dose?")

    assert answer.category == "medical_redirect"


@pytest.mark.asyncio
async def test_enabled_openai_requires_key_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "")

    with pytest.raises(AssistantConfigurationError, match="OPENAI_API_KEY"):
        await generate_study_answer("What is a clinical study?")


@pytest.mark.asyncio
async def test_empty_openai_response_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_responses = FakeResponses(SimpleNamespace(output_text="  ", output=[]))
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "test-model")
    monkeypatch.setattr(
        study_faq,
        "AsyncOpenAI",
        lambda api_key: FakeOpenAIClient(fake_responses),
    )

    with pytest.raises(AssistantProviderError, match="empty response"):
        await generate_study_answer("What is a clinical study?")


@pytest.mark.asyncio
async def test_exhausted_openai_credits_are_reported_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error_body = {
        "message": "No credits remaining",
        "type": "insufficient_quota",
        "code": "credit_balance_exhausted",
    }
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        json=error_body,
    )
    fake_responses = FakeResponses(SimpleNamespace(output_text="", output=[]))
    fake_responses.error = RateLimitError(
        "No credits remaining",
        response=response,
        body=error_body,
    )
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "test-model")
    monkeypatch.setattr(
        study_faq,
        "AsyncOpenAI",
        lambda api_key: FakeOpenAIClient(fake_responses),
    )

    with pytest.raises(AssistantProviderError, match="OpenAI API credits are exhausted"):
        await generate_study_answer("What is a clinical study?")
