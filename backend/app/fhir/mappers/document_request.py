"""Report requests: CommunicationRequest (the message to the workplace) + Task (the coordinator's tracking step)."""

from __future__ import annotations

from datetime import date, datetime

from app.domain.common import PartyRef
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.fhir.client import Resource
from app.fhir.mappers.directory import party_reference, role_from_codeable_concepts
from app.fhir.systems import (
    CS_TASK_BUSINESS_STATUS,
    CS_TASK_CODE,
    CS_WORKFLOW_ROLE,
    EXT_REQUEST_EXAM_DATE,
    SID_COMMUNICATION_REQUEST,
    SID_REQUEST_TASK,
    SID_SOURCE_DOCUMENT,
    TASK_CODE_REQUEST_REPORT,
)

REQUEST_TEXT = "Žádost o zaslání výsledku vyšetření: {label}"


def communication_request_to_fhir(
    task_id: str,
    *,
    label: str,
    exam_date: date | None,
    patient_reference: str,
    episode_reference: str,
    requester: PartyRef,
    requester_reference: str,
    recipient_reference: str,
    authored_on: datetime,
) -> Resource:
    """Fixed template + the label as entered by the coordinator (a proposal's label is the letter's wording)."""
    text = REQUEST_TEXT.format(label=label) + (f" ({exam_date.strftime('%-d. %-m. %Y')})" if exam_date else "")
    return {
        "resourceType": "CommunicationRequest",
        "identifier": [{"system": SID_COMMUNICATION_REQUEST, "value": task_id}],
        "status": "active",
        "subject": {"reference": patient_reference},
        "about": [{"reference": episode_reference}],
        "authoredOn": authored_on.isoformat(),
        "requester": party_reference(requester, requester_reference),
        "recipient": [{"reference": recipient_reference}],
        "payload": [{"contentString": text}],
    }


def request_task_to_fhir(
    task: Task,
    *,
    case_task_reference: str,
    patient_reference: str,
    communication_request_reference: str,
    owner_reference: str,
    recipient_reference: str,
    exam_date: date | None,
    result_document_reference: str | None = None,
) -> Resource:
    if task.owner is None or task.due is None:
        raise ValueError("a request task needs an owner and a due date")
    resource: Resource = {
        "resourceType": "Task",
        "identifier": [{"system": SID_REQUEST_TASK, "value": task.id}],
        "status": task.status.value.replace("_", "-"),
        "intent": "order",
        "code": {"coding": [{"system": CS_TASK_CODE, "code": TASK_CODE_REQUEST_REPORT}]},
        "description": task.title,
        "partOf": [{"reference": case_task_reference}],
        "basedOn": [{"reference": communication_request_reference}],
        "for": {"reference": patient_reference},
        "owner": party_reference(task.owner, owner_reference),
        "performerType": [{"coding": [{"system": CS_WORKFLOW_ROLE, "code": task.owner.role.value}]}],
        "restriction": {
            "period": {"end": task.due.isoformat()},
            "recipient": [_with_display({"reference": recipient_reference}, task.location)],
        },
    }
    if task.business_status:
        resource["businessStatus"] = {
            "coding": [{"system": CS_TASK_BUSINESS_STATUS, "code": task.business_status.value}]
        }
    if exam_date:
        resource["extension"] = [{"url": EXT_REQUEST_EXAM_DATE, "valueDate": exam_date.isoformat()}]
    if task.result_doc_id and result_document_reference:
        resource["output"] = [
            {
                "type": {"text": "Doručený výsledek"},
                "valueReference": {
                    "reference": result_document_reference,
                    "identifier": {"system": SID_SOURCE_DOCUMENT, "value": task.result_doc_id},
                },
            }
        ]
    return resource


def _with_display(reference: Resource, display: str | None) -> Resource:
    return {**reference, "display": display} if display else reference


def request_task_from_fhir(resource: Resource) -> Task:
    task_id = next((i["value"] for i in resource.get("identifier", []) if i.get("system") == SID_REQUEST_TASK), None)
    if task_id is None:
        raise ValueError("Task has no request-task identifier")
    case_id = task_id.rsplit("-req-", 1)[0]
    owner = resource.get("owner") or {}
    role = role_from_codeable_concepts(resource.get("performerType", []))
    business = next(
        (
            c["code"]
            for c in resource.get("businessStatus", {}).get("coding", [])
            if c.get("system") == CS_TASK_BUSINESS_STATUS
        ),
        None,
    )
    recipient = (resource.get("restriction", {}).get("recipient") or [{}])[0]
    output = (resource.get("output") or [{}])[0].get("valueReference", {}).get("identifier", {})
    end = resource.get("restriction", {}).get("period", {}).get("end")
    return Task(
        id=str(task_id),
        case_id=case_id,
        code=TASK_CODE_REQUEST_REPORT,
        title=str(resource.get("description", "")),
        status=TaskStatus(str(resource["status"]).replace("-", "_")),
        business_status=TaskBusinessStatus(business) if business else None,
        owner=PartyRef(
            id=(owner.get("identifier") or {}).get("value", "unknown"), display=owner.get("display", ""), role=role
        )
        if owner and role
        else None,
        owner_role=role,
        due=datetime.fromisoformat(end) if end else None,
        location=recipient.get("display"),
        result_doc_id=output.get("value"),
    )


def request_exam_date(resource: Resource) -> date | None:
    value = next(
        (e.get("valueDate") for e in resource.get("extension", []) if e.get("url") == EXT_REQUEST_EXAM_DATE), None
    )
    return date.fromisoformat(value) if value else None
