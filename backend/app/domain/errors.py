"""Domain exceptions. `app.api.errors` maps them to RFC 7807 problem+json responses."""

from __future__ import annotations


class DomainError(Exception):
    """Base class. Messages must not contain PHI: they may end up in logs and API responses."""


class NotFoundError(DomainError):
    def __init__(self, kind: str, identifier: str) -> None:
        super().__init__(f"{kind} '{identifier}' not found")
        self.kind = kind
        self.identifier = identifier


class ConflictError(DomainError):
    """The request is valid but not allowed in the current state (e.g. a forbidden case transition, #2)."""


class InvalidInputError(DomainError):
    """The request is well-formed but semantically invalid."""
