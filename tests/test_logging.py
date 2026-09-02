import logging

from app.core.logging import (
    NOISY_THIRD_PARTY_LOGGERS,
    SENSITIVE_THIRD_PARTY_LOGGERS,
    configure_logging,
)


def test_development_logging_suppresses_sensitive_sdk_details() -> None:
    configure_logging("development")

    assert logging.getLogger().level == logging.DEBUG
    assert all(
        logging.getLogger(name).level == logging.WARNING
        for name in SENSITIVE_THIRD_PARTY_LOGGERS
    )
    assert all(
        logging.getLogger(name).level == logging.INFO
        for name in NOISY_THIRD_PARTY_LOGGERS
    )
