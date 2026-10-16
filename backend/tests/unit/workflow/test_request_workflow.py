"""Report requests and received reports: one-click request, fulfilment, automatic `podklady_kompletni`."""

from __future__ import annotations

import copy
from datetime import date, datetime
from typing import Any

import pytest

from app.documents.ingest import normalize_upload
from app.domain.case import Case, CaseState
from app.domain.common import PartyRef, Role
from app.domain.errors import ConflictError, ForbiddenError, InvalidInputError, NotFoundError
from app.domain.events import TransitionError
from app.fhir.cases import LoadedCase
from app.fhir.mappers.case import case_task_to_fhir
from app.fhir.workflow import RequestItem, RequestWorkflow
from app.seed import demo_case
from app.settings import PRAGUE
from tests.directory_fixtures import demo_directory
from tests.document_fixtures import DOCS_DIR

NOW = datetime(2026, 10, 2, 10, 0, tzinfo=PRAGUE)  # Friday
DIRECTORY = demo_directory()
COORDINATOR = DIRECTORY.role(demo_case.COORDINATOR_ROLE)
GP = DIRECTORY.role(demo_case.GP_ROLE)
KOC2 = DIRECTORY.org(demo_case.KOC2)
assert COORDINATOR
assert GP
assert KOC2


class FakeRepo:
    def __init__(self, requests: list[dict[str, Any]] | None = None, duplicates: int = 0) -> None:
        self.requests = requests or []
        self.duplicates = duplicates
        self.bundles: list[dict[str, Any]] = []
        self.resources = {
            "CommunicationRequest/9": {"resourceType": "CommunicationRequest", "id": "9", "status": "active"}
        }

    async def search(self, resource_type: str, params: dict[str, str]) -> list[dict[str, Any]]:
        return [copy.deepcopy(r) for r in self.requests]

    async def count(self, resource_type: str, params: dict[str, str]) -> int:
        return self.duplicates if resource_type == "DocumentReference" else len(self.requests)

    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        return copy.deepcopy(self.resources[f"{resource_type}/{resource_id}"])

    async def audit_read(self, entities: list[str], *, subtype: str = "read") -> None:
        return None

    async def transaction(self, bundle: dict[str, Any]) -> dict[str, Any]:
        self.bundles.append(bundle)
        return {}


class FakeReader:
    def __init__(self, loaded: LoadedCase) -> None:
        self.loaded = loaded

    async def load(self, case_id: str) -> LoadedCase:
        return self.loaded


def loaded(state: CaseState) -> LoadedCase:
    case = Case(
        id=demo_case.CASE_ID,
        patient=demo_case.PATIENT,
        state=state,
        baton_holder=COORDINATOR.party(),  # type: ignore[union-attr]
        baton_role=Role.COORDINATOR,
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
        "meta": {"versionId": "1"},
    }
    return LoadedCase(task=task, episode={"managingOrganization": {"reference": KOC2.ref}}, case=case)  # type: ignore[union-attr]


def workflow(state: CaseState, repo: FakeRepo) -> RequestWorkflow:
    return RequestWorkflow(repo, FakeReader(loaded(state)))  # type: ignore[arg-type]


def items(n: int) -> list[RequestItem]:
    labels = [
        ("Laboratorní vyšetření 1. 9. 2026", "labjih", date(2026, 9, 1)),
        ("RTG plic 3. 9. 2026", "rc-modrany", date(2026, 9, 3)),
        ("UZ břicha 29. 9. 2026", "poliklinika-jizni", date(2026, 9, 29)),
    ]
    return [RequestItem(label, org, day) for label, org, day in labels[:n]]


def by_type(repo: FakeRepo) -> dict[str, list[dict[str, Any]]]:
    [bundle] = repo.bundles
    result: dict[str, list[dict[str, Any]]] = {}
    for entry in bundle["entry"]:
        result.setdefault(entry["resource"]["resourceType"], []).append(entry["resource"])
    return result


