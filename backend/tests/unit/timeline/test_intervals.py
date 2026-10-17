"""T1/T2/T3 proxies: the demo case yields the golden 31/19/14 when all anchors are known; missing anchors give null."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from app.domain.case import Case, CaseState
from app.domain.patient import Patient, Sex
from app.settings import PRAGUE
from app.timeline.intervals import Anchors, IntervalStatus, case_intervals, interval, time_to_treatment

GOLDEN = Path(__file__).resolve().parents[4] / "data" / "golden" / "expected_handover_2026-10-21.json"
REFERRAL = datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE)
MDT = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)
# The golden timeline: "První vyšetření u PL" 2026-09-01 and "Onkologické konzilium (plán)" 2026-11-04.
DEMO_ANCHORS = Anchors(
    first_gp_visit=date(2026, 9, 1), koc_referral=REFERRAL, mdt=MDT, oncology_consult=date(2026, 11, 4)
)


def _case(state: CaseState, *, opened_at: datetime | None = REFERRAL, mdt_start: datetime | None = MDT) -> Case:
    patient = Patient(
        given="Alena", family="Procházková", sex=Sex.FEMALE, birth_date=date(1963, 7, 22), birth_number="635722/1013"
    )
    return Case(id="rakathon-2026-prochazkova", patient=patient, state=state, opened_at=opened_at, mdt_start=mdt_start)


def test_demo_case_yields_the_golden_intervals() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["intervals_days"]

    result = time_to_treatment(DEMO_ANCHORS)

    assert (result.t1.days, result.t2.days, result.t3.days) == (
        golden["T1_first_GP_visit_to_KOC_referral"],
        golden["T2_KOC_referral_to_MDT"],
        golden["T3_MDT_to_oncology_consult"],
    )
    assert (result.t1.days, result.t2.days, result.t3.days) == (31, 19, 14)
    assert {result.t1.status, result.t2.status, result.t3.status} == {IntervalStatus.MEASURED}


def test_days_are_counted_on_prague_dates_not_by_datetime_subtraction() -> None:
    assert (MDT - REFERRAL).days == 18  # the trap
    assert interval(REFERRAL, MDT).days == 19
    # 23:30 UTC on 1 Oct is already 2 Oct in Prague.
    assert interval(datetime.fromisoformat("2026-10-01T23:30:00+00:00"), date(2026, 10, 3)).days == 1


@pytest.mark.parametrize(
    ("anchors", "expected"),
    [
        (Anchors(koc_referral=REFERRAL, mdt=MDT, oncology_consult=date(2026, 11, 4)), (None, 19, 14)),
        (Anchors(first_gp_visit=date(2026, 9, 1), koc_referral=REFERRAL, mdt=MDT), (31, 19, None)),
        (Anchors(first_gp_visit=date(2026, 9, 1), koc_referral=REFERRAL), (31, None, None)),
        (Anchors(), (None, None, None)),
    ],
)
def test_a_missing_end_point_gives_null(anchors: Anchors, expected: tuple[int | None, ...]) -> None:
    result = time_to_treatment(anchors)

    assert (result.t1.days, result.t2.days, result.t3.days) == expected


def test_status_says_why_a_value_is_null() -> None:
    result = time_to_treatment(Anchors(koc_referral=REFERRAL))

    assert result.t1.status is IntervalStatus.NOT_RECORDED
    assert result.t2.status is IntervalStatus.RUNNING
    assert result.t3.status is IntervalStatus.NOT_STARTED


def test_an_end_before_the_start_is_flagged_not_corrected() -> None:
    result = interval(MDT, REFERRAL)

    assert result.days is None
    assert result.status is IntervalStatus.INCONSISTENT


def test_naive_datetimes_are_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        interval(datetime(2026, 10, 2, 9, 30), MDT)  # noqa: DTZ001 - the point of the test


def test_a_planned_mdt_is_not_counted_until_it_was_held() -> None:
    planned = case_intervals(_case(CaseState.PRIPRAVENO_MDT))
    held = case_intervals(_case(CaseState.ZAVER_MDT))

    assert planned.t2.days is None
    assert planned.t2.status is IntervalStatus.RUNNING
    assert held.t2.days == 19


def test_stored_case_has_no_first_gp_visit_or_oncology_consult() -> None:
    result = case_intervals(_case(CaseState.UZAVRENO))

    assert result.t1.days is None
    assert result.t1.status is IntervalStatus.NOT_RECORDED
    assert result.t3.days is None
    assert result.t3.status is IntervalStatus.RUNNING


def test_case_without_referral_time_has_no_intervals() -> None:
    result = case_intervals(_case(CaseState.ODESLANO, opened_at=None, mdt_start=None))

    assert (result.t1.days, result.t2.days, result.t3.days) == (None, None, None)
