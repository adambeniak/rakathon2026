"""problem+json texts are Czech (#107); `type`, `status`, `code` and the body shape are unchanged."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_case_reader, get_handover_store
from app.api.errors import problem_title
from app.domain.errors import (
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthenticatedError,
)
from app.domain.events import TransitionError
from app.fhir.errors import FhirConflictError, FhirUnavailableError
from app.main import create_app
from app.settings import Settings
from tests.unit.api.fake_handover_store import FakeStore


class RaisingReader:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def list_cases(self) -> list[object]:
        raise self.error


def client_for(settings: Settings, error: Exception | None = None) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_case_reader] = lambda: RaisingReader(error or RuntimeError("unused"))
    app.dependency_overrides[get_handover_store] = FakeStore
    return TestClient(app)


def get_cases_failing_with(settings: Settings, error: Exception) -> httpx.Response:
    with client_for(settings, error) as client:
        return client.get("/api/cases")


@pytest.mark.parametrize(
    ("error", "status", "problem", "code", "title"),
    [
        (
            TransitionError("invalid_transition", "x"),
            409,
            "conflict",
            "invalid_transition",
            "Akce není v tomto stavu povolena",
        ),
        (TransitionError("forbidden_role", "x"), 409, "conflict", "forbidden_role", "Role nemá k akci oprávnění"),
        (TransitionError("guard_failed", "x"), 409, "conflict", "guard_failed", "Podmínky akce nejsou splněny"),
        (TransitionError("case_postponed", "x"), 409, "conflict", "case_postponed", "Případ je odložen"),
        (ConflictError("x"), 409, "conflict", None, "Záznam nelze v tomto stavu změnit"),
        (FhirConflictError("x", status_code=412), 409, "conflict", None, "Záznam nelze v tomto stavu změnit"),
        (ForbiddenError("x"), 403, "forbidden", None, "Přístup byl odepřen"),
        (UnauthenticatedError("x"), 401, "unauthenticated", None, "Uživatel není přihlášen"),
        (NotFoundError("case", "x"), 404, "not-found", None, "Záznam nebyl nalezen"),
        (InvalidInputError("x"), 422, "invalid-input", None, "Neplatný požadavek"),
        (ServiceUnavailableError("ai-unavailable", "x"), 503, "ai-unavailable", None, "Odpověď AI není dostupná"),
        (FhirUnavailableError("x"), 503, "storage-unavailable", None, "Úložiště není dostupné"),
    ],
)
def test_errors_keep_status_type_and_code_and_get_a_czech_title(
    settings: Settings, error: Exception, status: int, problem: str, code: str | None, title: str
) -> None:
    response = get_cases_failing_with(settings, error)

    body = response.json()
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert body["type"] == f"https://stafeta.example/problems/{problem}"
    assert body.get("code") == code
    assert body["title"] == title
    assert set(body) <= {"type", "title", "status", "detail", "instance", "request_id", "errors", "code"}


def test_a_missing_case_names_what_was_not_found_in_czech(settings: Settings) -> None:
    body = get_cases_failing_with(settings, NotFoundError("case", "rakathon-2026-xyz")).json()

    assert body["detail"] == "Nenalezeno: Případ 'rakathon-2026-xyz'"


def test_an_unknown_route_is_a_czech_404(settings: Settings) -> None:
    with client_for(settings) as client:
        response = client.get("/api/does-not-exist")

    body = response.json()
    assert response.status_code == 404
    assert body["type"] == "about:blank"
    assert body["title"] == "Záznam nebyl nalezen"
    assert body["detail"] == "Požadovaná adresa neexistuje."


def test_a_wrong_method_is_a_czech_405_and_keeps_the_allow_header(settings: Settings) -> None:
    with client_for(settings) as client:
        response = client.delete("/api/cases")

    body = response.json()
    assert response.status_code == 405
    assert response.headers["allow"]
    assert body["title"] == "Metoda není povolena"
    assert body["detail"] == "Tato metoda není pro danou adresu povolena."


def test_a_validation_error_is_a_czech_422_with_the_issues_listed(settings: Settings) -> None:
    with client_for(settings) as client:
        response = client.get("/api/cases/not%20a%20valid%20id!")

    body = response.json()
    assert response.status_code == 422
    assert body["type"].endswith("/validation")
    assert body["title"] == "Požadavek nemá platný tvar"
    assert body["detail"].startswith("Požadavek nemá platný tvar")
    assert body["errors"]
    assert {"loc", "msg", "type"} <= set(body["errors"][0])


@pytest.mark.parametrize(
    ("status", "problem", "code", "expected"),
    [
        (409, "conflict", "guard_failed", "Podmínky akce nejsou splněny"),  # the transition code wins
        (409, "conflict", None, "Záznam nelze v tomto stavu změnit"),  # then the problem type
        (409, "unknown-type", None, "Požadavek je v konfliktu se stavem záznamu"),  # then the status
        (502, None, None, "Chyba navazující služby"),
        (418, None, None, "I'm a Teapot"),  # a status without a Czech title keeps the English phrase
    ],
)
def test_title_resolution_order(status: int, problem: str | None, code: str | None, expected: str) -> None:
    assert problem_title(status, problem, code) == expected
