from scripts.check_secrets import PATTERNS


def test_secret_patterns_detect_openai_key_shape() -> None:
    simulated_key = "sk-" + "proj-" + ("A" * 32)

    assert PATTERNS["OpenAI API key"].search(simulated_key)
    assert not PATTERNS["OpenAI API key"].search("change-this-openai-key")
