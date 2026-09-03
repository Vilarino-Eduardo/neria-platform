from app.services.ai.errors import safe_ai_error_code


def test_unknown_provider_error_does_not_persist_original_details() -> None:
    error = RuntimeError("secret customer text and upstream metadata")

    code = safe_ai_error_code(error)

    assert code == "provider_error"
    assert "secret" not in code
    assert "customer" not in code
