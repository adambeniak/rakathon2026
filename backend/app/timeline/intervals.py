"""Time-to-treatment proxies T1/T2/T3, computed ONCE for the whole app (case header, insurer reviewer).

Definitions (docs/challenge-brief.md "Time to treatment"; golden `intervals_days`): the demo measures proxies and the UI
must call them so.

- T1 = first GP visit -> KOC referral   (golden `T1_first_GP_visit_to_KOC_referral`, demo case 31 days)
- T2 = KOC referral -> MDT              (golden `T2_KOC_referral_to_MDT`, 19 days)
- T3 = MDT -> oncology consult          (golden `T3_MDT_to_oncology_consult`, 14 days)

Days are whole calendar days between the Europe/Prague dates of the two anchors (10-02 09:30 -> 10-21 08:00 is
19 days, not the 18 of a datetime subtraction). An anchor nobody recorded is `None`; an interval is measured only when
both of its anchors are known, otherwise `days` is null and `status` says why. Nothing is estimated.

Sourcing (`case_anchors`): the KOC referral is `Case.opened_at`; the MDT is `Case.mdt_start`, counted only once the MDT
has been held (the case reached `zaver_mdt` or later), since before that it is a plan. The first GP visit and the
oncology consult are not stored as structured data today, so live T1 is `not_recorded` and T3 stays `running` after
the MDT (see the ADR `docs/adr/XXXX-reviewer-scoped-api.md`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.domain.case import Case, CaseState
from app.domain.clock import TZ

# States in which the MDT has been held: its conclusion was recorded (case_machine `record_mdt_conclusion`).
MDT_HELD_STATES = frozenset({CaseState.ZAVER_MDT, CaseState.ZPETNA_VAZBA_ODESLANA, CaseState.UZAVRENO})


class IntervalStatus(StrEnum):
    MEASURED = "measured"  # both anchors known: `days` is set
    RUNNING = "running"  # the start is known, the end is not (yet) recorded
    NOT_STARTED = "not_started"  # neither anchor is known yet (e.g. T3 before the MDT)
    NOT_RECORDED = "not_recorded"  # the end is known but the start was never recorded (e.g. T1, first GP visit)
    INCONSISTENT = "inconsistent"  # the recorded end lies before the start: shown as a mismatch, never "fixed"


@dataclass(frozen=True)
class Interval:
    start: date | None
    end: date | None
    days: int | None
    status: IntervalStatus


@dataclass(frozen=True)
class Anchors:
    """The four instants the proxies are measured between; `None` = not recorded."""

    first_gp_visit: date | datetime | None = None
    koc_referral: date | datetime | None = None
    mdt: date | datetime | None = None
    oncology_consult: date | datetime | None = None


@dataclass(frozen=True)
class TimeToTreatment:
    t1: Interval
    t2: Interval
    t3: Interval


def _day(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("interval anchors must be timezone-aware")
        return value.astimezone(TZ).date()
    return value


def interval(start: date | datetime | None, end: date | datetime | None) -> Interval:
    first, last = _day(start), _day(end)
    if first is not None and last is not None:
        if last < first:
            return Interval(first, last, None, IntervalStatus.INCONSISTENT)
        return Interval(first, last, (last - first).days, IntervalStatus.MEASURED)
    if first is not None:
        return Interval(first, None, None, IntervalStatus.RUNNING)
    if last is not None:
        return Interval(None, last, None, IntervalStatus.NOT_RECORDED)
    return Interval(None, None, None, IntervalStatus.NOT_STARTED)


def time_to_treatment(anchors: Anchors) -> TimeToTreatment:
    return TimeToTreatment(
        t1=interval(anchors.first_gp_visit, anchors.koc_referral),
        t2=interval(anchors.koc_referral, anchors.mdt),
        t3=interval(anchors.mdt, anchors.oncology_consult),
    )


def case_anchors(case: Case) -> Anchors:
    """The anchors the stored case carries (see the module docstring for what is not stored)."""
    return Anchors(
        koc_referral=case.opened_at,
        mdt=case.mdt_start if case.state in MDT_HELD_STATES else None,
    )


def case_intervals(case: Case) -> TimeToTreatment:
    return time_to_treatment(case_anchors(case))
