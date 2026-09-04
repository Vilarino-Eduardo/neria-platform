import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update

from app.database.session import SessionLocal
from app.integrations.whatsapp.processor import process_webhook_event
from app.models.core import WebhookEventStatus, WhatsAppWebhookEvent
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
MAX_PROCESSING_ATTEMPTS = 5


@celery_app.task(name="webhooks.process_event")
def process_webhook_event_task(event_id: str) -> None:
    with SessionLocal() as session:
        event = session.scalar(
            select(WhatsAppWebhookEvent)
            .where(
                WhatsAppWebhookEvent.id == uuid.UUID(event_id),
                WhatsAppWebhookEvent.status.in_(
                    {WebhookEventStatus.PENDING, WebhookEventStatus.FAILED}
                ),
                WhatsAppWebhookEvent.processing_attempts < MAX_PROCESSING_ATTEMPTS,
            )
            .with_for_update(skip_locked=True)
        )
        if event is None or event.payload is None:
            return
        event.status = WebhookEventStatus.PROCESSING
        event.processing_attempts += 1
        event.processing_claimed_at = datetime.now(UTC)
        session.commit()
        process_webhook_event(session, event)


def enqueue_webhook_event(event_id: str) -> bool:
    try:
        process_webhook_event_task.delay(event_id)
        return True
    except Exception:
        logger.exception("webhook_event_enqueue_failed", extra={"event_id": event_id})
        return False


@celery_app.task(name="webhooks.recover_pending_events")
def recover_pending_webhook_events() -> int:
    stale_before = datetime.now(UTC) - timedelta(minutes=5)
    with SessionLocal() as session:
        session.execute(
            update(WhatsAppWebhookEvent)
            .where(
                WhatsAppWebhookEvent.status == WebhookEventStatus.PROCESSING,
                WhatsAppWebhookEvent.processing_claimed_at < stale_before,
            )
            .values(
                status=WebhookEventStatus.PENDING,
                processing_claimed_at=None,
                error="Processamento interrompido; reagendado automaticamente.",
            )
        )
        event_ids = list(
            session.scalars(
                select(WhatsAppWebhookEvent.id)
                .where(
                    WhatsAppWebhookEvent.payload.is_not(None),
                    WhatsAppWebhookEvent.processing_attempts < MAX_PROCESSING_ATTEMPTS,
                    or_(
                        WhatsAppWebhookEvent.status == WebhookEventStatus.PENDING,
                        WhatsAppWebhookEvent.status == WebhookEventStatus.FAILED,
                    ),
                )
                .order_by(WhatsAppWebhookEvent.created_at)
                .limit(100)
            )
        )
        session.commit()

    dispatched = 0
    for event_id in event_ids:
        if not enqueue_webhook_event(str(event_id)):
            break
        dispatched += 1
    return dispatched
