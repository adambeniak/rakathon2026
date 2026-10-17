"""problem+json texts are Czech (#107); `type`, `status`, `code` and the body shape are unchanged."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import AwareDatetime, BaseModel, Field, ValidationError, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import get_case_reader, get_directory_provider, get_handover_store
from app.api.errors import STATUS_TITLES, _fhir_status, problem_title, validation_message
from app.api.schemas.common import _PROBLEM_DESCRIPTIONS, ProblemDetails
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
from tests.unit.api.test_api import DemoDirectory


class RaisingReader:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def list_cases(self) -> list[object]:
        raise self.error


def client_for(settings: Settings, error: Exception | None = None) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_case_reader] = lambda: RaisingReader(error or RuntimeError("unused"))
    app.dependency_overrides[get_directory_provider] = DemoDirectory  # the shared current_actor
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
        (TransitionError("forbidden_role", "x"), 403, "forbidden", "forbidden_role", "Přístup byl odepřen"),  # #136
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
    assert "blocking_items" not in body  # only a structured guard result carries it (#140)


def test_a_structured_guard_result_carries_blocking_items_next_to_the_unchanged_sentence(settings: Settings) -> None:
    detail = "Připravenost k MDT není splněna, chybí: performance_status, histology"
    error = TransitionError("guard_failed", detail, ("performance_status", "histology"))

    body = get_cases_failing_with(settings, error).json()

    assert body["code"] == "guard_failed"
    assert body["detail"] == detail
    assert body["blocking_items"] == ["performance_status", "histology"]


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


def test_a_storage_conflict_has_one_czech_detail() -> None:
    assert _fhir_status(FhirConflictError("x", status_code=412)) == (
        409,
        "conflict",
        "Záznam byl mezitím změněn, načtěte jej znovu.",
    )


@pytest.mark.parametrize("status", sorted(_PROBLEM_DESCRIPTIONS))
def test_contract_response_descriptions_start_with_the_czech_title_the_api_sends(status: int) -> None:
    # #116: the documented texts must not drift from the runtime ones again.
    assert _PROBLEM_DESCRIPTIONS[status].startswith(STATUS_TITLES[status])


def test_the_contract_example_uses_the_runtime_texts(settings: Settings) -> None:
    example = ProblemDetails.model_json_schema()["examples"][0]
    body = get_cases_failing_with(settings, NotFoundError("case", "rakathon-2026-xyz")).json()

    assert example["title"] == body["title"]
    assert example["detail"] == body["detail"]


class _Colour(StrEnum):
    RED = "red"
    BLUE = "blue"


class _Body(BaseModel):
    name: str = Field(min_length=2, max_length=3, pattern="^[a-z]+$")
    colour: _Colour
    kind: Literal["a", "b"]
    count: int = Field(ge=1)
    day: date
    at: AwareDatetime
    tags: list[str] = Field(max_length=1)
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        raise ValueError("Důvod musí být vyplněn.")


def _messages(data: dict[str, object]) -> dict[str, str]:
    with pytest.raises(ValidationError) as caught:
        _Body.model_validate(data)
    return {str(err["loc"][0]): validation_message(err) for err in caught.value.errors()}  # type: ignore[arg-type]


def test_common_validation_errors_get_czech_messages() -> None:
    messages = _messages(
        {
            "name": "x",
            "colour": "green",
            "kind": "c",
            "count": "many",
            "day": "21.10.2026",
            "at": "2026-10-21T08:00:00",
            "tags": ["a", "b"],
            "reason": "x",
        }
    )

    assert messages == {
        "name": "Text je příliš krátký (minimální počet znaků: 2).",
        "colour": "Hodnota musí být jedna z možností: 'red' nebo 'blue'.",
        "kind": "Hodnota musí být jedna z možností: 'a' nebo 'b'.",
        "count": "Hodnota musí být celé číslo.",
        "day": "Hodnota musí být datum ve formátu RRRR-MM-DD.",
        "at": "Datum a čas musí obsahovat časové pásmo (např. +02:00).",
        "tags": "Příliš mnoho položek (maximum: 1).",
        "reason": "Důvod musí být vyplněn.",  # the validator's own text, without Pydantic's "Value error, "
    }


def test_more_validation_errors_get_czech_messages() -> None:
    assert _messages({"name": "abcd", "count": 0})["name"] == "Text je příliš dlouhý (maximální počet znaků: 3)."
    assert _messages({"name": "AB"})["name"] == "Hodnota nemá povolený formát."
    assert _messages({"count": 0})["count"] == "Hodnota musí být alespoň 1."
    assert _messages({})["colour"] == "Povinná hodnota chybí."


def test_an_unknown_validation_type_keeps_the_original_message() -> None:
    error = {"type": "something_new", "msg": "Original text", "loc": ("body",)}

    assert validation_message(error) == "Original text"


def test_a_template_whose_placeholder_is_missing_keeps_the_original_message() -> None:
    error = {"type": "string_too_short", "msg": "String should have at least 2 characters", "ctx": {}}

    assert validation_message(error) == "String should have at least 2 characters"


def test_a_422_lists_czech_messages_with_the_stable_type(settings: Settings) -> None:
    with client_for(settings) as client:
        body = client.get("/api/cases/not%20a%20valid%20id!").json()

    assert body["errors"][0]["type"] == "string_pattern_mismatch"
    assert body["errors"][0]["msg"] == "Hodnota nemá povolený formát."


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (400, "Požadavek nelze zpracovat."),
        (401, "Pro tuto akci je nutné přihlášení."),
        (403, "K této akci nemáte oprávnění."),
        (503, "Služba je dočasně nedostupná."),
        (418, None),  # no Czech detail known: omitted rather than English
    ],
)
def test_framework_default_details_are_czech_or_omitted(settings: Settings, status: int, detail: str | None) -> None:
    app = create_app(settings)

    async def fail() -> None:
        raise StarletteHTTPException(status)

    app.add_api_route("/api/test-http-exception", fail)
    with TestClient(app) as client:
        body = client.get("/api/test-http-exception").json()

    assert body["status"] == status
    assert body.get("detail") == detail
