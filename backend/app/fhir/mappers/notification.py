"""SMS to the patient (appointment confirmation / reminder): a `Communication` that records the SMS that was sent.

Same shape as the MDT feedback e-mail (`app.fhir.mappers.feedback`), with medium `SMSWRIT`. Written only after the
gateway accepted the SMS; `identifier[0]` (`<task id>:<kind>`) makes it idempotent, `identifier[1]` is the gateway's
message id (the receipt). `sent` is the demo-aware clock, `received` is not set (no delivery report in the demo).
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from app.fhir.client import Resource
from app.fhir.systems import (
    CS_COMMUNICATION_CATEGORY,
    SID_SMS_GATEWAY_MESSAGE,
    SID_SMS_NOTIFICATION,
    V3_PARTICIPATION_MODE,
)

CATEGORY_APPOINTMENT_REMINDER: Final = "appointment-reminder"


def sms_business_id(task_id: str, kind: str) -> str:
    return f"{task_id}:{kind}"


def sms_communication_to_fhir(
    *,
    task_id: str,
    kind: str,
    patient_reference: str,
    task_reference: str,
    episode_reference: str | None,
    sender_reference: str | None,
    sent_at: datetime,
    message_id: str,
    body: str,
) -> Resource:
    about = [{"reference": r} for r in (episode_reference, task_reference) if r]
    resource: Resource = {
        "resourceType": "Communication",
        "identifier": [
            {"system": SID_SMS_NOTIFICATION, "value": sms_business_id(task_id, kind)},
            {"system": SID_SMS_GATEWAY_MESSAGE, "value": message_id},
        ],
        "status": "completed",
        "category": [{"coding": [{"system": CS_COMMUNICATION_CATEGORY, "code": CATEGORY_APPOINTMENT_REMINDER}]}],
        "medium": [{"coding": [{"system": V3_PARTICIPATION_MODE, "code": "SMSWRIT", "display": "SMS"}]}],
        "subject": {"reference": patient_reference},
        "about": about,
        "sent": sent_at.isoformat(),
        "recipient": [{"reference": patient_reference}],
        "payload": [{"contentString": body}],
    }
    if sender_reference:
        resource["sender"] = {"reference": sender_reference}
    return resource
