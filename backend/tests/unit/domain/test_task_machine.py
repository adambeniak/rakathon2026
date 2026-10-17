from dataclasses import replace
from datetime import date, datetime

import pytest

from app.domain import clock
from app.domain.common import Role
from app.domain.events import EventKind, TransitionError
from app.domain.task import Task
from app.domain.task import TaskBusinessStatus as B
from app.domain.task import TaskStatus as T
from app.domain.task_machine import TASK_EVENTS, TaskContext, check_overdue, escalate_if_overdue, transition

R = Role
SLOT = datetime(2026, 10, 12, 9, 0, tzinfo=clock.TZ)
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=clock.TZ)
CTX = TaskContext(place="KOC 2", scheduled_at=SLOT, result_doc_id="doc-11", reason="důvod",
                  completed_task_ids=frozenset({"c1.ct"}))  # fmt: skip


def eod(d):
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=clock.TZ)


def task(status=T.REQUESTED, business=B.OBJEDNANO, **kw):
    for k in ("due", "sla_due"):
        if isinstance(kw.get(k), date):
            kw[k] = eod(kw[k])
    base = dict(id="c1.eus", case_id="c1", code="eus-fnb", title="EUS-FNB", owner_role=R.COORDINATOR,
                location="KOC 2", due=eod(date(2026, 10, 12)), depends_on=["c1.ct"])  # fmt: skip
    return Task(**{**base, **kw}, status=status, business_status=business)


# (event, from status, from business, roles allowed, to status, to business)
ALLOWED = [
    ("order_confirmed", T.REQUESTED, B.OBJEDNANO, {R.COORDINATOR}, T.REQUESTED, B.POTVRZENO),
    ("accept", T.REQUESTED, B.POTVRZENO, {R.COORDINATOR}, T.ACCEPTED, B.POTVRZENO),
    ("start", T.ACCEPTED, B.POTVRZENO, {R.COORDINATOR, R.SYSTEM}, T.IN_PROGRESS, B.POTVRZENO),
    ("performed", T.IN_PROGRESS, B.POTVRZENO, {R.COORDINATOR, R.SYSTEM}, T.IN_PROGRESS, B.PROVEDENO),
    ("result_delivered", T.IN_PROGRESS, B.PROVEDENO, {R.COORDINATOR, R.SYSTEM}, T.COMPLETED, B.VYSLEDEK_DORUCEN),
    ("fail", T.ACCEPTED, B.POTVRZENO, {R.COORDINATOR}, T.FAILED, B.POTVRZENO),
    ("fail", T.IN_PROGRESS, B.POTVRZENO, {R.COORDINATOR}, T.FAILED, B.POTVRZENO),
    ("cancel", T.REQUESTED, B.OBJEDNANO, {R.COORDINATOR}, T.CANCELLED, B.OBJEDNANO),
    ("cancel", T.ACCEPTED, B.POTVRZENO, {R.COORDINATOR}, T.CANCELLED, B.POTVRZENO),
    ("cancel", T.IN_PROGRESS, B.POTVRZENO, {R.COORDINATOR}, T.CANCELLED, B.POTVRZENO),
]  # fmt: skip
# owner is COORD; the roles above are the only ones allowed (owner ∪ explicit), i.e. COORD (+SYSTEM)


@pytest.mark.parametrize("row", ALLOWED, ids=lambda r: f"{r[0]}-{r[1].value}")
def test_allowed(row):
    event, st, bs, roles, to_st, to_bs = row
    for role in roles:
        res = transition(task(st, bs), event, role, CTX, NOW)
        assert (res.task.status, res.task.business_status) == (to_st, to_bs)
        assert res.events[0].kind is EventKind.AUDIT
        assert res.events[0].payload["to"] == to_st.value


@pytest.mark.parametrize("row", ALLOWED, ids=lambda r: f"{r[0]}-{r[1].value}")
def test_forbidden_roles(row):
    event, st, bs, roles, *_ = row
    for role in set(R) - roles:
        with pytest.raises(TransitionError) as e:
            transition(task(st, bs), event, role, CTX, NOW)
        assert e.value.code == "forbidden_role"


def test_all_other_status_event_pairs_forbidden():
    allowed = {(r[0], r[1]) for r in ALLOWED}
    for event in TASK_EVENTS:
        for st in T:
            if (event, st) in allowed:
                continue
            for role in R:
                with pytest.raises(TransitionError) as e:
                    transition(task(st, B.POTVRZENO), event, role, CTX, NOW)
                assert e.value.code == "invalid_transition"


def test_owner_may_act_when_not_coordinator():
    t = task(T.ACCEPTED, B.POTVRZENO, owner_role=R.KOC_PHYSICIAN)
    assert transition(t, "start", R.KOC_PHYSICIAN, CTX, NOW).task.status is T.IN_PROGRESS
    with pytest.raises(TransitionError):
        transition(t, "start", R.COORDINATOR, CTX, NOW)  # start is owner-only


