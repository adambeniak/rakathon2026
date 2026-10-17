"""#132 as the dress rehearsal ran it: reports uploaded first, pathway launched, advance to 16. 10., clock to 21. 10.

The histology report (11) is in the case; once the clock passes its receipt the step shows `vysledek_dorucen`, the
board stops showing it overdue and `/alerts` drops the `sla_breach`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest

from app.api.services.coordination import CoordinationService
from app.api.watchdog import run_once
from app.domain import clock
from app.domain.common import PartyRef, Role
from app.domain.document import SourceDocument
from app.settings import Settings
from tests.unit.api.test_coordination import CASE_ID, FakeProvider
from tests.unit.api.test_demo_advance import Harness, make
from tests.unit.api.test_demo_advance import at as prague

HISTOLOGY_DOC = "11_Histologie_KOC2_2026-10-19"
COORDINATOR = PartyRef(id="dvorakova-lucie@koc2-nemocnice-lipova", display="Bc. Lucie Dvořáková", role=Role.COORDINATOR)


def doc(doc_id: str, type_code: str, authored: date, received: str) -> SourceDocument:
    return SourceDocument(
        doc_id=doc_id, title=doc_id, type_code=type_code, authored_at=authored, received_at=prague(received)
    )


# As uploaded in demo step 3 (clock 20. 10. 09:00), before the pathway exists; plus older reports of the same types.
UPLOADED = [
    doc("02_Laborator_2026-09-01", "11502-2", date(2026, 9, 1), "2026-10-20T09:00:00"),
    doc("06_UZ_bricha_2026-09-29", "18748-4", date(2026, 9, 29), "2026-10-20T09:00:00"),
    doc(HISTOLOGY_DOC, "11526-1", date(2026, 10, 19), "2026-10-20T09:01:00"),
]


@pytest.fixture
def harness(settings: Settings) -> Iterator[Harness]:
    for h in make(settings):
        h.store.result_documents = list(UPLOADED)
        yield h


def service(h: Harness) -> CoordinationService:
    from tests.unit.api.test_coordination import FakeReader

    return CoordinationService(
        FakeReader(mdt_start=prague("2026-10-21T08:00:00")),  # type: ignore[arg-type]
        h.store,  # type: ignore[arg-type]
        clock.now,
        FakeProvider(),  # type: ignore[arg-type]
    )


def test_at_16_october_a_report_uploaded_later_does_not_complete_the_histology(harness: Harness) -> None:
    harness.launch()

    body = harness.advance().json()

    assert f"{CASE_ID}.histology" not in {a["task_id"] for a in body["applied"] if "result_delivered" in a["events"]}
    histology = harness.task("histology")
    assert (histology["status"], histology["overdue"]) == ("accepted", True)
    assert [a["kind"] for a in harness.alerts()] == ["sla_breach"]


async def test_on_21_october_the_watchdog_completes_the_histology_and_the_alert_is_gone(harness: Harness) -> None:
    harness.launch()
    harness.advance()
    clock.set_override(prague("2026-10-21T09:00:00"))  # the date switcher: PUT /demo/clock only

    escalated = await run_once(harness.store, clock.now())  # type: ignore[arg-type]

    assert escalated == []
    histology = harness.task("histology")
    assert (histology["status"], histology["business_status"]) == ("completed", "vysledek_dorucen")
    assert histology["result_doc_id"] == HISTOLOGY_DOC
    assert histology["overdue"] is False
    assert harness.alerts() == []
    [save] = [s for s in harness.store.saves if s["task"] == f"{CASE_ID}.histology" and "system" in s["description"]]
    assert "start + performed + result_delivered" in save["description"]
    assert HISTOLOGY_DOC in save["description"]
    # the older lab and ultrasound reports did not touch the steps the replay already closed with 08-10
    assert harness.task("labs")["result_doc_id"] == "10_Laborator_KOC2_2026-10-15"
    assert harness.task("ct")["result_doc_id"] == "08_CT_KOC1_2026-10-08"

    saves = len(harness.store.saves)
    assert await run_once(harness.store, clock.now()) == []  # type: ignore[arg-type]
    assert len(harness.store.saves) == saves  # idempotent


async def test_the_upload_path_completes_the_step_when_its_report_arrives(harness: Harness) -> None:
    harness.launch()
    harness.advance()
    harness.store.result_documents = []  # report 11 not uploaded yet
    clock.set_override(prague("2026-10-19T16:00:00"))
    assert await service(harness).deliver_received_results(CASE_ID, COORDINATOR) == []

    harness.store.result_documents = [doc(HISTOLOGY_DOC, "11526-1", date(2026, 10, 19), "2026-10-19T16:00:00")]
    [step] = await service(harness).deliver_received_results(CASE_ID, COORDINATOR)

    assert (step.task_id, step.events) == (f"{CASE_ID}.histology", ["start", "performed", "result_delivered"])
    assert harness.task("histology")["business_status"] == "vysledek_dorucen"
    assert harness.alerts() == []


async def test_a_failed_save_leaves_the_step_for_the_next_round(harness: Harness) -> None:
    harness.launch()
    harness.advance()
    clock.set_override(prague("2026-10-21T09:00:00"))
    real_save = harness.store.save

    async def save(stored, task, **kwargs):  # type: ignore[no-untyped-def]
        if "recorded by the system" in kwargs["description"]:
            raise RuntimeError("store down")
        return await real_save(stored, task, **kwargs)

    harness.store.save = save  # type: ignore[method-assign]
    assert await service(harness).deliver_received_results(CASE_ID, COORDINATOR) == []
    assert harness.task("histology")["status"] == "accepted"

    harness.store.save = real_save  # type: ignore[method-assign]
    assert [s.task_id for s in await service(harness).deliver_received_results(CASE_ID, COORDINATOR)] == [
        f"{CASE_ID}.histology"
    ]
