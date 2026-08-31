import uuid

from app.core.crypto import decrypt_secret
from app.database.session import SessionLocal
from app.integrations.whatsapp.client import MetaWhatsAppClient
from app.models.core import (
    Contact,
    Conversation,
    Message,
    MessageStatus,
    WhatsAppAccount,
    WhatsAppAccountStatus,
)
from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, name="whatsapp.send_message", max_retries=4)
def send_whatsapp_message(self, message_id: str) -> None:
    with SessionLocal() as session:
        message = session.get(Message, uuid.UUID(message_id))
        if message is None or message.status not in {MessageStatus.QUEUED, MessageStatus.FAILED}:
            return

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
            session.commit()
            return

        client = MetaWhatsAppClient(
            access_token=decrypt_secret(account.access_token_encrypted),
            phone_number_id=account.meta_phone_number_id,
        )
        try:
            message.delivery_attempts += 1
            message.delivery_error = None
            session.commit()
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
            session.commit()
        except Exception as exc:
            session.rollback()
            if self.request.retries >= self.max_retries:
                failed_message = session.get(Message, uuid.UUID(message_id))
                if failed_message:
                    failed_message.status = MessageStatus.FAILED
                    failed_message.delivery_error = str(exc)[:2000]
                    session.commit()
                raise
            raise self.retry(exc=exc, countdown=min(2 ** (self.request.retries + 1), 60))
