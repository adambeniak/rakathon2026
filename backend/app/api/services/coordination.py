"""Care-pathway coordination: launch a pathway, move tasks along, board and alerts.

Routes stay thin; this is the only place that combines the case reader, the task state machine and the TaskStore.
`now` always comes from the (demo-aware) settings clock and is passed to the domain explicitly.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
from datetime import date, datetime, time

import structlog

from app.api.schemas.coordination import (
    AlertOut,
    BatonHolderOut,
    Board,
    BoardLane,
    CreateTaskRequest,
    LaunchPathwayRequest,
    PathwayLaunched,
    TaskOut,
    TaskOwner,
    TransitionRequest,
)
from app.domain import board as board_logic
from app.domain import clock
from app.domain.common import PartyRef, Role
from app.domain.errors import ConflictError, ForbiddenError, InvalidInputError
from app.domain.events import EventKind, TransitionError
from app.domain.pathway import instantiate
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.domain.task_machine import TaskContext, transition
from app.fhir.cases import CaseHeader, CaseReader
from app.fhir.directory import DirectoryProvider
from app.fhir.mappers.plan_definition import plan_definition_to_template
from app.fhir.tasks import PractitionerRoleRef, StoredTask, TaskStore
from app.fhir.workflow import authorize_case

log = structlog.get_logger(__name__)

AD_HOC_CODE = "ad-hoc"


def end_of_day(day: date) -> datetime:
    """Deadlines are stored as 23:59:59 Prague, like the pathway templates do."""
    return datetime.combine(day, time(23, 59, 59), tzinfo=clock.TZ)


def _aware(value: date | datetime) -> datetime:
    """A bare date means the start of that day in Prague; a naive date-time is read as Prague time."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=clock.TZ)
    return datetime.combine(value, time(0, 0), tzinfo=clock.TZ)


def _owner_out(owner: PartyRef | None) -> TaskOwner | None:
    return TaskOwner(id=owner.id, display=owner.display, role=owner.role) if owner else None


def task_out(item: board_logic.BoardTask) -> TaskOut:
    t = item.task
    return TaskOut(
        id=t.id,
        case_id=t.case_id,
        code=t.code,
        title=t.title,
        status=t.status,
        business_status=t.business_status,
        lane=item.lane,
        owner=_owner_out(t.owner),
        owner_role=t.owner_role,
        place=t.location,
        due=t.due,
        sla_due=t.sla_due,
        scheduled_at=t.scheduled_at,
        depends_on=list(t.depends_on),
        blocked_by=list(item.blocked_by),
        overdue=item.overdue,
        overdue_workdays=item.overdue_workdays,
        escalated_at=t.escalated_at,
        result_doc_id=t.result_doc_id,
        note=t.note,
        ad_hoc=t.ad_hoc,
        required_for_mdt=item.critical,
        demo_assumption=t.demo_assumption,
        recorded_on_behalf_by=_owner_out(t.recorded_on_behalf_by),
    )


def baton_out(baton: board_logic.BatonHolder | None) -> BatonHolderOut | None:
    if baton is None:
        return None
    return BatonHolderOut(
        role=baton.role,
        owner=_owner_out(baton.owner),
        task_id=baton.task_id,
        task_title=baton.task_title,
        due=baton.due,
        basis=baton.basis,
        reason=baton.reason,
        demo_assumption=baton.demo_assumption,
    )


def board_out(board: board_logic.Board) -> Board:
    return Board(
        case_id=board.case_id,
        computed_at=board.as_of,
        lanes=[BoardLane(role=lane.role, tasks=[task_out(bt) for bt in lane.tasks]) for lane in board.lanes],
        baton_holder=baton_out(board.baton_holder),
    )


def alert_out(alert: board_logic.Alert) -> AlertOut:
    return AlertOut(
        task_id=alert.task_id,
        case_id=alert.case_id,
        code=alert.code,
        title=alert.title,
        kind=alert.kind,
        deadline=alert.deadline,
        basis="sla" if alert.basis == "sla" else "due",
        overdue_workdays=alert.overdue_workdays,
        escalated_at=alert.escalated_at,
        recipients=list(alert.recipients),
        demo_assumption=alert.demo_assumption,
    )


MAX_TASKS_PER_CASE = 200
MSG_INDICATION_REQUIRED = "Sada vyšetření vyžaduje indikujícího lékaře KOC."
MSG_INDICATION_UNKNOWN = "Zadaný indikující lékař neexistuje."
MSG_MDT_START_REQUIRED = "Pro spuštění sady je nutné zadat termín MDT."
MSG_INDICATION_NOT_PHYSICIAN = "Indikujícím lékařem může být jen lékař KOC (role koc_physician)."


def _require_coordinator(actor: PartyRef, what: str) -> None:
    if actor.role is not Role.COORDINATOR:
        raise ForbiddenError(f"only the coordinator may {what}")


