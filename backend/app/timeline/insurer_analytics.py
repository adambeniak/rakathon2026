"""Insurer (ZP) analytics over a FICTITIOUS cohort: durations between care steps, order-to-exam delays per hospital,
coordinator load, illustrative cost and a transparent operational indicator,
not a measure of quality of care (ADR `docs/adr/XXXX-insurer-analytics.md`).

Pure: `load_cohort` parses the fixture `app/seed/data/insurer_cohort.json`, `compute` derives everything from it.
Nothing is read from FHIR and nothing is estimated: an interval whose end (or start) was not recorded has `days=None`.

Days are whole calendar days between the Europe/Prague dates of the two anchors, the same convention as the
time-to-treatment proxies (`app.timeline.intervals`, P1). TODO(#191) reuse `intervals.interval()` once it
is on main.

Operational indicator 0-100, not a measure of quality of care (a demo assumption, returned so the UI can show it):
    50 % speed  = inverted min-max of the hospital's median "contact -> MDT" days (fastest = 1, slowest = 0)
    30 % cost   = inverted min-max of the hospital's median illustrative cost per case (cheapest = 1)
    20 % target = share of the hospital's journeys with CT order -> CT <= 7 days AND biopsy order -> biopsy <= 10 days
When all hospitals have the same value (min == max) the component is 1 for everyone (no division by zero).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from statistics import median
from typing import Any

from app.domain.clock import TZ

COHORT_PATH = Path(__file__).resolve().parent.parent / "seed" / "data" / "insurer_cohort.json"

WEIGHT_SPEED = 0.5
WEIGHT_COST = 0.3
WEIGHT_TARGET = 0.2
TARGET_CT_DAYS = 7
TARGET_BIOPSY_DAYS = 10


class IntervalStatus(StrEnum):
    """Same values as `app.timeline.intervals.IntervalStatus` (P1), so the UI can share labels."""

    MEASURED = "measured"
    RUNNING = "running"  # start known, end not recorded
    NOT_STARTED = "not_started"  # neither anchor recorded
    NOT_RECORDED = "not_recorded"  # end known, start never recorded
    INCONSISTENT = "inconsistent"  # end before start: shown as a mismatch, never "fixed"


class IntervalKey(StrEnum):
    CONTACT_TO_ACCEPTED = "contact_to_accepted"
    CT_ORDER_TO_CT = "ct_order_to_ct"
    BIOPSY_ORDER_TO_BIOPSY = "biopsy_order_to_biopsy"
    CONTACT_TO_MDT = "contact_to_mdt"
    MDT_TO_TREATMENT = "mdt_to_treatment"
    CONTACT_TO_TREATMENT = "contact_to_treatment"


class MilestoneKey(StrEnum):
    GP_CONTACTED_COORDINATOR = "gp_contacted_coordinator"
    ACCEPTED = "accepted"
    CT_DONE = "ct_done"
    BIOPSY_DONE = "biopsy_done"
    MDT = "mdt"
    TREATMENT_START = "treatment_start"


MILESTONE_ORDER: tuple[MilestoneKey, ...] = tuple(MilestoneKey)

# interval -> (start field, end field) of a journey
INTERVAL_ANCHORS: Mapping[IntervalKey, tuple[str, str]] = {
    IntervalKey.CONTACT_TO_ACCEPTED: ("gp_contacted_coordinator", "accepted"),
    IntervalKey.CT_ORDER_TO_CT: ("ct_ordered", "ct_done"),
    IntervalKey.BIOPSY_ORDER_TO_BIOPSY: ("biopsy_ordered", "biopsy_done"),
    IntervalKey.CONTACT_TO_MDT: ("gp_contacted_coordinator", "mdt"),
    IntervalKey.MDT_TO_TREATMENT: ("mdt", "treatment_start"),
    IntervalKey.CONTACT_TO_TREATMENT: ("gp_contacted_coordinator", "treatment_start"),
}

DATE_FIELDS = (
    "gp_contacted_coordinator",
    "accepted",
    "ct_ordered",
    "ct_done",
    "biopsy_ordered",
    "biopsy_done",
    "mdt",
    "treatment_start",
)


class CohortError(ValueError):
    """The cohort fixture is malformed."""


# ---------------------------------------------------------------------------------------------------------- model


@dataclass(frozen=True)
class Hospital:
    id: str
    name: str
    simulated: bool


@dataclass(frozen=True)
class Coordinator:
    id: str
    display: str
    hospital_id: str
    simulated: bool


@dataclass(frozen=True)
class PriceItem:
    code: str
    label: str
    price_czk: int


@dataclass(frozen=True)
class Journey:
    code: str
    simulated: bool
    hospital_id: str
    coordinator_id: str
    gp_contacted_coordinator: date | None
    accepted: date | None
    ct_ordered: date | None
    ct_done: date | None
    biopsy_ordered: date | None
    biopsy_done: date | None
    mdt: date | None
    treatment_start: date | None
    coordinator_minutes: int | None
    steps: tuple[str, ...]

    def anchor(self, field: str) -> date | None:
        value: date | None = getattr(self, field)
        return value


@dataclass(frozen=True)
class Cohort:
    tag: str
    simulated: bool
    as_of: datetime
    capacity_minutes_per_week: int
    hospitals: tuple[Hospital, ...]
    coordinators: tuple[Coordinator, ...]
    price_list: tuple[PriceItem, ...]
    price_list_note: str
    journeys: tuple[Journey, ...]


@dataclass(frozen=True)
class Interval:
    key: IntervalKey
    start: date | None
    end: date | None
    days: int | None
    status: IntervalStatus


@dataclass(frozen=True)
class Milestone:
    key: MilestoneKey
    date: date | None
    days_since_previous: int | None  # only when this and the previous milestone are both recorded and in order


@dataclass(frozen=True)
class JourneyResult:
    journey: Journey
    hospital_name: str
    coordinator_display: str
    milestones: tuple[Milestone, ...]
    intervals: tuple[Interval, ...]
    cost_czk: int
    within_target: bool | None  # None when CT or biopsy wait is not measured

    def days(self, key: IntervalKey) -> int | None:
        return next(i.days for i in self.intervals if i.key is key)


@dataclass(frozen=True)
class HospitalStats:
    hospital: Hospital
    cases: int
    median_days: Mapping[IntervalKey, float | None]
    median_cost_czk: float | None
    median_coordinator_minutes: float | None
    coordinator_minutes_total: int
    coordinators: int
    utilisation_pct: float | None
    within_target_share: float | None
    speed_score: float | None
    cost_score: float | None
    indicator: float | None
    indicator_rank: int | None
    fastest: bool
    lowest_cost: bool


@dataclass(frozen=True)
class CoordinatorStats:
    coordinator: Coordinator
    hospital_name: str
    cases: int
    median_minutes_per_patient: float | None
    median_days_contact_to_accepted: float | None
    minutes_total: int
    utilisation_pct: float | None


@dataclass(frozen=True)
class Analytics:
    cohort: Cohort
    period_start: date
    period_end: date
    period_weeks: float
    journeys: tuple[JourneyResult, ...]
    hospitals: tuple[HospitalStats, ...]  # ordered by indicator rank, then name
    coordinators: tuple[CoordinatorStats, ...]
    ranking_by_indicator: tuple[str, ...]
    ranking_fastest: tuple[str, ...]
    ranking_lowest_cost: tuple[str, ...]
    cohort_median_days: Mapping[IntervalKey, float | None]  # over every journey of the cohort


# -------------------------------------------------------------------------------------------------------- parsing


def prague_date(value: str | None) -> date | None:
    """ISO date or datetime -> the Europe/Prague calendar date; None stays None. A naive datetime is Prague time."""
    if value is None:
        return None
    if "T" not in value:
        return date.fromisoformat(value)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ).date()


def _str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise CohortError(f"missing string {key!r}")
    return value


def _bool(raw: Mapping[str, Any], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise CohortError(f"missing boolean {key!r}")
    return value


def _opt_date(raw: Mapping[str, Any], key: str) -> date | None:
    value = raw.get(key)
    if value is not None and not isinstance(value, str):
        raise CohortError(f"{key!r} must be an ISO date or null")
    try:
        return prague_date(value)
    except ValueError as exc:
        raise CohortError(f"{key!r} is not an ISO date: {value!r}") from exc


def parse_cohort(raw: Mapping[str, Any]) -> Cohort:
    hospitals = tuple(Hospital(_str(h, "id"), _str(h, "name"), _bool(h, "simulated")) for h in raw["hospitals"])
    hospital_ids = {h.id for h in hospitals}
    coordinators = tuple(
        Coordinator(_str(c, "id"), _str(c, "display"), _str(c, "hospital_id"), _bool(c, "simulated"))
        for c in raw["coordinators"]
    )
    coordinator_ids = {c.id for c in coordinators}
    price = raw["price_list"]
    items = tuple(PriceItem(_str(i, "code"), _str(i, "label"), int(i["price_czk"])) for i in price["items"])
    codes = {i.code for i in items}
    journeys: list[Journey] = []
    for j in raw["journeys"]:
        minutes = j.get("coordinator_minutes")
        if minutes is not None and (not isinstance(minutes, int) or minutes < 0):
            raise CohortError("coordinator_minutes must be a non-negative integer or null")
        steps = tuple(j.get("steps", ()))
        unknown = set(steps) - codes
        if unknown:
            raise CohortError(f"journey {j.get('code')!r} has steps without a price: {sorted(unknown)}")
        journey = Journey(
            code=_str(j, "code"),
            simulated=_bool(j, "simulated"),
            hospital_id=_str(j, "hospital_id"),
            coordinator_id=_str(j, "coordinator_id"),
            gp_contacted_coordinator=_opt_date(j, "gp_contacted_coordinator"),
            accepted=_opt_date(j, "accepted"),
            ct_ordered=_opt_date(j, "ct_ordered"),
            ct_done=_opt_date(j, "ct_done"),
            biopsy_ordered=_opt_date(j, "biopsy_ordered"),
            biopsy_done=_opt_date(j, "biopsy_done"),
            mdt=_opt_date(j, "mdt"),
            treatment_start=_opt_date(j, "treatment_start"),
            coordinator_minutes=minutes,
            steps=steps,
        )
        if journey.hospital_id not in hospital_ids or journey.coordinator_id not in coordinator_ids:
            raise CohortError(f"journey {journey.code!r} refers to an unknown hospital or coordinator")
        journeys.append(journey)
    as_of = datetime.fromisoformat(_str(raw, "as_of"))
    if as_of.tzinfo is None:
        raise CohortError("as_of must carry a UTC offset")
    capacity = raw.get("coordinator_capacity_minutes_per_week")
    if not isinstance(capacity, int) or capacity <= 0:
        raise CohortError("coordinator_capacity_minutes_per_week must be a positive integer")
    return Cohort(
        tag=_str(raw, "tag"),
        simulated=_bool(raw, "simulated"),
        as_of=as_of,
        capacity_minutes_per_week=capacity,
        hospitals=hospitals,
        coordinators=coordinators,
        price_list=items,
        price_list_note=_str(price, "note"),
        journeys=tuple(journeys),
    )


def load_cohort(path: Path = COHORT_PATH) -> Cohort:
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise CohortError("cohort must be a JSON object")
    return parse_cohort(raw)


# ---------------------------------------------------------------------------------------------------- computation


def interval(key: IntervalKey, start: date | None, end: date | None) -> Interval:
    if start is None and end is None:
        return Interval(key, None, None, None, IntervalStatus.NOT_STARTED)
    if end is None:
        return Interval(key, start, None, None, IntervalStatus.RUNNING)
    if start is None:
        return Interval(key, None, end, None, IntervalStatus.NOT_RECORDED)
    days = (end - start).days
    if days < 0:
        return Interval(key, start, end, None, IntervalStatus.INCONSISTENT)
    return Interval(key, start, end, days, IntervalStatus.MEASURED)


def journey_intervals(journey: Journey) -> tuple[Interval, ...]:
    return tuple(
        interval(key, journey.anchor(start), journey.anchor(end)) for key, (start, end) in INTERVAL_ANCHORS.items()
    )


def journey_milestones(journey: Journey) -> tuple[Milestone, ...]:
    result: list[Milestone] = []
    previous: date | None = None
    for index, key in enumerate(MILESTONE_ORDER):
        current = journey.anchor(key.value)
        gap: int | None = None
        if index > 0 and previous is not None and current is not None and current >= previous:
            gap = (current - previous).days
        result.append(Milestone(key, current, gap))
        previous = current
    return tuple(result)


def journey_cost(journey: Journey, prices: Mapping[str, int]) -> int:
    return sum(prices[code] for code in journey.steps)


def _median(values: Iterable[float | int | None]) -> float | None:
    present = [float(v) for v in values if v is not None]
    return float(median(present)) if present else None


def inverted_min_max(value: float | None, values: Sequence[float | None]) -> float | None:
    """1 for the lowest value, 0 for the highest; 1 for everyone when all are equal; None when `value` is None."""
    present = [v for v in values if v is not None]
    if value is None or not present:
        return None
    low, high = min(present), max(present)
    if high == low:
        return 1.0
    return (high - value) / (high - low)


def operational_indicator(speed: float | None, cost: float | None, target_share: float | None) -> float | None:
    if speed is None or cost is None or target_share is None:
        return None
    return round(100 * (WEIGHT_SPEED * speed + WEIGHT_COST * cost + WEIGHT_TARGET * target_share), 1)


def competition_ranks(values: Mapping[str, float | None], *, descending: bool) -> dict[str, int | None]:
    """Standard competition ranking (1, 1, 3): equal values share a rank; None is unranked."""
    present = [v for v in values.values() if v is not None]
    ranks: dict[str, int | None] = {}
    for key, value in values.items():
        if value is None:
            ranks[key] = None
            continue
        better = sum(1 for other in present if (other > value if descending else other < value))
        ranks[key] = better + 1
    return ranks


def _ordered(values: Mapping[str, float | None], names: Mapping[str, str], *, descending: bool) -> tuple[str, ...]:
    ranked = [k for k, v in values.items() if v is not None]
    ranked.sort(key=lambda k: names[k])  # ties: by name, stable
    ranked.sort(key=lambda k: values[k] or 0.0, reverse=descending)
    return tuple(ranked)


def _within_target(result_days: Mapping[IntervalKey, int | None]) -> bool | None:
    ct = result_days[IntervalKey.CT_ORDER_TO_CT]
    biopsy = result_days[IntervalKey.BIOPSY_ORDER_TO_BIOPSY]
    if ct is None or biopsy is None:
        return None
    return ct <= TARGET_CT_DAYS and biopsy <= TARGET_BIOPSY_DAYS


def _utilisation(minutes: int, coordinators: int, capacity_per_week: int, weeks: float) -> float | None:
    capacity = coordinators * capacity_per_week * weeks
    if capacity <= 0:
        return None
    return round(100 * minutes / capacity, 1)


def compute(cohort: Cohort) -> Analytics:
    prices = {item.code: item.price_czk for item in cohort.price_list}
    hospital_names = {h.id: h.name for h in cohort.hospitals}
    coordinator_names = {c.id: c.display for c in cohort.coordinators}

    results: list[JourneyResult] = []
    for journey in cohort.journeys:
        intervals = journey_intervals(journey)
        days = {i.key: i.days for i in intervals}
        results.append(
            JourneyResult(
                journey=journey,
                hospital_name=hospital_names[journey.hospital_id],
                coordinator_display=coordinator_names[journey.coordinator_id],
                milestones=journey_milestones(journey),
                intervals=intervals,
                cost_czk=journey_cost(journey, prices),
                within_target=_within_target(days),
            )
        )
    # the real demo case first, then the simulated ones by code
    results.sort(key=lambda r: (r.journey.simulated, r.journey.code))

    all_dates = [d for j in cohort.journeys for f in DATE_FIELDS if (d := j.anchor(f)) is not None]
    period_start = min(all_dates) if all_dates else cohort.as_of.astimezone(TZ).date()
    period_end = max(all_dates) if all_dates else period_start
    weeks = round(((period_end - period_start).days + 1) / 7, 2)

    per_hospital: dict[str, list[JourneyResult]] = {h.id: [] for h in cohort.hospitals}
    for result in results:
        per_hospital[result.journey.hospital_id].append(result)

    speed_metric = {
        h.id: _median(r.days(IntervalKey.CONTACT_TO_MDT) for r in per_hospital[h.id]) for h in cohort.hospitals
    }
    cost_metric = {h.id: _median(r.cost_czk for r in per_hospital[h.id]) for h in cohort.hospitals}
    target_share: dict[str, float | None] = {}
    for h in cohort.hospitals:
        judged = [r.within_target for r in per_hospital[h.id] if r.within_target is not None]
        target_share[h.id] = round(sum(judged) / len(judged), 3) if judged else None

    speed_values = list(speed_metric.values())
    cost_values = list(cost_metric.values())
    indicator: dict[str, float | None] = {}
    speed_scores: dict[str, float | None] = {}
    cost_scores: dict[str, float | None] = {}
    for h in cohort.hospitals:
        speed_scores[h.id] = inverted_min_max(speed_metric[h.id], speed_values)
        cost_scores[h.id] = inverted_min_max(cost_metric[h.id], cost_values)
        indicator[h.id] = operational_indicator(speed_scores[h.id], cost_scores[h.id], target_share[h.id])
    ranks = competition_ranks(indicator, descending=True)
    fastest_value = min((v for v in speed_values if v is not None), default=None)
    cheapest_value = min((v for v in cost_values if v is not None), default=None)

    hospitals: list[HospitalStats] = []
    for h in cohort.hospitals:
        rows = per_hospital[h.id]
        staff = [c for c in cohort.coordinators if c.hospital_id == h.id]
        minutes_total = sum(r.journey.coordinator_minutes or 0 for r in rows)
        hospitals.append(
            HospitalStats(
                hospital=h,
                cases=len(rows),
                median_days={key: _median(r.days(key) for r in rows) for key in IntervalKey},
                median_cost_czk=cost_metric[h.id],
                median_coordinator_minutes=_median(r.journey.coordinator_minutes for r in rows),
                coordinator_minutes_total=minutes_total,
                coordinators=len(staff),
                utilisation_pct=_utilisation(minutes_total, len(staff), cohort.capacity_minutes_per_week, weeks),
                within_target_share=target_share[h.id],
                speed_score=None if speed_scores[h.id] is None else round(speed_scores[h.id] or 0.0, 3),
                cost_score=None if cost_scores[h.id] is None else round(cost_scores[h.id] or 0.0, 3),
                indicator=indicator[h.id],
                indicator_rank=ranks[h.id],
                fastest=fastest_value is not None and speed_metric[h.id] == fastest_value,
                lowest_cost=cheapest_value is not None and cost_metric[h.id] == cheapest_value,
            )
        )
    by_indicator = _ordered(indicator, hospital_names, descending=True)
    order = {hid: i for i, hid in enumerate(by_indicator)}
    hospitals.sort(key=lambda s: (order.get(s.hospital.id, len(order)), s.hospital.name))

    coordinators: list[CoordinatorStats] = []
    for c in cohort.coordinators:
        rows = [r for r in results if r.journey.coordinator_id == c.id]
        minutes_total = sum(r.journey.coordinator_minutes or 0 for r in rows)
        coordinators.append(
            CoordinatorStats(
                coordinator=c,
                hospital_name=hospital_names[c.hospital_id],
                cases=len(rows),
                median_minutes_per_patient=_median(r.journey.coordinator_minutes for r in rows),
                median_days_contact_to_accepted=_median(r.days(IntervalKey.CONTACT_TO_ACCEPTED) for r in rows),
                minutes_total=minutes_total,
                utilisation_pct=_utilisation(minutes_total, 1, cohort.capacity_minutes_per_week, weeks),
            )
        )
    coordinators.sort(key=lambda s: (order.get(s.coordinator.hospital_id, len(order)), s.coordinator.display))

    return Analytics(
        cohort=cohort,
        cohort_median_days={key: _median(r.days(key) for r in results) for key in IntervalKey},
        period_start=period_start,
        period_end=period_end,
        period_weeks=weeks,
        journeys=tuple(results),
        hospitals=tuple(hospitals),
        coordinators=tuple(coordinators),
        ranking_by_indicator=by_indicator,
        ranking_fastest=_ordered(speed_metric, hospital_names, descending=False),
        ranking_lowest_cost=_ordered(cost_metric, hospital_names, descending=False),
    )
