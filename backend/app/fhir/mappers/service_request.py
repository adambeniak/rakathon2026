"""Pathway step -> FHIR ServiceRequest: the indicating physician's request for the examination.

The ServiceRequest records *who requested* the step (`requester` = the KOC physician who indicated the pathway). The
Task of the same step (`Task.focus` -> ServiceRequest) tracks the booking and the delivery. The ServiceRequest status
stays `active` after launch (it is not synchronised with the Task; see docs/fhir-mapping.md).
"""

from __future__ import annotations

from datetime import datetime

from app.domain.task import Task
from app.fhir.client import Resource
from app.fhir.systems import CS_PATHWAY_ACTION, EXT_DEMO_ASSUMPTION, SID_STEP_ORDER


def service_request_to_fhir(
    task: Task, *, patient_reference: str, requester: Resource, authored_on: datetime
) -> Resource:
    resource: Resource = {
        "resourceType": "ServiceRequest",
        "identifier": [{"system": SID_STEP_ORDER, "value": task.id}],
        "status": "active",
        "intent": "order",
        "code": {"coding": [{"system": CS_PATHWAY_ACTION, "code": task.code}], "text": task.title},
        "subject": {"reference": patient_reference},
        "authoredOn": authored_on.isoformat(),
        "requester": requester,
    }
    if task.demo_assumption:
        resource["extension"] = [{"url": EXT_DEMO_ASSUMPTION, "valueBoolean": True}]
    return resource
