import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

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
    WhatsAppTemplate,
    WhatsAppTemplateStatus,
)
from app.tasks.whatsapp import send_whatsapp_message

client = TestClient(app)


def register_test_organization(suffix: str) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"Empresa {suffix}",
            "organization_slug": f"empresa-{suffix}",
            "admin_name": "Administrador",
            "admin_email": f"admin-{suffix}@example.com",
            "password": "senha-segura-123",
        },
    )
    assert response.status_code == 201
    return response.json()["organization"]["id"], response.json()["token"]["access_token"]


def test_conversation_message_ticket_and_tenant_isolation() -> None:
    suffix = uuid.uuid4().hex[:10]
    organization_id, token = register_test_organization(suffix)
    other_organization_id, other_token = register_test_organization(f"other-{suffix}")
    headers = {"Authorization": f"Bearer {token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    try:
        with SessionLocal() as session:
            account = WhatsAppAccount(
                organization_id=uuid.UUID(organization_id),
                display_name="WhatsApp principal",
                phone_number="5511999999999",
                meta_phone_number_id=f"phone-{suffix}",
                meta_business_account_id=f"business-{suffix}",
                access_token_encrypted=encrypt_secret("temporary-access-token-for-tests"),
                status=WhatsAppAccountStatus.ACTIVE,
            )
            session.add(account)
            session.commit()
            session.refresh(account)
            account_id = str(account.id)

        contact = client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"phone_number": "5511888888888", "name": "Cliente Teste"},
        )
        assert contact.status_code == 201

        conversation = client.post(
            "/api/v1/conversations",
            headers=headers,
            json={
                "whatsapp_account_id": account_id,
                "contact_id": contact.json()["id"],
            },
        )
        assert conversation.status_code == 201
        conversation_id = conversation.json()["id"]

        renamed = client.patch(
            f"/api/v1/contacts/{contact.json()['id']}",
            headers=headers,
            json={"name": "Cliente Renomeado"},
        )
        assert renamed.status_code == 200
        found_contacts = client.get(
            "/api/v1/contacts", headers=headers, params={"search": "Renomeado"}
        )
        assert found_contacts.status_code == 200
        assert len(found_contacts.json()) == 1
        contact_history = client.get(
            f"/api/v1/contacts/{contact.json()['id']}/conversations",
            headers=headers,
        )
        assert contact_history.status_code == 200
        assert contact_history.json()[0]["id"] == conversation_id

        with SessionLocal() as session:
            stored_conversation = session.get(Conversation, uuid.UUID(conversation_id))
            stored_conversation.last_customer_message_at = datetime.now(UTC)
            stored_conversation.mode = ConversationMode.HUMAN
            stored_conversation.unread_count = 2
            session.commit()

        notifications = client.get("/api/v1/notifications/summary", headers=headers)
        assert notifications.status_code == 200
        assert notifications.json()["human_unread"] == 2
        assert notifications.json()["waiting_human"] == 1
        marked_read = client.post(
            f"/api/v1/conversations/{conversation_id}/mark-read", headers=headers
        )
        assert marked_read.status_code == 200
        assert marked_read.json()["unread_count"] == 0

        isolated = client.get(
            f"/api/v1/conversations/{conversation_id}", headers=other_headers
        )
        assert isolated.status_code == 404

        tag = client.post(
            "/api/v1/tags",
            headers=headers,
            json={"name": "Orçamento", "color": "#1677A8"},
        )
        assert tag.status_code == 201
        tag_id = tag.json()["id"]
        assigned_tag = client.post(
            f"/api/v1/conversations/{conversation_id}/tags/{tag_id}", headers=headers
        )
        assert assigned_tag.status_code == 201
        conversation_tags = client.get(
            f"/api/v1/conversations/{conversation_id}/tags", headers=headers
        )
        assert conversation_tags.json()[0]["name"] == "Orçamento"
        tagged_inbox = client.get(
            "/api/v1/conversations/inbox", headers=headers, params={"tag_id": tag_id}
        )
        assert tagged_inbox.status_code == 200
        assert tagged_inbox.json()[0]["id"] == conversation_id
        tenant_assignment = client.post(
            f"/api/v1/conversations/{conversation_id}/tags/{tag_id}",
            headers=other_headers,
        )
        assert tenant_assignment.status_code == 404

        sla_config = client.patch(
            "/api/v1/organization/profile",
            headers=headers,
            json={"sla_first_response_minutes": 1, "auto_assignment_enabled": True},
        )
        assert sla_config.status_code == 200
        with SessionLocal() as session:
            stored_conversation = session.get(Conversation, uuid.UUID(conversation_id))
            stored_conversation.last_customer_message_at = datetime.now(UTC) - timedelta(minutes=2)
            session.commit()

        current_user = client.get("/api/v1/auth/me", headers=headers).json()
        prioritized = client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers,
            json={"priority": "urgent"},
        )
        assert prioritized.status_code == 200
        assert prioritized.json()["priority"] == "urgent"
        assert prioritized.json()["assigned_user_id"] == current_user["id"]
        my_urgent_queue = client.get(
            "/api/v1/conversations/inbox",
            headers=headers,
            params={"priority": "urgent", "assignment": "mine"},
        )
        assert my_urgent_queue.status_code == 200
        assert my_urgent_queue.json()[0]["id"] == conversation_id
        assert my_urgent_queue.json()[0]["sla_status"] == "overdue"
        sla_dashboard = client.get("/api/v1/dashboard", headers=headers)
        assert sla_dashboard.status_code == 200
        assert sla_dashboard.json()["sla_overdue"] == 1
        unassigned_queue = client.get(
            "/api/v1/conversations/inbox",
            headers=headers,
            params={"assignment": "unassigned"},
        )
        assert unassigned_queue.status_code == 200
        assert unassigned_queue.json() == []

        unassigned = client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers,
            json={"assigned_user_id": None},
        )
        assert unassigned.status_code == 200
        assert unassigned.json()["assigned_user_id"] is None
        unassigned_queue = client.get(
            "/api/v1/conversations/inbox",
            headers=headers,
            params={"assignment": "unassigned"},
        )
        assert [item["id"] for item in unassigned_queue.json()] == [conversation_id]

        reassigned = client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers,
            json={"assigned_user_id": current_user["id"]},
        )
        assert reassigned.status_code == 200
        assert reassigned.json()["assigned_user_id"] == current_user["id"]

        note = client.post(
            f"/api/v1/conversations/{conversation_id}/notes",
            headers=headers,
            json={"content": "Cliente pediu retorno na sexta-feira."},
        )
        assert note.status_code == 201
        assert note.json()["event_type"] == "note.created"
        events = client.get(
            f"/api/v1/conversations/{conversation_id}/events", headers=headers
        )
        assert events.status_code == 200
        event_types = {item["event_type"] for item in events.json()}
        assert "note.created" in event_types
        assert "priority.changed" in event_types
        isolated_events = client.get(
            f"/api/v1/conversations/{conversation_id}/events", headers=other_headers
        )
        assert isolated_events.status_code == 404

        with patch("app.api.conversations.send_whatsapp_message.delay") as enqueue:
            message_headers = {**headers, "Idempotency-Key": f"message-main-{suffix}"}
            message = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers=message_headers,
                json={"body": "Olá, cliente!"},
            )
            repeated_message = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers=message_headers,
                json={"body": "Olá, cliente!"},
            )
            conflicting_message = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers=message_headers,
                json={"body": "Conteúdo diferente"},
            )
        assert message.status_code == 201
        assert message.json()["direction"] == "outbound"
        assert message.json()["status"] == "queued"
        assert message.json()["sender_user_id"] == current_user["id"]
        assert repeated_message.status_code == 201
        assert repeated_message.json()["id"] == message.json()["id"]
        assert conflicting_message.status_code == 409
        enqueue.assert_called_once_with(message.json()["id"])

        team_dashboard = client.get("/api/v1/dashboard", headers=headers)
        assert team_dashboard.status_code == 200
        admin_performance = next(
            item
            for item in team_dashboard.json()["team_performance"]
            if item["user_id"] == current_user["id"]
        )
        assert admin_performance["open_assigned"] == 1
        assert admin_performance["messages_sent_30d"] == 1

        contacts_export = client.get("/api/v1/exports/contacts.csv", headers=headers)
        assert contacts_export.status_code == 200
        assert contacts_export.content.startswith(b"\xef\xbb\xbf")
        assert "Cliente Renomeado" in contacts_export.content.decode("utf-8-sig")
        conversations_export = client.get(
            "/api/v1/exports/conversations.csv", headers=headers
        )
        assert conversations_export.status_code == 200
        assert "Urgente" in conversations_export.content.decode("utf-8-sig")
        team_export = client.get(
            "/api/v1/exports/team-performance.csv", headers=headers
        )
        assert team_export.status_code == 200
        assert "Administrador" in team_export.content.decode("utf-8-sig")

        contact_blocked = client.patch(
            f"/api/v1/contacts/{contact.json()['id']}",
            headers=headers,
            json={"is_blocked": True},
        )
        assert contact_blocked.status_code == 200
        blocked_contact_message = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers={**headers, "Idempotency-Key": f"message-blocked-{suffix}"},
            json={"body": "Esta mensagem não pode ser enviada"},
        )
        assert blocked_contact_message.status_code == 409
        unblocked = client.patch(
            f"/api/v1/contacts/{contact.json()['id']}",
            headers=headers,
            json={"is_blocked": False},
        )
        assert unblocked.status_code == 200

        with patch(
            "app.tasks.whatsapp.MetaWhatsAppClient.send_message",
            return_value=f"wamid.outbound-{suffix}",
        ):
            send_whatsapp_message.run(message.json()["id"])

        sent_messages = client.get(
            f"/api/v1/conversations/{conversation_id}/messages", headers=headers
        )
        assert sent_messages.json()[0]["status"] == "sent"
        assert sent_messages.json()[0]["external_message_id"] == f"wamid.outbound-{suffix}"
        assert sent_messages.json()[0]["delivery_attempts"] == 1
        assert sent_messages.json()[0]["delivery_error"] is None

        with SessionLocal() as session:
            failed_message = session.get(Message, uuid.UUID(message.json()["id"]))
            failed_message.status = MessageStatus.FAILED
            failed_message.delivery_attempts = 5
            failed_message.delivery_error = "Falha temporária simulada"
            session.commit()

        with patch("app.api.conversations.send_whatsapp_message.delay") as retry_enqueue:
            retried = client.post(
                f"/api/v1/conversations/{conversation_id}/messages/{message.json()['id']}/retry",
                headers=headers,
            )
        assert retried.status_code == 200
        assert retried.json()["status"] == "queued"
        assert retried.json()["delivery_error"] is None
        retry_enqueue.assert_called_once_with(message.json()["id"])

        inbox = client.get("/api/v1/conversations/inbox", headers=headers)
        assert inbox.status_code == 200
        assert inbox.json()[0]["contact_name"] == "Cliente Renomeado"
        assert inbox.json()[0]["last_message_body"] == "Olá, cliente!"
        assert inbox.json()[0]["sla_status"] is None

        with patch("app.api.conversations.send_whatsapp_message.delay"):
            media = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers={**headers, "Idempotency-Key": f"message-media-{suffix}"},
                json={
                    "message_type": "document",
                    "body": "Documento solicitado",
                    "media_url": "https://example.com/documento.pdf",
                    "media_filename": "documento.pdf",
                },
            )
            interactive = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers={**headers, "Idempotency-Key": f"message-interactive-{suffix}"},
                json={
                    "message_type": "interactive",
                    "interactive": {
                        "kind": "buttons",
                        "body": "Escolha uma opção",
                        "buttons": [
                            {"id": "documents", "title": "Documentos"},
                            {"id": "attendant", "title": "Atendente"},
                        ],
                    },
                },
            )
        assert media.status_code == 201
        assert media.json()["media_filename"] == "documento.pdf"
        assert interactive.status_code == 201

        with SessionLocal() as session:
            stored_conversation = session.get(Conversation, uuid.UUID(conversation_id))
            stored_conversation.last_customer_message_at = datetime.now(UTC) - timedelta(hours=25)
            template = WhatsAppTemplate(
                organization_id=uuid.UUID(organization_id),
                whatsapp_account_id=uuid.UUID(account_id),
                name="retomar_atendimento",
                language="pt_BR",
                category="UTILITY",
                status=WhatsAppTemplateStatus.APPROVED,
            )
            session.add(template)
            session.commit()
            session.refresh(template)
            template_id = str(template.id)

        blocked = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers={**headers, "Idempotency-Key": f"message-window-{suffix}"},
            json={"body": "Mensagem comum fora da janela"},
        )
        assert blocked.status_code == 409

        with patch("app.api.conversations.send_whatsapp_message.delay"):
            templated = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers={**headers, "Idempotency-Key": f"message-template-{suffix}"},
                json={
                    "message_type": "template",
                    "template_id": template_id,
                    "template_parameters": ["Cliente"],
                },
            )
        assert templated.status_code == 201
        assert templated.json()["template_id"] == template_id

        ticket = client.post(
            f"/api/v1/conversations/{conversation_id}/tickets",
            headers=headers,
            json={"subject": "Atendimento solicitado"},
        )
        assert ticket.status_code == 201
        assert ticket.json()["protocol"].startswith("NR-")

        updated_conversation = client.get(
            f"/api/v1/conversations/{conversation_id}", headers=headers
        )
        assert updated_conversation.json()["mode"] == "human"

        closed = client.post(
            f"/api/v1/tickets/{ticket.json()['id']}/close", headers=headers
        )
        assert closed.status_code == 200
        assert closed.json()["status"] == "closed"

        closed_conversation = client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers,
            json={"status": "closed"},
        )
        assert closed_conversation.status_code == 200
        assert closed_conversation.json()["status"] == "closed"

        open_inbox = client.get("/api/v1/conversations/inbox", headers=headers)
        assert open_inbox.status_code == 200
        assert all(item["id"] != conversation_id for item in open_inbox.json())
        closed_inbox = client.get(
            "/api/v1/conversations/inbox",
            headers=headers,
            params={"conversation_status": "closed"},
        )
        assert closed_inbox.status_code == 200
        assert [item["id"] for item in closed_inbox.json()] == [conversation_id]

        privacy_export = client.get(
            f"/api/v1/privacy/contacts/{contact.json()['id']}/export",
            headers=headers,
        )
        assert privacy_export.status_code == 200
        assert privacy_export.json()["contact"]["phone_number"] == "5511888888888"
        invalid_anonymization = client.post(
            f"/api/v1/privacy/contacts/{contact.json()['id']}/anonymize",
            headers=headers,
            json={"confirmation": "cancelar"},
        )
        assert invalid_anonymization.status_code == 422
        anonymized = client.post(
            f"/api/v1/privacy/contacts/{contact.json()['id']}/anonymize",
            headers=headers,
            json={"confirmation": "ANONIMIZAR"},
        )
        assert anonymized.status_code == 200
        anonymized_contact = client.get(
            f"/api/v1/contacts/{contact.json()['id']}", headers=headers
        )
        assert anonymized_contact.json()["anonymized_at"] is not None
        assert anonymized_contact.json()["phone_number"].startswith("anon-")
        anonymized_messages = client.get(
            f"/api/v1/conversations/{conversation_id}/messages", headers=headers
        )
        assert all(item["body"] is None for item in anonymized_messages.json())

        retention_config = client.patch(
            "/api/v1/organization/profile",
            headers=headers,
            json={"data_retention_days": 30},
        )
        assert retention_config.status_code == 200
        with SessionLocal() as session:
            stored_conversation = session.get(Conversation, uuid.UUID(conversation_id))
            stored_conversation.closed_at = datetime.now(UTC) - timedelta(days=31)
            session.commit()
        retention_preview = client.get(
            "/api/v1/privacy/retention/preview", headers=headers
        )
        assert retention_preview.status_code == 200
        assert retention_preview.json()["conversations_eligible"] == 1
        retention_run = client.post(
            "/api/v1/privacy/retention/run",
            headers=headers,
            json={"confirmation": "LIMPAR"},
        )
        assert retention_run.status_code == 200
        assert retention_run.json()["conversations_sanitized"] == 1
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(Organization).where(
                    Organization.id.in_(
                        [uuid.UUID(organization_id), uuid.UUID(other_organization_id)]
                    )
                )
            )
            session.commit()
