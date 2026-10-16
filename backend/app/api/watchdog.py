"""SLA watchdog: escalate overdue tasks once.

`run_once` is the whole logic (testable without a loop): every open step past its earlier deadline (`due` or the
promised `sla_due`) gets `escalated_at` stamped, which makes the escalation fire exactly once. GET /alerts computes
overdue tasks at read time, so the watchdog only persists and audits the escalation. There is no delivery channel yet
(`app.notify` is a stub); the escalation is visible in alerts and on the board.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

import httpx
import structlog

from app.domain.common import PartyRef, Role
from app.domain.task_machine import escalate_if_overdue
from app.fhir.client import FhirClient
from app.fhir.repository import FhirRepository
from app.fhir.systems import DEMO_TAG_CODE
from app.fhir.tasks import TaskStore
from app.settings import Settings

log = structlog.get_logger(__name__)

WATCHDOG_ACTOR = PartyRef(id="sla-watchdog", display="Štafeta – hlídání termínů", role=Role.SYSTEM)


async def run_once(store: TaskStore, now: datetime) -> list[str]:
    """Escalate every overdue open task that was not escalated yet; returns the escalated task ids."""
    escalated: list[str] = []
    for stored in await store.list_open_everywhere():
        result = escalate_if_overdue(stored.task, now)
        if not result.events:
            continue
        event = result.events[0]
        try:
            await store.save(
                stored,
                result.task,
                description=(
                    f"task {stored.task.id}: overdue escalation ({event.payload['basis']}, "
                    f"{event.payload['overdue_workdays']} working day(s) after {event.payload['deadline']})"
                ),
            )
        except Exception:
            log.exception("escalation_not_saved", task_id=stored.task.id)
            continue
        escalated.append(stored.task.id)
        log.info("task_escalated", task_id=stored.task.id, basis=event.payload["basis"])
    return escalated


async def watchdog_loop(settings: Settings, http: httpx.AsyncClient, clock_now: Callable[[], datetime]) -> None:
    """Runs until cancelled; IRIS being down or any error only skips that round."""
    client = FhirClient(http, settings.fhir_base_url, settings.iris_user, settings.iris_password)
    repository = FhirRepository(client, WATCHDOG_ACTOR, tag_code=DEMO_TAG_CODE if settings.stafeta_demo_mode else None)
    store = TaskStore(repository)
    while True:
        try:
            await run_once(store, clock_now())
        except Exception:
            log.exception("watchdog_round_failed")
        await asyncio.sleep(settings.stafeta_watchdog_interval_s)


def start_watchdog(settings: Settings, http: httpx.AsyncClient) -> asyncio.Task[None]:
    return asyncio.create_task(watchdog_loop(settings, http, settings.now), name="sla-watchdog")
