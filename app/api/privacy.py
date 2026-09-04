import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import Text, cast, func, select, update

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import (
    Contact,
    Conversation,
    ConversationEvent,
    Message,
    OrganizationProfile,
    Ticket,
    UserRole,
    WebhookEventStatus,
    WhatsAppWebhookEvent,
)
from app.schemas.privacy import (
    ContactAnonymizationResponse,
    PrivacyConfirmation,
    RetentionPreviewResponse,
    RetentionRunResponse,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/privacy", tags=["privacy"])


def require_admin(current_user: CurrentUser) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem tratar dados pessoais.")


def get_contact(
    session: DatabaseSession, organization_id: uuid.UUID, contact_id: uuid.UUID
) -> Contact:
    contact = session.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.organization_id == organization_id,
        )
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contato não encontrado.")
    return contact


def profile_retention(session: DatabaseSession, organization_id: uuid.UUID) -> int:
    return session.scalar(
        select(OrganizationProfile.data_retention_days).where(
            OrganizationProfile.organization_id == organization_id
        )
    ) or 365


@router.get("/contacts/{contact_id}/export")
def export_contact_data(
    contact_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Response:
    require_admin(current_user)
    contact = get_contact(session, current_user.organization_id, contact_id)
    conversations = list(
        session.scalars(
            select(Conversation).where(
                Conversation.organization_id == current_user.organization_id,
                Conversation.contact_id == contact.id,
            )
        )
    )
    conversation_ids = [item.id for item in conversations]
    messages = list(
        session.scalars(select(Message).where(Message.conversation_id.in_(conversation_ids)))
    ) if conversation_ids else []
    tickets = list(
        session.scalars(select(Ticket).where(Ticket.conversation_id.in_(conversation_ids)))
    ) if conversation_ids else []
    payload = {
        "exported_at": datetime.now(UTC).isoformat(),
        "contact": {
            "id": contact.id,
            "phone_number": contact.phone_number,
            "name": contact.name,
            "profile_name": contact.profile_name,
            "is_blocked": contact.is_blocked,
            "created_at": contact.created_at,
        },
        "conversations": [
            {
                "id": item.id,
                "status": item.status.value,
                "mode": item.mode.value,
                "priority": item.priority.value,
                "created_at": item.created_at,
                "closed_at": item.closed_at,
            }
            for item in conversations
        ],
        "messages": [
            {
                "conversation_id": item.conversation_id,
                "direction": item.direction.value,
                "type": item.message_type.value,
                "body": item.body,
                "media_filename": item.media_filename,
                "created_at": item.created_at,
            }
            for item in messages
        ],
        "tickets": [
            {
                "conversation_id": item.conversation_id,
                "protocol": item.protocol,
                "subject": item.subject,
                "status": item.status.value,
                "created_at": item.created_at,
            }
            for item in tickets
        ],
    }
    record_audit(
        session,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="privacy.contact_exported",
        target_type="contact",
        target_id=str(contact.id),
    )
    session.commit()
    content = json.dumps(payload, ensure_ascii=False, default=str, indent=2).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="neria-contato-{contact.id}.json"'
        },
    )


