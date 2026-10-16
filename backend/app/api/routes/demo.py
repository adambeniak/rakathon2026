"""GET/PUT /api/demo/clock: the one demo clock that deadlines, the board and the watchdog read.

Served only with `STAFETA_DEMO_MODE=1`; otherwise every route answers 404 (before authentication, so the endpoint
is not discoverable). Who moves the clock is recorded as an AuditEvent without a patient.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import ActorDep, RepositoryDep, SettingsDep
from app.api.schemas.common import problem_responses
from app.api.schemas.demo import DemoClock, SetDemoClock
from app.domain import clock
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
