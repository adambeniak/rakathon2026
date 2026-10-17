from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_case_reader, get_case_workflow, get_directory_provider, get_fhir_client, get_iris_pool
from app.domain.case import Case, CaseState
from app.domain.common import PartyRef, Role
from app.domain.events import TransitionError
from app.fhir.cases import CaseOverview
from app.fhir.directory import Directory
from app.fhir.workflow import TransitionOutcome
from app.main import create_app
from app.seed import demo_case
from app.settings import PRAGUE, Settings
from tests.directory_fixtures import demo_directory

NOW = datetime(2026, 10, 2, 10, 0, tzinfo=PRAGUE)
COORDINATOR = "dvorakova-lucie@koc2-nemocnice-lipova"
GP = "reznicek-tomas@pl-dolni-brezany"


class FakeProvider:
    async def get(self) -> Directory:
        return demo_directory()


class FakeWorkflow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Role, str | None]] = []
        self.extras: list[dict[str, object]] = []
        self.error: Exception | None = None

    async def transition(
        self, case_id: str, event: str, *, actor: PartyRef, reason: str | None = None, **rest: object
    ) -> TransitionOutcome:
        self.calls.append((case_id, event, actor.role, reason))
        self.extras.append(rest)
        if self.error:
            raise self.error
        return TransitionOutcome(_case(CaseState.TRIAGE), ())


class FakeReader:
    async def overview(self, case_id: str) -> CaseOverview:
        return CaseOverview(case=_case(CaseState.TRIAGE), document_count=1)


def _case(state: CaseState) -> Case:
    return Case(
        id=demo_case.CASE_ID,
        patient=demo_case.PATIENT,
        state=state,
        baton_holder=PartyRef(id=COORDINATOR, display="Bc. Lucie Dvořáková", role=Role.COORDINATOR),
        opened_at=NOW,
    )


@pytest.fixture
def workflow() -> FakeWorkflow:
    return FakeWorkflow()


@pytest.fixture
def client(settings: Settings, workflow: FakeWorkflow) -> Iterator[TestClient]:
    app: FastAPI = create_app(settings)
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_case_workflow] = lambda: workflow
    app.dependency_overrides[get_case_reader] = lambda: FakeReader()
    app.dependency_overrides[get_fhir_client] = lambda: object()
    app.dependency_overrides[get_iris_pool] = lambda: object()
    with TestClient(app) as test_client:
        yield test_client


def test_koc_list_has_city_and_role_level_coordinator(client: TestClient) -> None:
    response = client.get("/api/directory/kocs")

    assert response.status_code == 200
    koc1, koc2 = response.json()
    assert koc2["id"] == "koc2-nemocnice-lipova"
    assert koc2["city"] == "Praha 4"
    assert koc2["coordinator"]["display"] == "Koordinátor KOC 2"
    assert koc1["coordinator"] is None


def test_transition_uses_the_role_from_the_directory_not_from_the_client(
    client: TestClient, workflow: FakeWorkflow
) -> None:
    response = client.post(
        "/api/cases/rakathon-2026-prochazkova/transitions",
        json={"event": "accept"},
        headers={"X-Demo-Role": "coordinator"},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "triage"
    assert workflow.calls == [("rakathon-2026-prochazkova", "accept", Role.COORDINATOR, None)]


def test_forbidden_transition_is_a_409_problem_with_a_machine_code(client: TestClient, workflow: FakeWorkflow) -> None:
    workflow.error = TransitionError("forbidden_role", "role 'gp' may not 'accept'")

    response = client.post(
        "/api/cases/rakathon-2026-prochazkova/transitions", json={"event": "accept"}, headers={"X-Demo-Role": "gp"}
    )

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "forbidden_role"
    assert body["type"].endswith("/conflict")


def test_unknown_role_is_401(client: TestClient) -> None:
    response = client.post(
        "/api/cases/rakathon-2026-prochazkova/transitions", json={"event": "accept"}, headers={"X-Demo-Role": "wizard"}
    )

    assert response.status_code == 401
    assert response.json()["type"].endswith("/unauthenticated")


def test_outside_demo_mode_every_request_is_401_even_with_the_header(
    settings: Settings, workflow: FakeWorkflow
) -> None:
    prod = settings.model_copy(update={"stafeta_demo_mode": False})
    app = create_app(prod)
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_case_workflow] = lambda: workflow
    app.dependency_overrides[get_case_reader] = lambda: FakeReader()
    app.dependency_overrides[get_fhir_client] = lambda: object()
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/cases/rakathon-2026-prochazkova/transitions",
            json={"event": "accept"},
            headers={"X-Demo-Role": "coordinator"},
        )

    assert response.status_code == 401


def test_cors_preflight_allows_the_actor_header(client: TestClient) -> None:
    response = client.options(
        "/api/cases/rakathon-2026-prochazkova/transitions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-demo-role,content-type",
        },
    )

    assert response.status_code == 200
    assert "x-demo-role" in response.headers["access-control-allow-headers"].lower()


def test_missing_header_in_demo_mode_is_the_coordinator(client: TestClient, workflow: FakeWorkflow) -> None:
    response = client.post("/api/cases/rakathon-2026-prochazkova/transitions", json={"event": "accept"})

    assert response.status_code == 200
    assert workflow.calls[0][2] is Role.COORDINATOR


@pytest.mark.parametrize("role", ["system", "patient", "SYSTEM ", ""])
def test_roles_that_a_browser_may_not_pick_are_refused_or_defaulted(
    client: TestClient, workflow: FakeWorkflow, role: str
) -> None:
    response = client.post(
        "/api/cases/rakathon-2026-prochazkova/transitions", json={"event": "accept"}, headers={"X-Demo-Role": role}
    )

    if role == "":
        assert response.status_code == 200  # empty = absent = coordinator
    else:
        assert response.status_code == 401
        assert all(call[2] is not Role.SYSTEM for call in workflow.calls)


def test_directory_needs_an_identified_actor(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"stafeta_demo_mode": False}))
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_fhir_client] = lambda: object()
    with TestClient(app) as test_client:
        response = test_client.get("/api/directory/kocs")

    assert response.status_code == 401


def test_conclusion_and_receipt_reach_the_workflow_but_the_signer_is_never_in_the_body(
    client: TestClient, workflow: FakeWorkflow
) -> None:
    url = "/api/cases/rakathon-2026-prochazkova/transitions"
    headers = {"X-Demo-Role": "koc_physician"}

    ok = client.post(url, json={"event": "record_mdt_conclusion", "conclusion": "Závěr MDT."}, headers=headers)
    forged = client.post(
        url, json={"event": "record_mdt_conclusion", "conclusion": "x", "confirmed_by": "someone"}, headers=headers
    )

    assert ok.status_code == 200
    assert workflow.extras[0]["conclusion"] == "Závěr MDT."
    assert forged.status_code == 422  # extra="forbid": the clinician id comes from the actor only
    receipt = client.post(url, json={"event": "delivery_confirmed", "receipt_id": "r-1"}, headers=headers)
    assert receipt.status_code == 200
    assert workflow.extras[1]["receipt_id"] == "r-1"
