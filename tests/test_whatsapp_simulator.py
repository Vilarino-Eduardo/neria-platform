import hashlib
import hmac
import json

import pytest

from app.integrations.whatsapp.simulator import (
    inbound_text_payload,
    message_status_payload,
    signed_body,
)
from scripts.simulate_whatsapp import require_local_url


def test_simulator_builds_meta_compatible_signed_inbound_message() -> None:
    payload = inbound_text_payload(
        phone_number_id="phone-123",
        sender="5511777777777",
        profile_name="Maria",
        body="Olá Neria",
        message_id="wamid.local.123",
        timestamp=1_800_000_000,
    )
    raw_body, signature = signed_body(payload, "secret")

    value = payload["entry"][0]["changes"][0]["value"]
    assert value["metadata"]["phone_number_id"] == "phone-123"
    assert value["contacts"][0]["profile"]["name"] == "Maria"
    assert value["messages"][0]["text"]["body"] == "Olá Neria"
    assert json.loads(raw_body) == payload
    expected = hmac.new(b"secret", raw_body, hashlib.sha256).hexdigest()
    assert signature == f"sha256={expected}"


@pytest.mark.parametrize("status", ["sent", "delivered", "read", "failed"])
def test_simulator_builds_supported_message_statuses(status: str) -> None:
    payload = message_status_payload(
        phone_number_id="phone-123",
        message_id="wamid.outbound.123",
        status=status,
    )
    value = payload["entry"][0]["changes"][0]["value"]
    assert value["statuses"] == [{"id": "wamid.outbound.123", "status": status}]


def test_simulator_blocks_external_destinations() -> None:
    assert require_local_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"
    with pytest.raises(ValueError, match="somente"):
        require_local_url("https://graph.facebook.com")
