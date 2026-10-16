"""Request context: request id, one access-log line per request, and a last-resort 500 handler.

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

log = structlog.get_logger("app.http")

_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware:
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
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            frame = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
            log.error(
                "unhandled_error",
                error_type=type(exc).__name__,
                location=f"{frame.filename}:{frame.lineno}" if frame else None,
            )
            if response_started:
                raise
            status = 500
            response = problem_response(
                500,
                problem="internal",
                detail="Neočekávaná chyba serveru.",
                instance=scope.get("path"),
                request_id=request_id,
            )
            await response(scope, receive, send_with_request_id)
        finally:
            route = scope.get("route")
            log.info(
                "http_request",
                method=scope.get("method"),
                route=getattr(route, "path", "<unmatched>"),
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            structlog.contextvars.unbind_contextvars("request_id")
