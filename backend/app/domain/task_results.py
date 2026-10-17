"""A received result report completes the pathway step it belongs to (#132).

Which report belongs to which step is a fixed, deterministic table: the step code from the PlanDefinition
(`CodeSystem/pathway-action`) → the LOINC document type that uploads get from their file name
(`app.documents.doc_type`). Only the diagnostic steps whose result is a report are listed; consultations
(algesiology, psycho-oncology) and the MDT are closed by people.

A report counts for a step only if all of this holds (otherwise nothing happens and a human closes the step):
- the step was ordered and accepted: status `accepted` or `in_progress`, so its date is confirmed (`scheduled_at`);
- the report was received at or before `now` (the demo clock may stand before an upload);
- it was authored on or after the confirmed date (an older CT or lab report of the same type is not this result).

The step then walks the real task machine to `vysledek_dorucen` (start → performed → result_delivered) as the system
actor; the machine's guards still apply (e.g. a step whose predecessors are open cannot start).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Final

from app.domain import clock
from app.domain.common import Role
from app.domain.document import SourceDocument
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.domain.task_machine import TaskContext, transition

# LOINC document types (same values as app.documents.doc_type; the domain does not import the parser).
_PATHOLOGY: Final = "11526-1"
_PROCEDURE_NOTE: Final = "28570-0"
_LAB_REPORT: Final = "11502-2"
_IMAGING: Final = "18748-4"

RESULT_TYPE_BY_STEP_CODE: Final[dict[str, str]] = {
    "histology": _PATHOLOGY,
    "eus-fnb": _PROCEDURE_NOTE,
    "labs-dx": _LAB_REPORT,
    "ct-thorax-abdomen": _IMAGING,
}

_AWAITING: Final = frozenset({TaskStatus.ACCEPTED, TaskStatus.IN_PROGRESS})


def result_type(task: Task) -> str | None:
    """LOINC type of the report that delivers `task`'s result, if the step is waiting for one."""
    if task.status not in _AWAITING or task.scheduled_at is None:
        return None
    if task.business_status is TaskBusinessStatus.VYSLEDEK_DORUCEN:
        return None
    return RESULT_TYPE_BY_STEP_CODE.get(task.code)


def matching_result(task: Task, documents: Iterable[SourceDocument], now: datetime) -> SourceDocument | None:
    """The earliest received report that delivers `task`'s result at `now`, or None."""
    wanted = result_type(task)
    if wanted is None or task.scheduled_at is None:
        return None
    scheduled_day = task.scheduled_at.astimezone(clock.TZ).date()
    candidates = [
        d for d in documents if d.type_code == wanted and d.received_at <= now and d.authored_at >= scheduled_day
    ]
    return min(candidates, key=lambda d: (d.received_at, d.doc_id), default=None)


def _pending_events(task: Task) -> list[str]:
    """Machine events still missing between `task`'s state and `vysledek_dorucen`."""
    business = task.business_status or TaskBusinessStatus.OBJEDNANO
    if task.status is TaskStatus.ACCEPTED:
        return ["start", "performed", "result_delivered"]
    if business is TaskBusinessStatus.PROVEDENO:
        return ["result_delivered"]
    return ["performed", "result_delivered"]


def deliver_result(task: Task, doc_id: str, completed_task_ids: Sequence[str], at: datetime) -> tuple[Task, list[str]]:
    """Walk `task` to `vysledek_dorucen` with `doc_id` as its result; raises TransitionError if a guard refuses."""
    ctx = TaskContext(result_doc_id=doc_id, completed_task_ids=frozenset(completed_task_ids))
    events = _pending_events(task)
    for event in events:
        task = transition(task, event, Role.SYSTEM, ctx, at).task
    return task, events
