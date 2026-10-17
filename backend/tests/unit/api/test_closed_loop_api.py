"""Demo steps 5-6 through the HTTP API against an in-memory FHIR store: sign-off stores the text, the feedback e-mail
goes out and confirms delivery, the GP reads, the coordinator closes."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_case_reader, get_case_workflow, get_directory_provider, get_fhir_client, get_iris_pool
from app.api.services.closed_loop import ClosedLoopWorkflow
from app.domain.board import build_board, collect_alerts
from app.domain.case import Case, CaseState
from app.domain.common import Role
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.domain.task_machine import OPEN_STATUSES
from app.fhir.cases import CaseOverview, LoadedCase
from app.fhir.client import Resource
from app.fhir.directory import Directory
from app.fhir.mappers.case import case_from_fhir, case_task_to_fhir
from app.fhir.mappers.task import task_from_fhir, task_to_fhir
from app.main import create_app
from app.notify.mailer import MailDeliveryError, MailMessage
from app.seed import demo_case
from app.settings import PRAGUE, Settings
from tests.directory_fixtures import demo_directory

CASE_URL = "/api/cases/rakathon-2026-prochazkova"
MDT_START = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)
CONCLUSION = "Závěr MDT: postup dle zápisu ze dne 21. 10. 2026."
DIRECTORY = demo_directory()
GP = DIRECTORY.role(demo_case.GP_ROLE)
KOC2 = DIRECTORY.org(demo_case.KOC2)
PHYSICIAN = DIRECTORY.role_holder(demo_case.KOC2, Role.KOC_PHYSICIAN)  # role-level baton holder of the seeded case
assert GP
assert KOC2
assert PHYSICIAN
SIGNER = DIRECTORY.role(PHYSICIAN.id)  # the person current_actor picks for X-Demo-Role: koc_physician
assert SIGNER
PHYSICIAN_HEADERS = {"X-Demo-Role": "koc_physician"}
COORDINATOR_HEADERS = {"X-Demo-Role": "coordinator"}
GP_HEADERS = {"X-Demo-Role": "gp"}
REVIEWER_HEADERS = {"X-Demo-Role": "reviewer"}


class MemoryFhir:
    """FhirRepository + CaseReader over a dict: transactions apply atomically, PUT honours If-Match."""

    def __init__(self, task: Resource) -> None:
        self.resources: dict[tuple[str, str], Resource] = {("Task", "5"): task}
        self.transactions = 0
        self.audit_reads: list[list[str]] = []
        self._next = 100

    # --- FhirRepository ---
    async def count(self, resource_type: str, params: dict[str, str]) -> int:
        return 0

    async def search(self, resource_type: str, params: dict[str, str]) -> list[Resource]:
        found = [r for (t, _), r in self.resources.items() if t == resource_type]
        if resource_type == "Composition":
            found = [r for r in found if r["subject"]["reference"] == params["subject"]]
        return found

    async def read(self, resource_type: str, resource_id: str) -> Resource:
        return dict(self.resources[(resource_type, resource_id)])

    async def audit_read(self, entities: list[str], **_: object) -> None:
        self.audit_reads.append(list(entities))

    async def transaction(self, bundle: Resource, **_: object) -> Resource:
        entries = bundle["entry"]
        urns: dict[str, str] = {}
        for entry in entries:
            if entry["request"]["method"] == "POST":
                self._next += 1
                urns[entry["fullUrl"]] = f"{entry['request']['url']}/{self._next}"
        staged: dict[tuple[str, str], Resource] = {}
        for entry in entries:
            request = entry["request"]
            resource = json.loads(_replace(json.dumps(entry["resource"]), urns))
            if request["method"] == "POST":
                resource_type, resource_id = urns[entry["fullUrl"]].split("/")
            else:
                resource_type, resource_id = request["url"].split("/")
                current = self.resources[(resource_type, resource_id)]
                version = current["meta"]["versionId"]
                if request.get("ifMatch") != f'W/"{version}"':
                    raise AssertionError("If-Match does not match the stored version")
                resource["meta"] = {**resource.get("meta", {}), "versionId": str(int(version) + 1)}
            resource["id"] = resource_id
            staged[(resource_type, resource_id)] = resource
        self.resources.update(staged)
        self.transactions += 1
        return {}

    # --- CaseReader ---
    async def load(self, case_id: str) -> LoadedCase:
        task = self.resources[("Task", "5")]
        episode = {"managingOrganization": {"reference": KOC2.ref}}  # type: ignore[union-attr]
        return LoadedCase(task=task, episode=episode, case=case_from_fhir(task, demo_case.PATIENT))

    async def overview(self, case_id: str) -> CaseOverview:
        return CaseOverview(case=(await self.load(case_id)).case, document_count=13)

    def of_type(self, resource_type: str) -> list[Resource]:
        return [r for (t, _), r in self.resources.items() if t == resource_type]


def _replace(text: str, urns: dict[str, str]) -> str:
    for urn, reference in urns.items():
        text = text.replace(urn, reference)
    return text


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[MailMessage] = []
        self.fail = False

    async def send(self, message: MailMessage) -> str:
        if self.fail:
            raise MailDeliveryError
        self.sent.append(message)
        return message.message_id


class FakeProvider:
    async def get(self) -> Directory:
        return DIRECTORY


def _initial_task() -> Resource:
    case = Case(
        id=demo_case.CASE_ID,
        patient=demo_case.PATIENT,
        state=CaseState.PRIPRAVENO_MDT,
        baton_holder=PHYSICIAN,
        baton_role=Role.KOC_PHYSICIAN,
        opened_at=datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE),
        mdt_start=MDT_START,
    )
    task = case_task_to_fhir(
        case,
        episode_reference="EpisodeOfCare/1",
        patient_reference="Patient/2",
        requester_reference=GP.ref,  # type: ignore[union-attr]
        owner_reference="PractitionerRole/9",
    )
    return {**task, "id": "5", "meta": {"versionId": "1"}}


@pytest.fixture
def store() -> MemoryFhir:
    return MemoryFhir(_initial_task())


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def client(settings: Settings, store: MemoryFhir, mailer: FakeMailer) -> Iterator[TestClient]:
    app: FastAPI = create_app(settings)
    workflow = ClosedLoopWorkflow(store, store, mailer, "http://localhost:5173/gp")  # type: ignore[arg-type]
    app.dependency_overrides[get_case_workflow] = lambda: workflow
    app.dependency_overrides[get_case_reader] = lambda: store
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_fhir_client] = lambda: object()
    app.dependency_overrides[get_iris_pool] = lambda: object()
    with TestClient(app) as test_client:
        yield test_client


def _post(client: TestClient, event: str, headers: dict[str, str], **body: Any) -> Any:
    return client.post(f"{CASE_URL}/transitions", json={"event": event, **body}, headers=headers)


def _sign_off(client: TestClient) -> Any:
    return _post(client, "record_mdt_conclusion", PHYSICIAN_HEADERS, conclusion=CONCLUSION)


def _state(store: MemoryFhir) -> str:
    return str(store.resources[("Task", "5")]["businessStatus"]["coding"][0]["code"])


def test_no_conclusion_before_the_physician_signs(client: TestClient) -> None:
    response = client.get(f"{CASE_URL}/mdt-conclusion", headers=PHYSICIAN_HEADERS)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_sign_off_stores_the_text_with_provenance_in_the_same_transaction(
    client: TestClient, store: MemoryFhir
) -> None:
    response = _sign_off(client)

    assert response.status_code == 200
    assert response.json()["state"] == "zaver_mdt"
    assert store.transactions == 1
    [composition] = store.of_type("Composition")
    [provenance] = store.of_type("Provenance")
    assert provenance["target"] == [{"reference": f"Composition/{composition['id']}"}]
    assert provenance["agent"][0]["who"]["identifier"]["value"] == SIGNER.role.id
    audits = store.of_type("AuditEvent")
    assert [a["subtype"][0]["code"] for a in audits] == ["record_mdt_conclusion"]
    assert CONCLUSION not in json.dumps(audits)  # clinical text is not copied into the audit trail

    read = client.get(f"{CASE_URL}/mdt-conclusion", headers=COORDINATOR_HEADERS)
    assert read.status_code == 200
    body = read.json()
    assert body["text"] == CONCLUSION
    assert body["signed_by"] == {"id": SIGNER.role.id, "display": SIGNER.display, "role": "koc_physician"}
    assert store.audit_reads[-1] == [f"Composition/{composition['id']}"]


@pytest.mark.parametrize(
    ("headers", "body", "status", "code"),
    [
        (COORDINATOR_HEADERS, {"conclusion": CONCLUSION}, 403, "forbidden_role"),
        (GP_HEADERS, {"conclusion": CONCLUSION}, 403, "forbidden_role"),
        (PHYSICIAN_HEADERS, {"conclusion": "   "}, 409, "guard_failed"),
        (PHYSICIAN_HEADERS, {}, 409, "guard_failed"),
        (REVIEWER_HEADERS, {"conclusion": CONCLUSION}, 403, None),
    ],
)
def test_refused_sign_offs_store_nothing(
    client: TestClient, store: MemoryFhir, headers: dict[str, str], body: dict[str, str], status: int, code: str | None
) -> None:
    response = _post(client, "record_mdt_conclusion", headers, **body)

    assert response.status_code == status
    if code:
        assert response.json()["code"] == code
    assert store.transactions == 0
    assert store.of_type("Composition") == []
    assert _state(store) == "pripraveno_mdt"


def test_the_gp_reads_the_conclusion_only_after_the_feedback_was_sent(client: TestClient) -> None:
    _sign_off(client)

    assert client.get(f"{CASE_URL}/mdt-conclusion", headers=GP_HEADERS).status_code == 403
    assert client.get(f"{CASE_URL}/mdt-conclusion", headers=REVIEWER_HEADERS).status_code == 403
    assert _post(client, "send_feedback", COORDINATOR_HEADERS).status_code == 200
    assert client.get(f"{CASE_URL}/mdt-conclusion", headers=GP_HEADERS).json()["text"] == CONCLUSION


def test_feedback_mails_the_gp_confirms_delivery_and_records_the_communication(
    client: TestClient, store: MemoryFhir, mailer: FakeMailer
) -> None:
    _sign_off(client)

    response = _post(client, "send_feedback", COORDINATOR_HEADERS)

    assert response.status_code == 200
    assert response.json()["state"] == "zpetna_vazba_odeslana"
    [message] = mailer.sent
    assert message.recipient_address.endswith("@demo.stafeta.example")
    assert "http://localhost:5173/gp" in message.body
    assert CONCLUSION not in message.body
    task = store.resources[("Task", "5")]
    assert {"url": "https://stafeta.example/fhir/StructureDefinition/delivery-receipt", "valueBoolean": True} in [
        {k: v for k, v in e.items() if k in ("url", "valueBoolean")} for e in task["extension"]
    ]
    [communication] = store.of_type("Communication")
    assert communication["status"] == "completed"
    assert message.message_id in [i["value"] for i in communication["identifier"]]
    assert communication["payload"][0]["contentString"] == message.body
    [composition] = store.of_type("Composition")
    assert {"reference": f"Composition/{composition['id']}"} in communication["about"]
    audits = {a["subtype"][0]["code"]: a for a in store.of_type("AuditEvent")}
    assert audits["send_feedback"]["agent"][0]["who"]["identifier"]["value"] == "dvorakova-lucie@koc2-nemocnice-lipova"
    assert audits["delivery_confirmed"]["agent"][0]["who"]["identifier"]["value"] == "system"
    receipt = {d["type"]: d["valueString"] for d in audits["delivery_confirmed"]["entity"][0]["detail"]}
    assert receipt["receipt_id"] == message.message_id


def test_a_failed_mail_changes_nothing_and_the_coordinator_can_retry(
    client: TestClient, store: MemoryFhir, mailer: FakeMailer
) -> None:
    _sign_off(client)
    transactions = store.transactions
    mailer.fail = True

    failed = _post(client, "send_feedback", COORDINATOR_HEADERS)

    assert failed.status_code == 503
    assert failed.json()["type"].endswith("/mail-unavailable")
    assert store.transactions == transactions
    assert store.of_type("Communication") == []
    assert _state(store) == "zaver_mdt"

    mailer.fail = False
    assert _post(client, "send_feedback", COORDINATOR_HEADERS).status_code == 200
    assert len(mailer.sent) == 1
    assert _state(store) == "zpetna_vazba_odeslana"


@pytest.mark.parametrize(
    ("headers", "status", "code"),
    [(PHYSICIAN_HEADERS, 403, "forbidden_role"), (GP_HEADERS, 403, "forbidden_role")],
)
def test_only_the_coordinator_sends_and_nothing_goes_out_when_refused(
    client: TestClient, mailer: FakeMailer, headers: dict[str, str], status: int, code: str
) -> None:
    _sign_off(client)

    response = _post(client, "send_feedback", headers)

    assert response.status_code == status
    assert response.json()["code"] == code
    assert mailer.sent == []


def test_feedback_before_the_conclusion_is_signed_sends_nothing(client: TestClient, mailer: FakeMailer) -> None:
    response = _post(client, "send_feedback", COORDINATOR_HEADERS)

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_transition"
    assert mailer.sent == []


def test_feedback_cannot_be_sent_twice(client: TestClient, mailer: FakeMailer) -> None:
    _sign_off(client)
    _post(client, "send_feedback", COORDINATOR_HEADERS)

    again = _post(client, "send_feedback", COORDINATOR_HEADERS)

    assert again.status_code == 409
    assert len(mailer.sent) == 1


def test_delivery_cannot_be_confirmed_by_a_user_and_the_gp_receipt_then_close_complete_the_loop(
    client: TestClient, store: MemoryFhir
) -> None:
    _sign_off(client)
    _post(client, "send_feedback", COORDINATOR_HEADERS)

    forged = _post(client, "delivery_confirmed", COORDINATOR_HEADERS, receipt_id="forged")
    opened = _post(client, "gp_opened", GP_HEADERS)
    closed = _post(client, "close", COORDINATOR_HEADERS)

    assert forged.status_code == 403
    assert forged.json()["code"] == "forbidden_role"
    assert opened.status_code == 200
    assert opened.json()["state"] == "zpetna_vazba_odeslana"
    assert closed.status_code == 200
    assert closed.json()["state"] == "uzavreno"
    assert _state(store) == "uzavreno"
    actions = [a["action"] for a in store.of_type("AuditEvent") if a["subtype"][0]["code"] == "gp_opened"]
    assert actions == ["R"]


def test_a_failed_write_after_a_sent_mail_is_an_error_and_leaves_the_state_alone(
    client: TestClient, store: MemoryFhir, mailer: FakeMailer
) -> None:
    _sign_off(client)
    original = store.transaction

    async def failing(bundle: Resource, **kwargs: object) -> Resource:
        raise RuntimeError("412 If-Match")

    store.transaction = failing  # type: ignore[method-assign]

    response = _post(client, "send_feedback", COORDINATOR_HEADERS)

    store.transaction = original  # type: ignore[method-assign]
    assert response.status_code == 500  # surfaced, not swallowed
    assert len(mailer.sent) == 1  # the mail is out (the Message-ID is logged); nothing was recorded
    assert _state(store) == "zaver_mdt"
    assert store.of_type("Communication") == []


@pytest.mark.parametrize(
    ("headers", "status"),
    [(COORDINATOR_HEADERS, 403), (GP_HEADERS, 403), (PHYSICIAN_HEADERS, 403), (REVIEWER_HEADERS, 403)],
)
def test_no_demo_role_can_confirm_delivery_or_supply_a_receipt(
    client: TestClient, store: MemoryFhir, headers: dict[str, str], status: int
) -> None:
    _sign_off(client)
    _post(client, "send_feedback", COORDINATOR_HEADERS)
    before = store.resources[("Task", "5")]["meta"]["versionId"]

    response = _post(client, "delivery_confirmed", headers, receipt_id="forged")

    assert response.status_code == status
    assert store.resources[("Task", "5")]["meta"]["versionId"] == before  # nothing written


# --- close: a closed case leaves no open step, alert or escalation behind (#133) ---

HISTOLOGY_DUE = datetime(2026, 10, 9, 16, 0, tzinfo=PRAGUE)  # overdue at the MDT clock
STEPS = {  # FHIR id -> (step, FHIR id of its order)
    "201": (
        Task(
            id="step-histology",
            case_id=demo_case.CASE_ID,
            code="histology",
            title="Histologie",
            status=TaskStatus.ACCEPTED,
            business_status=TaskBusinessStatus.POTVRZENO,
            owner_role=Role.EXTERNAL_WORKPLACE,
            due=HISTOLOGY_DUE,
            sla_due=HISTOLOGY_DUE,
        ),
        "301",
    ),
    "202": (
        Task(
            id="step-call-patient",
            case_id=demo_case.CASE_ID,
            code="ad-hoc",
            title="Zavolat pacientce",
            status=TaskStatus.REQUESTED,
            owner_role=Role.COORDINATOR,
            ad_hoc=True,
        ),
        None,
    ),
    "203": (
        Task(
            id="step-ct",
            case_id=demo_case.CASE_ID,
            code="ct-staging",
            title="CT hrudníku a břicha",
            status=TaskStatus.COMPLETED,
            business_status=TaskBusinessStatus.VYSLEDEK_DORUCEN,
            owner_role=Role.EXTERNAL_WORKPLACE,
            result_doc_id="09",
        ),
        "303",
    ),
}


@pytest.fixture
def steps(store: MemoryFhir) -> MemoryFhir:
    for fhir_id, (task, order_id) in STEPS.items():
        resource = task_to_fhir(
            task,
            case_task_reference="Task/5",
            patient_reference="Patient/2",
            service_request_reference=f"ServiceRequest/{order_id}" if order_id else None,
        )
        store.resources[("Task", fhir_id)] = {**resource, "id": fhir_id, "meta": {"versionId": "1"}}
        if order_id:
            store.resources[("ServiceRequest", order_id)] = {
                "resourceType": "ServiceRequest",
                "id": order_id,
                "status": "completed" if task.status is TaskStatus.COMPLETED else "active",
                "meta": {"versionId": "1"},
            }
    return store


def _step_tasks(store: MemoryFhir) -> list[Task]:
    return [task_from_fhir(store.resources[("Task", fhir_id)]) for fhir_id in STEPS]


def _feedback_sent(client: TestClient) -> None:
    assert _sign_off(client).status_code == 200
    assert _post(client, "send_feedback", COORDINATOR_HEADERS).status_code == 200


def test_close_cancels_the_open_steps_and_revokes_their_orders_in_the_same_transaction(
    client: TestClient, steps: MemoryFhir
) -> None:
    _feedback_sent(client)
    before = steps.transactions

    closed = _post(client, "close", COORDINATOR_HEADERS)

    assert closed.status_code == 200
    assert closed.json()["state"] == "uzavreno"
    assert closed.json()["baton_holder"] is None
    assert steps.transactions == before + 1  # case, steps, orders and audit commit together
    for fhir_id in ("201", "202"):
        step = steps.resources[("Task", fhir_id)]
        assert step["status"] == "cancelled"
        assert step["statusReason"] == {"text": "Případ uzavřen"}
        assert step["meta"]["versionId"] == "2"
    assert steps.resources[("Task", "201")]["focus"] == {"reference": "ServiceRequest/301"}
    assert steps.resources[("Task", "201")]["businessStatus"]["coding"][0]["code"] == "potvrzeno"  # never backwards
    assert steps.resources[("ServiceRequest", "301")]["status"] == "revoked"
    # A completed step and its order are history: untouched.
    assert steps.resources[("Task", "203")]["status"] == "completed"
    assert steps.resources[("Task", "203")]["meta"]["versionId"] == "1"
    assert steps.resources[("ServiceRequest", "303")]["status"] == "completed"
    cancels = [a for a in steps.of_type("AuditEvent") if a["subtype"][0]["code"] == "cancel"]
    assert sorted(a["entity"][0]["what"]["reference"] for a in cancels) == ["Task/201", "Task/202"]
    closes = [a for a in steps.of_type("AuditEvent") if a["subtype"][0]["code"] == "close"]
    assert [a["entity"][0]["what"]["reference"] for a in closes] == ["Task/5"]


def test_a_closed_case_has_no_alert_no_baton_and_nothing_left_to_escalate(
    client: TestClient, steps: MemoryFhir
) -> None:
    _feedback_sent(client)
    assert [a.task_id for a in collect_alerts(_step_tasks(steps), MDT_START)] == ["step-histology"]  # the #133 alert

    assert _post(client, "close", COORDINATOR_HEADERS).status_code == 200

    tasks = _step_tasks(steps)
    assert collect_alerts(tasks, MDT_START) == []
    board = build_board(demo_case.CASE_ID, tasks, MDT_START)
    assert board.baton_holder is None
    assert not any(bt.overdue for lane in board.lanes for bt in lane.tasks)
    assert [t for t in tasks if t.status in OPEN_STATUSES] == []  # what the SLA watchdog looks at


def test_a_refused_close_changes_no_step(client: TestClient, steps: MemoryFhir) -> None:
    _sign_off(client)  # no feedback sent yet: close is not allowed

    refused = _post(client, "close", COORDINATOR_HEADERS)
    waived = _post(client, "close", COORDINATOR_HEADERS, waivers=[{"item": "histology", "reason": "x"}])

    assert refused.status_code == 409
    assert waived.status_code == 422
    assert all(steps.resources[("Task", fhir_id)]["meta"]["versionId"] == "1" for fhir_id in STEPS)
    assert steps.resources[("ServiceRequest", "301")]["status"] == "active"
