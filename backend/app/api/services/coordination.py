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
from app.api.schemas.demo import AdvancedStep, SkippedStep
from app.api.services.demo_story import STORY, StoryStep
from app.domain import board as board_logic
from app.domain import clock
from app.domain.case import CaseState
from app.domain.common import PartyRef, Role
from app.domain.document import SourceDocument
from app.domain.errors import ConflictError, ForbiddenError, InvalidInputError
from app.domain.events import EventKind, TransitionError
from app.domain.pathway import instantiate
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.domain.task_machine import ON_BEHALF_EVENTS, TaskContext, escalate_if_overdue, transition
from app.domain.task_results import deliver_result, matching_result, result_type
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
DEMO_REPLAY_NOTE = "Demo: přehráno ze scénáře."
MSG_NO_PATHWAY = "Sada vyšetření není pro případ spuštěná."
MSG_MDT_START_REQUIRED = "Pro spuštění sady je nutné zadat termín MDT."
MSG_INDICATION_NOT_PHYSICIAN = "Indikujícím lékařem může být jen lékař KOC (role koc_physician)."


MSG_CASE_CLOSED = "Případ je uzavřen: úkoly a kroky už nelze zakládat ani měnit."


def _require_coordinator(actor: PartyRef, what: str) -> None:
    if actor.role is not Role.COORDINATOR:
        raise ForbiddenError(f"Tuto akci smí provést jen koordinátorka: {what}")


def _refuse_if_closed(header: CaseHeader) -> None:
    """A closed case leaves nobody on the move (#133): no new task, pathway or step change after `uzavreno` (#166).
    Checked after the role check, so a role denial stays 403."""
    if header.case.state is CaseState.UZAVRENO:
        raise ConflictError(MSG_CASE_CLOSED)


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


OWNER_EVENTS = frozenset({"confirm", "perform", "deliver_result"})


def with_indicating_owner(tasks: Sequence[Task], physician: PractitionerRoleRef) -> list[Task]:
    """Steps of KOC physicians start with the indicating physician as their named owner (#137); a physician who later
    acts on the step takes it over. Steps of other roles (external workplace, coordinator) stay without a named owner
    (the UI says "nepřiřazeno"): the coordinator records them on behalf and is not their owner."""
    owner = PartyRef(id=physician.business_id, display=physician.display, role=Role.KOC_PHYSICIAN)
    return [t.model_copy(update={"owner": owner}) if t.owner_role is Role.KOC_PHYSICIAN else t for t in tasks]


