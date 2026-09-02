from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.ai.contracts import AIMessage, AIRequest
from app.services.ai.openai_provider import OpenAIAnswer, OpenAIResponsesProvider


def test_provider_rejects_unsafe_output_limits() -> None:
    with pytest.raises(ValueError, match="entre 64 e 600"):
        OpenAIResponsesProvider(
            api_key="offline-test-key",
            model="offline-test",
            max_output_tokens=601,
        )


def test_provider_forwards_controlled_output_limit_without_external_call() -> None:
    provider = OpenAIResponsesProvider(
        api_key="offline-test-key",
        model="offline-test",
        max_output_tokens=300,
    )
    parse = Mock(
        return_value=SimpleNamespace(
            output_parsed=OpenAIAnswer(
                answer="Atendimento das 9h às 18h.",
                confidence=95,
                should_handoff=False,
            ),
            usage=SimpleNamespace(input_tokens=20, output_tokens=30),
        )
    )
    provider.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))

    result = provider.generate(
        AIRequest(
            system_instructions="Responda com base no contexto.",
            messages=[AIMessage(role="user", content="Qual é o horário?")],
        )
    )

    assert result.content == "Atendimento das 9h às 18h."
    assert result.input_tokens == 20
    assert result.output_tokens == 30
    assert parse.call_args.kwargs["max_output_tokens"] == 300
