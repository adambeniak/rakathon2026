from dataclasses import replace
from datetime import timedelta

import pytest

from app.domain.case import CaseState as S
from app.domain.case import QueueBucket
from app.domain.case_machine import CASE_EVENTS, CaseContext, submit_referral, transition
from app.domain.common import PartyRef, Role
from app.domain.events import EventKind, TransitionError
from app.domain.pathway import Readiness, Waiver, readiness_gate
from tests.unit.domain.conftest import MDT, PATIENT, make_case

R = Role
OK = Readiness(True, (), ())
CTX_OK = CaseContext(
    consent_confirmed=True, target_koc="KOC2", patient_id="p1", open_request_tasks=1,
    readiness=OK, reason="důvod", resume_on="2026-10-20", conclusion="závěr", confirmed_by="u-doc",
    gp_recipient="gp@example.test", receipt_id="r1",
)  # fmt: skip
NOW = MDT + timedelta(hours=1)
POSTPONABLE = (S.TRIAGE, S.CEKA_NA_PODKLADY, S.KOMPLETNI, S.PRIPRAVENO_MDT)

# (state, event, allowed roles, next state, baton role after, case overrides, ctx overrides)
ALLOWED = [
    (S.ODESLANO, "accept", {R.COORDINATOR}, S.TRIAGE, R.COORDINATOR, {}, {}),
    (S.TRIAGE, "request_documents", {R.COORDINATOR}, S.CEKA_NA_PODKLADY, R.COORDINATOR, {}, {}),
    (S.TRIAGE, "mark_complete", {R.COORDINATOR}, S.KOMPLETNI, R.KOC_PHYSICIAN, {}, {}),
    (S.CEKA_NA_PODKLADY, "docs_received", {R.COORDINATOR, R.SYSTEM}, S.KOMPLETNI, R.KOC_PHYSICIAN, {},
     {"open_request_tasks": 0}),
    (S.KOMPLETNI, "missing_found", {R.COORDINATOR, R.KOC_PHYSICIAN}, S.CEKA_NA_PODKLADY, R.COORDINATOR, {}, {}),
    (S.KOMPLETNI, "mark_ready_mdt", {R.KOC_PHYSICIAN}, S.PRIPRAVENO_MDT, R.KOC_PHYSICIAN, {}, {}),
    (S.PRIPRAVENO_MDT, "reopen", {R.KOC_PHYSICIAN}, S.KOMPLETNI, R.KOC_PHYSICIAN, {}, {}),
    (S.PRIPRAVENO_MDT, "record_mdt_conclusion", {R.KOC_PHYSICIAN}, S.ZAVER_MDT, R.COORDINATOR, {}, {}),
    (S.ZAVER_MDT, "send_feedback", {R.COORDINATOR}, S.ZPETNA_VAZBA_ODESLANA, R.GP,
     {"conclusion_confirmed": True}, {}),
    (S.ZPETNA_VAZBA_ODESLANA, "delivery_confirmed", {R.SYSTEM}, S.ZPETNA_VAZBA_ODESLANA, R.COORDINATOR, {}, {}),
    (S.ZPETNA_VAZBA_ODESLANA, "gp_opened", {R.GP, R.SYSTEM}, S.ZPETNA_VAZBA_ODESLANA, R.COORDINATOR,
     {"baton_role": R.COORDINATOR}, {}),
    (S.ZPETNA_VAZBA_ODESLANA, "close", {R.COORDINATOR}, S.UZAVRENO, None, {"delivery_receipt": True}, {}),
    *((s, "postpone", {R.COORDINATOR}, s, R.EXTERNAL_WORKPLACE, {}, {}) for s in POSTPONABLE),
    *(
        (s, "resume", {R.COORDINATOR}, s, R.KOC_PHYSICIAN, {"odlozeny": True, "resume_baton_role": R.KOC_PHYSICIAN}, {})
        for s in POSTPONABLE
    ),
]  # fmt: skip


def _id(row: tuple) -> str:  # type: ignore[type-arg]
    return f"{row[0].value}-{row[1]}"


