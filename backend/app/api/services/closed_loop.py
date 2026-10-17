"""Demo steps 5-6 as write operations that need more than a state change: MDT conclusion, GP feedback, closing.

`CaseWorkflow` stays the one entry point of `POST /cases/{id}/transitions`; this subclass intercepts the three events
that carry data or a side effect and delegates every other event to the base class.

- `record_mdt_conclusion`: ONE transaction = case Task PUT (If-Match) + business AuditEvent + the conclusion
  `Composition` + its sign-off `Provenance`. The case cannot be signed off without the text being stored, and the
  signer is always the acting physician. A second, idempotent write then completes the pathway's open MDT step
  (`app.domain.task_results.complete_mdt_step`, #149): the task machine walks it to `vysledek_dorucen` as the system
  actor with the conclusion as its result, guards included. That write never fails the sign-off: a refused guard or a
  failed save is logged, and `close` reconciles it.
- `send_feedback`: both machine events are checked in memory first (nothing is sent when a guard fails), then the
  e-mail goes to the referring GP through the `Mailer`; only after the relay accepted it ONE transaction writes the
  case Task (state `zpetna_vazba_odeslana`, delivery receipt), the AuditEvent of `send_feedback` (the coordinator),
  the AuditEvent of `delivery_confirmed` (the system actor, receipt = SMTP Message-ID) and the `Communication`.
  If SMTP fails the case stays in `zaver_mdt` and the coordinator can retry; the e-mail holds no clinical text.
  The receipt means "the relay accepted the message" (handed over for delivery), not that the GP got or read it;
  the GP opening the feedback is the separate `gp_opened` event. If the write fails AFTER a successful send, the
  mail is out but nothing is recorded: the Message-ID is logged and a retry would send a second mail (see PR risks).
- `close`: a closed case leaves nobody "on the move". Every still open step (pathway or ad-hoc) is cancelled with the
  reason "Případ uzavřen" and its order (ServiceRequest) revoked, in ONE transaction with the case Task: case state,
  step Tasks, orders and the AuditEvents (each step's on its own Task) commit or fail together. Completed and failed
  steps stay as they are. The MDT step, if still open (the second write of the sign-off failed), is completed with the
  signed conclusion in the same transaction instead of being cancelled; only if the machine refuses it is it cancelled.
  The board then shows the steps as cancelled, and alerts and the SLA watchdog, which only
  look at open steps, stop for the case (#133).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

import structlog

from app.domain import case_machine, task_machine
from app.domain.case import CaseState
from app.domain.common import PartyRef, Role
from app.domain.errors import ForbiddenError, InvalidInputError, NotFoundError
from app.domain.events import DomainEvent, EventKind, TransitionError
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.domain.task_machine import OPEN_STATUSES
from app.domain.task_results import complete_mdt_step, is_open_mdt_step
from app.fhir.audit import build_domain_audit_event
from app.fhir.bundles import BundleBuilder
from app.fhir.cases import CaseReader, LoadedCase
from app.fhir.client import Resource
from app.fhir.directory import Directory, RoleEntry
from app.fhir.mappers.feedback import feedback_communication_to_fhir
from app.fhir.mappers.mdt_conclusion import (
    TYPE_MDT_CONCLUSION,
    MdtConclusionRecord,
    conclusion_business_id,
    is_conclusion_of,
    latest_conclusion,
    mdt_conclusion_from_fhir,
    mdt_conclusion_provenance,
    mdt_conclusion_to_fhir,
)
from app.fhir.mappers.task import task_to_fhir
from app.fhir.readiness import WaiverRequest
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_COMPOSITION_TYPE
from app.fhir.tasks import StoredTask, TaskStore
from app.fhir.workflow import CaseWorkflow, TransitionOutcome, assign_holder, authorize_case, managing_koc_id
from app.notify.feedback_mail import FeedbackMailInput, build_feedback_mail
from app.notify.mailer import Mailer, new_message_id
from app.security.actor import SYSTEM_ACTOR

log = structlog.get_logger(__name__)

# The GP may read the conclusion only once the feedback has been sent to them.
GP_VISIBLE_STATES = frozenset({CaseState.ZPETNA_VAZBA_ODESLANA, CaseState.UZAVRENO})
# Status reason of the steps still open when the case is closed (workflow wording, no clinical content).
CLOSE_REASON = "Případ uzavřen"
# Confirmed place of an MDT step without one when the managing KOC is not in the directory (workflow wording).
MDT_PLACE_FALLBACK = "MDT KOC"


class ClosedLoopWorkflow(CaseWorkflow):
    def __init__(self, repository: FhirRepository, reader: CaseReader, mailer: Mailer, portal_url: str) -> None:
        super().__init__(repository, reader)
        self._mailer = mailer
        self._portal_url = portal_url

    async def transition(
        self,
        case_id: str,
        event: str,
        *,
        actor: PartyRef,
        directory: Directory,
        now: datetime,
        reason: str | None = None,
        resume_on: str | None = None,
        conclusion: str | None = None,
        receipt_id: str | None = None,
        waivers: Sequence[WaiverRequest] = (),
    ) -> TransitionOutcome:
        if event == "record_mdt_conclusion":
            return await self.record_conclusion(case_id, conclusion, actor=actor, directory=directory, now=now)
        if event == "send_feedback":
            return await self.send_feedback(case_id, actor=actor, directory=directory, now=now)
        if event == "close" and not waivers:  # waivers with close: the base class refuses them
            return await self.close(case_id, actor=actor, directory=directory, now=now)
        return await super().transition(
            case_id,
            event,
            actor=actor,
            directory=directory,
            now=now,
            reason=reason,
            resume_on=resume_on,
            conclusion=conclusion,
            receipt_id=receipt_id,
            waivers=waivers,
        )

    async def record_conclusion(
        self, case_id: str, conclusion: str | None, *, actor: PartyRef, directory: Directory, now: datetime
    ) -> TransitionOutcome:
        loaded = await self._reader.load(case_id)
        authorize_case(loaded, actor, directory)
        text = (conclusion or "").strip()
        # Sign-off is the acting clinician, never a client-supplied id; the machine checks the role and the guards.
        ctx = case_machine.CaseContext(conclusion=text, confirmed_by=actor.id)
        result = case_machine.transition(loaded.case, "record_mdt_conclusion", actor.role, ctx, now)
        new_case = assign_holder(result.case, actor, directory, loaded)

        builder = BundleBuilder()
        composition = builder.post(
            mdt_conclusion_to_fhir(
                case_id,
                text,
                patient_reference=_task_ref(loaded, "for"),
                episode_reference=_task_ref(loaded, "focus"),
                signer=actor,
                signed_at=now,
            )
        )
        builder.post(mdt_conclusion_provenance(target=composition, signer=actor, recorded=now))
        await self.save_case(loaded, new_case, result.events, actor=actor, directory=directory, bundle=builder)
        await self._complete_mdt_step(loaded, conclusion_business_id(case_id, now), directory=directory, now=now)
        return TransitionOutcome(new_case, result.events)

    async def _complete_mdt_step(
        self, loaded: LoadedCase, conclusion_id: str, *, directory: Directory, now: datetime
    ) -> None:
        """Second write after the sign-off (#149): the open MDT step of the pathway -> `vysledek_dorucen`.

        Idempotent: without a pathway, an open MDT step or with an already completed one nothing is written. Never
        raises: the conclusion is stored and signed. A refused guard (e.g. a predecessor is still open) or a failed save
        is logged; `close` completes the step later.
        """
        store = TaskStore(self._repo)
        step: StoredTask | None = None
        try:
            steps = await store.list_for_case(f"Task/{loaded.task['id']}")  # audited read
            step = next((s for s in steps if is_open_mdt_step(s.task)), None)
            if step is None:
                return
            task, events, _ = _completed_mdt_step(step, steps, conclusion_id, loaded, directory, now)
            await store.save(step, task, description=_mdt_description(step.task, task, events))
        except TransitionError as exc:
            log.info("mdt_step_not_completed", task_id=step.task.id if step else None, reason=exc.code)
        except Exception:
            log.exception("mdt_step_not_saved", task_id=step.task.id if step else None)

    async def get_conclusion(self, case_id: str, *, actor: PartyRef, directory: Directory) -> MdtConclusionRecord:
        loaded = await self._reader.load(case_id)  # audited read
        authorize_case(loaded, actor, directory)
        if actor.role is Role.GP and loaded.case.state not in GP_VISIBLE_STATES:
            raise ForbiddenError("Zpětná vazba ještě nebyla odeslána")
        latest = await self._latest_conclusion(loaded, case_id)
        if latest is None:
            raise NotFoundError("MDT conclusion", case_id)
        await self._repo.audit_read([f"Composition/{latest['id']}"])
        record = mdt_conclusion_from_fhir(latest)
        signer = directory.role(record.signer_id)  # the role comes from the directory, it is not assumed
        return replace(record, signer_role=signer.role.role if signer else None)

    async def _latest_conclusion(self, loaded: LoadedCase, case_id: str) -> Resource | None:
        found = await self._repo.search(
            "Composition",
            {
                "subject": _task_ref(loaded, "for"),
                "type": f"{CS_COMPOSITION_TYPE}|{TYPE_MDT_CONCLUSION}",
                "_count": "50",
            },
        )
        mine = [c for c in found if is_conclusion_of(c, case_id)]
        return latest_conclusion(mine) if mine else None

    async def send_feedback(
        self, case_id: str, *, actor: PartyRef, directory: Directory, now: datetime
    ) -> TransitionOutcome:
        loaded = await self._reader.load(case_id)
        authorize_case(loaded, actor, directory)
        gp = _referring_gp(loaded, directory)
        message_id = new_message_id()
        # Dry run of both machine events: a refused guard or role stops here, before anything is sent.
        sent = case_machine.transition(
            loaded.case,
            "send_feedback",
            actor.role,
            case_machine.CaseContext(gp_recipient=gp.role.id if gp else None),
            now,
        )
        delivered = case_machine.transition(
            sent.case, "delivery_confirmed", Role.SYSTEM, case_machine.CaseContext(receipt_id=message_id), now
        )
        if gp is None:  # unreachable: the send_feedback guard refuses a missing recipient
            raise InvalidInputError("Odesílající praktický lékař případu není znám")
        sender = directory.role(actor.id)
        koc = directory.org(managing_koc_id(loaded, directory) or "")
        if sender is None or koc is None:
            raise InvalidInputError("Odesílatel nebo vedoucí KOC není v adresáři")

        message = build_feedback_mail(
            FeedbackMailInput(
                recipient=gp.role,
                koc_name=koc.org.name,
                coordinator_display=actor.display,
                portal_url=self._portal_url,
                mdt_start=loaded.case.mdt_start,
            ),
            message_id=message_id,
        )
        # Everything that can fail on our side is built BEFORE the send, so a send is followed only by the write.
        conclusion = await self._latest_conclusion(loaded, case_id)  # metadata only: its text is not read here
        new_case = assign_holder(delivered.case, actor, directory, loaded)
        builder = BundleBuilder()
        builder.post(
            feedback_communication_to_fhir(
                case_id,
                patient_reference=_task_ref(loaded, "for"),
                episode_reference=_task_ref(loaded, "focus"),
                sender=actor,
                sender_reference=sender.ref,
                recipient_reference=gp.ref,
                sent_at=now,
                message_id=message_id,
                body=message.body,
                conclusion_reference=f"Composition/{conclusion['id']}" if conclusion else None,
            )
        )
        task_reference = f"Task/{loaded.task['id']}"
        for event in delivered.events:  # delivery is confirmed by the system, not by the coordinator who clicked
            if event.kind is EventKind.AUDIT:
                builder.post(build_domain_audit_event(event, actor=SYSTEM_ACTOR, entities=[task_reference]))

        await self._mailer.send(message)  # MailDeliveryError: nothing written, the coordinator may retry
        try:
            await self.save_case(loaded, new_case, sent.events, actor=actor, directory=directory, bundle=builder)
        except Exception:
            # The relay accepted the mail but the case was not updated (e.g. a concurrent write, IRIS down). Keep the
            # only trace there is: ids, no addresses or text.
            log.error("feedback_mail_sent_but_state_not_saved", message_id=message_id)
            raise
        return TransitionOutcome(new_case, (*sent.events, *delivered.events))

    async def close(self, case_id: str, *, actor: PartyRef, directory: Directory, now: datetime) -> TransitionOutcome:
        loaded = await self._reader.load(case_id)
        authorize_case(loaded, actor, directory)
        # The machine checks the role and the guard (delivery confirmed) before any step is read or changed.
        result = case_machine.transition(loaded.case, "close", actor.role, case_machine.CaseContext(), now)
        new_case = assign_holder(result.case, actor, directory, loaded)
        case_reference = f"Task/{loaded.task['id']}"
        builder = BundleBuilder()
        store = TaskStore(self._repo)
        steps = await store.list_for_case(case_reference)  # audited read
        has_open_mdt = any(is_open_mdt_step(s.task) for s in steps)
        conclusion_id = await self._conclusion_id(loaded, case_id) if has_open_mdt else None
        for stored in steps:
            if stored.task.status not in OPEN_STATUSES:
                continue
            task, events = _closed_step(stored, steps, conclusion_id, loaded, directory, actor, now)
            resource = task_to_fhir(
                task, case_task_reference=case_reference, patient_reference=str(stored.resource["for"]["reference"])
            )
            resource["id"] = stored.fhir_id
            if "focus" in stored.resource:
                resource["focus"] = stored.resource["focus"]  # the ServiceRequest this step fulfils
            builder.put(resource, version_id=stored.version_id)
            order = await store.closed_order(stored, task)  # cancelled -> revoked, completed -> completed
            if order is not None:
                builder.put(order, version_id=(order.get("meta") or {}).get("versionId"))
            for event in events:  # every step change is audited on the step, the close on the case Task
                if event.kind is EventKind.AUDIT:
                    builder.post(build_domain_audit_event(event, actor=actor, entities=[f"Task/{stored.fhir_id}"]))
        await self.save_case(loaded, new_case, result.events, actor=actor, directory=directory, bundle=builder)
        return TransitionOutcome(new_case, result.events)

    async def _conclusion_id(self, loaded: LoadedCase, case_id: str) -> str | None:
        """Business id of the signed conclusion (metadata only: its text is not read)."""
        latest = await self._latest_conclusion(loaded, case_id)
        value = ((latest or {}).get("identifier") or {}).get("value")
        return str(value) if value else None


def _completed_mdt_step(
    step: StoredTask,
    steps: Sequence[StoredTask],
    conclusion_id: str,
    loaded: LoadedCase,
    directory: Directory,
    now: datetime,
) -> tuple[Task, list[str], list[DomainEvent]]:
    """The open MDT step walked to `vysledek_dorucen`; raises TransitionError if the machine refuses."""
    koc = directory.org(managing_koc_id(loaded, directory) or "")
    return complete_mdt_step(
        step.task,
        conclusion_id,
        [s.task.id for s in steps if s.task.status is TaskStatus.COMPLETED],
        place=koc.org.name if koc else MDT_PLACE_FALLBACK,
        mdt_start=loaded.case.mdt_start or now,
        at=now,
    )


def _closed_step(
    stored: StoredTask,
    steps: Sequence[StoredTask],
    conclusion_id: str | None,
    loaded: LoadedCase,
    directory: Directory,
    actor: PartyRef,
    now: datetime,
) -> tuple[Task, tuple[DomainEvent, ...]]:
    """An open step at close: the MDT step is completed with the signed conclusion (reconciles a failed second write of
    the sign-off); every other step, and an MDT step the machine refuses, is cancelled."""
    if conclusion_id is not None and is_open_mdt_step(stored.task):
        try:
            task, _, events = _completed_mdt_step(stored, steps, conclusion_id, loaded, directory, now)
            return task, tuple(events)
        except TransitionError as exc:
            log.info("mdt_step_not_completed", task_id=stored.task.id, reason=exc.code)
    cancelled = task_machine.transition(
        stored.task, "cancel", actor.role, task_machine.TaskContext(reason=CLOSE_REASON), now
    )
    return cancelled.task.model_copy(update={"note": CLOSE_REASON}), cancelled.events  # note -> Task.statusReason


def _mdt_description(before: Task, after: Task, events: Sequence[str]) -> str:
    """Audit text of the MDT step's completion: ids and states only."""
    b = TaskBusinessStatus
    return (
        f"task {after.id}: {' + '.join(events)}; "
        f"{before.status.value}/{(before.business_status or b.OBJEDNANO).value} -> "
        f"{after.status.value}/{(after.business_status or b.OBJEDNANO).value}; "
        "MDT conclusion signed, recorded by the system"
    )


def _task_ref(loaded: LoadedCase, key: str) -> str:
    reference = loaded.task.get(key)
    if not isinstance(reference, dict) or "reference" not in reference:
        raise ValueError(f"coordinating Task has no {key} reference")
    return str(reference["reference"])


def _referring_gp(loaded: LoadedCase, directory: Directory) -> RoleEntry | None:
    reference = loaded.task.get("requester", {}).get("reference")
    return next((r for r in directory.roles if r.ref == reference), None) if reference else None
