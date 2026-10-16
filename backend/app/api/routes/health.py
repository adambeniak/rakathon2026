"""GET /api/health: liveness of the backend and its IRIS dependencies (FHIR + SQL)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Response, status

from app import __version__
from app.api.deps import FhirClientDep, IrisPoolDep
from app.api.schemas.health import CheckResult, HealthChecks, HealthResponse
from app.fhir.errors import FhirError

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_S = 10.0


async def _timed(check: Callable[[], Awaitable[object]]) -> CheckResult:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(check(), timeout=CHECK_TIMEOUT_S)
    except TimeoutError:
        detail: str | None = f"timeout after {CHECK_TIMEOUT_S:.0f} s"
    except FhirError as exc:
        detail = f"{type(exc).__name__} (HTTP {exc.status_code})" if exc.status_code else type(exc).__name__
    except Exception as exc:  # noqa: BLE001 - a health check reports every failure instead of raising
        detail = type(exc).__name__
    else:
        detail = None
    return CheckResult(ok=detail is None, latency_ms=round((time.perf_counter() - started) * 1000, 1), detail=detail)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Backend and IRIS health",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse, "description": "IRIS degraded"}},
)
async def health(response: Response, fhir: FhirClientDep, pool: IrisPoolDep) -> HealthResponse:
    fhir_check, sql_check = await asyncio.gather(
        _timed(fhir.capabilities),
        _timed(lambda: asyncio.to_thread(pool.ping)),
    )
    healthy = fhir_check.ok and sql_check.ok
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if healthy else "degraded",
        version=__version__,
        checks=HealthChecks(fhir=fhir_check, iris_sql=sql_check),
    )
