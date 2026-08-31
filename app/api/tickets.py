import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.conversations import get_organization_conversation
from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import ConversationMode, Ticket, TicketStatus
from app.schemas.conversation import TicketCreate, TicketResponse
from app.services.conversation_assignment import assign_conversation_if_needed

router = APIRouter(tags=["tickets"])


@router.get("/tickets", response_model=list[TicketResponse])
def list_tickets(
    session: DatabaseSession,
    current_user: CurrentUser,
    ticket_status: TicketStatus | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Ticket]:
    query = select(Ticket).where(Ticket.organization_id == current_user.organization_id)
    if ticket_status:
        query = query.where(Ticket.status == ticket_status)
    return list(
        session.scalars(query.order_by(Ticket.created_at.desc()).limit(limit).offset(offset))
    )


@router.post(
    "/conversations/{conversation_id}/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket(
    conversation_id: uuid.UUID,
    payload: TicketCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Ticket:
    conversation = get_organization_conversation(
        session, current_user.organization_id, conversation_id
    )
    existing = session.scalar(
        select(Ticket).where(
            Ticket.conversation_id == conversation.id,
            Ticket.status != TicketStatus.CLOSED,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Já existe um ticket aberto.")

    ticket = Ticket(
        organization_id=current_user.organization_id,
        conversation_id=conversation.id,
        assigned_user_id=conversation.assigned_user_id,
        protocol=f"NR-{uuid.uuid4().hex[:12].upper()}",
        subject=payload.subject,
        status=TicketStatus.OPEN,
    )
    conversation.mode = ConversationMode.HUMAN
    assign_conversation_if_needed(session, conversation)
    ticket.assigned_user_id = conversation.assigned_user_id
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/close", response_model=TicketResponse)
def close_ticket(
    ticket_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Ticket:
    ticket = session.scalar(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.organization_id == current_user.organization_id,
        )
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket não encontrado.")
    if ticket.status == TicketStatus.CLOSED:
        return ticket

    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = datetime.now(UTC)
    session.commit()
    session.refresh(ticket)
    return ticket
