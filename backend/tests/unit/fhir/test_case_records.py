"""CaseRecordsReader against a mocked IRIS: audit trail, timeline sources and messages, with fixtures built by the
real write-side mappers (what the workflow writes is what the reader reads back)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import pytest
import respx

from app.domain.activity import MessageKind
from app.domain.common import PartyRef, Role
from app.domain.events import DomainEvent, EventKind
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.fhir import case_records
from app.fhir.audit import build_audit_event, build_domain_audit_event
from app.fhir.case_records import CaseRecordsReader
from app.fhir.cases import LoadedCase
from app.fhir.client import FhirClient
from app.fhir.mappers.document_request import communication_request_to_fhir, request_task_to_fhir
from app.fhir.mappers.feedback import feedback_communication_to_fhir
from app.fhir.mappers.task import task_to_fhir
from app.fhir.repository import FhirRepository
from app.security.actor import SYSTEM_ACTOR
from app.settings import PRAGUE
from tests.conftest import FHIR_BASE
from tests.directory_fixtures import demo_directory
from tests.unit.fhir.test_cases_reader import CASE, DOCUMENT, TASK

CASE_ID = "rakathon-2026-prochazkova"
COORDINATOR = PartyRef(id="dvorakova-lucie@koc2-nemocnice-lipova", display="Bc. Lucie Dvořáková", role=Role.COORDINATOR)
LOADED = LoadedCase(task=TASK, episode={"resourceType": "EpisodeOfCare", "id": "4"}, case=CASE)
DIRECTORY = demo_directory()
LAB = next(o for o in DIRECTORY.orgs if o.org.name.startswith("Laborato"))
GP = DIRECTORY.roles[0]
SENT_AT = datetime(2026, 10, 2, 11, 30, tzinfo=PRAGUE)
REQUEST_ID = f"{CASE_ID}-req-1"
SECRET_REASON = "volný text důvodu, který API nikdy nevrací"

REQUEST_TASK = {
    **request_task_to_fhir(
        Task(
            id=REQUEST_ID,
            case_id=CASE_ID,
            code="request-report",
            title="Vyžádat výsledek: RTG plic 3. 9. 2026",
            status=TaskStatus.COMPLETED,
            business_status=TaskBusinessStatus.VYSLEDEK_DORUCEN,
            owner=COORDINATOR,
            due=datetime(2026, 10, 6, 23, 59, tzinfo=PRAGUE),
            location="Radiologické centrum Modřany",
            result_doc_id="07_PL_zadost_KOC2_2026-10-02",
        ),
        case_task_reference="Task/5",
        patient_reference="Patient/3",
        communication_request_reference="CommunicationRequest/31",
        owner_reference="PractitionerRole/2",
        recipient_reference=LAB.ref,
        exam_date=date(2026, 9, 3),
        result_document_reference="DocumentReference/9",
    ),
    "id": "21",
}
STEP_TASK = {
    **task_to_fhir(
        Task(
            id=f"{CASE_ID}-ct",
            case_id=CASE_ID,
            code="ct-staging",
            title="CT stagingu",
            status=TaskStatus.IN_PROGRESS,
            scheduled_at=datetime(2026, 10, 14, 10, 0, tzinfo=PRAGUE),
            location="KOC 1 – radiologie",
            escalated_at=datetime(2026, 10, 16, 8, 0, tzinfo=PRAGUE),
        ),
        case_task_reference="Task/5",
        patient_reference="Patient/3",
    ),
    "id": "22",
}
COMM_REQUEST = {
    **communication_request_to_fhir(
        REQUEST_ID,
        label="RTG plic 3. 9. 2026",
        exam_date=date(2026, 9, 3),
        patient_reference="Patient/3",
        episode_reference="EpisodeOfCare/4",
        requester=COORDINATOR,
        requester_reference="PractitionerRole/2",
        recipient_reference=LAB.ref,
        authored_on=SENT_AT,
    ),
    "id": "31",
    "status": "completed",
}
OTHER_CASE_REQUEST = {**COMM_REQUEST, "id": "33", "about": [{"reference": "EpisodeOfCare/99"}]}
FEEDBACK = {
    **feedback_communication_to_fhir(
        CASE_ID,
        patient_reference="Patient/3",
        episode_reference="EpisodeOfCare/4",
        sender=COORDINATOR,
        sender_reference="PractitionerRole/2",
        recipient_reference=GP.ref,
        sent_at=datetime(2026, 10, 21, 11, 0, tzinfo=PRAGUE),
        message_id="<abc@stafeta>",
        body="Dobrý den, zpětná vazba z MDT je v portálu.",
    ),
    "id": "32",
}


def _domain(code: str, at: datetime, entities: list[str], actor: PartyRef = COORDINATOR, **payload: Any) -> dict:
    event = DomainEvent(EventKind.AUDIT, "update", at, {"event": code, "case_id": CASE_ID, **payload})
    return build_domain_audit_event(event, actor=actor, entities=entities)


AUDIT_EVENTS = [
    {
        **_domain(
            "accept", datetime(2026, 10, 2, 9, 40, tzinfo=PRAGUE), ["Task/5"], **{"from": "odeslano"}, to="triage"
        ),
        "id": "a1",
    },
    {
        **_domain(
            "missing_found",
            datetime(2026, 10, 9, 9, 0, tzinfo=PRAGUE),
            ["Task/5"],
            reason=SECRET_REASON,
            **{"from": "kompletni"},
            to="ceka_na_podklady",
        ),
        "id": "a2",
    },
    {**_domain("request_report", SENT_AT, ["Task/21", "Task/5"], task_id=REQUEST_ID), "id": "a3"},
    {
        **_domain(
            "report_received",
            datetime(2026, 10, 3, 10, 0, tzinfo=PRAGUE),
            ["Task/21", "DocumentReference/9"],
            task_id=REQUEST_ID,
            result_doc_id="07_PL_zadost_KOC2_2026-10-02",
        ),
        "id": "a4",
    },
    {
        **_domain(
            "delivery_confirmed",
            datetime(2026, 10, 21, 11, 0, tzinfo=PRAGUE),
            ["Task/5"],
            actor=SYSTEM_ACTOR,
            receipt_id="<abc@stafeta>",
        ),
        "id": "a5",
    },
    {
        **build_audit_event(
            action="R",
            subtype="read",
            actor=COORDINATOR,
            entities=["Task/5", "Patient/3", "EpisodeOfCare/4"],
            recorded=datetime(2026, 10, 21, 12, 0, tzinfo=UTC),
        ),
        "id": "a6",
    },
    {
        **build_audit_event(
            action="C",
            subtype="create",
            actor=COORDINATOR,
            entities=["Task/5"],
            recorded=datetime(2026, 10, 21, 7, 0, tzinfo=UTC),
            description="MDT record exported as DOCX",
        ),
        "id": "a7",
    },
]


def _bundle(*resources: dict[str, Any]) -> dict[str, Any]:
    return {"resourceType": "Bundle", "entry": [{"resource": r} for r in resources]}


@pytest.fixture
def records(fhir_client: FhirClient) -> CaseRecordsReader:
    return CaseRecordsReader(FhirRepository(fhir_client, COORDINATOR, clock=lambda: datetime(2026, 10, 21, tzinfo=UTC)))


@pytest.fixture
def iris() -> respx.MockRouter:
    with respx.mock(base_url=FHIR_BASE, assert_all_called=False) as router:
        router.post("/AuditEvent").respond(201, headers={"Location": f"{FHIR_BASE}/AuditEvent/99"})
        router.get("/Task").respond(200, json=_bundle(REQUEST_TASK, STEP_TASK))
        router.get("/DocumentReference").respond(200, json=_bundle(DOCUMENT))
        router.get("/CommunicationRequest").respond(200, json=_bundle(COMM_REQUEST, OTHER_CASE_REQUEST))
        router.get("/Communication").respond(200, json=_bundle(FEEDBACK))
        router.get("/AuditEvent").respond(200, json=_bundle(*AUDIT_EVENTS))
        yield router


def _written_audit(iris: respx.MockRouter) -> dict[str, Any]:
    return json.loads(iris.routes[0].calls[-1].request.content)


async def test_audit_trail_is_newest_first_with_codes_and_no_free_text(
    records: CaseRecordsReader, iris: respx.MockRouter
) -> None:
    trail = await records.audit_trail(LOADED)

    assert [r.operation for r in trail.records] == [
        "read",  # 12:00 UTC = 14:00 Prague
        "delivery_confirmed",
        "export",  # 07:00 UTC = 09:00 Prague
        "missing_found",
        "report_received",
        "request_report",
        "accept",
    ]
    read, delivered = trail.records[0], trail.records[1]
    assert (read.action, read.actor_display, read.actor_role) == ("R", "Bc. Lucie Dvořáková", Role.COORDINATOR)
    assert read.entity_types == ("Task", "Patient", "EpisodeOfCare")
    assert not read.workflow_event
    assert delivered.workflow_event
    assert delivered.actor_role is Role.SYSTEM
    assert SECRET_REASON not in repr(trail)  # `reason` detail never leaves the mapper


async def test_audit_trail_searches_every_record_of_the_case_and_audits_the_read(
    records: CaseRecordsReader, iris: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(case_records, "ENTITY_CHUNK", 3)

    trail = await records.audit_trail(LOADED)

    searched = [c.request.url.params["entity"] for c in iris.routes[5].calls]
    assert ",".join(searched).split(",") == [
        "Task/5",
        "EpisodeOfCare/4",
        "Task/21",
        "Task/22",
        "DocumentReference/9",
        "CommunicationRequest/31",
        "Communication/32",
    ]
    assert len(searched) == 3  # chunks of ENTITY_CHUNK
    assert len(trail.records) == len(AUDIT_EVENTS)  # merged by id across chunks
    audit = _written_audit(iris)
    assert (audit["action"], audit["subtype"][0]["code"]) == ("E", "search-type")
    assert {e["what"]["reference"] for e in audit["entity"]} == {"Task/5", "Patient/3", "EpisodeOfCare/4"}


async def test_timeline_sources_read_business_events_steps_requests_and_documents(
    records: CaseRecordsReader, iris: respx.MockRouter
) -> None:
    sources = await records.timeline_sources(LOADED)

    params = iris.routes[5].calls[0].request.url.params
    assert params["type"].endswith("audit-type|domain-event")
    assert params["entity"].split(",") == ["Task/5", "Task/21", "Task/22"]
    by_code = {e.code: e for e in sources.events}
    assert by_code["accept"].on_case
    assert (by_code["accept"].from_state, by_code["accept"].to_state) == (
        "odeslano",
        "triage",
    )
    assert not by_code["report_received"].on_case
    assert by_code["report_received"].result_doc_id == "07_PL_zadost_KOC2_2026-10-02"
    assert by_code["delivery_confirmed"].receipt_id == "<abc@stafeta>"
    assert "read" not in by_code
    assert "export" not in by_code
    assert SECRET_REASON not in repr(sources)
    [step] = sources.steps
    assert step.scheduled_at == datetime(2026, 10, 14, 10, 0, tzinfo=PRAGUE)
    [request] = sources.requests
    assert (request.label, request.sent_at, request.status) == ("RTG plic 3. 9. 2026", SENT_AT, "completed")
    assert [d.doc_id for d in sources.documents] == ["07_PL_zadost_KOC2_2026-10-02"]
    audit = _written_audit(iris)
    assert {"DocumentReference/9", "CommunicationRequest/31", "Task/22"} <= {
        e["what"]["reference"] for e in audit["entity"]
    }
    assert iris.routes[4].call_count == 0  # the timeline does not read the feedback e-mail


async def test_messages_are_the_requests_and_the_feedback_of_this_case_only(
    records: CaseRecordsReader, iris: respx.MockRouter
) -> None:
    found = await records.messages(LOADED, DIRECTORY)

    request, feedback = found.messages
    assert (request.kind, request.id, request.recipient) == (MessageKind.DOCUMENT_REQUEST, REQUEST_ID, LAB.org.name)
    assert request.sender == "Bc. Lucie Dvořáková"
    assert request.text == "Žádost o zaslání výsledku vyšetření: RTG plic 3. 9. 2026 (3. 9. 2026)"
    assert (feedback.kind, feedback.receipt_id, feedback.recipient) == (
        MessageKind.MDT_FEEDBACK,
        "<abc@stafeta>",
        GP.display,
    )
    assert found.requests[REQUEST_ID].result_doc_id == "07_PL_zadost_KOC2_2026-10-02"
    assert iris.routes[3].calls[0].request.url.params["subject"] == "Patient/3"
    audit = _written_audit(iris)
    named = {e["what"]["reference"] for e in audit["entity"]}
    assert {"CommunicationRequest/31", "Communication/32", "Task/21"} <= named
    assert "CommunicationRequest/33" not in named  # another case of the patient is neither shown nor named
