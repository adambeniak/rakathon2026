"""build_timeline: one chronological list of documents, case events, requests, steps, MDT and feedback."""

from __future__ import annotations

from datetime import date, datetime

from app.domain.activity import RequestRecord, TimelineKind, WorkflowEvent
from app.domain.clock import TZ
from app.domain.document import SourceDocument
from app.domain.task import Task, TaskStatus
from app.timeline.events import build_timeline

MDT_START = datetime(2026, 10, 21, 8, 0, tzinfo=TZ)
NOW = datetime(2026, 10, 21, 10, 0, tzinfo=TZ)
CASE_ID = "rakathon-2026-prochazkova"


def _doc(doc_id: str, authored: date, received: datetime) -> SourceDocument:
    return SourceDocument(doc_id=doc_id, title=doc_id.split("_")[1], authored_at=authored, received_at=received)


HISTOLOGY = _doc("11_Histologie_KOC2_2026-10-19", date(2026, 10, 19), datetime(2026, 10, 19, 12, 10, tzinfo=TZ))
ALGEZIOLOGY = _doc("12_Algeziologie_2026-10-26", date(2026, 10, 26), datetime(2026, 10, 26, 14, 0, tzinfo=TZ))
# Authored before the MDT but received after it: still not part of the handover (as-of rule).
LATE = _doc("10_Laborator_2026-10-20", date(2026, 10, 20), datetime(2026, 10, 21, 9, 0, tzinfo=TZ))
STEP = Task(
    id=f"{CASE_ID}-histology",
    case_id=CASE_ID,
    code="histology",
    title="Histologie z EUS-FNB",
    status=TaskStatus.COMPLETED,
    location="KOC 2 – patologie",
    scheduled_at=datetime(2026, 10, 23, 9, 0, tzinfo=TZ),
    result_doc_id=HISTOLOGY.doc_id,
    escalated_at=datetime(2026, 10, 16, 8, 0, tzinfo=TZ),
)
REQUEST = RequestRecord(
    task_id=f"{CASE_ID}-req-1",
    label="RTG plic 3. 9. 2026",
    recipient="Radiologické centrum Modřany",
    sent_at=datetime(2026, 10, 2, 11, 30, tzinfo=TZ),
    status="completed",
)


def _event(code: str, at: datetime, *, on_case: bool = True, **kwargs: str) -> WorkflowEvent:
    return WorkflowEvent(code=code, at=at, on_case=on_case, actor_display="Bc. Lucie Dvořáková", **kwargs)  # type: ignore[arg-type]


EVENTS = [
    _event("accept", datetime(2026, 10, 2, 9, 40, tzinfo=TZ), from_state="odeslano", to_state="triage"),
    _event("request_report", REQUEST.sent_at or NOW, on_case=False, task_id=REQUEST.task_id),
    _event(
        "report_received",
        datetime(2026, 10, 3, 10, 0, tzinfo=TZ),
        on_case=False,
        task_id=REQUEST.task_id,
        result_doc_id="03_RTG_plic_2026-09-03",
    ),
    _event(
        "record_mdt_conclusion",
        datetime(2026, 10, 21, 9, 30, tzinfo=TZ),
        from_state="pripraveno_mdt",
        to_state="zaver_mdt",
    ),
    _event(
        "send_feedback",
        datetime(2026, 10, 21, 9, 45, tzinfo=TZ),
        from_state="zaver_mdt",
        to_state="zpetna_vazba_odeslana",
    ),
    _event(
        "delivery_confirmed",
        datetime(2026, 10, 21, 9, 45, tzinfo=TZ),
        from_state="zpetna_vazba_odeslana",
        to_state="zpetna_vazba_odeslana",
        receipt_id="<abc@stafeta>",
    ),
    _event("gp_opened", datetime(2026, 10, 22, 7, 0, tzinfo=TZ)),
    _event("cancel", datetime(2026, 10, 30, 9, 0, tzinfo=TZ), on_case=False, task_id=STEP.id),
]


