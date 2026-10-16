"""CaseWorkflow.transition against a recording repository: baton holder, bundle shape, optimistic lock."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from app.domain.case import Case, CaseState
from app.domain.common import Role
from app.domain.errors import InvalidInputError
from app.domain.events import TransitionError
from app.fhir.cases import LoadedCase
from app.fhir.mappers.case import case_task_to_fhir
from app.fhir.workflow import CaseWorkflow
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


def _loaded(state: CaseState, baton_role: Role = Role.COORDINATOR) -> LoadedCase:
    holder = DIRECTORY.role_holder(demo_case.KOC2, baton_role)
    case = Case(
        id=demo_case.CASE_ID,
        patient=demo_case.PATIENT,
        state=state,
        baton_holder=holder,
        baton_role=baton_role,
        opened_at=NOW,
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
