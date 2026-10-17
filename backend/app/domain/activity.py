"""What happened on a case, read back from the workflow's own records: audit trail, workflow events and messages.

Plain data (no FHIR, no I/O). The records carry ids, codes, states, display names and times only: never the free-text
reasons a transition stored (`reason`, waiver reasons) and never the unstructured audit description.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from app.domain.common import Role

AuditAction = Literal["C", "R", "U", "D", "E"]
AuditOutcome = Literal["success", "failure"]


@dataclass(frozen=True)
class AuditRecord:
    """One AuditEvent as the case audit trail shows it: who, when, what kind of action on which kinds of record."""

    recorded: datetime
    action: AuditAction
    operation: str  # workflow event code (`accept`, `gp_opened`, ...) or interaction (`read`, `search-type`, `export`)
    actor_display: str | None
    actor_role: Role | None
    on_behalf_of: str | None
    entity_types: tuple[str, ...]  # resource types named, e.g. ("Task", "DocumentReference")
    outcome: AuditOutcome
    workflow_event: bool  # a business event of the state machines, not a technical read/write
    written_at: datetime | None = None  # server write time (`meta.lastUpdated`): orders records with equal `recorded`


@dataclass(frozen=True)
class WorkflowEvent:
    """A business event of the case or one of its tasks (business AuditEvent of type `domain-event`)."""

    code: str  # `accept`, `send_feedback`, `delivery_confirmed`, `request_report`, `report_received`, `cancel`, ...
    at: datetime  # business time (demo clock)
    on_case: bool  # True: the coordinating Task changed; False: a step or a report request
    from_state: str | None = None
    to_state: str | None = None
    task_id: str | None = None  # business id of the step / request (task events)
    result_doc_id: str | None = None
    receipt_id: str | None = None  # `delivery_confirmed`: SMTP Message-ID accepted by the relay
    actor_display: str | None = None
    actor_role: Role | None = None


class MessageKind(StrEnum):
    DOCUMENT_REQUEST = "document_request"  # CommunicationRequest to a workplace
    MDT_FEEDBACK = "mdt_feedback"  # Communication: e-mail to the referring GP


@dataclass(frozen=True)
class MessageRecord:
    id: str  # business id (request task id / feedback id)
    kind: MessageKind
    fhir_status: str
    sent_at: datetime | None
    sender: str | None
    recipient: str | None
    text: str
    receipt_id: str | None = None
    reference: str = ""  # 'Communication/12', named in the audited read


@dataclass(frozen=True)
class RequestRecord:
    """A report request with the time it was sent (CommunicationRequest.authoredOn) and its tracking task."""

    task_id: str
    label: str
    recipient: str | None
    sent_at: datetime | None
    status: str  # domain TaskStatus value of the request task
    due: datetime | None = None
    exam_date: date | None = None
    result_doc_id: str | None = None


class TimelineKind(StrEnum):
    DOCUMENT_AUTHORED = "document_authored"
    DOCUMENT_RECEIVED = "document_received"
    CASE_EVENT = "case_event"
    REQUEST_SENT = "request_sent"
    REQUEST_FULFILLED = "request_fulfilled"
    STEP_SCHEDULED = "step_scheduled"
    STEP_RESULT_DELIVERED = "step_result_delivered"
    STEP_ESCALATED = "step_escalated"
    STEP_CANCELLED = "step_cancelled"
    MDT_MEETING = "mdt_meeting"
    MDT_CONCLUSION = "mdt_conclusion"
    FEEDBACK_SENT = "feedback_sent"
    FEEDBACK_DELIVERED = "feedback_delivered"
    GP_OPENED = "gp_opened"


@dataclass(frozen=True)
class TimelineEvent:
    id: str
    kind: TimelineKind
    at: datetime
    date_only: bool = False  # only the day is known (authored date of a report)
    event: str | None = None  # workflow event code of a case event
    title: str | None = None  # document title, step title or request label, as stored
    place: str | None = None  # issuing / receiving workplace
    actor: str | None = None
    doc_id: str | None = None
    task_id: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    receipt_id: str | None = None
    planned: bool = False  # after the current (demo) time: a scheduled step or the MDT meeting
    excluded_from_handover: bool | None = None  # documents only; None = no MDT start, nothing to compare with
