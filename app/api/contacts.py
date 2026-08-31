import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import Contact, Conversation
from app.schemas.conversation import (
    ContactCreate,
    ContactResponse,
    ContactUpdate,
    ConversationResponse,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=list[ContactResponse])
def list_contacts(
    session: DatabaseSession,
    current_user: CurrentUser,
    search: str | None = Query(default=None, max_length=160),
    blocked: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Contact]:
    query = select(Contact).where(Contact.organization_id == current_user.organization_id)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Contact.name.ilike(term),
                Contact.profile_name.ilike(term),
                Contact.phone_number.ilike(term),
            )
        )
    if blocked is not None:
        query = query.where(Contact.is_blocked == blocked)
    return list(
        session.scalars(
            query.order_by(Contact.created_at.desc()).limit(limit).offset(offset)
        )
    )


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Contact:
    existing = session.scalar(
        select(Contact).where(
            Contact.organization_id == current_user.organization_id,
            Contact.phone_number == payload.phone_number,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Contato já cadastrado.")

    contact = Contact(organization_id=current_user.organization_id, **payload.model_dump())
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact


@router.get("/{contact_id}", response_model=ContactResponse)
def get_contact(
    contact_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Contact:
    contact = session.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.organization_id == current_user.organization_id,
        )
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contato não encontrado.")
    return contact


@router.patch("/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Contact:
    contact = session.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.organization_id == current_user.organization_id,
        )
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contato não encontrado.")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(contact, field, value)
    record_audit(
        session,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="contact.updated",
        target_type="contact",
        target_id=str(contact.id),
        metadata={"fields": sorted(changes)},
    )
    session.commit()
    session.refresh(contact)
    return contact


@router.get("/{contact_id}/conversations", response_model=list[ConversationResponse])
def list_contact_conversations(
    contact_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[Conversation]:
    contact_exists = session.scalar(
        select(Contact.id).where(
            Contact.id == contact_id,
            Contact.organization_id == current_user.organization_id,
        )
    )
    if contact_exists is None:
        raise HTTPException(status_code=404, detail="Contato não encontrado.")
    return list(
        session.scalars(
            select(Conversation)
            .where(
                Conversation.contact_id == contact_id,
                Conversation.organization_id == current_user.organization_id,
            )
            .order_by(Conversation.created_at.desc())
        )
    )
