import logging
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.logging import configure_logging
from app.core.settings import get_settings

logger = logging.getLogger("neria.http")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def validate_production_settings(settings) -> None:
    if settings.environment != "production":
        return
    invalid = []
    if settings.secret_key == "development-only-change-this-key-before-production":
        invalid.append("SECRET_KEY")
    if settings.meta_app_secret == "development-meta-app-secret":
        invalid.append("META_APP_SECRET")
    if settings.meta_webhook_verify_token == "development-webhook-token":
        invalid.append("META_WEBHOOK_VERIFY_TOKEN")
    if not settings.credential_encryption_key:
        invalid.append("CREDENTIAL_ENCRYPTION_KEY")
    if settings.object_storage_backend != "r2":
        invalid.append("OBJECT_STORAGE_BACKEND=r2")
    if not settings.r2_endpoint_url:
        invalid.append("R2_ENDPOINT_URL")
    if not settings.r2_access_key_id:
        invalid.append("R2_ACCESS_KEY_ID")
    if not settings.r2_secret_access_key:
        invalid.append("R2_SECRET_ACCESS_KEY")
    if not settings.r2_bucket_name:
        invalid.append("R2_BUCKET_NAME")
    if invalid:
        raise RuntimeError(
            "Configuração insegura para produção. Defina: " + ", ".join(invalid)
        )


def create_application() -> FastAPI:
    settings = get_settings()
    validate_production_settings(settings)
    configure_logging(settings.environment)

    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.3.0-alpha.1",
    )
    application.include_router(api_router, prefix=settings.api_prefix)

    @application.middleware("http")
    async def request_observability(request, call_next):
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_request_id
            if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
            else uuid.uuid4().hex
        )
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

    web_directory = Path(__file__).parent / "web"
    application.mount(
        "/static", StaticFiles(directory=web_directory / "static"), name="static"
    )

    @application.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/app")

    @application.get("/app", include_in_schema=False)
    def web_app() -> FileResponse:
        return FileResponse(web_directory / "index.html")

    return application


app = create_application()
