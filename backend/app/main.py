"""FastAPI application factory (owner: P1).

Run: `uvicorn app.main:create_app --factory --port 8000`. Nothing connects to IRIS at startup: the backend starts
even when IRIS is down or still booting, and `/api/health` reports `degraded` until it answers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app import __version__
from app.api.errors import declare_problem_media_type, register_error_handlers
from app.api.middleware import (
    REQUEST_ID_HEADER,
    BodyLimitMiddleware,
    RequestContextMiddleware,
    UnhandledErrorMiddleware,
)
from app.api.routes import API_PREFIX, discover_routers
from app.api.routes.referrals import MAX_ATTACHMENTS
from app.iris.db import IrisPool
from app.logging_config import configure_logging
from app.security.actor import DEMO_ROLE_HEADER
from app.settings import Settings, get_settings

# IRIS community edition counts web sessions too: keep outbound HTTP connections low.
HTTP_LIMITS = httpx.Limits(max_connections=4, max_keepalive_connections=4)

OPENAPI_TAGS = [
    {"name": "health", "description": "Backend and IRIS status."},
    {"name": "cases", "description": "Shared oncology case: state, baton holder, documents."},
    {"name": "directory", "description": "Workplaces (KOC) and their coordinators."},
    {"name": "referrals", "description": "GP referral: prefill from the letter, confirm, create the case."},
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
    # The last added middleware is the outermost: RequestContext → CORS → UnhandledError → routes.
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(
        BodyLimitMiddleware, max_file_bytes=settings.upload_max_bytes, max_files_referral=MAX_ATTACHMENTS + 1
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", DEMO_ROLE_HEADER, REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestContextMiddleware)
    for router in discover_routers():
        app.include_router(router, prefix=API_PREFIX)
    _declare_problem_responses(app)
    return app


def _declare_problem_responses(app: FastAPI) -> None:
    """Generate the OpenAPI document once, then declare ProblemDetails bodies as application/problem+json."""
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = declare_problem_media_type(generate())
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
