"""Schemas shared by all endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
