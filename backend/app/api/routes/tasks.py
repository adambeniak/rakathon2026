"""Move a single task along its lifecycle (the task state machine enforces order, roles and guards)."""

from __future__ import annotations

from fastapi import APIRouter, Path

from app.api.deps import ActorDep, CoordinationDep
from app.api.schemas.common import problem_responses
from app.api.schemas.coordination import TaskOut, TransitionRequest
from app.domain.common import BUSINESS_ID_PATTERN

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "/{task_id}/transitions",
    response_model=TaskOut,
    summary="Confirm, perform, deliver the result of, fail or cancel a task",
    description=(
        "Roles are checked by the task state machine. For a task owned by an external workplace the coordinator "
        "may record perform / deliver_result on its behalf; the audit trail says so."
    ),
    responses=problem_responses(403, 404, 409, 422, 500, 502, 503),
)
async def transition_task(
    request: TransitionRequest,
    service: CoordinationDep,
    actor: ActorDep,
    task_id: str = Path(pattern=BUSINESS_ID_PATTERN, max_length=200, examples=["rakathon-2026-prochazkova.ct"]),
) -> TaskOut:
    return await service.transition(task_id, request, actor)
