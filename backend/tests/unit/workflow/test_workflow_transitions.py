"""CaseWorkflow.transition against a recording repository: baton holder, bundle shape, optimistic lock."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest

from app.domain.case import Case, CaseState
from app.domain.common import PartyRef, Role
from app.domain.errors import ForbiddenError, InvalidInputError
from app.domain.events import TransitionError
from app.fhir.cases import LoadedCase
from app.fhir.mappers.case import case_task_to_fhir
from app.fhir.workflow import CaseWorkflow
from app.security.actor import SYSTEM_ACTOR
from app.seed import demo_case
from app.settings import PRAGUE
from tests.directory_fixtures import demo_directory

NOW = datetime(2026, 10, 2, 10, 0, tzinfo=PRAGUE)
DIRECTORY = demo_directory()
COORDINATOR = DIRECTORY.role(demo_case.COORDINATOR_ROLE)
GP = DIRECTORY.role(demo_case.GP_ROLE)
assert COORDINATOR
assert GP
KOC2 = DIRECTORY.org(demo_case.KOC2)
assert KOC2


class FakeRepo:
    def __init__(self, open_requests: int = 0) -> None:
        self.open_requests = open_requests
        self.bundles: list[dict[str, Any]] = []

    async def count(self, resource_type: str, params: dict[str, str]) -> int:
        assert resource_type == "Task"
        assert params["part-of"] == "Task/5"
        return self.open_requests

    async def transaction(self, bundle: dict[str, Any]) -> dict[str, Any]:
        self.bundles.append(bundle)
        return {}


class FakeReader:
    def __init__(self, loaded: LoadedCase) -> None:
        self.loaded = loaded

    async def load(self, case_id: str) -> LoadedCase:
        return self.loaded


def _loaded(state: CaseState, baton_role: Role = Role.COORDINATOR, **case_fields: Any) -> LoadedCase:
    holder = DIRECTORY.role_holder(demo_case.KOC2, baton_role)
    case = Case(
        id=demo_case.CASE_ID,
        patient=demo_case.PATIENT,
        state=state,
        baton_holder=holder,
        baton_role=baton_role,
        opened_at=NOW,
        **case_fields,
    )
    task = {
        **case_task_to_fhir(
            case,
            episode_reference="EpisodeOfCare/1",
            patient_reference="Patient/2",
            requester_reference=GP.ref,  # type: ignore[union-attr]
            owner_reference=COORDINATOR.ref,  # type: ignore[union-attr]
        ),
        "id": "5",
        "meta": {"versionId": "3"},
        "requester": {"reference": GP.ref, "identifier": {"value": demo_case.GP_ROLE}},  # type: ignore[union-attr]
    }
    return LoadedCase(task=task, episode={"managingOrganization": {"reference": KOC2.ref}}, case=case)  # type: ignore[union-attr]


def _workflow(loaded: LoadedCase, open_requests: int = 0) -> tuple[CaseWorkflow, FakeRepo]:
    repo = FakeRepo(open_requests)
    return CaseWorkflow(repo, FakeReader(loaded)), repo  # type: ignore[arg-type]


async def test_accept_names_the_accepting_coordinator_and_writes_one_locked_transaction() -> None:
    workflow, repo = _workflow(_loaded(CaseState.ODESLANO))
    actor = COORDINATOR.party()  # type: ignore[union-attr]

    outcome = await workflow.transition("c", "accept", actor=actor, directory=DIRECTORY, now=NOW)

    assert outcome.case.state is CaseState.TRIAGE
    assert outcome.case.baton_holder == actor
    [bundle] = repo.bundles
    put, audit = bundle["entry"]
    assert put["request"] == {"method": "PUT", "url": "Task/5", "ifMatch": 'W/"3"'}
    assert put["resource"]["businessStatus"]["coding"][0]["code"] == "triage"
    assert put["resource"]["owner"]["display"] == actor.display
    assert audit["resource"]["resourceType"] == "AuditEvent"
    assert audit["resource"]["entity"][0]["what"] == {"reference": "Task/5"}


async def test_wrong_role_is_a_forbidden_role_transition_and_nothing_is_written() -> None:
    workflow, repo = _workflow(_loaded(CaseState.ODESLANO))

    with pytest.raises(TransitionError) as caught:
        await workflow.transition("c", "accept", actor=GP.party(), directory=DIRECTORY, now=NOW)  # type: ignore[union-attr]

    assert caught.value.code == "forbidden_role"
    assert repo.bundles == []


async def test_request_documents_needs_an_open_request_task() -> None:
    actor = COORDINATOR.party()  # type: ignore[union-attr]
    workflow, repo = _workflow(_loaded(CaseState.TRIAGE), open_requests=0)
    with pytest.raises(TransitionError) as caught:
        await workflow.transition("c", "request_documents", actor=actor, directory=DIRECTORY, now=NOW)
    assert caught.value.code == "guard_failed"

    workflow, repo = _workflow(_loaded(CaseState.TRIAGE), open_requests=2)
    outcome = await workflow.transition("c", "request_documents", actor=actor, directory=DIRECTORY, now=NOW)
    assert outcome.case.state is CaseState.CEKA_NA_PODKLADY
    assert len(repo.bundles) == 1


async def test_baton_goes_to_a_role_level_physician_when_the_coordinator_completes() -> None:
    workflow, _ = _workflow(_loaded(CaseState.CEKA_NA_PODKLADY))

    outcome = await workflow.transition(
        "c",
        "docs_received",
        actor=COORDINATOR.party(),
        directory=DIRECTORY,
        now=NOW,  # type: ignore[union-attr]
    )

    assert outcome.case.state is CaseState.KOMPLETNI
    assert outcome.case.baton_holder is not None
    assert outcome.case.baton_holder.role is Role.KOC_PHYSICIAN
    assert outcome.case.baton_holder.display == "Lékař KOC 2"


async def test_events_without_an_endpoint_yet_are_refused() -> None:
    workflow, repo = _workflow(_loaded(CaseState.KOMPLETNI))

    with pytest.raises(InvalidInputError):
        await workflow.transition("c", "mark_ready_mdt", actor=COORDINATOR.party(), directory=DIRECTORY, now=NOW)  # type: ignore[union-attr]

    assert repo.bundles == []


# --- demo steps 5-6: MDT conclusion, feedback to the GP, delivery, closing ---

MDT_START = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)
AFTER_MDT = datetime(2026, 10, 21, 11, 0, tzinfo=PRAGUE)
CONCLUSION = "Závěr MDT: dle zápisu ze dne 21. 10. 2026."
PHYSICIAN = DIRECTORY.role("markova-lenka@koc2-nemocnice-lipova")
assert PHYSICIAN


def _audit_events(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "AuditEvent"]


def _detail(audit: dict[str, Any]) -> dict[str, str]:
    return {d["type"]: d["valueString"] for d in audit["entity"][0]["detail"]}


async def test_the_conclusion_is_signed_by_the_acting_physician_and_audited_once() -> None:
    workflow, repo = _workflow(_loaded(CaseState.PRIPRAVENO_MDT, Role.KOC_PHYSICIAN, mdt_start=MDT_START))
    actor = PHYSICIAN.party()

    outcome = await workflow.transition(
        "c", "record_mdt_conclusion", actor=actor, directory=DIRECTORY, now=AFTER_MDT, conclusion=CONCLUSION
    )

    assert outcome.case.state is CaseState.ZAVER_MDT
    assert outcome.case.conclusion_confirmed
    assert outcome.case.baton_holder is not None
    assert outcome.case.baton_holder.role is Role.COORDINATOR
    [bundle] = repo.bundles
    [audit] = _audit_events(bundle)
    assert _detail(audit)["confirmed_by"] == actor.id
    assert _detail(audit)["event"] == "record_mdt_conclusion"
    assert CONCLUSION not in json.dumps(bundle)  # clinical text is not copied into the audit trail


@pytest.mark.parametrize("who", [COORDINATOR, GP])
async def test_only_a_koc_physician_may_record_the_conclusion(who: Any) -> None:
    workflow, repo = _workflow(_loaded(CaseState.PRIPRAVENO_MDT, Role.KOC_PHYSICIAN, mdt_start=MDT_START))

    with pytest.raises(TransitionError) as caught:
        await workflow.transition(
            "c", "record_mdt_conclusion", actor=who.party(), directory=DIRECTORY, now=AFTER_MDT, conclusion=CONCLUSION
        )

    assert caught.value.code == "forbidden_role"
    assert repo.bundles == []


@pytest.mark.parametrize(
    ("state", "now", "conclusion", "code"),
    [
        (CaseState.PRIPRAVENO_MDT, NOW, CONCLUSION, "guard_failed"),  # the MDT has not started
        (CaseState.PRIPRAVENO_MDT, AFTER_MDT, "  ", "guard_failed"),  # nothing to sign
        (CaseState.PRIPRAVENO_MDT, AFTER_MDT, None, "guard_failed"),
        (CaseState.KOMPLETNI, AFTER_MDT, CONCLUSION, "invalid_transition"),  # not ready for the MDT yet
    ],
)
async def test_conclusion_guards_and_state(state: CaseState, now: datetime, conclusion: str | None, code: str) -> None:
    workflow, repo = _workflow(_loaded(state, Role.KOC_PHYSICIAN, mdt_start=MDT_START))

    with pytest.raises(TransitionError) as caught:
        await workflow.transition(
            "c", "record_mdt_conclusion", actor=PHYSICIAN.party(), directory=DIRECTORY, now=now, conclusion=conclusion
        )

    assert caught.value.code == code
    assert repo.bundles == []


async def test_feedback_goes_to_the_referring_gp_and_hands_over_the_baton() -> None:
    workflow, repo = _workflow(_loaded(CaseState.ZAVER_MDT, conclusion_confirmed=True))

    outcome = await workflow.transition(
        "c", "send_feedback", actor=COORDINATOR.party(), directory=DIRECTORY, now=AFTER_MDT
    )

    assert outcome.case.state is CaseState.ZPETNA_VAZBA_ODESLANA
    assert outcome.case.baton_holder == GP.party()
    [audit] = _audit_events(repo.bundles[0])
    assert _detail(audit)["event"] == "send_feedback"


async def test_feedback_needs_a_confirmed_conclusion_and_the_coordinator() -> None:
    unconfirmed, repo = _workflow(_loaded(CaseState.ZAVER_MDT))
    with pytest.raises(TransitionError) as no_signoff:
        await unconfirmed.transition("c", "send_feedback", actor=COORDINATOR.party(), directory=DIRECTORY, now=NOW)
    assert no_signoff.value.code == "guard_failed"

    confirmed, repo2 = _workflow(_loaded(CaseState.ZAVER_MDT, conclusion_confirmed=True))
    with pytest.raises(TransitionError) as wrong_role:
        await confirmed.transition("c", "send_feedback", actor=PHYSICIAN.party(), directory=DIRECTORY, now=NOW)
    assert wrong_role.value.code == "forbidden_role"
    assert repo.bundles == repo2.bundles == []


async def test_gp_opened_is_an_audited_read_receipt_that_keeps_state_and_baton() -> None:
    gp = GP.party()
    base = _loaded(CaseState.ZPETNA_VAZBA_ODESLANA, Role.GP, conclusion_confirmed=True)
    loaded = LoadedCase(
        task=base.task, episode=base.episode, case=base.case.model_copy(update={"baton_holder": gp})
    )  # as after send_feedback: the referring GP holds the baton
    workflow, repo = _workflow(loaded)

    outcome = await workflow.transition("c", "gp_opened", actor=gp, directory=DIRECTORY, now=AFTER_MDT)

    assert outcome.case.state is CaseState.ZPETNA_VAZBA_ODESLANA
    assert outcome.case.baton_holder == loaded.case.baton_holder
    [audit] = _audit_events(repo.bundles[0])
    assert audit["action"] == "R"


async def test_gp_opened_only_for_the_referring_gp() -> None:
    loaded = _loaded(CaseState.ZPETNA_VAZBA_ODESLANA, Role.GP)
    other_gp = PartyRef(id="jina-gp@pl-jina", display="MUDr. Jiná", role=Role.GP)

    for actor in (other_gp, COORDINATOR.party()):
        workflow, repo = _workflow(loaded)
        with pytest.raises((TransitionError, ForbiddenError)):
            await workflow.transition("c", "gp_opened", actor=actor, directory=DIRECTORY, now=NOW)
        assert repo.bundles == []


async def test_gp_opened_before_the_feedback_was_sent_is_refused() -> None:
    workflow, repo = _workflow(_loaded(CaseState.ZAVER_MDT, Role.COORDINATOR, conclusion_confirmed=True))

    with pytest.raises(TransitionError) as caught:
        await workflow.transition("c", "gp_opened", actor=GP.party(), directory=DIRECTORY, now=NOW)

    assert caught.value.code == "invalid_transition"
    assert repo.bundles == []


async def test_delivery_is_confirmed_by_the_system_only() -> None:
    loaded = _loaded(CaseState.ZPETNA_VAZBA_ODESLANA, Role.GP, conclusion_confirmed=True)
    workflow, repo = _workflow(loaded)

    for actor in (COORDINATOR.party(), GP.party(), PHYSICIAN.party()):
        with pytest.raises(TransitionError) as caught:
            await workflow.transition(
                "c", "delivery_confirmed", actor=actor, directory=DIRECTORY, now=NOW, receipt_id="r-1"
            )
        assert caught.value.code == "forbidden_role"
    with pytest.raises(TransitionError) as blank:
        await workflow.transition("c", "delivery_confirmed", actor=SYSTEM_ACTOR, directory=DIRECTORY, now=NOW)
    assert blank.value.code == "guard_failed"
    assert repo.bundles == []

    outcome = await workflow.transition(
        "c", "delivery_confirmed", actor=SYSTEM_ACTOR, directory=DIRECTORY, now=NOW, receipt_id="r-1"
    )

    assert outcome.case.delivery_receipt
    assert outcome.case.state is CaseState.ZPETNA_VAZBA_ODESLANA
    [audit] = _audit_events(repo.bundles[0])
    assert _detail(audit)["receipt_id"] == "r-1"


async def test_close_needs_the_delivery_receipt_and_the_coordinator() -> None:
    open_loop, repo = _workflow(_loaded(CaseState.ZPETNA_VAZBA_ODESLANA, Role.COORDINATOR))
    with pytest.raises(TransitionError) as no_receipt:
        await open_loop.transition("c", "close", actor=COORDINATOR.party(), directory=DIRECTORY, now=NOW)
    assert no_receipt.value.code == "guard_failed"

    delivered = _loaded(CaseState.ZPETNA_VAZBA_ODESLANA, Role.COORDINATOR, delivery_receipt=True)
    workflow, repo2 = _workflow(delivered)
    with pytest.raises(TransitionError) as wrong_role:
        await workflow.transition("c", "close", actor=PHYSICIAN.party(), directory=DIRECTORY, now=NOW)
    assert wrong_role.value.code == "forbidden_role"
    assert repo.bundles == repo2.bundles == []

    outcome = await workflow.transition("c", "close", actor=COORDINATOR.party(), directory=DIRECTORY, now=NOW)

    assert outcome.case.state is CaseState.UZAVRENO
    assert outcome.case.baton_holder is None
    [audit] = _audit_events(repo2.bundles[0])
    assert _detail(audit)["event"] == "close"
