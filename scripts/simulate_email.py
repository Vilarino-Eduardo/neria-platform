"""Envia e confere um e-mail no Mailpit local, sem entrega externa."""

import json
import time
import uuid
from urllib.parse import urlparse

import httpx

from app.services.email_service import SMTPMailer, build_password_reset_message

MAILPIT_API = "http://localhost:8025"


def require_local_url(url: str) -> None:
    if urlparse(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("A homologação aceita somente o Mailpit local.")


def main() -> int:
    require_local_url(MAILPIT_API)
    suffix = uuid.uuid4().hex
    recipient = f"homologacao-{suffix}@neria.local"
    reset_url = f"http://localhost:8000/?reset_token=local-{suffix}"
    message = build_password_reset_message(
        recipient,
        reset_url,
        from_email="nao-responda@neria.local",
        expire_minutes=30,
    )
    try:
        SMTPMailer(host="localhost", port=1025, use_tls=False).send(message)
        stored = None
        with httpx.Client(base_url=MAILPIT_API, timeout=5) as client:
            for _ in range(20):
                listing = client.get("/api/v1/messages")
                listing.raise_for_status()
                candidates = listing.json().get("messages", [])
                stored = next(
                    (item for item in candidates if recipient in json.dumps(item)), None
                )
                if stored:
                    break
                time.sleep(0.25)
            if not stored:
                raise RuntimeError("O e-mail não apareceu no Mailpit.")
            detail = client.get(f"/api/v1/message/{stored['ID']}")
            detail.raise_for_status()
            content_verified = reset_url in detail.text
    except (OSError, httpx.HTTPError, RuntimeError) as exc:
        print(json.dumps({"error": f"Falha no Mailpit local: {exc}"}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "external_delivery_used": False,
                "recipient": recipient,
                "smtp_capture": "ok",
                "subject": message["Subject"],
                "content_verified": content_verified,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if content_verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
