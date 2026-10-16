from dataclasses import replace
from datetime import timedelta

import pytest

from domain.case_machine import (
    CASE_EVENTS,
    Baton,
    Bucket,
    Case,
    CaseContext,
    transition,
)
from domain.case_machine import (
    CaseState as S,
)
from domain.events import EventKind, Role, TransitionError
from domain.pathway import Readiness, Waiver, readiness_gate
from tests.conftest import MDT

R = Role
OK = Readiness(True, (), ())
CTX_OK = CaseContext(
    consent_confirmed=True, target_koc="KOC2", patient_id="p1", open_request_tasks=1,
    readiness=OK, reason="důvod", resume_on="2026-10-20", conclusion="závěr",
    gp_recipient="gp@example.test", receipt_id="r1",
)  # fmt: skip
NOW = MDT + timedelta(hours=1)


def case(state, **kw):
    base = {"id": "c1", "state": state, "mdt_start": MDT, "baton": Baton.COORD}
    return Case(**{**base, **kw})


# (state, event, allowed roles, expected next state, expected baton, case overrides, ctx overrides)
ALLOWED = [
    (None, "submit", {R.GP}, S.ODESLANO, Baton.COORD, {}, {}),
    (S.ODESLANO, "accept", {R.COORD}, S.TRIAGE, Baton.COORD, {}, {}),
    (S.TRIAGE, "request_documents", {R.COORD}, S.CEKA_NA_PODKLADY, Baton.COORD, {}, {}),
    (S.TRIAGE, "mark_complete", {R.COORD}, S.KOMPLETNI, Baton.KOC_DOC, {}, {}),
    (S.CEKA_NA_PODKLADY, "docs_received", {R.COORD, R.SYSTEM}, S.KOMPLETNI, Baton.KOC_DOC, {},
     {"open_request_tasks": 0}),
    (S.KOMPLETNI, "missing_found", {R.COORD, R.KOC_DOC}, S.CEKA_NA_PODKLADY, Baton.COORD, {}, {}),
    (S.KOMPLETNI, "mark_ready_mdt", {R.KOC_DOC}, S.PRIPRAVENO_MDT, Baton.MDT, {}, {}),
    (S.PRIPRAVENO_MDT, "reopen", {R.KOC_DOC}, S.KOMPLETNI, Baton.KOC_DOC, {}, {}),
    (S.PRIPRAVENO_MDT, "record_mdt_conclusion", {R.KOC_DOC, R.MDT}, S.ZAVER_MDT, Baton.COORD, {}, {}),
    (S.ZAVER_MDT, "send_feedback", {R.COORD}, S.ZPETNA_VAZBA_ODESLANA, Baton.GP,
     {"conclusion_confirmed": True}, {}),
    (S.ZPETNA_VAZBA_ODESLANA, "delivery_confirmed", {R.SYSTEM}, S.ZPETNA_VAZBA_ODESLANA,
     Baton.COORD, {}, {}),
    (S.ZPETNA_VAZBA_ODESLANA, "gp_opened", {R.GP, R.SYSTEM}, S.ZPETNA_VAZBA_ODESLANA, Baton.COORD,
     {}, {}),
    (S.ZPETNA_VAZBA_ODESLANA, "close", {R.COORD}, S.UZAVRENO, Baton.NONE,
     {"delivery_receipt": True}, {}),
    *(
        (s, "postpone", {R.COORD}, s, Baton.EXTERNAL, {}, {})
        for s in (S.TRIAGE, S.CEKA_NA_PODKLADY, S.KOMPLETNI, S.PRIPRAVENO_MDT)
    ),
    *(
        (s, "resume", {R.COORD}, s, Baton.KOC_DOC, {"odlozeny": True, "resume_baton": Baton.KOC_DOC}, {})
        for s in (S.TRIAGE, S.CEKA_NA_PODKLADY, S.KOMPLETNI, S.PRIPRAVENO_MDT)
    ),
]  # fmt: skip

# gp_opened keeps the baton it had; give it COORD (set after delivery confirmation)
ALL_ROLES = set(R)


def _id(p):
    return f"{p[0].value if p[0] else 'new'}-{p[1]}"


