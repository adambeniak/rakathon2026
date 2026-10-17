"""POST /api/demo/advance: replays the story steps through the task machine; demo mode only, idempotent, audited."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_coordination, get_directory_provider, get_fhir_client, get_iris_pool, get_repository
from app.api.services.coordination import CoordinationService
from app.api.services.demo_story import STORY
from app.domain import clock
from app.domain.common import Role
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.main import create_app
from app.seed.demo_case import DOCUMENTS
from app.settings import Settings
from tests.unit.api.test_coordination import (
    CASE_ID,
    COORDINATOR,
    GP,
    LAUNCH,
    FakeProvider,
    FakeReader,
    FakeStore,
    at,
)
from tests.unit.api.test_demo_clock import FakeRepository

URL = f"/api/demo/advance?case_id={CASE_ID}&to=2026-10-16"
STORY_DOCS = {step.result_doc_id: step.result_at for step in STORY}


class ScopedStore(FakeStore):
    """`list_for_case` answers for one case (the real store filters by `partOf`); `list_open_everywhere` does not."""

    async def list_for_case(self, case_task_reference: str) -> list[Any]:
        return [s for s in await super().list_for_case(case_task_reference) if s.task.case_id == CASE_ID]

    async def list_open_everywhere(self) -> list[Any]:
        from app.domain.board import due_order
        from app.domain.task_machine import OPEN_STATUSES
        from app.fhir.mappers.task import task_from_fhir
        from app.fhir.tasks import StoredTask

        stored = [StoredTask(task_from_fhir(r), r) for r in self.resources.values()]
        return sorted((s for s in stored if s.task.status in OPEN_STATUSES), key=lambda s: due_order(s.task))


class Harness:
    def __init__(self, client: TestClient, store: FakeStore, repository: FakeRepository) -> None:
        self.client, self.store, self.repository = client, store, repository

    def launch(self) -> None:
        response = self.client.post(f"/api/cases/{CASE_ID}/pathways", json=LAUNCH, headers=COORDINATOR)
        assert response.status_code == 201

    def advance(self, to: str = "2026-10-16", headers: dict[str, str] = COORDINATOR) -> Any:
        return self.client.post(f"/api/demo/advance?case_id={CASE_ID}&to={to}", headers=headers)

    def task(self, step: str) -> dict[str, Any]:
        board = self.client.get(f"/api/cases/{CASE_ID}/board", headers=COORDINATOR).json()
        return next(t for lane in board["lanes"] for t in lane["tasks"] if t["id"] == f"{CASE_ID}.{step}")

    def alerts(self) -> list[dict[str, Any]]:
        body: list[dict[str, Any]] = self.client.get(f"/api/cases/{CASE_ID}/alerts", headers=COORDINATOR).json()
        return body


def make(settings: Settings) -> Iterator[Harness]:
    app = create_app(settings)
    store = ScopedStore()
    store.documents = dict(STORY_DOCS)
    repository = FakeRepository()
    reader = FakeReader(mdt_start=at("2026-10-21T08:00:00"))
    clock.set_override(at("2026-10-02T09:00:00"))
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_fhir_client] = lambda: object()
    app.dependency_overrides[get_iris_pool] = lambda: object()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_coordination] = lambda: CoordinationService(
        reader,  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        clock.now,
        FakeProvider(),  # type: ignore[arg-type]
    )
    try:
        with TestClient(app) as client:
            yield Harness(client, store, repository)
    finally:
        clock.set_override(None)


@pytest.fixture
def harness(settings: Settings) -> Iterator[Harness]:
    yield from make(settings)


def test_at_16_october_only_the_histology_is_overdue(harness: Harness) -> None:
    harness.launch()

    response = harness.advance()

    assert response.status_code == 200
    body = response.json()
    assert body["now"] == "2026-10-16T09:00:00+02:00"
    assert body["overridden"] is True
    assert {a["task_id"]: a["events"] for a in body["applied"]} == {
        f"{CASE_ID}.ct": ["order_confirmed", "accept", "start", "performed", "result_delivered"],
        f"{CASE_ID}.eus-fnb": ["order_confirmed", "accept", "start", "performed", "result_delivered"],
        f"{CASE_ID}.labs": ["order_confirmed", "accept", "start", "performed", "result_delivered"],
        f"{CASE_ID}.histology": ["order_confirmed", "accept"],
    }
    assert body["skipped"] == []
    assert body["escalated"] == [f"{CASE_ID}.histology"]
    assert [a["task_id"] for a in harness.alerts()] == [f"{CASE_ID}.histology"]
    assert harness.alerts()[0]["kind"] == "sla_breach"
    for step in ("ct", "eus-fnb", "labs"):
        task = harness.task(step)
        assert (task["status"], task["business_status"]) == ("completed", "vysledek_dorucen")
    histology = harness.task("histology")
    assert (histology["status"], histology["business_status"]) == ("accepted", "potvrzeno")


def test_it_is_idempotent(harness: Harness) -> None:
    harness.launch()
    harness.advance()
    saves = len(harness.store.saves)

    again = harness.advance().json()

    assert again["applied"] == []
    assert again["escalated"] == []  # escalated once
    assert len(harness.store.saves) == saves


def test_earlier_target_applies_only_what_had_happened(harness: Harness) -> None:
    harness.launch()

    body = harness.advance("2026-10-09").json()

    assert {a["task_id"]: a["events"][-1] for a in body["applied"]} == {
        f"{CASE_ID}.ct": "result_delivered",
        f"{CASE_ID}.eus-fnb": "accept",  # ordered on 8. 10., examination on 12. 10.
    }
    assert body["now"] == "2026-10-09T09:00:00+02:00"


def test_continuing_to_19_october_delivers_the_histology(harness: Harness) -> None:
    harness.launch()
    harness.advance()

    body = harness.advance("2026-10-19T17:00:00").json()

    assert [a["task_id"] for a in body["applied"]] == [f"{CASE_ID}.histology"]
    assert body["applied"][0]["events"] == ["start", "performed", "result_delivered"]


def test_only_events_of_the_task_machine_are_written(harness: Harness) -> None:
    harness.launch()

    harness.advance()

    descriptions = [s["description"] for s in harness.store.saves]
    replay = [d for d in descriptions if d.endswith("; demo replay")]
    assert len(replay) == 4  # one save per step through the machine ...
    assert "order_confirmed + accept + start + performed + result_delivered" in replay[0]
    assert descriptions[len(replay) :] == [  # ... then the watchdog round, nothing else
        f"task {CASE_ID}.histology: overdue escalation (sla, 1 working day(s) after 2026-10-15); demo advance"
    ]


def test_replayed_steps_say_they_were_recorded_on_behalf(harness: Harness) -> None:
    harness.launch()

    harness.advance()

    saves = {s["task"]: s for s in harness.store.saves if s["description"].endswith("; demo replay")}
    for step in ("ct", "eus-fnb", "labs"):
        resource = harness.store.resources[f"{CASE_ID}.{step}"]
        assert resource["status"] == "completed"
        assert saves[f"{CASE_ID}.{step}"]["on_behalf_of"]  # named on the AuditEvent
        assert "on behalf of the external workplace" in saves[f"{CASE_ID}.{step}"]["description"]
    ct = harness.store.resources[f"{CASE_ID}.ct"]
    assert any(n["text"] == "Demo: přehráno ze scénáře." for n in ct.get("note", []))
    assert saves[f"{CASE_ID}.histology"]["on_behalf_of"] is None  # only confirmed and accepted: the coordinator's own


def test_escalation_stays_inside_the_case(harness: Harness) -> None:
    harness.launch()
    other = Task(
        id="other-case.exam",
        case_id="other-case",
        code="x",
        title="Cizí případ",
        status=TaskStatus.REQUESTED,
        business_status=TaskBusinessStatus.OBJEDNANO,
        owner_role=Role.EXTERNAL_WORKPLACE,
        due=at("2026-10-01T23:59:59"),
    )
    harness.store._stored(other, "900")

    body = harness.advance().json()

    assert body["escalated"] == [f"{CASE_ID}.histology"]
    assert all(s["task"] != "other-case.exam" for s in harness.store.saves)


def test_a_failed_audit_leaves_the_clock_and_a_retry_succeeds(harness: Harness) -> None:
    harness.launch()
    real_create = harness.repository.create

    async def fail(resource: dict[str, Any]) -> None:
        raise RuntimeError("audit store down")

    harness.repository.create = fail  # type: ignore[method-assign]
    assert harness.advance().status_code == 500
    assert clock.now() == at("2026-10-02T09:00:00")

    harness.repository.create = real_create  # type: ignore[method-assign]
    retry = harness.advance()

    assert retry.status_code == 200
    assert retry.json()["applied"] == []  # the replay had already happened
    assert clock.now() == at("2026-10-16T09:00:00")


def test_a_failed_escalation_save_does_not_fail_the_call(harness: Harness) -> None:
    harness.launch()
    real_save = harness.store.save

    async def save(stored: Any, task: Task, **kwargs: Any) -> Any:
        if "overdue escalation" in kwargs["description"]:
            raise RuntimeError("store down")
        return await real_save(stored, task, **kwargs)

    harness.store.save = save  # type: ignore[method-assign]

    response = harness.advance()

    assert response.status_code == 200
    assert response.json()["escalated"] == []  # left to the background watchdog
    assert clock.now() == at("2026-10-16T09:00:00")


def test_a_missing_result_document_is_reported_not_invented(harness: Harness) -> None:
    harness.launch()
    del harness.store.documents["08_CT_KOC1_2026-10-08"]

    body = harness.advance().json()

    skipped = {s["task_id"]: s["reason"] for s in body["skipped"]}
    assert skipped[f"{CASE_ID}.ct"] == "Dokument 08_CT_KOC1_2026-10-08 není u pacienta nahrán."
    assert "nelze provést" in skipped[f"{CASE_ID}.eus-fnb"]  # depends on the CT being completed
    assert harness.task("ct")["business_status"] == "provedeno"


def test_without_a_launched_pathway_it_is_a_czech_422_and_the_clock_stays(harness: Harness) -> None:
    response = harness.advance()

    assert response.status_code == 422
    assert response.json()["detail"] == "Sada vyšetření není pro případ spuštěná."
    assert clock.now() == at("2026-10-02T09:00:00")
    assert harness.repository.created == []


def test_the_move_is_audited_without_patient(harness: Harness) -> None:
    harness.launch()

    harness.advance()

    [audit] = harness.repository.created
    assert audit["subtype"][0]["code"] == "demo-advance"
    assert audit["outcomeDesc"] == f"demo advanced to 2026-10-16T09:00:00+02:00 for case {CASE_ID}: 4 step(s) replayed"
    assert "entity" not in audit


def test_only_the_coordinator_may_advance(harness: Harness) -> None:
    harness.launch()

    response = harness.advance(headers=GP)

    assert response.status_code == 403
    assert clock.now() == at("2026-10-02T09:00:00")


@pytest.mark.parametrize("to", ["tomorrow", "2019-01-01", "9999-12-31", "2026-13-01"])
def test_implausible_targets_are_422(harness: Harness, to: str) -> None:
    harness.launch()

    assert harness.advance(to).status_code == 422


def test_404_outside_demo_mode(settings: Settings) -> None:
    settings = settings.model_copy(update={"stafeta_demo_mode": False})
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.post(URL).status_code == 404
        assert client.post(URL, headers=COORDINATOR).status_code == 404


def test_story_result_times_are_the_receipt_times_of_the_seeded_reports() -> None:
    received = {d.doc_id: d.received_at for d in DOCUMENTS}
    assert {step.result_doc_id: step.result_at for step in STORY} == {k: received[k] for k in STORY_DOCS}
