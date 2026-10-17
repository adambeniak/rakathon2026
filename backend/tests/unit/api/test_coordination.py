"""Coordination API against an in-memory TaskStore: pathway launch, board, alerts, transitions, ad-hoc tasks."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_coordination, get_directory_provider, get_fhir_client, get_iris_pool
from app.api.schemas.coordination import TransitionRequest
from app.api.services.coordination import CoordinationService
from app.api.watchdog import run_once
from app.domain import clock
from app.domain.common import PartyRef, Role
from app.domain.errors import ForbiddenError, NotFoundError
from app.domain.task import Task
from app.fhir.cases import CaseHeader, LoadedCase
from app.fhir.directory import Directory
from app.fhir.mappers.task import task_to_fhir
from app.fhir.tasks import LaunchResult, PractitionerRoleRef, StoredTask
from app.main import create_app
from app.settings import Settings
from tests.directory_fixtures import demo_directory
from tests.unit.domain.conftest import load_plan, make_case

CASE_ID = "c1"
PLAN_URL = "https://stafeta.example/fhir/PlanDefinition/pancreas-dx"
RESULT_DOC = "07_PL_zadost_KOC2_2026-10-02"
FUTURE_DOC = "12_Algeziologie_2026-10-26"
SOURCE_NOTE = "Telefonicky potvrzeno pracovištěm"
COORDINATOR = {"X-Demo-Role": "coordinator"}
PHYSICIAN = {"X-Demo-Role": "koc_physician"}
GP = {"X-Demo-Role": "gp"}
PHYSICIAN_ID = "hruby-pavel@koc2-nemocnice-lipova"
LAUNCH = {"plan_url": PLAN_URL, "start_date": "2026-10-02", "indicated_by": PHYSICIAN_ID}


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=clock.TZ)


class FakeProvider:
    async def get(self) -> Directory:
        return demo_directory()


class FakeReader:
    """`CaseReader.load` for the demo case: managed by KOC 2, referred by the seeded GP (`authorize_case` is real)."""

    def __init__(self, mdt_start: datetime | None) -> None:
        directory = demo_directory()
        koc = directory.org("koc2-nemocnice-lipova")
        gp = directory.role("reznicek-tomas@pl-dolni-brezany")
        assert koc is not None
        assert gp is not None
        self.loaded = LoadedCase(
            task={"id": "5", "for": {"reference": "Patient/3"}, "requester": {"reference": gp.ref}},
            episode={"managingOrganization": {"reference": koc.ref}},
            case=make_case(mdt_start=mdt_start),
        )

    async def load(self, case_id: str) -> LoadedCase:
        if case_id != CASE_ID:
            raise NotFoundError("case", case_id)
        return self.loaded


class FakeStore:
    """The TaskStore contract without HTTP: keeps FHIR-shaped resources so reads exercise the real mappers."""

    def __init__(self) -> None:
        self.resources: dict[str, dict[str, Any]] = {}
        self.saves: list[dict[str, Any]] = []
        self.documents = {RESULT_DOC: at("2026-10-02T08:00:00"), FUTURE_DOC: at("2026-10-26T12:00:00")}
        self.care_plans: set[str] = set()
        self.launches: list[dict[str, Any]] = []

    def _stored(self, task: Task, fhir_id: str) -> StoredTask:
        resource = {
            **task_to_fhir(task, case_task_reference="Task/5", patient_reference="Patient/3"),
            "id": fhir_id,
            "meta": {"versionId": "1"},
        }
        self.resources[task.id] = resource
        return StoredTask(task, resource)

    async def get_plan_definition(self, url: str) -> dict[str, Any]:
        if url != PLAN_URL:
            raise NotFoundError("plan", url)
        return load_plan()

    async def care_plan_exists(self, case_id: str, plan: dict[str, Any]) -> bool:
        return case_id in self.care_plans

    async def launch_pathway(
        self,
        header: CaseHeader,
        plan: dict[str, Any],
        tasks: list[Task],
        start_date: date,
        *,
        indication: PractitionerRoleRef,
        coordinator: PartyRef,
        recorded: datetime,
        mdt_start: datetime | None = None,
    ) -> LaunchResult:
        self.launches.append(
            {"indication": indication, "coordinator": coordinator, "recorded": recorded, "mdt_start": mdt_start}
        )
        self.care_plans.add(header.case.id)
        ids = {t.id: str(len(self.resources) + i + 1) for i, t in enumerate(tasks)}
        for task in tasks:
            self._stored(task, ids[task.id])
        return LaunchResult("1", ids, dict(ids), "9")

    async def create(self, header: CaseHeader, task: Task) -> str:
        return self._stored(task, str(len(self.resources) + 1)).fhir_id

    async def list_for_case(self, case_task_reference: str) -> list[StoredTask]:
        from app.domain.board import due_order
        from app.fhir.mappers.task import task_from_fhir

        stored = [StoredTask(task_from_fhir(r), r) for r in self.resources.values()]
        return sorted(stored, key=lambda s: due_order(s.task))

    async def get(self, task_id: str) -> StoredTask:
        from app.fhir.mappers.task import task_from_fhir

        if task_id not in self.resources:
            raise NotFoundError("task", task_id)
        resource = self.resources[task_id]
        return StoredTask(task_from_fhir(resource), resource)

    async def list_open_everywhere(self) -> list[StoredTask]:
        from app.domain.task_machine import OPEN_STATUSES

        return [s for s in await self.list_for_case("Task/5") if s.task.status in OPEN_STATUSES]

    async def patient_document_received_at(self, patient_reference: str, doc_id: str) -> datetime | None:
        return self.documents.get(doc_id)

    async def save(
        self, stored: StoredTask, task: Task, *, description: str, on_behalf_of: str | None = None
    ) -> StoredTask:
        self.saves.append({"task": task.id, "description": description, "on_behalf_of": on_behalf_of})
        return self._stored(task, stored.fhir_id)


class Harness:
    def __init__(
        self, app: FastAPI, client: TestClient, store: FakeStore, now: dict[str, datetime], reader: FakeReader
    ) -> None:
        self.app, self.client, self.store, self._now, self.reader = app, client, store, now, reader

    def case_without_mdt_start(self) -> None:
        self.reader.loaded = LoadedCase(
            task=self.reader.loaded.task, episode=self.reader.loaded.episode, case=make_case(mdt_start=None)
        )

    def set_now(self, value: str) -> None:
        self._now["value"] = at(value)

    def launch(self, headers: dict[str, str] = COORDINATOR, **body: Any) -> Any:
        return self.client.post(f"/api/cases/{CASE_ID}/pathways", json={**LAUNCH, **body}, headers=headers)

    def move(self, step: str, event: str, headers: dict[str, str] = COORDINATOR, **body: Any) -> Any:
        return self.client.post(
            f"/api/tasks/{CASE_ID}.{step}/transitions", json={"event": event, **body}, headers=headers
        )

    def board(self) -> dict[str, Any]:
        body: dict[str, Any] = self.client.get(f"/api/cases/{CASE_ID}/board").json()
        return body

    def alerts(self) -> list[dict[str, Any]]:
        body: list[dict[str, Any]] = self.client.get(f"/api/cases/{CASE_ID}/alerts").json()
        return body


@pytest.fixture
def harness(settings: Settings) -> Iterator[Harness]:
    app = create_app(settings)
    store = FakeStore()
    now = {"value": at("2026-10-02T09:00:00")}
    reader = FakeReader(mdt_start=at("2026-10-21T08:00:00"))
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()  # for the shared current_actor
    app.dependency_overrides[get_fhir_client] = lambda: object()
    app.dependency_overrides[get_iris_pool] = lambda: object()
    app.dependency_overrides[get_coordination] = lambda: CoordinationService(
        reader,  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        lambda: now["value"],
        FakeProvider(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        yield Harness(app, client, store, now, reader)


def test_launch_persists_the_mdt_start_it_was_given(harness: Harness) -> None:
    harness.case_without_mdt_start()

    response = harness.launch(mdt_start="2026-10-21T08:00:00+02:00")

    assert response.status_code == 201
    assert harness.store.launches[-1]["mdt_start"] == at("2026-10-21T08:00:00")


def test_launch_keeps_the_mdt_start_the_case_already_has(harness: Harness) -> None:
    response = harness.launch()  # the case has 2026-10-21T08:00

    assert response.status_code == 201
    assert harness.store.launches[-1]["mdt_start"] is None  # nothing to write


def test_endpoints_are_in_the_contract(harness: Harness) -> None:
    paths = harness.app.openapi()["paths"]
    assert "post" in paths["/api/cases/{case_id}/pathways"]
    assert "get" in paths["/api/cases/{case_id}/board"]
    assert "get" in paths["/api/cases/{case_id}/alerts"]
    assert "post" in paths["/api/cases/{case_id}/tasks"]
    assert "post" in paths["/api/tasks/{task_id}/transitions"]


# --- acceptance A: 2. 10. ---


def test_launch_on_2_october_yields_the_pathway_in_dependency_order(harness: Harness) -> None:
    response = harness.launch()

    assert response.status_code == 201
    body = response.json()
    tasks = body["tasks"]
    assert [t["code"] for t in tasks] == [
        "ct-thorax-abdomen",
        "eus-fnb",
        "labs-dx",
        "histology",
        "mdt",
        "algesiology",
        "psychooncology",
    ]
    assert [t["due"][:10] for t in tasks] == [
        "2026-10-08",
        "2026-10-12",
        "2026-10-15",
        "2026-10-19",
        "2026-10-21",
        "2026-10-26",
        "2026-10-27",
    ]
    position = {t["id"]: i for i, t in enumerate(tasks)}
    assert all(position[dep] < position[t["id"]] for t in tasks for dep in t["depends_on"])
    assert all(t["status"] == "requested" and t["business_status"] == "objednano" for t in tasks)
    assert all(t["place"] and t["demo_assumption"] for t in tasks)
    assert not any(t["overdue"] for t in tasks)


def test_board_shows_lanes_and_who_holds_the_baton(harness: Harness) -> None:
    harness.launch()

    board = harness.board()

    assert [lane["role"] for lane in board["lanes"]] == [
        "gp",
        "coordinator",
        "koc_physician",
        "external_workplace",
        "patient",
    ]
    lanes = {lane["role"]: [t["id"].split(".")[1] for t in lane["tasks"]] for lane in board["lanes"]}
    assert lanes["external_workplace"] == ["ct", "labs", "histology"]
    assert lanes["koc_physician"] == ["eus-fnb", "mdt", "algesiology", "psychooncology"]
    baton = board["baton_holder"]
    # Nothing is ordered yet: the coordinator holds the baton until place and date are confirmed.
    assert (baton["task_id"], baton["role"], baton["basis"], baton["reason"]) == (
        "c1.ct",
        "coordinator",
        "required_for_mdt",
        "awaiting_confirmation",
    )
    assert baton["owner"] is None
    assert baton["demo_assumption"] is True
    assert board["computed_at"].startswith("2026-10-02T09:00")
    critical = {t["id"] for lane in board["lanes"] for t in lane["tasks"] if t["required_for_mdt"]}
    assert critical == {"c1.ct", "c1.eus-fnb", "c1.labs", "c1.histology", "c1.mdt"}
    mdt = next(t for lane in board["lanes"] for t in lane["tasks"] if t["id"] == "c1.mdt")
    assert mdt["blocked_by"] == ["c1.ct", "c1.histology", "c1.labs"]


def test_launch_records_the_indicating_physician_and_who_acted_on_their_behalf(harness: Harness) -> None:
    response = harness.launch()

    assert response.status_code == 201
    assert response.json()["indicated_by"] == {
        "id": PHYSICIAN_ID,
        "display": "doc. MUDr. Pavel Hrubý, Ph.D.",
        "role": "koc_physician",
    }
    [launch] = harness.store.launches
    assert launch["indication"].business_id == PHYSICIAN_ID
    assert launch["indication"].fhir_reference.startswith("PractitionerRole/")
    assert launch["coordinator"].role is Role.COORDINATOR
    assert launch["recorded"] == at("2026-10-02T09:00:00")  # the (demo) clock, not the wall clock


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_launch_without_an_indicating_physician_is_refused_in_czech(harness: Harness, missing: str | None) -> None:
    response = harness.launch(indicated_by=missing)

    assert response.status_code == 422
    assert response.json()["detail"] == "Sada vyšetření vyžaduje indikujícího lékaře KOC."
    assert harness.store.resources == {}
    assert harness.store.launches == []


def test_launch_without_the_field_at_all_is_refused_too(harness: Harness) -> None:
    body = {k: v for k, v in LAUNCH.items() if k != "indicated_by"}
    response = harness.client.post(f"/api/cases/{CASE_ID}/pathways", json=body, headers=COORDINATOR)
    assert response.status_code == 422
    assert response.json()["detail"] == "Sada vyšetření vyžaduje indikujícího lékaře KOC."


def test_only_a_koc_physician_can_indicate_the_set(harness: Harness) -> None:
    unknown = harness.launch(indicated_by="nobody@nowhere")
    assert unknown.status_code == 422
    assert unknown.json()["detail"] == "Zadaný indikující lékař neexistuje."

    not_a_physician = harness.launch(indicated_by="dvorakova-lucie@koc2-nemocnice-lipova")  # the coordinator herself
    assert not_a_physician.status_code == 422
    assert not_a_physician.json()["detail"] == "Indikujícím lékařem může být jen lékař KOC (role koc_physician)."
    assert harness.store.launches == []


def test_launch_is_coordinator_only_and_idempotent(harness: Harness) -> None:
    assert harness.launch(headers=GP).status_code == 403
    assert harness.launch(headers=PHYSICIAN).status_code == 403
    assert harness.store.resources == {}

    assert harness.launch().status_code == 201
    again = harness.launch()
    assert again.status_code == 409
    assert again.headers["content-type"].startswith("application/problem+json")
    assert len(harness.store.resources) == 7


def test_launch_without_header_acts_as_coordinator_in_demo_mode(harness: Harness) -> None:
    assert harness.client.post(f"/api/cases/{CASE_ID}/pathways", json=LAUNCH).status_code == 201


def test_launch_errors(harness: Harness) -> None:
    unknown = harness.launch(plan_url="https://stafeta.example/fhir/PlanDefinition/other")
    assert unknown.status_code == 404
    bad = harness.launch(plan_url="not-a-url")
    assert bad.status_code == 422
    missing_case = harness.client.post("/api/cases/nope/pathways", json=LAUNCH, headers=COORDINATOR)
    assert missing_case.status_code == 404


def test_launch_needs_an_mdt_start_from_the_case_or_the_request(settings: Settings) -> None:
    app = create_app(settings)
    store = FakeStore()
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_coordination] = lambda: CoordinationService(
        FakeReader(mdt_start=None),  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        lambda: at("2026-10-02T09:00:00"),
        FakeProvider(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        url = f"/api/cases/{CASE_ID}/pathways"
        refused = client.post(url, json=LAUNCH)
        assert refused.status_code == 422
        assert refused.headers["content-type"] == "application/problem+json"
        assert refused.json()["detail"] == "Pro spuštění sady je nutné zadat termín MDT."
        assert store.launches == []
        accepted = client.post(url, json={**LAUNCH, "mdt_start": "2026-10-21T08:00:00+02:00"})
        assert accepted.status_code == 201


# --- acceptance B: 16. 10. ---


def test_no_alerts_on_2_october_and_the_histology_sla_breach_on_16_october(harness: Harness) -> None:
    harness.launch()
    assert harness.alerts() == []

    harness.set_now("2026-10-15T23:00:00")
    assert "c1.histology" not in {a["task_id"] for a in harness.alerts()}  # Thursday: promise still holds

    harness.set_now("2026-10-16T09:00:00")
    histology = next(a for a in harness.alerts() if a["task_id"] == "c1.histology")
    assert histology["kind"] == "sla_breach"
    assert histology["basis"] == "sla"
    assert histology["deadline"] == "2026-10-15"
    assert histology["overdue_workdays"] == 1
    assert histology["recipients"] == ["coordinator"]
    assert histology["escalated_at"] is None


def test_watchdog_escalates_once_and_the_alert_shows_it(harness: Harness) -> None:
    import asyncio

    harness.launch()
    harness.set_now("2026-10-16T09:00:00")
    store = harness.store

    first = asyncio.run(run_once(store, at("2026-10-16T09:00:00")))  # type: ignore[arg-type]
    second = asyncio.run(run_once(store, at("2026-10-16T09:01:00")))  # type: ignore[arg-type]

    assert "c1.histology" in first
    assert second == []
    saved = next(s for s in store.saves if s["task"] == "c1.histology")
    assert "overdue escalation (sla, 1 working day(s) after 2026-10-15)" in saved["description"]
    histology = next(a for a in harness.alerts() if a["task_id"] == "c1.histology")
    assert histology["escalated_at"].startswith("2026-10-16T09:00")


def test_board_marks_overdue_tasks(harness: Harness) -> None:
    harness.launch()
    harness.set_now("2026-10-16T09:00:00")
    overdue = {t["id"] for lane in harness.board()["lanes"] for t in lane["tasks"] if t["overdue"]}
    assert {"c1.ct", "c1.eus-fnb", "c1.labs", "c1.histology"} <= overdue
    assert "c1.mdt" not in overdue


# --- transitions ---


def confirm_ct(h: Harness) -> Any:
    return h.move("ct", "confirm", date="2026-10-08")


def test_confirm_chains_order_confirmation_and_acceptance(harness: Harness) -> None:
    harness.launch()
    refused = harness.move("ct", "confirm")
    assert refused.status_code == 422

    response = confirm_ct(harness)

    assert response.status_code == 200
    task = response.json()
    assert (task["status"], task["business_status"]) == ("accepted", "potvrzeno")
    assert task["scheduled_at"].startswith("2026-10-08T00:00")
    assert harness.store.saves[-1]["description"].startswith("task c1.ct: order_confirmed + accept;")
    assert confirm_ct(harness).status_code == 409  # nothing left to confirm


def test_coordinator_records_perform_and_result_for_the_external_workplace(harness: Harness) -> None:
    harness.launch()
    confirm_ct(harness)

    no_source = harness.move("ct", "perform")  # recording for a workplace needs a stated source
    assert no_source.status_code == 422
    assert "source" in no_source.json()["detail"]

    performed = harness.move("ct", "perform", note=SOURCE_NOTE)
    assert performed.status_code == 200
    body = performed.json()
    assert (body["status"], body["business_status"]) == ("in_progress", "provedeno")
    assert body["note"] == SOURCE_NOTE
    assert body["recorded_on_behalf_by"]["role"] == "coordinator"  # visible to every reader of the task
    assert harness.store.saves[-1]["on_behalf_of"] == body["place"]
    assert harness.store.saves[-1]["description"].startswith("task c1.ct: start + performed;")
    assert "on behalf of the external workplace" in harness.store.saves[-1]["description"]
    assert SOURCE_NOTE not in harness.store.saves[-1]["description"]

    delivered = harness.move("ct", "deliver_result", document_id=RESULT_DOC)
    assert delivered.status_code == 200
    body = delivered.json()
    assert (body["status"], body["business_status"], body["result_doc_id"]) == (
        "completed",
        "vysledek_dorucen",
        RESULT_DOC,
    )
    assert harness.store.saves[-1]["on_behalf_of"] is not None
    baton = harness.board()["baton_holder"]
    assert (baton["task_id"], baton["role"], baton["reason"]) == ("c1.eus-fnb", "coordinator", "awaiting_confirmation")
    harness.move("eus-fnb", "confirm", date="2026-10-12", place="KOC 2")
    baton = harness.board()["baton_holder"]
    assert (baton["task_id"], baton["role"], baton["reason"]) == ("c1.eus-fnb", "koc_physician", "action")


def test_deliver_result_needs_an_existing_document(harness: Harness) -> None:
    harness.launch()
    confirm_ct(harness)
    harness.move("ct", "perform", note=SOURCE_NOTE)
    assert harness.move("ct", "deliver_result").status_code == 422
    unknown = harness.move("ct", "deliver_result", document_id="no-such-doc")
    assert unknown.status_code == 422
    assert "no-such-doc" in unknown.json()["detail"]
    future = harness.move("ct", "deliver_result", document_id=FUTURE_DOC)  # received after the (demo) clock
    assert future.status_code == 422
    assert "after the current time" in future.json()["detail"]


def test_refused_transitions_say_why(harness: Harness) -> None:
    harness.launch()
    harness.move("eus-fnb", "confirm", date="2026-10-12", place="KOC 2")

    forbidden = harness.move("eus-fnb", "perform", headers=COORDINATOR)  # the physician owns EUS-FNB
    assert forbidden.status_code == 409
    assert forbidden.json()["code"] == "forbidden_role"

    blocked = harness.move("eus-fnb", "perform", headers=PHYSICIAN)  # CT is not finished
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "guard_failed"
    assert "c1.ct" in blocked.json()["detail"]
    assert blocked.headers["content-type"].startswith("application/problem+json")

    invalid = harness.move("labs", "deliver_result", document_id=RESULT_DOC)
    assert invalid.status_code == 409
    assert invalid.json()["code"] == "invalid_transition"
    assert harness.move("nope", "confirm", date="2026-10-12").status_code == 404


def test_physician_performs_once_the_dependencies_are_done(harness: Harness) -> None:
    harness.launch()
    confirm_ct(harness)
    harness.move("ct", "perform", note=SOURCE_NOTE)
    harness.move("ct", "deliver_result", document_id=RESULT_DOC)
    harness.move("eus-fnb", "confirm", date="2026-10-12", place="KOC 2")

    response = harness.move("eus-fnb", "perform", headers=PHYSICIAN)

    assert response.status_code == 200
    assert response.json()["business_status"] == "provedeno"
    assert harness.store.saves[-1]["on_behalf_of"] is None


def test_fail_and_cancel_need_a_reason_and_the_right_role(harness: Harness) -> None:
    harness.launch()
    confirm_ct(harness)

    assert harness.move("ct", "cancel").status_code == 422
    assert harness.move("ct", "cancel", note="  ").status_code == 422
    assert harness.move("ct", "cancel", note="Pacientka odmítla", headers=PHYSICIAN).status_code == 409

    cancelled = harness.move("ct", "cancel", note="Pacientka odmítla")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    description = harness.store.saves[-1]["description"]
    assert description.endswith("reason recorded on the task")
    assert "Pacientka" not in description  # free text never reaches the audit trail
    assert "ct" not in harness.board()["baton_holder"]["task_id"]


def test_fail_after_acceptance(harness: Harness) -> None:
    harness.launch()
    confirm_ct(harness)
    failed = harness.move("ct", "fail", note="Přístroj mimo provoz")
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"


# --- single tasks ---


def test_coordinator_creates_an_ad_hoc_task_for_the_physician(harness: Harness) -> None:
    harness.launch()

    response = harness.client.post(
        f"/api/cases/{CASE_ID}/tasks",
        json={"title": "Doplnit ECOG", "owner_role": "koc_physician", "due": "2026-10-19"},
        headers=COORDINATOR,
    )

    assert response.status_code == 201
    task = response.json()
    assert task["id"].startswith("c1.adhoc-")
    assert (task["code"], task["ad_hoc"], task["lane"], task["required_for_mdt"]) == (
        "ad-hoc",
        True,
        "koc_physician",
        False,
    )
    assert (task["status"], task["business_status"]) == ("requested", "objednano")
    assert task["due"].startswith("2026-10-19T23:59:59")
    lane = next(lane for lane in harness.board()["lanes"] if lane["role"] == "koc_physician")
    assert task["id"] in {t["id"] for t in lane["tasks"]}
    assert harness.board()["baton_holder"]["task_id"] == "c1.ct"  # a single task never takes the baton from the path


def test_ad_hoc_task_without_a_pathway_holds_the_baton(harness: Harness) -> None:
    harness.client.post(
        f"/api/cases/{CASE_ID}/tasks",
        json={"title": "Doplnit ECOG", "owner_role": "koc_physician"},
        headers=COORDINATOR,
    )
    baton = harness.board()["baton_holder"]
    assert (baton["basis"], baton["task_title"]) == ("ad_hoc", "Doplnit ECOG")
    assert (baton["role"], baton["reason"]) == ("coordinator", "awaiting_confirmation")


def test_ad_hoc_task_rules(harness: Harness) -> None:
    harness.launch()
    url = f"/api/cases/{CASE_ID}/tasks"
    body = {"title": "Doplnit ECOG", "owner_role": "koc_physician"}
    assert harness.client.post(url, json=body, headers=PHYSICIAN).status_code == 403
    assert harness.client.post(url, json={**body, "owner_role": "system"}, headers=COORDINATOR).status_code == 422
    # a patient cannot act in Štafeta and nobody may record for them: such a task could never be completed
    assert harness.client.post(url, json={**body, "owner_role": "patient"}, headers=COORDINATOR).status_code == 422
    assert harness.client.post(url, json={**body, "title": ""}, headers=COORDINATOR).status_code == 422
    unknown = harness.client.post(url, json={**body, "depends_on": ["c1.nope"]}, headers=COORDINATOR)
    assert unknown.status_code == 422
    known = harness.client.post(url, json={**body, "depends_on": ["c1.ct"]}, headers=COORDINATOR)
    assert known.status_code == 201
    assert known.json()["blocked_by"] == ["c1.ct"]
    assert harness.client.post("/api/cases/nope/tasks", json=body, headers=COORDINATOR).status_code == 404


def test_ad_hoc_task_can_be_confirmed_and_performed(harness: Harness) -> None:
    created = harness.client.post(
        f"/api/cases/{CASE_ID}/tasks",
        json={"title": "Doplnit ECOG", "owner_role": "koc_physician"},
        headers=COORDINATOR,
    ).json()
    step = created["id"].split(".", 1)[1]

    assert harness.move(step, "confirm", date="2026-10-05").status_code == 409  # no place known: guard refuses
    confirmed = harness.move(step, "confirm", date="2026-10-05", place="KOC 2")
    assert confirmed.status_code == 200
    assert harness.move(step, "perform", headers=PHYSICIAN).json()["business_status"] == "provedeno"


# --- demo role header ---


def test_unknown_or_unselectable_roles_are_401(harness: Harness) -> None:
    for role in ("wizard", "system", "patient", "external_workplace"):
        assert harness.launch(headers={"X-Demo-Role": role}).status_code == 401, role
    assert harness.store.resources == {}


def test_the_seeded_reviewer_can_log_in_but_sees_no_case_content(harness: Harness) -> None:
    reviewer = {"X-Demo-Role": "reviewer"}

    kocs = harness.client.get("/api/directory/kocs", headers=reviewer)
    board = harness.client.get(f"/api/cases/{CASE_ID}/board", headers=reviewer)
    alerts = harness.client.get(f"/api/cases/{CASE_ID}/alerts", headers=reviewer)

    assert kocs.status_code == 200
    assert board.status_code == 403
    assert alerts.status_code == 403
    assert harness.launch(headers=reviewer).status_code == 403


OUTSIDER = PartyRef(id="fiala-daniel@koc1-nemocnice-severni", display="MUDr. Fiala", role=Role.EXTERNAL_WORKPLACE)


def _service(harness: Harness) -> CoordinationService:
    return CoordinationService(
        FakeReader(at("2026-10-21T08:00:00")),  # type: ignore[arg-type]
        harness.store,  # type: ignore[arg-type]
        lambda: at("2026-10-02T09:00:00"),
        FakeProvider(),  # type: ignore[arg-type]
    )


def test_the_referring_gp_reads_the_board(harness: Harness) -> None:
    harness.launch()
    for path in ("board", "alerts"):
        assert harness.client.get(f"/api/cases/{CASE_ID}/{path}", headers=GP).status_code == 200


async def test_only_participants_of_the_case_read_or_move_it(harness: Harness) -> None:
    harness.launch()
    service = _service(harness)
    with pytest.raises(ForbiddenError):
        await service.board(CASE_ID, OUTSIDER)
    with pytest.raises(ForbiddenError):
        await service.alerts(CASE_ID, OUTSIDER)
    with pytest.raises(ForbiddenError):
        await service.transition("c1.ct", TransitionRequest(event="confirm", date=date(2026, 10, 8)), OUTSIDER)
    assert harness.store.saves == []
