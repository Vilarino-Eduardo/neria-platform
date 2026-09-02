import pytest

from app.services.ai.retrieval import relevance_score


@pytest.mark.parametrize(
    ("segment", "question", "relevant", "unrelated"),
    [
        (
            "comercio_pagamento",
            "Consigo parcelar?",
            "O pagamento pode ser feito no cartão em três parcelas.",
            "A entrega ocorre em até cinco dias úteis.",
        ),
        (
            "comercio_estoque",
            "Tem em estoque?",
            "Consulte a disponibilidade atual antes de concluir o pedido.",
            "Aceitamos pagamentos com cartão e Pix.",
        ),
        (
            "servico_reagendamento",
            "Preciso remarcar minha reserva.",
            "O reagendamento deve ser solicitado com 24 horas de antecedência.",
            "O endereço da clínica fica no centro.",
        ),
        (
            "servico_cancelamento",
            "Quero cancelar o horário marcado.",
            "Cancelamentos de horários marcados devem ser informados com antecedência.",
            "O pagamento pode ser realizado por Pix.",
        ),
        (
            "autonomo_orcamento",
            "Qual é o orçamento do serviço?",
            "O investimento é calculado após a avaliação do projeto.",
            "O atendimento acontece de segunda a sexta.",
        ),
    ],
)
def test_market_vocabulary_prioritizes_relevant_content(
    segment: str,
    question: str,
    relevant: str,
    unrelated: str,
) -> None:
    relevant_score = relevance_score(question, relevant)
    unrelated_score = relevance_score(question, unrelated)

    assert relevant_score >= 1.5, segment
    assert relevant_score > unrelated_score, segment