def open_request(number: int, doc: str | None = None) -> dict[str, Any]:
    task = {
        "resourceType": "Task",
        "id": f"r{number}",
        "meta": {"versionId": "1"},
        "identifier": [
            {"system": "https://stafeta.example/fhir/sid/request-task", "value": f"{demo_case.CASE_ID}-req-{number}"}
        ],
        "status": "completed" if doc else "requested",
        "description": "Vyžádat výsledek: RTG plic",
        "basedOn": [{"reference": "CommunicationRequest/9"}],
        "owner": {"reference": COORDINATOR.ref, "identifier": {"value": demo_case.COORDINATOR_ROLE}, "display": "x"},  # type: ignore[union-attr]
        "performerType": [
            {"coding": [{"system": "https://stafeta.example/fhir/CodeSystem/workflow-role", "code": "coordinator"}]}
        ],
        "restriction": {
            "period": {"end": "2026-10-06T23:59:00+02:00"},
            "recipient": [{"reference": "Organization/3", "display": "Radiologické centrum Modřany"}],
        },
    }
    return task


async def test_one_click_creates_requests_and_moves_the_case_to_waiting() -> None:
    repo = FakeRepo()

    outcome = await workflow(CaseState.TRIAGE, repo).create_requests(
        "c",
        items(3),
        actor=COORDINATOR.party(),
        directory=DIRECTORY,
        now=NOW,  # type: ignore[union-attr]
    )

    assert outcome.case.state is CaseState.CEKA_NA_PODKLADY
    created = by_type(repo)
    assert len(created["CommunicationRequest"]) == 3
    assert len(created["Task"]) == 4  # 3 requests + the case Task
    request_task = created["Task"][0]
    assert request_task["restriction"]["period"]["end"].startswith("2026-10-06T23:59")  # Fri + 2 working days
    assert request_task["businessStatus"]["coding"][0]["code"] == "objednano"
    assert request_task["owner"]["identifier"]["value"] == demo_case.COORDINATOR_ROLE
    assert "Laboratorní vyšetření 1. 9. 2026" in created["CommunicationRequest"][0]["payload"][0]["contentString"]
    assert created["Task"][-1]["businessStatus"]["coding"][0]["code"] == "ceka_na_podklady"


async def test_ad_hoc_request_in_a_waiting_case_does_not_change_the_state() -> None:
    repo = FakeRepo([open_request(1)])

    outcome = await workflow(CaseState.CEKA_NA_PODKLADY, repo).create_requests(
        "c",
        [RequestItem("Epikríza PL 4. 9. 2026", demo_case.GP_PRACTICE)],
        actor=COORDINATOR.party(),  # type: ignore[union-attr]
        directory=DIRECTORY,
        now=NOW,
    )

    assert outcome.case.state is CaseState.CEKA_NA_PODKLADY
    created = by_type(repo)
    assert "Task" in created
    assert created["Task"][0]["identifier"][0]["value"].endswith("-req-2")
    codes = [t["code"]["coding"][0]["code"] for t in created["Task"]]
    assert codes == ["request-report", "coordinate-case"]  # the case Task is PUT too: serialises concurrent writers


@pytest.mark.parametrize("state", [CaseState.ODESLANO, CaseState.KOMPLETNI, CaseState.UZAVRENO])
async def test_requests_are_refused_outside_triage_and_waiting(state: CaseState) -> None:
    with pytest.raises(TransitionError) as caught:
        await workflow(state, FakeRepo()).create_requests(
            "c",
            items(1),
            actor=COORDINATOR.party(),
            directory=DIRECTORY,
            now=NOW,  # type: ignore[union-attr]
        )

    assert caught.value.code == "invalid_transition"


async def test_only_the_coordinator_requests_and_the_workplace_must_exist() -> None:
    with pytest.raises(TransitionError) as caught:
        await workflow(CaseState.TRIAGE, FakeRepo()).create_requests(
            "c",
            items(1),
            actor=GP.party(),
            directory=DIRECTORY,
            now=NOW,  # type: ignore[union-attr]
        )
    assert caught.value.code == "forbidden_role"

    with pytest.raises(InvalidInputError):
        await workflow(CaseState.TRIAGE, FakeRepo()).create_requests(
            "c",
            [RequestItem("x", "nikde")],
            actor=COORDINATOR.party(),
            directory=DIRECTORY,
            now=NOW,  # type: ignore[union-attr]
        )


def upload(name: str = "03_RTG_plic_2026-09-03.docx") -> Any:
    return normalize_upload(name, (DOCS_DIR / name).read_bytes())


