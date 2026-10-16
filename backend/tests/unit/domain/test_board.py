from datetime import date, datetime

import pytest

from app.domain import clock
from app.domain.board import (
    LANE_ORDER,
    AlertKind,
    BatonBasis,
    BatonReason,
    build_board,
    collect_alerts,
    critical_path_ids,
    lane_of,
)
from app.domain.common import PartyRef, Role
from app.domain.pathway import instantiate
from app.domain.task import Task, TaskBusinessStatus, TaskStatus

from .conftest import load_template, make_case

START = date(2026, 10, 2)
D2 = datetime(2026, 10, 2, 9, 0, tzinfo=clock.TZ)
D16 = datetime(2026, 10, 16, 9, 0, tzinfo=clock.TZ)


@pytest.fixture
def tasks() -> list[Task]:
    return instantiate(load_template(), make_case(), START)


def done(t: Task) -> Task:
    return t.model_copy(update={"status": TaskStatus.COMPLETED, "business_status": TaskBusinessStatus.VYSLEDEK_DORUCEN})


def complete(tasks: list[Task], *step_ids: str) -> list[Task]:
    ids = {f"c1.{s}" for s in step_ids}
    return [done(t) if t.id in ids else t for t in tasks]


def ordered(tasks: list[Task], *step_ids: str) -> list[Task]:
    """Place and date confirmed and accepted: the step's owner is to act."""
    ids = {f"c1.{s}" for s in step_ids}
    return [
        t.model_copy(update={"status": TaskStatus.ACCEPTED, "business_status": TaskBusinessStatus.POTVRZENO})
        if t.id in ids
        else t
        for t in tasks
    ]


def adhoc(**kw) -> Task:
    base = dict(
        id="c1.adhoc-1",
        case_id="c1",
        code="ad-hoc",
        title="Doplnit ECOG",
        status=TaskStatus.REQUESTED,
        business_status=TaskBusinessStatus.OBJEDNANO,
        owner_role=Role.KOC_PHYSICIAN,
        ad_hoc=True,
    )
    return Task(**{**base, **kw})


def test_critical_path_is_what_the_mdt_waits_for(tasks):
    assert critical_path_ids(tasks) == {"c1.ct", "c1.eus-fnb", "c1.labs", "c1.histology", "c1.mdt"}


def test_critical_path_without_mdt_step_is_every_pathway_step(tasks):
    no_mdt = [t for t in tasks if t.code != "mdt"] + [adhoc()]
    assert critical_path_ids(no_mdt) == {t.id for t in no_mdt if not t.ad_hoc}


def test_lanes_are_fixed_and_follow_the_owner_role(tasks):
    board = build_board("c1", tasks, D2)
    assert tuple(lane.role for lane in board.lanes) == LANE_ORDER
    lanes = {lane.role: [bt.task.id.split(".")[1] for bt in lane.tasks] for lane in board.lanes}
    assert lanes[Role.EXTERNAL_WORKPLACE] == ["ct", "labs", "histology"]
    assert lanes[Role.KOC_PHYSICIAN] == ["eus-fnb", "algesiology", "psychooncology", "mdt"]
    assert lanes[Role.COORDINATOR] == lanes[Role.GP] == lanes[Role.PATIENT] == []


def test_concrete_owner_decides_the_lane_and_staff_sits_with_physicians(tasks):
    ct = tasks[0].model_copy(update={"owner": PartyRef(id="fiala-daniel", display="MUDr. Fiala", role=Role.KOC_STAFF)})
    assert lane_of(ct) is Role.KOC_PHYSICIAN
    assert lane_of(tasks[0].model_copy(update={"owner_role": None})) is Role.COORDINATOR


def test_baton_starts_with_the_coordinator_ordering_ct_and_follows_the_path_to_the_mdt(tasks):
    baton = build_board("c1", tasks, D2).baton_holder
    assert baton is not None
    assert (baton.task_id, baton.role, baton.basis, baton.reason) == (
        "c1.ct",
        Role.COORDINATOR,
        BatonBasis.REQUIRED_FOR_MDT,
        BatonReason.AWAITING_CONFIRMATION,
    )
    assert baton.owner is None
    assert baton.demo_assumption is True

    at_workplace = build_board("c1", ordered(tasks, "ct"), D2).baton_holder
    assert at_workplace is not None
    assert (at_workplace.task_id, at_workplace.role, at_workplace.reason) == (
        "c1.ct",
        Role.EXTERNAL_WORKPLACE,
        BatonReason.ACTION,
    )

    after_ct = build_board("c1", complete(tasks, "ct"), D2).baton_holder
    assert after_ct is not None
    assert (after_ct.task_id, after_ct.role, after_ct.reason) == (
        "c1.eus-fnb",
        Role.COORDINATOR,
        BatonReason.AWAITING_CONFIRMATION,
    )
    eus_ordered = build_board("c1", ordered(complete(tasks, "ct"), "eus-fnb"), D2).baton_holder
    assert eus_ordered is not None
    assert (eus_ordered.task_id, eus_ordered.role) == ("c1.eus-fnb", Role.KOC_PHYSICIAN)

    after_labs = build_board("c1", complete(tasks, "ct", "eus-fnb", "labs"), D2).baton_holder
    assert after_labs is not None
    assert after_labs.task_id == "c1.histology"  # due 19. 10. beats the MDT on 21. 10.


