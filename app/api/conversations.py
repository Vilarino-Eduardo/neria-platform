import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, status
from sqlalchemy import case, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import (
    AIRun,
    Contact,
    Conversation,
    ConversationEvent,
    ConversationMode,
    ConversationPriority,
    ConversationStatus,
    ConversationTag,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    OrganizationProfile,
    User,
    WhatsAppAccount,
    WhatsAppTemplate,
    WhatsAppTemplateStatus,
)
from app.schemas.conversation import (
    ConversationCreate,
    ConversationEventResponse,
    ConversationNoteCreate,
    ConversationResponse,
    ConversationUpdate,
    InboxConversationResponse,
    MessageCreate,
    MessageResponse,
)
from app.services.conversation_assignment import assign_conversation_if_needed
from app.services.conversation_lock import lock_active_conversation
from app.tasks.whatsapp import enqueue_outbound_message

router = APIRouter(prefix="/conversations", tags=["conversations"])


def get_organization_conversation(
    session: DatabaseSession,
    organization_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> Conversation:
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return conversation


@router.get("/inbox", response_model=list[InboxConversationResponse])
def list_inbox(
    session: DatabaseSession,
    current_user: CurrentUser,
    conversation_status: ConversationStatus | None = None,
    mode: ConversationMode | None = None,
    tag_id: uuid.UUID | None = None,
    priority: ConversationPriority | None = None,
    assignment: str | None = Query(default=None, pattern="^(mine|unassigned)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    now = datetime.now(UTC)
    sla_minutes = session.scalar(
        select(OrganizationProfile.sla_first_response_minutes).where(
            OrganizationProfile.organization_id == current_user.organization_id
        )
    ) or 15
    assigned_user = aliased(User)
    latest_message = (
        select(Message)
        .where(Message.conversation_id == Conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
        .lateral()
    )
    query = (
        select(
            Conversation,
            Contact.name,
            Contact.profile_name,
            Contact.phone_number,
            assigned_user.name.label("assigned_user_name"),
            latest_message.c.body.label("last_message_body"),
            latest_message.c.direction.label("last_message_direction"),
            latest_message.c.status.label("last_message_status"),
        )
        .join(Contact, Contact.id == Conversation.contact_id)
        .outerjoin(assigned_user, assigned_user.id == Conversation.assigned_user_id)
        .outerjoin(latest_message, true())
        .where(Conversation.organization_id == current_user.organization_id)
    )
    query = query.where(
        Conversation.status
        == (conversation_status or ConversationStatus.OPEN)
    )
    if mode:
        query = query.where(Conversation.mode == mode)
    if tag_id:
        query = query.join(
            ConversationTag,
            ConversationTag.conversation_id == Conversation.id,
        ).where(ConversationTag.tag_id == tag_id)
    if priority:
        query = query.where(Conversation.priority == priority)
    if assignment == "mine":
        query = query.where(Conversation.assigned_user_id == current_user.id)
    elif assignment == "unassigned":
        query = query.where(Conversation.assigned_user_id.is_(None))
    rows = session.execute(
        query.order_by(
            case(
                (Conversation.priority == ConversationPriority.URGENT, 4),
                (Conversation.priority == ConversationPriority.HIGH, 3),
                (Conversation.priority == ConversationPriority.NORMAL, 2),
                else_=1,
            ).desc(),
            Conversation.last_message_at.desc().nullslast(),
        )
        .limit(limit)
        .offset(offset)
    )
    result = []
    for row in rows:
        waiting = (
            row.Conversation.mode == ConversationMode.HUMAN
            and row.Conversation.status != ConversationStatus.CLOSED
            and row.Conversation.last_customer_message_at is not None
            and (
                row.Conversation.last_human_response_at is None
                or row.Conversation.last_human_response_at
                < row.Conversation.last_customer_message_at
            )
        )
        due_at = (
            row.Conversation.last_customer_message_at + timedelta(minutes=sla_minutes)
            if waiting
            else None
        )
        elapsed_minutes = (
            max(0, int((now - row.Conversation.last_customer_message_at).total_seconds() // 60))
            if waiting
            else None
        )
        if not waiting:
            sla_status = None
        elif now >= due_at:
            sla_status = "overdue"
        elif elapsed_minutes >= sla_minutes * 0.8:
            sla_status = "warning"
        else:
            sla_status = "on_time"
        result.append({
            **{
                column.name: getattr(row.Conversation, column.name)
                for column in Conversation.__table__.columns
            },
            "contact_name": row.name or row.profile_name or row.phone_number,
            "contact_phone": row.phone_number,
            "assigned_user_name": row.assigned_user_name,
            "last_message_body": row.last_message_body,
            "last_message_direction": row.last_message_direction,
            "last_message_status": row.last_message_status,
            "sla_status": sla_status,
            "sla_due_at": due_at,
            "waiting_minutes": elapsed_minutes,
        })
    return result


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    session: DatabaseSession,
    current_user: CurrentUser,
    conversation_status: ConversationStatus | None = None,
    mode: ConversationMode | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Conversation]:
    query = select(Conversation).where(
        Conversation.organization_id == current_user.organization_id
    )
    if conversation_status:
        query = query.where(Conversation.status == conversation_status)
    if mode:
        query = query.where(Conversation.mode == mode)

    return list(
        session.scalars(
            query.order_by(Conversation.last_message_at.desc().nullslast()).limit(limit).offset(offset)
        )
    )


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Conversation:
    account = session.scalar(
        select(WhatsAppAccount.id).where(
            WhatsAppAccount.id == payload.whatsapp_account_id,
            WhatsAppAccount.organization_id == current_user.organization_id,
        )
    )
    contact = session.scalar(
        select(Contact.id).where(
            Contact.id == payload.contact_id,
            Contact.organization_id == current_user.organization_id,
        )
    )
    if account is None or contact is None:
        raise HTTPException(status_code=404, detail="Conta do WhatsApp ou contato não encontrado.")

    lock_active_conversation(
        session,
        current_user.organization_id,
        payload.whatsapp_account_id,
        payload.contact_id,
    )
    existing = session.scalar(
        select(Conversation).where(
            Conversation.organization_id == current_user.organization_id,
            Conversation.whatsapp_account_id == payload.whatsapp_account_id,
            Conversation.contact_id == payload.contact_id,
            Conversation.status != ConversationStatus.CLOSED,
        )
    )
    if existing:
        return existing

    conversation = Conversation(
        organization_id=current_user.organization_id,
        **payload.model_dump(),
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Conversation:
    return get_organization_conversation(session, current_user.organization_id, conversation_id)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Conversation:
    conversation = get_organization_conversation(
        session, current_user.organization_id, conversation_id
    )

    if payload.assigned_user_id is not None:
        assigned_user = session.scalar(
            select(User.id).where(
                User.id == payload.assigned_user_id,
                User.organization_id == current_user.organization_id,
                User.is_active.is_(True),
            )
        )
        if assigned_user is None:
            raise HTTPException(status_code=404, detail="Atendente não encontrado.")

    changes = payload.model_dump(exclude_unset=True)
    tracked_fields = {"assigned_user_id", "priority", "mode", "status"}
    previous_values = {field: getattr(conversation, field) for field in tracked_fields}
    for field, value in changes.items():
        setattr(conversation, field, value)

    explicit_unassignment = (
        "assigned_user_id" in changes and changes["assigned_user_id"] is None
    )
    if not explicit_unassignment:
        assign_conversation_if_needed(session, conversation)

    if payload.status == ConversationStatus.CLOSED:
        conversation.closed_at = datetime.now(UTC)
    elif payload.status is not None:
        conversation.closed_at = None

    for field in tracked_fields.intersection(changes):
        old_value = previous_values[field]
        new_value = getattr(conversation, field)
        if old_value == new_value:
            continue
        session.add(
            ConversationEvent(
                organization_id=current_user.organization_id,
                conversation_id=conversation.id,
                actor_user_id=current_user.id,
                event_type=f"{field}.changed",
                event_data={
                    "from": str(old_value.value if hasattr(old_value, "value") else old_value)
                    if old_value is not None
                    else None,
                    "to": str(new_value.value if hasattr(new_value, "value") else new_value)
                    if new_value is not None
                    else None,
                },
            )
        )
    session.commit()
    session.refresh(conversation)
    return conversation


@router.get(
    "/{conversation_id}/events",
    response_model=list[ConversationEventResponse],
)
def list_conversation_events(
    conversation_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict]:
    get_organization_conversation(session, current_user.organization_id, conversation_id)
    actor = aliased(User)
    rows = session.execute(
        select(ConversationEvent, actor.name.label("actor_name"))
        .outerjoin(actor, actor.id == ConversationEvent.actor_user_id)
        .where(
            ConversationEvent.conversation_id == conversation_id,
            ConversationEvent.organization_id == current_user.organization_id,
        )
        .order_by(ConversationEvent.created_at.desc())
        .limit(limit)
    )
    return [
        {
            **{
                column.name: getattr(row.ConversationEvent, column.name)
                for column in ConversationEvent.__table__.columns
            },
            "actor_name": row.actor_name,
        }
        for row in rows
    ]


@router.post(
    "/{conversation_id}/notes",
    response_model=ConversationEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation_note(
    conversation_id: uuid.UUID,
    payload: ConversationNoteCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> dict:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="A nota não pode ficar vazia.")
    conversation = get_organization_conversation(
        session, current_user.organization_id, conversation_id
    )
    note = ConversationEvent(
        organization_id=current_user.organization_id,
        conversation_id=conversation.id,
        actor_user_id=current_user.id,
        event_type="note.created",
        content=content,
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    return {
        **{
            column.name: getattr(note, column.name)
            for column in ConversationEvent.__table__.columns
        },
        "actor_name": current_user.name,
    }


@router.post("/{conversation_id}/mark-read", response_model=ConversationResponse)
def mark_conversation_read(
    conversation_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Conversation:
    conversation = get_organization_conversation(
        session, current_user.organization_id, conversation_id
    )
    conversation.unread_count = 0
    session.commit()
    session.refresh(conversation)
    return conversation


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conversation_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    get_organization_conversation(session, current_user.organization_id, conversation_id)
    rows = session.execute(
        select(Message, AIRun.id.label("ai_run_id"))
        .outerjoin(AIRun, AIRun.output_message_id == Message.id)
        .where(
            Message.conversation_id == conversation_id,
            Message.organization_id == current_user.organization_id,
        )
        .order_by(Message.created_at, Message.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            **{
                column.name: getattr(row.Message, column.name)
                for column in Message.__table__.columns
            },
            "ai_run_id": row.ai_run_id,
            "ai_source_titles": (
                row.Message.raw_payload.get("source_titles", [])
                if row.ai_run_id and row.Message.raw_payload
                else []
            ),
        }
        for row in rows
    ]


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_outbound_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=16, max_length=128),
    ],
) -> Message:
    conversation = get_organization_conversation(
        session, current_user.organization_id, conversation_id
    )
    payload_hash = hashlib.sha256(
        json.dumps(
            {
                "conversation_id": str(conversation.id),
                "payload": payload.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    existing_message = session.scalar(
        select(Message).where(
            Message.organization_id == current_user.organization_id,
            Message.idempotency_key == idempotency_key,
        )
    )
    if existing_message:
        if existing_message.idempotency_payload_hash != payload_hash:
            raise HTTPException(
                status_code=409,
                detail="A chave de idempotência já foi usada com outro conteúdo.",
            )
        return existing_message
    if conversation.status == ConversationStatus.CLOSED:
        raise HTTPException(status_code=409, detail="A conversa está encerrada.")
    contact = session.get(Contact, conversation.contact_id)
    if contact is None or contact.is_blocked:
        raise HTTPException(status_code=409, detail="Este contato está bloqueado.")

    template = None
    if payload.message_type == MessageType.TEMPLATE:
        template = session.scalar(
            select(WhatsAppTemplate).where(
                WhatsAppTemplate.id == payload.template_id,
                WhatsAppTemplate.organization_id == current_user.organization_id,
                WhatsAppTemplate.whatsapp_account_id == conversation.whatsapp_account_id,
                WhatsAppTemplate.status == WhatsAppTemplateStatus.APPROVED,
            )
        )
        if template is None:
            raise HTTPException(status_code=422, detail="Template aprovado não encontrado.")
    else:
        window_start = datetime.now(UTC) - timedelta(hours=24)
        if (
            conversation.last_customer_message_at is None
            or conversation.last_customer_message_at < window_start
        ):
            raise HTTPException(
                status_code=409,
                detail="Fora da janela de 24 horas. Utilize um template aprovado.",
            )

    raw_payload = None
    if payload.interactive:
        raw_payload = {"interactive": payload.interactive.model_dump(mode="json")}
    elif template:
        raw_payload = {
            "template": {
                "name": template.name,
                "language": template.language,
                "parameters": payload.template_parameters,
            }
        }

    sent_at = datetime.now(UTC)
    message = Message(
        organization_id=current_user.organization_id,
        conversation_id=conversation.id,
        template_id=template.id if template else None,
        sender_user_id=current_user.id,
        direction=MessageDirection.OUTBOUND,
        message_type=payload.message_type,
        status=MessageStatus.QUEUED,
        body=payload.body,
        media_url=str(payload.media_url) if payload.media_url else None,
        media_filename=payload.media_filename,
        raw_payload=raw_payload,
        idempotency_key=idempotency_key,
        idempotency_payload_hash=payload_hash,
    )
    conversation.last_message_at = sent_at
    conversation.last_human_response_at = sent_at
    session.add(message)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing_message = session.scalar(
            select(Message).where(
                Message.organization_id == current_user.organization_id,
                Message.idempotency_key == idempotency_key,
            )
        )
        if existing_message and existing_message.idempotency_payload_hash == payload_hash:
            return existing_message
        raise HTTPException(
            status_code=409,
            detail="A chave de idempotência já foi usada com outro conteúdo.",
        ) from None
    session.refresh(message)
    enqueue_outbound_message(str(message.id))
    return message


@router.post(
    "/{conversation_id}/messages/{message_id}/retry",
    response_model=MessageResponse,
)
def retry_failed_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Message:
    conversation = get_organization_conversation(
        session, current_user.organization_id, conversation_id
    )
    message = session.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.conversation_id == conversation.id,
            Message.organization_id == current_user.organization_id,
            Message.direction == MessageDirection.OUTBOUND,
        )
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada.")
    if message.status != MessageStatus.FAILED:
        raise HTTPException(
            status_code=409,
            detail="Apenas mensagens com falha podem ser reenviadas.",
        )
    message.status = MessageStatus.QUEUED
    message.delivery_error = None
    session.add(
        ConversationEvent(
            organization_id=current_user.organization_id,
            conversation_id=conversation.id,
            actor_user_id=current_user.id,
            event_type="message.retry_requested",
            content="Reenvio de mensagem solicitado.",
            event_data={"message_id": str(message.id)},
        )
    )
    session.commit()
    session.refresh(message)
    enqueue_outbound_message(str(message.id))
    return message
