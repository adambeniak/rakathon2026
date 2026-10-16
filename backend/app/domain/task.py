"""Steps of the case (CT in KOC 1, EUS-FNB, labs, histology, …) with owner, place and due date.

The task state machine, overdue detection and escalation live in `app.domain.task_machine`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.domain.common import BUSINESS_ID_PATTERN, DomainModel, PartyRef, Role


class TaskStatus(StrEnum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskBusinessStatus(StrEnum):
    """FBMI principle: a sent request is not an ordered examination."""

    OBJEDNANO = "objednano"
    POTVRZENO = "potvrzeno"
    PROVEDENO = "provedeno"
    VYSLEDEK_DORUCEN = "vysledek_dorucen"


class Task(DomainModel):
    id: str = Field(pattern=BUSINESS_ID_PATTERN)
    case_id: str = Field(pattern=BUSINESS_ID_PATTERN)
    code: str = Field(description="Step type, e.g. 'ct-staging', 'eus-fnb', 'request-report'.")
    title: str = Field(description="Czech title shown on the board.")
    status: TaskStatus
    business_status: TaskBusinessStatus | None = None
    owner: PartyRef | None = None
    due: AwareDatetime | None = None
    location: str | None = Field(None, description="Workplace where the step happens.")
    depends_on: list[str] = Field(default_factory=list, description="Task ids that must finish first.")
    note: str | None = None
    # Workflow fields below are owned by the task state machine; all are additive.
    owner_role: Role | None = Field(None, description="Role that updates the step when no concrete `owner` is set.")
    scheduled_at: AwareDatetime | None = Field(None, description="Confirmed date/time of the step (order confirmed).")
    result_doc_id: str | None = Field(None, description="Document id of the delivered result.")
    sla_due: AwareDatetime | None = Field(
        None, description="Agreed deadline; may be earlier than `due`. Drives escalation."
    )
    escalated_at: AwareDatetime | None = Field(None, description="When the overdue escalation fired (fires once).")
    demo_assumption: bool = Field(
        False, description="`due` and `sla_due` come from a demo template, not from clinical guidance."
    )
    recorded_on_behalf_by: PartyRef | None = Field(
        None, description="Coordinator who recorded progress for the external workplace that owns the step."
    )
    ad_hoc: bool = Field(False, description="Single task created by the coordinator, not part of a pathway.")
