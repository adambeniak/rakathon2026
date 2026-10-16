from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_case_reader, get_fhir_client, get_iris_pool
from app.domain.case import Case, CaseState
from app.domain.common import PartyRef, Role
from app.domain.document import SourceDocument
from app.domain.errors import NotFoundError
from app.domain.patient import Patient, Sex
from app.export_openapi import stable_json
from app.fhir.cases import CaseDetailView, CaseOverview
from app.fhir.errors import FhirAuthError, FhirUnavailableError
from app.main import create_app
from app.settings import PRAGUE, Settings

CASE = Case(
    id="rakathon-2026-prochazkova",
    patient=Patient(
        given="Alena",
        family="Procházková",
        sex=Sex.FEMALE,
        birth_date=date(1963, 7, 22),
        birth_number="635722/1013",
        insurer_code="211",
    ),
    state=CaseState.PRIPRAVENO_MDT,
    baton_holder=PartyRef(id="hruby-pavel@koc2-nemocnice-lipova", display="MDT GIT", role=Role.KOC_PHYSICIAN),
    next_deadline=datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE),
    opened_at=datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE),
)
DOCUMENT = SourceDocument(
    doc_id="07_PL_zadost_KOC2_2026-10-02",
    title="PL – žádost",
    type_code="57133-1",
    authored_at=date(2026, 10, 2),
    received_at=datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE),
)


class FakeReader:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def list_cases(self) -> list[CaseOverview]:
        if self.error:
            raise self.error
        return [CaseOverview(case=CASE, document_count=13)]

    async def get_case(self, case_id: str) -> CaseDetailView:
        if self.error:
            raise self.error
        if case_id != CASE.id:
            raise NotFoundError("case", case_id)
        return CaseDetailView(case=CASE, documents=[DOCUMENT])


class FakeFhir:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def capabilities(self) -> dict[str, str]:
        if self.error:
            raise self.error
        return {"resourceType": "CapabilityStatement"}


class FakePool:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    def ping(self) -> None:
        if not self.ok:
            raise ConnectionError("down")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    app.dependency_overrides[get_case_reader] = lambda: FakeReader()
    app.dependency_overrides[get_fhir_client] = lambda: FakeFhir()
    app.dependency_overrides[get_iris_pool] = lambda: FakePool()
    with TestClient(app) as test_client:
        yield test_client


def test_routers_are_auto_discovered(app: FastAPI) -> None:
    assert {"/api/health", "/api/cases", "/api/cases/{case_id}"} <= set(app.openapi()["paths"])


def test_health_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["fhir"]["ok"]
    assert body["checks"]["iris_sql"]["ok"]
    assert response.headers["X-Request-ID"]


def test_health_degraded_returns_503_with_reasons(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_fhir_client] = lambda: FakeFhir(FhirAuthError("x", status_code=401))
    app.dependency_overrides[get_iris_pool] = lambda: FakePool(ok=False)

    response = client.get("/api/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["fhir"]["detail"] == "FhirAuthError (HTTP 401)"
    assert body["checks"]["iris_sql"]["detail"] == "ConnectionError"


def test_list_cases(client: TestClient) -> None:
    response = client.get("/api/cases")

    assert response.status_code == 200
    [case] = response.json()
    assert case["id"] == "rakathon-2026-prochazkova"
    assert case["patient"]["display_name"] == "Alena Procházková"
    assert case["patient"]["age_years"] == 63
    assert case["state"] == "pripraveno_mdt"
    assert case["baton_holder"]["role"] == "koc_physician"
    assert case["document_count"] == 13
    assert case["missing_count"] is None
    assert case["conflict_count"] is None
    assert "birth_number" not in case["patient"]


def test_case_detail_lists_documents(client: TestClient) -> None:
    response = client.get("/api/cases/rakathon-2026-prochazkova")

    assert response.status_code == 200
    body = response.json()
    assert body["document_count"] == 1
    assert body["documents"][0]["doc_id"] == "07_PL_zadost_KOC2_2026-10-02"
    assert body["documents"][0]["received_at"] == "2026-10-02T09:30:00+02:00"


def test_unknown_case_is_problem_json(client: TestClient) -> None:
    response = client.get("/api/cases/unknown-case", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"] == "https://stafeta.example/problems/not-found"
    assert body["request_id"] == "req-123"


def test_invalid_case_id_is_422_without_echoing_input(client: TestClient) -> None:
    response = client.get("/api/cases/bad id with spaces")

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "https://stafeta.example/problems/validation"
    assert body["errors"][0]["loc"] == ["path", "case_id"]
    assert all("input" not in error for error in body["errors"])


def test_storage_unavailable_is_503(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_case_reader] = lambda: FakeReader(FhirUnavailableError("GET Task: ConnectError"))

    response = client.get("/api/cases")

    assert response.status_code == 503
    assert response.json()["type"] == "https://stafeta.example/problems/storage-unavailable"


def test_unhandled_error_is_500_problem_without_details(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_case_reader] = lambda: FakeReader(RuntimeError("Alena Procházková 635722/1013"))

    response = client.get("/api/cases")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert "Alena" not in response.text
    assert "Traceback" not in response.text


def test_openapi_is_stable_and_has_operation_ids(settings: Settings) -> None:
    first = stable_json(create_app(settings).openapi())
    second = stable_json(create_app(settings).openapi())

    assert first == second
    assert '"operationId": "cases-list_cases"' in first
    assert '"operationId": "cases-get_case"' in first
    assert '"operationId": "health-health"' in first


def test_access_log_has_full_route_template_and_no_ids(settings: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    app = create_app(settings.model_copy(update={"log_level": "INFO"}))
    app.dependency_overrides[get_case_reader] = lambda: FakeReader()
    with TestClient(app) as test_client:
        test_client.get("/api/cases/rakathon-2026-prochazkova")

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if '"http_request"' in line]
    assert lines[-1]["route"] == "/api/cases/{case_id}"
    assert "rakathon-2026-prochazkova" not in json.dumps(lines[-1])


def test_405_problem_keeps_allow_header(client: TestClient) -> None:
    response = client.post("/api/cases")

    assert response.status_code == 405
    assert response.headers["content-type"] == "application/problem+json"
    assert "GET" in response.headers["allow"]


def test_openapi_declares_problem_json_for_errors(app: FastAPI) -> None:
    responses = app.openapi()["paths"]["/api/cases/{case_id}"]["get"]["responses"]

    assert list(responses["404"]["content"]) == ["application/problem+json"]
    assert list(responses["422"]["content"]) == ["application/problem+json"]
    assert list(responses["200"]["content"]) == ["application/json"]


def test_unhandled_error_response_carries_cors_headers(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_case_reader] = lambda: FakeReader(RuntimeError("boom"))

    response = client.get("/api/cases", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["X-Request-ID"]
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_cors_preflight_gets_a_request_id(client: TestClient) -> None:
    response = client.options(
        "/api/cases", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_case_summary_has_the_header_fields_and_null_counters(client: TestClient) -> None:
    [case] = client.get("/api/cases").json()

    assert case["postponed"] is False
    assert case["bucket"] == "aktivni"
    assert case["counts"] is None  # not 0: the handover service does not exist yet
    assert case["suspected_diagnosis"] is None
    assert case["koc"] is None
    assert case["referring_gp"] is None
