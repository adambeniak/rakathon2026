"""Case <-> EpisodeOfCare + coordinating Task.

The coordinating Task carries the case state (`businessStatus`, CodeSystem case-state), the baton holder (`owner`
with business identifier + display, `performerType` = workflow role) and the next deadline
(`restriction.period.end`). The EpisodeOfCare groups documents (`DocumentReference.context.encounter`).
"""

from __future__ import annotations

from datetime import datetime

from app.domain.case import Case, CaseState
from app.domain.common import PartyRef
from app.domain.patient import Patient
from app.fhir.client import Resource
from app.fhir.mappers.directory import party_reference, role_from_codeable_concepts
from app.fhir.systems import (
    CS_CASE_STATE,
    CS_EPISODE_TYPE,
    CS_TASK_CODE,
    CS_WORKFLOW_ROLE,
    SID_CASE,
    SID_CASE_TASK,
    TASK_CODE_COORDINATE_CASE,
)

# Display texts of the case-state CodeSystem (UI labels come from the frontend i18n).
CASE_STATE_DISPLAY = {
    CaseState.ODESLANO: "Odesláno",
    CaseState.TRIAGE: "V triage",
    CaseState.CEKA_NA_PODKLADY: "Čeká na podklady",
    CaseState.KOMPLETNI: "Kompletní",
    CaseState.PRIPRAVENO_MDT: "Připraveno k rozhodnutí/MDT",
    CaseState.ZAVER_MDT: "Závěr KOC/MDT",
    CaseState.ZPETNA_VAZBA_ODESLANA: "Zpětná vazba odeslána",
    CaseState.UZAVRENO: "Uzavřeno",
}

# FHIR Task.status for the coordinating task per case state.
_TASK_STATUS = {CaseState.ODESLANO: "requested", CaseState.UZAVRENO: "completed"}


def episode_of_care_to_fhir(
    case: Case,
    *,
    patient_reference: str,
    managing_organization_reference: str,
    care_manager: tuple[PartyRef, str] | None,
) -> Resource:
    resource: Resource = {
        "resourceType": "EpisodeOfCare",
        "identifier": [{"system": SID_CASE, "value": case.id}],
        "status": "finished" if case.state is CaseState.UZAVRENO else "active",
        "type": [{"coding": [{"system": CS_EPISODE_TYPE, "code": "oncology-diagnostics"}]}],
        "patient": {"reference": patient_reference},
        "managingOrganization": {"reference": managing_organization_reference},
    }
    if case.opened_at:
        resource["period"] = {"start": case.opened_at.isoformat()}
    if care_manager:
        party, fhir_reference = care_manager
        resource["careManager"] = party_reference(party, fhir_reference)
    return resource


def case_task_to_fhir(
    case: Case,
    *,
    episode_reference: str,
    patient_reference: str,
    requester_reference: str | None,
    owner_reference: str | None,
) -> Resource:
    resource: Resource = {
        "resourceType": "Task",
        "identifier": [{"system": SID_CASE_TASK, "value": case.id}],
        "status": _TASK_STATUS.get(case.state, "in-progress"),
        "businessStatus": {
            "coding": [{"system": CS_CASE_STATE, "code": case.state.value, "display": CASE_STATE_DISPLAY[case.state]}]
        },
        "intent": "order",
        "priority": "urgent",
        "code": {"coding": [{"system": CS_TASK_CODE, "code": TASK_CODE_COORDINATE_CASE}]},
        "description": "Koordinace onkologického případu",
        "focus": {"reference": episode_reference},
        "for": {"reference": patient_reference},
    }
    if case.opened_at:
        resource["authoredOn"] = case.opened_at.isoformat()
    if requester_reference:
        resource["requester"] = {"reference": requester_reference}
    if case.baton_holder and owner_reference:
        resource["owner"] = party_reference(case.baton_holder, owner_reference)
        resource["performerType"] = [{"coding": [{"system": CS_WORKFLOW_ROLE, "code": case.baton_holder.role.value}]}]
    if case.next_deadline:
        resource["restriction"] = {"period": {"end": case.next_deadline.isoformat()}}
    return resource


def case_from_fhir(task: Resource, patient: Patient) -> Case:
    if task.get("resourceType") != "Task":
        raise ValueError("expected the coordinating Task")
    case_id = next((i["value"] for i in task.get("identifier", []) if i.get("system") == SID_CASE_TASK), None)
    if case_id is None:
        raise ValueError("coordinating Task has no case identifier")
    state_code = next(
        (c["code"] for c in task.get("businessStatus", {}).get("coding", []) if c.get("system") == CS_CASE_STATE),
        None,
    )
    if state_code is None:
        raise ValueError("coordinating Task has no case-state businessStatus")
    return Case(
        id=str(case_id),
        patient=patient,
        state=CaseState(state_code),
        baton_holder=_baton_holder(task),
        next_deadline=_optional_datetime(task.get("restriction", {}).get("period", {}).get("end")),
        opened_at=_optional_datetime(task.get("authoredOn")),
    )


def _baton_holder(task: Resource) -> PartyRef | None:
    owner = task.get("owner")
    role = role_from_codeable_concepts(task.get("performerType", []))
    if not owner or role is None:
        return None
    identifier = owner.get("identifier") or {}
    return PartyRef(id=identifier.get("value", "unknown"), display=owner.get("display", ""), role=role)


def _optional_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
