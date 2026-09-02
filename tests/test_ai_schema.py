import pytest
from pydantic import ValidationError

from app.schemas.ai import AIConfigurationUpdate


def test_ai_tone_is_normalized_to_one_instruction_line() -> None:
    payload = AIConfigurationUpdate(tone="  profissional\n e   acolhedor  ")

    assert payload.tone == "profissional e acolhedor"


def test_ai_tone_rejects_whitespace_only_value() -> None:
    with pytest.raises(ValidationError, match="tom de voz válido"):
        AIConfigurationUpdate(tone="   ")
