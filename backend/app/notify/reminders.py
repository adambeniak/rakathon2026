"""SMS texts for the patient: appointment confirmation and the day-before reminder (pure functions, no I/O).

Minimisation and safety: the text says only what, when and where — a plain patient-facing label of the step (not the
clinical board title, which may name tumour markers or "psychoonkologie"), the confirmed date/time and the workplace.
No diagnosis, no clinical advice, no preparation instructions. The label and the workplace are still health data; this
is the accepted trade-off of an appointment reminder.
Times are always shown in Europe/Prague, whatever offset the stored instant carries; `now` is the demo-aware clock.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Final, Literal

from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.settings import PRAGUE

SmsKind = Literal["confirmation", "reminder"]

SMS_MAX_CHARS: Final = 320
REMINDER_WINDOW: Final = timedelta(hours=24)
ELLIPSIS: Final = "…"

# Pathway steps the patient attends in person. Histology works on a sample and the MDT meets without the patient;
# ad-hoc tasks may be anything, so they are not announced to the patient.
# Only these get an SMS, under these plain labels (never the clinical title).
PATIENT_LABELS: Final = {
    "ct-thorax-abdomen": "CT vyšetření",
    "eus-fnb": "endoskopické vyšetření",
    "labs-dx": "odběr krve",
    "algesiology": "vyšetření v ambulanci léčby bolesti",
    "psychooncology": "konzultace s psychologem",
}
PATIENT_ATTENDED_CODES: Final = frozenset(PATIENT_LABELS)

CONFIRMATION: Final = "Štafeta: Dobrý den, máte termín: {title}, {date}{time}{place}. {contact}"
CONTACT_WITH_PHONE: Final = "Změnu termínu řešte s koordinátorem KOC, tel. {phone}."
CONTACT_WITHOUT_PHONE: Final = "Změnu termínu řešte s koordinátorem KOC."
REMINDER: Final = "Štafeta: Připomínka – {day} {day_month}{time}: {title}{place}."


def czech_date(moment: datetime) -> str:
    """'8. 10. 2026' in Prague."""
    local = moment.astimezone(PRAGUE)
    return f"{local.day}. {local.month}. {local.year}"


def czech_day_month(moment: datetime) -> str:
    """'8. 10.' in Prague."""
    local = moment.astimezone(PRAGUE)
    return f"{local.day}. {local.month}."


def czech_time(moment: datetime) -> str:
    """'08:00' in Prague."""
    return moment.astimezone(PRAGUE).strftime("%H:%M")


def is_patient_appointment(task: Task) -> bool:
    return task.code in PATIENT_ATTENDED_CODES and task.scheduled_at is not None


def confirmation_due(task: Task, at: datetime) -> bool:
    """Announce a confirmed appointment only if it lies ahead of the confirmation moment `at` (the demo replay passes
    the story's confirmation time, so it announces the story's appointments as of then)."""
    return is_patient_appointment(task) and task.scheduled_at is not None and task.scheduled_at > at


def reminder_due(task: Task, now: datetime) -> bool:
    """A confirmed, not yet performed appointment within (now, now + 24 h]."""
    if not is_patient_appointment(task) or task.scheduled_at is None:
        return False
    if task.business_status is not TaskBusinessStatus.POTVRZENO:
        return False
    if task.status not in (TaskStatus.REQUESTED, TaskStatus.ACCEPTED):
        return False
    return now < task.scheduled_at <= now + REMINDER_WINDOW


def confirmation_text(task: Task, koc_phone: str | None) -> str:
    when = _scheduled(task)
    contact = CONTACT_WITH_PHONE.format(phone=koc_phone) if koc_phone else CONTACT_WITHOUT_PHONE
    return _fit(
        lambda title: CONFIRMATION.format(
            title=title, date=czech_date(when), time=_at_time(when), place=_place(task), contact=contact
        ),
        PATIENT_LABELS.get(task.code, task.title),
    )


def reminder_text(task: Task, now: datetime) -> str:
    when = _scheduled(task)
    return _fit(
        lambda title: REMINDER.format(
            day=_relative_day(when, now),
            day_month=czech_day_month(when),
            time=_at_time(when),
            title=title,
            place=_place(task),
        ),
        PATIENT_LABELS.get(task.code, task.title),
    )


def _scheduled(task: Task) -> datetime:
    if task.scheduled_at is None:
        raise ValueError(f"task {task.id} has no confirmed date")
    return task.scheduled_at


def _at_time(moment: datetime) -> str:
    """' v 08:00'; empty for a date confirmed without a time (stored as 00:00 Prague), so no midnight is invented."""
    local = moment.astimezone(PRAGUE)
    return "" if (local.hour, local.minute) == (0, 0) else f" v {czech_time(local)}"


def _relative_day(scheduled_at: datetime, now: datetime) -> str:
    """'dnes' or 'zítra' by the Prague calendar day (a 24 h window can still fall on the same day)."""
    day = scheduled_at.astimezone(PRAGUE).date()
    return "dnes" if day == now.astimezone(PRAGUE).date() else "zítra"


def _place(task: Task) -> str:
    location = " ".join((task.location or "").split())
    return f", {location}" if location else ""


def _fit(render: Callable[[str], str], title: str) -> str:
    """Render with the title shortened (never the date, time or place) until the SMS fits `SMS_MAX_CHARS`."""
    title = " ".join(title.split())
    text = render(title)
    overflow = len(text) - SMS_MAX_CHARS
    if overflow > 0:
        text = render(title[: max(len(title) - overflow - len(ELLIPSIS), 0)].rstrip() + ELLIPSIS)
    return text[:SMS_MAX_CHARS]