@pytest.mark.parametrize("row", ALLOWED, ids=_id)
def test_allowed_transitions(row):
    state, event, roles, to, baton, case_kw, ctx_kw = row
    ctx = replace(CTX_OK, **ctx_kw)
    c = case(state, **case_kw) if state else Case(id="c1", mdt_start=MDT)
    for role in roles:
        res = transition(c, event, role, ctx, NOW)
        assert res.case.state == to
        assert res.case.baton == baton
        audit = res.events[0]
        assert audit.kind is EventKind.AUDIT and audit.payload["event"] == event
        assert audit.payload["actor_role"] == role.value


@pytest.mark.parametrize("row", ALLOWED, ids=_id)
def test_forbidden_roles(row):
    state, event, roles, _to, _b, case_kw, ctx_kw = row
    ctx = replace(CTX_OK, **ctx_kw)
    c = case(state, **case_kw) if state else Case(id="c1", mdt_start=MDT)
    for role in ALL_ROLES - roles:
        with pytest.raises(TransitionError) as e:
            transition(c, event, role, ctx, NOW)
        assert e.value.code == "forbidden_role"


def test_every_other_state_event_pair_is_forbidden():
    allowed = {(r[0], r[1]) for r in ALLOWED}
    states = [None, *S]
    checked = 0
    for state in states:
        for event in CASE_EVENTS:
            if (state, event) in allowed:
                continue
            c = case(state) if state else Case(id="c1", mdt_start=MDT)
            for role in R:
                with pytest.raises(TransitionError) as e:
                    transition(c, event, role, CTX_OK, NOW)
                assert e.value.code in {"invalid_transition", "case_postponed"}
                checked += 1
    assert checked > 200


# --- guards -----------------------------------------------------------------------------------

GUARD_FAILS = [
    (None, "submit", R.GP, {"consent_confirmed": False}, {}),
    (None, "submit", R.GP, {"target_koc": None}, {}),
    (None, "submit", R.GP, {"patient_id": " "}, {}),
    (S.TRIAGE, "request_documents", R.COORD, {"open_request_tasks": 0}, {}),
    (S.TRIAGE, "mark_complete", R.COORD, {"missing_blockers": 2}, {}),
    (S.CEKA_NA_PODKLADY, "docs_received", R.COORD, {"open_request_tasks": 1}, {}),
    (S.KOMPLETNI, "missing_found", R.COORD, {"reason": None}, {}),
    (S.KOMPLETNI, "mark_ready_mdt", R.KOC_DOC, {"readiness": None}, {}),
    (S.KOMPLETNI, "mark_ready_mdt", R.KOC_DOC,
     {"readiness": Readiness(False, ("performance_status",), ())}, {}),
    (S.PRIPRAVENO_MDT, "reopen", R.KOC_DOC, {"reason": ""}, {}),
    (S.PRIPRAVENO_MDT, "record_mdt_conclusion", R.MDT, {"conclusion": None}, {}),
    (S.PRIPRAVENO_MDT, "record_mdt_conclusion", R.MDT, {}, {"mdt_start": None}),
    (S.ZAVER_MDT, "send_feedback", R.COORD, {"gp_recipient": None}, {"conclusion_confirmed": True}),
    (S.ZAVER_MDT, "send_feedback", R.COORD, {}, {"conclusion_confirmed": False}),
    (S.ZPETNA_VAZBA_ODESLANA, "delivery_confirmed", R.SYSTEM, {"receipt_id": None}, {}),
    (S.ZPETNA_VAZBA_ODESLANA, "close", R.COORD, {}, {"delivery_receipt": False}),
    (S.TRIAGE, "postpone", R.COORD, {"reason": None}, {}),
    (S.TRIAGE, "postpone", R.COORD, {"resume_on": None}, {}),
    (S.TRIAGE, "resume", R.COORD, {}, {"odlozeny": False}),
]  # fmt: skip


@pytest.mark.parametrize("row", GUARD_FAILS, ids=lambda r: f"{r[0]}-{r[1]}-{sorted(r[3] or r[4])}")
def test_guard_failures(row):
    state, event, role, ctx_kw, case_kw = row
    case_kw = dict(case_kw)
    c = case(state, **case_kw) if state else Case(id="c1", mdt_start=MDT)
    with pytest.raises(TransitionError) as e:
        transition(c, event, role, replace(CTX_OK, **ctx_kw), NOW)
    assert e.value.code == "guard_failed"


def test_conclusion_before_mdt_start_rejected():
    with pytest.raises(TransitionError) as e:
        transition(
            case(S.PRIPRAVENO_MDT),
            "record_mdt_conclusion",
            R.MDT,
            CTX_OK,
            MDT - timedelta(minutes=1),
        )
    assert e.value.code == "guard_failed"