@pytest.mark.parametrize("row", ALLOWED, ids=_id)
def test_allowed_transitions(row: tuple) -> None:  # type: ignore[type-arg]
    state, event, roles, to, baton, case_kw, ctx_kw = row
    ctx = replace(CTX_OK, **ctx_kw)
    for role in roles:
        res = transition(make_case(state, **case_kw), event, role, ctx, NOW)
        assert res.case.state == to
        assert res.case.baton_role == baton
        audit = res.events[0]
        assert audit.kind is EventKind.AUDIT
        assert audit.payload["event"] == event
        assert audit.payload["actor_role"] == role.value


@pytest.mark.parametrize("row", ALLOWED, ids=_id)
def test_forbidden_roles(row: tuple) -> None:  # type: ignore[type-arg]
    state, event, roles, _to, _b, case_kw, ctx_kw = row
    ctx = replace(CTX_OK, **ctx_kw)
    for role in set(R) - roles:
        with pytest.raises(TransitionError) as e:
            transition(make_case(state, **case_kw), event, role, ctx, NOW)
        assert e.value.code == "forbidden_role"


def test_every_other_state_event_pair_is_forbidden() -> None:
    allowed = {(r[0], r[1]) for r in ALLOWED}
    checked = 0
    for state in S:
        for event in CASE_EVENTS:
            if (state, event) in allowed:
                continue
            for role in R:
                with pytest.raises(TransitionError) as e:
                    transition(make_case(state), event, role, CTX_OK, NOW)
                assert e.value.code in {"invalid_transition", "case_postponed"}
                checked += 1
    assert checked > 200


def test_transition_error_is_a_conflict() -> None:
    from app.domain.errors import ConflictError

    with pytest.raises(ConflictError):
        transition(make_case(S.UZAVRENO), "accept", R.COORDINATOR, CTX_OK, NOW)


# --- submit (creates the case) ---------------------------------------------------------------


def test_submit_creates_case_for_gp_only() -> None:
    res = submit_referral("c1", PATIENT, R.GP, CTX_OK, NOW)
    assert res.case.state is S.ODESLANO
    assert res.case.baton_role is R.COORDINATOR
    assert res.case.bucket is QueueBucket.NOVY
    assert res.events[0].action == "create"
    assert res.events[1].recipients == (R.COORDINATOR,)
    for role in set(R) - {R.GP}:
        with pytest.raises(TransitionError) as e:
            submit_referral("c1", PATIENT, role, CTX_OK, NOW)
        assert e.value.code == "forbidden_role"


@pytest.mark.parametrize(
    "ctx_kw", [{"consent_confirmed": False}, {"target_koc": None}, {"patient_id": " "}], ids=lambda kw: next(iter(kw))
)
def test_submit_guards(ctx_kw: dict[str, object]) -> None:
    with pytest.raises(TransitionError) as e:
        submit_referral("c1", PATIENT, R.GP, replace(CTX_OK, **ctx_kw), NOW)  # type: ignore[arg-type]
    assert e.value.code == "guard_failed"


# --- guards -----------------------------------------------------------------------------------

