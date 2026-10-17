import dataclasses
from datetime import date

import pytest

from app.domain import clock
from app.domain.case import CaseState
from app.domain.common import Role
from app.domain.pathway import PathwayTemplate, Waiver, instantiate, readiness_gate
from app.domain.task_machine import check_overdue, escalate_if_overdue
from tests.unit.domain.conftest import load_plan, load_template, make_case

START = date(2026, 10, 2)
CASE = make_case(CaseState.TRIAGE)


@pytest.fixture(scope="module")
def plan() -> PathwayTemplate:
    return load_template()


@pytest.fixture(scope="module")
def tasks(plan):
    return {t.id.split(".")[1]: t for t in instantiate(plan, CASE, START)}


def test_demo_story_dates(tasks):
    assert tasks["ct"].due.date() == date(2026, 10, 8)
    assert tasks["eus-fnb"].due.date() == date(2026, 10, 12)
    assert tasks["labs"].due.date() == date(2026, 10, 15)
    assert tasks["histology"].due.date() == date(2026, 10, 19)
    assert tasks["mdt"].due.date() == date(2026, 10, 21)
    assert tasks["algesiology"].due.date() == date(2026, 10, 26)
    assert tasks["psychooncology"].due.date() == date(2026, 10, 27)


def test_places_owners_and_labels(tasks):
    assert "KOC 1" in tasks["ct"].location
    assert "KOC 2" in tasks["eus-fnb"].location
    assert tasks["mdt"].owner_role is Role.KOC_PHYSICIAN
    assert {k: t.owner_role for k, t in tasks.items()} == {
        "ct": Role.EXTERNAL_WORKPLACE,
        "labs": Role.EXTERNAL_WORKPLACE,
        "histology": Role.EXTERNAL_WORKPLACE,
        "eus-fnb": Role.KOC_PHYSICIAN,
        "algesiology": Role.KOC_PHYSICIAN,
        "psychooncology": Role.KOC_PHYSICIAN,
        "mdt": Role.KOC_PHYSICIAN,
    }
    assert all(t.demo_assumption for t in tasks.values())


def test_dependencies_and_order(plan):
    ordered = instantiate(plan, CASE, START)
    pos = {t.id: i for i, t in enumerate(ordered)}
    assert all(pos[d] < pos[t.id] for t in ordered for d in t.depends_on)
    deps = {t.id.split(".")[1]: {d.split(".")[1] for d in t.depends_on} for t in ordered}
    assert deps["eus-fnb"] == {"ct"}
    assert deps["histology"] == {"eus-fnb"}
    assert deps["mdt"] == {"ct", "histology", "labs"}
    assert "mdt" not in {d for v in deps.values() for d in v}  # nothing waits for the MDT


def test_plan_labels_demo_assumptions():
    raw = load_plan()
    assert "DEMO ASSUMPTION" in raw["description"]
    assert all("DEMO ASSUMPTION" in a["description"] for a in raw["action"])
    assert raw["resourceType"] == "PlanDefinition"
    assert raw["status"] == "draft"


def test_histology_sla_resolves_thursday_and_escalates_on_friday(tasks):
    h = tasks["histology"]
    assert clock.add_workdays(date(2026, 10, 12), 3) == date(2026, 10, 15)
    assert h.sla_due.date() == date(2026, 10, 15)
    assert h.sla_due.weekday() == 3
    with clock.frozen("2026-10-15T23:59:00+02:00"):
        assert check_overdue(h) == []
    with clock.frozen("2026-10-16T09:00:00+02:00"):
        res = escalate_if_overdue(h)
    (ev,) = res.events
    assert ev.recipients == (Role.COORDINATOR,)
    assert ev.payload["basis"] == "sla"
    assert ev.at.date() == date(2026, 10, 16)


def test_cycle_and_unknown_reference_rejected(plan):
    steps = list(plan.steps)
    ct = steps[0]
    assert ct.id == "ct"
    cyclic = dataclasses.replace(plan, steps=(dataclasses.replace(ct, after=("mdt",)), *steps[1:]))
    with pytest.raises(ValueError, match="cycle"):
        instantiate(cyclic, CASE, START)
    unknown = dataclasses.replace(plan, steps=(dataclasses.replace(ct, after=("nope",)), *steps[1:]))
    with pytest.raises(ValueError, match="unknown"):
        instantiate(unknown, CASE, START)


def test_mdt_anchor_needs_case_mdt_start(plan):
    with pytest.raises(ValueError, match="mdt_start"):
        instantiate(plan, make_case(CaseState.TRIAGE, mdt_start=None), START)


# --- readiness ---------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def required(plan):
    return list(plan.mdt_required_items)


def statuses(required, **over):
    return {i: "complete" for i in required} | over


def test_required_items(required):
    assert required == ["histology", "ct_staging", "tumour_markers", "comorbidities",
                        "performance_status", "mdt_question"]  # fmt: skip


def test_all_complete_is_ready(required):
    g = readiness_gate(statuses(required), required)
    assert g.ready
    assert g.missing == ()
    assert g.waived == ()
    assert g.warnings == ()


def test_demo_case_ecog_missing_blocks(required):
    g = readiness_gate(statuses(required, performance_status="missing"), required)
    assert not g.ready
    assert g.missing == ("performance_status",)


def test_absent_item_counts_as_missing(required):
    s = statuses(required)
    del s["histology"]
    assert readiness_gate(s, required).missing == ("histology",)


def test_physician_waiver_makes_ready_and_is_listed(required):
    w = Waiver("performance_status", Role.KOC_PHYSICIAN, "u1", "ECOG bude doplněn na jednání")
    g = readiness_gate(statuses(required, performance_status="missing"), required, [w])
    assert g.ready
    assert g.missing == ()
    assert g.waived == (w,)


@pytest.mark.parametrize(
    "waiver",
    [
        Waiver("performance_status", Role.KOC_PHYSICIAN, "", "důvod"),
        Waiver("performance_status", Role.KOC_PHYSICIAN, "  ", "důvod"),
        Waiver("performance_status", Role.COORDINATOR, "u2", "důvod"),
        Waiver("performance_status", Role.KOC_PHYSICIAN, "u1", "  "),
        Waiver("nonsense", Role.KOC_PHYSICIAN, "u1", "důvod"),
    ],
)
def test_invalid_waivers_raise(required, waiver):
    with pytest.raises(ValueError, match="romin"):
        readiness_gate(statuses(required, performance_status="missing"), required, [waiver])


def test_conflict_and_stale_are_warnings_not_blockers(required):
    g = readiness_gate(
        statuses(required, histology="complete_with_conflict", comorbidities="stale",
                 mdt_question="needs_clarification"), required)  # fmt: skip
    assert g.ready
    assert set(g.warnings) == {"histology", "comorbidities", "mdt_question"}


def test_waiver_for_non_blocking_item_is_ignored(required):
    w = Waiver("histology", Role.KOC_PHYSICIAN, "u1", "důvod")
    assert readiness_gate(statuses(required), required, [w]).waived == ()
