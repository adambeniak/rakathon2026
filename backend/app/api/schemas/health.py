"""Health check schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CheckResult(BaseModel):
    ok: bool
    latency_ms: float
    detail: str | None = Field(None, description="Error class and status if the check failed (no secrets).")


class HealthChecks(BaseModel):
    fhir: CheckResult = Field(description="IRIS FHIR endpoint: GET /metadata.")
    iris_sql: CheckResult = Field(description="IRIS SQL over the DB-API pool: SELECT 1.")


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "version": "0.1.0",
                    "checks": {
                        "fhir": {"ok": True, "latency_ms": 84.2},
                        "iris_sql": {"ok": True, "latency_ms": 31.7},
                    },
                }
            ]
        }
    )

    status: Literal["ok", "degraded"]
    version: str
    checks: HealthChecks
