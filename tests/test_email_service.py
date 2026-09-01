from unittest.mock import MagicMock, patch

from app.core.settings import Settings
from app.services.email_service import (
    SMTPMailer,
    build_password_reset_message,
    send_password_reset_email,
)


def test_password_reset_message_contains_safe_expected_content() -> None:
    message = build_password_reset_message(
        "cliente@example.com",
        "https://neria.example/reset?token=secret",
        from_email="nao-responda@neria.example",
        expire_minutes=30,
    )
    assert message["To"] == "cliente@example.com"
    assert message["Subject"] == "Redefinição de senha da Neria"
    assert "30 minutos" in message.get_content()
    assert "token=secret" in message.get_content()


@patch("app.services.email_service.smtplib.SMTP")
def test_smtp_mailer_supports_local_server_without_tls(smtp_class) -> None:
    smtp = MagicMock()
    smtp_class.return_value.__enter__.return_value = smtp
    message = build_password_reset_message(
        "cliente@example.com",
        "http://localhost/reset",
        from_email="nao-responda@neria.local",
        expire_minutes=30,
    )

    SMTPMailer(host="localhost", port=1025, use_tls=False).send(message)

    smtp_class.assert_called_once_with("localhost", 1025, timeout=15)
    smtp.starttls.assert_not_called()
    smtp.login.assert_not_called()
    smtp.send_message.assert_called_once_with(message)


def test_missing_smtp_never_logs_reset_secret_or_email(caplog) -> None:
    settings = Settings(_env_file=None, smtp_host=None)
    reset_url = "http://localhost:8000/?reset_token=highly-sensitive-token"

    with patch("app.services.email_service.get_settings", return_value=settings):
        send_password_reset_email("private@example.com", reset_url)

    assert "SMTP is not configured" in caplog.text
    assert "highly-sensitive-token" not in caplog.text
    assert "private@example.com" not in caplog.text
