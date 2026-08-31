import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.application import app
from app.database.session import SessionLocal
from app.models.core import (
    AutomationSession,
    Contact,
    Conversation,
    Message,
    Organization,
    WhatsAppAccount,
)
from app.services.automation_engine import process_automation

client = TestClient(app)


def test_configurable_menu_flow() -> None:
    suffix = uuid.uuid4().hex[:10]
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"Empresa {suffix}",
            "organization_slug": f"automation-{suffix}",
            "admin_name": "Administrador",
            "admin_email": f"automation-{suffix}@example.com",
            "password": "senha-segura-123",
        },
    )
    assert registration.status_code == 201
    organization_id = uuid.UUID(registration.json()["organization"]["id"])
    headers = {
        "Authorization": f"Bearer {registration.json()['token']['access_token']}"
    }

    try:
        created = client.post(
            "/api/v1/automations",
            headers=headers,
            json={
                "name": "Menu principal",
                "is_fallback": True,
                "trigger_keywords": ["menu", "olá"],
                "definition": {
                    "start_node_id": "main_menu",
                    "nodes": {
                        "main_menu": {
                            "type": "menu",
                            "text": "Como podemos ajudar?",
                            "options": [
                                {
                                    "id": "sales",
                                    "title": "Comprar",
                                    "next_node_id": "sales_reply",
                                },
                                {
                                    "id": "agent",
                                    "title": "Atendente",
                                    "next_node_id": "handoff",
                                },
                            ],
                        },
                        "sales_reply": {
                            "type": "message",
                            "text": "Vou apresentar nossos produtos.",
                            "next_node_id": "finish",
                        },
                        "handoff": {
                            "type": "handoff",
                            "text": "Vou chamar um atendente.",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        assert created.status_code == 201
        automation_id = created.json()["id"]
        assert created.json()["status"] == "draft"

        activated = client.post(
            f"/api/v1/automations/{automation_id}/activate", headers=headers
        )
        assert activated.status_code == 200
        assert activated.json()["status"] == "active"

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

            first_messages = process_automation(session, conversation, "Olá").message_ids
            assert len(first_messages) == 1
            menu = session.get(Message, first_messages[0])
            assert menu.raw_payload["interactive"]["buttons"][0]["id"] == "sales"

            reply_messages = process_automation(session, conversation, "sales").message_ids
            assert len(reply_messages) == 1
            reply = session.get(Message, reply_messages[0])
            assert reply.body == "Vou apresentar nossos produtos."
            automation_session = session.scalar(
                select(AutomationSession).where(
                    AutomationSession.conversation_id == conversation.id
                )
            )
            assert automation_session.is_active is False
            session.commit()
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()