def transition_steps(event: str, task: Task) -> list[str]:
    """Machine events behind an API verb, skipping the ones that already happened (so every state is reachable)."""
    business = task.business_status or TaskBusinessStatus.OBJEDNANO
    if event == "confirm":
        if task.status is not TaskStatus.REQUESTED:
            return []
        return (["order_confirmed"] if business is TaskBusinessStatus.OBJEDNANO else []) + ["accept"]
    if event == "perform":
        return (["start"] if task.status is TaskStatus.ACCEPTED else []) + ["performed"]
    if event == "deliver_result":
        return ["result_delivered"]
    return [event]  # fail | cancel


class CoordinationService:
    def __init__(
        self, reader: CaseReader, store: TaskStore, now: Callable[[], datetime], directory: DirectoryProvider
    ) -> None:
        self._reader = reader
        self._store = store
        self._now = now
        self._directory = directory

    async def _header(self, case_id: str, actor: PartyRef) -> CaseHeader:
        """The case, if the actor takes part in it (referring GP, or staff of the managing KOC): else 403."""
        loaded = await self._reader.load(case_id)
        authorize_case(loaded, actor, await self._directory.get())
        return CaseHeader(
            case=loaded.case,
            task_reference=f"Task/{loaded.task['id']}",
            patient_reference=str(loaded.task["for"]["reference"]),
        )

    # --- reads ---

    async def board(self, case_id: str, actor: PartyRef) -> Board:
        header = await self._header(case_id, actor)
        stored = await self._store.list_for_case(header.task_reference)
        return board_out(board_logic.build_board(case_id, [s.task for s in stored], self._now()))

    async def alerts(self, case_id: str, actor: PartyRef) -> list[AlertOut]:
        header = await self._header(case_id, actor)
        stored = await self._store.list_for_case(header.task_reference)
        return [alert_out(a) for a in board_logic.collect_alerts([s.task for s in stored], self._now())]

    # --- pathway ---

    async def launch_pathway(self, case_id: str, request: LaunchPathwayRequest, actor: PartyRef) -> PathwayLaunched:
        _require_coordinator(actor, "launch a pathway")
        if not (request.indicated_by and request.indicated_by.strip()):
            raise InvalidInputError(MSG_INDICATION_REQUIRED)
        entry = (await self._directory.get()).role(request.indicated_by.strip())
        if entry is None:
            raise InvalidInputError(MSG_INDICATION_UNKNOWN)
        if entry.role.role is not Role.KOC_PHYSICIAN:
            raise InvalidInputError(MSG_INDICATION_NOT_PHYSICIAN)
        physician = PractitionerRoleRef(entry.ref, entry.role.id, entry.display, entry.role.role)
        header = await self._header(case_id, actor)
        plan = await self._store.get_plan_definition(request.plan_url)
        mdt_start = request.mdt_start or header.case.mdt_start
        if mdt_start is None:
            raise InvalidInputError(MSG_MDT_START_REQUIRED)
        if await self._store.care_plan_exists(case_id, plan):
            raise ConflictError("this pathway has already been launched for the case")
        try:
            template = plan_definition_to_template(plan)
            tasks = instantiate(template, header.case.model_copy(update={"mdt_start": mdt_start}), request.start_date)
        except ValueError as exc:
            raise InvalidInputError(f"pathway template cannot be used: {exc}") from exc
        await self._store.launch_pathway(
            header,
            plan,
            tasks,
            request.start_date,
            indication=physician,
            coordinator=actor,
            recorded=self._now(),
            mdt_start=mdt_start if mdt_start != header.case.mdt_start else None,  # persisted in the same transaction
        )
        tasks.sort(key=board_logic.due_order)
        board = board_logic.build_board(case_id, tasks, self._now())
        by_id = {bt.task.id: bt for lane in board.lanes for bt in lane.tasks}
        return PathwayLaunched(
            plan_url=request.plan_url,
            start_date=request.start_date,
            indicated_by=TaskOwner(id=physician.business_id, display=physician.display, role=Role.KOC_PHYSICIAN),
            tasks=[task_out(by_id[t.id]) for t in tasks],
            baton_holder=baton_out(board.baton_holder),
        )

    # --- single tasks ---

    async def create_task(self, case_id: str, request: CreateTaskRequest, actor: PartyRef) -> TaskOut:
        _require_coordinator(actor, "create tasks")
        header = await self._header(case_id, actor)
        existing = await self._store.list_for_case(header.task_reference)
        if len(existing) >= MAX_TASKS_PER_CASE:
            raise InvalidInputError(f"a case may have at most {MAX_TASKS_PER_CASE} tasks")
        unknown = sorted(set(request.depends_on) - {s.task.id for s in existing})
        if unknown:
            raise InvalidInputError(f"unknown dependencies: {', '.join(unknown)}")
        due = request.due
        task = Task(
            id=f"{case_id}.adhoc-{secrets.token_hex(4)}",
            case_id=case_id,
            code=AD_HOC_CODE,
            title=request.title.strip(),
            status=TaskStatus.REQUESTED,
            business_status=TaskBusinessStatus.OBJEDNANO,
            owner_role=request.owner_role,
            due=(due if isinstance(due, datetime) else end_of_day(due)) if due else None,
            location=request.place,
            depends_on=list(request.depends_on),
            note=request.note,
            ad_hoc=True,
        )
        await self._store.create(header, task)
        return self._view([*(s.task for s in existing), task], task.id)

    # --- transitions ---

    async def transition(self, task_id: str, request: TransitionRequest, actor: PartyRef) -> TaskOut:
        if actor.role is Role.SYSTEM:
            raise ForbiddenError("tasks cannot be moved without an identified user (authentication is not configured)")
        stored = await self._store.get(task_id)
        await self._header(stored.task.case_id, actor)  # membership: only a participant of the case moves its tasks
        now = self._now()
        task = stored.task
        steps = transition_steps(request.event, task)
        if not steps:
            raise TransitionError(
                "invalid_transition", f"{request.event!r} is not possible in status {task.status.value!r}"
            )
        siblings = [s.task for s in await self._store.list_for_case(_case_task_reference(stored))]
        ctx = await self._context(stored, request, steps, siblings)
        on_behalf = False
        for step in steps:
            result = transition(task, step, actor.role, ctx, now)
            task, on_behalf = result.task, on_behalf or result.on_behalf
            for event in result.events:
                if event.kind is EventKind.NOTIFICATION:
                    # No delivery channel yet (app.notify is a stub): record it in the log, never lose it silently.
                    log.info("notification_pending", template=event.action, task_id=task.id)
        if on_behalf and "performed" in steps and not (request.note and request.note.strip()):
            raise InvalidInputError(
                "note with the source of the information is required when recording for a workplace"
            )
        updates: dict[str, object] = {}
        if request.note and request.note.strip():
            updates["note"] = request.note.strip()  # the reason / source stays on the task, not in the audit text
        if on_behalf:
            updates["recorded_on_behalf_by"] = actor
        task = task.model_copy(update=updates)
        reason = request.note if request.event in {"fail", "cancel"} else None
        await self._store.save(
            stored,
            task,
            description=_describe(stored.task, task, steps, reason, on_behalf),
            on_behalf_of=(task.owner.display if task.owner else task.location or "externí pracoviště")
            if on_behalf
            else None,
        )
        return self._view([task if t.id == task.id else t for t in siblings], task.id)

    async def _context(
        self, stored: StoredTask, request: TransitionRequest, steps: Sequence[str], siblings: Sequence[Task]
    ) -> TaskContext:
        scheduled_at = None
        if "order_confirmed" in steps:
            if request.date is None:
                raise InvalidInputError("date is required to confirm an order")
            scheduled_at = _aware(request.date)
        if request.document_id:
            received = await self._store.patient_document_received_at(
                str(stored.resource["for"]["reference"]), request.document_id
            )
            if received is None:
                raise InvalidInputError(f"document {request.document_id!r} does not exist for this patient")
            if received > self._now():
                raise InvalidInputError(f"document {request.document_id!r} was received after the current time")
        return TaskContext(
            place=request.place,
            scheduled_at=scheduled_at,
            result_doc_id=request.document_id,
            reason=request.note,
            completed_task_ids=frozenset(t.id for t in siblings if t.status is TaskStatus.COMPLETED),
        )

    def _view(self, tasks: Sequence[Task], task_id: str) -> TaskOut:
        ordered = sorted(tasks, key=board_logic.due_order)
        board = board_logic.build_board(ordered[0].case_id, ordered, self._now())
        return next(task_out(bt) for lane in board.lanes for bt in lane.tasks if bt.task.id == task_id)


def _case_task_reference(stored: StoredTask) -> str:
    return str(stored.resource["partOf"][0]["reference"])


def _describe(before: Task, after: Task, steps: Sequence[str], reason: str | None, on_behalf: bool) -> str:
    """Audit text: ids and states only. A fail / cancel reason is free text and stays on the Task (`note`)."""
    text = (
        f"task {after.id}: {' + '.join(steps)}; "
        f"{before.status.value}/{(before.business_status or TaskBusinessStatus.OBJEDNANO).value} -> "
        f"{after.status.value}/{(after.business_status or TaskBusinessStatus.OBJEDNANO).value}"
    )
    if on_behalf:
        text += "; recorded by the coordinator on behalf of the external workplace"
    return f"{text}; reason recorded on the task" if reason and reason.strip() else text
