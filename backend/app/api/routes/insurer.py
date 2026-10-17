"""GET /api/insurer/analytics: the insurer reviewer's view of care durations, order-to-exam delays, coordinator load
and a transparent operational indicator (not a measure of quality of care), over a FICTITIOUS cohort
(ADR `docs/adr/XXXX-insurer-analytics.md`).

Fixture-only: no FHIR read, so no clinical content is read and no AuditEvent is written. Reviewer role only.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache

from fastapi import APIRouter

from app.api.deps import ActorDep
from app.api.schemas.common import problem_responses
from app.api.schemas.insurer import (
    CoordinatorAnalytics,
    HospitalAnalytics,
    HospitalBadge,
    InsurerAnalytics,
    InsurerAssumptions,
    InsurerCapacity,
    InsurerInterval,
    InsurerIntervalMedians,
    InsurerMilestone,
    InsurerPriceItem,
    InsurerRankings,
    InsurerSummary,
    InsurerTargets,
    InsurerWeights,
    JourneyAnalytics,
)
from app.domain.common import Role
from app.domain.errors import ForbiddenError
from app.timeline import insurer_analytics as ia

router = APIRouter(prefix="/insurer", tags=["insurer"])

DISCLAIMER = (
    "Simulovaná data – fiktivní kohorta pro demo, ilustrativní ceník. Nejde o skutečné úhrady ani hodnocení "
    "kvality péče. Všechny nemocnice, koordinátoři a cesty jsou smyšlené; KOC 1 a KOC 2 jsou fiktivní pracoviště "
    "demo případu, jejich údaje jsou převážně simulované. U demo případu je datum objednání CT a biopsie převzato "
    "z data žádosti praktického lékaře (předpoklad pro demo)."
)
DEMO_ASSUMPTION = "Předpoklad pro demo, ne klinický ani smluvní standard."
FORMULA = (
    "Provozní indikátor (0–100) = 100 × (0,5 × rychlost + 0,3 × náklady + 0,2 × podíl případů v cílových lhůtách). "
    "Rychlost a náklady jsou min-max škály mezi nemocnicemi kohorty (nejkratší medián kontakt PL → MDT = 1, "
    "nejnižší medián nákladů na případ = 1); při shodě všech nemocnic dostanou všechny 1."
)


@lru_cache(maxsize=1)
def _analytics() -> InsurerAnalytics:
    """The fixture never changes while the process runs: computed once."""
    return to_response(ia.compute(ia.load_cohort()))


def _medians(medians: Mapping[ia.IntervalKey, float | None]) -> InsurerIntervalMedians:
    return InsurerIntervalMedians(**{key.value: value for key, value in medians.items()})


def _badges(stats: ia.HospitalStats) -> list[HospitalBadge]:
    badges: list[HospitalBadge] = []
    if stats.fastest:
        badges.append("fastest")
    if stats.lowest_cost:
        badges.append("lowest_cost")
    return badges


def to_response(result: ia.Analytics) -> InsurerAnalytics:
    cohort = result.cohort
    return InsurerAnalytics(
        simulated=cohort.simulated,
        disclaimer=DISCLAIMER,
        as_of=cohort.as_of,
        assumptions=InsurerAssumptions(
            capacity=InsurerCapacity(
                minutes_per_week=cohort.capacity_minutes_per_week,
                period_start=result.period_start,
                period_end=result.period_end,
                weeks=result.period_weeks,
                note=f"Kapacita koordinátora pro případy této kohorty, {cohort.capacity_minutes_per_week} min "
                f"týdně. {DEMO_ASSUMPTION}",
            ),
            targets=InsurerTargets(
                ct_order_to_ct_max_days=ia.TARGET_CT_DAYS,
                biopsy_order_to_biopsy_max_days=ia.TARGET_BIOPSY_DAYS,
                note=DEMO_ASSUMPTION,
            ),
            weights=InsurerWeights(speed=ia.WEIGHT_SPEED, cost=ia.WEIGHT_COST, target_share=ia.WEIGHT_TARGET),
            speed_metric="contact_to_mdt",
            formula=FORMULA,
            price_list_note=cohort.price_list_note,
            price_list=[InsurerPriceItem(code=p.code, label=p.label, price_czk=p.price_czk) for p in cohort.price_list],
        ),
        hospitals=[
            HospitalAnalytics(
                id=s.hospital.id,
                name=s.hospital.name,
                simulated=s.hospital.simulated,
                cases=s.cases,
                median_days=_medians(s.median_days),
                median_cost_czk=s.median_cost_czk,
                median_coordinator_minutes=s.median_coordinator_minutes,
                coordinators=s.coordinators,
                coordinator_minutes_total=s.coordinator_minutes_total,
                utilisation_pct=s.utilisation_pct,
                within_target_share=s.within_target_share,
                speed_score=s.speed_score,
                cost_score=s.cost_score,
                indicator=s.indicator,
                indicator_rank=s.indicator_rank,
                badges=_badges(s),
            )
            for s in result.hospitals
        ],
        coordinators=[
            CoordinatorAnalytics(
                id=c.coordinator.id,
                display=c.coordinator.display,
                simulated=c.coordinator.simulated,
                hospital_id=c.coordinator.hospital_id,
                hospital_name=c.hospital_name,
                cases=c.cases,
                median_minutes_per_patient=c.median_minutes_per_patient,
                median_days_contact_to_accepted=c.median_days_contact_to_accepted,
                minutes_total=c.minutes_total,
                utilisation_pct=c.utilisation_pct,
            )
            for c in result.coordinators
        ],
        journeys=[
            JourneyAnalytics(
                code=j.journey.code,
                simulated=j.journey.simulated,
                hospital_id=j.journey.hospital_id,
                hospital_name=j.hospital_name,
                coordinator_display=j.coordinator_display,
                milestones=[
                    InsurerMilestone(key=m.key.value, date=m.date, days_since_previous=m.days_since_previous)
                    for m in j.milestones
                ],
                intervals=[
                    InsurerInterval(key=i.key.value, start=i.start, end=i.end, days=i.days, status=i.status.value)
                    for i in j.intervals
                ],
                cost_czk=j.cost_czk,
                coordinator_minutes=j.journey.coordinator_minutes,
                within_target=j.within_target,
            )
            for j in result.journeys
        ],
        summary=InsurerSummary(
            cases=len(result.journeys),
            simulated_cases=sum(1 for j in result.journeys if j.journey.simulated),
            median_days=_medians(result.cohort_median_days),
        ),
        rankings=InsurerRankings(
            by_indicator=list(result.ranking_by_indicator),
            fastest=list(result.ranking_fastest),
            lowest_cost=list(result.ranking_lowest_cost),
        ),
    )


@router.get(
    "/analytics",
    response_model=InsurerAnalytics,
    summary="Insurer analytics over a simulated cohort: care durations, exam delays, coordinator load, indicator",
    description="For the insurer's reviewer only. A FICTITIOUS cohort (pseudonymous codes, no patient identifiers) "
    "plus the demo case: per journey the milestone dates and the Europe/Prague calendar-day intervals between them "
    "(null when not recorded, never estimated); per hospital the medians, illustrative cost, coordinator "
    "utilisation and a 0–100 indicator; per coordinator the load. InsurerWeights, targets, capacity and the price list "
    "are returned as explicit demo assumptions. Fixture data only: no FHIR read, no AuditEvent.",
    responses=problem_responses(401, 403, 500),
)
async def get_insurer_analytics(actor: ActorDep) -> InsurerAnalytics:
    if actor.role is not Role.REVIEWER:
        raise ForbiddenError("Analytika péče je dostupná jen reviznímu lékaři zdravotní pojišťovny")
    return _analytics()
