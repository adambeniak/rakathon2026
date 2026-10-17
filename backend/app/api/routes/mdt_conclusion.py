"""GET /api/cases/{case_id}/mdt-conclusion: the signed MDT conclusion (written by the `record_mdt_conclusion` event)."""

from __future__ import annotations

from fastapi import APIRouter, Path

from app.api.deps import ActorDep, CaseWorkflowDep, DirectoryProviderDep
from app.api.schemas.common import problem_responses
from app.api.schemas.mdt_conclusion import MdtConclusionOut, SignedBy
from app.domain.common import BUSINESS_ID_PATTERN

router = APIRouter(prefix="/cases", tags=["cases"])

CaseId = Path(pattern=BUSINESS_ID_PATTERN, max_length=100, examples=["rakathon-2026-prochazkova"])


@router.get(
    "/{case_id}/mdt-conclusion",
    response_model=MdtConclusionOut,
    summary="The signed MDT conclusion of the case",
    description="404 until a KOC physician has signed the conclusion (`record_mdt_conclusion`). Participants of the "
    "case only; the referring GP can read it once the feedback has been sent. Every read is audited, but a read does "
    "not record `gp_opened`: the GP portal sends `POST /cases/{id}/transitions {event: gp_opened}` after showing it.",
    responses=problem_responses(401, 403, 404, 502, 503),
)
async def get_mdt_conclusion(
    workflow: CaseWorkflowDep, provider: DirectoryProviderDep, actor: ActorDep, case_id: str = CaseId
) -> MdtConclusionOut:
    record = await workflow.get_conclusion(case_id, actor=actor, directory=await provider.get())
    return MdtConclusionOut(
        text=record.text,
        signed_by=SignedBy(id=record.signer_id, display=record.signer_display, role=record.signer_role),
        signed_at=record.signed_at,
    )
