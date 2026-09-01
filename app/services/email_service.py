import logging
import smtplib
from email.message import EmailMessage

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


def build_password_reset_message(
    email: str, reset_url: str, *, from_email: str, expire_minutes: int
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "Redefinição de senha da Neria"
    message["From"] = from_email
    message["To"] = email
    message.set_content(
        "Recebemos uma solicitação para redefinir sua senha da Neria.\n\n"
        f"Acesse o link abaixo em até {expire_minutes} minutos:\n"
        f"{reset_url}\n\n"
        "Se você não fez essa solicitação, ignore este e-mail."
    )
    return message


class SMTPMailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        use_tls: bool,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.username = username
        self.password = password

    def send(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.username and self.password:
                smtp.login(self.username, self.password)
            smtp.send_message(message)


def send_password_reset_email(email: str, reset_url: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        logger.warning("Password reset email skipped because SMTP is not configured")
        return
    message = build_password_reset_message(
        email,
        reset_url,
        from_email=settings.smtp_from_email,
        expire_minutes=settings.password_reset_expire_minutes,
    )
    SMTPMailer(
        host=settings.smtp_host,
        port=settings.smtp_port,
        use_tls=settings.smtp_use_tls,
        username=settings.smtp_username,
        password=settings.smtp_password,
    ).send(message)
