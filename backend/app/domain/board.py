"""Coordination board: who holds the baton, lane per owner role, overdue and blocked steps.

Pure functions over a case's tasks — the API supplies the tasks and the clock.
Lane = role of the concrete owner, else the step's `owner_role`. Lane keys are roles; the Czech lane
labels (PL · Koordinátor · Lékař KOC · Externí pracoviště · Pacient) belong to the UI.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.domain import clock
from app.domain.common import PartyRef, Role
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.domain.task_machine import OPEN_STATUSES, overdue_info

LANE_ORDER: tuple[Role, ...] = (
    Role.GP,
    Role.COORDINATOR,
    Role.KOC_PHYSICIAN,
    Role.EXTERNAL_WORKPLACE,
    Role.PATIENT,
)
_LANE_ALIASES: dict[Role, Role] = {Role.KOC_STAFF: Role.KOC_PHYSICIAN}
MDT_TASK_CODE = "mdt"
FAR_FUTURE = datetime(9999, 1, 1, tzinfo=clock.TZ)


class BatonBasis(StrEnum):
    REQUIRED_FOR_MDT = "required_for_mdt"  # open step the MDT readiness depends on (logistics, not clinical priority)
    OTHER_PATHWAY = "other_pathway"  # open pathway step the MDT does not wait for
    AD_HOC = "ad_hoc"  # only single tasks are open


class BatonReason(StrEnum):
    """Why the baton sits with this role."""

    ACTION = "action"  # the step's owner is to act (do the examination / deliver the result)
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # nothing is ordered yet: the coordinator confirms place and date
    DEPENDENCY_FAILED = "dependency_failed"  # a prerequisite failed or was cancelled: the coordinator decides


class AlertKind(StrEnum):
    SLA_BREACH = "sla_breach"  # a promised turnaround was missed
    OVERDUE = "overdue"  # the planned due date passed


@dataclass(frozen=True)
class BoardTask:
    task: Task
    lane: Role
    critical: bool
    overdue: bool
    overdue_workdays: int
    blocked_by: tuple[str, ...]


@dataclass(frozen=True)
class BoardLane:
    role: Role
    tasks: tuple[BoardTask, ...]


@dataclass(frozen=True)
class BatonHolder:
    role: Role
    owner: PartyRef | None
    task_id: str
    task_title: str
    due: datetime | None
    basis: BatonBasis
    reason: BatonReason
    demo_assumption: bool


@dataclass(frozen=True)
class Board:
    case_id: str
    as_of: datetime
    lanes: tuple[BoardLane, ...]
    baton_holder: BatonHolder | None


@dataclass(frozen=True)
class Alert:
    task_id: str
    case_id: str
    code: str
    title: str
    kind: AlertKind
    deadline: date
    basis: str
    overdue_workdays: int
    escalated_at: datetime | None
    recipients: tuple[Role, ...]
    demo_assumption: bool


def due_order(task: Task) -> tuple[datetime, str]:
    """Sort key for listings: earliest due date first (= dependency order in the pathway), ties by id."""
    return task.due or FAR_FUTURE, task.id


def lane_of(task: Task) -> Role:
    role = task.owner.role if task.owner else task.owner_role
    if role is None:
        return Role.COORDINATOR
    role = _LANE_ALIASES.get(role, role)
    return role if role in LANE_ORDER else Role.COORDINATOR


def critical_path_ids(tasks: Sequence[Task]) -> frozenset[str]:
    """The MDT step plus everything it transitively waits for (ad-hoc tasks excluded).

    Without an MDT step every pathway step counts as critical.
    """
    pathway = {t.id: t for t in tasks if not t.ad_hoc}
    mdt = next((t for t in pathway.values() if t.code == MDT_TASK_CODE), None)
    if mdt is None:
        return frozenset(pathway)
    seen: set[str] = set()
    stack = [mdt.id]
    while stack:
        tid = stack.pop()
        if tid in seen or tid not in pathway:
            continue
        seen.add(tid)
        stack.extend(pathway[tid].depends_on)
    return frozenset(seen)


def _holder(task: Task, basis: BatonBasis, dead: set[str]) -> BatonHolder:
    """Whose turn it is on `task`: the coordinator until the order is confirmed or when a prerequisite is dead."""
    business = task.business_status or TaskBusinessStatus.OBJEDNANO
    if any(d in dead for d in task.depends_on):
        reason = BatonReason.DEPENDENCY_FAILED
    elif task.status is TaskStatus.REQUESTED and business is TaskBusinessStatus.OBJEDNANO:
        reason = BatonReason.AWAITING_CONFIRMATION
    else:
        return BatonHolder(
            lane_of(task), task.owner, task.id, task.title, task.due, basis, BatonReason.ACTION, task.demo_assumption
        )
    return BatonHolder(Role.COORDINATOR, None, task.id, task.title, task.due, basis, reason, task.demo_assumption)


def _baton(tasks: Sequence[Task], critical: frozenset[str]) -> BatonHolder | None:
    completed = {t.id for t in tasks if t.status is TaskStatus.COMPLETED}
    dead = {t.id for t in tasks if t.status in (TaskStatus.FAILED, TaskStatus.CANCELLED)}
    open_tasks = [(i, t) for i, t in enumerate(tasks) if t.status in OPEN_STATUSES]
    tiers = (
        (BatonBasis.REQUIRED_FOR_MDT, [(i, t) for i, t in open_tasks if t.id in critical]),
        (BatonBasis.OTHER_PATHWAY, [(i, t) for i, t in open_tasks if t.id not in critical and not t.ad_hoc]),
        (BatonBasis.AD_HOC, [(i, t) for i, t in open_tasks if t.ad_hoc]),
    )
    for basis, candidates in tiers:
        if candidates:
            # A step still waiting for unfinished prerequisites cannot be acted on: prefer the ones that can.
            ready = [c for c in candidates if all(d in completed for d in c[1].depends_on)]
            _, first = min(ready or candidates, key=lambda it: (it[1].due or FAR_FUTURE, it[0]))
            return _holder(first, basis, dead)
    return None


def build_board(case_id: str, tasks: Sequence[Task], now: datetime) -> Board:
    """Board at `now`. Task order within a lane follows the order of `tasks` (pathway order)."""
    critical = critical_path_ids(tasks)
    completed = {t.id for t in tasks if t.status is TaskStatus.COMPLETED}
    by_lane: dict[Role, list[BoardTask]] = {r: [] for r in LANE_ORDER}
    for t in tasks:
        info = overdue_info(t, now)
        by_lane[lane_of(t)].append(
            BoardTask(
                task=t,
                lane=lane_of(t),
                critical=t.id in critical,
                overdue=info is not None,
                overdue_workdays=info.overdue_workdays if info else 0,
                blocked_by=tuple(d for d in t.depends_on if d not in completed) if t.status in OPEN_STATUSES else (),
            )
        )
    lanes = tuple(BoardLane(r, tuple(by_lane[r])) for r in LANE_ORDER)
    return Board(case_id, now, lanes, _baton(tasks, critical))


def collect_alerts(tasks: Sequence[Task], now: datetime) -> list[Alert]:
    """Overdue open tasks, SLA breaches included (already-escalated ones too), worst first."""
    alerts: list[Alert] = []
    for t in tasks:
        info = overdue_info(t, now)
        if info is None:
            continue
        alerts.append(
            Alert(
                task_id=t.id,
                case_id=t.case_id,
                code=t.code,
                title=t.title,
                kind=AlertKind.SLA_BREACH if info.basis == "sla" else AlertKind.OVERDUE,
                deadline=info.deadline,
                basis=info.basis,
                overdue_workdays=info.overdue_workdays,
                escalated_at=t.escalated_at,
                recipients=(Role.COORDINATOR,),
                demo_assumption=t.demo_assumption,
            )
        )
    return sorted(alerts, key=lambda a: (a.deadline, a.task_id))
