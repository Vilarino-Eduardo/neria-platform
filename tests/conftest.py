import pytest

from app.services.rate_limit import clear_attempts


@pytest.fixture(autouse=True)
def isolate_registration_rate_limit() -> None:
    clear_attempts("registration:ip", "testclient")
    yield
    clear_attempts("registration:ip", "testclient")
