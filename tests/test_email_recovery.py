import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import delete

from app.core.crypto import encrypt_secret
from app.database.session import SessionLocal
from app.models.core import (
    EmailDeliveryStatus,
    Organization,
    PasswordResetToken,
    User,
    UserRole,
)
from app.tasks.emails import (
    recover_pending_password_reset_emails,
    send_password_reset_email_task,
)


def test_password_reset_email_is_sent_once_and_secret_is_discarded() -> None:
    suffix = uuid.uuid4().hex
    organization_id = uuid.uuid4()
    token_id = uuid.uuid4()
    raw_token = f"reset-{suffix}"
    try:
        with SessionLocal() as session:
            organization = Organization(
                id=organization_id,
                name="Recuperação de e-mail",
                slug=f"email-recovery-{suffix}",
            )
            user = User(
                organization=organization,
                name="Administrador",
                email=f"email-recovery-{suffix}@example.com",
                password_hash="not-used-in-this-test",
                role=UserRole.ADMIN,
            )
            session.add_all([organization, user])
            session.flush()
            session.add(
                PasswordResetToken(
                    id=token_id,
                    user_id=user.id,
                    token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
                    delivery_token_encrypted=encrypt_secret(raw_token),
                    expires_at=datetime.now(UTC) + timedelta(minutes=30),
                )
            )
            session.commit()

        with patch(
            "app.tasks.emails.send_password_reset_email", return_value=True
        ) as send:
            send_password_reset_email_task.run(str(token_id))
            send_password_reset_email_task.run(str(token_id))

        send.assert_called_once()
        assert raw_token in send.call_args.args[1]
        with SessionLocal() as session:
            delivered = session.get(PasswordResetToken, token_id)
            assert delivered.delivery_status == EmailDeliveryStatus.SENT
            assert delivered.delivery_attempts == 1
            assert delivered.delivery_token_encrypted is None
            assert delivered.delivered_at is not None
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()


def test_interrupted_password_reset_delivery_is_recovered() -> None:
    suffix = uuid.uuid4().hex
    organization_id = uuid.uuid4()
    token_id = uuid.uuid4()
    try:
        with SessionLocal() as session:
            organization = Organization(
                id=organization_id,
                name="Recuperação interrompida",
                slug=f"email-interrupted-{suffix}",
            )
            user = User(
                organization=organization,
                name="Administrador",
                email=f"email-interrupted-{suffix}@example.com",
                password_hash="not-used-in-this-test",
                role=UserRole.ADMIN,
            )
            session.add_all([organization, user])
            session.flush()
            session.add(
                PasswordResetToken(
                    id=token_id,
                    user_id=user.id,
                    token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                    delivery_token_encrypted=encrypt_secret("temporary-reset-token"),
                    delivery_status=EmailDeliveryStatus.SENDING,
                    delivery_claimed_at=datetime.now(UTC) - timedelta(minutes=10),
                    expires_at=datetime.now(UTC) + timedelta(minutes=30),
                )
            )
            session.commit()

        with patch("app.tasks.emails.send_password_reset_email_task.delay") as dispatch:
            recovered = recover_pending_password_reset_emails.run()

        assert recovered >= 1
        dispatch.assert_any_call(str(token_id))
        with SessionLocal() as session:
            recovered_token = session.get(PasswordResetToken, token_id)
            assert recovered_token.delivery_status == EmailDeliveryStatus.PENDING
            assert recovered_token.delivery_claimed_at is None
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()
