"""The case timeline: documents, case events, report requests, steps, the MDT and the feedback, oldest first.

Pure function over domain records (no FHIR, no I/O). Times are business times (the demo clock), as the workflow wrote
them. Whether a document is part of the MDT handover is decided here with the one as-of rule
(`app.extraction.lock.as_of_exclusion`) against the case's MDT start; the frontend only renders the flag.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, time

from app.domain.activity import RequestRecord, TimelineEvent, TimelineKind, WorkflowEvent
from app.domain.clock import TZ as PRAGUE
from app.domain.document import SourceDocument
from app.domain.task import Task
from app.extraction.lock import as_of_exclusion

# Case events with a kind of their own; every other case event is a `case_event` with its code and states.
_CASE_EVENT_KINDS = {
    "record_mdt_conclusion": TimelineKind.MDT_CONCLUSION,
    "send_feedback": TimelineKind.FEEDBACK_SENT,
    "delivery_confirmed": TimelineKind.FEEDBACK_DELIVERED,
    "gp_opened": TimelineKind.GP_OPENED,
}
# Kinds listed in this order when two events share the same instant (e.g. a report received and the request it
# fulfils, or the feedback sent and its relay receipt in one transaction).
_ORDER = {kind: index for index, kind in enumerate(TimelineKind)}


def build_timeline(
    *,
    documents: Sequence[SourceDocument],
    steps: Sequence[Task],
    requests: Sequence[RequestRecord],
    events: Sequence[WorkflowEvent],
    mdt_start: datetime | None,
    now: datetime,
) -> list[TimelineEvent]:
    """Every event once, oldest first. `planned` marks what lies after `now` (a scheduled step, the MDT meeting)."""
    docs = {d.doc_id: d for d in documents}
    titles = {**{s.id: s.title for s in steps}, **{r.task_id: r.label for r in requests}}
    out: list[TimelineEvent] = []

    for doc in documents:
        excluded = (
            None if mdt_start is None else as_of_exclusion(doc.authored_at, doc.received_at, mdt_start) is not None
        )
        authored = datetime.combine(doc.authored_at, time.min, tzinfo=PRAGUE)
        for kind, at, date_only in (
            (TimelineKind.DOCUMENT_AUTHORED, authored, True),
            (TimelineKind.DOCUMENT_RECEIVED, doc.received_at, False),
        ):
            out.append(
                TimelineEvent(
                    f"{kind.value}:{doc.doc_id}",
                    kind,
                    at,
                    date_only=date_only,
                    title=doc.title,
                    place=doc.custodian,
                    doc_id=doc.doc_id,
                    excluded_from_handover=excluded,
                )
            )

    for request in requests:
        if request.sent_at is not None:
            out.append(
                TimelineEvent(
                    f"request-sent:{request.task_id}",
                    TimelineKind.REQUEST_SENT,
                    request.sent_at,
                    title=request.label,
                    place=request.recipient,
                    task_id=request.task_id,
                )
            )

    for step in steps:
        if step.scheduled_at is not None:
            out.append(
                TimelineEvent(
                    f"step-scheduled:{step.id}",
                    TimelineKind.STEP_SCHEDULED,
                    step.scheduled_at,
                    title=step.title,
                    place=step.location,
                    task_id=step.id,
                    planned=step.scheduled_at > now,
                )
            )
        result = docs.get(step.result_doc_id) if step.result_doc_id else None
        if result is not None:
            out.append(
                TimelineEvent(
                    f"step-result:{step.id}",
                    TimelineKind.STEP_RESULT_DELIVERED,
                    result.received_at,
                    title=step.title,
                    place=step.location,
                    task_id=step.id,
                    doc_id=result.doc_id,
                )
            )
        if step.escalated_at is not None:
            out.append(
                TimelineEvent(
                    f"step-escalated:{step.id}",
                    TimelineKind.STEP_ESCALATED,
                    step.escalated_at,
                    title=step.title,
                    place=step.location,
                    task_id=step.id,
                )
            )

    for index, event in enumerate(events):
        item = _from_workflow_event(event, index, titles)
        if item is not None:
            out.append(item)

    if mdt_start is not None:
        out.append(TimelineEvent("mdt-meeting", TimelineKind.MDT_MEETING, mdt_start, planned=mdt_start > now))

    return sorted(out, key=lambda e: (e.at, _ORDER[e.kind], e.id))


def _from_workflow_event(event: WorkflowEvent, index: int, titles: dict[str, str]) -> TimelineEvent | None:
    """Case events, fulfilled requests and cancelled steps. `request_report` is skipped: the request itself (with
    its label and workplace) is the `request_sent` event."""
    at_id = f"{event.code}:{event.at.isoformat()}:{index}"
    if event.on_case:
        return TimelineEvent(
            f"case:{at_id}",
            _CASE_EVENT_KINDS.get(event.code, TimelineKind.CASE_EVENT),
            event.at,
            event=event.code,
            actor=event.actor_display,
            from_state=event.from_state,
            to_state=event.to_state if event.to_state != event.from_state else None,
            receipt_id=event.receipt_id if event.code == "delivery_confirmed" else None,
        )
    if event.code == "report_received":
        return TimelineEvent(
            f"request-fulfilled:{at_id}",
            TimelineKind.REQUEST_FULFILLED,
            event.at,
            title=titles.get(event.task_id or ""),
            task_id=event.task_id,
            doc_id=event.result_doc_id,
            actor=event.actor_display,
        )
    if event.code == "cancel":
        return TimelineEvent(
            f"step-cancelled:{at_id}",
            TimelineKind.STEP_CANCELLED,
            event.at,
            title=titles.get(event.task_id or ""),
            task_id=event.task_id,
            actor=event.actor_display,
        )
    return None
