"""GET /api/cases/{case_id}/audit, /timeline and /messages: what happened on a case, read back from its own records.

Only the KOC team of the case (coordinator, KOC physician, KOC staff) may read them; the role is checked before any
clinical content is read, so a refused caller causes no audited read. Every successful read is audited, including the
read of the audit trail itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import ActorDep, CaseReaderDep, CaseRecordsDep, DirectoryProviderDep, SettingsDep
from app.api.schemas.activity import (
    AuditEntry,
    CaseAuditTrail,
    CaseMessage,
    CaseTimeline,
    MessageDelivery,
    MessageRequestInfo,
    MessageStatus,
    TimelineEntry,
)
from app.api.schemas.common import problem_responses
from app.domain.activity import MessageKind, MessageRecord, RequestRecord
from app.domain.common import BUSINESS_ID_PATTERN, PartyRef, Role
from app.domain.errors import ForbiddenError
from app.domain.task import TaskStatus
from app.fhir.cases import CaseReader, LoadedCase
from app.fhir.directory import DirectoryProvider
from app.fhir.workflow import authorize_case
from app.timeline.events import build_timeline

router = APIRouter(prefix="/cases", tags=["cases"])

CaseId = Annotated[str, Path(pattern=BUSINESS_ID_PATTERN, max_length=100, examples=["rakathon-2026-prochazkova"])]
# The audit trail, the timeline and the messages are the KOC's working view of the case; the GP has the portal and
# the insurer's reviewer the reviewer overview.
KOC_ROLES = frozenset({Role.COORDINATOR, Role.KOC_PHYSICIAN, Role.KOC_STAFF})
FORBIDDEN_TEXT = "Průběh případu je dostupný jen týmu KOC, který případ vede"
_CANCELLED = {TaskStatus.CANCELLED.value, TaskStatus.FAILED.value}


async def _load_for_koc(case_id: str, actor: PartyRef, reader: CaseReader, provider: DirectoryProvider) -> LoadedCase:
    if actor.role not in KOC_ROLES:  # checked first: a refused caller causes no audited read of clinical content
        raise ForbiddenError(FORBIDDEN_TEXT)
    loaded = await reader.load(case_id)  # audited read
    authorize_case(loaded, actor, await provider.get())
    return loaded


@router.get(
    "/{case_id}/audit",
    response_model=CaseAuditTrail,
    summary="Audit trail of the case (who, when, what kind of action)",
    description="AuditEvents naming the case's coordinating Task, EpisodeOfCare, steps, report requests, documents "
    "and messages, newest first, paged by `offset`/`limit`. Codes only (workflow event or interaction, record "
    "types, outcome) — no free-text reasons or clinical content. KOC team of the case only; the read is audited.",
    responses=problem_responses(401, 403, 404, 422, 502, 503),
)
async def get_case_audit(
    reader: CaseReaderDep,
    records: CaseRecordsDep,
    provider: DirectoryProviderDep,
    actor: ActorDep,
    case_id: CaseId,
    limit: Annotated[int, Query(ge=1, le=500, description="Page size.")] = 100,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> CaseAuditTrail:
    loaded = await _load_for_koc(case_id, actor, reader, provider)
    trail = await records.audit_trail(loaded)
    page = trail.records[offset : offset + limit]
    return CaseAuditTrail(
        case_id=case_id,
        items=[
            AuditEntry(
                recorded=r.recorded,
                actor=r.actor_display,
                actor_role=r.actor_role,
                on_behalf_of=r.on_behalf_of,
                action=r.action,
                operation=r.operation,
                workflow_event=r.workflow_event,
                entity_types=list(r.entity_types),
                outcome=r.outcome,
            )
            for r in page
        ],
        total=len(trail.records),
        offset=offset,
        limit=limit,
        truncated=offset + limit < len(trail.records),
    )


@router.get(
    "/{case_id}/timeline",
    response_model=CaseTimeline,
    summary="Timeline of the case",
    description="Documents (authored and received), case events and state changes, report requests and their "
    "fulfilment, step dates (scheduled, result delivered, escalated, cancelled), the MDT meeting and conclusion, and "
    "the feedback to the GP (sent, accepted by the relay, opened by the GP), oldest first, in business time. "
    "`excluded_from_handover` is the backend's as-of decision against the MDT start. KOC team of the case only; the "
    "read is audited.",
    responses=problem_responses(401, 403, 404, 422, 502, 503),
)
async def get_case_timeline(
    reader: CaseReaderDep,
    records: CaseRecordsDep,
    provider: DirectoryProviderDep,
    actor: ActorDep,
    settings: SettingsDep,
    case_id: CaseId,
) -> CaseTimeline:
    loaded = await _load_for_koc(case_id, actor, reader, provider)
    sources = await records.timeline_sources(loaded)
    now = settings.now()
    events = build_timeline(
        documents=sources.documents,
        steps=sources.steps,
        requests=sources.requests,
        events=sources.events,
        mdt_start=loaded.case.mdt_start,
        now=now,
    )
    return CaseTimeline(
        case_id=case_id,
        as_of=loaded.case.mdt_start,
        now=now,
        events=[TimelineEntry.model_validate(e, from_attributes=True) for e in events],
    )


@router.get(
    "/{case_id}/messages",
    response_model=list[CaseMessage],
    summary="Messages of the case",
    description="Report requests sent to workplaces (CommunicationRequest, with the state of their tracking task) and "
    "the MDT feedback e-mail to the referring GP (Communication, with the relay's receipt id and when the GP opened "
    "it), oldest first. KOC team of the case only; the read is audited.",
    responses=problem_responses(401, 403, 404, 422, 502, 503),
)
async def get_case_messages(
    reader: CaseReaderDep,
    records: CaseRecordsDep,
    provider: DirectoryProviderDep,
    actor: ActorDep,
    case_id: CaseId,
) -> list[CaseMessage]:
    loaded = await _load_for_koc(case_id, actor, reader, provider)
    found = await records.messages(loaded, await provider.get())
    gp_opened_at = None
    if any(m.kind is MessageKind.MDT_FEEDBACK for m in found.messages):
        gp_opened_at = (await reader.activity(loaded.task, loaded.case, waivers=False)).gp_opened_at
    return [_message_out(m, found.requests.get(m.id), gp_opened_at) for m in found.messages]


def _message_out(message: MessageRecord, request: RequestRecord | None, gp_opened_at: datetime | None) -> CaseMessage:
    if message.kind is MessageKind.MDT_FEEDBACK:
        return CaseMessage(
            id=message.id,
            kind=message.kind,
            status="sent",
            sent_at=message.sent_at,
            sender=message.sender,
            recipient=message.recipient,
            text=message.text,
            delivery=MessageDelivery(receipt_id=message.receipt_id, gp_opened_at=gp_opened_at),
        )
    return CaseMessage(
        id=message.id,
        kind=message.kind,
        status=_request_status(message, request),
        sent_at=message.sent_at,
        sender=message.sender,
        recipient=message.recipient,
        text=message.text,
        request=MessageRequestInfo(
            request_id=request.task_id,
            status=TaskStatus(request.status),
            due=request.due,
            exam_date=request.exam_date,
            result_doc_id=request.result_doc_id,
        )
        if request is not None
        else None,
    )


def _request_status(message: MessageRecord, request: RequestRecord | None) -> MessageStatus:
    """The tracking task decides; without one, the CommunicationRequest status."""
    if request is not None:
        if request.status == TaskStatus.COMPLETED.value:
            return "fulfilled"
        return "cancelled" if request.status in _CANCELLED else "open"
    if message.fhir_status == "completed":
        return "fulfilled"
    return "cancelled" if message.fhir_status in ("revoked", "entered-in-error") else "open"
