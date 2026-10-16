"""RFC 7807 problem+json responses for every error (never a stack trace, never PHI)."""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.schemas.common import ProblemDetails, ValidationIssue
from app.domain.errors import ConflictError, DomainError, InvalidInputError, NotFoundError
from app.fhir.errors import (
    AuditWriteError,
    FhirAuthError,
    FhirError,
    FhirNotFoundError,
    FhirUnavailableError,
    FhirValidationError,
)

PROBLEM_JSON = "application/problem+json"
PROBLEM_BASE = "https://stafeta.example/problems/"

log = structlog.get_logger(__name__)


def problem_response(
    status: int,
    *,
    problem: str | None = None,
    detail: str | None = None,
    instance: str | None = None,
    request_id: str | None = None,
    errors: list[ValidationIssue] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ProblemDetails(
        type=f"{PROBLEM_BASE}{problem}" if problem else "about:blank",
        title=HTTPStatus(status).phrase,
        status=status,
        detail=detail,
        instance=instance,
        request_id=request_id,
        errors=errors,
    )
    return JSONResponse(
        body.model_dump(exclude_none=True), status_code=status, media_type=PROBLEM_JSON, headers=headers
    )


def declare_problem_media_type(openapi: dict[str, Any]) -> dict[str, Any]:
    """FastAPI documents every `responses={...: {"model": ...}}` as application/json; ProblemDetails bodies are sent
    as application/problem+json, so declare them under that media type in the contract."""
    ref = "#/components/schemas/ProblemDetails"
    for path_item in openapi.get("paths", {}).values():
        for operation in path_item.values():
            for response in operation.get("responses", {}).values():
                content = response.get("content", {})
                body = content.get("application/json")
                if body is not None and body.get("schema", {}).get("$ref") == ref:
                    content[PROBLEM_JSON] = content.pop("application/json")
    return openapi


def _request_id(request: Request) -> str | None:
    value = request.scope.get("state", {}).get("request_id")
    return str(value) if value else None


def _domain_status(exc: DomainError) -> tuple[int, str]:
    if isinstance(exc, NotFoundError):
        return 404, "not-found"
    if isinstance(exc, ConflictError):
        return 409, "conflict"
    if isinstance(exc, InvalidInputError):
        return 422, "invalid-input"
    return 400, "domain-error"


def _fhir_status(exc: FhirError) -> tuple[int, str, str]:
    """Storage errors are upstream problems: do not echo FHIR details to clients."""
    if isinstance(exc, FhirUnavailableError):
        return 503, "storage-unavailable", "Úložiště FHIR (IRIS) není dostupné."
    if isinstance(exc, AuditWriteError):
        return 502, "audit-failed", "Záznam auditu se nepodařilo uložit."
    if isinstance(exc, FhirAuthError):
        return 502, "storage-auth", "Backend se nemůže přihlásit k úložišti FHIR."
    if isinstance(exc, FhirNotFoundError):
        return 404, "not-found", "Záznam v úložišti FHIR neexistuje."
    if isinstance(exc, FhirValidationError):
        return 502, "storage-rejected", "Úložiště FHIR odmítlo zápis."
    return 502, "storage-error", "Chyba úložiště FHIR."


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status, problem = _domain_status(exc)
        return problem_response(
            status, problem=problem, detail=str(exc), instance=request.url.path, request_id=_request_id(request)
        )

    @app.exception_handler(FhirError)
    async def handle_fhir_error(request: Request, exc: FhirError) -> JSONResponse:
        status, problem, detail = _fhir_status(exc)
        log.error("fhir_error", error_type=type(exc).__name__, upstream_status=exc.status_code)
        return problem_response(
            status, problem=problem, detail=detail, instance=request.url.path, request_id=_request_id(request)
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo the submitted input back (it may contain PHI): location, message and type only.
        issues = [
            ValidationIssue(loc=list(err.get("loc", ())), msg=str(err.get("msg", "")), type=str(err.get("type", "")))
            for err in exc.errors()
        ]
        return problem_response(
            422,
            problem="validation",
            detail="Request validation failed.",
            instance=request.url.path,
            request_id=_request_id(request),
            errors=issues,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else None
        return problem_response(
            exc.status_code,
            detail=detail,
            instance=request.url.path,
            request_id=_request_id(request),
            headers=exc.headers,  # e.g. `Allow` on 405
        )
