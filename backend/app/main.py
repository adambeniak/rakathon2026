"""FastAPI application factory (owner: P1).

Run: `uvicorn app.main:create_app --factory --port 8000`. Nothing connects to IRIS at startup: the backend starts
even when IRIS is down or still booting, and `/api/health` reports `degraded` until it answers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app import __version__
from app.api.errors import register_error_handlers
from app.api.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.api.routes import discover_routers
from app.iris.db import IrisPool
from app.logging_config import configure_logging
from app.settings import Settings, get_settings

# IRIS community edition counts web sessions too: keep outbound HTTP connections low.
HTTP_LIMITS = httpx.Limits(max_connections=4, max_keepalive_connections=4)

OPENAPI_TAGS = [
    {"name": "health", "description": "Backend and IRIS status."},
    {"name": "cases", "description": "Shared oncology case: state, baton holder, documents."},
]


def operation_id(route: APIRoute) -> str:
    """Stable operationIds for the generated TypeScript client, e.g. 'cases-list_cases'."""
    return f"{route.tags[0]}-{route.name}" if route.tags else route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        timeout = httpx.Timeout(settings.http_timeout_s, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, limits=HTTP_LIMITS) as http:
            pool = IrisPool.from_settings(settings)
            app.state.http = http
            app.state.iris_pool = pool
            try:
                yield
            finally:
                pool.close_all()

    app = FastAPI(
        title="Štafeta API",
        version=__version__,
        description="Shared oncology patient case (Rakathon 2026, VZP challenge). Fictitious data only.",
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS,
        generate_unique_id_function=operation_id,
    )
    app.state.settings = settings
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestContextMiddleware)
    for router in discover_routers():
        app.include_router(router, prefix="/api")
    return app
