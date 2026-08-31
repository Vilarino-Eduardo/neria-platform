import pytest
from fastapi.testclient import TestClient

from app.application import app, validate_production_settings
from app.core.settings import Settings

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_liveness_and_readiness() -> None:
    request_id = "health-test-request"
    live = client.get("/api/v1/health/live", headers={"X-Request-ID": request_id})
    ready = client.get("/api/v1/health/ready")

    assert live.status_code == 200
    assert live.headers["X-Request-ID"] == request_id
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "components": {"database": "ok", "redis": "ok"},
    }


def test_production_rejects_default_secrets() -> None:
    settings = Settings(_env_file=None, environment="production")

    with pytest.raises(RuntimeError, match="Configuração insegura"):
        validate_production_settings(settings)
