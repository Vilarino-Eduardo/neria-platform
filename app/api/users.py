import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.security import hash_password
from app.models.core import Organization, User, UserRole
from app.schemas.auth import CreateUserRequest, UpdateUserRequest, UserResponse
from app.services.audit import record_audit
from app.services.database import integrity_conflict

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
def list_users(session: DatabaseSession, current_user: CurrentUser) -> list[User]:
    return list(
        session.scalars(
            select(User)
            .where(User.organization_id == current_user.organization_id)
            .order_by(User.name)
        )
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem criar usuários.")

    organization = session.scalar(
        select(Organization)
        .where(Organization.id == current_user.organization_id)
        .with_for_update()
    )
    user_count = session.scalar(
        select(func.count(User.id)).where(
            User.organization_id == current_user.organization_id,
            User.is_active.is_(True),
        )
    )
    if organization is None or user_count >= organization.max_users:
        raise HTTPException(status_code=409, detail="Limite de usuários atingido.")

    email_exists = session.scalar(select(User.id).where(User.email == payload.email))
    if email_exists:
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")

    user = User(
        organization_id=current_user.organization_id,
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    with integrity_conflict(session, "E-mail já cadastrado."):
        session.flush()
        record_audit(
            session,
            organization_id=current_user.organization_id,
            actor_user_id=current_user.id,
            action="user.created",
            target_type="user",
            target_id=str(user.id),
            metadata={"role": user.role.value},
        )
        session.commit()
    session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar usuários.")

    user = session.scalar(
        select(User).where(
            User.id == user_id,
            User.organization_id == current_user.organization_id,
        )
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if user.id == current_user.id and (
        payload.role not in (None, UserRole.ADMIN) or payload.is_active is False
    ):
        raise HTTPException(
            status_code=409,
            detail="O administrador não pode remover o próprio acesso.",
        )

    if payload.is_active is True and not user.is_active:
        organization = session.scalar(
            select(Organization)
            .where(Organization.id == current_user.organization_id)
            .with_for_update()
        )
        active_count = session.scalar(
            select(func.count(User.id)).where(
                User.organization_id == current_user.organization_id,
                User.is_active.is_(True),
            )
        )
        if organization is None or active_count >= organization.max_users:
            raise HTTPException(status_code=409, detail="Limite de usuários atingido.")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(user, field, value)

    record_audit(
        session,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="user.updated",
        target_type="user",
        target_id=str(user.id),
        metadata={"fields": sorted(changes)},
    )

    session.commit()
    session.refresh(user)
    return user
