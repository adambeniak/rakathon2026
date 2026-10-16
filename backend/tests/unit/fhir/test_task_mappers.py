from __future__ import annotations

from datetime import date

import pytest

from app.domain.common import PartyRef, Role
from app.domain.pathway import instantiate
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.fhir.audit import build_audit_event
from app.fhir.mappers.care_plan import care_plan_identifier, care_plan_to_fhir, plan_key
from app.fhir.mappers.provenance import pathway_launch_provenance
from app.fhir.mappers.service_request import service_request_to_fhir
from app.fhir.mappers.task import task_from_fhir, task_to_fhir
from app.fhir.systems import (
    CS_TASK_BUSINESS_STATUS,
    EXT_DEMO_ASSUMPTION,
    EXT_ON_BEHALF_OF,
    SID_CAREPLAN,
    SID_CASE,
    SID_CASE_STEP,
    SID_STEP_ORDER,
)
from app.security.actor import SYSTEM_ACTOR
from tests.unit.domain.conftest import MDT, load_plan, load_template, make_case

PHYSICIAN_REF = {
    "reference": "PractitionerRole/12",
    "identifier": {"system": "https://stafeta.example/fhir/sid/practitioner-role", "value": "hruby-pavel@koc2"},
    "display": "doc. MUDr. Pavel Hrubý, Ph.D.",
}
REFS = {"case_task_reference": "Task/5", "patient_reference": "Patient/3"}


def pathway() -> list[Task]:
    return instantiate(load_template(), make_case(), date(2026, 10, 2))


def test_every_pathway_step_survives_a_fhir_round_trip() -> None:
    for task in pathway():
        resource = task_to_fhir(task, **REFS)
        assert task_from_fhir(resource) == task


def test_step_task_shape() -> None:
    ct = pathway()[0]
    resource = task_to_fhir(ct, **REFS)
    assert resource["identifier"] == [{"system": SID_CASE_STEP, "value": "c1.ct"}]
    assert resource["groupIdentifier"] == {"system": SID_CASE, "value": "c1"}
    assert resource["partOf"] == [{"reference": "Task/5"}]
    assert resource["status"] == "requested"
    assert resource["businessStatus"]["coding"][0]["system"] == CS_TASK_BUSINESS_STATUS
    assert resource["performerType"][0]["coding"][0]["code"] == "external_workplace"
    assert resource["restriction"]["period"]["end"] == "2026-10-08T23:59:59+02:00"
    assert "owner" not in resource  # nobody has taken the step yet


def test_full_task_round_trip_with_owner_result_and_escalation() -> None:
    hist = pathway()[3]
    task = hist.model_copy(
        update={
            "status": TaskStatus.COMPLETED,
            "business_status": TaskBusinessStatus.VYSLEDEK_DORUCEN,
            "owner": PartyRef(id="patolog@koc2", display="MUDr. Patolog", role=Role.EXTERNAL_WORKPLACE),
            "owner_role": None,
            "scheduled_at": MDT,
            "result_doc_id": "11_Histologie_KOC2_2026-10-19",
            "escalated_at": MDT,
            "note": "Poznámka",
        }
    )
    resource = task_to_fhir(task, **REFS)
    assert resource["status"] == "completed"
    assert resource["output"][0]["valueReference"]["identifier"]["value"] == "11_Histologie_KOC2_2026-10-19"
    assert task_from_fhir(resource) == task


@pytest.mark.parametrize("status", list(TaskStatus))
def test_every_status_round_trips(status: TaskStatus) -> None:
    task = pathway()[0].model_copy(update={"status": status})
    assert task_from_fhir(task_to_fhir(task, **REFS)).status is status


def test_reason_of_a_failed_or_cancelled_task_is_the_status_reason() -> None:
    for status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
        task = pathway()[0].model_copy(update={"status": status, "note": "Pacientka odmítla"})
        resource = task_to_fhir(task, **REFS)
        assert resource["statusReason"] == {"text": "Pacientka odmítla"}
        assert "note" not in resource
        assert task_from_fhir(resource) == task


def test_workplace_is_task_location_and_coordinator_record_survives() -> None:
    task = pathway()[0].model_copy(
        update={
            "recorded_on_behalf_by": PartyRef(id="dvorakova-lucie@koc2", display="Bc. Lucie", role=Role.COORDINATOR)
        }
    )
    resource = task_to_fhir(task, **REFS)
    assert resource["location"] == {"display": task.location}
    assert task_from_fhir(resource) == task


