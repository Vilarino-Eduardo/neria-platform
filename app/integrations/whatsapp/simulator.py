"""Utilitários sem rede para simular eventos recebidos da Meta."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any


def inbound_text_payload(
    *,
    phone_number_id: str,
    sender: str,
    body: str,
    message_id: str,
    business_account_id: str = "local-business-account",
    profile_name: str = "Cliente simulado",
    timestamp: int | None = None,
) -> dict[str, Any]:
    """Cria um webhook de texto com o mesmo formato entregue pela Meta."""
    received_at = timestamp or int(datetime.now(UTC).timestamp())
    return _payload(
        phone_number_id=phone_number_id,
        business_account_id=business_account_id,
        value={
            "contacts": [{"wa_id": sender, "profile": {"name": profile_name}}],
            "messages": [
                {
                    "id": message_id,
                    "from": sender,
                    "timestamp": str(received_at),
                    "type": "text",
                    "text": {"body": body},
                }
            ],
        },
    )


def message_status_payload(
    *,
    phone_number_id: str,
    message_id: str,
    status: str,
    business_account_id: str = "local-business-account",
) -> dict[str, Any]:
    """Cria um webhook de status de uma mensagem enviada pela Neria."""
    if status not in {"sent", "delivered", "read", "failed"}:
        raise ValueError(f"Status não suportado pelo simulador: {status}")
    return _payload(
        phone_number_id=phone_number_id,
        business_account_id=business_account_id,
        value={"statuses": [{"id": message_id, "status": status}]},
    )


def signed_body(payload: dict[str, Any], app_secret: str) -> tuple[bytes, str]:
    """Serializa o evento e calcula X-Hub-Signature-256 como a Meta."""
    raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    digest = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return raw_body, f"sha256={digest}"


def _payload(
    *, phone_number_id: str, business_account_id: str, value: dict[str, Any]
) -> dict[str, Any]:
    value["metadata"] = {"phone_number_id": phone_number_id}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": business_account_id,
                "changes": [{"field": "messages", "value": value}],
            }
        ],
    }
