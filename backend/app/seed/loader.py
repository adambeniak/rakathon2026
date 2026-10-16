"""Seed scenarios. Every resource is created with `ensure` (search by identifier, then conditional create), so a
second run writes nothing — no resources and no AuditEvents.

- `story` (default): directory, users, patient (+ daughter, coverage), the case in state `pripraveno_mdt`
  (snapshot as of the MDT start) and all 13 documents with their simulated received times.
- `demo-start`: directory, users and the patient only; the GP creates the case live in demo step 1.
"""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from app.domain.case import Case
from app.domain.common import PartyRef
from app.domain.document import SourceDocument
from app.fhir.client import Resource
from app.fhir.mappers.case import case_task_to_fhir, episode_of_care_to_fhir
from app.fhir.mappers.directory import organization_to_fhir, practitioner_role_to_fhir, practitioner_to_fhir
from app.fhir.mappers.document import document_to_fhir
from app.fhir.mappers.patient import coverage_to_fhir, patient_to_fhir, related_person_to_fhir
from app.fhir.repository import EnsureResult
from app.retrieval.indexing import IndexResult
from app.seed import demo_case
from app.settings import REPO_ROOT

DEFAULT_DATA_DIR = REPO_ROOT / "data" / "raw" / "Pacient"

# Dependents first: used by `--reset` to delete everything carrying the demo tag. AuditEvents are never deleted.
RESET_ORDER = (
    "Provenance",
    "Composition",
    "Communication",
    "CommunicationRequest",
    "Consent",
    "DocumentReference",
    "Observation",
    "MedicationStatement",
    "DiagnosticReport",
    "Condition",
    "CarePlan",
    "ServiceRequest",
    "Task",
    "EpisodeOfCare",
    "Coverage",
    "RelatedPerson",
    "Patient",
    "PractitionerRole",
    "Practitioner",
    "Organization",
)


class Scenario(StrEnum):
    STORY = "story"
    DEMO_START = "demo-start"


class SeedRepository(Protocol):
    async def ensure(self, resource: Resource) -> EnsureResult: ...

    async def read(self, resource_type: str, resource_id: str) -> Resource: ...


class SeedIndexer(Protocol):
    async def index(self, resource: Resource, *, force: bool = False) -> IndexResult: ...

    async def is_indexed(self, reference: str) -> bool: ...


class SeedReport:
    def __init__(self) -> None:
        self.created: Counter[str] = Counter()
        self.existing: Counter[str] = Counter()
        self.chunks_indexed = 0

    def record(self, result: EnsureResult) -> None:
        (self.created if result.created else self.existing)[result.resource_type] += 1

    @property
    def total_created(self) -> int:
        return sum(self.created.values())

    def lines(self) -> list[str]:
        types = sorted(set(self.created) | set(self.existing))
        return [f"{t:<18} created {self.created[t]:>3}   existing {self.existing[t]:>3}" for t in types]


async def seed(
    repo: SeedRepository,
    scenario: Scenario,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    indexer: SeedIndexer | None = None,
) -> SeedReport:
    """With `indexer`, every document is also chunked and embedded into Stafeta.DocChunk (skipped if present)."""
    report = SeedReport()

    async def ensure(resource: Resource) -> str:
        result = await repo.ensure(resource)
        report.record(result)
        return result.reference

    org_refs: dict[str, str] = {}
    for org in demo_case.ORGANIZATIONS:
        org_refs[org.id] = await ensure(organization_to_fhir(org))
    org_names = {org.id: org.name for org in demo_case.ORGANIZATIONS}

    role_refs: dict[str, str] = {}
    parties: dict[str, PartyRef] = {}
    for person in demo_case.PEOPLE:
        practitioner_ref = await ensure(practitioner_to_fhir(person.practitioner))
        role = person.role
        role_refs[role.id] = await ensure(
            practitioner_role_to_fhir(
                role,
                practitioner_reference=practitioner_ref,
                practitioner_display=person.practitioner.display_name,
                organization_reference=org_refs[role.organization_id],
                organization_display=org_names[role.organization_id],
            )
        )
        parties[role.id] = PartyRef(id=role.id, display=person.practitioner.display_name, role=role.role)

    patient = demo_case.PATIENT
    patient_ref = await ensure(patient_to_fhir(patient, general_practitioner=role_refs[demo_case.GP_ROLE]))
    if scenario is Scenario.DEMO_START:
        return report

    await ensure(related_person_to_fhir(demo_case.CONTACT_PERSON, patient_reference=patient_ref, patient=patient))
    await ensure(
        coverage_to_fhir(
            patient=patient,
            patient_reference=patient_ref,
            payor_reference=org_refs[demo_case.INSURER],
            payor_display=org_names[demo_case.INSURER],
        )
    )

    mdt_chair = parties[demo_case.MDT_CHAIR_ROLE]
    case = Case(
        id=demo_case.CASE_ID,
        patient=patient,
        state=demo_case.CASE_STATE,
        baton_holder=mdt_chair.model_copy(update={"display": demo_case.MDT_BATON_DISPLAY}),
        next_deadline=demo_case.MDT_START,
        opened_at=demo_case.CASE_OPENED_AT,
    )
    episode_ref = await ensure(
        episode_of_care_to_fhir(
            case,
            patient_reference=patient_ref,
            managing_organization_reference=org_refs[demo_case.KOC2],
            care_manager=(parties[demo_case.COORDINATOR_ROLE], role_refs[demo_case.COORDINATOR_ROLE]),
        )
    )
    await ensure(
        case_task_to_fhir(
            case,
            episode_reference=episode_ref,
            patient_reference=patient_ref,
            requester_reference=role_refs[demo_case.GP_ROLE],
            owner_reference=role_refs[demo_case.MDT_CHAIR_ROLE],
        )
    )

    for doc in demo_case.DOCUMENTS:
        source = SourceDocument(
            doc_id=doc.doc_id,
            title=doc.title,
            type_code=doc.loinc,
            authored_at=doc.authored_at,
            received_at=doc.received_at,
            custodian=org_names[doc.custodian],
            author=parties[doc.author_role].display,
            file_name=doc.file_name,
        )
        resource = document_to_fhir(
            source,
            (data_dir / doc.file_name).read_bytes(),
            patient_reference=patient_ref,
            episode_reference=episode_ref,
            custodian_reference=org_refs[doc.custodian],
            author_reference=role_refs[doc.author_role],
        )
        result = await repo.ensure(resource)
        report.record(result)
        if indexer is None or (not result.created and await indexer.is_indexed(result.reference)):
            continue
        # An existing document is indexed from what IRIS stores, never from the local file (which may differ).
        stored = {**resource, "id": result.id} if result.created else await repo.read("DocumentReference", result.id)
        indexed = await indexer.index(stored)
        report.chunks_indexed += 0 if indexed.skipped else indexed.chunks
    return report
