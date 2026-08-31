import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import Conversation, ConversationTag, Tag, UserRole
from app.schemas.tag import TagCreate, TagResponse, TagUpdate
from app.services.audit import record_audit

router = APIRouter(tags=["tags"])


def require_admin(current_user: CurrentUser) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar etiquetas.")


def get_tag(session: DatabaseSession, organization_id: uuid.UUID, tag_id: uuid.UUID) -> Tag:
    tag = session.scalar(select(Tag).where(Tag.id == tag_id, Tag.organization_id == organization_id))
    if tag is None:
        raise HTTPException(status_code=404, detail="Etiqueta não encontrada.")
    return tag


@router.get("/tags", response_model=list[TagResponse])
def list_tags(session: DatabaseSession, current_user: CurrentUser) -> list[Tag]:
    return list(session.scalars(select(Tag).where(Tag.organization_id == current_user.organization_id).order_by(Tag.name)))


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(payload: TagCreate, session: DatabaseSession, current_user: CurrentUser) -> Tag:
    require_admin(current_user)
    tag = Tag(organization_id=current_user.organization_id, **payload.model_dump())
    session.add(tag)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma etiqueta com este nome.") from None
    record_audit(session, organization_id=current_user.organization_id, actor_user_id=current_user.id, action="tag.created", target_type="tag", target_id=str(tag.id))
    session.commit()
    session.refresh(tag)
    return tag


@router.patch("/tags/{tag_id}", response_model=TagResponse)
def update_tag(tag_id: uuid.UUID, payload: TagUpdate, session: DatabaseSession, current_user: CurrentUser) -> Tag:
    require_admin(current_user)
    tag = get_tag(session, current_user.organization_id, tag_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(tag, field, value)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma etiqueta com este nome.") from None
    session.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(tag_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser) -> Response:
    require_admin(current_user)
    tag = get_tag(session, current_user.organization_id, tag_id)
    session.delete(tag)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def get_conversation(session: DatabaseSession, organization_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
    conversation = session.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.organization_id == organization_id))
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return conversation


@router.get("/conversations/{conversation_id}/tags", response_model=list[TagResponse])
def list_conversation_tags(conversation_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser) -> list[Tag]:
    get_conversation(session, current_user.organization_id, conversation_id)
    return list(session.scalars(select(Tag).join(ConversationTag, ConversationTag.tag_id == Tag.id).where(ConversationTag.conversation_id == conversation_id).order_by(Tag.name)))


@router.post("/conversations/{conversation_id}/tags/{tag_id}", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def assign_tag(conversation_id: uuid.UUID, tag_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser) -> Tag:
    get_conversation(session, current_user.organization_id, conversation_id)
    tag = get_tag(session, current_user.organization_id, tag_id)
    existing = session.get(ConversationTag, (conversation_id, tag_id))
    if existing is None:
        session.add(ConversationTag(conversation_id=conversation_id, tag_id=tag_id, assigned_by_user_id=current_user.id))
        session.commit()
    return tag


@router.delete("/conversations/{conversation_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_tag(conversation_id: uuid.UUID, tag_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser) -> Response:
    get_conversation(session, current_user.organization_id, conversation_id)
    assignment = session.get(ConversationTag, (conversation_id, tag_id))
    if assignment:
        session.delete(assignment)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
