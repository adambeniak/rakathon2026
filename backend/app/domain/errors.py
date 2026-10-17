"""Domain exceptions. `app.api.errors` maps them to RFC 7807 problem+json responses."""

from __future__ import annotations


class DomainError(Exception):
    """Base class. Messages must not contain PHI: they may end up in logs and API responses."""


# Czech name of what was not found, by the `kind` the caller passes (an unknown kind is shown as given).
KIND_NAMES = {
    "case": "Případ",
    "task": "Úkol",
    "plan": "Sada vyšetření",
    "request": "Požadavek na podklady",
    "route": "Adresa",
    "MDT conclusion": "Závěr MDT",
    "referral letter content": "Text žádosti o převzetí",
}


class NotFoundError(DomainError):
    def __init__(self, kind: str, identifier: str) -> None:
        super().__init__(f"Nenalezeno: {KIND_NAMES.get(kind, kind)} '{identifier}'")
        self.kind = kind
        self.identifier = identifier


class ConflictError(DomainError):
    """The request is valid but not allowed in the current state (e.g. a forbidden case transition, #2)."""


class InvalidInputError(DomainError):
    """The request is well-formed but semantically invalid."""


class UnauthenticatedError(DomainError):
    """The actor could not be identified (missing or unknown `X-Demo-Role`, or demo mode off)."""


class ForbiddenError(DomainError):
    """The identified actor's role may not perform this operation."""


class PayloadTooLargeError(DomainError):
    """An upload exceeds the size limit."""


class UnsupportedMediaError(DomainError):
    """An upload is not a DOCX or PDF document (checked by content, not by the declared type)."""


class ExtractionUnavailableError(DomainError):
    """The document could not be analysed now (no recorded response in cache-only mode, or the model is unreachable)."""


class ServiceUnavailableError(DomainError):
    """A dependency of the request is unavailable (AI answer, IRIS search). Mapped to 503 with `problem`."""

    def __init__(self, problem: str, message: str) -> None:
        super().__init__(message)
        self.problem = problem
