import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.application import app
from app.core.crypto import encrypt_secret
from app.database.session import SessionLocal
from app.models.core import (
    Conversation,
    ConversationMode,
    Message,
    MessageStatus,
    Organization,
    WhatsAppAccount,
    WhatsAppAccountStatus,
)
from app.tasks.whatsapp import recover_pending_messages, send_whatsapp_message

client = TestClient(app)


def test_temporary_meta_failure_preserves_and_recovers_outbound_message() -> None:
    suffix = uuid.uuid4().hex[:10]
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"Recuperação WhatsApp {suffix}",
            "organization_slug": f"whatsapp-recovery-{suffix}",
            "admin_name": "Administrador",
            "admin_email": f"whatsapp-recovery-{suffix}@example.com",
            "password": "senha-segura-123",
        },
    )
    assert registration.status_code == 201
    organization_id = uuid.UUID(registration.json()["organization"]["id"])
    headers = {"Authorization": f"Bearer {registration.json()['token']['access_token']}"}

    try:
        with SessionLocal() as session:
            account = WhatsAppAccount(
                organization_id=organization_id,
                display_name="WhatsApp de recuperação",
                phone_number=f"5511{suffix}",
                meta_phone_number_id=f"phone-{suffix}",
                meta_business_account_id=f"business-{suffix}",
                access_token_encrypted=encrypt_secret("offline-recovery-token"),
                status=WhatsAppAccountStatus.ACTIVE,
            )
            session.add(account)
            session.commit()
            session.refresh(account)
            account_id = str(account.id)

        contact = client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"phone_number": f"5522{suffix}", "name": "Cliente Recuperação"},
        )
        conversation = client.post(
            "/api/v1/conversations",
            headers=headers,
            json={
                "whatsapp_account_id": account_id,
                "contact_id": contact.json()["id"],
            },
        )
        conversation_id = conversation.json()["id"]
        with SessionLocal() as session:
            stored_conversation = session.get(Conversation, uuid.UUID(conversation_id))
            stored_conversation.mode = ConversationMode.HUMAN
            stored_conversation.last_customer_message_at = datetime.now(UTC)
            session.commit()

        with patch("app.api.conversations.enqueue_outbound_message"):
            outbound = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers={**headers, "Idempotency-Key": f"recovery-{suffix}"},
                json={"body": "Mensagem que não pode ser perdida"},
            )
        assert outbound.status_code == 201
        message_id = outbound.json()["id"]

        with patch(
            "app.tasks.whatsapp.MetaWhatsAppClient.send_message",
            side_effect=TimeoutError("Meta temporariamente indisponível"),
        ), pytest.raises(TimeoutError, match="temporariamente indisponível"):
            send_whatsapp_message.run(message_id)

        with SessionLocal() as session:
            failed = session.get(Message, uuid.UUID(message_id))
            assert failed.status == MessageStatus.FAILED
            assert failed.body == "Mensagem que não pode ser perdida"
            assert failed.delivery_attempts == 1
            assert failed.delivery_claimed_at is None
            assert "temporariamente indisponível" in failed.delivery_error

        with patch("app.api.conversations.enqueue_outbound_message") as enqueue:
            retry = client.post(
                f"/api/v1/conversations/{conversation_id}/messages/{message_id}/retry",
                headers=headers,
            )
        assert retry.status_code == 200
        assert retry.json()["status"] == "queued"
        assert retry.json()["delivery_error"] is None
        enqueue.assert_called_once_with(message_id)

        with patch(
            "app.tasks.whatsapp.MetaWhatsAppClient.send_message",
            return_value=f"wamid.recovered.{suffix}",
        ) as external_send:
            send_whatsapp_message.run(message_id)
            send_whatsapp_message.run(message_id)
        external_send.assert_called_once()

        with SessionLocal() as session:
            recovered = session.get(Message, uuid.UUID(message_id))
            assert recovered.status == MessageStatus.SENT
            assert recovered.external_message_id == f"wamid.recovered.{suffix}"
            assert recovered.delivery_attempts == 2
            assert recovered.delivery_error is None
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()


def test_broker_outage_keeps_message_queued_for_periodic_recovery() -> None:
    suffix = uuid.uuid4().hex[:10]
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"Recuperação de fila {suffix}",
            "organization_slug": f"queue-recovery-{suffix}",
            "admin_name": "Administrador",
            "admin_email": f"queue-recovery-{suffix}@example.com",
            "password": "senha-segura-123",
        },
    )
    assert registration.status_code == 201
    organization_id = uuid.UUID(registration.json()["organization"]["id"])
    headers = {"Authorization": f"Bearer {registration.json()['token']['access_token']}"}

    try:
        with SessionLocal() as session:
            account = WhatsAppAccount(
                organization_id=organization_id,
                display_name="WhatsApp da fila",
                phone_number=f"5533{suffix}",
                meta_phone_number_id=f"queue-phone-{suffix}",
                meta_business_account_id=f"queue-business-{suffix}",
                access_token_encrypted=encrypt_secret("offline-queue-token"),
                status=WhatsAppAccountStatus.ACTIVE,
            )
            session.add(account)
            session.commit()
            session.refresh(account)
            account_id = str(account.id)

        contact = client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"phone_number": f"5544{suffix}", "name": "Cliente da Fila"},
        )
        conversation = client.post(
            "/api/v1/conversations",
            headers=headers,
            json={
                "whatsapp_account_id": account_id,
                "contact_id": contact.json()["id"],
            },
        )
        conversation_id = conversation.json()["id"]
        with SessionLocal() as session:
            stored_conversation = session.get(Conversation, uuid.UUID(conversation_id))
            stored_conversation.mode = ConversationMode.HUMAN
            stored_conversation.last_customer_message_at = datetime.now(UTC)
            session.commit()

        with patch(
            "app.tasks.whatsapp.send_whatsapp_message.delay",
            side_effect=ConnectionError("Redis temporariamente indisponível"),
        ):
            outbound = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers={**headers, "Idempotency-Key": f"queue-outage-{suffix}"},
                json={"body": "Mensagem preservada durante queda da fila"},
            )
        assert outbound.status_code == 201
        message_id = outbound.json()["id"]
        assert outbound.json()["status"] == "queued"

        with SessionLocal() as session:
            queued = session.get(Message, uuid.UUID(message_id))
            assert queued.status == MessageStatus.QUEUED
            assert queued.body == "Mensagem preservada durante queda da fila"
            assert queued.delivery_attempts == 0

        with patch(
            "app.tasks.whatsapp.send_whatsapp_message.delay"
        ) as recovered_dispatch:
            recovered_count = recover_pending_messages.run()
        assert recovered_count >= 1
        recovered_dispatch.assert_any_call(message_id)

        with SessionLocal() as session:
            still_queued = session.get(Message, uuid.UUID(message_id))
            assert still_queued.status == MessageStatus.QUEUED
            assert still_queued.body == "Mensagem preservada durante queda da fila"
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()
