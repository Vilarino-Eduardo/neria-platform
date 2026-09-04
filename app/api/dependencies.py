import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database.session import get_database_session
from app.models.core import Organization, OrganizationStatus, Subscription, SubscriptionStatus, User

DatabaseSession = Annotated[Session, Depends(get_database_session)]
bearer_scheme = HTTPBearer(auto_error=False)
SESSION_COOKIE_NAME = "neria_session"
CSRF_COOKIE_NAME = "neria_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def enforce_cookie_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS or SESSION_COOKIE_NAME not in request.cookies:
        return
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    header_token = request.headers.get("X-CSRF-Token", "")
    if not cookie_token or not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="Proteção CSRF inválida.")


def get_authenticated_user(
    request: Request,
    session: DatabaseSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials if credentials else request.cookies.get(SESSION_COOKIE_NAME)
    if token is None:
        raise unauthorized
    if credentials is None:
        enforce_cookie_csrf(request)

    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
        session_version = int(payload["session_version"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise unauthorized from None

    user = session.get(User, user_id)
    if user is None or not user.is_active or user.session_version != session_version:
        raise unauthorized
    organization = session.get(Organization, user.organization_id)
    if organization is None or organization.status != OrganizationStatus.ACTIVE:
        raise HTTPException(
            status_code=403,
            detail="Organização suspensa. Entre em contato com o suporte da Neria.",
        )

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
