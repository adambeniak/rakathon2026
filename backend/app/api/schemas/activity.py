"""Case activity of the public API: audit trail, timeline and messages (read-only, KOC team of the case)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.domain.activity import MessageKind, TimelineKind
from app.domain.common import Role
from app.domain.task import TaskStatus


class AuditEntry(BaseModel):
    """One audit record. Codes only: the UI names them in Czech; no free text or clinical content is returned."""

    recorded: AwareDatetime = Field(description="When it happened (AuditEvent.recorded).")
    actor: str | None = Field(None, description="Display name of who acted (person or 'Štafeta (systém)').")
    actor_role: Role | None = None
    on_behalf_of: str | None = Field(None, description="Workplace the coordinator recorded a step for.")
    action: Literal["C", "R", "U", "D", "E"] = Field(
        description="FHIR AuditEventAction: C create, R read, U update, D delete, E execute (search, transaction)."
    )
    operation: str = Field(
        description="Workflow event code (`accept`, `send_feedback`, `gp_opened`, `request_report`, ...) or the "
        "interaction (`read`, `search-type`, `create`, `update`, `transaction`, `export`, `index`, `extract`, "
        "`launch_pathway`)."
    )
    workflow_event: bool = Field(description="A business event of the case or task state machine.")
    entity_types: list[str] = Field(description="Kinds of record touched, e.g. ['Task', 'DocumentReference'].")
    outcome: Literal["success", "failure"]


class CaseAuditTrail(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "case_id": "rakathon-2026-prochazkova",
                    "total": 42,
                    "offset": 0,
                    "limit": 100,
                    "truncated": False,
                    "items": [
                        {
                            "recorded": "2026-10-21T09:30:00+02:00",
                            "actor": "doc. MUDr. Pavel Hrubý, Ph.D.",
                            "actor_role": "koc_physician",
                            "on_behalf_of": None,
                            "action": "U",
                            "operation": "record_mdt_conclusion",
                            "workflow_event": True,
                            "entity_types": ["Task"],
                            "outcome": "success",
                        }
                    ],
                }
            ]
        }
    )

    case_id: str
    items: list[AuditEntry] = Field(description="Newest first.")
    total: int = Field(description="Records in the trail of the case (before offset/limit).")
    offset: int
    limit: int
    truncated: bool = Field(description="More records exist after this page.")


class TimelineEntry(BaseModel):
    id: str = Field(description="Stable within one response; use it as a list key.")
    kind: TimelineKind
    at: AwareDatetime = Field(description="Business time; for `date_only` the start of that day in Europe/Prague.")
    date_only: bool = Field(False, description="Only the day is known (authored date of a report).")
    event: str | None = Field(None, description="Workflow event code of a case event (`accept`, `reopen`, ...).")
    title: str | None = Field(None, description="Document title, step title or request label, as stored.")
    place: str | None = Field(None, description="Issuing or receiving workplace.")
    actor: str | None = None
    doc_id: str | None = None
    task_id: str | None = None
    from_state: str | None = Field(None, description="Case state before a case event.")
    to_state: str | None = Field(None, description="Case state after a case event; null when it did not change.")
    receipt_id: str | None = Field(None, description="`feedback_delivered`: SMTP Message-ID accepted by the relay.")
    planned: bool = Field(False, description="After the current (demo) time: a scheduled step or the MDT meeting.")
    excluded_from_handover: bool | None = Field(
        None,
        description="Documents only: authored or received after the MDT start, so not part of the MDT handover "
        "(as-of rule, decided by the backend). Null when the case has no MDT start or for other kinds.",
    )


class CaseTimeline(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "case_id": "rakathon-2026-prochazkova",
                    "as_of": "2026-10-21T08:00:00+02:00",
                    "now": "2026-10-21T10:00:00+02:00",
                    "events": [
                        {
                            "id": "doc-received:11_Histologie_KOC2_2026-10-19",
                            "kind": "document_received",
                            "at": "2026-10-19T12:10:00+02:00",
                            "title": "Histologie",
                            "place": "Nemocnice Lipová – patologie",
                            "doc_id": "11_Histologie_KOC2_2026-10-19",
                            "excluded_from_handover": False,
                        },
                        {
                            "id": "mdt-meeting",
                            "kind": "mdt_meeting",
                            "at": "2026-10-21T08:00:00+02:00",
                        },
                    ],
                }
            ]
        }
    )

    case_id: str
    as_of: AwareDatetime | None = Field(None, description="MDT start the handover flag is computed against.")
    now: AwareDatetime = Field(description="Current (demo) time `planned` is computed against.")
    events: list[TimelineEntry] = Field(description="Oldest first.")


class MessageRequestInfo(BaseModel):
    request_id: str
    status: TaskStatus = Field(description="Status of the request's tracking task.")
    due: AwareDatetime | None = None
    exam_date: date | None = None
    result_doc_id: str | None = Field(None, description="The report that fulfilled the request.")


class MessageDelivery(BaseModel):
    channel: Literal["email"] = "email"
    receipt_id: str | None = Field(
        None, description="SMTP Message-ID: the relay accepted the e-mail (handed over, not proof it was read)."
    )
    gp_opened_at: AwareDatetime | None = Field(
        None, description="First time the referring GP opened the feedback in the portal; null = not recorded."
    )


MessageStatus = Literal["open", "fulfilled", "cancelled", "sent"]


class CaseMessage(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "rakathon-2026-prochazkova-req-1",
                    "kind": "document_request",
                    "status": "fulfilled",
                    "sent_at": "2026-10-02T11:30:00+02:00",
                    "sender": "Bc. Jana Nováková",
                    "recipient": "Laboratoř LabJih",
                    "text": "Žádost o zaslání výsledku vyšetření: RTG plic 3. 9. 2026 (3. 9. 2026)",
                    "request": {
                        "request_id": "rakathon-2026-prochazkova-req-1",
                        "status": "completed",
                        "due": "2026-10-06T23:59:00+02:00",
                        "result_doc_id": "03_RTG_plic_2026-09-03",
                    },
                    "delivery": None,
                }
            ]
        }
    )

    id: str
    kind: MessageKind
    status: MessageStatus = Field(
        description="`open` request awaiting the report, `fulfilled` report received, `cancelled` request withdrawn, "
        "`sent` feedback e-mail accepted by the relay."
    )
    sent_at: AwareDatetime | None = None
    sender: str | None = None
    recipient: str | None = None
    text: str = Field(
        description="The message as sent (fixed template; the feedback e-mail holds no clinical content)."
    )
    request: MessageRequestInfo | None = None
    delivery: MessageDelivery | None = None
