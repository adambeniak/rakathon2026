"""Insurer analytics over the fictitious cohort: Prague calendar days, nulls never estimated, medians, indicator."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date

import pytest

from app.timeline import insurer_analytics as ia
from app.timeline.insurer_analytics import IntervalKey, IntervalStatus, MilestoneKey


@pytest.fixture(scope="module")
def cohort() -> ia.Cohort:
    return ia.load_cohort()


@pytest.fixture(scope="module")
def analytics(cohort: ia.Cohort) -> ia.Analytics:
    return ia.compute(cohort)


# ------------------------------------------------------------------------------------------------- day counting


def test_prague_date_uses_the_prague_calendar_day_not_utc() -> None:
    # 23:30 UTC on 7 Oct is 01:30 on 8 Oct in Prague (CEST)
    assert ia.prague_date("2026-10-07T23:30:00Z") == date(2026, 10, 8)
    assert ia.prague_date("2026-10-08") == date(2026, 10, 8)
    assert ia.prague_date("2026-10-08T00:10:00") == date(2026, 10, 8)  # naive = Prague
    assert ia.prague_date(None) is None


def test_demo_referral_to_mdt_is_19_calendar_days_not_18() -> None:
    start = ia.prague_date("2026-10-02T09:30:00+02:00")
    end = ia.prague_date("2026-10-21T08:00:00+02:00")
    assert ia.interval(IntervalKey.CONTACT_TO_MDT, start, end).days == 19


def test_dst_change_counts_whole_calendar_days() -> None:
    # spring forward 29 Mar 2026 (a 23 h day) and fall back 25 Oct 2026 (a 25 h day): still one day each
    spring = ia.interval(
        IntervalKey.CT_ORDER_TO_CT,
        ia.prague_date("2026-03-28T23:30:00+01:00"),
        ia.prague_date("2026-03-29T23:30:00+02:00"),
    )
    autumn = ia.interval(
        IntervalKey.CT_ORDER_TO_CT,
        ia.prague_date("2026-10-24T23:30:00+02:00"),
        ia.prague_date("2026-10-25T23:30:00+01:00"),
    )
    assert (spring.days, autumn.days) == (1, 1)


@pytest.mark.parametrize(
    ("start", "end", "days", "status"),
    [
        (date(2026, 10, 2), date(2026, 10, 8), 6, IntervalStatus.MEASURED),
        (date(2026, 10, 2), date(2026, 10, 2), 0, IntervalStatus.MEASURED),
        (date(2026, 10, 21), None, None, IntervalStatus.RUNNING),
        (None, date(2026, 10, 8), None, IntervalStatus.NOT_RECORDED),
        (None, None, None, IntervalStatus.NOT_STARTED),
        (date(2026, 10, 8), date(2026, 10, 2), None, IntervalStatus.INCONSISTENT),
    ],
)
def test_interval_is_null_unless_both_anchors_are_known_and_in_order(
    start: date | None, end: date | None, days: int | None, status: IntervalStatus
) -> None:
    result = ia.interval(IntervalKey.CT_ORDER_TO_CT, start, end)
    assert (result.days, result.status) == (days, status)


# ----------------------------------------------------------------------------------------------------- the cohort


def test_cohort_is_tagged_simulated_and_pseudonymous(cohort: ia.Cohort) -> None:
    assert cohort.tag == "stafeta-demo"
    assert cohort.simulated is True
    assert len(cohort.hospitals) == 4
    simulated = [j for j in cohort.journeys if j.simulated]
    assert len(simulated) >= 20
    assert all(re.fullmatch(r"SIM-2026-\d{3}", j.code) for j in simulated)
    assert [j.code for j in cohort.journeys if not j.simulated] == ["rakathon-2026-prochazkova"]


def test_no_date_lies_after_the_snapshot(cohort: ia.Cohort) -> None:
    as_of = cohort.as_of.astimezone(ia.TZ).date()
    for journey in cohort.journeys:
        for field in ia.DATE_FIELDS:
            value = journey.anchor(field)
            assert value is None or value <= as_of, (journey.code, field)


def test_demo_journey_follows_the_golden_dates_and_has_no_treatment_start(analytics: ia.Analytics) -> None:
    demo = analytics.journeys[0]  # the real demo case first
    assert demo.journey.code == "rakathon-2026-prochazkova"
    milestones = {m.key: m.date for m in demo.milestones}
    assert milestones == {
        MilestoneKey.GP_CONTACTED_COORDINATOR: date(2026, 10, 2),
        MilestoneKey.ACCEPTED: None,
        MilestoneKey.CT_DONE: date(2026, 10, 8),
        MilestoneKey.BIOPSY_DONE: date(2026, 10, 12),
        MilestoneKey.MDT: date(2026, 10, 21),
        MilestoneKey.TREATMENT_START: None,  # the oncology consult on 4 Nov is planned, not a treatment start
    }
    assert demo.days(IntervalKey.CT_ORDER_TO_CT) == 6
    assert demo.days(IntervalKey.BIOPSY_ORDER_TO_BIOPSY) == 10
    assert demo.days(IntervalKey.CONTACT_TO_MDT) == 19
    assert demo.days(IntervalKey.MDT_TO_TREATMENT) is None
    assert demo.days(IntervalKey.CONTACT_TO_TREATMENT) is None
    assert demo.journey.coordinator_minutes is None  # not recorded, never estimated


def test_milestone_gaps_only_between_two_recorded_neighbours(analytics: ia.Analytics) -> None:
    gaps = [m.days_since_previous for m in analytics.journeys[0].milestones]
    # contact (first) | accepted missing | CT after a missing one | biopsy +4 | MDT +9 | start missing
    assert gaps == [None, None, None, 4, 9, None]


# ------------------------------------------------------------------------------------------- aggregation helpers


def test_median_skips_nulls_and_is_none_without_values() -> None:
    assert ia._median([3, None, 5, 10]) == 5.0
    assert ia._median([None, None]) is None


def test_inverted_min_max_and_the_all_equal_case() -> None:
    values = [10.0, 20.0, 30.0]
    assert ia.inverted_min_max(10.0, values) == 1.0
    assert ia.inverted_min_max(30.0, values) == 0.0
    assert ia.inverted_min_max(20.0, values) == 0.5
    assert ia.inverted_min_max(7.0, [7.0]) == 1.0  # a single hospital: no division by zero
    assert ia.inverted_min_max(None, values) is None


def test_indicator_formula_weights_speed_cost_and_target_share() -> None:
    assert ia.operational_indicator(1.0, 1.0, 1.0) == 100.0
    assert ia.operational_indicator(0.0, 0.0, 0.0) == 0.0
    assert ia.operational_indicator(0.5, 1.0, 0.25) == pytest.approx(60.0)
    assert ia.operational_indicator(None, 1.0, 1.0) is None


def test_competition_ranking_shares_ranks_on_ties() -> None:
    ranks = ia.competition_ranks({"a": 90.0, "b": 90.0, "c": 50.0, "d": None}, descending=True)
    assert ranks == {"a": 1, "b": 1, "c": 3, "d": None}


def test_single_hospital_cohort_scores_one_everywhere(cohort: ia.Cohort) -> None:
    only = cohort.hospitals[0]
    single = replace(
        cohort,
        hospitals=(only,),
        coordinators=tuple(c for c in cohort.coordinators if c.hospital_id == only.id),
        journeys=tuple(j for j in cohort.journeys if j.hospital_id == only.id),
    )
    result = ia.compute(single)
    (stats,) = result.hospitals
    assert (stats.speed_score, stats.cost_score) == (1.0, 1.0)
    assert stats.indicator_rank == 1
    assert stats.fastest
    assert stats.lowest_cost


# --------------------------------------------------------------------------------------------- per hospital / rank


def test_hospital_medians_and_ranking(analytics: ia.Analytics) -> None:
    by_id = {s.hospital.id: s for s in analytics.hospitals}
    fast = by_id["koc3-nemocnice-vychodni-sim"]
    slow = by_id["koc4-nemocnice-horska-sim"]
    assert fast.median_days[IntervalKey.CONTACT_TO_MDT] == 11.5
    assert slow.median_days[IntervalKey.CONTACT_TO_MDT] == 39.0
    assert fast.indicator == 100.0
    assert fast.fastest
    assert fast.lowest_cost
    assert slow.indicator == 0.0
    assert analytics.ranking_by_indicator == (
        "koc3-nemocnice-vychodni-sim",
        "koc1-nemocnice-severni",
        "koc2-nemocnice-lipova",
        "koc4-nemocnice-horska-sim",
    )
    assert analytics.ranking_lowest_cost[:3] == (
        "koc3-nemocnice-vychodni-sim",
        "koc2-nemocnice-lipova",
        "koc1-nemocnice-severni",
    )
    assert [s.hospital.id for s in analytics.hospitals] == list(analytics.ranking_by_indicator)
    assert sum(s.cases for s in analytics.hospitals) == len(analytics.journeys)


def test_indicator_matches_its_components(analytics: ia.Analytics) -> None:
    for stats in analytics.hospitals:
        assert stats.speed_score is not None
        assert stats.cost_score is not None
        assert stats.within_target_share is not None
        expected = 100 * (0.5 * stats.speed_score + 0.3 * stats.cost_score + 0.2 * stats.within_target_share)
        assert stats.indicator == pytest.approx(expected, abs=0.1)


def test_utilisation_uses_the_explicit_capacity(analytics: ia.Analytics) -> None:
    capacity = analytics.cohort.capacity_minutes_per_week * analytics.period_weeks
    for stats in analytics.coordinators:
        assert stats.utilisation_pct == pytest.approx(100 * stats.minutes_total / capacity, abs=0.1)


def test_malformed_cohort_is_rejected() -> None:
    with pytest.raises(ia.CohortError):
        ia.parse_cohort(
            {
                "tag": "stafeta-demo",
                "simulated": True,
                "as_of": "2026-10-21T08:00:00+02:00",
                "coordinator_capacity_minutes_per_week": 120,
                "hospitals": [{"id": "h", "name": "H", "simulated": True}],
                "coordinators": [{"id": "c", "display": "C", "hospital_id": "h", "simulated": True}],
                "price_list": {"note": "n", "items": []},
                "journeys": [
                    {
                        "code": "SIM-1",
                        "simulated": True,
                        "hospital_id": "h",
                        "coordinator_id": "c",
                        "steps": ["UNPRICED"],
                    }
                ],
            }
        )