def test_baton_prefers_a_concrete_owner_once_the_order_is_confirmed(tasks):
    owner = PartyRef(id="fiala-daniel", display="MUDr. Fiala", role=Role.EXTERNAL_WORKPLACE)
    tasks[0] = tasks[0].model_copy(update={"owner": owner})
    unordered = build_board("c1", tasks, D2).baton_holder
    assert unordered is not None
    assert (unordered.role, unordered.owner) == (Role.COORDINATOR, None)  # the coordinator confirms first
    baton = build_board("c1", ordered(tasks, tasks[0].id.split(".")[1]), D2).baton_holder
    assert baton is not None
    assert baton.owner == owner


def test_baton_skips_steps_that_still_wait_for_prerequisites(tasks):
    by_code = {t.code: i for i, t in enumerate(tasks)}
    ct = by_code["ct-thorax-abdomen"]
    tasks[ct] = tasks[ct].model_copy(update={"due": datetime(2026, 10, 30, tzinfo=clock.TZ)})
    baton = build_board("c1", tasks, D2).baton_holder  # EUS-FNB is due first but cannot start before CT
    assert baton is not None
    assert baton.task_id == "c1.ct"


def test_baton_goes_to_the_coordinator_when_a_prerequisite_failed_or_was_cancelled(tasks):
    for status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
        broken = [t.model_copy(update={"status": status}) if t.id == "c1.ct" else t for t in tasks]
        baton = build_board("c1", broken, D2).baton_holder
        assert baton is not None
        assert (baton.task_id, baton.role, baton.reason) == (
            "c1.eus-fnb",
            Role.COORDINATOR,
            BatonReason.DEPENDENCY_FAILED,
        )


def test_baton_falls_back_to_other_pathway_steps_then_ad_hoc_then_none(tasks):
    crit = complete(tasks, "ct", "eus-fnb", "labs", "histology", "mdt")
    other = build_board("c1", ordered(crit, "algesiology"), D2).baton_holder
    assert other is not None
    assert (other.task_id, other.basis, other.role) == ("c1.algesiology", BatonBasis.OTHER_PATHWAY, Role.KOC_PHYSICIAN)
    pathway_done = complete(tasks, "ct", "eus-fnb", "labs", "histology", "mdt", "algesiology", "psychooncology")
    single = build_board("c1", [*pathway_done, adhoc()], D2).baton_holder
    assert single is not None
    assert (single.task_id, single.basis, single.role) == ("c1.adhoc-1", BatonBasis.AD_HOC, Role.COORDINATOR)
    assert single.demo_assumption is False
    assert build_board("c1", pathway_done, D2).baton_holder is None


def test_open_ad_hoc_task_never_takes_the_baton_from_the_critical_path(tasks):
    baton = build_board("c1", [*tasks, adhoc(due=datetime(2026, 10, 3, tzinfo=clock.TZ))], D2).baton_holder
    assert baton is not None
    assert baton.task_id == "c1.ct"


def test_blocked_by_lists_unfinished_dependencies(tasks):
    by_id = {bt.task.id: bt for lane in build_board("c1", tasks, D2).lanes for bt in lane.tasks}
    assert by_id["c1.ct"].blocked_by == ()
    assert by_id["c1.mdt"].blocked_by == ("c1.ct", "c1.histology", "c1.labs")
    after_ct = {bt.task.id: bt for lane in build_board("c1", complete(tasks, "ct"), D2).lanes for bt in lane.tasks}
    assert after_ct["c1.eus-fnb"].blocked_by == ()
    assert after_ct["c1.ct"].blocked_by == ()  # finished tasks are never "blocked"


def test_overdue_flag_follows_the_effective_deadline(tasks):
    def overdue(now):
        return {bt.task.id for lane in build_board("c1", tasks, now).lanes for bt in lane.tasks if bt.overdue}

    assert overdue(D2) == set()
    assert overdue(datetime(2026, 10, 9, 9, 0, tzinfo=clock.TZ)) == {"c1.ct"}  # due Thu 8. 10.
    assert "c1.histology" in overdue(D16)  # SLA 15. 10. is earlier than due 19. 10.


def test_alerts_on_16_october_escalate_histology_on_its_sla(tasks):
    assert collect_alerts(tasks, D2) == []
    by_id = {a.task_id: a for a in collect_alerts(tasks, D16)}
    hist = by_id["c1.histology"]
    assert (hist.kind, hist.basis, hist.deadline, hist.overdue_workdays) == (
        AlertKind.SLA_BREACH,
        "sla",
        date(2026, 10, 15),
        1,
    )
    assert hist.recipients == (Role.COORDINATOR,)
    assert by_id["c1.ct"].kind is AlertKind.OVERDUE  # due 8. 10., nothing done in this scenario


def test_alerts_include_already_escalated_tasks_but_not_finished_ones(tasks):
    tasks = [t.model_copy(update={"escalated_at": D16}) if t.code == "histology" else t for t in tasks]
    tasks = complete(tasks, "ct")
    ids = {a.task_id for a in collect_alerts(tasks, D16)}
    assert "c1.histology" in ids
    assert "c1.ct" not in ids
