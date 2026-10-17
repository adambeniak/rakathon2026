"""Task state machine: requested → accepted → in_progress → completed | failed | cancelled.

`business_status` tracks the real-world progress and only moves forward:
objednano → potvrzeno → provedeno → vysledek_dorucen.
Principle (FBMI): a sent request is not an ordered examination — `potvrzeno` needs a confirmed
date, and `completed` is impossible before the result has been delivered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from app.domain import clock
from app.domain.common import Role
from app.domain.events import DomainEvent, EventKind, TransitionError
from app.domain.task import Task, TaskBusinessStatus, TaskStatus

B = TaskBusinessStatus
OPEN_STATUSES = frozenset({TaskStatus.REQUESTED, TaskStatus.ACCEPTED, TaskStatus.IN_PROGRESS})


class _Owner:
    """Sentinel: the actor must hold the task's owner role."""


OWNER = _Owner()


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
    on_behalf: bool = False  # the coordinator recorded the step for an external workplace


Guard = Callable[[Task, TaskContext], str | None]


@dataclass(frozen=True)
class _Rule:
    event: str
    from_status: TaskStatus
    roles: frozenset[Role | _Owner]
    guard: Guard | None
    update: Callable[[Task, TaskContext], Task]
    notify: tuple[tuple[Role, str], ...] = ()


def _business(t: Task) -> TaskBusinessStatus:
    """A task without a business status has not been ordered yet."""
    return t.business_status or B.OBJEDNANO


def _owner_role(t: Task) -> Role | None:
    return t.owner.role if t.owner else t.owner_role


def _reason(_t: Task, ctx: TaskContext) -> str | None:
    return None if ctx.reason and ctx.reason.strip() else "Důvod je povinný"


def _confirm_guard(t: Task, ctx: TaskContext) -> str | None:
    if _business(t) is not B.OBJEDNANO:
        return "Objednání už bylo potvrzeno"
    if not (ctx.place or t.location):
        return "Je nutné zadat potvrzené místo"
    if ctx.scheduled_at is None:
        return "Je nutné zadat potvrzené datum a čas"
    if ctx.scheduled_at.utcoffset() is None:
        return "Potvrzené datum a čas musí obsahovat časové pásmo"
    return None


def _accept_guard(t: Task, _c: TaskContext) -> str | None:
    if _business(t) is not B.POTVRZENO:
        return "Před převzetím musí být objednání potvrzeno (místo a termín)"
    return None


def _start_guard(t: Task, ctx: TaskContext) -> str | None:
    open_deps = [d for d in t.depends_on if d not in ctx.completed_task_ids]
    return f"Nedokončené předcházející kroky: {', '.join(open_deps)}" if open_deps else None


def _performed_guard(t: Task, _c: TaskContext) -> str | None:
    return None if _business(t) is B.POTVRZENO else "Vyšetření není potvrzeno"


def _result_guard(t: Task, ctx: TaskContext) -> str | None:
    if _business(t) is not B.PROVEDENO:
        return "Vyšetření nebylo provedeno"
    return None if ctx.result_doc_id else "Je nutný dokument s výsledkem"


_OC: frozenset[Role | _Owner] = frozenset({OWNER, Role.COORDINATOR})
# SYSTEM may record start / performed / result only when a received result report proves them
# (`app.domain.task_results`, #132); the API refuses a SYSTEM actor, so no user reaches these through it.
_OWNER_SYSTEM: frozenset[Role | _Owner] = frozenset({OWNER, Role.SYSTEM})
_COORD_ONLY: frozenset[Role | _Owner] = frozenset({Role.COORDINATOR})

# External workplaces do not use Štafeta in the PoC: for steps they own, the coordinator records
# these events on their behalf (the audit trail says so).
ON_BEHALF_EVENTS = frozenset({"start", "performed", "result_delivered"})

