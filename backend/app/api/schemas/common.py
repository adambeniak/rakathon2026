"""Schemas shared by all endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Response descriptions in the contract start with the Czech problem `title` the API sends for the status
# (`app.api.errors.STATUS_TITLES`; a drift test keeps them in sync), followed by an English note for developers.
_PROBLEM_DESCRIPTIONS = {
    401: "Uživatel není přihlášen (actor not identified)",
    403: "Přístup byl odepřen (role not allowed)",
    404: "Záznam nebyl nalezen (not found)",
    409: "Požadavek je v konfliktu se stavem záznamu (not allowed in the current state; `code` names a refused "
    "transition)",
    413: "Soubor je příliš velký (upload too large)",
    415: "Nepodporovaný typ dokumentu (unsupported document type)",
    422: "Neplatný požadavek (request validation failed; issues in `errors`)",
    500: "Neočekávaná chyba serveru (unexpected server error)",
    502: "Chyba navazující služby (FHIR storage rejected the operation)",
    503: "Služba není dostupná (IRIS or the AI service unavailable)",
}


class ValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ProblemDetails(BaseModel):
    """RFC 7807 problem details (`application/problem+json`). `title` and `detail` are Czech texts for people;
    programs branch on `type`, `status`, `code` and `blocking_items`, never on the wording."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "https://stafeta.example/problems/not-found",
                    "title": "Záznam nebyl nalezen",
                    "status": 404,
                    "detail": "Nenalezeno: Případ 'rakathon-2026-xyz'",
                    "instance": "/api/cases/rakathon-2026-xyz",
                    "request_id": "4f1c2a9e0b7d4c55",
                },
                {
                    "type": "https://stafeta.example/problems/conflict",
                    "title": "Podmínky akce nejsou splněny",
                    "status": 409,
                    "detail": "Připravenost k MDT není splněna, chybí: performance_status",
                    "instance": "/api/cases/rakathon-2026-prochazkova/transitions",
                    "request_id": "9a2b7c1d3e4f5a60",
                    "code": "guard_failed",
                    "blocking_items": ["performance_status"],
                },
            ]
        }
    )

    type: str = Field("about:blank", description="URI identifying the problem type.")
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None
    errors: list[ValidationIssue] | None = Field(
        None, description="Present for 422 validation problems; `msg` is Czech, `type` is the stable machine key."
    )
    code: str | None = Field(
        None,
        description="Forbidden transition: invalid_transition | forbidden_role | guard_failed | case_postponed.",
    )
    blocking_items: list[str] | None = Field(
        None,
        description="Only with `code` = guard_failed of `mark_ready_mdt`: keys of the blocking readiness items that "
        "are not waived (e.g. `performance_status`), the same keys as the waiver `item`. English identifiers; the UI "
        "maps them to Czech labels. Absent for every other problem. Read this field, never parse `detail`.",
        examples=[["performance_status"]],
    )


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` for error statuses; the body is `ProblemDetails` sent as application/problem+json."""
    return {
        status: {"model": ProblemDetails, "description": f"{_PROBLEM_DESCRIPTIONS[status]} (application/problem+json)"}
        for status in statuses
    }
