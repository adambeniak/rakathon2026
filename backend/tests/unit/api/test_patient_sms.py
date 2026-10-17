"""SMS to the patient through the API: confirmation on `confirm`, day-before reminder in the watchdog round and on demo
advance; one SMS + one Communication per (task, kind), a gateway failure never fails the transition."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from app.api.deps import get_coordination, get_directory_provider, get_fhir_client, get_iris_pool, get_repository
from app.api.services.coordination import CoordinationService
from app.api.watchdog import run_once
from app.domain import clock
from app.fhir.systems import SID_SMS_NOTIFICATION
from app.main import create_app
from app.notify.mailer import MailDeliveryError
from app.notify.patient_sms import PatientSmsNotifier
from app.notify.sms import SmsMessage
from app.settings import Settings
from tests.directory_fixtures import demo_directory
from tests.unit.api.test_coordination import CASE_ID, COORDINATOR, LAUNCH, FakeProvider, FakeReader, at
from tests.unit.api.test_demo_advance import STORY_DOCS, ScopedStore
from tests.unit.api.test_demo_clock import FakeRepository as AuditSink

PHONE = "+420 777 000 541"
CT_CONFIRMATION = (
    "Štafeta: Dobrý den, máte termín: CT vyšetření, 8. 10. 2026 v 08:00, "
    "KOC 1 – Nemocnice Severní, radiologie. Změnu termínu řešte s koordinátorem KOC."
)
CT_REMINDER = "Štafeta: Připomínka – zítra 8. 10. v 08:00: CT vyšetření, KOC 1 – Nemocnice Severní, radiologie."


class FakeGateway:
    def __init__(self) -> None:
        self.sent: list[SmsMessage] = []
        self.fail = False

    async def send(self, message: SmsMessage) -> str:
        if self.fail:
            raise MailDeliveryError
        self.sent.append(message)
        return f"<sms-{len(self.sent)}@stafeta.example>"


class FakeFhir:
    """The repository calls the notifier makes: reads of Patient / case Task / EpisodeOfCare, Communication search
    and create, and the audit of the patient read."""

    def __init__(self, phone: str | None = PHONE) -> None:
        koc = demo_directory().org("koc2-nemocnice-lipova")
        assert koc is not None
        telecom = [{"system": "phone", "value": phone, "use": "mobile"}] if phone else []
        self.resources: dict[str, dict[str, Any]] = {
            "Patient/3": {"resourceType": "Patient", "id": "3", "telecom": telecom},
            "Task/5": {"resourceType": "Task", "id": "5", "focus": {"reference": "EpisodeOfCare/7"}},
            "EpisodeOfCare/7": {
                "resourceType": "EpisodeOfCare",
                "id": "7",
                "managingOrganization": {"reference": koc.ref},
            },
        }
        self.koc_ref = koc.ref
        self.communications: list[dict[str, Any]] = []
        self.audited_reads: list[str] = []
        self.fail_create = False

    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        return self.resources[f"{resource_type}/{resource_id}"]

    async def audit_read(self, entities: list[str], *, subtype: str = "read") -> None:
        self.audited_reads += entities

    async def count(self, resource_type: str, params: dict[str, str]) -> int:
        assert resource_type == "Communication"
        system, value = params["identifier"].split("|", 1)
        return sum({"system": system, "value": value} in c["identifier"] for c in self.communications)

    async def create(self, resource: dict[str, Any], *, if_none_exist: str | None = None) -> None:
        if self.fail_create:
            raise RuntimeError("IRIS down")
        self.communications.append(resource)

    def kinds(self) -> list[str]:
        return [c["identifier"][0]["value"] for c in self.communications]


class Harness:
    def __init__(self, client: TestClient, store: ScopedStore, fhir: FakeFhir, gateway: FakeGateway) -> None:
        self.client, self.store, self.fhir, self.gateway = client, store, fhir, gateway
        self.notifier = PatientSmsNotifier(fhir, gateway, FakeProvider())  # type: ignore[arg-type]

    def confirm(self, step: str, when: str) -> Any:
        return self.client.post(
            f"/api/tasks/{CASE_ID}.{step}/transitions", json={"event": "confirm", "date": when}, headers=COORDINATOR
        )

    def advance(self, to: str) -> Any:
        return self.client.post(f"/api/demo/advance?case_id={CASE_ID}&to={to}", headers=COORDINATOR)


def make(settings: Settings, fhir: FakeFhir) -> Iterator[Harness]:
    app = create_app(settings)
    store = ScopedStore()
    store.documents = dict(STORY_DOCS)
    gateway = FakeGateway()
    reader = FakeReader(mdt_start=at("2026-10-21T08:00:00"))
    clock.set_override(at("2026-10-02T09:00:00"))
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_fhir_client] = lambda: object()
    app.dependency_overrides[get_iris_pool] = lambda: object()
    app.dependency_overrides[get_repository] = lambda: AuditSink()
    try:
        with TestClient(app) as client:
            harness = Harness(client, store, fhir, gateway)
            app.dependency_overrides[get_coordination] = lambda: CoordinationService(
                reader,  # type: ignore[arg-type]
                store,  # type: ignore[arg-type]
                clock.now,
                FakeProvider(),  # type: ignore[arg-type]
                notifier=harness.notifier,
            )
            assert client.post(f"/api/cases/{CASE_ID}/pathways", json=LAUNCH, headers=COORDINATOR).status_code == 201
            yield harness
    finally:
        clock.set_override(None)


@pytest.fixture
def harness(settings: Settings) -> Iterator[Harness]:
    yield from make(settings, FakeFhir())


def test_confirming_the_ct_sends_one_sms_and_records_it(harness: Harness) -> None:
    response = harness.confirm("ct", "2026-10-08T08:00:00+02:00")

    assert response.status_code == 200
    assert harness.gateway.sent == [SmsMessage(phone=PHONE, body=CT_CONFIRMATION)]
    (communication,) = harness.fhir.communications
    assert communication["identifier"] == [
        {"system": SID_SMS_NOTIFICATION, "value": f"{CASE_ID}.ct:confirmation"},
        {"system": "https://stafeta.example/fhir/sid/sms-gateway-message-id", "value": "<sms-1@stafeta.example>"},
    ]
    assert communication["status"] == "completed"
    assert communication["medium"][0]["coding"][0]["code"] == "SMSWRIT"
    assert communication["category"][0]["coding"][0] == {
        "system": "https://stafeta.example/fhir/CodeSystem/communication-category",
        "code": "appointment-reminder",
    }
    assert communication["subject"] == {"reference": "Patient/3"}
    assert communication["recipient"] == [{"reference": "Patient/3"}]
    ct_fhir_id = harness.store.resources[f"{CASE_ID}.ct"]["id"]
    assert communication["about"] == [{"reference": "EpisodeOfCare/7"}, {"reference": f"Task/{ct_fhir_id}"}]
    assert communication["sender"] == {"reference": harness.fhir.koc_ref}
    assert communication["sent"] == "2026-10-02T09:00:00+02:00"  # the demo clock
    assert communication["payload"] == [{"contentString": CT_CONFIRMATION}]
    assert harness.fhir.audited_reads == ["Patient/3"]


def test_a_repeated_confirmation_sends_nothing_more(harness: Harness) -> None:
    harness.confirm("ct", "2026-10-08T08:00:00+02:00")
    stored = harness.store.resources[f"{CASE_ID}.ct"]
    from app.fhir.mappers.task import task_from_fhir

    again = asyncio.run(
        harness.notifier.appointment_confirmed(stored, task_from_fhir(stored), at("2026-10-02T09:05:00"))
    )

    assert again is False
    assert len(harness.gateway.sent) == 1
    assert harness.fhir.kinds() == [f"{CASE_ID}.ct:confirmation"]


def test_gateway_failure_keeps_the_transition_and_records_nothing(harness: Harness) -> None:
    harness.gateway.fail = True

    with capture_logs() as logs:
        response = harness.confirm("ct", "2026-10-08T08:00:00+02:00")

    assert response.status_code == 200
    assert response.json()["business_status"] == "potvrzeno"
    assert harness.fhir.communications == []
    failed = [e for e in logs if e["event"] == "sms_failed"]
    assert failed == [
        {"event": "sms_failed", "log_level": "warning", "task_id": f"{CASE_ID}.ct", "kind": "confirmation"}
    ]
    assert PHONE not in str(logs)
    assert "radiologie" not in str(logs)


def test_no_sms_for_a_step_the_patient_does_not_attend(harness: Harness) -> None:
    response = harness.confirm("histology", "2026-10-12T13:00:00+02:00")

    assert response.status_code == 200
    assert harness.gateway.sent == []


def test_patient_without_phone_is_skipped_and_logged(settings: Settings) -> None:
    info = settings.model_copy(update={"log_level": "INFO"})  # the info log is filtered at WARNING
    for harness in make(info, FakeFhir(phone=None)):
        with capture_logs() as logs:
            assert harness.confirm("ct", "2026-10-08T08:00:00+02:00").status_code == 200
        assert harness.gateway.sent == []
        assert harness.fhir.communications == []
        assert any(e["event"] == "sms_skipped_no_phone" for e in logs)


def test_watchdog_reminds_once_inside_the_window_and_never_after(harness: Harness) -> None:
    harness.confirm("ct", "2026-10-08T08:00:00+02:00")

    def round_at(moment: datetime) -> None:
        asyncio.run(run_once(harness.store, moment, reminders=harness.notifier))  # type: ignore[arg-type]

    round_at(at("2026-10-07T07:59:00"))  # 24 h + 1 min ahead: not yet
    assert harness.fhir.kinds() == [f"{CASE_ID}.ct:confirmation"]
    round_at(at("2026-10-07T09:00:00"))
    round_at(at("2026-10-07T10:00:00"))  # the next round: already sent
    round_at(at("2026-10-08T09:00:00"))  # the appointment is past

    assert harness.fhir.kinds() == [f"{CASE_ID}.ct:confirmation", f"{CASE_ID}.ct:reminder"]
    assert [m.body for m in harness.gateway.sent] == [CT_CONFIRMATION, CT_REMINDER]


def test_failed_reminder_is_retried_next_round(harness: Harness) -> None:
    harness.confirm("ct", "2026-10-08T08:00:00+02:00")
    harness.gateway.fail = True
    asyncio.run(run_once(harness.store, at("2026-10-07T09:00:00"), reminders=harness.notifier))  # type: ignore[arg-type]
    harness.gateway.fail = False
    asyncio.run(run_once(harness.store, at("2026-10-07T09:01:00"), reminders=harness.notifier))  # type: ignore[arg-type]

    assert harness.fhir.kinds() == [f"{CASE_ID}.ct:confirmation", f"{CASE_ID}.ct:reminder"]


def test_demo_advance_confirms_the_story_appointments_once(harness: Harness) -> None:
    first = harness.advance("2026-10-16")
    second = harness.advance("2026-10-16")

    assert (first.status_code, second.status_code) == (200, 200)
    assert harness.fhir.kinds() == [
        f"{CASE_ID}.ct:confirmation",
        f"{CASE_ID}.eus-fnb:confirmation",
        f"{CASE_ID}.labs:confirmation",
    ]
    assert len(harness.gateway.sent) == 3  # histology (sample, past date) gets none
    assert harness.gateway.sent[0].body == CT_CONFIRMATION
    assert harness.fhir.communications[0]["sent"] == "2026-10-05T10:00:00+02:00"  # when the story confirmed it


def test_demo_advance_sends_the_day_before_reminder(harness: Harness) -> None:
    response = harness.advance("2026-10-07T10:00:00%2B02:00")

    assert response.status_code == 200
    assert harness.fhir.kinds() == [f"{CASE_ID}.ct:confirmation", f"{CASE_ID}.ct:reminder"]
    assert harness.gateway.sent[1].body == CT_REMINDER


def test_sent_but_unrecorded_sms_is_not_sent_again(harness: Harness) -> None:
    harness.confirm("ct", "2026-10-08T08:00:00+02:00")
    harness.fhir.fail_create = True

    def round_at(moment: datetime) -> None:
        asyncio.run(run_once(harness.store, moment, reminders=harness.notifier))  # type: ignore[arg-type]

    with capture_logs() as logs:
        round_at(at("2026-10-07T09:00:00"))
        round_at(at("2026-10-07T09:01:00"))

    assert [m.body for m in harness.gateway.sent] == [CT_CONFIRMATION, CT_REMINDER]  # the reminder went out once
    assert [e["event"] for e in logs if e["event"].startswith("sms_")] == ["sms_sent_not_recorded"]


def test_no_sms_to_a_deceased_patient(settings: Settings) -> None:
    fhir = FakeFhir()
    fhir.resources["Patient/3"]["deceasedBoolean"] = True
    for harness in make(settings, fhir):
        assert harness.confirm("ct", "2026-10-08T08:00:00+02:00").status_code == 200
        assert harness.gateway.sent == []
        assert harness.fhir.communications == []
