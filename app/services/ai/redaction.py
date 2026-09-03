import re
from dataclasses import replace

from app.services.ai.contracts import AIMessage, AIRequest

REDACTED = "[REDIGIDO]"

_CPF_PATTERN = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_CVV_PATTERN = re.compile(
    r"\b(cvv|cvc|código\s+de\s+segurança)\s*[:=\-]?\s*\d{3,4}\b",
    re.IGNORECASE,
)
_SECRET_PATTERN = re.compile(
    r"\b(senha|password|token|access_token|chave\s+de\s+api|api[ _-]?key)"
    r"\s*[:=]\s*[^\s,;]{4,}",
    re.IGNORECASE,
)
_BEARER_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)


def _passes_luhn(value: str) -> bool:
    digits = [int(character) for character in value if character.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def redact_sensitive_data(value: str) -> str:
    """Remove common high-risk secrets before content leaves Neria."""
    value = _CPF_PATTERN.sub("[CPF REDIGIDO]", value)
    value = _CVV_PATTERN.sub(lambda match: f"{match.group(1)}: {REDACTED}", value)
    value = _SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}: {REDACTED}", value
    )
    value = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", value)
    return _CARD_PATTERN.sub(
        lambda match: "[CARTÃO REDIGIDO]"
        if _passes_luhn(match.group(0))
        else match.group(0),
        value,
    )


def redact_ai_request(request: AIRequest) -> AIRequest:
    """Return a sanitized copy while leaving persisted conversation data untouched."""
    return AIRequest(
        system_instructions=redact_sensitive_data(request.system_instructions),
        messages=[
            AIMessage(role=message.role, content=redact_sensitive_data(message.content))
            for message in request.messages
        ],
        knowledge=[
            replace(
                item,
                source_title=redact_sensitive_data(item.source_title),
                content=redact_sensitive_data(item.content),
            )
            for item in request.knowledge
        ],
    )
