"""Insurer analytics schemas (GET /api/insurer/analytics): a simulated cohort, aggregated per hospital and coordinator.

Every number comes from `app.timeline.insurer_analytics`; the UI renders them and never recomputes an indicator.
`days` is null whenever an anchor was not recorded: nothing is estimated.
"""

from __future__ import annotations

from datetime import date, datetime
from datetime import date as calendar_date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.config import JsonDict

IntervalKeyOut = Literal[
    "contact_to_accepted",
    "ct_order_to_ct",
    "biopsy_order_to_biopsy",
    "contact_to_mdt",
    "mdt_to_treatment",
    "contact_to_treatment",
]
IntervalStatusOut = Literal["measured", "running", "not_started", "not_recorded", "inconsistent"]
MilestoneKeyOut = Literal["gp_contacted_coordinator", "accepted", "ct_done", "biopsy_done", "mdt", "treatment_start"]
HospitalBadge = Literal["fastest", "lowest_cost"]

_HOSPITAL_EXAMPLE: JsonDict = {
    "id": "koc3-nemocnice-vychodni-sim",
    "name": "KOC 3 – Nemocnice Východní (simulace)",
    "simulated": True,
    "cases": 6,
    "median_days": {
        "contact_to_accepted": 0.0,
        "ct_order_to_ct": 2.5,
        "biopsy_order_to_biopsy": 5.0,
        "contact_to_mdt": 11.5,
        "mdt_to_treatment": 9.0,
        "contact_to_treatment": 20.0,
    },
    "median_cost_czk": 27850.0,
    "median_coordinator_minutes": 132.5,
    "coordinators": 1,
    "coordinator_minutes_total": 795,
    "utilisation_pct": 32.7,
    "within_target_share": 1.0,
    "speed_score": 1.0,
    "cost_score": 1.0,
    "indicator": 100.0,
    "indicator_rank": 1,
    "badges": ["fastest", "lowest_cost"],
}
_JOURNEY_EXAMPLE: JsonDict = {
    "code": "rakathon-2026-prochazkova",
    "simulated": False,
    "hospital_id": "koc2-nemocnice-lipova",
    "hospital_name": "KOC 2 – Nemocnice Lipová",
    "coordinator_display": "Bc. Lucie Dvořáková",
    "milestones": [
        {"key": "gp_contacted_coordinator", "date": "2026-10-02", "days_since_previous": None},
        {"key": "accepted", "date": None, "days_since_previous": None},
        {"key": "ct_done", "date": "2026-10-08", "days_since_previous": None},
        {"key": "biopsy_done", "date": "2026-10-12", "days_since_previous": 4},
        {"key": "mdt", "date": "2026-10-21", "days_since_previous": 9},
        {"key": "treatment_start", "date": None, "days_since_previous": None},
    ],
    "intervals": [
        {"key": "ct_order_to_ct", "start": "2026-10-02", "end": "2026-10-08", "days": 6, "status": "measured"},
        {"key": "mdt_to_treatment", "start": "2026-10-21", "end": None, "days": None, "status": "running"},
    ],
    "cost_czk": 27850,
    "coordinator_minutes": None,
    "within_target": True,
}


class InsurerIntervalMedians(BaseModel):
    """Median whole Europe/Prague calendar days over the journeys where the interval was measured; null = none."""

    contact_to_accepted: float | None = Field(description="GP contacted the coordinator -> coordinator accepted.")
    ct_order_to_ct: float | None = Field(description="CT ordered -> CT performed.")
    biopsy_order_to_biopsy: float | None = Field(description="Biopsy ordered -> biopsy performed.")
    contact_to_mdt: float | None = Field(description="GP contacted the coordinator -> MDT.")
    mdt_to_treatment: float | None = Field(description="MDT -> treatment start (only where a start is recorded).")
    contact_to_treatment: float | None = Field(description="GP contacted the coordinator -> treatment start.")


class HospitalAnalytics(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_HOSPITAL_EXAMPLE]})

    id: str
    name: str
    simulated: bool = Field(description="True for a hospital invented only for this cohort.")
    cases: int
    median_days: InsurerIntervalMedians
    median_cost_czk: float | None = Field(description="Median illustrative cost per case (CZK), from `price_list`.")
    median_coordinator_minutes: float | None = Field(description="Median coordinator minutes per patient.")
    coordinators: int
    coordinator_minutes_total: int = Field(description="Sum of recorded coordinator minutes (unrecorded = 0).")
    utilisation_pct: float | None = Field(
        description="Coordinator minutes / (coordinators × assumed capacity per week × weeks of the period), in %."
    )
    within_target_share: float | None = Field(
        description="0–1 share of journeys within both demo targets, over journeys where both waits were measured."
    )
    speed_score: float | None = Field(description="0–1 inverted min-max of the median contact -> MDT.")
    cost_score: float | None = Field(description="0–1 inverted min-max of the median cost per case.")
    indicator: float | None = Field(
        description="0–100 operational indicator (speed, illustrative cost, share within demo targets; see "
        "`assumptions.formula`); not a measure of quality of care."
    )
    indicator_rank: int | None = Field(description="1 = highest indicator; equal values share a rank.")
    badges: list[HospitalBadge] = Field(description="fastest = lowest median contact -> MDT; lowest_cost.")


