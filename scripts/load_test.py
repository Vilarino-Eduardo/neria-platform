import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from collections import Counter

import httpx
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from app.models.core import Organization

AUTHENTICATED_PATHS = (
    "/api/v1/dashboard",
    "/api/v1/conversations/inbox",
    "/api/v1/notifications/summary",
    "/api/v1/tags",
)


def percentile(values: list[float], percentile_value: int) -> float:
    if not values:
        return 0
    position = min(len(values) - 1, round((percentile_value / 100) * (len(values) - 1)))
    return sorted(values)[position]


async def create_temporary_tenant(client: httpx.AsyncClient) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:12]
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Neria Load Test",
            "organization_slug": f"load-test-{suffix}",
            "admin_name": "Load Test",
            "admin_email": f"load-test-{suffix}@example.com",
            "password": f"Load-test-{uuid.uuid4().hex}!",
        },
    )
    response.raise_for_status()
    payload = response.json()
    return payload["organization"]["id"], payload["token"]["access_token"]


def cleanup_temporary_tenant(organization_id: str, database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            session.execute(
                delete(Organization).where(Organization.id == uuid.UUID(organization_id))
            )
            session.commit()
    finally:
        engine.dispose()


async def run(args: argparse.Namespace) -> int:
    limits = httpx.Limits(
        max_connections=args.concurrency,
        max_keepalive_connections=args.concurrency,
    )
    timeout = httpx.Timeout(args.timeout)
    organization_id = None
    token = args.token
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"), limits=limits, timeout=timeout
    ) as client:
        if args.temporary_tenant:
            organization_id, token = await create_temporary_tenant(client)
        paths = AUTHENTICATED_PATHS if token else ("/api/v1/health", "/api/v1/health/ready")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        semaphore = asyncio.Semaphore(args.concurrency)
        latencies: list[float] = []
        statuses: Counter = Counter()

        async def request_once(index: int) -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(paths[index % len(paths)], headers=headers)
                    statuses[response.status_code] += 1
                except httpx.HTTPError:
                    statuses["network_error"] += 1
                finally:
                    latencies.append((time.perf_counter() - started) * 1000)

        for index in range(min(20, args.requests)):
            await request_once(index)
        latencies.clear()
        statuses.clear()
        started = time.perf_counter()
        await asyncio.gather(*(request_once(index) for index in range(args.requests)))
        duration = time.perf_counter() - started

    if organization_id:
        cleanup_temporary_tenant(organization_id, args.database_url)

    failures = sum(count for code, count in statuses.items() if code != 200)
    result = {
        "requests": args.requests,
        "concurrency": args.concurrency,
        "duration_seconds": round(duration, 2),
        "requests_per_second": round(args.requests / duration, 2),
        "latency_ms": {
            "average": round(statistics.fmean(latencies), 2),
            "p50": round(percentile(latencies, 50), 2),
            "p95": round(percentile(latencies, 95), 2),
            "p99": round(percentile(latencies, 99), 2),
        },
        "statuses": dict(statuses),
        "failure_rate_percent": round((failures / args.requests) * 100, 2),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["failure_rate_percent"] > args.max_failure_rate or result["latency_ms"]["p95"] > args.max_p95_ms)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teste de carga HTTP reproduzível da Neria.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--token", default=os.getenv("NERIA_LOAD_TEST_TOKEN"))
    parser.add_argument("--temporary-tenant", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "postgresql+psycopg://neria:neria@localhost:5432/neria"))
    parser.add_argument("--max-failure-rate", type=float, default=1)
    parser.add_argument("--max-p95-ms", type=float, default=1000)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1 or args.concurrency > 500:
        parser.error("requests e concurrency devem ser positivos; concurrency máximo é 500")
    if args.temporary_tenant and args.base_url not in {
        "http://localhost:8000",
        "http://localhost:18000",
        "http://localhost:18001",
    }:
        parser.error("temporary-tenant só pode ser usado contra localhost")
    return args


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
