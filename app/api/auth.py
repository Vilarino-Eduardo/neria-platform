import hashlib
import ipaddress
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select, update

from app.api.dependencies import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    AuthenticatedUser,
    DatabaseSession,
    enforce_cookie_csrf,
)
from app.core.crypto import encrypt_secret
from app.core.security import create_access_token, hash_password, verify_password
from app.core.settings import get_settings
from app.models.core import (
    Organization,
    OrganizationProfile,
    OrganizationStatus,
    PasswordResetToken,
    Subscription,
    User,
    UserRole,
)
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    OrganizationResponse,
    RegisterOrganizationRequest,
    RegistrationResponse,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.services.audit import record_audit
from app.services.database import integrity_conflict
from app.services.rate_limit import clear_attempts, record_attempt, retry_after
from app.tasks.emails import enqueue_password_reset_email

router = APIRouter(prefix="/auth", tags=["authentication"])


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=secrets.token_urlsafe(32),
        max_age=settings.access_token_expire_minutes * 60,
        httponly=False,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


def resolve_client_ip(peer: str, forwarded_for: str | None, trusted_networks: str) -> str:
    try:
        peer_address = ipaddress.ip_address(peer)
        networks = [
            ipaddress.ip_network(item.strip())
            for item in trusted_networks.split(",")
            if item.strip()
        ]
    except ValueError:
        return peer

    if not any(peer_address in network for network in networks) or not forwarded_for:
        return peer_address.compressed

    try:
        forwarded_addresses = [
            ipaddress.ip_address(item.strip()) for item in forwarded_for.split(",")
        ]
    except ValueError:
        return peer_address.compressed

    for address in reversed([*forwarded_addresses, peer_address]):
        if not any(address in network for network in networks):
            return address.compressed
    return forwarded_addresses[0].compressed


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    return resolve_client_ip(
        peer,
        request.headers.get("X-Forwarded-For"),
        get_settings().trusted_proxy_networks,
    )


def enforce_rate_limits(rules: list[tuple[str, str, int]]) -> None:
    waits = [retry_after(scope, identity, limit) for scope, identity, limit in rules]
    active_waits = [wait for wait in waits if wait is not None]
    if active_waits:
        retry = max(active_waits)
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas. Aguarde antes de tentar novamente.",
            headers={"Retry-After": str(retry)},
        )


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
def register_organization(
    payload: RegisterOrganizationRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> RegistrationResponse:
    settings = get_settings()
    ip = client_ip(request)
    enforce_rate_limits([("registration:ip", ip, settings.registration_ip_limit)])
    record_attempt("registration:ip", ip, settings.registration_rate_window_seconds)

    slug_exists = session.scalar(
        select(Organization.id).where(Organization.slug == payload.organization_slug)
    )
    email_exists = session.scalar(select(User.id).where(User.email == payload.admin_email))
    if slug_exists or email_exists:
        raise HTTPException(status_code=409, detail="Empresa ou e-mail já cadastrado.")

    organization = Organization(name=payload.organization_name, slug=payload.organization_slug)
    profile = OrganizationProfile(
        organization=organization,
        company_name=payload.organization_name,
    )
    subscription = Subscription(
        organization=organization,
        plan_code="starter",
        trial_ends_at=datetime.now(UTC) + timedelta(days=settings.trial_days),
    )
    user = User(
        organization=organization,
        name=payload.admin_name,
        email=payload.admin_email,
        password_hash=hash_password(payload.password),
        role=UserRole.ADMIN,
    )
    session.add_all([organization, profile, subscription, user])
    with integrity_conflict(session, "Empresa ou e-mail já cadastrado."):
        session.commit()
    session.refresh(organization)
    session.refresh(user)

    token = create_access_token(
        user_id=user.id,
        organization_id=organization.id,
        role=user.role.value,
        session_version=user.session_version,
    )
    set_session_cookie(response, token)
    return RegistrationResponse(
        organization=OrganizationResponse.model_validate(organization),
        user=UserResponse.model_validate(user),
        token=TokenResponse(access_token=token),
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> TokenResponse:
    settings = get_settings()
    ip = client_ip(request)
    rules = [
        ("login:account", payload.email, settings.login_attempt_limit),
        ("login:ip", ip, settings.login_ip_limit),
    ]
    enforce_rate_limits(rules)
    user = session.scalar(select(User).where(User.email == payload.email))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        record_attempt("login:account", payload.email, settings.login_rate_window_seconds)
        record_attempt("login:ip", ip, settings.login_rate_window_seconds)
        if user is not None:
            record_audit(
                session,
                organization_id=user.organization_id,
                actor_user_id=user.id,
                action="auth.login_failed",
                target_type="user",
                target_id=str(user.id),
                ip_address=ip,
            )
            session.commit()
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    organization = session.get(Organization, user.organization_id)
    if organization is None or organization.status != OrganizationStatus.ACTIVE:
        raise HTTPException(
            status_code=403,
            detail="Organização suspensa. Entre em contato com o suporte da Neria.",
        )

    clear_attempts("login:account", payload.email)
    clear_attempts("login:ip", ip)
    record_audit(
        session,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="auth.login_succeeded",
        target_type="user",
        target_id=str(user.id),
        ip_address=ip,
    )
    session.commit()

    token = create_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role.value,
        session_version=user.session_version,
    )
    set_session_cookie(response, token)
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response) -> None:
    enforce_cookie_csrf(request)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=get_settings().environment == "production",
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        secure=get_settings().environment == "production",
        samesite="lax",
        path="/",
    )


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    session: DatabaseSession,
) -> MessageResponse:
    settings = get_settings()
    ip = client_ip(request)
    rules = [
        ("password-reset:account", payload.email, settings.password_reset_limit),
        ("password-reset:ip", ip, settings.password_reset_ip_limit),
    ]
    enforce_rate_limits(rules)
    record_attempt(
        "password-reset:account", payload.email, settings.password_reset_rate_window_seconds
    )
    record_attempt("password-reset:ip", ip, settings.password_reset_rate_window_seconds)
    user = session.scalar(
        select(User).where(User.email == payload.email, User.is_active.is_(True))
    )
    if user:
        now = datetime.now(UTC)
        session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now, delivery_token_encrypted=None)
        )
        raw_token = secrets.token_urlsafe(48)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            delivery_token_encrypted=encrypt_secret(raw_token),
            expires_at=now + timedelta(minutes=settings.password_reset_expire_minutes),
        )
        session.add(reset_token)
        record_audit(
            session,
            organization_id=user.organization_id,
            actor_user_id=user.id,
            action="auth.password_reset_requested",
            target_type="user",
            target_id=str(user.id),
            ip_address=ip,
        )
        session.commit()
        enqueue_password_reset_email(str(reset_token.id))
    return MessageResponse(
        message="Se o e-mail estiver cadastrado, enviaremos as instruções de recuperação."
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    payload: ResetPasswordRequest,
    session: DatabaseSession,
) -> MessageResponse:
    now = datetime.now(UTC)
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    reset_token = session.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
    )
    if reset_token is None:
        raise HTTPException(status_code=400, detail="Link inválido ou expirado.")
    user = session.get(User, reset_token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Link inválido ou expirado.")
    user.password_hash = hash_password(payload.password)
    user.session_version += 1
    session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now, delivery_token_encrypted=None)
    )
    record_audit(
        session,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="auth.password_reset_completed",
        target_type="user",
        target_id=str(user.id),
    )
    session.commit()
    return MessageResponse(message="Senha redefinida com sucesso.")


@router.get("/me", response_model=UserResponse)
def get_me(current_user: AuthenticatedUser) -> User:
    return current_user
