"""TaskStore and the new repository paths against a mocked IRIS (real mappers build the fixtures)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
import respx

from app.domain.common import PartyRef, Role
from app.domain.errors import ConflictError, InvalidInputError, NotFoundError
from app.domain.pathway import instantiate
from app.domain.task import Task, TaskStatus
from app.fhir.cases import CaseHeader
from app.fhir.client import FhirClient
from app.fhir.errors import FhirConflictError
from app.fhir.mappers.task import task_to_fhir
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_TASK_CODE, EXT_MDT_START, EXT_ON_BEHALF_OF, SID_CASE_STEP, SID_REQUEST_TASK
from app.fhir.tasks import PractitionerRoleRef, TaskStore
from app.security.actor import SYSTEM_ACTOR
from tests.conftest import FHIR_BASE
from tests.unit.domain.conftest import load_plan, load_template, make_case

NOW = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
HEADER = CaseHeader(case=make_case(), task_reference="Task/5", patient_reference="Patient/3")


def bundle(*resources: dict[str, Any]) -> dict[str, Any]:
    return {"resourceType": "Bundle", "entry": [{"resource": r, "search": {"mode": "match"}} for r in resources]}


def audit_ok() -> httpx.Response:
    return httpx.Response(201, headers={"Location": f"{FHIR_BASE}/AuditEvent/99/_history/1"})


def body(call: respx.models.Call) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(call.request.content)
    return data


def stored_resource(task: Task, fhir_id: str, version: str = "1") -> dict[str, Any]:
    resource = task_to_fhir(task, case_task_reference="Task/5", patient_reference="Patient/3")
    return {**resource, "id": fhir_id, "meta": {"versionId": version}}


@pytest.fixture
def repo(fhir_client: FhirClient) -> FhirRepository:
    return FhirRepository(fhir_client, SYSTEM_ACTOR, clock=lambda: NOW)


@pytest.fixture
def store(repo: FhirRepository) -> TaskStore:
    return TaskStore(repo)


@pytest.fixture
def steps() -> list[Task]:
    return instantiate(load_template(), make_case(), date(2026, 10, 2))


PHYSICIAN = PractitionerRoleRef(
    "PractitionerRole/12", "hruby-pavel@koc2-nemocnice-lipova", "doc. MUDr. Pavel Hrubý, Ph.D.", Role.KOC_PHYSICIAN
)
COORDINATOR = PartyRef(id="dvorakova-lucie@koc2-nemocnice-lipova", display="Bc. Lucie Dvořáková", role=Role.COORDINATOR)


@respx.mock
async def test_launch_posts_orders_tasks_care_plan_and_provenance_in_one_transaction(
    store: TaskStore, steps: list[Task]
) -> None:
    count = len(steps)
    response = {
        "resourceType": "Bundle",
        "type": "transaction-response",
        "entry": [{"response": {"status": "201", "location": "CarePlan/100/_history/1"}}]
        + [{"response": {"status": "201", "location": f"ServiceRequest/{300 + i}/_history/1"}} for i in range(count)]
        + [{"response": {"status": "201", "location": f"Task/{200 + i}/_history/1"}} for i in range(count)]
        + [{"response": {"status": "201", "location": "Provenance/400/_history/1"}}],
    }
    tx = respx.post(FHIR_BASE).mock(return_value=httpx.Response(200, json=response))
    audit = respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())

    result = await store.launch_pathway(
        HEADER, load_plan(), steps, date(2026, 10, 2), indication=PHYSICIAN, coordinator=COORDINATOR, recorded=NOW
    )

    sent = body(tx.calls.last)
    assert sent["type"] == "transaction"
    entries = sent["entry"]
    by_type = {
        t: [e for e in entries if e["resource"]["resourceType"] == t]
        for t in ("CarePlan", "ServiceRequest", "Task", "Provenance")
    }
    assert {t: len(v) for t, v in by_type.items()} == {"CarePlan": 1, "ServiceRequest": 7, "Task": 7, "Provenance": 1}
    [care_plan] = by_type["CarePlan"]
    assert care_plan["request"] == {
        "method": "POST",
        "url": "CarePlan",
        "ifNoneExist": "identifier=https://stafeta.example/fhir/sid/careplan|c1.pancreas-dx",
    }
    # The indicating physician is the author of the plan and the requester of every order.
    assert care_plan["resource"]["author"]["reference"] == "PractitionerRole/12"
    assert care_plan["resource"]["author"]["identifier"]["value"] == PHYSICIAN.business_id
    assert {e["resource"]["requester"]["reference"] for e in by_type["ServiceRequest"]} == {"PractitionerRole/12"}
    assert all(e["resource"]["intent"] == "order" for e in by_type["ServiceRequest"])
    assert (
        next(e["request"]["ifNoneExist"] for e in by_type["ServiceRequest"])
        == "identifier=https://stafeta.example/fhir/sid/case-step-order|c1.ct"
    )
    # Every task fulfils its own order; the plan lists the tasks.
    order_urls = {e["resource"]["identifier"][0]["value"]: e["fullUrl"] for e in by_type["ServiceRequest"]}
    assert {
        e["resource"]["identifier"][0]["value"]: e["resource"]["focus"]["reference"] for e in by_type["Task"]
    } == order_urls
    activity_refs = [a["reference"]["reference"] for a in care_plan["resource"]["activity"]]
    assert activity_refs == [e["fullUrl"] for e in by_type["Task"]]
    assert next(e["request"]["ifNoneExist"] for e in by_type["Task"]) == f"identifier={SID_CASE_STEP}|c1.ct"
    assert all(e["resource"]["partOf"] == [{"reference": "Task/5"}] for e in by_type["Task"])
    assert all(e["resource"]["meta"]["tag"] for e in entries)  # demo tag is applied by the repository
    # Provenance: the coordinator acted on behalf of the physician for the plan and every order.
    [provenance] = by_type["Provenance"]
    agent = provenance["resource"]["agent"][0]
    assert agent["who"]["identifier"]["value"] == COORDINATOR.id
    assert agent["onBehalfOf"]["reference"] == "PractitionerRole/12"
    assert provenance["resource"]["target"] == [{"reference": care_plan["fullUrl"]}] + [
        {"reference": url} for url in order_urls.values()
    ]
    assert result.care_plan_id == "100"
    assert result.task_ids["c1.ct"] == "200"
    assert result.service_request_ids["c1.ct"] == "300"
    assert result.provenance_id == "400"
    assert body(audit.calls.last)["outcomeDesc"] == "pathway launched for case c1: 7 steps"


ORDER = {"resourceType": "ServiceRequest", "id": "300", "status": "active", "meta": {"versionId": "2"}}
TX_OK = {"resourceType": "Bundle", "type": "transaction-response", "entry": []}


async def _store_with_order(store: TaskStore, steps: list[Task], *, tx_status: int = 200) -> tuple[Any, Any, Any]:
    """A stored step with an order; returns (stored task, the transaction route, the single Task PUT route)."""
    resource = {**stored_resource(steps[0], "1"), "focus": {"reference": "ServiceRequest/300"}}
    respx.get(f"{FHIR_BASE}/Task").mock(return_value=httpx.Response(200, json=bundle(resource)))
    respx.get(f"{FHIR_BASE}/ServiceRequest/300").mock(return_value=httpx.Response(200, json=ORDER))
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())
    task_put = respx.put(f"{FHIR_BASE}/Task/1").mock(return_value=httpx.Response(200, json={}))
    transaction = respx.post(FHIR_BASE).mock(
        return_value=httpx.Response(tx_status, json=TX_OK if tx_status == 200 else {"resourceType": "OperationOutcome"})
    )
    return await store.get("c1.ct"), transaction, task_put


@pytest.mark.parametrize(
    ("status", "order_status"), [(TaskStatus.COMPLETED, "completed"), (TaskStatus.CANCELLED, "revoked")]
)
@respx.mock
async def test_finishing_a_task_commits_it_with_its_order_and_the_audit_in_one_transaction(
    store: TaskStore, steps: list[Task], status: TaskStatus, order_status: str
) -> None:
    stored, transaction, task_put = await _store_with_order(store, steps)

    await store.save(
        stored,
        stored.task.model_copy(update={"status": status}),
        description="task c1.ct: done",
        on_behalf_of="KOC 1",
    )

    assert task_put.call_count == 0  # no separate write that could succeed alone
    assert transaction.call_count == 1
    task, order, audit = body(transaction.calls.last)["entry"]
    assert task["request"] == {"method": "PUT", "url": "Task/1", "ifMatch": 'W/"1"'}
    assert order["request"] == {"method": "PUT", "url": "ServiceRequest/300", "ifMatch": 'W/"2"'}
    assert order["resource"]["status"] == order_status
    assert audit["request"] == {"method": "POST", "url": "AuditEvent"}
    event = audit["resource"]
    assert [e["what"]["reference"] for e in event["entity"]] == ["Task/1", "ServiceRequest/300"]
    assert event["outcomeDesc"] == "task c1.ct: done"
    assert event["agent"][0]["extension"][0]["url"] == EXT_ON_BEHALF_OF


@pytest.mark.parametrize("status", [TaskStatus.ACCEPTED, TaskStatus.IN_PROGRESS, TaskStatus.FAILED])
@respx.mock
async def test_other_transitions_leave_the_order_alone(store: TaskStore, steps: list[Task], status: TaskStatus) -> None:
    stored, transaction, task_put = await _store_with_order(store, steps)

    await store.save(stored, stored.task.model_copy(update={"status": status}), description="x")

    assert transaction.call_count == 0
    assert task_put.call_count == 1


@respx.mock
async def test_a_stale_order_version_fails_the_whole_write(store: TaskStore, steps: list[Task]) -> None:
    stored, transaction, task_put = await _store_with_order(store, steps, tx_status=412)

    with pytest.raises(FhirConflictError):
        await store.save(stored, stored.task.model_copy(update={"status": TaskStatus.COMPLETED}), description="x")

    assert transaction.call_count == 1
    assert task_put.call_count == 0  # the task is not written without its order


@respx.mock
async def test_report_requests_and_other_tasks_of_the_case_are_not_steps(store: TaskStore, steps: list[Task]) -> None:
    report_request = {
        "resourceType": "Task",
        "id": "9",
        "status": "requested",
        "identifier": [{"system": SID_REQUEST_TASK, "value": "c1.report-1"}],
        "code": {"coding": [{"system": CS_TASK_CODE, "code": "request-report"}]},
    }
    respx.get(f"{FHIR_BASE}/Task").mock(
        return_value=httpx.Response(200, json=bundle(report_request, stored_resource(steps[0], "1")))
    )
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())

    listed = await store.list_for_case("Task/5")

    assert [s.task.id for s in listed] == ["c1.ct"]


@respx.mock
async def test_a_document_without_a_receipt_timestamp_is_refused(store: TaskStore) -> None:
    document = {"resourceType": "DocumentReference", "id": "8"}
    respx.get(f"{FHIR_BASE}/DocumentReference").mock(return_value=httpx.Response(200, json=bundle(document)))
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())

    with pytest.raises(InvalidInputError, match="nemá čas přijetí"):
        await store.patient_document_received_at("Patient/3", "doc-1")


@respx.mock
async def test_receipt_timestamp_of_a_patient_document(store: TaskStore) -> None:
    document = {"resourceType": "DocumentReference", "id": "8", "date": "2026-10-02T09:30:00+02:00"}
    route = respx.get(f"{FHIR_BASE}/DocumentReference").mock(return_value=httpx.Response(200, json=bundle(document)))
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())

    received = await store.patient_document_received_at("Patient/3", "doc-1")

    assert received == datetime(2026, 10, 2, 7, 30, tzinfo=UTC)
    assert route.calls.last.request.url.params["patient"] == "Patient/3"
    route.mock(return_value=httpx.Response(200, json=bundle()))
    assert await store.patient_document_received_at("Patient/3", "doc-1") is None


@respx.mock
async def test_a_lost_launch_race_is_a_conflict(store: TaskStore, steps: list[Task]) -> None:
    count = len(steps)
    matched = {"response": {"status": "200 OK"}}  # the conditional create found the other launch's resource
    response = {"resourceType": "Bundle", "type": "transaction-response", "entry": [matched] * (2 * count + 2)}
    respx.post(FHIR_BASE).mock(return_value=httpx.Response(200, json=response))
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())

    with pytest.raises(ConflictError):
        await store.launch_pathway(
            HEADER, load_plan(), steps, date(2026, 10, 2), indication=PHYSICIAN, coordinator=COORDINATOR, recorded=NOW
        )


@respx.mock
async def test_saving_a_transition_keeps_the_link_to_the_order(store: TaskStore, steps: list[Task]) -> None:
    resource = {**stored_resource(steps[0], "1"), "focus": {"reference": "ServiceRequest/300"}}
    respx.get(f"{FHIR_BASE}/Task").mock(return_value=httpx.Response(200, json=bundle(resource)))
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())
    stored = await store.get("c1.ct")
    put = respx.put(f"{FHIR_BASE}/Task/1").mock(return_value=httpx.Response(200, json={}))

    await store.save(stored, stored.task.model_copy(update={"status": TaskStatus.ACCEPTED}), description="x")

    assert body(put.calls.last)["focus"] == {"reference": "ServiceRequest/300"}


@respx.mock
async def test_list_for_case_sorts_by_due_and_audits_the_read(store: TaskStore, steps: list[Task]) -> None:
    ct, eus, hist = (next(t for t in steps if t.code == c) for c in ("ct-thorax-abdomen", "eus-fnb", "histology"))
    search = respx.get(f"{FHIR_BASE}/Task").mock(
        return_value=httpx.Response(
            200, json=bundle(stored_resource(hist, "3"), stored_resource(eus, "2"), stored_resource(ct, "1"))
        )
    )
    audit = respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())

    stored = await store.list_for_case("Task/5")

    assert [s.task.id for s in stored] == ["c1.ct", "c1.eus-fnb", "c1.histology"]
    assert search.calls.last.request.url.params["part-of"] == "Task/5"
    event = body(audit.calls.last)
    assert event["action"] == "E"
    assert [e["what"]["reference"] for e in event["entity"]] == ["Task/3", "Task/2", "Task/1"]


@respx.mock
async def test_list_for_case_without_tasks_writes_no_audit(store: TaskStore) -> None:
    respx.get(f"{FHIR_BASE}/Task").mock(return_value=httpx.Response(200, json=bundle()))
    audit = respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())
    assert await store.list_for_case("Task/5") == []
    assert audit.call_count == 0


@respx.mock
async def test_get_reads_by_business_id_and_audits(store: TaskStore, steps: list[Task]) -> None:
    respx.get(f"{FHIR_BASE}/Task").mock(
        return_value=httpx.Response(200, json=bundle(stored_resource(steps[0], "1", "4")))
    )
    audit = respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())
    stored = await store.get("c1.ct")
    assert (stored.fhir_id, stored.version_id, stored.task.id) == ("1", "4", "c1.ct")
    assert body(audit.calls.last)["action"] == "R"


@respx.mock
async def test_get_unknown_task_is_not_found(store: TaskStore) -> None:
    respx.get(f"{FHIR_BASE}/Task").mock(return_value=httpx.Response(200, json=bundle()))
    with pytest.raises(NotFoundError):
        await store.get("c1.nope")


@respx.mock
async def test_save_sends_if_match_and_puts_the_transition_on_the_audit(store: TaskStore, steps: list[Task]) -> None:
    respx.get(f"{FHIR_BASE}/Task").mock(
        return_value=httpx.Response(200, json=bundle(stored_resource(steps[0], "1", "4")))
    )
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())
    stored = await store.get("c1.ct")
    put = respx.put(f"{FHIR_BASE}/Task/1").mock(return_value=httpx.Response(200, json={}))

    changed = stored.task.model_copy(update={"status": TaskStatus.ACCEPTED})
    await store.save(stored, changed, description="task c1.ct: accept")

    assert put.calls.last.request.headers["If-Match"] == 'W/"4"'
    sent = body(put.calls.last)
    assert (sent["id"], sent["status"]) == ("1", "accepted")
    assert sent["partOf"] == [{"reference": "Task/5"}]


@respx.mock
async def test_save_audit_event_carries_description_and_workplace(store: TaskStore, steps: list[Task]) -> None:
    respx.get(f"{FHIR_BASE}/Task").mock(return_value=httpx.Response(200, json=bundle(stored_resource(steps[0], "1"))))
    audit = respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())
    stored = await store.get("c1.ct")
    respx.put(f"{FHIR_BASE}/Task/1").mock(return_value=httpx.Response(200, json={}))

    await store.save(stored, stored.task, description="task c1.ct: performed", on_behalf_of="KOC 1")

    event = body(audit.calls.last)
    assert event["action"] == "U"
    assert event["outcomeDesc"] == "task c1.ct: performed"
    assert event["agent"][0]["extension"][0]["url"] == EXT_ON_BEHALF_OF


@respx.mock
async def test_concurrent_change_is_a_conflict(store: TaskStore, steps: list[Task]) -> None:
    respx.get(f"{FHIR_BASE}/Task").mock(return_value=httpx.Response(200, json=bundle(stored_resource(steps[0], "1"))))
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())
    stored = await store.get("c1.ct")
    respx.put(f"{FHIR_BASE}/Task/1").mock(return_value=httpx.Response(412, json={"resourceType": "OperationOutcome"}))
    with pytest.raises(FhirConflictError):
        await store.save(stored, stored.task, description="x")


@respx.mock
async def test_plan_definition_is_looked_up_by_url(store: TaskStore) -> None:
    plan = {**load_plan(), "id": "9"}
    search = respx.get(f"{FHIR_BASE}/PlanDefinition").mock(return_value=httpx.Response(200, json=bundle(plan)))
    assert (await store.get_plan_definition(plan["url"]))["id"] == "9"
    assert search.calls.last.request.url.params["url"] == plan["url"]
    respx.get(f"{FHIR_BASE}/PlanDefinition").mock(return_value=httpx.Response(200, json=bundle()))
    with pytest.raises(NotFoundError):
        await store.get_plan_definition("https://stafeta.example/fhir/PlanDefinition/none")


@respx.mock
async def test_list_open_everywhere_skips_finished_steps(store: TaskStore, steps: list[Task]) -> None:
    done = steps[0].model_copy(update={"status": TaskStatus.COMPLETED})
    calls = iter(
        [
            httpx.Response(200, json=bundle({"resourceType": "Task", "id": "5"})),
            httpx.Response(200, json=bundle(stored_resource(done, "1"), stored_resource(steps[1], "2"))),
        ]
    )
    respx.get(f"{FHIR_BASE}/Task").mock(side_effect=lambda _request: next(calls))
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())
    open_tasks = await store.list_open_everywhere()
    assert [s.task.id for s in open_tasks] == ["c1.eus-fnb"]


@respx.mock
async def test_ensure_by_url_creates_once_without_the_client_id(repo: FhirRepository) -> None:
    plan = load_plan()
    respx.get(f"{FHIR_BASE}/PlanDefinition").mock(return_value=httpx.Response(200, json=bundle()))
    create = respx.post(f"{FHIR_BASE}/PlanDefinition").mock(
        return_value=httpx.Response(201, headers={"Location": f"{FHIR_BASE}/PlanDefinition/9/_history/1"})
    )
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())

    result = await repo.ensure_by_url(plan)

    assert (result.reference, result.created) == ("PlanDefinition/9", True)
    assert create.calls.last.request.headers["If-None-Exist"] == f"url={plan['url']}"
    assert "id" not in body(create.calls.last)


@respx.mock
async def test_ensure_by_url_existing_writes_nothing(repo: FhirRepository) -> None:
    respx.get(f"{FHIR_BASE}/PlanDefinition").mock(
        return_value=httpx.Response(200, json=bundle({**load_plan(), "id": "9"}))
    )
    posts = respx.post(url__startswith=FHIR_BASE)
    result = await repo.ensure_by_url(load_plan())
    assert (result.reference, result.created) == ("PlanDefinition/9", False)
    assert posts.call_count == 0


@respx.mock
async def test_watchdog_listing_writes_no_audit_event_per_round(store: TaskStore, steps: list[Task]) -> None:
    calls = iter(
        [
            httpx.Response(200, json=bundle({"resourceType": "Task", "id": "5"})),
            httpx.Response(200, json=bundle(stored_resource(steps[0], "1"))),
        ]
    )
    respx.get(f"{FHIR_BASE}/Task").mock(side_effect=lambda _request: next(calls))
    audit = respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())

    assert len(await store.list_open_everywhere()) == 1
    assert audit.call_count == 0


@respx.mock
async def test_two_plan_definitions_with_one_url_are_a_conflict(store: TaskStore) -> None:
    plan = load_plan()
    respx.get(f"{FHIR_BASE}/PlanDefinition").mock(
        return_value=httpx.Response(200, json=bundle({**plan, "id": "1"}, {**plan, "id": "2"}))
    )
    with pytest.raises(FhirConflictError):
        await store.get_plan_definition(plan["url"])


@respx.mock
async def test_launch_persists_mdt_start_on_the_coordinating_task_in_the_same_transaction(
    store: TaskStore, steps: list[Task]
) -> None:
    count = len(steps)
    response = {
        "resourceType": "Bundle",
        "type": "transaction-response",
        "entry": [{"response": {"status": "201", "location": "CarePlan/100/_history/1"}}]
        + [{"response": {"status": "201", "location": f"ServiceRequest/{300 + i}/_history/1"}} for i in range(count)]
        + [{"response": {"status": "201", "location": f"Task/{200 + i}/_history/1"}} for i in range(count)]
        + [{"response": {"status": "200", "location": "Task/5/_history/4"}}]
        + [{"response": {"status": "201", "location": "Provenance/400/_history/1"}}],
    }
    case_task = {
        "resourceType": "Task",
        "id": "5",
        "meta": {"versionId": "3"},
        "extension": [
            {"url": EXT_MDT_START, "valueDateTime": "2026-01-01T08:00:00+01:00"},
            {"url": "https://stafeta.example/fhir/StructureDefinition/other", "valueCode": "keep"},
        ],
    }
    respx.get(f"{FHIR_BASE}/Task/5").mock(return_value=httpx.Response(200, json=case_task))
    tx = respx.post(FHIR_BASE).mock(return_value=httpx.Response(200, json=response))
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())

    result = await store.launch_pathway(
        HEADER,
        load_plan(),
        steps,
        date(2026, 10, 2),
        indication=PHYSICIAN,
        coordinator=COORDINATOR,
        recorded=NOW,
        mdt_start=datetime(2026, 10, 21, 8, 0, tzinfo=UTC),
    )

    entries = body(tx.calls.last)["entry"]
    [put] = [e for e in entries if e["request"]["method"] == "PUT"]
    assert put["request"] == {"method": "PUT", "url": "Task/5", "ifMatch": 'W/"3"'}  # lost update = failed launch
    extensions = {e["url"]: e for e in put["resource"]["extension"]}
    assert extensions[EXT_MDT_START]["valueDateTime"] == "2026-10-21T08:00:00+00:00"  # replaced, not duplicated
    assert len(put["resource"]["extension"]) == 2  # the other extension is kept
    assert result.provenance_id == "400"  # ids stay aligned with the entries


@respx.mock
async def test_launch_without_mdt_start_does_not_touch_the_coordinating_task(
    store: TaskStore, steps: list[Task]
) -> None:
    count = len(steps)
    response = {
        "resourceType": "Bundle",
        "type": "transaction-response",
        "entry": [
            {"response": {"status": "201", "location": f"{kind}/{i}/_history/1"}}
            for i, kind in enumerate(["CarePlan"] + ["ServiceRequest"] * count + ["Task"] * count + ["Provenance"])
        ],
    }
    tx = respx.post(FHIR_BASE).mock(return_value=httpx.Response(200, json=response))
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=audit_ok())

    await store.launch_pathway(
        HEADER, load_plan(), steps, date(2026, 10, 2), indication=PHYSICIAN, coordinator=COORDINATOR, recorded=NOW
    )

    assert all(e["request"]["method"] == "POST" for e in body(tx.calls.last)["entry"])
