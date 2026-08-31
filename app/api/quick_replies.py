import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import QuickReply, UserRole
from app.schemas.quick_reply import QuickReplyCreate, QuickReplyResponse, QuickReplyUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/quick-replies", tags=["quick-replies"])


def require_admin(current_user: CurrentUser) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar respostas rápidas.")


def get_organization_reply(
    session: DatabaseSession, organization_id: uuid.UUID, reply_id: uuid.UUID
) -> QuickReply:
    reply = session.scalar(
        select(QuickReply).where(
            QuickReply.id == reply_id,
            QuickReply.organization_id == organization_id,
        )
    )
    if reply is None:
        raise HTTPException(status_code=404, detail="Resposta rápida não encontrada.")
    return reply


@router.get("", response_model=list[QuickReplyResponse])
def list_quick_replies(
    session: DatabaseSession, current_user: CurrentUser
) -> list[QuickReply]:
    return list(
        session.scalars(
            select(QuickReply)
            .where(
                QuickReply.organization_id == current_user.organization_id,
                QuickReply.is_active.is_(True),
            )
            .order_by(QuickReply.title)
        )
    )


@router.post("", response_model=QuickReplyResponse, status_code=status.HTTP_201_CREATED)
def create_quick_reply(
    payload: QuickReplyCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> QuickReply:
    require_admin(current_user)
    reply = QuickReply(organization_id=current_user.organization_id, **payload.model_dump())
    session.add(reply)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Este atalho já está em uso.") from None
    record_audit(session, organization_id=current_user.organization_id, actor_user_id=current_user.id, action="quick_reply.created", target_type="quick_reply", target_id=str(reply.id))
    session.commit()
    session.refresh(reply)
    return reply


@router.patch("/{reply_id}", response_model=QuickReplyResponse)
def update_quick_reply(reply_id: uuid.UUID, payload: QuickReplyUpdate, session: DatabaseSession, current_user: CurrentUser) -> QuickReply:
    require_admin(current_user)
    reply = get_organization_reply(session, current_user.organization_id, reply_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(reply, field, value)
    record_audit(session, organization_id=current_user.organization_id, actor_user_id=current_user.id, action="quick_reply.updated", target_type="quick_reply", target_id=str(reply.id), metadata={"fields": sorted(changes)})
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Este atalho já está em uso.") from None
    session.refresh(reply)
    return reply


@router.delete("/{reply_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quick_reply(reply_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser) -> Response:
    require_admin(current_user)
    reply = get_organization_reply(session, current_user.organization_id, reply_id)
    reply.is_active = False
    record_audit(session, organization_id=current_user.organization_id, actor_user_id=current_user.id, action="quick_reply.deleted", target_type="quick_reply", target_id=str(reply.id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
