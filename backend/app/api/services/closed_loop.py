"""Demo steps 5-6 as write operations that need more than a state change: the MDT conclusion and the GP feedback.

`CaseWorkflow` stays the one entry point of `POST /cases/{id}/transitions`; this subclass intercepts the two events
that carry data or a side effect and delegates every other event to the base class.

- `record_mdt_conclusion`: ONE transaction = case Task PUT (If-Match) + business AuditEvent + the conclusion
  `Composition` + its sign-off `Provenance`. The case cannot be signed off without the text being stored, and the
  signer is always the acting physician.
- `send_feedback`: both machine events are checked in memory first (nothing is sent when a guard fails), then the
  e-mail goes to the referring GP through the `Mailer`; only after the relay accepted it ONE transaction writes the
  case Task (state `zpetna_vazba_odeslana`, delivery receipt), the AuditEvent of `send_feedback` (the coordinator),
  the AuditEvent of `delivery_confirmed` (the system actor, receipt = SMTP Message-ID) and the `Communication`.
  If SMTP fails the case stays in `zaver_mdt` and the coordinator can retry; the e-mail holds no clinical text.
"""

from __future__ import annotations

from datetime import datetime

from app.domain import case_machine
from app.domain.case import CaseState
from app.domain.common import PartyRef, Role
from app.domain.errors import ForbiddenError, InvalidInputError, NotFoundError
from app.domain.events import EventKind
from app.fhir.audit import build_domain_audit_event
from app.fhir.bundles import BundleBuilder
from app.fhir.cases import CaseReader, LoadedCase
from app.fhir.directory import Directory, RoleEntry
from app.fhir.mappers.feedback import feedback_communication_to_fhir
from app.fhir.mappers.mdt_conclusion import (
    TYPE_MDT_CONCLUSION,
    MdtConclusionRecord,
    is_conclusion_of,
    mdt_conclusion_from_fhir,
    mdt_conclusion_provenance,
    mdt_conclusion_to_fhir,
)
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_COMPOSITION_TYPE
from app.fhir.workflow import CaseWorkflow, TransitionOutcome, assign_holder, authorize_case, managing_koc_id
from app.notify.feedback_mail import FeedbackMailInput, build_feedback_mail
from app.notify.mailer import Mailer, new_message_id
from app.security.actor import SYSTEM_ACTOR

# The GP may read the conclusion only once the feedback has been sent to them.
GP_VISIBLE_STATES = frozenset({CaseState.ZPETNA_VAZBA_ODESLANA, CaseState.UZAVRENO})


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
    ) -> TransitionOutcome:
        if event == "record_mdt_conclusion":
            return await self.record_conclusion(case_id, conclusion, actor=actor, directory=directory, now=now)
        if event == "send_feedback":
            return await self.send_feedback(case_id, actor=actor, directory=directory, now=now)
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
        return TransitionOutcome(new_case, result.events)

    async def get_conclusion(self, case_id: str, *, actor: PartyRef, directory: Directory) -> MdtConclusionRecord:
        loaded = await self._reader.load(case_id)  # audited read
        authorize_case(loaded, actor, directory)
        if actor.role is Role.GP and loaded.case.state not in GP_VISIBLE_STATES:
            raise ForbiddenError("the feedback has not been sent yet")
        found = await self._repo.search(
            "Composition",
            {
                "subject": _task_ref(loaded, "for"),
                "type": f"{CS_COMPOSITION_TYPE}|{TYPE_MDT_CONCLUSION}",
                "_count": "50",
            },
        )
        mine = [c for c in found if is_conclusion_of(c, case_id)]
        if not mine:
            raise NotFoundError("MDT conclusion", case_id)
        latest = max(mine, key=lambda c: str(c["date"]))
        await self._repo.audit_read([f"Composition/{latest['id']}"])
        return mdt_conclusion_from_fhir(latest)

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
            raise InvalidInputError("the referring GP of the case is unknown")
        sender = directory.role(actor.id)
        koc = directory.org(managing_koc_id(loaded, directory) or "")
        if sender is None or koc is None:
            raise InvalidInputError("the sender or the managing KOC is not in the directory")

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
        receipt = await self._mailer.send(message)  # MailDeliveryError: nothing written, the coordinator may retry

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
                message_id=receipt,
                body=message.body,
            )
        )
        task_reference = f"Task/{loaded.task['id']}"
        for event in delivered.events:  # delivery is confirmed by the system, not by the coordinator who clicked
            if event.kind is EventKind.AUDIT:
                builder.post(build_domain_audit_event(event, actor=SYSTEM_ACTOR, entities=[task_reference]))
        await self.save_case(loaded, new_case, sent.events, actor=actor, directory=directory, bundle=builder)
        return TransitionOutcome(new_case, (*sent.events, *delivered.events))


def _task_ref(loaded: LoadedCase, key: str) -> str:
    reference = loaded.task.get(key)
    if not isinstance(reference, dict) or "reference" not in reference:
        raise ValueError(f"coordinating Task has no {key} reference")
    return str(reference["reference"])


def _referring_gp(loaded: LoadedCase, directory: Directory) -> RoleEntry | None:
    reference = loaded.task.get("requester", {}).get("reference")
    return next((r for r in directory.roles if r.ref == reference), None) if reference else None