class CoordinatorAnalytics(BaseModel):
    id: str
    display: str = Field(description="Staff name (fictitious); '(simulace)' marks a simulated coordinator.")
    simulated: bool
    hospital_id: str
    hospital_name: str
    cases: int
    median_minutes_per_patient: float | None
    median_days_contact_to_accepted: float | None
    minutes_total: int
    utilisation_pct: float | None = Field(description="Minutes / (assumed capacity per week × weeks), in %.")


class InsurerMilestone(BaseModel):
    key: MilestoneKeyOut
    date: calendar_date | None = Field(description="Prague calendar date; null = not recorded, never estimated.")
    days_since_previous: int | None = Field(
        description="Days since the previous milestone in the list; null when either is not recorded."
    )


class InsurerInterval(BaseModel):
    key: IntervalKeyOut
    start: date | None
    end: date | None
    days: int | None = Field(description="Whole Europe/Prague calendar days; null unless `status` = measured.")
    status: IntervalStatusOut


class JourneyAnalytics(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_JOURNEY_EXAMPLE]})

    code: str = Field(description="Pseudonymous case code (SIM-…) or the demo case id; no patient identifiers.")
    simulated: bool
    hospital_id: str
    hospital_name: str
    coordinator_display: str
    milestones: list[InsurerMilestone] = Field(
        description="In pathway order: contact, accepted, CT, biopsy, MDT, start."
    )
    intervals: list[InsurerInterval]
    cost_czk: int = Field(description="Illustrative cost of the recorded steps (CZK).")
    coordinator_minutes: int | None
    within_target: bool | None = Field(description="Both demo targets met; null when a wait was not measured.")


class InsurerWeights(BaseModel):
    speed: float
    cost: float
    target_share: float


class InsurerTargets(BaseModel):
    ct_order_to_ct_max_days: int
    biopsy_order_to_biopsy_max_days: int
    note: str


class InsurerCapacity(BaseModel):
    minutes_per_week: int = Field(description="Assumed coordinator time per week for the cases of this cohort.")
    period_start: date
    period_end: date
    weeks: float
    note: str


class InsurerPriceItem(BaseModel):
    code: str
    label: str
    price_czk: int


class InsurerAssumptions(BaseModel):
    capacity: InsurerCapacity
    targets: InsurerTargets
    weights: InsurerWeights
    speed_metric: IntervalKeyOut
    formula: str = Field(description="The indicator formula in Czech, for display.")
    price_list_note: str
    price_list: list[InsurerPriceItem]


class InsurerRankings(BaseModel):
    by_indicator: list[str] = Field(description="Hospital ids, highest indicator first; ties by name.")
    fastest: list[str] = Field(description="Hospital ids, lowest median contact -> MDT first.")
    lowest_cost: list[str] = Field(description="Hospital ids, lowest median cost per case first.")


class InsurerSummary(BaseModel):
    cases: int = Field(description="Journeys in the cohort, the demo case included.")
    simulated_cases: int
    median_days: InsurerIntervalMedians = Field(description="Medians over every journey of the cohort.")


class InsurerAnalytics(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "simulated": True,
                    "disclaimer": "Simulovaná data – fiktivní kohorta pro demo, ilustrativní ceník.",
                    "as_of": "2026-10-21T08:00:00+02:00",
                    "assumptions": {
                        "capacity": {
                            "minutes_per_week": 120,
                            "period_start": "2026-06-02",
                            "period_end": "2026-10-21",
                            "weeks": 20.29,
                            "note": "Předpoklad pro demo.",
                        },
                        "targets": {
                            "ct_order_to_ct_max_days": 7,
                            "biopsy_order_to_biopsy_max_days": 10,
                            "note": "Předpoklad pro demo.",
                        },
                        "weights": {"speed": 0.5, "cost": 0.3, "target_share": 0.2},
                        "speed_metric": "contact_to_mdt",
                        "formula": "Indikátor = 100 × (0,5 × rychlost + 0,3 × náklady + 0,2 × podíl v cíli)",
                        "price_list_note": "Ilustrativní ceník pro demo.",
                        "price_list": [{"code": "MDT", "label": "Projednání v MDT", "price_czk": 1600}],
                    },
                    "hospitals": [_HOSPITAL_EXAMPLE],
                    "coordinators": [],
                    "journeys": [_JOURNEY_EXAMPLE],
                    "summary": {
                        "cases": 24,
                        "simulated_cases": 23,
                        "median_days": {
                            "contact_to_accepted": 1.0,
                            "ct_order_to_ct": 5.0,
                            "biopsy_order_to_biopsy": 8.0,
                            "contact_to_mdt": 18.0,
                            "mdt_to_treatment": 13.0,
                            "contact_to_treatment": 28.5,
                        },
                    },
                    "rankings": {
                        "by_indicator": ["koc3-nemocnice-vychodni-sim"],
                        "fastest": ["koc3-nemocnice-vychodni-sim"],
                        "lowest_cost": ["koc3-nemocnice-vychodni-sim"],
                    },
                }
            ]
        }
    )

    simulated: bool = Field(description="Always true: the cohort is fictitious (only the demo case is not simulated).")
    disclaimer: str = Field(description="Czech notice the UI must show with the data.")
    as_of: datetime = Field(description="Snapshot time of the cohort.")
    assumptions: InsurerAssumptions
    hospitals: list[HospitalAnalytics] = Field(description="Ordered by `rankings.by_indicator`.")
    coordinators: list[CoordinatorAnalytics]
    journeys: list[JourneyAnalytics] = Field(description="The demo case first, then simulated journeys by code.")
    rankings: InsurerRankings
    summary: InsurerSummary
