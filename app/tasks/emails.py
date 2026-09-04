import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update

from app.core.crypto import decrypt_secret
from app.core.settings import get_settings
from app.database.session import SessionLocal
from app.models.core import EmailDeliveryStatus, PasswordResetToken, User
from app.services.email_service import send_password_reset_email
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
MAX_DELIVERY_ATTEMPTS = 5


@celery_app.task(name="emails.send_password_reset")
def send_password_reset_email_task(token_id: str) -> None:
    now = datetime.now(UTC)
    with SessionLocal() as session:
        token = session.scalar(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.id == uuid.UUID(token_id),
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > now,
                PasswordResetToken.delivery_token_encrypted.is_not(None),
                PasswordResetToken.delivery_attempts < MAX_DELIVERY_ATTEMPTS,
                PasswordResetToken.delivery_status.in_(
                    {EmailDeliveryStatus.PENDING, EmailDeliveryStatus.FAILED}
                ),
            )
            .with_for_update(skip_locked=True)
        )
        if token is None:
            return
        user = session.get(User, token.user_id)
        if user is None or not user.is_active:
            token.delivery_status = EmailDeliveryStatus.FAILED
            token.delivery_error = "Destinatário indisponível."
            token.delivery_token_encrypted = None
            session.commit()
            return
        encrypted_token = token.delivery_token_encrypted
        recipient = user.email
        token.delivery_status = EmailDeliveryStatus.SENDING
        token.delivery_attempts += 1
        token.delivery_claimed_at = now
        token.delivery_error = None
        session.commit()

        try:
            raw_token = decrypt_secret(encrypted_token)
            reset_url = get_settings().password_reset_url.format(token=raw_token)
            if not send_password_reset_email(recipient, reset_url):
                raise RuntimeError("SMTP não configurado")
        except Exception as exc:
            session.rollback()
            failed = session.get(PasswordResetToken, uuid.UUID(token_id))
            if failed:
                failed.delivery_status = EmailDeliveryStatus.FAILED
                failed.delivery_error = f"Falha no envio: {type(exc).__name__}"
                failed.delivery_claimed_at = None
                session.commit()
            raise

        delivered = session.get(PasswordResetToken, uuid.UUID(token_id))
        if delivered:
            delivered.delivery_status = EmailDeliveryStatus.SENT
            delivered.delivered_at = datetime.now(UTC)
            delivered.delivery_claimed_at = None
            delivered.delivery_error = None
            delivered.delivery_token_encrypted = None
            session.commit()


def enqueue_password_reset_email(token_id: str) -> bool:
    try:
        send_password_reset_email_task.delay(token_id)
        return True
    except Exception:
        logger.exception("password_reset_email_enqueue_failed", extra={"token_id": token_id})
        return False


@celery_app.task(name="emails.recover_pending_password_resets")
def recover_pending_password_reset_emails() -> int:
    now = datetime.now(UTC)
    stale_before = now - timedelta(minutes=5)
    with SessionLocal() as session:
        session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.delivery_status == EmailDeliveryStatus.SENDING,
                PasswordResetToken.delivery_claimed_at < stale_before,
            )
            .values(
                delivery_status=EmailDeliveryStatus.PENDING,
                delivery_claimed_at=None,
                delivery_error="Envio interrompido; reagendado automaticamente.",
            )
        )
        token_ids = list(
            session.scalars(
                select(PasswordResetToken.id)
                .where(
                    PasswordResetToken.used_at.is_(None),
                    PasswordResetToken.expires_at > now,
                    PasswordResetToken.delivery_token_encrypted.is_not(None),
                    PasswordResetToken.delivery_attempts < MAX_DELIVERY_ATTEMPTS,
                    or_(
                        PasswordResetToken.delivery_status == EmailDeliveryStatus.PENDING,
                        PasswordResetToken.delivery_status == EmailDeliveryStatus.FAILED,
                    ),
                )
                .order_by(PasswordResetToken.created_at)
                .limit(100)
            )
        )
        session.commit()

    dispatched = 0
    for token_id in token_ids:
        if not enqueue_password_reset_email(str(token_id)):
            break
        dispatched += 1
    return dispatched
