"""GET /api/cases/{id}/audit, /timeline, /messages: KOC team of the case only, response shapes, paging.

How the records are read from FHIR (and that every read is audited) is tested in tests/unit/fhir/test_case_records.py;
the merge of the timeline in tests/unit/timeline/test_events.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_case_records
from app.domain.activity import (
    AuditRecord,
    MessageKind,
    MessageRecord,
    RequestRecord,
    WorkflowEvent,
)
from app.domain.common import Role
from app.domain.document import SourceDocument
from app.fhir.case_records import AuditTrail, CaseMessages, TimelineSources
from app.fhir.cases import CaseActivity, LoadedCase
from app.fhir.directory import Directory
from app.settings import PRAGUE, Settings
from tests.unit.api import test_mdt_record_api as mdt
from tests.unit.api.test_mdt_record_api import CaseReader, FakeRepository

BASE = "/api/cases/rakathon-2026-prochazkova"
OPENED = datetime(2026, 10, 22, 7, 0, tzinfo=PRAGUE)
REQUEST_ID = "rakathon-2026-prochazkova-req-1"


def _audit(minute: int, operation: str = "read") -> AuditRecord:
    return AuditRecord(
        recorded=datetime(2026, 10, 21, 9, minute, tzinfo=PRAGUE),
        action="R",
        operation=operation,
        actor_display="Bc. Lucie Dvořáková",
        actor_role=Role.COORDINATOR,
        on_behalf_of=None,
        entity_types=("Task", "EpisodeOfCare"),
        outcome="success",
        workflow_event=False,
    )


class FakeRecords:
    calls: ClassVar[list[str]] = []

    async def audit_trail(self, loaded: LoadedCase) -> AuditTrail:
        self.calls.append("audit")
        return AuditTrail([_audit(m) for m in (50, 40, 30, 20, 10)])

    async def timeline_sources(self, loaded: LoadedCase) -> TimelineSources:
        self.calls.append("timeline")
        late = SourceDocument(
            doc_id="12_Algeziologie_2026-10-26",
            title="Algeziologie",
            authored_at=date(2026, 10, 26),
            received_at=datetime(2026, 10, 26, 14, 0, tzinfo=PRAGUE),
        )
        accept = WorkflowEvent(
            code="accept",
            at=datetime(2026, 10, 2, 9, 40, tzinfo=PRAGUE),
            on_case=True,
            from_state="odeslano",
            to_state="triage",
            actor_display="Bc. Lucie Dvořáková",
        )
        return TimelineSources(documents=[late], steps=[], requests=[], events=[accept])

    async def messages(self, loaded: LoadedCase, directory: Directory) -> CaseMessages:
        self.calls.append("messages")
        request = MessageRecord(
            id=REQUEST_ID,
            kind=MessageKind.DOCUMENT_REQUEST,
            fhir_status="completed",
            sent_at=datetime(2026, 10, 2, 11, 30, tzinfo=PRAGUE),
            sender="Bc. Lucie Dvořáková",
            recipient="Radiologické centrum Modřany",
            text="Žádost o zaslání výsledku vyšetření: RTG plic 3. 9. 2026",
        )
        feedback = MessageRecord(
            id="rakathon-2026-prochazkova@20261021T074500000000Z",
            kind=MessageKind.MDT_FEEDBACK,
            fhir_status="completed",
            sent_at=datetime(2026, 10, 21, 9, 45, tzinfo=PRAGUE),
            sender="Bc. Lucie Dvořáková",
            recipient="MUDr. Tomáš Řezníček",
            text="Dobrý den, zpětná vazba z MDT je v portálu.",
            receipt_id="<abc@stafeta>",
        )
        tracked = RequestRecord(
            task_id=REQUEST_ID,
            label="RTG plic 3. 9. 2026",
            recipient="Radiologické centrum Modřany",
            sent_at=request.sent_at,
            status="completed",
            due=datetime(2026, 10, 6, 23, 59, tzinfo=PRAGUE),
            result_doc_id="03_RTG_plic_2026-09-03",
        )
        return CaseMessages([request, feedback], {REQUEST_ID: tracked})


class OpenedReader(CaseReader):
    async def activity(self, task: object, case: object, *, waivers: bool = True) -> CaseActivity:  # type: ignore[override]
        return CaseActivity(gp_opened_at=OPENED)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    OpenedReader.loads = 0
    FakeRecords.calls.clear()
    for test_client in mdt._client(settings, OpenedReader(mdt_start=mdt.MDT_START), FakeRepository()):
        test_client.app.dependency_overrides[get_case_records] = lambda: FakeRecords()  # type: ignore[attr-defined]
        yield test_client


@pytest.mark.parametrize("part", ["audit", "timeline", "messages"])
@pytest.mark.parametrize("role", ["gp", "reviewer"])
def test_only_the_koc_team_reads_the_case_activity(client: TestClient, part: str, role: str) -> None:
    response = client.get(f"{BASE}/{part}", headers={"X-Demo-Role": role})

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert OpenedReader.loads == 0  # refused by role before any audited read
    assert FakeRecords.calls == []


def test_a_koc_member_of_another_koc_is_refused(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    other_koc = next(o for o in mdt.DIRECTORY.kocs() if o.org.id != mdt.KOC2.org.id)  # type: ignore[union-attr]
    monkeypatch.setattr(mdt, "KOC2", other_koc)  # the case is managed by another KOC than the coordinator's

    response = client.get(f"{BASE}/audit", headers={"X-Demo-Role": "coordinator"})

    assert response.status_code == 403
    assert FakeRecords.calls == []


def test_audit_trail_is_paged_newest_first(client: TestClient) -> None:
    body = client.get(f"{BASE}/audit?limit=2&offset=1", headers={"X-Demo-Role": "koc_physician"}).json()

    assert (body["total"], body["offset"], body["limit"], body["truncated"]) == (5, 1, 2, True)
    assert [i["recorded"] for i in body["items"]] == ["2026-10-21T09:40:00+02:00", "2026-10-21T09:30:00+02:00"]
    assert body["items"][0] == {
        "recorded": "2026-10-21T09:40:00+02:00",
        "actor": "Bc. Lucie Dvořáková",
        "actor_role": "coordinator",
        "on_behalf_of": None,
        "action": "R",
        "operation": "read",
        "workflow_event": False,
        "entity_types": ["Task", "EpisodeOfCare"],
        "outcome": "success",
    }
    assert OpenedReader.loads == 1


def test_audit_limit_is_bounded(client: TestClient) -> None:
    response = client.get(f"{BASE}/audit?limit=501", headers={"X-Demo-Role": "coordinator"})

    assert response.status_code == 422


def test_timeline_carries_as_of_now_and_the_backend_handover_flag(client: TestClient) -> None:
    body = client.get(f"{BASE}/timeline", headers={"X-Demo-Role": "coordinator"}).json()

    assert body["as_of"] == "2026-10-21T08:00:00+02:00"
    assert body["now"] == "2026-10-21T08:00:00+02:00"  # the demo clock of the test settings
    kinds = [e["kind"] for e in body["events"]]
    assert kinds == ["case_event", "mdt_meeting", "document_authored", "document_received"]
    accept = body["events"][0]
    assert (accept["event"], accept["from_state"], accept["to_state"]) == ("accept", "odeslano", "triage")
    assert [e["excluded_from_handover"] for e in body["events"][2:]] == [True, True]
    assert body["events"][2]["date_only"] is True


def test_messages_show_request_state_and_delivery_proof(client: TestClient) -> None:
    request, feedback = client.get(f"{BASE}/messages", headers={"X-Demo-Role": "coordinator"}).json()

    assert (request["kind"], request["status"]) == ("document_request", "fulfilled")
    assert request["request"]["result_doc_id"] == "03_RTG_plic_2026-09-03"
    assert request["delivery"] is None
    assert (feedback["kind"], feedback["status"]) == ("mdt_feedback", "sent")
    assert feedback["delivery"] == {
        "channel": "email",
        "receipt_id": "<abc@stafeta>",
        "gp_opened_at": "2026-10-22T07:00:00+02:00",
    }
    assert feedback["request"] is None


def test_the_three_endpoints_are_in_the_contract(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]

    for part, schema in (("audit", "CaseAuditTrail"), ("timeline", "CaseTimeline")):
        ok = paths[f"/api/cases/{{case_id}}/{part}"]["get"]["responses"]["200"]["content"]["application/json"]
        assert ok["schema"]["$ref"].endswith(schema)
    assert paths["/api/cases/{case_id}/messages"]["get"]["operationId"] == "cases-get_case_messages"
