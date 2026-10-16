"""TriageReader: letter -> extraction (recorded) -> proposals, for a case created from letter 07."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from app.documents.ingest import normalize_upload
from app.domain.case import Case, CaseState
from app.domain.common import Role
from app.domain.document import SourceDocument
from app.extraction.llm import CACHE_MODEL, LLMClient
from app.fhir.cases import LoadedCase
from app.fhir.mappers.case import case_task_to_fhir
from app.fhir.mappers.document import document_to_fhir
from app.fhir.triage import TriageReader
from app.seed import demo_case
from app.settings import PRAGUE
from tests.directory_fixtures import demo_directory
from tests.document_fixtures import DOCS_DIR

NOW = datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE)
DIRECTORY = demo_directory()
COORDINATOR = DIRECTORY.role(demo_case.COORDINATOR_ROLE)
KOC2 = DIRECTORY.org(demo_case.KOC2)
assert COORDINATOR
assert KOC2


def _letter_resource() -> dict[str, Any]:
    path = DOCS_DIR / "07_PL_zadost_KOC2_2026-10-02.docx"
    upload = normalize_upload(path.name, path.read_bytes())
    resource = document_to_fhir(
        SourceDocument(
            doc_id=upload.doc.doc_id,
            title="Žádost",
            authored_at=upload.doc.authored_date,  # type: ignore[arg-type]
            received_at=NOW,
            file_name=path.name,
        ),
        upload.content,
        patient_reference="Patient/2",
        episode_reference="EpisodeOfCare/1",
        custodian_reference=None,
        author_reference=None,
    )
    return {**resource, "id": "40"}


class FakeRepo:
    def __init__(self, with_letter: bool = True) -> None:
        self.with_letter = with_letter
        self.letter = _letter_resource()

    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        if resource_type == "ServiceRequest":
            return {"id": resource_id, "supportingInfo": [{"reference": "DocumentReference/40"}]}
        return copy.deepcopy(self.letter)

    async def search(self, resource_type: str, params: dict[str, str]) -> list[dict[str, Any]]:
        return [copy.deepcopy(self.letter)]

    async def audit_read(self, entities: list[str], *, subtype: str = "read") -> None:
        self.audited = entities

    async def audit_extract(self) -> None:
        self.extracted = True


class FakeReader:
    def __init__(self, based_on: str | None) -> None:
        case = Case(
            id=demo_case.CASE_ID,
            patient=demo_case.PATIENT,
            state=CaseState.TRIAGE,
            baton_holder=COORDINATOR.party(),  # type: ignore[union-attr]
            baton_role=Role.COORDINATOR,
        )
        task = {
            **case_task_to_fhir(
                case,
                episode_reference="EpisodeOfCare/1",
                patient_reference="Patient/2",
                requester_reference=None,
                owner_reference=COORDINATOR.ref,  # type: ignore[union-attr]
                based_on_reference=based_on,
            ),
            "id": "5",
        }
        self.loaded = LoadedCase(task=task, episode={"managingOrganization": {"reference": KOC2.ref}}, case=case)

    async def load(self, case_id: str) -> LoadedCase:
        return self.loaded


def reader(based_on: str | None, repo: FakeRepo) -> TriageReader:
    return TriageReader(repo, FakeReader(based_on), LLMClient(model=CACHE_MODEL, cache_only=True))  # type: ignore[arg-type]


async def test_case_from_letter_07_proposes_the_five_listed_reports() -> None:
    repo = FakeRepo()

    view = await reader("ServiceRequest/30", repo).proposals("c", DIRECTORY, COORDINATOR.party())

    assert view.source_doc_id == "07_PL_zadost_KOC2_2026-10-02"
    assert [p.recipient_org_id for p in view.proposals] == [
        "labjih", "rc-modrany", "poliklinika-jizni", "poliklinika-jizni", "kardio-jesenice"
    ]  # fmt: skip
    assert {p.status.value for p in view.proposals} == {"missing"}
    assert repo.extracted
    assert "DocumentReference/40" in repo.audited  # the read of the letter is audited


async def test_case_without_a_referral_has_no_proposals() -> None:
    view = await reader(None, FakeRepo()).proposals("c", DIRECTORY, COORDINATOR.party())

    assert view.source_doc_id is None
    assert view.proposals == []