def claims_ownership(task: Task, event: str, actor: PartyRef, on_behalf: bool) -> bool:
    """Whether `actor` becomes the named owner: they moved the step forward in the step's own role (not on behalf, so
    the owner role and the board lane never change)."""
    role = task.owner.role if task.owner else task.owner_role
    return event in OWNER_EVENTS and not on_behalf and actor.role is role and task.owner != actor


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
        _require_coordinator(actor, "spustit sadu vyšetření")
        if not (request.indicated_by and request.indicated_by.strip()):
            raise InvalidInputError(MSG_INDICATION_REQUIRED)
        entry = (await self._directory.get()).role(request.indicated_by.strip())
        if entry is None:
            raise InvalidInputError(MSG_INDICATION_UNKNOWN)
        if entry.role.role is not Role.KOC_PHYSICIAN:
            raise InvalidInputError(MSG_INDICATION_NOT_PHYSICIAN)
        physician = PractitionerRoleRef(entry.ref, entry.role.id, entry.display, entry.role.role)
        header = await self._header(case_id, actor)
        _refuse_if_closed(header)
        plan = await self._store.get_plan_definition(request.plan_url)
        mdt_start = request.mdt_start or header.case.mdt_start
        if mdt_start is None:
            raise InvalidInputError(MSG_MDT_START_REQUIRED)
        if await self._store.care_plan_exists(case_id, plan):
            raise ConflictError("Tato sada vyšetření už byla pro případ spuštěna")
        try:
            template = plan_definition_to_template(plan)
            tasks = instantiate(template, header.case.model_copy(update={"mdt_start": mdt_start}), request.start_date)
        except ValueError as exc:
            log.warning("pathway_template_unusable", reason=str(exc))  # the technical reason stays in the log
            raise InvalidInputError("Šablonu sady vyšetření nelze použít") from exc
        tasks = with_indicating_owner(tasks, physician)
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

    # --- demo story ---

    async def replay_story(
        self, case_id: str, to: datetime, actor: PartyRef
    ) -> tuple[list[AdvancedStep], list[SkippedStep]]:
        """Bring the story steps of the demo case to where they were at `to`, through the task state machine.

        Idempotent: only events that are due at `to` and not yet applied are applied (a repeat saves nothing).
        The machine's rules hold: the coordinator confirms and accepts the order and records start / performed /
        result for an external workplace (its on-behalf path). A step owned by a KOC physician cannot be recorded by
        the coordinator, so the owner's role is used there. Either way the Task says it was recorded on behalf by the
        real actor (`recorded_on_behalf_by`, the AuditEvent agent) with a "demo replay" note. A result document must
        exist for the patient; its receipt time is not compared with `to` (documents may have been uploaded live in an
        earlier demo step, the replay simulates history).
        """
        if actor.role is not Role.COORDINATOR:
            raise ForbiddenError("Demo smí posouvat jen koordinátorka")
        header = await self._header(case_id, actor)
        stored = {s.task.id: s for s in await self._store.list_for_case(header.task_reference)}
        if not any(f"{case_id}.{step.step}" in stored for step in STORY):
            raise InvalidInputError(MSG_NO_PATHWAY)
        completed = {t_id for t_id, s in stored.items() if s.task.status is TaskStatus.COMPLETED}
        applied: list[AdvancedStep] = []
        skipped: list[SkippedStep] = []
        for step in STORY:
            current = stored.get(f"{case_id}.{step.step}")
            if current is None:
                continue
            task, events, problem = await self._replay_step(current, step, to, frozenset(completed))
            if events:
                recorded_for_owner = bool(set(events) & ON_BEHALF_EVENTS)
                if recorded_for_owner:
                    task = task.model_copy(update={"recorded_on_behalf_by": actor, "note": DEMO_REPLAY_NOTE})
                await self._store.save(
                    current,
                    task,
                    description=f"{_describe(current.task, task, events, None, recorded_for_owner)}; demo replay",
                    on_behalf_of=(task.owner.display if task.owner else task.location or "externí pracoviště")
                    if recorded_for_owner
                    else None,
                )
                applied.append(AdvancedStep(task_id=task.id, events=events))
            if problem:
                skipped.append(SkippedStep(task_id=task.id, reason=problem))
            if task.status is TaskStatus.COMPLETED:
                completed.add(task.id)
        return applied, skipped

    async def _replay_step(
        self, stored: StoredTask, step: StoryStep, to: datetime, completed: frozenset[str]
    ) -> tuple[Task, list[str], str | None]:
        task = stored.task
        owner = task.owner.role if task.owner else task.owner_role
        if owner is Role.EXTERNAL_WORKPLACE:
            owner = Role.COORDINATOR  # the machine's on-behalf path
        timeline = (
            ("order_confirmed", step.confirmed_at, Role.COORDINATOR),
            ("accept", step.confirmed_at, Role.COORDINATOR),
            ("start", step.examined_at, owner),
            ("performed", step.examined_at, owner),
            ("result_delivered", step.result_at, owner),
        )
        events: list[str] = []
        for event, at, role in timeline:
            if at > to or role is None or not _due_in_story(task, event):
                continue
            if event == "result_delivered":
                received = await self._store.patient_document_received_at(
                    str(stored.resource["for"]["reference"]), step.result_doc_id
                )
                if received is None:
                    return task, events, f"Dokument {step.result_doc_id} není u pacienta nahrán."
            ctx = TaskContext(
                place=task.location,
                scheduled_at=step.scheduled_at,
                result_doc_id=step.result_doc_id,
                completed_task_ids=completed,
            )
            try:
                task = transition(task, event, role, ctx, at).task
            except TransitionError as exc:  # e.g. an earlier step is not finished: report it, keep what was applied
                return task, events, f"Krok {event} nelze provést: {exc.detail}"
            events.append(event)
        return task, events, None

    async def escalate_overdue(self, case_id: str, now: datetime, actor: PartyRef) -> list[str]:
        """The watchdog's rule for this case only, at `now` (the demo clock was just moved). A failed save is logged and
        left to the background watchdog: the clock has already moved, so the call must not fail after the fact."""
        header = await self._header(case_id, actor)
        if header.case.state is CaseState.UZAVRENO:
            return []  # a closed case is not escalated (#166)
        escalated: list[str] = []
        for stored in await self._store.list_for_case(header.task_reference):
            result = escalate_if_overdue(stored.task, now)
            if not result.events:
                continue
            payload = result.events[0].payload
            try:
                await self._store.save(
                    stored,
                    result.task,
                    description=(
                        f"task {stored.task.id}: overdue escalation ({payload['basis']}, "
                        f"{payload['overdue_workdays']} working day(s) after {payload['deadline']}); demo advance"
                    ),
                )
            except Exception:
                log.exception("escalation_not_saved", task_id=stored.task.id)
                continue
            escalated.append(stored.task.id)
        return escalated

    async def deliver_received_results(self, case_id: str, actor: PartyRef) -> list[AdvancedStep]:
        """Complete the steps of this case whose result report is already in the case at the (demo) clock (#132)."""
        header = await self._header(case_id, actor)
        if header.case.state is CaseState.UZAVRENO:
            return []  # nothing moves on a closed case (#166)
        stored = await self._store.list_for_case(header.task_reference)
        delivered = await deliver_received_results(self._store, stored, self._now())
        return [AdvancedStep(task_id=task_id, events=events) for task_id, events in delivered]

    # --- single tasks ---

    async def create_task(self, case_id: str, request: CreateTaskRequest, actor: PartyRef) -> TaskOut:
        _require_coordinator(actor, "zakládat úkoly")
        header = await self._header(case_id, actor)
        _refuse_if_closed(header)
        existing = await self._store.list_for_case(header.task_reference)
        if len(existing) >= MAX_TASKS_PER_CASE:
            raise InvalidInputError(f"Případ může mít nejvýše {MAX_TASKS_PER_CASE} úkolů")
        unknown = sorted(set(request.depends_on) - {s.task.id for s in existing})
        if unknown:
            raise InvalidInputError(f"Neznámé závislosti: {', '.join(unknown)}")
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
            raise ForbiddenError("Úkoly nelze posouvat bez identifikovaného uživatele (přihlášení není nastaveno)")
        stored = await self._store.get(task_id)
        header = await self._header(stored.task.case_id, actor)  # membership: only a participant moves its tasks
        now = self._now()
        task = stored.task
        steps = transition_steps(request.event, task)
        if not steps:
            raise TransitionError(
                "invalid_transition", f"Událost {request.event!r} není ve stavu {task.status.value!r} možná"
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
            raise InvalidInputError("Při zápisu za pracoviště je nutná poznámka se zdrojem informace")
        if request.event != "cancel":  # cancelling still clears a step left open on a closed case (data before #166)
            _refuse_if_closed(header)  # after the machine: its role denial (403) and state conflicts answer first
        updates: dict[str, object] = {}
        if claims_ownership(stored.task, request.event, actor, on_behalf):
            updates["owner"] = actor  # who acted on their own step holds it from now on (#137)
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
                raise InvalidInputError("K potvrzení objednání je nutné zadat datum")
            scheduled_at = _aware(request.date)
        if request.document_id:
            received = await self._store.patient_document_received_at(
                str(stored.resource["for"]["reference"]), request.document_id
            )
            if received is None:
                raise InvalidInputError(f"Dokument {request.document_id!r} pro tohoto pacienta neexistuje")
            if received > self._now():
                raise InvalidInputError(f"Dokument {request.document_id!r} byl přijat až po aktuálním čase")
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


async def deliver_received_results(
    store: TaskStore, stored: Sequence[StoredTask], now: datetime, *, audit: bool = True
) -> list[tuple[str, list[str]]]:
    """Walk every step of one case whose result report has been received to `vysledek_dorucen` (rules:
    `app.domain.task_results`). `stored` are all steps of the case, in due order (predecessors first). A step the
    machine refuses (e.g. its predecessors are open) or that cannot be saved is left as it is and tried again on the
    next call (upload, demo advance, watchdog round).
    Returns (task id, machine events) per completed step.
    """
    completed = {s.task.id for s in stored if s.task.status is TaskStatus.COMPLETED}
    documents: dict[tuple[str, str], list[SourceDocument]] = {}
    delivered: list[tuple[str, list[str]]] = []
    for current in stored:
        wanted = result_type(current.task)
        if wanted is None:
            continue
        key = (str(current.resource["for"]["reference"]), wanted)
        if key not in documents:
            documents[key] = await store.patient_result_documents(key[0], wanted, audit=audit)
        document = matching_result(current.task, documents[key], now)
        if document is None:
            continue
        try:
            task, events = deliver_result(current.task, document.doc_id, sorted(completed), now)
        except TransitionError as exc:
            log.info("result_not_delivered", task_id=current.task.id, doc_id=document.doc_id, reason=exc.code)
            continue
        try:
            await store.save(
                current,
                task,
                description=f"{_describe(current.task, task, events, None, False)}; "
                f"result document {document.doc_id} received, recorded by the system",
            )
        except Exception:  # like the escalation: logged, the next call (upload, advance, watchdog) tries again
            log.exception("result_step_not_saved", task_id=current.task.id)
            continue
        completed.add(task.id)
        delivered.append((task.id, events))
    return delivered


def _due_in_story(task: Task, event: str) -> bool:
    """Whether the story event is the next one for `task` (so a repeated replay applies nothing)."""
    business = task.business_status or TaskBusinessStatus.OBJEDNANO
    status = task.status
    if event == "order_confirmed":
        return status is TaskStatus.REQUESTED and business is TaskBusinessStatus.OBJEDNANO
    if event == "accept":
        return status is TaskStatus.REQUESTED and business is TaskBusinessStatus.POTVRZENO
    if event == "start":
        return status is TaskStatus.ACCEPTED
    if event == "performed":
        return status is TaskStatus.IN_PROGRESS and business is TaskBusinessStatus.POTVRZENO
    return status is TaskStatus.IN_PROGRESS and business is TaskBusinessStatus.PROVEDENO  # result_delivered


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
