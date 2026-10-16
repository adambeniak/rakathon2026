"""Task state machine: requested → accepted → in_progress → completed | failed | cancelled.

`business_status` tracks the real-world progress and only moves forward:
objednano → potvrzeno → provedeno → vysledek_dorucen.
Principle (FBMI): a sent request is not an ordered examination — `potvrzeno` needs a confirmed
date, and `completed` is impossible before the result has been delivered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum

from . import clock
from .events import DomainEvent, EventKind, Role, TransitionError


class TaskStatus(StrEnum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


OPEN_STATUSES = frozenset({TaskStatus.REQUESTED, TaskStatus.ACCEPTED, TaskStatus.IN_PROGRESS})


class BusinessStatus(StrEnum):
    OBJEDNANO = "objednano"
    POTVRZENO = "potvrzeno"
    PROVEDENO = "provedeno"
    VYSLEDEK_DORUCEN = "vysledek_dorucen"


class _Owner:
    """Sentinel: the actor must hold the task's `owner_role`."""


OWNER = _Owner()


@dataclass(frozen=True)
class Task:
    id: str
    case_id: str
    code: str
    title: str
    owner_role: Role
    place: str | None
    due: date
    depends_on: tuple[str, ...] = ()
    status: TaskStatus = TaskStatus.REQUESTED
    business_status: BusinessStatus = BusinessStatus.OBJEDNANO
    scheduled_at: datetime | None = None
    result_doc_id: str | None = None
    sla_due: date | None = None  # contractual/agreed deadline, may be earlier than `due`
    escalated_at: datetime | None = None
    demo_assumption: bool = False  # due dates are demo assumptions, not clinical guidance


@dataclass(frozen=True)
class TaskContext:
    place: str | None = None
    scheduled_at: datetime | None = None
    result_doc_id: str | None = None
    reason: str | None = None
    completed_task_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class TaskResult:
    task: Task
    events: tuple[DomainEvent, ...]


Guard = Callable[[Task, TaskContext], str | None]


@dataclass(frozen=True)
class _Rule:
    event: str
    from_status: TaskStatus
    roles: frozenset[Role | _Owner]
    guard: Guard | None
    update: Callable[[Task, TaskContext], Task]
    notify: tuple[tuple[Role, str], ...] = ()


def _reason(_t: Task, ctx: TaskContext) -> str | None:
    return None if ctx.reason and ctx.reason.strip() else "reason is required"


def _confirm_guard(t: Task, ctx: TaskContext) -> str | None:
    if t.business_status is not BusinessStatus.OBJEDNANO:
        return "order already confirmed"
    if not (ctx.place or t.place):
        return "confirmed place is required"
    if ctx.scheduled_at is None:
        return "confirmed date/time is required"
    return None


def _accept_guard(t: Task, _c: TaskContext) -> str | None:
    if t.business_status is not BusinessStatus.POTVRZENO:
        return "order must be confirmed (place and date) before acceptance"
    return None


def _start_guard(t: Task, ctx: TaskContext) -> str | None:
    open_deps = [d for d in t.depends_on if d not in ctx.completed_task_ids]
    return f"unfinished dependencies: {', '.join(open_deps)}" if open_deps else None


def _performed_guard(t: Task, _c: TaskContext) -> str | None:
    return None if t.business_status is BusinessStatus.POTVRZENO else "examination is not confirmed"


def _result_guard(t: Task, ctx: TaskContext) -> str | None:
    if t.business_status is not BusinessStatus.PROVEDENO:
        return "examination has not been performed"
    return None if ctx.result_doc_id else "result document is required"


_OC = frozenset({OWNER, Role.COORD})

