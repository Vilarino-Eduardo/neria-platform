"""Envia webhooks realistas à Neria local, sem usar a Meta ou gerar custos."""

import argparse
import json
import uuid
from urllib.parse import urlparse

import httpx

from app.core.settings import get_settings
from app.integrations.whatsapp.simulator import (
    inbound_text_payload,
    message_status_payload,
    signed_body,
)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--phone-number-id", required=True)
    parser.add_argument("--business-account-id", default="local-business-account")
    parser.add_argument("--duplicate", action="store_true", help="Reenvia o mesmo evento.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--text", help="Texto recebido do cliente simulado.")
    mode.add_argument("--status", choices=("sent", "delivered", "read", "failed"))
    parser.add_argument("--sender", default="5511777777777")
    parser.add_argument("--profile-name", default="Cliente simulado")
    parser.add_argument("--message-id")
    return parser.parse_args()


def require_local_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOCAL_HOSTS:
        raise ValueError("O simulador aceita somente localhost, 127.0.0.1 ou ::1.")
    return base_url.rstrip("/")


def main() -> int:
    args = parse_args()
    try:
        base_url = require_local_url(args.base_url)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    settings = get_settings()
    message_id = args.message_id or f"wamid.local.{uuid.uuid4().hex}"
    if args.text is not None:
        payload = inbound_text_payload(
            phone_number_id=args.phone_number_id,
            business_account_id=args.business_account_id,
            sender=args.sender,
            profile_name=args.profile_name,
            body=args.text,
            message_id=message_id,
        )
    else:
        if not args.message_id:
            print(
                json.dumps(
                    {"error": "--message-id é obrigatório ao simular status."},
                    ensure_ascii=False,
                )
            )
            return 2
        payload = message_status_payload(
            phone_number_id=args.phone_number_id,
            business_account_id=args.business_account_id,
            message_id=message_id,
            status=args.status,
        )

    raw_body, signature = signed_body(payload, settings.meta_app_secret)
    webhook_url = f"{base_url}/api/v1/webhooks/whatsapp"
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": signature,
    }
    try:
        verification = httpx.get(
            webhook_url,
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": settings.meta_webhook_verify_token,
                "hub.challenge": "24680",
            },
            timeout=10,
        )
        verification.raise_for_status()
        responses = [httpx.post(webhook_url, content=raw_body, headers=headers, timeout=10)]
        if args.duplicate:
            responses.append(
                httpx.post(webhook_url, content=raw_body, headers=headers, timeout=10)
            )
        for response in responses:
            response.raise_for_status()
    except httpx.HTTPError as exc:
        print(json.dumps({"error": f"Falha na Neria local: {exc}"}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "external_network_used": False,
                "message_id": message_id,
                "verification": verification.json(),
                "webhook_results": [response.json() for response in responses],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
