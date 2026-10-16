"""Request for a report from another workplace: a small lifecycle next to the heavy examination task machine.

The examination machine (`task_machine`) models ordering, scheduling and performing a step. Asking a workplace to send a
report that already exists needs only: requested → completed when the report arrives (`vysledek_dorucen`). Both
transitions return audit events like the other machines. Documented in ADR-0005.
"""

from __future__ import annotations

from datetime import datetime, time

from app.domain import clock
from app.domain.common import PartyRef, Role
from app.domain.events import DomainEvent, EventKind, TransitionError
from app.domain.task import Task, TaskBusinessStatus, TaskStatus

TASK_CODE = "request-report"
DUE_WORKDAYS = 2


def request_task_id(case_id: str, number: int) -> str:
    return f"{case_id}-req-{number}"


def new_request(
    *, case_id: str, number: int, label: str, recipient_name: str, owner: PartyRef, now: datetime
) -> tuple[Task, DomainEvent]:
    """Due: end of the second working day after `now` (Europe/Prague)."""
    due_day = clock.add_workdays(now.astimezone(clock.TZ).date(), DUE_WORKDAYS)
    task = Task(
        id=request_task_id(case_id, number),
        case_id=case_id,
        code=TASK_CODE,
        title=f"Vyžádat výsledek: {label}",
        status=TaskStatus.REQUESTED,
        business_status=TaskBusinessStatus.OBJEDNANO,
        owner=owner,
        owner_role=Role.COORDINATOR,
        due=datetime.combine(due_day, time(23, 59), tzinfo=clock.TZ),
        location=recipient_name,
    )
    event = DomainEvent(
        EventKind.AUDIT,
        "create",
        now,
        {"event": "request_report", "task_id": task.id, "case_id": case_id, "actor_role": owner.role.value},
    )
    return task, event


def fulfil(task: Task, *, result_doc_id: str, actor: Role, now: datetime) -> tuple[Task, DomainEvent]:
    if task.code != TASK_CODE:
        raise TransitionError("invalid_transition", "not a report request")
    if task.status is not TaskStatus.REQUESTED:
        raise TransitionError("invalid_transition", f"request is already {task.status.value}")
    done = task.model_copy(
        update={
            "status": TaskStatus.COMPLETED,
            "business_status": TaskBusinessStatus.VYSLEDEK_DORUCEN,
            "result_doc_id": result_doc_id,
        }
    )
    event = DomainEvent(
        EventKind.AUDIT,
        "update",
        now,
        {
            "event": "report_received",
            "task_id": task.id,
            "case_id": task.case_id,
            "result_doc_id": result_doc_id,
            "actor_role": actor.value,
        },
    )
    return done, event
