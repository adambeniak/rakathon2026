"""RFC 7807 problem+json responses for every error (never a stack trace, never PHI)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.schemas.common import ProblemDetails, ValidationIssue
from app.domain.errors import (
    ConflictError,
    DomainError,
    ExtractionUnavailableError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    UnauthenticatedError,
    UnsupportedMediaError,
)
from app.domain.events import TransitionError
from app.fhir.errors import (
    AuditWriteError,
    FhirAuthError,
    FhirConflictError,
    FhirError,
    FhirNotFoundError,
    FhirUnavailableError,
    FhirValidationError,
)

PROBLEM_JSON = "application/problem+json"
PROBLEM_BASE = "https://stafeta.example/problems/"

log = structlog.get_logger(__name__)

# Czech `title` of a problem (RFC 7807: short, the same for every occurrence of the type). Neutral system wording only.
# Resolved most specific first: transition `code`, then problem `type`, then HTTP status, then the English phrase.
CODE_TITLES: Mapping[str, str] = {
    "invalid_transition": "Akce není v tomto stavu povolena",
    "forbidden_role": "Role nemá k akci oprávnění",
    "guard_failed": "Podmínky akce nejsou splněny",
    "case_postponed": "Případ je odložen",
}
PROBLEM_TITLES: Mapping[str, str] = {
    "not-found": "Záznam nebyl nalezen",
    "unauthenticated": "Uživatel není přihlášen",
    "forbidden": "Přístup byl odepřen",
    "invalid-input": "Neplatný požadavek",
    "validation": "Požadavek nemá platný tvar",
    "conflict": "Záznam nelze v tomto stavu změnit",
    "payload-too-large": "Soubor je příliš velký",
    "unsupported-media": "Nepodporovaný typ dokumentu",
    "extraction-unavailable": "Dokument se nepodařilo analyzovat",
    "search-unavailable": "Vyhledávání není dostupné",
    "ai-unavailable": "Odpověď AI není dostupná",
    "ai-invalid": "Odpověď AI nemá očekávaný tvar",
    "mail-unavailable": "E-mail se nepodařilo odeslat",
    "storage-unavailable": "Úložiště není dostupné",
    "storage-auth": "Úložiště odmítlo přihlášení backendu",
    "storage-rejected": "Úložiště odmítlo zápis",
    "storage-error": "Chyba úložiště",
    "audit-failed": "Záznam auditu se nepodařilo uložit",
    "internal": "Neočekávaná chyba serveru",
}
STATUS_TITLES: Mapping[int, str] = {
    400: "Neplatný požadavek",
    401: "Uživatel není přihlášen",
    403: "Přístup byl odepřen",
    404: "Záznam nebyl nalezen",
    405: "Metoda není povolena",
    409: "Požadavek je v konfliktu se stavem záznamu",
    413: "Soubor je příliš velký",
    415: "Nepodporovaný typ dokumentu",
    422: "Neplatný požadavek",
    500: "Neočekávaná chyba serveru",
    502: "Chyba navazující služby",
    503: "Služba není dostupná",
}
# Detail of the framework's own errors (an unknown route, a wrong method): Starlette words them in English.
STATUS_DETAILS: Mapping[int, str] = {
    400: "Požadavek nelze zpracovat.",
    401: "Pro tuto akci je nutné přihlášení.",
    403: "K této akci nemáte oprávnění.",
    404: "Požadovaná adresa neexistuje.",
    405: "Tato metoda není pro danou adresu povolena.",
    413: "Požadavek je příliš velký.",
    415: "Typ obsahu požadavku není podporován.",
    500: "Na serveru došlo k neočekávané chybě.",
    503: "Služba je dočasně nedostupná.",
}

# Czech `errors[].msg` of a 422, keyed by the Pydantic error `type` (which stays the stable machine key).
# Placeholders come from the error's `ctx` (schema constants such as min_length); the submitted input is never used.
# A type not listed here keeps Pydantic's English message.
_DATE = "Hodnota musí být datum ve formátu RRRR-MM-DD."
_DATETIME = "Hodnota musí být datum a čas ve formátu ISO 8601 (např. 2026-10-21T08:00:00+02:00)."
_CHOICE = "Hodnota není mezi povolenými možnostmi: {expected}."
VALIDATION_MESSAGES: Mapping[str, str] = {
    "missing": "Povinná hodnota chybí.",
    "extra_forbidden": "Tato položka není v požadavku povolena.",
    "string_type": "Hodnota musí být text.",
    "string_too_short": "Text je příliš krátký (minimální délka: {min_length}).",
    "string_too_long": "Text je příliš dlouhý (maximální délka: {max_length}).",
    "string_pattern_mismatch": "Hodnota nemá povolený formát.",
    "too_short": "Příliš málo položek (minimum: {min_length}).",
    "too_long": "Příliš mnoho položek (maximum: {max_length}).",
    "int_type": "Hodnota musí být celé číslo.",
    "int_parsing": "Hodnota musí být celé číslo.",
    "int_from_float": "Hodnota musí být celé číslo.",
    "float_type": "Hodnota musí být číslo.",
    "float_parsing": "Hodnota musí být číslo.",
    "bool_type": "Hodnota musí být true nebo false.",
    "bool_parsing": "Hodnota musí být true nebo false.",
    "greater_than": "Hodnota musí být větší než {gt}.",
    "greater_than_equal": "Hodnota musí být alespoň {ge}.",
    "less_than": "Hodnota musí být menší než {lt}.",
    "less_than_equal": "Hodnota může být nejvýše {le}.",
    "enum": _CHOICE,
    "literal_error": _CHOICE,
    "date_type": _DATE,
    "date_parsing": _DATE,
    "date_from_datetime_parsing": _DATE,
    "date_from_datetime_inexact": _DATE,
    "datetime_type": _DATETIME,
    "datetime_parsing": _DATETIME,
    "datetime_from_date_parsing": _DATETIME,
    "timezone_aware": "Datum a čas musí obsahovat časové pásmo (např. +02:00).",
    "list_type": "Hodnota musí být seznam.",
    "dict_type": "Hodnota musí být objekt.",
    "model_type": "Hodnota musí být objekt.",
    "model_attributes_type": "Hodnota musí být objekt.",
    "json_invalid": "Tělo požadavku není platný JSON.",
}


def problem_title(status: int, problem: str | None = None, code: str | None = None) -> str:
    return (
        CODE_TITLES.get(code or "")
        or PROBLEM_TITLES.get(problem or "")
        or STATUS_TITLES.get(status)
        or HTTPStatus(status).phrase
    )


def problem_response(
    status: int,
    *,
    problem: str | None = None,
    detail: str | None = None,
    instance: str | None = None,
    request_id: str | None = None,
    errors: list[ValidationIssue] | None = None,
    code: str | None = None,
    blocking_items: Sequence[str] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ProblemDetails(
        type=f"{PROBLEM_BASE}{problem}" if problem else "about:blank",
        title=problem_title(status, problem, code),
        status=status,
        detail=detail,
        instance=instance,
        request_id=request_id,
        errors=errors,
        code=code,
        blocking_items=list(blocking_items) if blocking_items is not None else None,
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
    if isinstance(exc, UnauthenticatedError):
        return 401, "unauthenticated"
    if isinstance(exc, ForbiddenError):
        return 403, "forbidden"
    if isinstance(exc, ExtractionUnavailableError):
        return 503, "extraction-unavailable"
    if isinstance(exc, ServiceUnavailableError):
        return 503, exc.problem
    if isinstance(exc, PayloadTooLargeError):
        return 413, "payload-too-large"
    if isinstance(exc, UnsupportedMediaError):
        return 415, "unsupported-media"
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
    if isinstance(exc, FhirConflictError):
        return 409, "conflict", "Záznam byl mezitím změněn, načtěte jej znovu."
    if isinstance(exc, FhirAuthError):
        return 502, "storage-auth", "Backend se nemůže přihlásit k úložišti FHIR."
    if isinstance(exc, FhirNotFoundError):
        return 404, "not-found", "Záznam v úložišti FHIR neexistuje."
    if isinstance(exc, FhirValidationError):
        return 502, "storage-rejected", "Úložiště FHIR odmítlo zápis."
    return 502, "storage-error", "Chyba úložiště FHIR."


def validation_message(error: Mapping[str, Any]) -> str:
    """Czech `msg` of one Pydantic error; Pydantic's own text when the type is unknown or a placeholder is missing."""
    kind = str(error.get("type", ""))
    original = str(error.get("msg", ""))
    ctx = error.get("ctx") or {}
    if kind in {"value_error", "assertion_error"}:
        # Our validators word the reason themselves (in Czech); Pydantic only prefixes it with "Value error, ".
        reason = ctx.get("error")
        return str(reason) if reason is not None and str(reason) else original
    template = VALIDATION_MESSAGES.get(kind)
    if template is None:
        return original
    values = {key: str(value) for key, value in ctx.items()}
    if "expected" in values:
        values["expected"] = values["expected"].replace(" or ", " nebo ")
    try:
        return template.format_map(values)
    except (KeyError, IndexError, ValueError):
        return original


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status, problem = _domain_status(exc)
        transition = exc if isinstance(exc, TransitionError) else None
        return problem_response(
            status,
            problem=problem,
            detail=transition.detail if transition else str(exc),
            instance=request.url.path,
            request_id=_request_id(request),
            code=transition.code if transition else None,
            # Structured guard result (`mark_ready_mdt`): the UI reads the keys, never the Czech `detail` sentence.
            blocking_items=transition.blocking_items if transition else None,
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
            ValidationIssue(loc=list(err.get("loc", ())), msg=validation_message(err), type=str(err.get("type", "")))
            for err in exc.errors()
        ]
        return problem_response(
            422,
            problem="validation",
            detail="Požadavek nemá platný tvar; podrobnosti jsou v poli errors.",
            instance=request.url.path,
            request_id=_request_id(request),
            errors=issues,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Starlette's default detail is the English status phrase (mapped to Czech, or omitted); a custom detail passes
        # through unchanged.
        detail: str | None = exc.detail if isinstance(exc.detail, str) else None
        if detail == HTTPStatus(exc.status_code).phrase:
            detail = STATUS_DETAILS.get(exc.status_code)
        return problem_response(
            exc.status_code,
            detail=detail,
            instance=request.url.path,
            request_id=_request_id(request),
            headers=exc.headers,  # e.g. `Allow` on 405
        )
