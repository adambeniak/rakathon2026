from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

import pytest

from app.fhir.client import Resource
from app.fhir.mappers.plan_definition import plan_definition_to_template
from app.fhir.repository import EnsureResult, primary_identifier
from app.fhir.systems import SID_SOURCE_DOCUMENT
from app.seed import demo_case
from app.seed.loader import DEFAULT_DATA_DIR, Scenario, seed
from app.settings import PRAGUE, REPO_ROOT

AS_OF = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)
GOLDEN = json.loads((REPO_ROOT / "data/golden/expected_handover_2026-10-21.json").read_text(encoding="utf-8"))


class InMemoryRepository:
    """Implements the `ensure` contract of FhirRepository without a server."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str, str], Resource] = {}
        self.writes: Counter[str] = Counter()

    async def ensure(self, resource: Resource) -> EnsureResult:
        resource_type = resource["resourceType"]
        key = (resource_type, *primary_identifier(resource))
        if key in self.store:
            return EnsureResult(resource_type, self.store[key]["id"], created=False)
        stored = {**resource, "id": str(len(self.store) + 1)}
        self.store[key] = stored
        self.writes[resource_type] += 1
        return EnsureResult(resource_type, stored["id"], created=True)

    async def read(self, resource_type: str, resource_id: str) -> Resource:
        return next(r for (t, _, _), r in self.store.items() if t == resource_type and r["id"] == resource_id)

    async def ensure_by_url(self, resource: Resource) -> EnsureResult:
        resource_type = resource["resourceType"]
        key = (resource_type, resource["url"], "")
        if key in self.store:
            return EnsureResult(resource_type, self.store[key]["id"], created=False)
        stored = {k: v for k, v in resource.items() if k != "id"} | {"id": str(len(self.store) + 1)}
        self.store[key] = stored
        self.writes[resource_type] += 1
        return EnsureResult(resource_type, stored["id"], created=True)

    def of_type(self, resource_type: str) -> list[Resource]:
        return [r for (t, _, _), r in self.store.items() if t == resource_type]


def test_thirteen_documents_exist_on_disk() -> None:
    assert len(demo_case.DOCUMENTS) == 13
    for doc in demo_case.DOCUMENTS:
        assert (DEFAULT_DATA_DIR / doc.file_name).is_file(), doc.file_name


def test_received_times_match_golden_as_of_split() -> None:
    known = {d.doc_id for d in demo_case.DOCUMENTS if d.received_at <= AS_OF and d.authored_at <= AS_OF.date()}
    assert known == set(GOLDEN["included_documents"])
    assert {d.doc_id for d in demo_case.DOCUMENTS} - known == {e["doc"] for e in GOLDEN["excluded_documents"]}


def test_received_never_before_authored_and_dst_is_handled() -> None:
    for doc in demo_case.DOCUMENTS:
        assert doc.received_at.date() >= doc.authored_at, doc.doc_id
    by_id = {d.doc_id: d for d in demo_case.DOCUMENTS}
    assert by_id["11_Histologie_KOC2_2026-10-19"].received_at.isoformat() == "2026-10-19T16:00:00+02:00"
    assert by_id["12_Algeziologie_2026-10-26"].received_at.isoformat() == "2026-10-26T12:00:00+01:00"


def test_people_reference_known_organizations() -> None:
    org_ids = {o.id for o in demo_case.ORGANIZATIONS}
    role_ids = {p.role.id for p in demo_case.PEOPLE}
    assert {p.role.organization_id for p in demo_case.PEOPLE} <= org_ids
    assert {d.author_role for d in demo_case.DOCUMENTS} <= role_ids
    named = {demo_case.GP_ROLE, demo_case.COORDINATOR_ROLE, demo_case.MDT_CHAIR_ROLE, demo_case.REVIEWER_ROLE}
    assert named <= role_ids


async def test_story_scenario_is_idempotent() -> None:
    repo = InMemoryRepository()

    first = await seed(repo, Scenario.STORY)
    second = await seed(repo, Scenario.STORY)

    assert first.created == Counter(
        {
            "Organization": 8,
            "Practitioner": 18,
            "PractitionerRole": 18,
            "Patient": 1,
            "RelatedPerson": 1,
            "Coverage": 1,
            "EpisodeOfCare": 1,
            "Task": 1,
            "DocumentReference": 13,
            "PlanDefinition": 1,
        }
    )
    assert second.total_created == 0
    assert sum(second.existing.values()) == sum(first.created.values())


async def test_story_case_and_documents_are_linked() -> None:
    repo = InMemoryRepository()
    await seed(repo, Scenario.STORY)

    [task] = repo.of_type("Task")
    [episode] = repo.of_type("EpisodeOfCare")
    assert task["businessStatus"]["coding"][0]["code"] == "pripraveno_mdt"
    assert task["focus"] == {"reference": f"EpisodeOfCare/{episode['id']}"}
    assert task["owner"]["display"] == demo_case.MDT_BATON_DISPLAY
    documents = repo.of_type("DocumentReference")
    assert {d["context"]["encounter"][0]["reference"] for d in documents} == {f"EpisodeOfCare/{episode['id']}"}
    doc_ids = {i["value"] for d in documents for i in d["identifier"] if i["system"] == SID_SOURCE_DOCUMENT}
    assert doc_ids == {d.doc_id for d in demo_case.DOCUMENTS}


async def test_demo_start_seeds_directory_and_patient_only() -> None:
    repo = InMemoryRepository()

    report = await seed(repo, Scenario.DEMO_START)

    assert set(report.created) == {"Organization", "Practitioner", "PractitionerRole", "Patient", "PlanDefinition"}


async def test_pathway_template_is_seeded_by_url_and_usable() -> None:
    repo = InMemoryRepository()
    await seed(repo, Scenario.STORY)

    [plan] = repo.of_type("PlanDefinition")
    assert plan["url"] == "https://stafeta.example/fhir/PlanDefinition/pancreas-dx"
    assert plan_definition_to_template(plan).title == "Karcinom pankreatu – diagnostika"


async def test_seeded_case_carries_the_mdt_start() -> None:
    repo = InMemoryRepository()
    await seed(repo, Scenario.STORY)

    [task] = repo.of_type("Task")
    [extension] = task["extension"]
    assert extension["valueDateTime"] == demo_case.MDT_START.isoformat()


@pytest.mark.parametrize("missing", ["email"])
async def test_seed_does_not_invent_values_the_documents_lack(missing: str) -> None:
    repo = InMemoryRepository()
    await seed(repo, Scenario.STORY)

    [patient] = repo.of_type("Patient")
    telecom: list[dict[str, Any]] = patient["telecom"]
    assert all(t["system"] != missing for t in telecom)


@pytest.mark.parametrize("scenario", [Scenario.STORY, Scenario.DEMO_START])
async def test_both_scenarios_seed_a_reviewer_of_the_insurer(scenario: Scenario) -> None:
    repo = InMemoryRepository()
    await seed(repo, scenario)

    reviewers = [r for r in repo.of_type("PractitionerRole") if r["identifier"][0]["value"] == demo_case.REVIEWER_ROLE]
    [reviewer] = reviewers
    assert reviewer["code"][0]["coding"][0]["code"] == "reviewer"
    insurer = next(o for o in repo.of_type("Organization") if o["name"].startswith("Zdravotní pojišťovna"))
    assert reviewer["organization"]["reference"] == f"Organization/{insurer['id']}"
