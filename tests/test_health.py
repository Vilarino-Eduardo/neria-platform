import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.application import app, create_application, validate_production_settings
from app.core.settings import Settings

client = TestClient(app)


def secure_production_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="production",
        secret_key="7b2d62b6b73041c8967a42377149c90f",
        meta_app_secret="8b7f506cd4d44a949aa0b15b553fdb25",
        meta_webhook_verify_token="f23b77b5d58c43b6896165aa",
        credential_encryption_key=Fernet.generate_key().decode(),
        object_storage_backend="r2",
        r2_endpoint_url="https://storage.neria.test",
        r2_access_key_id="r2-access-5f20c1",
        r2_secret_access_key="r2-secret-b40e1df6f7c3497b",
        r2_bucket_name="neria-production-data",
        password_reset_url="https://app.neria.test/?reset_token={token}",
        smtp_host="smtp.neria.test",
        smtp_use_tls=True,
    )


def test_api_documentation_is_only_exposed_outside_production() -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200

    production_client = TestClient(create_application(secure_production_settings()))
    assert production_client.get("/docs").status_code == 404
    assert production_client.get("/redoc").status_code == 404
    assert production_client.get("/openapi.json").status_code == 404


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


def test_production_rejects_documented_placeholders() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        secret_key="change-this-development-key-before-production-123456",
        meta_app_secret="change-this-meta-app-secret-with-more-characters",
        meta_webhook_verify_token="change-this-webhook-verify-token",
        credential_encryption_key=Fernet.generate_key().decode(),
        object_storage_backend="r2",
        r2_endpoint_url="https://example.invalid",
        r2_access_key_id="change-this",
        r2_secret_access_key="change-this",
        r2_bucket_name="change-this",
        password_reset_url="https://example.invalid/reset?token={token}",
        smtp_host="smtp.example.invalid",
    )

    with pytest.raises(RuntimeError) as error:
        validate_production_settings(settings)

    message = str(error.value)
    assert "SECRET_KEY" in message
    assert "META_APP_SECRET" in message
    assert "META_WEBHOOK_VERIFY_TOKEN" in message
    assert "R2_ACCESS_KEY_ID" in message
    assert "PASSWORD_RESET_URL" not in message


def test_production_accepts_strong_complete_configuration() -> None:
    validate_production_settings(secure_production_settings())
