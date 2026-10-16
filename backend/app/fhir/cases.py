"""Read side of cases: FHIR (coordinating Task + Patient + Coverage + DocumentReference) -> domain models.

Every successful read of clinical content writes one AuditEvent (action R) through the repository.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.domain.case import Case
from app.domain.document import SourceDocument
from app.domain.errors import NotFoundError
from app.domain.evidence import Evidence
from app.fhir.client import Resource
from app.fhir.errors import FhirNotFoundError
from app.fhir.mappers.case import case_from_fhir
from app.fhir.mappers.document import document_content, document_from_fhir
from app.fhir.mappers.patient import insurer_code_from_coverage, patient_from_fhir
from app.fhir.mappers.referral import diagnosis_from_service_request
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_TASK_CODE, SID_CASE_TASK, TASK_CODE_COORDINATE_CASE


@dataclass(frozen=True)
class CaseExtras:
    """Header facts read around the coordinating Task; every field is optional (e.g. the seeded story case has no
    ServiceRequest, so no diagnosis)."""

    koc_name: str | None = None
    gp_name: str | None = None
    gp_practice: str | None = None
    diagnosis_code: str | None = None
    diagnosis_text: str | None = None
    diagnosis_evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class CaseOverview:
    case: Case
    document_count: int
    extras: CaseExtras = field(default_factory=CaseExtras)


@dataclass(frozen=True)
class CaseDetailView:
    case: Case
    documents: list[SourceDocument]
    extras: CaseExtras = field(default_factory=CaseExtras)


@dataclass(frozen=True)
class LoadedCase:
    """The coordinating Task as stored (id, version), its EpisodeOfCare and the domain case. `load` audits the read;
    the writer records its own write in the transaction."""

    task: Resource
    episode: Resource
    case: Case


@dataclass(frozen=True)
class CaseContentsView:
    case: Case
    documents: list[SourceDocument]
    contents: dict[str, bytes]


@dataclass(frozen=True)
class CaseHeader:
    """The case without its documents, plus the references coordination resources attach to."""

    case: Case
    task_reference: str  # the coordinating Task, target of `Task.partOf`
    patient_reference: str


class CaseReader:
    def __init__(self, repository: FhirRepository) -> None:
        self._repo = repository

    async def list_cases(self) -> list[CaseOverview]:
        tasks = await self._repo.search(
            "Task", {"code": f"{CS_TASK_CODE}|{TASK_CODE_COORDINATE_CASE}", "_count": "100"}
        )
        overviews = await asyncio.gather(*(self._overview(task) for task in tasks))
        result = sorted(overviews, key=lambda o: o.case.id)
        if tasks:
            await self._repo.audit_read(_audit_entities(tasks), subtype="search-type")
        return result

    async def case_patient(self, case_id: str) -> tuple[str, str]:
        """(coordinating Task reference, Patient reference) of a case. Ids only: no clinical content is read."""
        task = await self._repo.find_by_identifier("Task", SID_CASE_TASK, case_id)
        if task is None:
            raise NotFoundError("case", case_id)
        return f"Task/{task['id']}", _patient(task)

    async def get_case(self, case_id: str) -> CaseDetailView:
        task = await self._repo.find_by_identifier("Task", SID_CASE_TASK, case_id)
        if task is None:
            raise NotFoundError("case", case_id)
        case, extras = await asyncio.gather(self._case(task), self._extras(task))
        resources = await self._repo.search("DocumentReference", {"encounter": _focus(task), "_count": "100"})
        documents = sorted((document_from_fhir(r) for r in resources), key=lambda d: (d.received_at, d.doc_id))
        await self._repo.audit_read(
            [*_audit_entities([task]), *(f"DocumentReference/{r['id']}" for r in resources)], subtype="read"
        )
        return CaseDetailView(case=case, documents=documents, extras=extras)

    async def get_case_contents(self, case_id: str) -> CaseContentsView:
        """Case, document metadata and the documents' DOCX bytes (handover assembly). Audited as one read."""
        task = await self._repo.find_by_identifier("Task", SID_CASE_TASK, case_id)
        if task is None:
            raise NotFoundError("case", case_id)
        case = await self._case(task)
        resources = await self._repo.search("DocumentReference", {"encounter": _focus(task), "_count": "100"})
        await self._repo.audit_read(
            [*_audit_entities([task]), *(f"DocumentReference/{r['id']}" for r in resources)], subtype="read"
        )
        documents: list[SourceDocument] = []
        contents: dict[str, bytes] = {}
        for resource in resources:
            document = document_from_fhir(resource)
            documents.append(document)
            contents[document.doc_id] = document_content(resource)
        documents.sort(key=lambda d: (d.received_at, d.doc_id))
        return CaseContentsView(case=case, documents=documents, contents=contents)

    async def overview(self, case_id: str) -> CaseOverview:
        """Summary of one case (fresh read, e.g. after a write); the read is audited like `list_cases`."""
        task = await self._repo.find_by_identifier("Task", SID_CASE_TASK, case_id)
        if task is None:
            raise NotFoundError("case", case_id)
        result = await self._overview(task)
        await self._repo.audit_read(_audit_entities([task]), subtype="read")
        return result

    async def load(self, case_id: str) -> LoadedCase:
        task = await self._repo.find_by_identifier("Task", SID_CASE_TASK, case_id)
        if task is None:
            raise NotFoundError("case", case_id)
        episode_reference = _focus(task)
        episode, case = await asyncio.gather(self._repo.read(*episode_reference.split("/", 1)), self._case(task))
        await self._repo.audit_read(_audit_entities([task]), subtype="read")  # clinical content was read
        return LoadedCase(task=task, episode=episode, case=case)

    async def _overview(self, task: Resource) -> CaseOverview:
        case, document_count, extras = await asyncio.gather(
            self._case(task),
            self._repo.count("DocumentReference", {"encounter": _focus(task)}),
            self._extras(task),
        )
        return CaseOverview(case=case, document_count=document_count, extras=extras)

    async def _extras(self, task: Resource) -> CaseExtras:
        episode_ref = _focus(task)
        requester_ref = task.get("requester", {}).get("reference")
        request_ref = next(
            (
                b.get("reference")
                for b in task.get("basedOn", [])
                if str(b.get("reference", "")).startswith("ServiceRequest/")
            ),
            None,
        )
        episode, role, request = await asyncio.gather(
            self._repo.read(*episode_ref.split("/", 1)),
            self._read_optional(requester_ref, "PractitionerRole"),
            self._read_optional(request_ref, "ServiceRequest"),
        )
        koc = await self._read_optional(episode.get("managingOrganization", {}).get("reference"), "Organization")
        code, text, evidence = diagnosis_from_service_request(request) if request else (None, None, [])
        return CaseExtras(
            koc_name=koc.get("name") if koc else None,
            gp_name=role.get("practitioner", {}).get("display") if role else None,
            gp_practice=role.get("organization", {}).get("display") if role else None,
            diagnosis_code=code,
            diagnosis_text=text,
            diagnosis_evidence=tuple(evidence),
        )

    async def _read_optional(self, reference: str | None, expected_type: str) -> Resource | None:
        if not reference or not str(reference).startswith(f"{expected_type}/"):
            return None
        try:
            return await self._repo.read(*str(reference).split("/", 1))
        except FhirNotFoundError:
            return None

    async def _case(self, task: Resource) -> Case:
        patient_reference = _patient(task)
        patient_resource, coverages = await asyncio.gather(
            self._repo.read(*patient_reference.split("/", 1)),
            self._repo.search("Coverage", {"beneficiary": patient_reference, "status": "active"}),
        )
        insurer_code = next((code for c in coverages if (code := insurer_code_from_coverage(c))), None)
        return case_from_fhir(task, patient_from_fhir(patient_resource, insurer_code=insurer_code))


def _patient(task: Resource) -> str:
    reference = task.get("for", {}).get("reference")
    if not reference or not str(reference).startswith("Patient/"):
        raise ValueError("coordinating Task has no Patient in Task.for")
    return str(reference)


def _focus(task: Resource) -> str:
    reference = task.get("focus", {}).get("reference")
    if not reference or not str(reference).startswith("EpisodeOfCare/"):
        raise ValueError("coordinating Task has no EpisodeOfCare in Task.focus")
    return str(reference)


def _audit_entities(tasks: list[Resource]) -> list[str]:
    entities: list[str] = []
    for task in tasks:
        entities += [f"Task/{task['id']}", _patient(task), _focus(task)]
    return entities
