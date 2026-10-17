"""Care pathway of a case: launch the pathway, board with the baton holder, SLA alerts, single tasks."""

from __future__ import annotations

from fastapi import APIRouter, Path

from app.api.deps import ActorDep, CoordinationDep
from app.api.schemas.common import problem_responses
from app.api.schemas.coordination import (
    AlertOut,
    Board,
    CreateTaskRequest,
    LaunchPathwayRequest,
    PathwayLaunched,
    TaskOut,
)
from app.domain.common import BUSINESS_ID_PATTERN

router = APIRouter(prefix="/cases", tags=["coordination"])

CaseId = Path(pattern=BUSINESS_ID_PATTERN, max_length=100, examples=["rakathon-2026-prochazkova"])


@router.post(
    "/{case_id}/pathways",
    status_code=201,
    response_model=PathwayLaunched,
    summary="Launch a care pathway (CarePlan + step tasks) for the case",
    responses=problem_responses(403, 404, 409, 422, 500, 502, 503),
)
async def launch_pathway(
    request: LaunchPathwayRequest, service: CoordinationDep, actor: ActorDep, case_id: str = CaseId
) -> PathwayLaunched:
    return await service.launch_pathway(case_id, request, actor)


@router.get(
    "/{case_id}/board",
    response_model=Board,
    summary="Board: lanes by owner role and the baton holder of the case",
    responses=problem_responses(401, 403, 404, 422, 500, 502, 503),
)
async def get_board(service: CoordinationDep, actor: ActorDep, case_id: str = CaseId) -> Board:
    return await service.board(case_id, actor)


@router.get(
    "/{case_id}/alerts",
    response_model=list[AlertOut],
    summary="Overdue tasks and missed promised turnarounds at the (demo) current time",
    responses=problem_responses(401, 403, 404, 422, 500, 502, 503),
)
async def get_alerts(service: CoordinationDep, actor: ActorDep, case_id: str = CaseId) -> list[AlertOut]:
    return await service.alerts(case_id, actor)


@router.post(
    "/{case_id}/tasks",
    status_code=201,
    response_model=TaskOut,
    summary="Create a single (ad-hoc) task",
    description="Coordinator only (403 otherwise). A closed case (`uzavreno`) takes no new tasks: 409 `conflict`.",
    responses=problem_responses(403, 404, 409, 422, 500, 502, 503),
)
async def create_task(
    request: CreateTaskRequest, service: CoordinationDep, actor: ActorDep, case_id: str = CaseId
) -> TaskOut:
    return await service.create_task(case_id, request, actor)
