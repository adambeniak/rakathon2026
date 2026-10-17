"""The case's baton role and next action for the queue card (#180)."""

from __future__ import annotations

import pytest

from app.domain.case import CaseAction, CaseState
from app.domain.common import Role
from tests.unit.domain.conftest import make_case

S = CaseState


@pytest.mark.parametrize(
    ("state", "role", "action"),
    [
        (S.ODESLANO, Role.COORDINATOR, CaseAction.ACCEPT_CASE),
        (S.TRIAGE, Role.COORDINATOR, CaseAction.TRIAGE),
        (S.CEKA_NA_PODKLADY, Role.COORDINATOR, CaseAction.COMPLETE_DOCUMENTS),
        (S.KOMPLETNI, Role.KOC_PHYSICIAN, CaseAction.REVIEW_HANDOVER),
        (S.PRIPRAVENO_MDT, Role.KOC_PHYSICIAN, CaseAction.HOLD_MDT),
        (S.ZAVER_MDT, Role.COORDINATOR, CaseAction.SEND_FEEDBACK),
        (S.ZPETNA_VAZBA_ODESLANA, Role.GP, CaseAction.CONFIRM_RECEIPT),
    ],
)
def test_action_follows_the_state_and_the_machines_baton_role(state: CaseState, role: Role, action: CaseAction) -> None:
    case = make_case(state, baton_role=role)
    assert (case.current_baton_role, case.next_action) == (role, action)


def test_after_delivery_confirmed_the_coordinator_closes() -> None:
    case = make_case(S.ZPETNA_VAZBA_ODESLANA, baton_role=Role.COORDINATOR, delivery_receipt=True)
    assert (case.current_baton_role, case.next_action) == (Role.COORDINATOR, CaseAction.CLOSE_CASE)


def test_a_stored_case_without_baton_role_falls_back_to_the_state_table() -> None:
    assert make_case(S.KOMPLETNI).current_baton_role is Role.KOC_PHYSICIAN
    sent = make_case(S.ZPETNA_VAZBA_ODESLANA)
    assert (sent.current_baton_role, sent.next_action) == (Role.GP, CaseAction.CONFIRM_RECEIPT)
    delivered = make_case(S.ZPETNA_VAZBA_ODESLANA, delivery_receipt=True)
    assert (delivered.current_baton_role, delivered.next_action) == (Role.COORDINATOR, CaseAction.CLOSE_CASE)


def test_postponed_case_waits_for_the_external_workplace() -> None:
    case = make_case(S.CEKA_NA_PODKLADY, odlozeny=True, baton_role=Role.EXTERNAL_WORKPLACE)
    assert (case.current_baton_role, case.next_action) == (Role.EXTERNAL_WORKPLACE, CaseAction.AWAIT_EXTERNAL)


def test_closed_case_has_no_baton() -> None:
    case = make_case(S.UZAVRENO, baton_role=Role.COORDINATOR)
    assert (case.current_baton_role, case.next_action) == (None, CaseAction.NONE)