def test_in_progress_uses_the_fhir_spelling() -> None:
    task = pathway()[0].model_copy(update={"status": TaskStatus.IN_PROGRESS})
    assert task_to_fhir(task, **REFS)["status"] == "in-progress"


def test_ad_hoc_task_keeps_its_marker() -> None:
    task = Task(
        id="c1.adhoc-1a2b3c4d",
        case_id="c1",
        code="ad-hoc",
        title="Doplnit ECOG",
        status=TaskStatus.REQUESTED,
        business_status=TaskBusinessStatus.OBJEDNANO,
        owner_role=Role.KOC_PHYSICIAN,
        ad_hoc=True,
    )
    assert task_from_fhir(task_to_fhir(task, **REFS)).ad_hoc is True


def test_step_task_needs_identifier_and_case() -> None:
    with pytest.raises(ValueError, match="identifier"):
        task_from_fhir({"resourceType": "Task", "status": "requested"})
    with pytest.raises(ValueError, match="expected a Task"):
        task_from_fhir({"resourceType": "Patient"})


def test_care_plan_lists_every_step_as_activity() -> None:
    plan = load_plan()
    assert plan_key(plan) == "pancreas-dx"
    assert care_plan_identifier("c1", plan) == (SID_CAREPLAN, "c1.pancreas-dx")
    cp = care_plan_to_fhir(
        case_id="c1",
        plan=plan,
        start_date=date(2026, 10, 2),
        patient_reference="Patient/3",
        activity_references=["urn:uuid:a", "urn:uuid:b"],
        author=PHYSICIAN_REF,
        created=MDT,
    )
    assert cp["author"] == PHYSICIAN_REF
    assert cp["instantiatesCanonical"] == [plan["url"]]
    assert (cp["status"], cp["intent"]) == ("active", "plan")
    assert cp["period"] == {"start": "2026-10-02"}
    assert [a["reference"]["reference"] for a in cp["activity"]] == ["urn:uuid:a", "urn:uuid:b"]


def test_service_request_names_the_indicating_physician_as_requester() -> None:
    ct = pathway()[0]
    order = service_request_to_fhir(ct, patient_reference="Patient/3", requester=PHYSICIAN_REF, authored_on=MDT)
    assert (order["status"], order["intent"]) == ("active", "order")
    assert order["requester"] == PHYSICIAN_REF
    assert order["identifier"] == [{"system": SID_STEP_ORDER, "value": "c1.ct"}]
    assert order["code"]["coding"][0]["code"] == "ct-thorax-abdomen"
    assert order["extension"] == [{"url": EXT_DEMO_ASSUMPTION, "valueBoolean": True}]  # a template date, not guidance


def test_task_points_to_the_order_it_fulfils() -> None:
    resource = task_to_fhir(pathway()[0], **REFS, service_request_reference="urn:uuid:order")
    assert resource["focus"] == {"reference": "urn:uuid:order"}
    assert "focus" not in task_to_fhir(pathway()[0], **REFS)


def test_provenance_says_the_coordinator_acted_on_behalf_of_the_physician() -> None:
    coordinator = PartyRef(id="dvorakova-lucie@koc2", display="Bc. Lucie Dvořáková", role=Role.COORDINATOR)
    provenance = pathway_launch_provenance(
        targets=["urn:uuid:plan", "urn:uuid:order"], coordinator=coordinator, indicating=PHYSICIAN_REF, recorded=MDT
    )
    [agent] = provenance["agent"]
    assert agent["who"]["identifier"]["value"] == coordinator.id
    assert agent["onBehalfOf"] == PHYSICIAN_REF
    assert [t["reference"] for t in provenance["target"]] == ["urn:uuid:plan", "urn:uuid:order"]
    assert provenance["activity"]["coding"][0]["code"] == "CREATE"


def test_audit_event_names_the_workplace_the_step_was_recorded_for() -> None:
    event = build_audit_event(
        action="U",
        subtype="update",
        actor=SYSTEM_ACTOR,
        entities=["Task/7"],
        recorded=MDT,
        description="task c1.ct: performed",
        on_behalf_of="KOC 1 – radiologie",
    )
    assert event["agent"][0]["extension"] == [
        {"url": EXT_ON_BEHALF_OF, "valueReference": {"display": "KOC 1 – radiologie"}}
    ]
    plain = build_audit_event(action="U", subtype="update", actor=SYSTEM_ACTOR, entities=[], recorded=MDT)
    assert "extension" not in plain["agent"][0]
