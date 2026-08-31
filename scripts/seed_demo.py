"""Cria ou remove uma empresa demonstrativa isolada da Neria."""

import argparse
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.core import (
    AIConfiguration,
    Automation,
    AutomationStatus,
    Contact,
    Conversation,
    ConversationMode,
    ConversationPriority,
    ConversationStatus,
    ConversationTag,
    KnowledgeSourceType,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    Organization,
    OrganizationProfile,
    Subscription,
    Tag,
    User,
    UserRole,
    WhatsAppAccount,
    WhatsAppAccountStatus,
)
from app.services.knowledge_service import create_processed_source

DEMO_SLUG = "neria-demonstracao"
DEMO_EMAIL = "demo@neria.local"


def remove_demo() -> None:
    with SessionLocal() as session:
        result = session.execute(delete(Organization).where(Organization.slug == DEMO_SLUG))
        session.commit()
    print("Demonstração removida." if result.rowcount else "Nenhuma demonstração encontrada.")


def create_demo(password: str) -> None:
    if len(password) < 8:
        raise SystemExit("NERIA_DEMO_PASSWORD deve ter pelo menos oito caracteres.")
    now = datetime.now(UTC)
    with SessionLocal() as session:
        if session.scalar(select(Organization.id).where(Organization.slug == DEMO_SLUG)):
            raise SystemExit("A demonstração já existe. Use --remove antes de recriá-la.")

        organization = Organization(name="Neria Demonstração", slug=DEMO_SLUG)
        session.add(organization)
        session.flush()
        admin = User(
            organization_id=organization.id,
            name="Marina Costa",
            email=DEMO_EMAIL,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
        )
        account = WhatsAppAccount(
            organization_id=organization.id,
            display_name="WhatsApp demonstrativo",
            phone_number="5511999990000",
            status=WhatsAppAccountStatus.DISCONNECTED,
        )
        session.add_all(
            [
                admin,
                account,
                OrganizationProfile(
                    organization_id=organization.id,
                    company_name="Neria Demonstração",
                    description="Empresa fictícia para apresentação do atendimento comercial da Neria.",
                    contact_email="contato@demonstracao.local",
                    contact_phone="(11) 99999-0000",
                    address="São Paulo - SP",
                    opening_hours="Segunda a sexta, das 8h às 18h",
                    welcome_message="Olá! Como a Neria pode ajudar você hoje?",
                    auto_assignment_enabled=True,
                ),
                Subscription(
                    organization_id=organization.id,
                    plan_code="starter",
                    trial_ends_at=now + timedelta(days=30),
                ),
                AIConfiguration(
                    organization_id=organization.id,
                    is_enabled=False,
                    tone="profissional e acolhedor",
                    instructions="Responda apenas com informações confirmadas na base.",
                ),
            ]
        )
        session.flush()

        create_processed_source(
            session,
            organization_id=organization.id,
            title="Informações de atendimento",
            source_type=KnowledgeSourceType.MANUAL,
            text=(
                "O atendimento funciona de segunda a sexta, das 8h às 18h.\n"
                "Solicitações de orçamento devem incluir nome, serviço desejado e prazo.\n"
                "Quando uma informação não estiver disponível, o atendimento deve ser transferido para uma pessoa."
            ),
        )
        session.add(
            Automation(
                organization_id=organization.id,
                name="Menu principal",
                status=AutomationStatus.ACTIVE,
                trigger_keywords=["olá", "menu", "início"],
                is_fallback=True,
                definition={
                    "start_node_id": "menu",
                    "nodes": {
                        "menu": {
                            "type": "menu",
                            "text": "Olá! Escolha uma opção:",
                            "options": [
                                {"id": "orcamento", "title": "Orçamento", "next_node_id": "orcamento"},
                                {"id": "atendente", "title": "Atendente", "next_node_id": "atendente"},
                            ],
                        },
                        "orcamento": {"type": "message", "text": "Conte qual serviço você procura.", "next_node_id": "fim"},
                        "atendente": {"type": "handoff", "text": "Vou chamar um atendente."},
                        "fim": {"type": "end"},
                    },
                },
            )
        )

        tag_budget = Tag(organization_id=organization.id, name="Orçamento", color="#1677A8")
        tag_priority = Tag(organization_id=organization.id, name="Retorno", color="#D9822B")
        session.add_all([tag_budget, tag_priority])
        session.flush()

        samples = [
            ("Camila Oliveira", "5511988880001", ConversationMode.HUMAN, ConversationPriority.HIGH, 2, "Gostaria de receber um orçamento."),
            ("Rafael Santos", "5511988880002", ConversationMode.BOT, ConversationPriority.NORMAL, 1, "Qual é o horário de atendimento?"),
            ("Fernanda Lima", "5511988880003", ConversationMode.HUMAN, ConversationPriority.NORMAL, 0, "Obrigada pelo atendimento!"),
        ]
        for index, (name, phone, mode, priority, unread, body) in enumerate(samples):
            contact = Contact(organization_id=organization.id, phone_number=phone, name=name)
            session.add(contact)
            session.flush()
            occurred_at = now - timedelta(minutes=8 + index * 23)
            conversation = Conversation(
                organization_id=organization.id,
                whatsapp_account_id=account.id,
                contact_id=contact.id,
                assigned_user_id=admin.id if mode == ConversationMode.HUMAN else None,
                status=ConversationStatus.OPEN,
                mode=mode,
                priority=priority,
                unread_count=unread,
                last_message_at=occurred_at,
                last_customer_message_at=occurred_at,
            )
            session.add(conversation)
            session.flush()
            session.add(
                Message(
                    organization_id=organization.id,
                    conversation_id=conversation.id,
                    external_message_id=f"demo-inbound-{index}",
                    direction=MessageDirection.INBOUND,
                    message_type=MessageType.TEXT,
                    status=MessageStatus.RECEIVED,
                    body=body,
                    created_at=occurred_at,
                )
            )
            if index == 0:
                session.add(ConversationTag(conversation_id=conversation.id, tag_id=tag_budget.id))
            if index == 2:
                session.add(ConversationTag(conversation_id=conversation.id, tag_id=tag_priority.id))

        session.commit()
    print(f"Demonstração criada. E-mail: {DEMO_EMAIL}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true", help="Remove somente a empresa demonstrativa.")
    args = parser.parse_args()
    if args.remove:
        remove_demo()
        return
    password = os.getenv("NERIA_DEMO_PASSWORD")
    if not password:
        raise SystemExit("Defina NERIA_DEMO_PASSWORD antes de criar a demonstração.")
    create_demo(password)


if __name__ == "__main__":
    main()