GUARD_FAILS = [
    (S.TRIAGE, "request_documents", R.COORDINATOR, {"open_request_tasks": 0}, {}),
    (S.TRIAGE, "mark_complete", R.COORDINATOR, {"missing_blockers": 2}, {}),
    (S.CEKA_NA_PODKLADY, "docs_received", R.COORDINATOR, {"open_request_tasks": 1}, {}),
    (S.KOMPLETNI, "missing_found", R.COORDINATOR, {"reason": None}, {}),
    (S.KOMPLETNI, "mark_ready_mdt", R.KOC_PHYSICIAN, {"readiness": None}, {}),
    (S.KOMPLETNI, "mark_ready_mdt", R.KOC_PHYSICIAN,
     {"readiness": Readiness(False, ("performance_status",), ())}, {}),
    (S.PRIPRAVENO_MDT, "reopen", R.KOC_PHYSICIAN, {"reason": ""}, {}),
    (S.PRIPRAVENO_MDT, "record_mdt_conclusion", R.KOC_PHYSICIAN, {"conclusion": None}, {}),
    (S.PRIPRAVENO_MDT, "record_mdt_conclusion", R.KOC_PHYSICIAN, {"confirmed_by": None}, {}),
    (S.PRIPRAVENO_MDT, "record_mdt_conclusion", R.KOC_PHYSICIAN, {}, {"mdt_start": None}),
    (S.ZAVER_MDT, "send_feedback", R.COORDINATOR, {"gp_recipient": None}, {"conclusion_confirmed": True}),
    (S.ZAVER_MDT, "send_feedback", R.COORDINATOR, {}, {"conclusion_confirmed": False}),
    (S.ZPETNA_VAZBA_ODESLANA, "delivery_confirmed", R.SYSTEM, {"receipt_id": None}, {}),
    (S.ZPETNA_VAZBA_ODESLANA, "close", R.COORDINATOR, {}, {"delivery_receipt": False}),
    (S.TRIAGE, "postpone", R.COORDINATOR, {"reason": None}, {}),
    (S.TRIAGE, "postpone", R.COORDINATOR, {"resume_on": None}, {}),
    (S.TRIAGE, "resume", R.COORDINATOR, {}, {"odlozeny": False}),
]  # fmt: skip


@pytest.mark.parametrize("row", GUARD_FAILS, ids=lambda r: f"{r[0].value}-{r[1]}-{sorted(r[3] or r[4])}")
def test_guard_failures(row: tuple) -> None:  # type: ignore[type-arg]
    state, event, role, ctx_kw, case_kw = row
    with pytest.raises(TransitionError) as e:
        transition(make_case(state, **case_kw), event, role, replace(CTX_OK, **ctx_kw), NOW)
    assert e.value.code == "guard_failed"


def test_conclusion_before_mdt_start_rejected() -> None:
    with pytest.raises(TransitionError) as e:
        transition(
            make_case(S.PRIPRAVENO_MDT), "record_mdt_conclusion", R.KOC_PHYSICIAN, CTX_OK, MDT - timedelta(minutes=1)
        )
    assert e.value.code == "guard_failed"


def test_conclusion_audit_records_confirming_clinician() -> None:
    res = transition(make_case(S.PRIPRAVENO_MDT), "record_mdt_conclusion", R.KOC_PHYSICIAN, CTX_OK, NOW)
    assert res.case.conclusion_confirmed
    assert res.events[0].payload["confirmed_by"] == "u-doc"


# --- readiness waiver path -----------------------------------------------------------------------

REQUIRED = ["histology", "ct_staging", "tumour_markers", "comorbidities", "performance_status", "mdt_question"]
STATUSES = {i: "complete" for i in REQUIRED} | {"performance_status": "missing"}


def test_ready_via_physician_waiver_records_it_in_audit() -> None:
    w = Waiver("performance_status", R.KOC_PHYSICIAN, "u-doc", "ECOG v dokumentaci chybí, doplní se na MDT")
    gate = readiness_gate(STATUSES, REQUIRED, [w])
    assert gate.ready
    assert gate.waived == (w,)
    res = transition(make_case(S.KOMPLETNI), "mark_ready_mdt", R.KOC_PHYSICIAN, CaseContext(readiness=gate), NOW)
    assert res.events[0].payload["waived"][0]["item"] == "performance_status"  # type: ignore[index]
    assert res.events[1].recipients == (R.KOC_PHYSICIAN,)


def test_unwaived_gate_blocks_and_coordinator_cannot_move_case() -> None:
    gate = readiness_gate(STATUSES, REQUIRED)
    assert not gate.ready
    assert gate.missing == ("performance_status",)
    with pytest.raises(TransitionError) as e:
        transition(make_case(S.KOMPLETNI), "mark_ready_mdt", R.KOC_PHYSICIAN, CaseContext(readiness=gate), NOW)
    assert e.value.code == "guard_failed"
    with pytest.raises(TransitionError) as e:
        transition(make_case(S.KOMPLETNI), "mark_ready_mdt", R.COORDINATOR, CaseContext(readiness=OK), NOW)
    assert e.value.code == "forbidden_role"


