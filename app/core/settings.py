from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Neria"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    secret_key: str = "development-only-change-this-key-before-production"
    access_token_expire_minutes: int = 60
    credential_encryption_key: str | None = None
    meta_app_secret: str = "development-meta-app-secret"
    meta_webhook_verify_token: str = "development-webhook-token"
    meta_graph_api_version: str = "v26.0"
    database_url: str = "postgresql+psycopg://neria:neria@localhost:5432/neria"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout_seconds: int = 30
    database_retry_after_seconds: int = 5
    redis_url: str = "redis://localhost:6379/0"
    trusted_proxy_networks: str = ""
    max_request_body_bytes: int = 12 * 1024 * 1024
    knowledge_storage_path: str = "storage/knowledge"
    knowledge_max_file_bytes: int = 10 * 1024 * 1024
    object_storage_backend: str = "local"
    r2_endpoint_url: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str | None = None
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "neria-minio"
    s3_secret_access_key: str = "neria-minio-development"
    s3_bucket_name: str = "neria-knowledge"
    s3_region: str = "us-east-1"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    password_reset_expire_minutes: int = 30
    password_reset_url: str = "http://localhost:8000/?reset_token={token}"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "nao-responda@neria.local"
    smtp_use_tls: bool = True
    registration_ip_limit: int = 20
    registration_rate_window_seconds: int = 3600
    login_attempt_limit: int = 5
    login_ip_limit: int = 30
    login_rate_window_seconds: int = 900
    password_reset_limit: int = 5
    password_reset_ip_limit: int = 20
    password_reset_rate_window_seconds: int = 3600
    trial_days: int = 14
    billing_admin_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
