from fastapi import APIRouter, Response, status
from redis.exceptions import RedisError
from sqlalchemy import text

from app.api.dependencies import DatabaseSession
from app.services.rate_limit import get_rate_limit_redis

router = APIRouter(tags=["health"])


@router.get("/health", summary="Verifica a disponibilidade da API")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live", summary="Verifica se o processo da API está ativo")
def liveness_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", summary="Verifica dependências necessárias para operar")
def readiness_check(session: DatabaseSession, response: Response) -> dict:
    components = {"database": "ok", "redis": "ok"}
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - readiness must summarize any driver failure
        components["database"] = "unavailable"
    try:
        get_rate_limit_redis().ping()
    except RedisError:
        components["redis"] = "unavailable"
    ready = all(value == "ok" for value in components.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "unavailable", "components": components}
