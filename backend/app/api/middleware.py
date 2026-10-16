"""Request context (request id + one access-log line per request) and a last-resort 500 handler.

Order in `app.main` (outer → inner): RequestContextMiddleware → CORSMiddleware → UnhandledErrorMiddleware → app, so
the fallback 500 still gets CORS headers and every request — preflights included — gets an id and a log line.
Logs the route template (`/api/cases/{case_id}`), never the raw path or query string. Unhandled exceptions are
logged by type and code location only (exception messages may contain PHI) and answered with problem+json.
"""

from __future__ import annotations

import re
import time
import traceback
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import problem_response
from app.api.routes import API_PREFIX

log = structlog.get_logger("app.http")

_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware:
    """Outermost: request id (incoming `X-Request-ID` or a new one) and the access-log line."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers", [])).get(REQUEST_ID_HEADER.lower().encode(), b"").decode("latin-1")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            # Included routers keep paths relative to their mount prefix: add it back for API routes.
            route = scope.get("route")
            prefix = API_PREFIX if str(scope.get("path", "")).startswith(f"{API_PREFIX}/") else ""
            log.info(
                "http_request",
                method=scope.get("method"),
                route=f"{prefix}{route.path}" if route is not None else "<unmatched>",
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            structlog.contextvars.unbind_contextvars("request_id")


class UnhandledErrorMiddleware:
    """Innermost: turns any unhandled exception into a 500 problem+json (inside CORS, so browsers can read it)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            frame = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
            log.error(
                "unhandled_error",
                error_type=type(exc).__name__,
                location=f"{frame.filename}:{frame.lineno}" if frame else None,
            )
            if response_started:
                raise
            response = problem_response(
                500,
                problem="internal",
                detail="Neočekávaná chyba serveru.",
                instance=scope.get("path"),
                request_id=scope.get("state", {}).get("request_id"),
            )
            await response(scope, receive, send)
