"""SMS to the patient about a confirmed appointment: the confirmation (when the order is confirmed) and the reminder
the day before (watchdog round / demo advance). Texts: `app.notify.reminders`; channel: `app.notify.sms`.

Rules:
- Sent only after the task write has committed; a failure here never fails or undoes the transition.
- Idempotent per (task, kind): the `Communication` identifier `<task id>:<kind>` is looked up before sending, so demo
  replays, repeated watchdog rounds and retries send nothing twice. (Two truly concurrent calls could both send; the
  conditional create still keeps one record. Acceptable for the demo.)
- Each sent SMS is recorded as `Communication` through the repository (-> AuditEvent). Gateway failure: a warning, no
  record, the reminder is tried again next round. No phone: an info log. Logs carry ids only (no number, no text).
- SMS contact consent is not modelled: the demo relies on the referral consent (see the PR / issue).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

import structlog

from app.domain.task import Task
from app.fhir.client import Resource
from app.fhir.directory import DirectoryProvider
from app.fhir.mappers.notification import sms_business_id, sms_communication_to_fhir
from app.fhir.repository import FhirRepository
from app.fhir.systems import SID_SMS_NOTIFICATION
from app.fhir.tasks import StoredTask
from app.notify.reminders import SmsKind, confirmation_due, confirmation_text, reminder_due, reminder_text
from app.notify.sms import InvalidPhoneError, SmsDeliveryError, SmsGateway, SmsMessage

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SmsContacts:
    patient_reference: str
    phone: str | None
    episode_reference: str | None
    koc_reference: str | None  # the managing KOC Organization: the sender
    koc_phone: str | None  # structured phone of the managing KOC, if the directory has one


class PatientSmsNotifier:
    def __init__(self, repository: FhirRepository, gateway: SmsGateway, directory: DirectoryProvider) -> None:
        self._repo = repository
        self._gateway = gateway
        self._directory = directory

    async def appointment_confirmed(self, step: Resource, task: Task, at: datetime) -> bool:
        """After `order_confirmed` was saved: announce the appointment if it is a patient visit still ahead of `at`."""
        if not confirmation_due(task, at):
            return False
        return await self._send(step, task, "confirmation", at, lambda c: confirmation_text(task, c.koc_phone))

    async def remind_upcoming(self, steps: Iterable[StoredTask], now: datetime) -> list[str]:
        """Remind every confirmed patient visit within (now, now + 24 h] once; returns the reminded task ids."""
        reminded: list[str] = []
        for stored in steps:
            task = stored.task
            if not reminder_due(task, now):
                continue
            if await self._send(stored.resource, task, "reminder", now, reminder_text(task, now)):
                reminded.append(task.id)
        return reminded

    async def _send(
        self, step: Resource, task: Task, kind: SmsKind, at: datetime, render: str | Callable[[SmsContacts], str]
    ) -> bool:
        """`render` is the text, or builds it from the contacts (the confirmation names the KOC phone)."""
        business_id = sms_business_id(task.id, kind)
        try:
            if await self._repo.find_by_identifier("Communication", SID_SMS_NOTIFICATION, business_id):
                return False  # already sent (replay, repeated round)
            contacts = await self._contacts(step)
            if not contacts.phone:
                log.info("sms_skipped_no_phone", task_id=task.id, kind=kind)
                return False
            body = render if isinstance(render, str) else render(contacts)
            try:
                message_id = await self._gateway.send(SmsMessage(phone=contacts.phone, body=body))
            except InvalidPhoneError:
                log.warning("sms_skipped_invalid_phone", task_id=task.id, kind=kind)
                return False
            except SmsDeliveryError:
                log.warning("sms_failed", task_id=task.id, kind=kind)
                return False
            communication = sms_communication_to_fhir(
                task_id=task.id,
                kind=kind,
                patient_reference=contacts.patient_reference,
                task_reference=f"Task/{step['id']}",
                episode_reference=contacts.episode_reference,
                sender_reference=contacts.koc_reference,
                sent_at=at,
                message_id=message_id,
                body=body,
            )
            await self._repo.create(communication, if_none_exist=f"identifier={SID_SMS_NOTIFICATION}|{business_id}")
        except Exception:  # the task change is committed already: report, never undo it or answer 5xx for it
            log.exception("sms_notification_failed", task_id=task.id, kind=kind)
            return False
        log.info("sms_sent", task_id=task.id, kind=kind)
        return True

    async def _contacts(self, step: Resource) -> SmsContacts:
        """Patient phone (mobile first) and the managing KOC, from the step's `for` and `partOf` (ids only logged)."""
        patient_reference = str(step["for"]["reference"])
        patient = await self._repo.read(*patient_reference.split("/", 1))
        await self._repo.audit_read([patient_reference], subtype="read")  # contact data read to send the SMS
        case_task = await self._repo.read(*str(step["partOf"][0]["reference"]).split("/", 1))
        episode_reference = (case_task.get("focus") or {}).get("reference")
        koc_reference = koc_phone = None
        if episode_reference:
            episode = await self._repo.read(*str(episode_reference).split("/", 1))
            koc_reference = (episode.get("managingOrganization") or {}).get("reference")
        if koc_reference:
            directory = await self._directory.get()
            koc = next((o for o in directory.orgs if o.ref == koc_reference), None)
            koc_phone = koc.org.phone if koc else None
        return SmsContacts(
            patient_reference=patient_reference,
            phone=_mobile(patient.get("telecom", [])),
            episode_reference=str(episode_reference) if episode_reference else None,
            koc_reference=str(koc_reference) if koc_reference else None,
            koc_phone=koc_phone,
        )


def _mobile(telecom: list[Resource]) -> str | None:
    phones = [t for t in telecom if t.get("system") in ("phone", "sms") and t.get("value")]
    phones.sort(key=lambda t: t.get("use") != "mobile")
    return str(phones[0]["value"]) if phones else None
