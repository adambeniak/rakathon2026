"""Pathway step / ad-hoc Task <-> FHIR Task.

Business key: `identifier` (SID_CASE_STEP | domain Task.id); the case is `groupIdentifier` (SID_CASE) and `partOf`
points to the coordinating Task. `performerType` is the *effective* owner role (concrete owner's role, else the
step's role); the concrete owner is a display/identifier-only Reference (no PractitionerRole lookup in the PoC).
The workplace is plain text in the `place` extension (no Location resources). `depends-on` carries business ids,
so a transaction needs no urn:uuid rewriting between steps.
The delivered result (`output`, type `result-document`) is the source document by business id; for the MDT step it is
the signed MDT conclusion `Composition` by its business id (`sid/mdt-conclusion`, #149).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.domain.board import MDT_TASK_CODE
from app.domain.common import PartyRef, Role
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.fhir.client import Resource
from app.fhir.mappers.directory import role_from_codeable_concepts
from app.fhir.mappers.mdt_conclusion import SID_MDT_CONCLUSION
from app.fhir.systems import (
    CS_TASK_BUSINESS_STATUS,
    CS_TASK_CODE,
    CS_WORKFLOW_ROLE,
    EXT_AD_HOC,
    EXT_DEMO_ASSUMPTION,
    EXT_DEPENDS_ON,
    EXT_ESCALATED_AT,
    EXT_RECORDED_BY,
    EXT_SLA_DUE,
    SID_CASE,
    SID_CASE_STEP,
    SID_PRACTITIONER_ROLE,
    SID_SOURCE_DOCUMENT,
    TASK_CODE_RESULT_DOCUMENT,
)

_STATUS_TO_FHIR = {
    TaskStatus.REQUESTED: "requested",
    TaskStatus.ACCEPTED: "accepted",
    TaskStatus.IN_PROGRESS: "in-progress",
    TaskStatus.COMPLETED: "completed",
    TaskStatus.FAILED: "failed",
    TaskStatus.CANCELLED: "cancelled",
}
_STATUS_FROM_FHIR = {v: k for k, v in _STATUS_TO_FHIR.items()}

_BUSINESS_DISPLAY = {
    TaskBusinessStatus.OBJEDNANO: "Objednáno",
    TaskBusinessStatus.POTVRZENO: "Potvrzeno",
    TaskBusinessStatus.PROVEDENO: "Provedeno",
    TaskBusinessStatus.VYSLEDEK_DORUCEN: "Výsledek doručen",
}


def task_to_fhir(
    task: Task, *, case_task_reference: str, patient_reference: str, service_request_reference: str | None = None
) -> Resource:
    resource: Resource = {
        "resourceType": "Task",
        "identifier": [{"system": SID_CASE_STEP, "value": task.id}],
        "groupIdentifier": {"system": SID_CASE, "value": task.case_id},
        "status": _STATUS_TO_FHIR[task.status],
        "intent": "order",
        "code": {"coding": [{"system": CS_TASK_CODE, "code": task.code}]},
        "description": task.title,
        "partOf": [{"reference": case_task_reference}],
        "for": {"reference": patient_reference},
    }
    if service_request_reference:
        resource["focus"] = {"reference": service_request_reference}  # the request this step fulfils
    if task.business_status:
        resource["businessStatus"] = {
            "coding": [
                {
                    "system": CS_TASK_BUSINESS_STATUS,
                    "code": task.business_status.value,
                    "display": _BUSINESS_DISPLAY[task.business_status],
                }
            ]
        }
    role = task.owner.role if task.owner else task.owner_role
    if role:
        resource["performerType"] = [{"coding": [{"system": CS_WORKFLOW_ROLE, "code": role.value}]}]
    if task.owner:
        resource["owner"] = {
            "type": "PractitionerRole",
            "identifier": {"system": SID_PRACTITIONER_ROLE, "value": task.owner.id},
            "display": task.owner.display,
        }
    if task.due:
        resource["restriction"] = {"period": {"end": task.due.isoformat()}}
    if task.scheduled_at:
        resource["executionPeriod"] = {"start": task.scheduled_at.isoformat()}
    if task.note and task.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
        resource["statusReason"] = {"text": task.note}
    elif task.note:
        resource["note"] = [{"text": task.note}]
    if task.location:
        resource["location"] = {"display": task.location}
    if task.result_doc_id:
        resource["output"] = [
            {
                "type": {"coding": [{"system": CS_TASK_CODE, "code": TASK_CODE_RESULT_DOCUMENT}]},
                "valueReference": _result_reference(task, task.result_doc_id),
            }
        ]
    extensions: list[dict[str, Any]] = []
    extensions += [{"url": EXT_DEPENDS_ON, "valueString": dep} for dep in task.depends_on]
    if task.sla_due:
        extensions.append({"url": EXT_SLA_DUE, "valueDateTime": task.sla_due.isoformat()})
    if task.escalated_at:
        extensions.append({"url": EXT_ESCALATED_AT, "valueDateTime": task.escalated_at.isoformat()})
    if task.ad_hoc:
        extensions.append({"url": EXT_AD_HOC, "valueBoolean": True})
    if task.demo_assumption:
        extensions.append({"url": EXT_DEMO_ASSUMPTION, "valueBoolean": True})
    if task.recorded_on_behalf_by:
        extensions.append(
            {
                "url": EXT_RECORDED_BY,
                "valueReference": {
                    "identifier": {"system": SID_PRACTITIONER_ROLE, "value": task.recorded_on_behalf_by.id},
                    "display": task.recorded_on_behalf_by.display,
                },
            }
        )
    if extensions:
        resource["extension"] = extensions
    return resource


def task_from_fhir(resource: Resource) -> Task:
    if resource.get("resourceType") != "Task":
        raise ValueError("expected a Task")
    task_id = next((i["value"] for i in resource.get("identifier", []) if i.get("system") == SID_CASE_STEP), None)
    case_id = (resource.get("groupIdentifier") or {}).get("value")
    if task_id is None or case_id is None:
        raise ValueError("step Task needs a SID_CASE_STEP identifier and a case groupIdentifier")
    code = next(
        (c["code"] for c in resource.get("code", {}).get("coding", []) if c.get("system") == CS_TASK_CODE), None
    )
    business = next(
        (
            c["code"]
            for c in resource.get("businessStatus", {}).get("coding", [])
            if c.get("system") == CS_TASK_BUSINESS_STATUS
        ),
        None,
    )
    role = role_from_codeable_concepts(resource.get("performerType", []))
    owner = resource.get("owner")
    extensions = resource.get("extension", [])
    return Task(
        id=str(task_id),
        case_id=str(case_id),
        code=str(code),
        title=str(resource.get("description", "")),
        status=_STATUS_FROM_FHIR[resource["status"]],
        business_status=TaskBusinessStatus(business) if business else None,
        owner=_owner(owner, role),
        owner_role=None if owner else role,
        due=_dt(resource.get("restriction", {}).get("period", {}).get("end")),
        location=(resource.get("location") or {}).get("display"),
        depends_on=[e["valueString"] for e in extensions if e.get("url") == EXT_DEPENDS_ON],
        note=(resource.get("statusReason") or {}).get("text")
        or next((n["text"] for n in resource.get("note", [])), None),
        scheduled_at=_dt(resource.get("executionPeriod", {}).get("start")),
        result_doc_id=_result_doc_id(resource),
        sla_due=_dt(_ext(extensions, EXT_SLA_DUE, "valueDateTime")),
        escalated_at=_dt(_ext(extensions, EXT_ESCALATED_AT, "valueDateTime")),
        ad_hoc=bool(_ext(extensions, EXT_AD_HOC, "valueBoolean")),
        demo_assumption=bool(_ext(extensions, EXT_DEMO_ASSUMPTION, "valueBoolean")),
        recorded_on_behalf_by=_recorded_by(_ext(extensions, EXT_RECORDED_BY, "valueReference")),
    )


def _owner(owner: dict[str, Any] | None, role: Any) -> PartyRef | None:
    if not owner or role is None:
        return None
    return PartyRef(
        id=(owner.get("identifier") or {}).get("value", "unknown"), display=owner.get("display", ""), role=role
    )


def _recorded_by(reference: dict[str, Any] | None) -> PartyRef | None:
    if not reference:
        return None
    return PartyRef(
        id=(reference.get("identifier") or {}).get("value", "unknown"),
        display=reference.get("display", ""),
        role=Role.COORDINATOR,
    )


def _result_reference(task: Task, result_id: str) -> Resource:
    """The MDT step's result is the signed conclusion (a Composition); every other step's is a source document."""
    if task.code == MDT_TASK_CODE and not task.ad_hoc:
        return {"type": "Composition", "identifier": {"system": SID_MDT_CONCLUSION, "value": result_id}}
    return {"identifier": {"system": SID_SOURCE_DOCUMENT, "value": result_id}}


def _result_doc_id(resource: Resource) -> str | None:
    for output in resource.get("output", []):
        value = (output.get("valueReference") or {}).get("identifier") or {}
        if value.get("system") in (SID_SOURCE_DOCUMENT, SID_MDT_CONCLUSION):
            return str(value["value"])
    return None


def _ext(extensions: list[dict[str, Any]], url: str, key: str) -> Any:
    return next((e.get(key) for e in extensions if e.get("url") == url), None)


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