_RULES: tuple[_Rule, ...] = (
    _Rule(
        "order_confirmed",
        TaskStatus.REQUESTED,
        _OC,
        _confirm_guard,
        lambda t, c: replace(
            t,
            business_status=BusinessStatus.POTVRZENO,
            place=c.place or t.place,
            scheduled_at=c.scheduled_at,
        ),
    ),
    _Rule(
        "accept",
        TaskStatus.REQUESTED,
        _OC,
        _accept_guard,
        lambda t, _c: replace(t, status=TaskStatus.ACCEPTED),
    ),
    _Rule(
        "start",
        TaskStatus.ACCEPTED,
        frozenset({OWNER}),
        _start_guard,
        lambda t, _c: replace(t, status=TaskStatus.IN_PROGRESS),
    ),
    _Rule(
        "performed",
        TaskStatus.IN_PROGRESS,
        frozenset({OWNER}),
        _performed_guard,
        lambda t, _c: replace(t, business_status=BusinessStatus.PROVEDENO),
    ),
    _Rule(
        "result_delivered",
        TaskStatus.IN_PROGRESS,
        frozenset({OWNER, Role.SYSTEM}),
        _result_guard,
        lambda t, c: replace(
            t,
            status=TaskStatus.COMPLETED,
            business_status=BusinessStatus.VYSLEDEK_DORUCEN,
            result_doc_id=c.result_doc_id,
        ),
    ),
    *(
        _Rule(
            "fail",
            s,
            _OC,
            _reason,
            lambda t, _c: replace(t, status=TaskStatus.FAILED),
            notify=((Role.COORD, "task.failed"),),
        )
        for s in (TaskStatus.ACCEPTED, TaskStatus.IN_PROGRESS)
    ),
    *(
        _Rule(
            "cancel",
            s,
            frozenset({Role.COORD}),
            _reason,
            lambda t, _c: replace(t, status=TaskStatus.CANCELLED),
        )
        for s in OPEN_STATUSES
    ),
)

TASK_EVENTS = tuple(dict.fromkeys(r.event for r in _RULES))
_BY_KEY = {(r.event, r.from_status): r for r in _RULES}


def transition(
    task: Task,
    event: str,
    actor: Role,
    ctx: TaskContext | None = None,
    at: datetime | None = None,
) -> TaskResult:
    ctx = ctx or TaskContext()
    at = at or clock.now()
    rule = _BY_KEY.get((event, task.status))
    if rule is None:
        raise TransitionError(
            "invalid_transition", f"event {event!r} not allowed in status {task.status.value!r}"
        )
    if actor not in rule.roles and not (OWNER in rule.roles and actor == task.owner_role):
        raise TransitionError("forbidden_role", f"role {actor.value!r} may not {event!r}")
    problem = rule.guard(task, ctx) if rule.guard else None
    if problem:
        raise TransitionError("guard_failed", problem)
    new = rule.update(task, ctx)
    audit = DomainEvent(
        EventKind.AUDIT,
        "update",
        at,
        {
            "task_id": task.id,
            "case_id": task.case_id,
            "event": event,
            "from": task.status.value,
            "to": new.status.value,
            "business_status": new.business_status.value,
            "actor_role": actor.value,
        },
    )
    notes = tuple(
        DomainEvent(EventKind.NOTIFICATION, tpl, at, {"task_id": task.id}, (r,))
        for r, tpl in rule.notify
    )
    return TaskResult(new, (audit, *notes))


# --- overdue detection -----------------------------------------------------------------------


def effective_deadline(task: Task) -> date:
    return min(task.due, task.sla_due) if task.sla_due else task.due


def check_overdue(task: Task, now: datetime | None = None) -> list[DomainEvent]:
    """Escalation events for `task` at `now` (empty if not overdue or already escalated).

    A task is overdue once the deadline day is over (today > deadline), so a result due Thu
    15. 10. escalates on Fri 16. 10.
    """
    now = now or clock.now()
    if task.status not in OPEN_STATUSES or task.escalated_at is not None:
        return []
    deadline = effective_deadline(task)
    today = now.astimezone(clock.TZ).date()
    if today <= deadline:
        return []
    return [
        DomainEvent(
            EventKind.ESCALATION,
            "task.overdue",
            now,
            {
                "task_id": task.id,
                "case_id": task.case_id,
                "code": task.code,
                "deadline": deadline.isoformat(),
                "basis": "sla" if task.sla_due and task.sla_due <= task.due else "due",
                "overdue_workdays": clock.workdays_between(deadline, today),
            },
            (Role.COORD,),
        )
    ]


def escalate_if_overdue(task: Task, now: datetime | None = None) -> TaskResult:
    """Like `check_overdue` but also stamps `escalated_at` so the escalation fires once."""
    now = now or clock.now()
    events = check_overdue(task, now)
    return TaskResult(replace(task, escalated_at=now) if events else task, tuple(events))
