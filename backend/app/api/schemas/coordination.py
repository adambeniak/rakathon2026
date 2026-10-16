"""Coordination API: pathway launch, task transitions, board, alerts, ad-hoc tasks.

Ids are business identifiers. Lanes are keyed by role; the Czech lane labels belong to the UI. Wording stays
neutral — the API reports states and dates, it never recommends clinical action.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.domain.board import AlertKind, BatonBasis, BatonReason
from app.domain.common import BUSINESS_ID_PATTERN, Role
from app.domain.task import TaskBusinessStatus, TaskStatus

TransitionEvent = Literal["confirm", "perform", "deliver_result", "fail", "cancel"]
# A module-level alias: a field named `date` would shadow the `date` type inside the class body.
DateOrDateTime = date | datetime
# No patient: a patient cannot act in Štafeta and the coordinator may record only for external workplaces, so a
# patient-owned task would never reach completion (see docs/known-issues.md K18).
ALLOWED_OWNER_ROLES = frozenset({Role.GP, Role.COORDINATOR, Role.KOC_PHYSICIAN, Role.EXTERNAL_WORKPLACE})


class TaskOwner(BaseModel):
    id: str = Field(description="Business id of the PractitionerRole.")
    display: str
    role: Role


class TaskOut(BaseModel):
    id: str = Field(description="Task business id, e.g. 'rakathon-2026-prochazkova.ct'.")
    case_id: str
    code: str = Field(description="Step type, e.g. 'ct-thorax-abdomen'; 'ad-hoc' for single tasks.")
    title: str
    status: TaskStatus
    business_status: TaskBusinessStatus | None = Field(
        None,
        description="Real-world progress: objednano (planned from the template, NOT yet ordered) → potvrzeno "
        "(place and date confirmed) → provedeno → vysledek_dorucen.",
    )
    lane: Role = Field(description="Board lane: role of the concrete owner, else of the step.")
    owner: TaskOwner | None = None
    owner_role: Role | None = Field(None, description="Role responsible while no concrete owner is set.")
    place: str | None = Field(None, description="Workplace where the step happens.")
    due: AwareDatetime | None = Field(None, description="Planned date (demo templates: a demo assumption).")
    sla_due: AwareDatetime | None = Field(None, description="Promised turnaround; may be earlier than `due`.")
    scheduled_at: AwareDatetime | None = Field(None, description="Confirmed date/time of the step.")
    depends_on: list[str] = Field(description="Task ids that must finish first.")
    blocked_by: list[str] = Field(description="Subset of `depends_on` that is not finished yet.")
    overdue: bool
    overdue_workdays: int = Field(description="Working days past the earlier of `due` and `sla_due`.")
    escalated_at: AwareDatetime | None = None
    result_doc_id: str | None = None
    note: str | None = None
    ad_hoc: bool
    required_for_mdt: bool = Field(
        description="The MDT readiness waits for this step. Dependency ordering only; not a clinical priority."
    )
    demo_assumption: bool = Field(
        description="`due` and `sla_due` are demo-template assumptions, not clinical guidance."
    )
    recorded_on_behalf_by: TaskOwner | None = Field(
        None,
        description="Set when the coordinator recorded progress for the external workplace that owns the step "
        "(the source is the note or the result document).",
    )


class BoardLane(BaseModel):
    role: Role
    tasks: list[TaskOut]


class BatonHolderOut(BaseModel):
    role: Role
    owner: TaskOwner | None = None
    task_id: str
    task_title: str
    due: AwareDatetime | None = None
    basis: BatonBasis = Field(description="Which group of steps the baton is taken from.")
    reason: BatonReason = Field(
        description="action = the owner acts; awaiting_confirmation = nothing is ordered yet, the coordinator "
        "confirms place and date; dependency_failed = a prerequisite failed or was cancelled."
    )
    demo_assumption: bool


class Board(BaseModel):
    case_id: str
    computed_at: AwareDatetime = Field(description="The (demo) time the board was computed for.")
    lanes: list[BoardLane] = Field(
        description="Always five lanes: gp, coordinator, koc_physician, external_workplace, patient."
    )
    baton_holder: BatonHolderOut | None = Field(
        None, description="Owner of the earliest-due open task on the critical path; null when nothing is open."
    )


class AlertOut(BaseModel):
    task_id: str
    case_id: str
    code: str
    title: str
    kind: AlertKind
    deadline: date = Field(description="The earlier of `due` and `sla_due`.")
    basis: Literal["sla", "due"]
    overdue_workdays: int
    escalated_at: AwareDatetime | None = Field(None, description="When the watchdog escalated it (once).")
    recipients: list[Role]
    demo_assumption: bool = Field(description="The deadline comes from a demo template, not from clinical guidance.")


class LaunchPathwayRequest(BaseModel):
    plan_url: str = Field(
        pattern=r"^https?://[^\s,|$\\]+$",
        max_length=300,
        examples=["https://stafeta.example/fhir/PlanDefinition/pancreas-dx"],
        description="Canonical url of the PlanDefinition seeded in IRIS.",
    )
    start_date: date = Field(description="Day the pathway starts; due dates are computed from it.")
    mdt_start: AwareDatetime | None = Field(
        None, description="Planned MDT start; defaults to the case's `mdt_start` (required when the case has none)."
    )
    indicated_by: str | None = Field(
        None,
        max_length=200,
        examples=["hruby-pavel@koc2-nemocnice-lipova"],
        description="REQUIRED: business id of the KOC physician (PractitionerRole `koc_physician`) who indicates the "
        "examination set. Stored as CarePlan.author and ServiceRequest.requester of every order, with a Provenance "
        "(the coordinator acts on the physician's behalf). Without it the answer is 422 "
        "'Sada vyšetření vyžaduje indikujícího lékaře KOC.' The UI pre-fills the physician of the case; the "
        "coordinator confirms.",
    )


class PathwayLaunched(BaseModel):
    plan_url: str
    start_date: date
    indicated_by: TaskOwner = Field(description="The KOC physician who indicated the set.")
    tasks: list[TaskOut] = Field(description="Steps ordered by due date (= dependency order).")
    baton_holder: BatonHolderOut | None = None


class TransitionRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"event": "confirm", "date": "2026-10-08", "place": "KOC 1 – radiologie"},
                {"event": "deliver_result", "document_id": "11_Histologie_KOC2_2026-10-19"},
            ]
        }
    )

    event: TransitionEvent = Field(
        description="confirm = order confirmed + accepted; perform = started + performed; "
        "deliver_result = result delivered; fail / cancel need a note."
    )
    note: str | None = Field(None, max_length=500, description="Reason for fail / cancel; free text.")
    date: DateOrDateTime | None = Field(
        None, description="Confirmed date (or date-time) of the step; required to confirm an order."
    )
    place: str | None = Field(None, max_length=200, description="Confirmed workplace when the task has none.")
    document_id: str | None = Field(
        None, pattern=BUSINESS_ID_PATTERN, max_length=200, description="Result document; required to deliver a result."
    )

    @model_validator(mode="after")
    def _event_needs(self) -> Self:
        if self.event == "deliver_result" and not self.document_id:
            raise ValueError("document_id is required to deliver a result")
        if self.event in {"fail", "cancel"} and not (self.note and self.note.strip()):
            raise ValueError("note is required to fail or cancel a task")
        return self


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"title": "Doplnit ECOG", "owner_role": "koc_physician", "due": "2026-10-19"}]}
    )

    title: str = Field(min_length=1, max_length=200)
    owner_role: Role = Field(description="Role that works on the task; decides its board lane.")
    due: date | AwareDatetime | None = Field(None, description="A bare date means the end of that day (Prague).")
    place: str | None = Field(None, max_length=200)
    note: str | None = Field(None, max_length=500)
    depends_on: list[Annotated[str, Field(pattern=BUSINESS_ID_PATTERN, max_length=200)]] = Field(
        default_factory=list, max_length=20, description="Ids of tasks of the same case."
    )

    @model_validator(mode="after")
    def _owner_role_is_assignable(self) -> Self:
        if self.owner_role not in ALLOWED_OWNER_ROLES:
            raise ValueError(f"owner_role must be one of {sorted(r.value for r in ALLOWED_OWNER_ROLES)}")
        return self
