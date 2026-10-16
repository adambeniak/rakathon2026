"""Steps of the case (CT in KOC 1, EUS-FNB, labs, histology, …) with owner, place and due date.

The task state machine, overdue detection and escalation are P4's work (#3).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.domain.common import BUSINESS_ID_PATTERN, DomainModel, PartyRef


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
    # TODO(#3): transitions (requested -> … -> completed / failed / cancelled), overdue detection, escalation.
