import hashlib
import hmac
import json
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.application import app
from app.core.settings import get_settings
from app.database.session import SessionLocal
from app.models.core import (
    Message,
    MessageStatus,
    Organization,
    WebhookEventStatus,
    WhatsAppWebhookEvent,
)
from app.tasks.whatsapp import send_whatsapp_message

client = TestClient(app)


def test_whatsapp_account_and_signed_webhook() -> None:
    suffix = uuid.uuid4().hex[:10]
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Empresa WhatsApp",
            "organization_slug": f"whatsapp-{suffix}",
            "admin_name": "Administrador",
            "admin_email": f"whatsapp-{suffix}@example.com",
            "password": "senha-segura-123",
        },
    )
    assert registration.status_code == 201
    organization_id = registration.json()["organization"]["id"]
    token = registration.json()["token"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    phone_number_id = f"phone-{suffix}"

    payload = {
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
                                    "wa_id": "5511777777777",
                                    "profile": {"name": "Cliente WhatsApp"},
                                }
                            ],
                            "messages": [
                                {
                                    "id": f"wamid.{suffix}",
                                    "from": "5511777777777",
                                    "type": "text",
                                    "text": {"body": "Olá pelo WhatsApp"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    payload_hashes = {hashlib.sha256(raw_body).hexdigest()}

    try:
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
        assert "access_token" not in account.json()

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

        with patch(
            "app.api.whatsapp_accounts.MetaWhatsAppClient.list_templates",
            return_value=[
                {
                    "name": "retomar_atendimento",
                    "language": "pt_BR",
                    "status": "APPROVED",
                    "category": "UTILITY",
                }
            ],
        ):
            templates = client.post(
                f"/api/v1/whatsapp-accounts/{account.json()['id']}/templates/sync",
                headers=headers,
            )
        assert templates.status_code == 200
        assert templates.json()[0]["status"] == "approved"

        settings = get_settings()
        verification = client.get(
            "/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": settings.meta_webhook_verify_token,
                "hub.challenge": "12345",
            },
        )
        assert verification.status_code == 200
        assert verification.json() == 12345

        signature = "sha256=" + hmac.new(
            settings.meta_app_secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        received = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
        assert received.status_code == 200
        assert received.json()["status"] == "accepted"

        duplicate = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
        assert duplicate.json()["status"] == "duplicate"

        with SessionLocal() as session:
            stored_event = session.scalar(
                select(WhatsAppWebhookEvent).where(
                    WhatsAppWebhookEvent.payload_hash
                    == hashlib.sha256(raw_body).hexdigest()
                )
            )
            stored_event.status = WebhookEventStatus.FAILED
            stored_event.error = "Falha temporária simulada"
            session.commit()
        with patch("app.api.webhooks.process_event_in_background") as reprocess:
            retried = client.post(
                "/api/v1/webhooks/whatsapp",
                content=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": signature,
                },
            )
        assert retried.json()["status"] == "retried"
        reprocess.assert_called_once()

        conversations = client.get("/api/v1/conversations", headers=headers)
        assert conversations.status_code == 200
        assert len(conversations.json()) == 1
        assert conversations.json()[0]["unread_count"] == 1

        messages = client.get(
            f"/api/v1/conversations/{conversations.json()[0]['id']}/messages",
            headers=headers,
        )
        assert messages.json()[0]["body"] == "Olá pelo WhatsApp"
        assert messages.json()[0]["direction"] == "inbound"

        conversation_id = conversations.json()[0]["id"]
        with patch("app.api.conversations.enqueue_outbound_message"):
            outbound = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers={**headers, "Idempotency-Key": f"webhook-message-{suffix}"},
                json={"body": "Olá! Como posso ajudar?"},
            )
        assert outbound.status_code == 201
        external_outbound_id = f"wamid.outbound.{suffix}"
        with patch(
            "app.tasks.whatsapp.MetaWhatsAppClient.send_message",
            return_value=external_outbound_id,
        ):
            send_whatsapp_message.run(outbound.json()["id"])

        def post_status(status_value: str) -> None:
            status_payload = {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": f"business-{suffix}",
                        "changes": [
                            {
                                "field": "messages",
                                "value": {
                                    "metadata": {"phone_number_id": phone_number_id},
                                    "statuses": [
                                        {"id": external_outbound_id, "status": status_value}
                                    ],
                                },
                            }
                        ],
                    }
                ],
            }
            status_body = json.dumps(status_payload, separators=(",", ":")).encode()
            payload_hashes.add(hashlib.sha256(status_body).hexdigest())
            status_signature = "sha256=" + hmac.new(
                settings.meta_app_secret.encode(), status_body, hashlib.sha256
            ).hexdigest()
            response = client.post(
                "/api/v1/webhooks/whatsapp",
                content=status_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": status_signature,
                },
            )
            assert response.status_code == 200

        post_status("delivered")
        post_status("sent")
        with SessionLocal() as session:
            stored_outbound = session.get(Message, uuid.UUID(outbound.json()["id"]))
            assert stored_outbound.status == MessageStatus.DELIVERED

        post_status("read")
        with SessionLocal() as session:
            stored_outbound = session.get(Message, uuid.UUID(outbound.json()["id"]))
            assert stored_outbound.status == MessageStatus.READ
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(Organization).where(Organization.id == uuid.UUID(organization_id))
            )
            session.execute(
                delete(WhatsAppWebhookEvent).where(
                    WhatsAppWebhookEvent.payload_hash.in_(payload_hashes)
                )
            )
            session.commit()
