import uuid
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database.session import get_database_session
from app.models.core import Subscription, SubscriptionStatus, User

DatabaseSession = Annotated[Session, Depends(get_database_session)]
bearer_scheme = HTTPBearer(auto_error=False)


def get_authenticated_user(
    session: DatabaseSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
        session_version = int(payload["session_version"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise unauthorized from None

    user = session.get(User, user_id)
    if user is None or not user.is_active or user.session_version != session_version:
        raise unauthorized

    return user


AuthenticatedUser = Annotated[User, Depends(get_authenticated_user)]


def get_current_user(
    session: DatabaseSession,
    user: AuthenticatedUser,
) -> User:
    subscription = session.scalar(
        select(Subscription).where(Subscription.organization_id == user.organization_id)
    )
    now = datetime.now(UTC)
    allowed = subscription is not None and (
        subscription.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE}
        or (
            subscription.status == SubscriptionStatus.TRIALING
            and subscription.trial_ends_at is not None
            and subscription.trial_ends_at > now
        )
    )
    if not allowed:
        raise HTTPException(
            status_code=402,
            detail="Assinatura inativa. Entre em contato com o suporte da Neria.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
