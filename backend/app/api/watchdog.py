"""SLA watchdog: complete steps whose result report has arrived, and escalate overdue tasks once.

`run_once` is the whole logic (testable without a loop): every open step past its earlier deadline (`due` or the
promised `sla_due`) gets `escalated_at` stamped, which makes the escalation fire exactly once. GET /alerts computes
overdue tasks at read time, so the watchdog only persists and audits the escalation. There is no delivery channel yet
(`app.notify` is a stub); the escalation is visible in alerts and on the board. Before escalating, a step whose result
report was received by `now` is completed (`app.domain.task_results`), so a delivered result is never escalated; this
also catches up when the demo clock moves past a report uploaded earlier.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

import httpx
import structlog

from app.api.services.coordination import deliver_received_results
from app.domain.common import PartyRef, Role
from app.domain.task_machine import escalate_if_overdue
from app.domain.task_results import result_type
from app.fhir.client import FhirClient
from app.fhir.directory import DirectoryProvider
from app.fhir.repository import FhirRepository
from app.fhir.systems import DEMO_TAG_CODE
from app.fhir.tasks import StoredTask, TaskStore
from app.notify.mailer import SmtpMailer
from app.notify.patient_sms import PatientSmsNotifier
from app.notify.sms import MailpitSmsGateway
from app.settings import Settings

log = structlog.get_logger(__name__)

WATCHDOG_ACTOR = PartyRef(id="sla-watchdog", display="Štafeta – hlídání termínů", role=Role.SYSTEM)


async def run_once(store: TaskStore, now: datetime, *, reminders: PatientSmsNotifier | None = None) -> list[str]:
    """Complete steps whose result report has arrived, then escalate every overdue open task that was not escalated
    yet, then send the day-before SMS reminders (`reminders`, demo mode); returns the escalated task ids."""
    open_tasks = await store.list_open_everywhere()
    delivered = await _deliver_results(store, open_tasks, now)
    escalated: list[str] = []
    for stored in open_tasks:
        if stored.task.id in delivered:
            continue
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
    if reminders is not None:
        await reminders.remind_upcoming((s for s in open_tasks if s.task.id not in delivered), now)
    return escalated


async def _deliver_results(store: TaskStore, open_tasks: list[StoredTask], now: datetime) -> set[str]:
    """Steps completed because their result report was received by `now` (#132); one case at a time."""
    cases = sorted({str(s.resource["partOf"][0]["reference"]) for s in open_tasks if result_type(s.task)})
    delivered: set[str] = set()
    for case_task_reference in cases:
        try:
            steps = await store.list_for_case(case_task_reference, audit=False)
            done = await deliver_received_results(store, steps, now, audit=False)
        except Exception:
            log.exception("results_not_delivered", case_task=case_task_reference)
            continue
        delivered |= {task_id for task_id, _events in done}
    return delivered


async def watchdog_loop(settings: Settings, http: httpx.AsyncClient, clock_now: Callable[[], datetime]) -> None:
    """Runs until cancelled; IRIS being down or any error only skips that round."""
    client = FhirClient(http, settings.fhir_base_url, settings.iris_user, settings.iris_password)
    repository = FhirRepository(client, WATCHDOG_ACTOR, tag_code=DEMO_TAG_CODE if settings.stafeta_demo_mode else None)
    store = TaskStore(repository)
    reminders = (
        PatientSmsNotifier(
            repository, MailpitSmsGateway(SmtpMailer(settings.smtp_host, settings.smtp_port)), DirectoryProvider(client)
        )
        if settings.stafeta_demo_mode
        else None
    )
    while True:
        try:
            await run_once(store, clock_now(), reminders=reminders)
        except Exception:
            log.exception("watchdog_round_failed")
        await asyncio.sleep(settings.stafeta_watchdog_interval_s)


def start_watchdog(settings: Settings, http: httpx.AsyncClient) -> asyncio.Task[None]:
    return asyncio.create_task(watchdog_loop(settings, http, settings.now), name="sla-watchdog")