# --- postponement, buckets, baton ----------------------------------------------------------------


def test_postpone_resume_restores_baton_and_bucket() -> None:
    c = make_case(S.KOMPLETNI, baton_role=R.KOC_PHYSICIAN)
    assert c.bucket is QueueBucket.AKTIVNI
    c = transition(c, "postpone", R.COORDINATOR, CTX_OK, NOW).case
    assert c.odlozeny
    assert c.bucket is QueueBucket.ODLOZENY
    assert c.baton_role is R.EXTERNAL_WORKPLACE
    with pytest.raises(TransitionError) as e:  # nothing but resume while postponed
        transition(c, "mark_ready_mdt", R.KOC_PHYSICIAN, CTX_OK, NOW)
    assert e.value.code == "case_postponed"
    c = transition(c, "resume", R.COORDINATOR, CTX_OK, NOW).case
    assert not c.odlozeny
    assert c.baton_role is R.KOC_PHYSICIAN
    assert c.bucket is QueueBucket.AKTIVNI


def test_baton_holder_cleared_when_role_changes() -> None:
    holder = PartyRef(id="dvorakova-lucie@koc2", display="Bc. Dvořáková", role=R.COORDINATOR)
    c = make_case(S.TRIAGE, baton_role=R.COORDINATOR, baton_holder=holder)
    kept = transition(c, "request_documents", R.COORDINATOR, CTX_OK, NOW).case
    assert kept.baton_holder == holder  # same role keeps the person
    moved = transition(c, "mark_complete", R.COORDINATOR, replace(CTX_OK, missing_blockers=0), NOW).case
    assert moved.baton_holder is None
    assert moved.baton_role is R.KOC_PHYSICIAN


def test_happy_path_buckets_and_notifications() -> None:
    res = submit_referral("c1", PATIENT, R.GP, CTX_OK, NOW, mdt_start=MDT)
    c = res.case
    seen = [(c.state, c.bucket)]
    steps = [
        ("accept", R.COORDINATOR, {}), ("request_documents", R.COORDINATOR, {}),
        ("docs_received", R.COORDINATOR, {"open_request_tasks": 0}),
        ("mark_ready_mdt", R.KOC_PHYSICIAN, {}), ("record_mdt_conclusion", R.KOC_PHYSICIAN, {}),
        ("send_feedback", R.COORDINATOR, {}), ("delivery_confirmed", R.SYSTEM, {}),
        ("gp_opened", R.GP, {}), ("close", R.COORDINATOR, {}),
    ]  # fmt: skip
    for event, role, kw in steps:
        res = transition(c, event, role, replace(CTX_OK, **kw), NOW)
        c = res.case
        seen.append((c.state, c.bucket))
        if event == "send_feedback":
            assert {e.recipients for e in res.events[1:]} == {(R.GP,), (R.REVIEWER,)}
        if event == "gp_opened":
            assert res.events[0].action == "read"
    assert seen[0] == (S.ODESLANO, QueueBucket.NOVY)
    assert seen[1] == (S.TRIAGE, QueueBucket.AKTIVNI)  # Nový is only `odeslano`
    assert seen[-1] == (S.UZAVRENO, QueueBucket.ARCHIV)
    assert c.baton_role is None
    assert c.delivery_receipt


def test_closed_is_terminal() -> None:
    c = make_case(S.UZAVRENO)
    for event in CASE_EVENTS:
        for role in R:
            with pytest.raises(TransitionError):
                transition(c, event, role, CTX_OK, NOW)


def test_clock_default_uses_demo_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STAFETA_DEMO_NOW", "2026-10-21T09:00:00+02:00")
    res = transition(make_case(S.PRIPRAVENO_MDT), "record_mdt_conclusion", R.KOC_PHYSICIAN, CTX_OK)
    assert res.events[0].at.hour == 9
