import uuid
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.application import app
from app.database.session import SessionLocal
from app.models.core import (
    AIConfiguration,
    AIRun,
    AIRunStatus,
    Contact,
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    Organization,
    WhatsAppAccount,
)
from app.services.ai.contracts import AIResult
from app.services.ai.retrieval import relevance_score
from app.tasks.ai import generate_ai_reply

client = TestClient(app)


def test_ai_configuration_feedback_and_approved_learning() -> None:
    suffix = uuid.uuid4().hex[:10]
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"Empresa {suffix}",
            "organization_slug": f"ai-{suffix}",
            "admin_name": "Administrador",
            "admin_email": f"ai-{suffix}@example.com",
            "password": "senha-segura-123",
        },
    )
    organization_id = uuid.UUID(registration.json()["organization"]["id"])
    headers = {
        "Authorization": f"Bearer {registration.json()['token']['access_token']}"
    }
    try:
        configuration = client.patch(
            "/api/v1/ai/configuration",
            headers=headers,
            json={"tone": "consultivo", "retrieval_limit": 4},
        )
        assert configuration.status_code == 200
        assert configuration.json()["tone"] == "consultivo"
        operating_hours = client.post(
            "/api/v1/knowledge/sources/manual",
            headers=headers,
            json={
                "title": "Horários de atendimento",
                "content": "Atendemos somente de segunda a sexta.",
            },
        )
        assert operating_hours.status_code == 201

        with SessionLocal() as session:
            account = WhatsAppAccount(
                organization_id=organization_id,
                display_name="Principal",
                phone_number=f"5511{suffix}",
            )
            contact = Contact(
                organization_id=organization_id,
                phone_number=f"5522{suffix}",
            )
            session.add_all([account, contact])
            session.flush()
            conversation = Conversation(
                organization_id=organization_id,
                whatsapp_account_id=account.id,
                contact_id=contact.id,
            )
            session.add(conversation)
            session.flush()
            conversation_id = str(conversation.id)
            message = Message(
                organization_id=organization_id,
                conversation_id=conversation.id,
                direction=MessageDirection.INBOUND,
                message_type=MessageType.TEXT,
                status=MessageStatus.RECEIVED,
                body="Qual é o prazo para troca?",
            )
            session.add(message)
            session.flush()
            run = AIRun(
                organization_id=organization_id,
                conversation_id=conversation.id,
                input_message_id=message.id,
                status=AIRunStatus.COMPLETED,
                prompt_version="v1",
            )
            session.add(run)
            ai_input = Message(
                organization_id=organization_id,
                conversation_id=conversation.id,
                direction=MessageDirection.INBOUND,
                message_type=MessageType.TEXT,
                status=MessageStatus.RECEIVED,
                body="Vocês atendem aos sábados?",
            )
            session.add(ai_input)
            session.flush()
            session.add(
                AIRun(
                    organization_id=organization_id,
                    conversation_id=conversation.id,
                    input_message_id=ai_input.id,
                    status=AIRunStatus.PENDING,
                    prompt_version="customer-service-v1",
                )
            )
            configuration_record = session.scalar(
                select(AIConfiguration).where(
                    AIConfiguration.organization_id == organization_id
                )
            )
            configuration_record.is_enabled = True
            session.commit()
            run_id = str(run.id)
            ai_input_id = str(ai_input.id)

        with (
            patch(
                "app.tasks.ai.get_settings",
                return_value=SimpleNamespace(
                    openai_api_key="test-key", openai_model="gpt-test"
                ),
            ),
            patch(
                "app.tasks.ai.OpenAIResponsesProvider.generate",
                return_value=AIResult(
                    content="Atendemos somente de segunda a sexta.",
                    confidence=92,
                    provider="openai",
                    model="gpt-test",
                ),
            ),
            patch("app.tasks.ai.enqueue_outbound_message") as enqueue,
        ):
            generate_ai_reply.run(ai_input_id)
        enqueue.assert_called_once()
        with SessionLocal() as session:
            generated_run = session.scalar(
                select(AIRun).where(AIRun.input_message_id == uuid.UUID(ai_input_id))
            )
            generated_message = session.get(Message, generated_run.output_message_id)
            assert generated_run.status == AIRunStatus.COMPLETED
            assert generated_run.confidence == 92
            assert generated_run.model == "gpt-test"
            assert generated_message.body == "Atendemos somente de segunda a sexta."

        messages = client.get(
            f"/api/v1/conversations/{conversation_id}/messages", headers=headers
        )
        assert messages.status_code == 200
        generated_payload = next(
            item
            for item in messages.json()
            if item["body"] == "Atendemos somente de segunda a sexta."
        )
        assert generated_payload["ai_run_id"] == str(generated_run.id)

        feedback = client.post(
            f"/api/v1/ai/runs/{run_id}/feedback",
            headers=headers,
            json={
                "rating": "unhelpful",
                "correction": "O prazo para troca é de sete dias após o recebimento.",
            },
        )
        assert feedback.status_code == 200

        metrics = client.get("/api/v1/ai/metrics", headers=headers)
        assert metrics.status_code == 200
        assert metrics.json()["total_runs"] == 2
        assert metrics.json()["completed_runs"] == 2
        assert metrics.json()["average_confidence"] == 92
        assert metrics.json()["correction_feedback"] == 1

        suggestions = client.get("/api/v1/ai/knowledge-suggestions", headers=headers)
        assert suggestions.status_code == 200
        assert suggestions.json()[0]["status"] == "pending"

        approved = client.post(
            f"/api/v1/ai/knowledge-suggestions/{suggestions.json()[0]['id']}/approve",
            headers=headers,
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        simulation = client.post(
            "/api/v1/ai/simulate",
            headers=headers,
            json={"question": "Qual é o prazo para troca?"},
        )
        assert simulation.status_code == 200
        assert simulation.json()["sources"]
        assert "sete dias" in simulation.json()["sources"][0]["content"]

        unknown_simulation = client.post(
            "/api/v1/ai/simulate",
            headers=headers,
            json={"question": "Existe estacionamento com carregador elétrico?"},
        )
        assert unknown_simulation.status_code == 200
        assert unknown_simulation.json()["should_handoff"] is True
        assert unknown_simulation.json()["sources"] == []

        sources = client.get("/api/v1/knowledge/sources", headers=headers)
        assert any("Resposta aprendida" in source["title"] for source in sources.json())
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()


def test_lexical_relevance_prioritizes_matching_content() -> None:
    query = "qual o prazo de troca"
    matching = relevance_score(query, "O prazo para troca é de sete dias.")
    unrelated = relevance_score(query, "Funcionamos de segunda a sexta.")
    assert matching > unrelated

    morphological_match = relevance_score(
        "Qual é o horário de atendimento?",
        "Atendemos de segunda a sexta. Informe o horário desejado.",
    )
    assert morphological_match >= 2.5


def test_lexical_relevance_understands_accents_and_commercial_synonyms() -> None:
    exchange = relevance_score(
        "Quanto tempo tenho para devolver o produto?",
        "O prazo para troca é de sete dias após o recebimento.",
    )
    unrelated = relevance_score(
        "Quanto tempo tenho para devolver o produto?",
        "Aceitamos pagamentos com cartão e Pix.",
    )
    assert exchange > unrelated
    assert exchange >= 2.5

    hours = relevance_score(
        "Que horas vocês abrem?",
        "Nosso horário de funcionamento é das 9h às 18h.",
    )
    assert hours >= 2

    accent_insensitive = relevance_score(
        "Qual o endereco?",
        "Nossa localização fica na Avenida Atlântica.",
    )
    assert accent_insensitive >= 2