@router.post(
    "/contacts/{contact_id}/anonymize",
    response_model=ContactAnonymizationResponse,
)
def anonymize_contact(
    contact_id: uuid.UUID,
    payload: PrivacyConfirmation,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> ContactAnonymizationResponse:
    require_admin(current_user)
    if payload.confirmation != "ANONIMIZAR":
        raise HTTPException(status_code=422, detail="Confirmação inválida.")
    contact = get_contact(session, current_user.organization_id, contact_id)
    conversation_ids = list(
        session.scalars(
            select(Conversation.id).where(
                Conversation.organization_id == current_user.organization_id,
                Conversation.contact_id == contact.id,
            )
        )
    )
    messages = list(
        session.scalars(select(Message).where(Message.conversation_id.in_(conversation_ids)))
    ) if conversation_ids else []
    events = list(
        session.scalars(
            select(ConversationEvent).where(
                ConversationEvent.conversation_id.in_(conversation_ids)
            )
        )
    ) if conversation_ids else []
    tickets = list(
        session.scalars(select(Ticket).where(Ticket.conversation_id.in_(conversation_ids)))
    ) if conversation_ids else []
    pending_webhooks = list(
        session.scalars(
            select(WhatsAppWebhookEvent).where(
                WhatsAppWebhookEvent.organization_id == current_user.organization_id,
                WhatsAppWebhookEvent.payload.is_not(None),
                cast(WhatsAppWebhookEvent.payload, Text).contains(contact.phone_number),
            )
        )
    )
    for message in messages:
        message.body = None
        message.media_id = None
        message.media_url = None
        message.media_filename = None
        message.raw_payload = None
        message.external_message_id = None
    for event in events:
        event.content = None
    for ticket in tickets:
        ticket.subject = None
    for webhook_event in pending_webhooks:
        webhook_event.payload = None
        webhook_event.status = WebhookEventStatus.PROCESSED
        webhook_event.processed_at = datetime.now(UTC)
        webhook_event.error = "Payload descartado por solicitação de privacidade."
    contact.phone_number = f"anon-{contact.id.hex[:26]}"
    contact.name = "Contato anonimizado"
    contact.profile_name = None
    contact.is_blocked = True
    contact.anonymized_at = datetime.now(UTC)
    record_audit(
        session,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="privacy.contact_anonymized",
        target_type="contact",
        target_id=str(contact.id),
        metadata={"conversations": len(conversation_ids), "messages": len(messages)},
    )
    session.commit()
    return ContactAnonymizationResponse(
        contact_id=contact.id,
        conversations_sanitized=len(conversation_ids),
        messages_sanitized=len(messages),
    )


def retention_scope(session: DatabaseSession, organization_id: uuid.UUID):
    retention_days = profile_retention(session, organization_id)
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    query = select(Conversation).where(
        Conversation.organization_id == organization_id,
        Conversation.closed_at.is_not(None),
        Conversation.closed_at <= cutoff,
    )
    return retention_days, cutoff, query


@router.get("/retention/preview", response_model=RetentionPreviewResponse)
def preview_retention(
    session: DatabaseSession, current_user: CurrentUser
) -> RetentionPreviewResponse:
    require_admin(current_user)
    retention_days, cutoff, query = retention_scope(
        session, current_user.organization_id
    )
    count = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    return RetentionPreviewResponse(
        retention_days=retention_days,
        cutoff=cutoff.isoformat(),
        conversations_eligible=count,
    )


@router.post("/retention/run", response_model=RetentionRunResponse)
def run_retention(
    payload: PrivacyConfirmation,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> RetentionRunResponse:
    require_admin(current_user)
    if payload.confirmation != "LIMPAR":
        raise HTTPException(status_code=422, detail="Confirmação inválida.")
    retention_days, cutoff, query = retention_scope(
        session, current_user.organization_id
    )
    eligible_count = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    conversations = list(session.scalars(query.limit(5000)))
    conversation_ids = [item.id for item in conversations]
    if conversation_ids:
        for message in session.scalars(
            select(Message).where(Message.conversation_id.in_(conversation_ids))
        ):
            message.body = None
            message.media_id = None
            message.media_url = None
            message.media_filename = None
            message.raw_payload = None
        for event in session.scalars(
            select(ConversationEvent).where(
                ConversationEvent.conversation_id.in_(conversation_ids)
            )
        ):
            event.content = None
        for ticket in session.scalars(
            select(Ticket).where(Ticket.conversation_id.in_(conversation_ids))
        ):
            ticket.subject = None
    session.execute(
        update(WhatsAppWebhookEvent)
        .where(
            WhatsAppWebhookEvent.organization_id == current_user.organization_id,
            WhatsAppWebhookEvent.created_at <= cutoff,
            WhatsAppWebhookEvent.payload.is_not(None),
        )
        .values(
            payload=None,
            status=WebhookEventStatus.PROCESSED,
            processed_at=datetime.now(UTC),
            error="Payload descartado pela política de retenção.",
        )
    )
    record_audit(
        session,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="privacy.retention_run",
        target_type="organization",
        target_id=str(current_user.organization_id),
        metadata={"conversations": len(conversations), "retention_days": retention_days},
    )
    session.commit()
    return RetentionRunResponse(
        retention_days=retention_days,
        cutoff=cutoff.isoformat(),
        conversations_eligible=eligible_count,
        conversations_sanitized=len(conversations),
        conversations_remaining=max(eligible_count - len(conversations), 0),
    )