async def test_last_report_completes_the_request_and_the_case() -> None:
    repo = FakeRepo([open_request(1)])

    outcome = await workflow(CaseState.CEKA_NA_PODKLADY, repo).receive_document(
        "c",
        upload(),
        authored_at=date(2026, 9, 3),
        request_id=f"{demo_case.CASE_ID}-req-1",
        actor=COORDINATOR.party(),  # type: ignore[union-attr]
        directory=DIRECTORY,
        now=NOW,
    )

    assert outcome.case_event == "podklady_kompletni"
    assert outcome.case.state is CaseState.KOMPLETNI
    assert outcome.open_requests_remaining == 0
    created = by_type(repo)
    request = next(t for t in created["Task"] if t["id"] == "r1")
    assert request["status"] == "completed"
    assert request["businessStatus"]["coding"][0]["code"] == "vysledek_dorucen"
    assert request["output"][0]["valueReference"]["identifier"]["value"] == "03_RTG_plic_2026-09-03"
    assert created["CommunicationRequest"][0]["status"] == "completed"
    assert created["DocumentReference"][0]["date"].startswith("2026-10-02T10:00")  # received = now
    assert created["Task"][-1]["businessStatus"]["coding"][0]["code"] == "kompletni"
    assert created["Task"][-1]["owner"]["display"] == "Lékař KOC 2"


async def test_report_with_other_requests_still_open_keeps_the_case_waiting() -> None:
    repo = FakeRepo([open_request(1), open_request(2)])

    outcome = await workflow(CaseState.CEKA_NA_PODKLADY, repo).receive_document(
        "c",
        upload(),
        authored_at=date(2026, 9, 3),
        request_id=f"{demo_case.CASE_ID}-req-1",
        actor=COORDINATOR.party(),  # type: ignore[union-attr]
        directory=DIRECTORY,
        now=NOW,
    )

    assert outcome.case_event is None
    assert outcome.open_requests_remaining == 1
    assert outcome.case.state is CaseState.CEKA_NA_PODKLADY
    assert "kompletni" not in str(by_type(repo).get("Task", []))


async def test_duplicate_document_unknown_and_fulfilled_request_are_refused() -> None:
    common: dict[str, Any] = {
        "authored_at": date(2026, 9, 3),
        "actor": COORDINATOR.party(),  # type: ignore[union-attr]
        "directory": DIRECTORY,
        "now": NOW,
    }
    with pytest.raises(ConflictError):
        await workflow(CaseState.CEKA_NA_PODKLADY, FakeRepo([open_request(1)], duplicates=1)).receive_document(
            "c", upload(), request_id=None, **common
        )
    with pytest.raises(NotFoundError):
        await workflow(CaseState.CEKA_NA_PODKLADY, FakeRepo([open_request(1)])).receive_document(
            "c", upload(), request_id="nope-req-9", **common
        )
    with pytest.raises(ConflictError):
        await workflow(CaseState.CEKA_NA_PODKLADY, FakeRepo([open_request(1, doc="x")])).receive_document(
            "c", upload(), request_id=f"{demo_case.CASE_ID}-req-1", **common
        )


async def test_report_without_a_request_is_stored_and_the_state_is_unchanged() -> None:
    repo = FakeRepo([open_request(1)])

    outcome = await workflow(CaseState.CEKA_NA_PODKLADY, repo).receive_document(
        "c",
        upload("04_PL_epikriza_2026-09-04.docx"),
        authored_at=date(2026, 9, 4),
        request_id=None,
        actor=COORDINATOR.party(),  # type: ignore[union-attr]
        directory=DIRECTORY,
        now=NOW,
    )

    assert outcome.case_event is None
    assert outcome.open_requests_remaining == 1
    assert set(by_type(repo)) == {"DocumentReference", "Task"}  # + the case Task PUT: serialises writers


async def test_patient_role_may_not_upload() -> None:
    with pytest.raises(ForbiddenError):
        await workflow(CaseState.TRIAGE, FakeRepo()).receive_document(
            "c",
            upload(),
            authored_at=date(2026, 9, 3),
            request_id=None,
            actor=PartyRef(id="p1", display="Pacient", role=Role.PATIENT),
            directory=DIRECTORY,
            now=NOW,
        )


