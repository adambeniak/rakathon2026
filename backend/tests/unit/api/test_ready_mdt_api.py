"""`mark_ready_mdt` / `reopen` through POST /transitions (#68): the readiness gate is computed on the server from the
launched pathway and the persisted handover; a KOC physician may waive blocking items with a reason (Provenance +
AuditEvent in the same transaction). The client cannot supply readiness."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_case_reader, get_case_workflow, get_directory_provider, get_fhir_client, get_iris_pool
from app.api.services.closed_loop import ClosedLoopWorkflow
from app.domain.case import Case, CaseState
from app.domain.common import Role
from app.fhir.client import Resource
from app.fhir.mappers.case import case_task_to_fhir
from app.fhir.mappers.handover import handover_business_id
from app.fhir.readiness import READINESS_SECTION
from app.fhir.systems import (
    CS_HANDOVER_SECTION,
    CS_HANDOVER_STATUS,
    EXT_HANDOVER_EDITED_VALUE,
    EXT_HANDOVER_FIELD_STATUS,
    EXT_READINESS_ITEM,
    SID_CAREPLAN,
    SID_HANDOVER,
)
from app.main import create_app
from app.seed import demo_case
from app.settings import Settings
from tests.unit.api.test_closed_loop_api import (
    CASE_URL,
    COORDINATOR_HEADERS,
    GP,
    MDT_START,
    PHYSICIAN,
    PHYSICIAN_HEADERS,
    SIGNER,
    FakeMailer,
    FakeProvider,
    MemoryFhir,
)

PLAN_PATH = Path(__file__).resolve().parents[4] / "iris" / "fhir" / "plandefinition-pancreas-dx.json"
PLAN: Resource = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
REQUIRED = tuple(READINESS_SECTION)  # the six items of the demo pathway, in the PlanDefinition's order
WAIVER_REASON = "PS doplní lékař osobně na MDT."


class ReadinessFhir(MemoryFhir):
    """MemoryFhir that also answers the CarePlan / PlanDefinition searches and identifier lookups."""

    async def search(self, resource_type: str, params: dict[str, str]) -> list[Resource]:
        if resource_type == "CarePlan":
            return [r for r in self.of_type("CarePlan") if params["subject"] == "Patient/2"]
        if resource_type == "PlanDefinition":
            return [r for r in self.of_type("PlanDefinition") if r["url"] == params["url"]]
        return await super().search(resource_type, params)

    async def find_by_identifier(self, resource_type: str, system: str, value: str) -> Resource | None:
        for resource in self.of_type(resource_type):
            identifier = resource.get("identifier")
            if identifier == {"system": system, "value": value}:
                return resource
        return None


def _section(item: str, status: str, *, edited: bool = False) -> Resource:
    key = READINESS_SECTION[item]
    extensions: list[Resource] = [
        {"url": EXT_HANDOVER_FIELD_STATUS, "valueCoding": {"system": CS_HANDOVER_STATUS, "code": status}}
    ]
    if edited:
        extensions.append({"url": EXT_HANDOVER_EDITED_VALUE, "valueString": json.dumps("doplněno lékařem")})
    return {"code": {"coding": [{"system": CS_HANDOVER_SECTION, "code": key}]}, "extension": extensions}


def _composition(statuses: dict[str, str], *, edited: tuple[str, ...] = ()) -> Resource:
    return {
        "resourceType": "Composition",
        "id": "40",
        "meta": {"versionId": "1"},
        "identifier": {"system": SID_HANDOVER, "value": handover_business_id(demo_case.CASE_ID, MDT_START)},
        "status": "preliminary",
        "subject": {"reference": "Patient/2"},
        "section": [_section(item, status, edited=item in edited) for item, status in statuses.items()],
    }


def _care_plan() -> Resource:
    return {
        "resourceType": "CarePlan",
        "id": "30",
        "identifier": [{"system": SID_CAREPLAN, "value": f"{demo_case.CASE_ID}.pancreas-dx"}],
        "instantiatesCanonical": [PLAN["url"]],
    }


def _task(state: CaseState = CaseState.KOMPLETNI, mdt_start: datetime | None = MDT_START) -> Resource:
    case = Case(
        id=demo_case.CASE_ID,
        patient=demo_case.PATIENT,
        state=state,
        baton_holder=PHYSICIAN,
        baton_role=Role.KOC_PHYSICIAN,
        opened_at=datetime(2026, 10, 2, 9, 30, tzinfo=MDT_START.tzinfo),
        mdt_start=mdt_start,
    )
    task = case_task_to_fhir(
        case,
        episode_reference="EpisodeOfCare/1",
        patient_reference="Patient/2",
        requester_reference=GP.ref,  # type: ignore[union-attr]
        owner_reference="PractitionerRole/9",
    )
    return {**task, "id": "5", "meta": {"versionId": "1"}}


def _all(status: str) -> dict[str, str]:
    return dict.fromkeys(REQUIRED, status)


def _fhir(
    statuses: dict[str, str] | None,
    *,
    state: CaseState = CaseState.KOMPLETNI,
    mdt_start: datetime | None = MDT_START,
    care_plan: bool = True,
    edited: tuple[str, ...] = (),
) -> ReadinessFhir:
    store = ReadinessFhir(_task(state, mdt_start))
    store.resources[("PlanDefinition", "20")] = {**PLAN, "id": "20"}
    if care_plan:
        store.resources[("CarePlan", "30")] = _care_plan()
    if statuses is not None:
        store.resources[("Composition", "40")] = _composition(statuses, edited=edited)
    return store


@pytest.fixture
def make_client(settings: Settings) -> Iterator[Any]:
    clients: list[TestClient] = []

    def build(store: ReadinessFhir) -> TestClient:
        app: FastAPI = create_app(settings)
        workflow = ClosedLoopWorkflow(store, store, FakeMailer(), "http://localhost:5173/gp")  # type: ignore[arg-type]
        app.dependency_overrides[get_case_workflow] = lambda: workflow
        app.dependency_overrides[get_case_reader] = lambda: store
        app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
        app.dependency_overrides[get_fhir_client] = lambda: object()
        app.dependency_overrides[get_iris_pool] = lambda: object()
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.__exit__(None, None, None)


def _post(client: TestClient, event: str, headers: dict[str, str] = PHYSICIAN_HEADERS, **body: Any) -> Any:
    return client.post(f"{CASE_URL}/transitions", json={"event": event, **body}, headers=headers)


def _state(store: ReadinessFhir) -> str:
    return str(store.resources[("Task", "5")]["businessStatus"]["coding"][0]["code"])


def _ready_waiver(item: str = "performance_status", reason: str = WAIVER_REASON) -> dict[str, str]:
    return {"item": item, "reason": reason}


def test_gate_passes_when_every_required_section_is_complete(make_client: Any) -> None:
    store = _fhir(_all("complete"))

    response = _post(make_client(store), "mark_ready_mdt")

    assert response.status_code == 200
    assert response.json()["state"] == "pripraveno_mdt"
    assert _state(store) == "pripraveno_mdt"
    assert store.of_type("Provenance") == []
    assert [a["subtype"][0]["code"] for a in store.of_type("AuditEvent")] == ["mark_ready_mdt"]


def test_partial_stale_and_conflicting_sections_warn_but_do_not_block(make_client: Any) -> None:
    statuses = _all("complete") | {
        "histology": "partial",
        "comorbidities": "stale",
        "ct_staging": "complete_with_conflict",
    }
    store = _fhir(statuses)

    assert _post(make_client(store), "mark_ready_mdt").status_code == 200


def test_missing_section_blocks_and_names_the_item(make_client: Any) -> None:
    store = _fhir(_all("complete") | {"performance_status": "missing"})

    response = _post(make_client(store), "mark_ready_mdt")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "guard_failed"
    # Structured keys for the waiver form (#140); the Czech sentence stays unchanged for people.
    assert body["blocking_items"] == ["performance_status"]
    assert body["detail"] == "Připravenost k MDT není splněna, chybí: performance_status"
    assert _state(store) == "kompletni"
    assert store.transactions == 0


def test_physician_waiver_passes_and_leaves_provenance_and_audit_in_one_transaction(make_client: Any) -> None:
    store = _fhir(_all("complete") | {"performance_status": "missing"})

    response = _post(make_client(store), "mark_ready_mdt", waivers=[_ready_waiver()])

    assert response.status_code == 200
    assert response.json()["state"] == "pripraveno_mdt"
    assert store.transactions == 1
    [provenance] = store.of_type("Provenance")
    assert provenance["target"] == [{"reference": "Task/5"}]
    assert provenance["reason"] == [{"text": WAIVER_REASON}]
    assert provenance["activity"]["coding"][0]["code"] == "waive-readiness"
    assert provenance["extension"] == [{"url": EXT_READINESS_ITEM, "valueCode": "performance_status"}]
    agent = provenance["agent"][0]
    assert agent["who"]["identifier"]["value"] == SIGNER.role.id
    assert agent["role"][0]["coding"][0]["code"] == "koc_physician"
    [audit] = store.of_type("AuditEvent")
    assert audit["subtype"][0]["code"] == "mark_ready_mdt"
    detail = {d["type"]: d["valueString"] for d in audit["entity"][0]["detail"]}
    assert "performance_status" in detail["waived"]
    assert WAIVER_REASON in detail["waived"]


def test_a_waiver_does_not_cover_other_blocking_items(make_client: Any) -> None:
    store = _fhir(_all("complete") | {"performance_status": "missing", "histology": "missing"})

    response = _post(make_client(store), "mark_ready_mdt", waivers=[_ready_waiver()])

    assert response.status_code == 409
    assert "histology" in response.json()["detail"]
    assert "performance_status" not in response.json()["detail"]
    assert response.json()["blocking_items"] == ["histology"]  # the waived item is no longer blocking
    assert store.transactions == 0


def test_a_waiver_for_a_passing_item_records_nothing(make_client: Any) -> None:
    store = _fhir(_all("complete"))

    response = _post(make_client(store), "mark_ready_mdt", waivers=[_ready_waiver("histology")])

    assert response.status_code == 200
    assert store.of_type("Provenance") == []


def test_a_section_the_physician_filled_in_counts_as_complete(make_client: Any) -> None:
    store = _fhir(_all("complete") | {"performance_status": "missing"}, edited=("performance_status",))

    assert _post(make_client(store), "mark_ready_mdt").status_code == 200


@pytest.mark.parametrize("waivers", [[], [_ready_waiver()]])
def test_a_coordinator_is_refused_by_role_with_or_without_waivers(make_client: Any, waivers: list[Any]) -> None:
    store = _fhir(_all("complete") | {"performance_status": "missing"})

    response = _post(make_client(store), "mark_ready_mdt", COORDINATOR_HEADERS, waivers=waivers)

    assert response.status_code == 409
    assert response.json()["code"] == "forbidden_role"
    assert store.transactions == 0


def test_a_wrong_state_is_refused_by_the_machine_before_readiness_is_looked_at(make_client: Any) -> None:
    store = _fhir(None, state=CaseState.TRIAGE, care_plan=False)

    response = _post(make_client(store), "mark_ready_mdt")

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_transition"


@pytest.mark.parametrize(
    ("kwargs", "detail"),
    [
        ({"care_plan": False, "statuses": _all("complete")}, "žádná sada vyšetření"),
        ({"statuses": None}, "ještě nebyl sestaven"),
        ({"statuses": _all("complete"), "mdt_start": None}, "termín MDT"),
    ],
)
def test_readiness_that_cannot_be_established_fails_closed(
    make_client: Any, kwargs: dict[str, Any], detail: str
) -> None:
    statuses = kwargs.pop("statuses")
    store = _fhir(statuses, **kwargs)

    response = _post(make_client(store), "mark_ready_mdt", waivers=[_ready_waiver()])

    assert response.status_code == 409
    assert response.json()["code"] == "guard_failed"
    assert detail in response.json()["detail"]
    assert "blocking_items" not in response.json()  # no structured items when readiness is unknown
    assert _state(store) == "kompletni"


def test_a_section_missing_from_the_handover_blocks_like_a_missing_one(make_client: Any) -> None:
    statuses = _all("complete")
    del statuses["tumour_markers"]
    store = _fhir(statuses)

    response = _post(make_client(store), "mark_ready_mdt")

    assert response.status_code == 409
    assert "tumour_markers" in response.json()["detail"]


@pytest.mark.parametrize(
    "waivers",
    [
        [_ready_waiver("not_an_item")],
        [_ready_waiver(reason="   ")],
        [_ready_waiver(), _ready_waiver()],
    ],
)
def test_invalid_waivers_are_422_and_write_nothing(make_client: Any, waivers: list[dict[str, str]]) -> None:
    store = _fhir(_all("complete") | {"performance_status": "missing"})

    response = _post(make_client(store), "mark_ready_mdt", waivers=waivers)

    assert response.status_code == 422
    assert store.transactions == 0


@pytest.mark.parametrize(
    "body",
    [
        {"readiness": {"ready": True, "missing": [], "waived": []}},
        {"ready": True},
        {"waivers": [{"item": "performance_status", "reason": "x", "by": "someone-else"}]},
        {"waivers": [{"item": "performance_status", "reason": "x", "by_role": "koc_physician"}]},
    ],
)
def test_the_client_cannot_supply_readiness_or_a_signer(make_client: Any, body: dict[str, Any]) -> None:
    store = _fhir(_all("complete") | {"performance_status": "missing"})

    response = _post(make_client(store), "mark_ready_mdt", **body)

    assert response.status_code == 422
    assert _state(store) == "kompletni"
    assert store.transactions == 0


def test_waivers_belong_to_mark_ready_mdt_only(make_client: Any) -> None:
    store = _fhir(_all("complete"), state=CaseState.PRIPRAVENO_MDT)

    response = _post(make_client(store), "reopen", reason="chybí CT", waivers=[_ready_waiver()])

    assert response.status_code == 422
    assert store.transactions == 0


def test_reopen_needs_a_reason(make_client: Any) -> None:
    store = _fhir(_all("complete"), state=CaseState.PRIPRAVENO_MDT)
    client = make_client(store)

    refused = _post(client, "reopen")
    assert refused.status_code == 409
    assert refused.json()["code"] == "guard_failed"
    assert _state(store) == "pripraveno_mdt"

    reopened = _post(client, "reopen", reason="přišel nový nález")
    assert reopened.status_code == 200
    assert reopened.json()["state"] == "kompletni"
