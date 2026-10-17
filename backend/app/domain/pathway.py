"""Diagnostic pathway template → Tasks, and the MDT readiness gate.

All due-date offsets in a template are DEMO ASSUMPTIONS, not clinical guidelines. The template is a typed,
FHIR-independent structure; parsing the FHIR PlanDefinition into it is `app.fhir.mappers.plan_definition`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from app.domain import clock
from app.domain.case import Case
from app.domain.common import Role
from app.domain.task import Task, TaskBusinessStatus, TaskStatus


class Anchor(StrEnum):
    START = "start"  # pathway start date
    MDT = "mdt"  # case.mdt_start
    STEP = "step"  # the resolved due date of another step


@dataclass(frozen=True)
class DueRule:
    anchor: Anchor
    days: int
    workdays: bool = False
    step_id: str | None = None  # required when anchor is STEP


@dataclass(frozen=True)
class PathwayStep:
    id: str
    code: str
    title: str
    owner_role: Role
    location: str | None
    due: DueRule
    after: tuple[str, ...] = ()  # step ids that must be completed first
    sla: DueRule | None = None  # agreed deadline, may be earlier than `due`


@dataclass(frozen=True)
class PathwayTemplate:
    id: str
    title: str
    steps: tuple[PathwayStep, ...]
    mdt_required_items: tuple[str, ...]


def _resolve(rule: DueRule, start: date, mdt: date | None, resolved: Mapping[str, date]) -> date:
    if rule.anchor is Anchor.START:
        base = start
    elif rule.anchor is Anchor.MDT:
        if mdt is None:
            raise ValueError("pathway needs case.mdt_start")
        base = mdt
    else:
        if rule.step_id is None or rule.step_id not in resolved:
            raise ValueError(f"anchor {rule.step_id!r} unresolved (cycle or unknown step)")
        base = resolved[rule.step_id]
    return clock.add_workdays(base, rule.days) if rule.workdays else base + timedelta(days=rule.days)


def _end_of_day(d: date) -> datetime:
    """Deadlines are calendar days; store them as the last second of that day (Prague)."""
    return datetime.combine(d, time(23, 59, 59), tzinfo=clock.TZ)


def instantiate(template: PathwayTemplate, case: Case, start_date: date) -> list[Task]:
    """Tasks for `case` in dependency order (every task comes after all it depends on)."""
    by_id = {st.id: st for st in template.steps}
    for st in template.steps:
        for ref in st.after:
            if ref not in by_id:
                raise ValueError(f"step {st.id!r} references unknown step {ref!r}")

    mdt = case.mdt_start.astimezone(clock.TZ).date() if case.mdt_start else None
    order: list[str] = []
    pending = dict(by_id)
    while pending:
        ready = [i for i, st in pending.items() if all(d in order for d in st.after)]
        if not ready:
            raise ValueError(f"dependency cycle among steps: {sorted(pending)}")
        for i in ready:  # stable: follows template order
            order.append(i)
            del pending[i]

    due: dict[str, date] = {}
    tasks: list[Task] = []
    for sid in order:
        st = by_id[sid]
        # anchors may point to any already-ordered step, even without an `after` link
        due[sid] = _resolve(st.due, start_date, mdt, due)
        sla = _resolve(st.sla, start_date, mdt, due) if st.sla else None
        tasks.append(
            Task(
                id=f"{case.id}.{sid}",
                case_id=case.id,
                code=st.code,
                title=st.title,
                status=TaskStatus.REQUESTED,
                business_status=TaskBusinessStatus.OBJEDNANO,
                owner_role=st.owner_role,
                location=st.location,
                due=_end_of_day(due[sid]),
                depends_on=[f"{case.id}.{d}" for d in st.after],
                sla_due=_end_of_day(sla) if sla else None,
                demo_assumption=True,
            )
        )
    return tasks


# --- MDT readiness gate ----------------------------------------------------------------------

# Handover field statuses (shared enum, see AGENTS.md). Only `missing` blocks the gate; the rest
# is surfaced as a warning so a human decides.
BLOCKING = frozenset({"missing"})
SATISFIED = frozenset({"complete", "generated_with_citations"})


@dataclass(frozen=True)
class Waiver:
    item: str
    by_role: Role
    by: str  # user id
    reason: str


@dataclass(frozen=True)
class Readiness:
    ready: bool
    missing: tuple[str, ...]  # blocking and NOT waived
    waived: tuple[Waiver, ...]
    warnings: tuple[str, ...] = ()  # items present but partial/stale/conflicting


def readiness_gate(statuses: Mapping[str, str], required: Sequence[str], waivers: Sequence[Waiver] = ()) -> Readiness:
    """Gate for `pripraveno_mdt`. Items absent from `statuses` count as missing.

    Waivers are valid only from a physician (KOC_PHYSICIAN) with a clinician id and a non-empty reason; anything else
    raises ValueError. A waiver for an item that is not blocking is ignored.
    """
    for w in waivers:
        if w.item not in required:
            raise ValueError(f"Prominutí neznámé položky {w.item!r}")
        if w.by_role is not Role.KOC_PHYSICIAN:
            raise ValueError("Položku připravenosti může prominout jen lékař KOC")
        if not w.by.strip():
            raise ValueError("Prominutí vyžaduje identifikátor lékaře")
        if not w.reason.strip():
            raise ValueError("Prominutí vyžaduje důvod")
    blocking = [i for i in required if statuses.get(i, "missing") in BLOCKING]
    waived_by_item = {w.item: w for w in waivers}
    missing = tuple(i for i in blocking if i not in waived_by_item)
    waived = tuple(waived_by_item[i] for i in blocking if i in waived_by_item)
    warnings = tuple(i for i in required if i not in blocking and statuses.get(i) not in SATISFIED)
    return Readiness(not missing, missing, waived, warnings)
