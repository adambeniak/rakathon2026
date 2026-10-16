"""Typed errors of the FHIR adapter. Messages carry method, resource path and status only (no query strings,
which may contain identifiers such as RČ)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OutcomeIssue:
    severity: str
    code: str
    diagnostics: str | None = None
    expression: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, issue: dict[str, Any]) -> OutcomeIssue:
        details = issue.get("details") or {}
        diagnostics = issue.get("diagnostics") or details.get("text")
        return cls(
            severity=str(issue.get("severity", "error")),
            code=str(issue.get("code", "unknown")),
            diagnostics=str(diagnostics)[:300] if diagnostics else None,
            expression=tuple(str(e) for e in issue.get("expression", [])),
        )


class FhirError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, issues: Sequence[OutcomeIssue] = ()) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.issues = tuple(issues)


class FhirNotFoundError(FhirError):
    """404/410 from the server."""


class FhirValidationError(FhirError):
    """400/422: the server rejected the resource (see `issues`)."""


class FhirConflictError(FhirError):
    """409/412, or an identifier that matches more than one resource."""


class FhirAuthError(FhirError):
    """401/403: wrong IRIS_USER / IRIS_PASSWORD."""


class FhirUnavailableError(FhirError):
    """Transport error, timeout or 5xx: IRIS is down, starting or overloaded."""


class AuditWriteError(FhirError):
    """The clinical write succeeded but its AuditEvent could not be stored."""


def error_for_status(message: str, status_code: int, issues: Sequence[OutcomeIssue]) -> FhirError:
    if status_code in (401, 403):
        return FhirAuthError(message, status_code=status_code, issues=issues)
    if status_code in (404, 410):
        return FhirNotFoundError(message, status_code=status_code, issues=issues)
    if status_code in (409, 412):
        return FhirConflictError(message, status_code=status_code, issues=issues)
    if status_code in (400, 422):
        return FhirValidationError(message, status_code=status_code, issues=issues)
    if status_code >= 500:
        return FhirUnavailableError(message, status_code=status_code, issues=issues)
    return FhirError(message, status_code=status_code, issues=issues)
