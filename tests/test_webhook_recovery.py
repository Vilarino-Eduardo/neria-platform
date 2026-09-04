import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import delete

from app.database.session import SessionLocal
from app.models.core import WebhookEventStatus, WhatsAppWebhookEvent
from app.tasks.webhooks import recover_pending_webhook_events


def test_pending_and_interrupted_webhooks_are_redispatched() -> None:
    pending_id = uuid.uuid4()
    interrupted_id = uuid.uuid4()
    try:
        with SessionLocal() as session:
            session.add_all(
                [
                    WhatsAppWebhookEvent(
                        id=pending_id,
                        payload_hash=uuid.uuid4().hex,
                        payload={"entry": []},
                        status=WebhookEventStatus.PENDING,
                    ),
                    WhatsAppWebhookEvent(
                        id=interrupted_id,
                        payload_hash=uuid.uuid4().hex,
                        payload={"entry": []},
                        status=WebhookEventStatus.PROCESSING,
                        processing_claimed_at=datetime.now(UTC) - timedelta(minutes=10),
                    ),
                ]
            )
            session.commit()

        with patch("app.tasks.webhooks.process_webhook_event_task.delay") as dispatch:
            recovered = recover_pending_webhook_events.run()

        assert recovered >= 2
        dispatch.assert_any_call(str(pending_id))
        dispatch.assert_any_call(str(interrupted_id))
        with SessionLocal() as session:
            interrupted = session.get(WhatsAppWebhookEvent, interrupted_id)
            assert interrupted.status == WebhookEventStatus.PENDING
            assert interrupted.processing_claimed_at is None
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(WhatsAppWebhookEvent).where(
                    WhatsAppWebhookEvent.id.in_([pending_id, interrupted_id])
                )
            )
            session.commit()
