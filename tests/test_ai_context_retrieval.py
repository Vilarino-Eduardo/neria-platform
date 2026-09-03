import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.application import app
from app.database.session import SessionLocal
from app.models.core import (
    Contact,
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    Organization,
    WhatsAppAccount,
)
from app.services.ai.context import (
    MAX_HISTORY_CONTEXT_CHARS,
    MAX_HISTORY_MESSAGE_CHARS,
    bound_history_context,
    build_ai_request,
)
from app.services.ai.contracts import AIMessage
from app.services.ai.retrieval import LexicalKnowledgeRetriever

client = TestClient(app)


def test_history_context_keeps_newest_messages_within_character_budget() -> None:
    messages = [
        AIMessage(role="user", content=character * 5_000)
        for character in ("a", "b", "c", "d")
    ]

    bounded = bound_history_context(messages)

    assert [message.content[0] for message in bounded] == ["b", "c", "d"]
    assert all(len(message.content) <= MAX_HISTORY_MESSAGE_CHARS for message in bounded)
    assert sum(len(message.content) for message in bounded) == MAX_HISTORY_CONTEXT_CHARS


def register_organization(prefix: str) -> tuple[uuid.UUID, dict[str, str]]:
    suffix = uuid.uuid4().hex[:10]
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"Empresa {prefix}",
            "organization_slug": f"{prefix}-{suffix}",
            "admin_name": "Administrador",
            "admin_email": f"{prefix}-{suffix}@example.com",
            "password": "senha-segura-123",
        },
    )
    assert registration.status_code == 201
    return uuid.UUID(registration.json()["organization"]["id"]), {
        "Authorization": f"Bearer {registration.json()['token']['access_token']}"
    }


def test_context_memory_retrieval_and_tenant_isolation() -> None:
    organization_id, headers = register_organization("context")
    other_organization_id, other_headers = register_organization("context-other")

    try:
        configuration = client.patch(
            "/api/v1/ai/configuration",
            headers=headers,
            json={
                "history_message_limit": 4,
                "retrieval_limit": 2,
                "tone": "profissional e acolhedor",
                "instructions": "Chame a empresa de Loja Azul.",
            },
        )
        assert configuration.status_code == 200
        profile = client.patch(
            "/api/v1/organization/profile",
            headers=headers,
            json={
                "company_name": "Loja Azul",
                "description": "Loja de utilidades domésticas.",
                "opening_hours": "Segunda a sexta, das 9h às 18h.",
            },
        )
        assert profile.status_code == 200

        own_source = client.post(
            "/api/v1/knowledge/sources/manual",
            headers=headers,
            json={
                "title": "Política de trocas",
                "content": "A troca pode ser solicitada em até sete dias após o recebimento.",
            },
        )
        assert own_source.status_code == 201
        unrelated_source = client.post(
            "/api/v1/knowledge/sources/manual",
            headers=headers,
            json={
                "title": "Formas de pagamento",
                "content": "Aceitamos cartão de crédito e Pix.",
            },
        )
        assert unrelated_source.status_code == 201
        foreign_source = client.post(
            "/api/v1/knowledge/sources/manual",
            headers=other_headers,
            json={
                "title": "Política de outra empresa",
                "content": "A troca pode ser solicitada em até trinta dias.",
            },
        )
        assert foreign_source.status_code == 201

        with SessionLocal() as session:
            account = WhatsAppAccount(
                organization_id=organization_id,
                display_name="Principal",
                phone_number="5511999991000",
            )
            contact = Contact(
                organization_id=organization_id,
                phone_number="5511888881000",
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

            history = [
                (MessageDirection.INBOUND, "Mensagem antiga que deve sair do contexto."),
                (MessageDirection.OUTBOUND, "Olá, como posso ajudar?"),
                (MessageDirection.INBOUND, "Comprei uma cafeteira ontem."),
                (MessageDirection.OUTBOUND, "Entendi. Qual é a sua dúvida?"),
                (MessageDirection.INBOUND, "Qual é o prazo para troca?"),
            ]
            for direction, body in history:
                session.add(
                    Message(
                        organization_id=organization_id,
                        conversation_id=conversation.id,
                        direction=direction,
                        message_type=MessageType.TEXT,
                        status=(
                            MessageStatus.RECEIVED
                            if direction == MessageDirection.INBOUND
                            else MessageStatus.SENT
                        ),
                        body=body,
                    )
                )
                session.flush()
            session.commit()

            request = build_ai_request(
                session,
                organization_id=str(organization_id),
                conversation_id=str(conversation.id),
                question="Qual é o prazo para troca?",
                retriever=LexicalKnowledgeRetriever(session),
            )
            profile_request = build_ai_request(
                session,
                organization_id=str(organization_id),
                conversation_id=str(conversation.id),
                question="Qual é o horário de funcionamento?",
                retriever=LexicalKnowledgeRetriever(session),
            )
            no_match = LexicalKnowledgeRetriever(session).search(
                str(organization_id), "estacionamento elétrico", 2
            )

        assert [message.role for message in request.messages] == [
            "assistant",
            "user",
            "assistant",
            "user",
        ]
        assert [message.content for message in request.messages] == [
            "Olá, como posso ajudar?",
            "Comprei uma cafeteira ontem.",
            "Entendi. Qual é a sua dúvida?",
            "Qual é o prazo para troca?",
        ]
        assert "Mensagem antiga" not in " ".join(
            message.content for message in request.messages
        )
        assert request.knowledge
        assert request.knowledge[0].source_title == "Política de trocas"
        assert "sete dias" in request.knowledge[0].content
        assert all("trinta dias" not in item.content for item in request.knowledge)
        assert "Empresa: Loja Azul" in request.system_instructions
        assert "Tom de voz: profissional e acolhedor." in request.system_instructions
        assert "Chame a empresa de Loja Azul" in request.system_instructions
        profile_sources = [
            item for item in profile_request.knowledge if item.chunk_id.startswith("profile:")
        ]
        assert profile_sources[0].source_title == "Perfil da empresa"
        assert "9h às 18h" in profile_sources[0].content
        assert no_match == []
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(Organization).where(
                    Organization.id.in_([organization_id, other_organization_id])
                )
            )
            session.commit()
