import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.core import (
    AIConfiguration,
    AIRun,
    AIRunStatus,
    Contact,
    Conversation,
    ConversationMode,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    WebhookEventStatus,
    WhatsAppAccount,
    WhatsAppWebhookEvent,
)
from app.services.ai.context import PROMPT_VERSION
from app.services.automation_engine import process_automation
from app.tasks.ai import generate_ai_reply
from app.tasks.whatsapp import enqueue_outbound_message


def extract_message_body(message: dict) -> str | None:
    message_type = message.get("type")
    if message_type == "text":
        return message.get("text", {}).get("body")
    if message_type == "interactive":
        interactive = message.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return reply.get("title") or reply.get("id")
    return message.get(message_type or "", {}).get("caption")


def normalize_message_type(value: str | None) -> MessageType:
    try:
        return MessageType(value)
    except ValueError:
        return MessageType.SYSTEM


def process_webhook_event(session: Session, event: WhatsAppWebhookEvent) -> None:
    queued_message_ids = []
    ai_message_ids = []
    try:
        for entry in event.payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                phone_number_id = value.get("metadata", {}).get("phone_number_id")
                account = session.scalar(
                    select(WhatsAppAccount).where(
                        WhatsAppAccount.meta_phone_number_id == phone_number_id
                    )
                )
                if account is None:
                    continue

                profile_names = {
                    item.get("wa_id"): item.get("profile", {}).get("name")
                    for item in value.get("contacts", [])
                }
                for incoming in value.get("messages", []):
                    queued, ai_input = process_incoming_message(
                        session, account, incoming, profile_names
                    )
                    queued_message_ids.extend(queued)
                    if ai_input:
                        ai_message_ids.append(ai_input)

                for status_payload in value.get("statuses", []):
                    update_message_status(session, status_payload)

        event.status = WebhookEventStatus.PROCESSED
        event.processed_at = datetime.now(UTC)
        session.commit()
        for message_id in queued_message_ids:
            enqueue_outbound_message(str(message_id))
        for message_id in ai_message_ids:
            generate_ai_reply.delay(str(message_id))
    except Exception as exc:
        session.rollback()
        stored_event = session.get(WhatsAppWebhookEvent, event.id)
        if stored_event:
            stored_event.status = WebhookEventStatus.FAILED
            stored_event.error = str(exc)[:2000]
            session.commit()
        raise


def process_incoming_message(
    session: Session,
    account: WhatsAppAccount,
    incoming: dict,
    profile_names: dict[str, str | None],
) -> tuple[list, uuid.UUID | None]:
    external_id = incoming.get("id")
    if not external_id or session.scalar(
        select(Message.id).where(Message.external_message_id == external_id)
    ):
        return [], None

    phone_number = incoming.get("from")
    if not phone_number:
        return [], None

    contact = session.scalar(
        select(Contact).where(
            Contact.organization_id == account.organization_id,
            Contact.phone_number == phone_number,
        )
    )
    if contact is None:
        contact = Contact(
            organization_id=account.organization_id,
            phone_number=phone_number,
            profile_name=profile_names.get(phone_number),
        )
        session.add(contact)
        session.flush()

    conversation = session.scalar(
        select(Conversation).where(
            Conversation.organization_id == account.organization_id,
            Conversation.whatsapp_account_id == account.id,
            Conversation.contact_id == contact.id,
            Conversation.status != ConversationStatus.CLOSED,
        )
    )
    if conversation is None:
        conversation = Conversation(
            organization_id=account.organization_id,
            whatsapp_account_id=account.id,
            contact_id=contact.id,
        )
        session.add(conversation)
        session.flush()

    message = Message(
        organization_id=account.organization_id,
        conversation_id=conversation.id,
        external_message_id=external_id,
        direction=MessageDirection.INBOUND,
        message_type=normalize_message_type(incoming.get("type")),
        status=MessageStatus.RECEIVED,
        body=extract_message_body(incoming),
        media_id=incoming.get(incoming.get("type", ""), {}).get("id"),
        media_mime_type=incoming.get(incoming.get("type", ""), {}).get("mime_type"),
        media_filename=incoming.get(incoming.get("type", ""), {}).get("filename"),
        raw_payload=incoming,
    )
    received_at = datetime.now(UTC)
    try:
        received_at = datetime.fromtimestamp(int(incoming.get("timestamp")), UTC)
    except (TypeError, ValueError, OSError):
        pass
    conversation.last_message_at = received_at
    conversation.last_customer_message_at = received_at
    conversation.unread_count += 1
    session.add(message)
    session.flush()
    if contact.is_blocked:
        conversation.mode = ConversationMode.HUMAN
        return [], None
    outcome = process_automation(session, conversation, message.body)
    if outcome.handled:
        return outcome.message_ids, None
    configuration = session.scalar(
        select(AIConfiguration).where(
            AIConfiguration.organization_id == account.organization_id
        )
    )
    settings = get_settings()
    if configuration is None or not configuration.is_enabled or not settings.openai_api_key:
        return outcome.message_ids, None
    session.add(
        AIRun(
            organization_id=account.organization_id,
            conversation_id=conversation.id,
            input_message_id=message.id,
            status=AIRunStatus.PENDING,
            provider="openai",
            model=settings.openai_model,
            prompt_version=PROMPT_VERSION,
        )
    )
    return outcome.message_ids, message.id


def update_message_status(session: Session, payload: dict) -> None:
    message = session.scalar(
        select(Message).where(Message.external_message_id == payload.get("id"))
    )
    if message is None:
        return
    try:
        incoming_status = MessageStatus(payload.get("status"))
    except (TypeError, ValueError):
        return
    progression = {
        MessageStatus.QUEUED: 0,
        MessageStatus.SENDING: 0,
        MessageStatus.SENT: 1,
        MessageStatus.DELIVERED: 2,
        MessageStatus.READ: 3,
    }
    current_rank = progression.get(message.status)
    incoming_rank = progression.get(incoming_status)
    if current_rank is not None and incoming_rank is not None:
        if incoming_rank >= current_rank:
            message.status = incoming_status
        return
    if message.status not in {MessageStatus.DELIVERED, MessageStatus.READ}:
        message.status = incoming_status