GUARDS = [
    ("order_confirmed", T.REQUESTED, B.OBJEDNANO, {"scheduled_at": None}),
    ("order_confirmed", T.REQUESTED, B.POTVRZENO, {}),
    ("accept", T.REQUESTED, B.OBJEDNANO, {}),  # requested ≠ ordered
    ("start", T.ACCEPTED, B.POTVRZENO, {"completed_task_ids": frozenset()}),
    ("performed", T.IN_PROGRESS, B.OBJEDNANO, {}),
    ("result_delivered", T.IN_PROGRESS, B.POTVRZENO, {}),  # not performed
    ("result_delivered", T.IN_PROGRESS, B.PROVEDENO, {"result_doc_id": None}),
    ("fail", T.IN_PROGRESS, B.POTVRZENO, {"reason": " "}),
    ("cancel", T.REQUESTED, B.OBJEDNANO, {"reason": None}),
]


@pytest.mark.parametrize("row", GUARDS, ids=lambda r: f"{r[0]}-{sorted(r[3])}-{r[2].value}")
def test_guards(row):
    event, st, bs, ctx_kw = row
    with pytest.raises(TransitionError) as e:
        transition(task(st, bs),
                   event, R.COORDINATOR, replace(CTX, **ctx_kw), NOW)  # fmt: skip
    assert e.value.code == "guard_failed"


def test_order_needs_place():
    with pytest.raises(TransitionError):
        transition(task(location=None), "order_confirmed", R.COORDINATOR, replace(CTX, place=None), NOW)


def test_full_happy_path_cannot_skip_result():
    t = task()
    for ev, role in [("order_confirmed", R.COORDINATOR), ("accept", R.COORDINATOR), ("start", R.COORDINATOR),
                     ("performed", R.COORDINATOR), ("result_delivered", R.SYSTEM)]:  # fmt: skip
        t = transition(t, ev, role, CTX, NOW).task
    assert t.status is T.COMPLETED
    assert t.business_status is B.VYSLEDEK_DORUCEN
    assert t.result_doc_id == "doc-11"
    assert t.scheduled_at == SLOT


def test_fail_notifies_coordinator():
    res = transition(task(T.IN_PROGRESS, B.POTVRZENO), "fail", R.COORDINATOR, CTX, NOW)
    assert res.events[1].recipients == (R.COORDINATOR,)


# --- overdue -----------------------------------------------------------------------------------


def at(d, h=9, m=0):
    return datetime(2026, 10, d, h, m, tzinfo=clock.TZ)


def test_not_overdue_on_due_day_even_late_evening():
    t = task(T.IN_PROGRESS, due=date(2026, 10, 15))
    assert check_overdue(t, at(15, 23, 59)) == []


def test_overdue_next_day_escalates_to_coordinator_once():
    t = task(T.IN_PROGRESS, due=date(2026, 10, 15))
    res = escalate_if_overdue(t, at(16))
    (ev,) = res.events
    assert ev.kind is EventKind.ESCALATION
    assert ev.recipients == (R.COORDINATOR,)
    assert ev.payload["overdue_workdays"] == 1
    assert ev.payload["deadline"] == "2026-10-15"
    assert res.task.escalated_at == at(16)
    assert escalate_if_overdue(res.task, at(19)).events == ()  # idempotent


def test_sla_earlier_than_due_drives_escalation():
    t = task(T.REQUESTED, due=date(2026, 10, 19), sla_due=date(2026, 10, 15))
    assert check_overdue(t, at(15, 20)) == []
    (ev,) = check_overdue(t, at(16))
    assert ev.payload["basis"] == "sla"


@pytest.mark.parametrize("st", [T.COMPLETED, T.FAILED, T.CANCELLED])
def test_closed_tasks_never_escalate(st):
    assert check_overdue(task(st, due=date(2026, 10, 1)), at(16)) == []


def test_overdue_uses_demo_clock(monkeypatch):
    monkeypatch.setenv(clock.ENV_VAR, "2026-10-16T09:00:00+02:00")
    assert len(check_overdue(task(T.ACCEPTED, due=date(2026, 10, 15)))) == 1


def test_naive_appointment_rejected():
    naive = datetime(2026, 10, 12, 9, 0)  # noqa: DTZ001
    with pytest.raises(TransitionError, match="časové pásmo") as e:
        transition(task(), "order_confirmed", R.COORDINATOR, replace(CTX, scheduled_at=naive), NOW)
    assert e.value.code == "guard_failed"


@pytest.mark.parametrize(("event", "status"), [("fail", T.IN_PROGRESS), ("cancel", T.REQUESTED)])
def test_termination_reason_is_audited(event, status):
    res = transition(task(status, B.POTVRZENO), event, R.COORDINATOR, CTX, NOW)
    assert res.events[0].payload["reason"] == "důvod"


def test_other_events_do_not_carry_reason():
    res = transition(task(), "order_confirmed", R.COORDINATOR, CTX, NOW)
    assert "reason" not in res.events[0].payload
