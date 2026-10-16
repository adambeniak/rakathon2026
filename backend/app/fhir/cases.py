"""Read side of cases: FHIR (coordinating Task + Patient + Coverage + DocumentReference) -> domain models.

Every successful read of clinical content writes one AuditEvent (action R) through the repository.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.domain.case import Case
from app.domain.document import SourceDocument
from app.domain.errors import NotFoundError
from app.fhir.client import Resource
from app.fhir.mappers.case import case_from_fhir
from app.fhir.mappers.document import document_from_fhir
from app.fhir.mappers.patient import insurer_code_from_coverage, patient_from_fhir
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_TASK_CODE, SID_CASE_TASK, TASK_CODE_COORDINATE_CASE


@dataclass(frozen=True)
class CaseOverview:
    case: Case
    document_count: int


@dataclass(frozen=True)
class CaseDetailView:
    case: Case
    documents: list[SourceDocument]


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

    async def get_case(self, case_id: str) -> CaseDetailView:
        task = await self._repo.find_by_identifier("Task", SID_CASE_TASK, case_id)
        if task is None:
            raise NotFoundError("case", case_id)
        case = await self._case(task)
        resources = await self._repo.search("DocumentReference", {"encounter": _focus(task), "_count": "100"})
        documents = sorted((document_from_fhir(r) for r in resources), key=lambda d: (d.received_at, d.doc_id))
        await self._repo.audit_read(
            [*_audit_entities([task]), *(f"DocumentReference/{r['id']}" for r in resources)], subtype="read"
        )
        return CaseDetailView(case=case, documents=documents)

    async def _overview(self, task: Resource) -> CaseOverview:
        case, document_count = await asyncio.gather(
            self._case(task), self._repo.count("DocumentReference", {"encounter": _focus(task)})
        )
        return CaseOverview(case=case, document_count=document_count)

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
