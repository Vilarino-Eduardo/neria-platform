from app.services.ai.contracts import AIMessage, AIRequest, RetrievedKnowledge
from app.services.ai.redaction import redact_ai_request, redact_sensitive_data


def test_redacts_formatted_cpf_without_changing_phone() -> None:
    result = redact_sensitive_data(
        "CPF 123.456.789-09 e telefone (11) 99876-5432."
    )

    assert "123.456.789-09" not in result
    assert "[CPF REDIGIDO]" in result
    assert "(11) 99876-5432" in result


def test_redacts_only_luhn_valid_card_candidates() -> None:
    result = redact_sensitive_data(
        "Cartão 4111 1111 1111 1111; protocolo 1234 5678 9012 3456."
    )

    assert "4111 1111 1111 1111" not in result
    assert "[CARTÃO REDIGIDO]" in result
    assert "1234 5678 9012 3456" in result


def test_redacts_labeled_secrets_and_bearer_credentials() -> None:
    result = redact_sensitive_data(
        "CVV: 123, senha=segredo123, token: abcdefgh e Bearer abc.def-12345"
    )

    assert "123" not in result
    assert "segredo123" not in result
    assert "abcdefgh" not in result
    assert "abc.def-12345" not in result
    assert result.count("[REDIGIDO]") == 4


def test_redacts_every_provider_request_surface_without_mutating_original() -> None:
    secret = "123.456.789-09"
    request = AIRequest(
        system_instructions=f"Cliente {secret}",
        messages=[AIMessage(role="user", content=f"Meu CPF é {secret}")],
        knowledge=[
            RetrievedKnowledge(
                chunk_id="source-1",
                source_title=f"Cadastro {secret}",
                content=f"Titular {secret}",
                score=0.9,
            )
        ],
    )

    sanitized = redact_ai_request(request)

    assert secret in request.messages[0].content
    assert secret not in sanitized.system_instructions
    assert secret not in sanitized.messages[0].content
    assert secret not in sanitized.knowledge[0].source_title
    assert secret not in sanitized.knowledge[0].content
    assert sanitized.knowledge[0].chunk_id == "source-1"
    assert sanitized.knowledge[0].score == 0.9
