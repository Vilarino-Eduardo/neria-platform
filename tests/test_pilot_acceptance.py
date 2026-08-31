import hashlib
import hmac
import json
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.application import app
from app.core.settings import get_settings
from app.database.session import SessionLocal
from app.models.core import Organization, WhatsAppWebhookEvent

client = TestClient(app)


def signed_webhook(payload: dict) -> tuple[bytes, dict[str, str], str]:
    body = json.dumps(payload, separators=(",", ":")).encode()
    settings = get_settings()
    signature = "sha256=" + hmac.new(
        settings.meta_app_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return body, {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": signature,
    }, hashlib.sha256(body).hexdigest()


def test_complete_pilot_acceptance_journey() -> None:
    suffix = uuid.uuid4().hex[:10]
    organization_id: uuid.UUID | None = None
    webhook_hashes: list[str] = []

    try:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": "Loja Piloto",
                "organization_slug": f"pilot-{suffix}",
                "admin_name": "Gestora Piloto",
                "admin_email": f"pilot-{suffix}@example.com",
                "password": "senha-segura-123",
            },
        )
        assert registration.status_code == 201
        organization_id = uuid.UUID(registration.json()["organization"]["id"])
        headers = {
            "Authorization": f"Bearer {registration.json()['token']['access_token']}"
        }

        profile = client.patch(
            "/api/v1/organization/profile",
            headers=headers,
            json={
                "company_name": "Loja Piloto",
                "description": "Comércio usado na homologação da jornada do piloto.",
                "contact_email": f"pilot-{suffix}@example.com",
                "opening_hours": "Segunda a sexta, das 9h às 18h.",
                "welcome_message": "Olá! Como podemos ajudar?",
                "auto_assignment_enabled": True,
            },
        )
        assert profile.status_code == 200

        knowledge = client.post(
            "/api/v1/knowledge/sources/manual",
            headers=headers,
            json={
                "title": "Trocas e horários",
                "content": (
                    "Atendemos de segunda a sexta, das 9h às 18h. "
                    "Trocas são aceitas em até sete dias após o recebimento."
                ),
            },
        )
        assert knowledge.status_code == 201
        assert knowledge.json()["status"] == "ready"

        automation = client.post(
            "/api/v1/automations",
            headers=headers,
            json={
                "name": "Recepção do piloto",
                "is_fallback": True,
                "trigger_keywords": ["olá", "menu"],
                "definition": {
                    "start_node_id": "menu",
                    "nodes": {
                        "menu": {
                            "type": "menu",
                            "text": "Como podemos ajudar?",
                            "options": [
                                {
                                    "id": "agent",
                                    "title": "Falar com atendente",
                                    "next_node_id": "handoff",
                                }
                            ],
                        },
                        "handoff": {
                            "type": "handoff",
                            "text": "Certo, vou chamar um atendente.",
                        },
                    },
                },
            },
        )
        assert automation.status_code == 201
        activated = client.post(
            f"/api/v1/automations/{automation.json()['id']}/activate", headers=headers
        )
        assert activated.status_code == 200

        phone_number_id = f"phone-{suffix}"
        account = client.post(
            "/api/v1/whatsapp-accounts",
            headers=headers,
            json={
                "display_name": "WhatsApp principal",
                "phone_number": "5511999999999",
                "meta_phone_number_id": phone_number_id,
                "meta_business_account_id": f"business-{suffix}",
                "access_token": "temporary-access-token-for-tests",
            },
        )
        assert account.status_code == 201
        with patch(
            "app.api.whatsapp_accounts.MetaWhatsAppClient.verify_phone_number",
            return_value={"display_phone_number": "5511999999999"},
        ):
            verified = client.post(
                f"/api/v1/whatsapp-accounts/{account.json()['id']}/verify",
                headers=headers,
            )
        assert verified.status_code == 200
        assert verified.json()["status"] == "active"

        onboarding = client.get("/api/v1/onboarding", headers=headers)
        assert onboarding.status_code == 200
        assert onboarding.json()["completed_required"] == onboarding.json()["total_required"]

        def incoming_payload(message_id: str, body: str) -> dict:
            return {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": f"business-{suffix}",
                        "changes": [
                            {
                                "field": "messages",
                                "value": {
                                    "metadata": {"phone_number_id": phone_number_id},
                                    "contacts": [
                                        {
                                            "wa_id": "5511888887777",
                                            "profile": {"name": "Cliente Piloto"},
                                        }
                                    ],
                                    "messages": [
                                        {
                                            "id": message_id,
                                            "from": "5511888887777",
                                            "type": "text",
                                            "text": {"body": body},
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                ],
            }

        first_body, first_headers, first_hash = signed_webhook(
            incoming_payload(f"wamid.greeting.{suffix}", "Olá")
        )
        webhook_hashes.append(first_hash)
        with patch("app.integrations.whatsapp.processor.send_whatsapp_message.delay"):
            received = client.post(
                "/api/v1/webhooks/whatsapp",
                content=first_body,
                headers=first_headers,
            )
        assert received.status_code == 200
        assert received.json()["status"] == "accepted"

        conversations = client.get("/api/v1/conversations/inbox", headers=headers)
        assert conversations.status_code == 200
        assert len(conversations.json()) == 1
        conversation_id = conversations.json()[0]["id"]
        messages = client.get(
            f"/api/v1/conversations/{conversation_id}/messages", headers=headers
        )
        assert [item["body"] for item in messages.json()] == [
            "Olá",
            "Como podemos ajudar?",
        ]

        handoff_body, handoff_headers, handoff_hash = signed_webhook(
            incoming_payload(f"wamid.handoff.{suffix}", "agent")
        )
        webhook_hashes.append(handoff_hash)
        with patch("app.integrations.whatsapp.processor.send_whatsapp_message.delay"):
            handoff = client.post(
                "/api/v1/webhooks/whatsapp",
                content=handoff_body,
                headers=handoff_headers,
            )
        assert handoff.status_code == 200
        conversation = client.get(
            f"/api/v1/conversations/{conversation_id}", headers=headers
        )
        assert conversation.json()["mode"] == "human"
        assert conversation.json()["assigned_user_id"] is not None

        ticket = client.post(
            f"/api/v1/conversations/{conversation_id}/tickets",
            headers=headers,
            json={"subject": "Atendimento do piloto"},
        )
        assert ticket.status_code == 201
        with patch("app.api.conversations.send_whatsapp_message.delay") as enqueue:
            human_reply = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers=headers,
                json={"body": "Olá, sou a Marina. Vou cuidar do seu atendimento."},
            )
        assert human_reply.status_code == 201
        enqueue.assert_called_once_with(human_reply.json()["id"])

        closed = client.post(
            f"/api/v1/tickets/{ticket.json()['id']}/close", headers=headers
        )
        assert closed.status_code == 200
        assert closed.json()["status"] == "closed"
    finally:
        with SessionLocal() as session:
            if organization_id is not None:
                session.execute(
                    delete(Organization).where(Organization.id == organization_id)
                )
            if webhook_hashes:
                session.execute(
                    delete(WhatsAppWebhookEvent).where(
                        WhatsAppWebhookEvent.payload_hash.in_(webhook_hashes)
                    )
                )
            session.commit()
