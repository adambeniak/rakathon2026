"""MDT feedback to the referring GP: a `Communication` that records the e-mail that was sent (the delivery proof).

Status `completed` is written only after the SMTP relay accepted the message. The payload is the e-mail body, which by
design holds no clinical content (see `app.notify.feedback_mail`); the SMTP Message-ID is the receipt (second
identifier) and also the `receipt_id` of the `delivery_confirmed` event.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from app.domain.common import PartyRef
from app.fhir.client import Resource
from app.fhir.mappers.directory import party_reference
from app.fhir.systems import CS, SID

SID_FEEDBACK: Final = SID + "feedback-communication"
SID_MESSAGE_ID: Final = SID + "smtp-message-id"
CS_COMMUNICATION_CATEGORY: Final = CS + "communication-category"
V3_PARTICIPATION_MODE: Final = "http://terminology.hl7.org/CodeSystem/v3-ParticipationMode"


def feedback_business_id(case_id: str, sent_at: datetime) -> str:
    return f"{case_id}@{sent_at.astimezone(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"


def feedback_communication_to_fhir(
    case_id: str,
    *,
    patient_reference: str,
    episode_reference: str,
    sender: PartyRef,
    sender_reference: str,
    recipient_reference: str,
    sent_at: datetime,
    message_id: str,
    body: str,
    conclusion_reference: str | None = None,
) -> Resource:
    """`sent` is when the SMTP relay accepted the message: a hand-over for delivery, not proof that the GP read it
    (`received` is deliberately not set; the GP opening the feedback is the separate `gp_opened` event).
    `conclusion_reference` names the signed MDT conclusion that was announced (traceability of the proof)."""
    about = [{"reference": episode_reference}]
    if conclusion_reference:
        about.append({"reference": conclusion_reference})
    return {
        "resourceType": "Communication",
        "identifier": [
            {"system": SID_FEEDBACK, "value": feedback_business_id(case_id, sent_at)},
            {"system": SID_MESSAGE_ID, "value": message_id},
        ],
        "status": "completed",
        "category": [{"coding": [{"system": CS_COMMUNICATION_CATEGORY, "code": "mdt-feedback"}]}],
        "medium": [{"coding": [{"system": V3_PARTICIPATION_MODE, "code": "EMAILWRIT", "display": "email"}]}],
        "subject": {"reference": patient_reference},
        "about": about,
        "sent": sent_at.isoformat(),
        "sender": party_reference(sender, sender_reference),
        "recipient": [{"reference": recipient_reference}],
        "payload": [{"contentString": body}],
    }
