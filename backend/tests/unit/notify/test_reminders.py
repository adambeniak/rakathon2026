"""SMS texts for the patient: exact wording, Prague time (DST), length cap, no clinical content, reminder window."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.notify.reminders import (
    SMS_MAX_CHARS,
    confirmation_due,
    confirmation_text,
    reminder_due,
    reminder_text,
)
from app.settings import PRAGUE

CT_PLACE = "KOC 1 – Nemocnice Severní, radiologie"
CT_AT = datetime(2026, 10, 8, 8, 0, tzinfo=PRAGUE)


def ct(**update: Any) -> Task:
    task = Task(
        id="c1.ct",
        case_id="c1",
        code="ct-thorax-abdomen",
        title="CT hrudníku a břicha (pankreatický protokol)",
        status=TaskStatus.ACCEPTED,
        business_status=TaskBusinessStatus.POTVRZENO,
        location=CT_PLACE,
        scheduled_at=CT_AT,
    )
    return task.model_copy(update=update)


def test_confirmation_text_for_the_ct() -> None:
    assert confirmation_text(ct(), "+420 311 000 287") == (
        "Štafeta: Dobrý den, máte termín: CT vyšetření, 8. 10. 2026 v 08:00, "
        "KOC 1 – Nemocnice Severní, radiologie. Změnu termínu řešte s koordinátorem KOC, tel. +420 311 000 287."
    )


def test_patient_label_replaces_the_clinical_title() -> None:
    labs = confirmation_text(ct(code="labs-dx", title="Kontrolní odběry (KO, biochemie, CA 19-9)"), None)
    psycho = reminder_text(ct(code="psychooncology", title="Klinický psycholog (psychoonkologie)"), CT_AT)
    assert "máte termín: odběr krve, 8. 10. 2026" in labs
    assert "CA 19-9" not in labs
    assert ": konzultace s psychologem," in psycho


def test_confirmation_without_a_structured_phone_omits_the_number() -> None:
    assert confirmation_text(ct(), None).endswith("radiologie. Změnu termínu řešte s koordinátorem KOC.")


def test_reminder_text_for_the_ct() -> None:
    now = datetime(2026, 10, 7, 9, 0, tzinfo=PRAGUE)
    assert reminder_text(ct(), now) == (
        "Štafeta: Připomínka – zítra 8. 10. v 08:00: CT vyšetření, KOC 1 – Nemocnice Severní, radiologie."
    )


def test_reminder_says_today_when_the_window_falls_on_the_same_day() -> None:
    now = datetime(2026, 10, 8, 6, 0, tzinfo=PRAGUE)
    assert reminder_text(ct(), now).startswith("Štafeta: Připomínka – dnes 8. 10. v 08:00:")


def test_times_are_prague_local_across_the_dst_change() -> None:
    # 25. 10. 2026 the clocks go back (CEST -> CET): 07:00 UTC is 09:00 before, 08:00 after.
    before = ct(scheduled_at=datetime(2026, 10, 24, 7, 0, tzinfo=UTC))
    after = ct(scheduled_at=datetime(2026, 10, 26, 7, 0, tzinfo=UTC))
    assert "24. 10. 2026 v 09:00" in confirmation_text(before, None)
    assert "26. 10. 2026 v 08:00" in confirmation_text(after, None)


def test_a_date_without_time_does_not_invent_midnight() -> None:
    text = confirmation_text(ct(scheduled_at=datetime(2026, 10, 8, 0, 0, tzinfo=PRAGUE)), None)
    assert "8. 10. 2026, KOC 1" in text
    assert "00:00" not in text


def test_texts_fit_the_cap_and_carry_no_diagnosis_code() -> None:
    long_title = "Vyšetření " * 60
    for text in (
        confirmation_text(ct(), "+420 311 000 287"),
        reminder_text(ct(), CT_AT - timedelta(hours=10)),
        confirmation_text(ct(code="ad-hoc", title=long_title), "+420 311 000 287"),
        reminder_text(ct(code="ad-hoc", title=long_title), CT_AT - timedelta(hours=10)),
    ):
        assert len(text) <= SMS_MAX_CHARS
        assert not re.search(r"\b[A-Z]\d{2}(\.\d)?\b", text)  # no MKN-10 code such as C25
        assert "Traceback" not in text
    shortened = confirmation_text(ct(code="ad-hoc", title=long_title), "+420 311 000 287")
    assert "…" in shortened
    assert shortened.endswith("tel. +420 311 000 287.")


@pytest.mark.parametrize(
    ("now", "due"),
    [
        (CT_AT - timedelta(hours=24), True),  # boundary: exactly 24 h ahead is inside
        (CT_AT - timedelta(hours=24, seconds=1), False),  # not yet
        (CT_AT - timedelta(minutes=1), True),
        (CT_AT, False),  # the appointment has begun
        (CT_AT + timedelta(hours=1), False),  # past
    ],
)
def test_reminder_window(now: datetime, due: bool) -> None:
    assert reminder_due(ct(), now) is due


def test_reminders_only_for_confirmed_open_patient_visits() -> None:
    now = CT_AT - timedelta(hours=2)
    assert not reminder_due(ct(code="histology"), now)  # works on a sample, the patient does not come
    assert not reminder_due(ct(code="ad-hoc"), now)
    assert not reminder_due(ct(business_status=TaskBusinessStatus.PROVEDENO, status=TaskStatus.IN_PROGRESS), now)
    assert not reminder_due(ct(status=TaskStatus.CANCELLED), now)
    assert not reminder_due(ct(scheduled_at=None), now)


def test_confirmation_only_for_an_appointment_still_ahead() -> None:
    assert confirmation_due(ct(), CT_AT - timedelta(days=3))
    assert not confirmation_due(ct(), CT_AT + timedelta(minutes=1))  # replayed past date
    assert not confirmation_due(ct(code="mdt"), CT_AT - timedelta(days=3))
