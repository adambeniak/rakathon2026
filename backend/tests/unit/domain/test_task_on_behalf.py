from datetime import date, datetime

import pytest

from app.domain import clock
from app.domain.common import PartyRef, Role
from app.domain.events import TransitionError
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.domain.task_machine import TaskContext, check_overdue, overdue_info, transition

R = Role
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=clock.TZ)
CTX = TaskContext(
    place="KOC 1", scheduled_at=NOW, result_doc_id="doc-9", reason="důvod", completed_task_ids=frozenset()
)


def ext_task(status: TaskStatus, business: TaskBusinessStatus, role: Role = R.EXTERNAL_WORKPLACE, **kw) -> Task:
    return Task(
        id="c1.ct",
        case_id="c1",
        code="ct-thorax-abdomen",
        title="CT",
        status=status,
        business_status=business,
        owner_role=role,
        location="KOC 1",
        **kw,
    )


CASES = [
    ("start", TaskStatus.ACCEPTED, TaskBusinessStatus.POTVRZENO),
    ("performed", TaskStatus.IN_PROGRESS, TaskBusinessStatus.POTVRZENO),
    ("result_delivered", TaskStatus.IN_PROGRESS, TaskBusinessStatus.PROVEDENO),
]


@pytest.mark.parametrize(("event", "status", "business"), CASES)
def test_coordinator_records_for_an_external_workplace(event, status, business):
    res = transition(ext_task(status, business), event, R.COORDINATOR, CTX, NOW)
    assert res.on_behalf is True
    audit = res.events[0]
    assert audit.payload["actor_role"] == "coordinator"
    assert audit.payload["on_behalf_of_role"] == "external_workplace"


@pytest.mark.parametrize(("event", "status", "business"), CASES)
def test_workplace_itself_is_not_on_behalf(event, status, business):
    res = transition(ext_task(status, business), event, R.EXTERNAL_WORKPLACE, CTX, NOW)
    assert res.on_behalf is False
    assert "on_behalf_of_role" not in res.events[0].payload


@pytest.mark.parametrize(("event", "status", "business"), CASES)
def test_coordinator_may_not_record_for_a_physician(event, status, business):
    with pytest.raises(TransitionError) as e:
        transition(ext_task(status, business, role=R.KOC_PHYSICIAN), event, R.COORDINATOR, CTX, NOW)
    assert e.value.code == "forbidden_role"


@pytest.mark.parametrize(("event", "status", "business"), CASES)
@pytest.mark.parametrize("actor", [R.GP, R.KOC_PHYSICIAN, R.PATIENT, R.REVIEWER])
def test_nobody_else_acts_for_an_external_workplace(event, status, business, actor):
    with pytest.raises(TransitionError) as e:
        transition(ext_task(status, business), event, actor, CTX, NOW)
    assert e.value.code == "forbidden_role"


def test_a_concrete_owner_decides_whose_behalf():
    owner = PartyRef(id="fiala-daniel", display="MUDr. Fiala", role=R.KOC_PHYSICIAN)
    t = ext_task(TaskStatus.ACCEPTED, TaskBusinessStatus.POTVRZENO, owner=owner)
    with pytest.raises(TransitionError):
        transition(t, "start", R.COORDINATOR, CTX, NOW)


def test_guards_still_apply_on_behalf():
    t = ext_task(TaskStatus.ACCEPTED, TaskBusinessStatus.POTVRZENO, depends_on=["c1.prev"])
    with pytest.raises(TransitionError) as e:
        transition(t, "start", R.COORDINATOR, CTX, NOW)
    assert e.value.code == "guard_failed"


def test_overdue_info_ignores_escalation_stamp_and_closed_tasks():
    due = datetime(2026, 10, 15, 23, 59, 59, tzinfo=clock.TZ)
    open_t = ext_task(TaskStatus.REQUESTED, TaskBusinessStatus.OBJEDNANO, due=due)
    friday = datetime(2026, 10, 16, 9, 0, tzinfo=clock.TZ)
    info = overdue_info(open_t, friday)
    assert info is not None
    assert (info.deadline, info.basis, info.overdue_workdays) == (date(2026, 10, 15), "due", 1)
    stamped = open_t.model_copy(update={"escalated_at": friday})
    assert overdue_info(stamped, friday) == info
    assert check_overdue(stamped, friday) == []
    assert overdue_info(open_t.model_copy(update={"status": TaskStatus.COMPLETED}), friday) is None
    assert overdue_info(open_t, datetime(2026, 10, 15, 23, 0, tzinfo=clock.TZ)) is None
