"""Valida uma resposta paga pelo pipeline completo da IA, sem enviar ao WhatsApp."""

import argparse
import json
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.application import app
from app.core.settings import get_settings
from app.database.session import SessionLocal
from app.models.core import (
    AIRun,
    AIRunStatus,
    AIUsageDaily,
    Contact,
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    Organization,
    WhatsAppAccount,
)
from app.tasks.ai import generate_ai_reply


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-paid-api",
        action="store_true",
        help="Confirma uma única chamada paga à OpenAI.",
    )
    return parser.parse_args()


def main() -> int:
    if not parse_args().confirm_paid_api:
        print(
            json.dumps(
                {
                    "error": (
                        "Execução bloqueada para evitar custos. Use --confirm-paid-api "
                        "somente após autorização explícita."
                    ),
                    "maximum_paid_calls": 1,
                },
                ensure_ascii=False,
            )
        )
        return 2

    settings = get_settings()
    if not settings.openai_api_key:
        print(json.dumps({"error": "OPENAI_API_KEY não configurada."}, ensure_ascii=False))
        return 2

    client = TestClient(app)
    suffix = str(uuid.uuid4().int)[-10:]
    organization_id: uuid.UUID | None = None
    try:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": "Avaliação temporária da IA",
                "organization_slug": f"ai-pipeline-{suffix}",
                "admin_name": "Avaliador",
                "admin_email": f"ai-pipeline-{suffix}@example.invalid",
                "password": "senha-segura-123",
            },
        )
        registration.raise_for_status()
        organization_id = uuid.UUID(registration.json()["organization"]["id"])
        headers = {
            "Authorization": f"Bearer {registration.json()['token']['access_token']}"
        }

        configuration = client.patch(
            "/api/v1/ai/configuration",
            headers=headers,
            json={"is_enabled": True, "minimum_confidence": 70},
        )
        configuration.raise_for_status()
        knowledge = client.post(
            "/api/v1/knowledge/sources/manual",
            headers=headers,
            json={
                "title": "Política temporária de trocas",
                "content": "Trocas são aceitas em até sete dias após o recebimento.",
            },
        )
        knowledge.raise_for_status()

        with SessionLocal() as session:
            account = WhatsAppAccount(
                organization_id=organization_id,
                display_name="Canal temporário",
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
            input_message = Message(
                organization_id=organization_id,
                conversation_id=conversation.id,
                direction=MessageDirection.INBOUND,
                message_type=MessageType.TEXT,
                status=MessageStatus.RECEIVED,
                body="Em quanto tempo posso trocar um produto?",
            )
            session.add(input_message)
            session.commit()
            input_message_id = input_message.id

        with patch("app.tasks.ai.enqueue_outbound_message") as enqueue:
            generate_ai_reply.run(str(input_message_id))

        with SessionLocal() as session:
            run = session.scalar(
                select(AIRun).where(AIRun.input_message_id == input_message_id)
            )
            if run is None:
                raise RuntimeError("O pipeline não registrou a execução da IA.")
            output = session.get(Message, run.output_message_id)
            usage = session.scalar(
                select(AIUsageDaily).where(
                    AIUsageDaily.organization_id == organization_id
                )
            )
            passed = bool(
                run.status == AIRunStatus.COMPLETED
                and output
                and output.status == MessageStatus.QUEUED
                and "sete" in (output.body or "").casefold()
                and usage
                and usage.request_count == 1
                and enqueue.call_count == 1
            )
            result = {
                "passed": passed,
                "model": run.model,
                "status": run.status.value,
                "knowledge_chunks_retrieved": len(run.retrieved_chunk_ids),
                "confidence": run.confidence,
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "latency_ms": run.latency_ms,
                "outbound_message_queued": bool(output),
                "external_whatsapp_send_blocked": True,
                "daily_usage_recorded": bool(usage and usage.request_count == 1),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if passed else 1
    finally:
        if organization_id is not None:
            with SessionLocal() as session:
                session.execute(
                    delete(Organization).where(Organization.id == organization_id)
                )
                session.commit()


if __name__ == "__main__":
    raise SystemExit(main())
