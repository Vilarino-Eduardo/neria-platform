import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.application import app
from app.database.session import SessionLocal
from app.integrations.whatsapp.processor import process_incoming_message
from app.models.core import (
    AIConfiguration,
    AIRun,
    AIRunStatus,
    AIUsageDaily,
    Contact,
    Conversation,
    ConversationMode,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    Organization,
    WhatsAppAccount,
)
from app.services.ai.context import PROMPT_VERSION
from app.tasks.ai import recover_pending_ai_runs

client = TestClient(app)


def test_recovery_dispatches_pending_and_safely_fails_interrupted_run() -> None:
    suffix = uuid.uuid4().hex[:10]
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"Recuperação IA {suffix}",
            "organization_slug": f"ai-recovery-{suffix}",
            "admin_name": "Administrador",
            "admin_email": f"ai-recovery-{suffix}@example.com",
            "password": "senha-segura-123",
        },
    )
    organization_id = uuid.UUID(registration.json()["organization"]["id"])
    try:
        with SessionLocal() as session:
            session.add(
                AIConfiguration(organization_id=organization_id, is_enabled=True)
            )
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
            interrupted_input = Message(
                organization_id=organization_id,
                conversation_id=conversation.id,
                direction=MessageDirection.INBOUND,
                message_type=MessageType.TEXT,
                status=MessageStatus.RECEIVED,
                body="Pergunta interrompida",
            )
            session.add(interrupted_input)
            session.flush()
            interrupted_run = AIRun(
                organization_id=organization_id,
                conversation_id=conversation.id,
                input_message_id=interrupted_input.id,
                status=AIRunStatus.PROCESSING,
                provider="openai",
                model="offline-test",
                prompt_version=PROMPT_VERSION,
                processing_started_at=datetime.now(UTC) - timedelta(minutes=10),
                token_reservation=500,
            )
            session.add(interrupted_run)
            session.add(
                AIUsageDaily(
                    organization_id=organization_id,
                    usage_date=datetime.now(UTC).date(),
                    request_count=1,
                    reserved_tokens=500,
                )
            )
            with patch(
                "app.integrations.whatsapp.processor.get_settings",
                return_value=SimpleNamespace(
                    openai_api_key="offline-test-key",
                    openai_model="offline-test",
                ),
            ):
                _, pending_input_id = process_incoming_message(
                    session,
                    account,
                    {
                        "id": f"wamid.recovery.{suffix}",
                        "from": contact.phone_number,
                        "type": "text",
                        "text": {"body": "Pergunta ainda pendente"},
                    },
                    {},
                )
            session.flush()
            pending_run = session.scalar(
                select(AIRun).where(AIRun.input_message_id == pending_input_id)
            )
            assert pending_run is not None
            assert pending_run.status == AIRunStatus.PENDING
            session.commit()
            interrupted_run_id = interrupted_run.id

        with (
            patch("app.tasks.ai.generate_ai_reply.delay") as dispatch_ai,
            patch("app.tasks.ai.enqueue_outbound_message") as dispatch_fallback,
        ):
            result = recover_pending_ai_runs.run()

        assert result == {"dispatched": 1, "recovered": 1}
        dispatch_ai.assert_called_once_with(str(pending_input_id))
        dispatch_fallback.assert_called_once()
        with SessionLocal() as session:
            recovered = session.get(AIRun, interrupted_run_id)
            usage = session.get(
                AIUsageDaily, (organization_id, datetime.now(UTC).date())
            )
            fallback = session.get(Message, recovered.output_message_id)
            conversation = session.get(Conversation, recovered.conversation_id)
            assert recovered.status == AIRunStatus.FAILED
            assert recovered.error == "worker_interrupted"
            assert recovered.processing_started_at is None
            assert recovered.token_reservation == 0
            assert usage.reserved_tokens == 0
            assert fallback.status == MessageStatus.QUEUED
            assert fallback.raw_payload["reason"] == "worker_interrupted"
            assert conversation.mode == ConversationMode.HUMAN
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()
