"""Schemas shared by all endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_PROBLEM_DESCRIPTIONS = {
    401: "Actor not identified",
    403: "Role not allowed",
    404: "Not found",
    409: "Not allowed in the current state",
    413: "Upload too large",
    415: "Unsupported document type",
    422: "Request validation failed",
    500: "Unexpected server error",
    502: "FHIR storage rejected the operation",
    503: "IRIS or the AI service unavailable",
}


class ValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ProblemDetails(BaseModel):
    """RFC 7807 problem details (`application/problem+json`). The UI maps `type` to a Czech message."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "https://stafeta.example/problems/not-found",
                    "title": "Not Found",
                    "status": 404,
                    "detail": "case 'rakathon-2026-xyz' not found",
                    "instance": "/api/cases/rakathon-2026-xyz",
                    "request_id": "4f1c2a9e0b7d4c55",
                }
            ]
        }
    )

    type: str = Field("about:blank", description="URI identifying the problem type.")
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None
    errors: list[ValidationIssue] | None = Field(None, description="Present for 422 validation problems.")
    code: str | None = Field(
        None,
        description="Forbidden transition: invalid_transition | forbidden_role | guard_failed | case_postponed.",
    )


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` for error statuses; the body is `ProblemDetails` sent as application/problem+json."""
    return {
        status: {"model": ProblemDetails, "description": f"{_PROBLEM_DESCRIPTIONS[status]} (application/problem+json)"}
        for status in statuses
    }
