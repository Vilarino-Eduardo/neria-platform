import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.crypto import decrypt_secret
from app.database.session import SessionLocal
from app.integrations.whatsapp.client import MetaWhatsAppClient
from app.models.core import (
    Contact,
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
    WhatsAppAccount,
    WhatsAppAccountStatus,
)
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="whatsapp.send_message", max_retries=4)
def send_whatsapp_message(self, message_id: str) -> None:
    with SessionLocal() as session:
        message = session.scalar(
            select(Message)
            .where(
                Message.id == uuid.UUID(message_id),
                Message.status.in_({MessageStatus.QUEUED, MessageStatus.FAILED}),
            )
            .with_for_update(skip_locked=True)
        )
        if message is None:
            return
        message.status = MessageStatus.SENDING
        message.delivery_claimed_at = datetime.now(UTC)
        message.delivery_attempts += 1
        message.delivery_error = None
        session.commit()

        conversation = session.get(Conversation, message.conversation_id)
        if conversation is None:
            return
        account = session.get(WhatsAppAccount, conversation.whatsapp_account_id)
        contact = session.get(Contact, conversation.contact_id)
        if (
            account is None
            or contact is None
            or account.status != WhatsAppAccountStatus.ACTIVE
            or not account.access_token_encrypted
            or not account.meta_phone_number_id
        ):
            message.status = MessageStatus.FAILED
            message.delivery_error = "Conta do WhatsApp indisponível ou incompleta."
            message.delivery_claimed_at = None
            session.commit()
            return

        client = MetaWhatsAppClient(
            access_token=decrypt_secret(account.access_token_encrypted),
            phone_number_id=account.meta_phone_number_id,
        )
        try:
            external_id = client.send_message(
                recipient=contact.phone_number,
                message_type=message.message_type.value,
                body=message.body,
                media_url=message.media_url,
                media_filename=message.media_filename,
                interactive=(message.raw_payload or {}).get("interactive"),
                template=(message.raw_payload or {}).get("template"),
            )
            message.external_message_id = external_id
            message.status = MessageStatus.SENT
            message.delivery_error = None
            message.delivery_claimed_at = None
            session.commit()
        except Exception as exc:
            session.rollback()
            failed_message = session.get(Message, uuid.UUID(message_id))
            if failed_message:
                failed_message.status = MessageStatus.FAILED
                failed_message.delivery_error = str(exc)[:2000]
                failed_message.delivery_claimed_at = None
                session.commit()
            if self.request.retries >= self.max_retries:
                raise
            raise self.retry(exc=exc, countdown=min(2 ** (self.request.retries + 1), 60))


def enqueue_outbound_message(message_id: str) -> bool:
    try:
        send_whatsapp_message.delay(message_id)
        return True
    except Exception:
        logger.exception("outbound_message_enqueue_failed", extra={"message_id": message_id})
        return False


@celery_app.task(name="whatsapp.recover_pending_messages")
def recover_pending_messages() -> int:
    now = datetime.now(UTC)
    stale_before = now - timedelta(minutes=5)
    with SessionLocal() as session:
        session.execute(
            update(Message)
            .where(
                Message.status == MessageStatus.SENDING,
                Message.delivery_claimed_at < stale_before,
            )
            .values(status=MessageStatus.QUEUED, delivery_claimed_at=None)
        )
        message_ids = list(
            session.scalars(
                select(Message.id)
                .where(
                    Message.direction == MessageDirection.OUTBOUND,
                    Message.status == MessageStatus.QUEUED,
                )
                .order_by(Message.created_at)
                .limit(100)
            )
        )
        session.commit()

    dispatched = 0
    for pending_id in message_ids:
        if not enqueue_outbound_message(str(pending_id)):
            break
        dispatched += 1
    return dispatched