# --- readiness waiver path -----------------------------------------------------------------------

REQUIRED = [
    "histology",
    "ct_staging",
    "tumour_markers",
    "comorbidities",
    "performance_status",
    "mdt_question",
]
STATUSES = {i: "complete" for i in REQUIRED} | {"performance_status": "missing"}


def test_ready_via_physician_waiver_records_it_in_audit():
    w = Waiver(
        "performance_status", R.KOC_DOC, "u-doc", "ECOG v dokumentaci chybí, doplní se na MDT"
    )
    gate = readiness_gate(STATUSES, REQUIRED, [w])
    assert gate.ready and gate.waived == (w,)
    res = transition(
        case(S.KOMPLETNI), "mark_ready_mdt", R.KOC_DOC, CaseContext(readiness=gate), NOW
    )
    assert res.events[0].payload["waived"][0]["item"] == "performance_status"
    assert res.events[1].recipients == (R.MDT,)


def test_unwaived_gate_blocks_and_coordinator_cannot_move_case():
    gate = readiness_gate(STATUSES, REQUIRED)
    assert not gate.ready and gate.missing == ("performance_status",)
    with pytest.raises(TransitionError) as e:
        transition(case(S.KOMPLETNI), "mark_ready_mdt", R.KOC_DOC, CaseContext(readiness=gate), NOW)
    assert e.value.code == "guard_failed"
    with pytest.raises(TransitionError) as e:
        transition(case(S.KOMPLETNI), "mark_ready_mdt", R.COORD, CaseContext(readiness=OK), NOW)
    assert e.value.code == "forbidden_role"


# --- postponement, buckets, baton --------------------------------------------------------------


def test_postpone_resume_restores_baton_and_bucket():
    c = case(S.KOMPLETNI, baton=Baton.KOC_DOC)
    assert c.bucket is Bucket.AKTIVNI
    c = transition(c, "postpone", R.COORD, CTX_OK, NOW).case
    assert c.odlozeny and c.bucket is Bucket.ODLOZENY and c.baton is Baton.EXTERNAL
    with pytest.raises(TransitionError) as e:  # nothing but resume while postponed
        transition(c, "mark_ready_mdt", R.KOC_DOC, CTX_OK, NOW)
    assert e.value.code == "case_postponed"
    c = transition(c, "resume", R.COORD, CTX_OK, NOW).case
    assert not c.odlozeny and c.baton is Baton.KOC_DOC and c.bucket is Bucket.AKTIVNI


def test_buckets_along_happy_path_and_notifications():
    c = Case(id="c1", mdt_start=MDT)
    seen = []
    steps = [
        ("submit", R.GP, {}), ("accept", R.COORD, {}), ("request_documents", R.COORD, {}),
        ("docs_received", R.COORD, {"open_request_tasks": 0}),
        ("mark_ready_mdt", R.KOC_DOC, {}), ("record_mdt_conclusion", R.MDT, {}),
        ("send_feedback", R.COORD, {}), ("delivery_confirmed", R.SYSTEM, {}),
        ("gp_opened", R.GP, {}), ("close", R.COORD, {}),
    ]  # fmt: skip
    for event, role, kw in steps:
        res = transition(c, event, role, replace(CTX_OK, **kw), NOW)
        c = res.case
        seen.append((c.state, c.bucket))
        if event == "send_feedback":
            assert {e.recipients for e in res.events[1:]} == {(R.GP,), (R.REVIEWER,)}
        if event == "gp_opened":
            assert res.events[0].action == "read"
    assert seen[0] == (S.ODESLANO, Bucket.NOVY)
    assert seen[1] == (S.TRIAGE, Bucket.AKTIVNI)
    assert seen[-1] == (S.UZAVRENO, Bucket.ARCHIV)
    assert c.baton is Baton.NONE and c.delivery_receipt


def test_closed_is_terminal():
    c = case(S.UZAVRENO, baton=Baton.NONE)
    for event in CASE_EVENTS:
        for role in R:
            with pytest.raises(TransitionError):
                transition(c, event, role, CTX_OK, NOW)


def test_clock_default_uses_demo_now(monkeypatch):
    monkeypatch.setenv("STAFETA_DEMO_NOW", "2026-10-21T09:00:00+02:00")
    res = transition(case(S.PRIPRAVENO_MDT), "record_mdt_conclusion", R.MDT, CTX_OK)
    assert res.events[0].at.hour == 9