_RULES: tuple[_Rule, ...] = (
    _Rule(
        "order_confirmed",
        TaskStatus.REQUESTED,
        _OC,
        _confirm_guard,
        lambda t, c: t.model_copy(
            update={
                "business_status": B.POTVRZENO,
                "location": c.place or t.location,
                "scheduled_at": c.scheduled_at,
            }
        ),
    ),
    _Rule(
        "accept",
        TaskStatus.REQUESTED,
        _OC,
        _accept_guard,
        lambda t, _c: t.model_copy(update={"status": TaskStatus.ACCEPTED}),
    ),
    _Rule(
        "start",
        TaskStatus.ACCEPTED,
        _OWNER_SYSTEM,
        _start_guard,
        lambda t, _c: t.model_copy(update={"status": TaskStatus.IN_PROGRESS}),
    ),
    _Rule(
        "performed",
        TaskStatus.IN_PROGRESS,
        _OWNER_SYSTEM,
        _performed_guard,
        lambda t, _c: t.model_copy(update={"business_status": B.PROVEDENO}),
    ),
    _Rule(
        "result_delivered",
        TaskStatus.IN_PROGRESS,
        _OWNER_SYSTEM,
        _result_guard,
        lambda t, c: t.model_copy(
            update={
                "status": TaskStatus.COMPLETED,
                "business_status": B.VYSLEDEK_DORUCEN,
                "result_doc_id": c.result_doc_id,
            }
        ),
    ),
    *(
        _Rule(
            "fail",
            s,
            _OC,
            _reason,
            lambda t, _c: t.model_copy(update={"status": TaskStatus.FAILED}),
            notify=((Role.COORDINATOR, "task.failed"),),
        )
        for s in (TaskStatus.ACCEPTED, TaskStatus.IN_PROGRESS)
    ),
    *(
        _Rule(
            "cancel",
            s,
            _COORD_ONLY,
            _reason,
            lambda t, _c: t.model_copy(update={"status": TaskStatus.CANCELLED}),
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
        raise TransitionError("invalid_transition", f"Událost {event!r} není ve stavu {task.status.value!r} povolena")
    owner_role = _owner_role(task)
    allowed = actor in rule.roles or (OWNER in rule.roles and actor == owner_role)
    on_behalf = (
        not allowed
        and event in ON_BEHALF_EVENTS
        and actor is Role.COORDINATOR
        and owner_role is Role.EXTERNAL_WORKPLACE
    )
    if not (allowed or on_behalf):
        raise TransitionError("forbidden_role", f"Role {actor.value!r} nemůže provést akci {event!r}")
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
            "business_status": _business(new).value,
            "actor_role": actor.value,
            **({"on_behalf_of_role": Role.EXTERNAL_WORKPLACE.value} if on_behalf else {}),
            **({"reason": ctx.reason} if event in {"fail", "cancel"} else {}),
        },
    )
    notes = tuple(DomainEvent(EventKind.NOTIFICATION, tpl, at, {"task_id": task.id}, (r,)) for r, tpl in rule.notify)
    return TaskResult(new, (audit, *notes), on_behalf=on_behalf)


# --- overdue detection -----------------------------------------------------------------------


def effective_deadline(task: Task) -> date | None:
    """Earliest of `due` and `sla_due`, as a Prague calendar day; None if the task has no deadline."""
    candidates = [d for d in (task.due, task.sla_due) if d is not None]
    return min(candidates).astimezone(clock.TZ).date() if candidates else None


@dataclass(frozen=True)
class OverdueInfo:
    deadline: date
    basis: str  # "sla" | "due"
    overdue_workdays: int


def overdue_info(task: Task, now: datetime | None = None) -> OverdueInfo | None:
    """Whether an open `task` is past its effective deadline at `now` (ignores `escalated_at`).

    A task is overdue once the deadline day is over (today > deadline), so a result due Thu
    15. 10. is overdue on Fri 16. 10.
    """
    now = now or clock.now()
    if task.status not in OPEN_STATUSES:
        return None
    deadline = effective_deadline(task)
    today = now.astimezone(clock.TZ).date()
    if deadline is None or today <= deadline:
        return None
    sla_first = task.sla_due is not None and (task.due is None or task.sla_due <= task.due)
    return OverdueInfo(deadline, "sla" if sla_first else "due", clock.workdays_between(deadline, today))


def check_overdue(task: Task, now: datetime | None = None) -> list[DomainEvent]:
    """Escalation events for `task` at `now` (empty if not overdue or already escalated)."""
    now = now or clock.now()
    info = overdue_info(task, now)
    if info is None or task.escalated_at is not None:
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
                "deadline": info.deadline.isoformat(),
                "basis": info.basis,
                "overdue_workdays": info.overdue_workdays,
            },
            (Role.COORDINATOR,),
        )
    ]


def escalate_if_overdue(task: Task, now: datetime | None = None) -> TaskResult:
    """Like `check_overdue` but also stamps `escalated_at` so the escalation fires once."""
    now = now or clock.now()
    events = check_overdue(task, now)
    return TaskResult(task.model_copy(update={"escalated_at": now}) if events else task, tuple(events))
