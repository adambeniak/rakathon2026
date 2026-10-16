"""POST /api/cases/{case_id}/transitions: one entry point to the case state machine."""

from __future__ import annotations

from fastapi import APIRouter, Path

from app.api.deps import (
    ActorDep,
    CaseReaderDep,
    CaseWorkflowDep,
    DirectoryProviderDep,
    RequestWorkflowDep,
    SettingsDep,
    TriageReaderDep,
)
from app.api.routes.cases import summary_fields
from app.api.schemas.cases import CaseSummary
from app.api.schemas.common import problem_responses
from app.api.schemas.workflow import (
    DocumentRequestOut,
    DocumentRequestsBody,
    DocumentRequestsCreated,
    ProposalsOut,
    TransitionRequest,
)
from app.domain.common import BUSINESS_ID_PATTERN
from app.fhir.workflow import RequestItem, RequestView

router = APIRouter(prefix="/cases", tags=["cases"])

CaseId = Path(pattern=BUSINESS_ID_PATTERN, max_length=100, examples=["rakathon-2026-prochazkova"])


@router.post(
    "/{case_id}/transitions",
    response_model=CaseSummary,
    summary="Apply a case event (state machine)",
    description="Forbidden transitions answer 409 problem+json with `code` = invalid_transition | forbidden_role | "
    "guard_failed | case_postponed. The acting role comes from the `X-Demo-Role` header (demo mode).",
    responses=problem_responses(401, 404, 409, 422, 502, 503),
)
async def transition_case(
    body: TransitionRequest,
    workflow: CaseWorkflowDep,
    reader: CaseReaderDep,
    provider: DirectoryProviderDep,
    actor: ActorDep,
    settings: SettingsDep,
    case_id: str = CaseId,
) -> CaseSummary:
    directory = await provider.get()
    await workflow.transition(
        case_id,
        body.event,
        actor=actor,
        directory=directory,
        now=settings.now(),
        reason=body.reason,
        resume_on=body.resume_on,
    )
    overview = await reader.overview(case_id)
    return CaseSummary.model_validate(
        {
            **summary_fields(overview.case, settings.now().date(), overview.extras),
            "document_count": overview.document_count,
        }
    )


def _request_out(view: RequestView) -> DocumentRequestOut:
    task = view.task
    return DocumentRequestOut(
        id=task.id,
        label=task.title.removeprefix("Vyžádat výsledek: "),
        recipient=task.location,
        exam_date=view.exam_date,
        due=task.due,
        status=task.status,
        business_status=task.business_status,
        result_doc_id=task.result_doc_id,
    )


@router.get(
    "/{case_id}/document-requests/proposals",
    response_model=ProposalsOut,
    summary="Reports the referral letter lists but nobody attached (triage notice)",
    description="Quoted from the letter, each with its evidence; the workplace is resolved from the directory or left "
    "empty for the coordinator. The proposals are facts from the letter, not a recommendation of examinations.",
    responses=problem_responses(401, 404, 502, 503),
)
async def document_request_proposals(
    triage: TriageReaderDep, provider: DirectoryProviderDep, actor: ActorDep, case_id: str = CaseId
) -> ProposalsOut:
    view = await triage.proposals(case_id, await provider.get(), actor)
    return ProposalsOut(source_doc_id=view.source_doc_id, proposals=view.proposals)


@router.get(
    "/{case_id}/document-requests",
    response_model=list[DocumentRequestOut],
    summary="Report requests of the case",
    responses=problem_responses(401, 404, 502, 503),
)
async def list_document_requests(
    workflow: RequestWorkflowDep, provider: DirectoryProviderDep, actor: ActorDep, case_id: str = CaseId
) -> list[DocumentRequestOut]:
    views = await workflow.list_requests(case_id, actor=actor, directory=await provider.get())
    return [_request_out(v) for v in views]


@router.post(
    "/{case_id}/document-requests",
    status_code=201,
    response_model=DocumentRequestsCreated,
    summary="Request reports from workplaces (one click)",
    description="Creates a CommunicationRequest and a tracking Task (owner: the coordinator, due: +2 working days) per "
    "item. While the case is in `triage` the same transaction moves it to `ceka_na_podklady`. Coordinator only.",
    responses=problem_responses(401, 404, 409, 422, 502, 503),
)
async def create_document_requests(
    body: DocumentRequestsBody,
    workflow: RequestWorkflowDep,
    reader: CaseReaderDep,
    provider: DirectoryProviderDep,
    actor: ActorDep,
    settings: SettingsDep,
    case_id: str = CaseId,
) -> DocumentRequestsCreated:
    outcome = await workflow.create_requests(
        case_id,
        [RequestItem(i.label, i.recipient_org_id, i.exam_date) for i in body.items],
        actor=actor,
        directory=await provider.get(),
        now=settings.now(),
    )
    overview = await reader.overview(case_id)
    case = CaseSummary.model_validate(
        {
            **summary_fields(overview.case, settings.now().date(), overview.extras),
            "document_count": overview.document_count,
        }
    )
    return DocumentRequestsCreated(case=case, requests=[_request_out(v) for v in outcome.requests])
