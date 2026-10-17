"""GET/PUT /api/demo/clock: the one demo clock that deadlines, the board and the watchdog read.

Served only with `STAFETA_DEMO_MODE=1`; otherwise every route answers 404 (before authentication, so the endpoint
is not discoverable). Who moves the clock is recorded as an AuditEvent without a patient.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import ActorDep, CoordinationDep, RepositoryDep, SettingsDep
from app.api.schemas.common import problem_responses
from app.api.schemas.demo import DemoAdvanced, DemoClock, SetDemoClock, parse_target
from app.domain import clock
from app.domain.common import BUSINESS_ID_PATTERN
from app.domain.errors import NotFoundError
from app.domain.events import DomainEvent, EventKind
from app.fhir.audit import build_domain_audit_event


def require_demo_mode(settings: SettingsDep) -> None:
    if not settings.stafeta_demo_mode:
        raise NotFoundError("route", "demo")


router = APIRouter(
    prefix="/demo",
    tags=["demo"],
    dependencies=[Depends(require_demo_mode)],
)

DEMO_CLOCK_EVENT = "demo-clock"
ADVANCE_EVENT = "demo-advance"


def _view(settings: SettingsDep) -> DemoClock:
    return DemoClock(now=settings.now(), overridden=clock.is_overridden())


@router.get(
    "/clock",
    response_model=DemoClock,
    summary="Demo clock (demo mode only)",
    responses=problem_responses(401, 404),
)
async def get_clock(settings: SettingsDep, _actor: ActorDep) -> DemoClock:
    return _view(settings)


@router.put(
    "/clock",
    response_model=DemoClock,
    summary="Move or reset the demo clock (demo mode only)",
    description="Every deadline, escalation and the board use this clock. `now: null` resets it.",
    responses=problem_responses(401, 404, 422, 502, 503),
)
async def put_clock(body: SetDemoClock, settings: SettingsDep, actor: ActorDep, repository: RepositoryDep) -> DemoClock:
    # Audit first: if it cannot be stored, the clock does not move.
    event = DomainEvent(kind=EventKind.AUDIT, action="update", at=settings.now(), payload={"event": DEMO_CLOCK_EVENT})
    audit = build_domain_audit_event(event, actor=actor, entities=[])
    audit["outcomeDesc"] = f"demo clock set to {body.now.isoformat()}" if body.now else "demo clock reset"
    await repository.create(audit)
    clock.set_override(body.now)
    return _view(settings)


@router.post(
    "/advance",
    response_model=DemoAdvanced,
    summary="Move the demo clock and replay the story steps up to it (demo mode only)",
    description="Brings CT, EUS-FNB, labs (and histology's order) of the case to where the story had them at `to`, "
    "through the task state machine, then moves the clock and runs one watchdog round. At 2026-10-16 only the "
    "histology is overdue. Idempotent. Coordinator only; the result documents must be uploaded for the patient.",
    responses=problem_responses(401, 403, 404, 409, 422, 502, 503),
)
async def advance(
    settings: SettingsDep,
    actor: ActorDep,
    repository: RepositoryDep,
    service: CoordinationDep,
    case_id: str = Query(pattern=BUSINESS_ID_PATTERN, max_length=100, description="The demo case."),
    to: str = Query(
        max_length=40,
        examples=["2026-10-16"],
        description="YYYY-MM-DD (09:00 Prague) or an ISO 8601 timestamp; years 2020–2035.",
    ),
) -> DemoAdvanced:
    target = parse_target(to)
    applied, skipped = await service.replay_story(case_id, target, actor)  # refused before the clock moves
    event = DomainEvent(kind=EventKind.AUDIT, action="update", at=settings.now(), payload={"event": ADVANCE_EVENT})
    audit = build_domain_audit_event(event, actor=actor, entities=[])
    audit["outcomeDesc"] = f"demo advanced to {target.isoformat()} for case {case_id}: {len(applied)} step(s) replayed"
    await repository.create(audit)
    clock.set_override(target)
    escalated = await service.escalate_overdue(case_id, target, actor)
    return DemoAdvanced(now=settings.now(), overridden=True, applied=applied, skipped=skipped, escalated=escalated)
