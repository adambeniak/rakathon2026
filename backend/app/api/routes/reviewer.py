"""GET /api/reviewer/cases and /api/reviewer/cases/{ref}: the insurer reviewer's minimal, pseudonymous case view."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response

from app.api.deps import ActorDep, CaseReaderDep, DirectoryProviderDep, SettingsDep
from app.api.schemas.common import problem_responses
from app.api.schemas.reviewer import REVIEWER_REF_PATTERN, ReviewerCase
from app.api.services.reviewer import ReviewerCases

router = APIRouter(prefix="/reviewer", tags=["reviewer"])


async def get_reviewer_cases(
    reader: CaseReaderDep, actor: ActorDep, directory: DirectoryProviderDep, settings: SettingsDep
) -> ReviewerCases:
    return ReviewerCases(reader, actor, await directory.get(), settings.reviewer_pseudonym_key)


ReviewerCasesDep = Annotated[ReviewerCases, Depends(get_reviewer_cases)]


def _no_store(response: Response) -> None:
    """Personal data scoped by the acting role: never cached, and never served from a cache to another role."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "X-Demo-Role, Authorization"


@router.get(
    "/cases",
    response_model=list[ReviewerCase],
    summary="Cases of the reviewer's insured persons (minimal, pseudonymous)",
    description="Only for the `reviewer` role (others 403). Only cases of the reviewer's own insurer. No name, birth "
    "date, birth number or clinical text; T1-T3 are proxies and null when an end point is not recorded. Audited.",
    responses=problem_responses(401, 403, 500, 502, 503),
)
async def list_reviewer_cases(service: ReviewerCasesDep, response: Response) -> list[ReviewerCase]:
    _no_store(response)
    return await service.list()


@router.get(
    "/cases/{ref}",
    response_model=ReviewerCase,
    summary="One case of the reviewer's insured persons (minimal, pseudonymous)",
    description="404 also for a case of another insurer, so its existence is not confirmed. Audited.",
    responses=problem_responses(401, 403, 404, 422, 500, 502, 503),
)
async def get_reviewer_case(
    service: ReviewerCasesDep,
    response: Response,
    ref: str = Path(pattern=REVIEWER_REF_PATTERN, examples=["RV-3F9A2C1B7D40"]),
) -> ReviewerCase:
    _no_store(response)
    return await service.get(ref)