async def test_actors_outside_the_case_are_refused_everywhere() -> None:
    other_gp = PartyRef(id="jiny@pl-jinde", display="Jiný PL", role=Role.GP)
    other_koc = DIRECTORY.role("svoboda-martin@koc2-nemocnice-lipova")
    assert other_koc
    # a coordinator of another KOC: the same person with an organisation that does not manage the case
    outsider = LoadedCase(
        task=loaded(CaseState.TRIAGE).task,
        episode={"managingOrganization": {"reference": "Organization/999"}},
        case=loaded(CaseState.TRIAGE).case,
    )
    wf = RequestWorkflow(FakeRepo(), FakeReader(outsider))  # type: ignore[arg-type]

    with pytest.raises(ForbiddenError):
        await wf.list_requests("c", actor=COORDINATOR.party(), directory=DIRECTORY)  # type: ignore[union-attr]
    with pytest.raises(ForbiddenError):
        await workflow(CaseState.TRIAGE, FakeRepo()).list_requests("c", actor=other_gp, directory=DIRECTORY)
    with pytest.raises(ForbiddenError):
        await workflow(CaseState.TRIAGE, FakeRepo()).transition(
            "c", "accept", actor=other_gp, directory=DIRECTORY, now=NOW
        )
    assert (
        await workflow(CaseState.TRIAGE, FakeRepo()).list_requests("c", actor=GP.party(), directory=DIRECTORY)
    ) == []  # type: ignore[union-attr]


async def test_only_the_coordinator_links_a_report_to_a_request() -> None:
    with pytest.raises(ForbiddenError):
        await workflow(CaseState.CEKA_NA_PODKLADY, FakeRepo([open_request(1)])).receive_document(
            "c",
            upload(),
            authored_at=date(2026, 9, 3),
            request_id=f"{demo_case.CASE_ID}-req-1",
            actor=GP.party(),  # type: ignore[union-attr]
            directory=DIRECTORY,
            now=NOW,
        )


async def test_report_is_accepted_while_the_case_is_postponed_and_the_state_stays() -> None:
    repo = FakeRepo([open_request(1)])
    wf = workflow(CaseState.CEKA_NA_PODKLADY, repo)
    wf._reader.loaded = LoadedCase(  # type: ignore[attr-defined]
        task=loaded(CaseState.CEKA_NA_PODKLADY).task,
        episode=loaded(CaseState.CEKA_NA_PODKLADY).episode,
        case=loaded(CaseState.CEKA_NA_PODKLADY).case.model_copy(update={"odlozeny": True}),
    )

    outcome = await wf.receive_document(
        "c",
        upload(),
        authored_at=date(2026, 9, 3),
        request_id=f"{demo_case.CASE_ID}-req-1",
        actor=COORDINATOR.party(),  # type: ignore[union-attr]
        directory=DIRECTORY,
        now=NOW,
    )

    assert outcome.case.state is CaseState.CEKA_NA_PODKLADY
    assert outcome.case.odlozeny is True
    assert outcome.case_event is None  # the machine refuses events while postponed; docs_received follows after resume
    request = next(t for t in by_type(repo)["Task"] if t["id"] == "r1")
    assert request["status"] == "completed"


async def test_linked_report_keeps_the_workplace_reference_and_unlinked_upload_is_locked() -> None:
    repo = FakeRepo([open_request(1)])
    await workflow(CaseState.CEKA_NA_PODKLADY, repo).receive_document(
        "c",
        upload(),
        authored_at=date(2026, 9, 3),
        request_id=f"{demo_case.CASE_ID}-req-1",
        actor=COORDINATOR.party(),  # type: ignore[union-attr]
        directory=DIRECTORY,
        now=NOW,
    )
    document = by_type(repo)["DocumentReference"][0]
    assert document["custodian"]["reference"] == "Organization/3"

    repo = FakeRepo()
    await workflow(CaseState.CEKA_NA_PODKLADY, repo).receive_document(
        "c",
        upload(),
        authored_at=date(2026, 9, 3),
        request_id=None,
        actor=COORDINATOR.party(),  # type: ignore[union-attr]
        directory=DIRECTORY,
        now=NOW,
    )
    [bundle] = repo.bundles
    put = next(e for e in bundle["entry"] if e["request"]["method"] == "PUT")
    assert put["request"]["ifMatch"] == 'W/"1"'
