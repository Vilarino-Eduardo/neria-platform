from app.core.settings import Settings


def test_default_openai_model_matches_supported_evaluation_model() -> None:
    settings = Settings(_env_file=None)

    assert settings.openai_model == "gpt-5-mini"
