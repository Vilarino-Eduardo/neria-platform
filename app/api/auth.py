import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from sqlalchemy import select, update

from app.api.dependencies import AuthenticatedUser, DatabaseSession
from app.core.security import create_access_token, hash_password, verify_password
from app.core.settings import get_settings
from app.models.core import (
    Organization,
    OrganizationProfile,
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
from app.services.email_service import send_password_reset_email
from app.services.rate_limit import clear_attempts, record_attempt, retry_after

router = APIRouter(prefix="/auth", tags=["authentication"])


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


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
    session: DatabaseSession,
) -> RegistrationResponse:
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
        trial_ends_at=datetime.now(UTC) + timedelta(days=get_settings().trial_days),
    )
    user = User(
        organization=organization,
        name=payload.admin_name,
        email=payload.admin_email,
        password_hash=hash_password(payload.password),
        role=UserRole.ADMIN,
    )
    session.add_all([organization, profile, subscription, user])
    session.commit()
    session.refresh(organization)
    session.refresh(user)

    token = create_access_token(
        user_id=user.id,
        organization_id=organization.id,
        role=user.role.value,
    )
    return RegistrationResponse(
        organization=OrganizationResponse.model_validate(organization),
        user=UserResponse.model_validate(user),
        token=TokenResponse(access_token=token),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, session: DatabaseSession) -> TokenResponse:
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

    return TokenResponse(
        access_token=create_access_token(
            user_id=user.id,
            organization_id=user.organization_id,
            role=user.role.value,
        )
    )


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
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
            .values(used_at=now)
        )
        raw_token = secrets.token_urlsafe(48)
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
                expires_at=now + timedelta(minutes=settings.password_reset_expire_minutes),
            )
        )
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
        reset_url = settings.password_reset_url.format(token=raw_token)
        background_tasks.add_task(send_password_reset_email, user.email, reset_url)
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
    session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
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
