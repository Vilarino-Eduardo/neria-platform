from unittest.mock import patch

import pytest

from app.core.settings import Settings
from app.database.session import build_database_engine


def test_default_openai_model_matches_supported_evaluation_model() -> None:
    settings = Settings(_env_file=None)

    assert settings.openai_model == "gpt-5-mini"


def test_local_database_uses_ipv4_and_bounded_connection_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)

    assert "@127.0.0.1:" in settings.database_url
    with patch("app.database.session.create_engine") as create_engine:
        build_database_engine(settings)

    assert create_engine.call_args.kwargs["connect_args"] == {"connect_timeout": 5}