def _timeline(mdt_start: datetime | None = MDT_START) -> list:  # type: ignore[type-arg]
    return build_timeline(
        documents=[HISTOLOGY, ALGEZIOLOGY, LATE],
        steps=[STEP],
        requests=[REQUEST],
        events=EVENTS,
        mdt_start=mdt_start,
        now=NOW,
    )


def test_events_are_merged_oldest_first_with_one_kind_each() -> None:
    kinds = [e.kind for e in _timeline()]

    assert kinds == [
        TimelineKind.CASE_EVENT,  # 2. 10. 09:40 accept
        TimelineKind.REQUEST_SENT,  # 2. 10. 11:30 (request_report itself is not listed twice)
        TimelineKind.REQUEST_FULFILLED,
        TimelineKind.STEP_ESCALATED,  # 16. 10.
        TimelineKind.DOCUMENT_AUTHORED,  # 19. 10. (day only)
        TimelineKind.DOCUMENT_RECEIVED,
        TimelineKind.STEP_RESULT_DELIVERED,  # same instant as the report: listed after it
        TimelineKind.DOCUMENT_AUTHORED,  # 20. 10.
        TimelineKind.MDT_MEETING,  # 21. 10. 08:00
        TimelineKind.DOCUMENT_RECEIVED,  # 21. 10. 09:00 (late report)
        TimelineKind.MDT_CONCLUSION,
        TimelineKind.FEEDBACK_SENT,
        TimelineKind.FEEDBACK_DELIVERED,
        TimelineKind.GP_OPENED,
        TimelineKind.STEP_SCHEDULED,  # 23. 10., after now: planned
        TimelineKind.DOCUMENT_AUTHORED,  # 26. 10.
        TimelineKind.DOCUMENT_RECEIVED,
        TimelineKind.STEP_CANCELLED,
    ]
    ids = [e.id for e in _timeline()]
    assert len(ids) == len(set(ids))


def test_documents_after_the_mdt_start_are_flagged_by_the_backend() -> None:
    flags = {
        (e.doc_id, e.kind): e.excluded_from_handover
        for e in _timeline()
        if e.kind in (TimelineKind.DOCUMENT_AUTHORED, TimelineKind.DOCUMENT_RECEIVED)
    }

    assert flags[(HISTOLOGY.doc_id, TimelineKind.DOCUMENT_RECEIVED)] is False
    assert flags[(ALGEZIOLOGY.doc_id, TimelineKind.DOCUMENT_AUTHORED)] is True
    assert flags[(LATE.doc_id, TimelineKind.DOCUMENT_RECEIVED)] is True  # received after the MDT start
    assert {e.excluded_from_handover for e in _timeline() if e.doc_id is None} == {None}


def test_without_an_mdt_start_nothing_is_flagged_and_no_meeting_is_listed() -> None:
    timeline = _timeline(mdt_start=None)

    assert {e.excluded_from_handover for e in timeline} == {None}  # unknown, never a guessed "included"
    assert TimelineKind.MDT_MEETING not in {e.kind for e in timeline}


def test_case_events_carry_codes_states_receipt_and_titles_come_from_the_records() -> None:
    by_kind = {e.kind: e for e in _timeline()}

    accept = by_kind[TimelineKind.CASE_EVENT]
    assert (accept.event, accept.from_state, accept.to_state) == ("accept", "odeslano", "triage")
    delivered = by_kind[TimelineKind.FEEDBACK_DELIVERED]
    assert delivered.receipt_id == "<abc@stafeta>"
    assert delivered.to_state is None  # no state change
    assert by_kind[TimelineKind.REQUEST_FULFILLED].title == "RTG plic 3. 9. 2026"
    assert by_kind[TimelineKind.STEP_CANCELLED].title == "Histologie z EUS-FNB"
    assert by_kind[TimelineKind.STEP_SCHEDULED].planned is True
    assert by_kind[TimelineKind.MDT_MEETING].planned is False  # 08:00 is before now (10:00)
    authored = next(e for e in _timeline() if e.kind is TimelineKind.DOCUMENT_AUTHORED)
    assert authored.date_only is True
    assert authored.at == datetime(2026, 10, 19, 0, 0, tzinfo=TZ)
