"""Persistence of pathway steps and ad-hoc tasks (FHIR Task / CarePlan) for coordination.

Every successful read of tasks writes an AuditEvent through the repository (AGENTS.md non-negotiable 6), so routes
and the watchdog cannot forget it. Steps of a case are found through `Task.partOf` (the coordinating Task);
results are sorted by (due, id) because the search returns no stable order.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from app.domain.board import due_order
from app.domain.common import PartyRef, Role
from app.domain.errors import ConflictError, InvalidInputError, NotFoundError
from app.domain.task import Task, TaskStatus
from app.domain.task_machine import OPEN_STATUSES
from app.fhir.cases import CaseHeader
from app.fhir.client import Resource, reference_from_location
from app.fhir.errors import FhirConflictError, FhirError, FhirNotFoundError
from app.fhir.mappers.care_plan import care_plan_identifier, care_plan_to_fhir
from app.fhir.mappers.directory import party_reference
from app.fhir.mappers.provenance import pathway_launch_provenance
from app.fhir.mappers.service_request import service_request_to_fhir
from app.fhir.mappers.task import task_from_fhir, task_to_fhir
from app.fhir.repository import FhirRepository
from app.fhir.systems import (
    CS_TASK_CODE,
    SID_CASE_STEP,
    SID_SOURCE_DOCUMENT,
    SID_STEP_ORDER,
    TASK_CODE_COORDINATE_CASE,
)


@dataclass(frozen=True)
class StoredTask:
    task: Task
    resource: Resource  # as read: carries the FHIR id, `meta.versionId` and the `partOf`/`for` references

    @property
    def fhir_id(self) -> str:
        return str(self.resource["id"])

    @property
    def version_id(self) -> str | None:
        version = self.resource.get("meta", {}).get("versionId")
        return str(version) if version else None


@dataclass(frozen=True)
class LaunchResult:
    care_plan_id: str
    task_ids: dict[str, str]  # domain Task.id -> FHIR id
    service_request_ids: dict[str, str]  # domain Task.id -> FHIR id of its ServiceRequest
    provenance_id: str


@dataclass(frozen=True)
class PractitionerRoleRef:
    """A person in a workflow role, as found in the directory."""

    fhir_reference: str  # PractitionerRole/<id>
    business_id: str
    display: str
    role: Role | None


class TaskStore:
    def __init__(self, repository: FhirRepository) -> None:
        self._repo = repository

    # --- reads (audited) ---

    async def list_for_case(self, case_task_reference: str, *, audit: bool = True) -> list[StoredTask]:
        resources = await self._repo.search("Task", {"part-of": case_task_reference, "_count": "100"})
        if resources and audit:
            await self._repo.audit_read([f"Task/{r['id']}" for r in resources], subtype="search-type")
        return _sorted(StoredTask(task_from_fhir(r), r) for r in resources if _is_step(r))

    async def get(self, task_id: str) -> StoredTask:
        resource = await self._repo.find_by_identifier("Task", SID_CASE_STEP, task_id)
        if resource is None:
            raise NotFoundError("task", task_id)
        await self._repo.audit_read([f"Task/{resource['id']}"], subtype="read")
        return StoredTask(task_from_fhir(resource), resource)

    async def list_open_everywhere(self) -> list[StoredTask]:
        """Open steps of every case (SLA watchdog; demo-scale: one search per case).

        Not audited per round: the watchdog is a technical job that discloses nothing to a user, and an AuditEvent per
        case per minute would drown the real trail. Its writes (the escalations) are audited as usual.
        """
        cases = await self._repo.search(
            "Task", {"code": f"{CS_TASK_CODE}|{TASK_CODE_COORDINATE_CASE}", "_count": "100"}
        )
        open_tasks: list[StoredTask] = []
        for case_task in cases:
            stored = await self.list_for_case(f"Task/{case_task['id']}", audit=False)
            open_tasks += [s for s in stored if s.task.status in OPEN_STATUSES]
        return open_tasks

    async def get_plan_definition(self, url: str) -> Resource:
        found = await self._repo.search("PlanDefinition", {"url": url})
        if not found:
            raise NotFoundError("plan", url)
        if len(found) > 1:
            raise FhirConflictError(f"PlanDefinition url is not unique ({len(found)} matches)")
        return found[0]

    async def care_plan_exists(self, case_id: str, plan: Resource) -> bool:
        system, value = care_plan_identifier(case_id, plan)
        return await self._repo.find_by_identifier("CarePlan", system, value) is not None

    async def patient_document_received_at(self, patient_reference: str, doc_id: str) -> datetime | None:
        """When the KOC received the source document `doc_id` of this patient; None if there is no such document."""
        found = await self._repo.search(
            "DocumentReference", {"identifier": f"{SID_SOURCE_DOCUMENT}|{doc_id}", "patient": patient_reference}
        )
        if found:
            await self._repo.audit_read([f"DocumentReference/{r['id']}" for r in found], subtype="search-type")
        if not found:
            return None
        received = found[0].get("date")
        if not received:
            raise InvalidInputError(f"document {doc_id!r} has no receipt timestamp")
        return datetime.fromisoformat(str(received))

    # --- writes ---

    async def launch_pathway(
        self,
        header: CaseHeader,
        plan: Resource,
        tasks: Sequence[Task],
        start_date: date,
        *,
        indication: PractitionerRoleRef,
        coordinator: PartyRef,
        recorded: datetime,
    ) -> LaunchResult:
        """CarePlan, one ServiceRequest + Task per step and the Provenance in one transaction.

        `indication` is the KOC physician who indicated the pathway: CarePlan.author and ServiceRequest.requester.
        The Provenance says the coordinator created it all on that physician's behalf. `If-None-Exist` makes a lost
        race on the CarePlan and the per-step resources harmless.
        """
        requester = party_reference(
            PartyRef(id=indication.business_id, display=indication.display, role=Role.KOC_PHYSICIAN),
            indication.fhir_reference,
        )
        care_plan_url = f"urn:uuid:{uuid.uuid4()}"
        task_urls = {t.id: f"urn:uuid:{uuid.uuid4()}" for t in tasks}
        order_urls = {t.id: f"urn:uuid:{uuid.uuid4()}" for t in tasks}
        system, value = care_plan_identifier(header.case.id, plan)
        care_plan = care_plan_to_fhir(
            case_id=header.case.id,
            plan=plan,
            start_date=start_date,
            patient_reference=header.patient_reference,
            activity_references=[task_urls[t.id] for t in tasks],
            author=requester,
            created=recorded,
        )
        entries: list[Resource] = [
            {
                "fullUrl": care_plan_url,
                "resource": care_plan,
                "request": {"method": "POST", "url": "CarePlan", "ifNoneExist": f"identifier={system}|{value}"},
            }
        ]
        for task in tasks:
            order = service_request_to_fhir(
                task, patient_reference=header.patient_reference, requester=requester, authored_on=recorded
            )
            entries.append(
                {
                    "fullUrl": order_urls[task.id],
                    "resource": order,
                    "request": {
                        "method": "POST",
                        "url": "ServiceRequest",
                        "ifNoneExist": f"identifier={SID_STEP_ORDER}|{task.id}",
                    },
                }
            )
        for task in tasks:
            resource = task_to_fhir(
                task,
                case_task_reference=header.task_reference,
                patient_reference=header.patient_reference,
                service_request_reference=order_urls[task.id],
            )
            entries.append(
                {
                    "fullUrl": task_urls[task.id],
                    "resource": resource,
                    "request": {
                        "method": "POST",
                        "url": "Task",
                        "ifNoneExist": f"identifier={SID_CASE_STEP}|{task.id}",
                    },
                }
            )
        provenance = pathway_launch_provenance(
            targets=[care_plan_url, *order_urls.values()],
            coordinator=coordinator,
            indicating=requester,
            recorded=recorded,
        )
        entries.append({"resource": provenance, "request": {"method": "POST", "url": "Provenance"}})
        response = await self._repo.transaction(
            {"resourceType": "Bundle", "type": "transaction", "entry": entries},
            description=f"pathway launched for case {header.case.id}: {len(tasks)} steps",
        )
        if any(str(e.get("response", {}).get("status", "")).startswith("200") for e in response.get("entry", [])):
            # A conditional create matched: another launch won the race (the pre-check ran before it committed).
            raise ConflictError("this pathway has already been launched for the case")
        ids = [_entry_id(e) for e in response.get("entry", [])]
        if len(ids) != len(entries):
            raise FhirError("pathway transaction returned an unexpected number of entries")
        count = len(tasks)
        return LaunchResult(
            care_plan_id=ids[0],
            service_request_ids={t.id: ids[1 + i] for i, t in enumerate(tasks)},
            task_ids={t.id: ids[1 + count + i] for i, t in enumerate(tasks)},
            provenance_id=ids[-1],
        )

    async def create(self, header: CaseHeader, task: Task) -> str:
        """Create a single (ad-hoc) task; returns its FHIR id."""
        resource = task_to_fhir(
            task, case_task_reference=header.task_reference, patient_reference=header.patient_reference
        )
        result = await self._repo.create(resource, if_none_exist=f"identifier={SID_CASE_STEP}|{task.id}")
        return result.id

    async def save(
        self, stored: StoredTask, task: Task, *, description: str, on_behalf_of: str | None = None
    ) -> StoredTask:
        """Write `task` over `stored` (optimistic: `If-Match` on the version that was read).

        A task that becomes completed or cancelled changes its order (ServiceRequest) in the **same transaction**, with
        the AuditEvent in the bundle too: the task, the order and the audit commit or fail together.
        """
        resource = task_to_fhir(
            task,
            case_task_reference=str(stored.resource["partOf"][0]["reference"]),
            patient_reference=str(stored.resource["for"]["reference"]),
        )
        resource["id"] = stored.fhir_id
        if "focus" in stored.resource:
            resource["focus"] = stored.resource["focus"]  # the ServiceRequest this step fulfils
        order = await self._closed_order(stored, task)
        try:
            if order is None:
                updated = await self._repo.update(
                    resource, if_match=stored.version_id, description=description, on_behalf_of=on_behalf_of
                )
                return StoredTask(task, updated or resource)
            entries = [
                _put_entry("Task", resource, stored.version_id),
                _put_entry("ServiceRequest", order, (order.get("meta") or {}).get("versionId")),
            ]
            await self._repo.transaction(
                {"resourceType": "Bundle", "type": "transaction", "entry": entries},
                audit_in_bundle=True,
                description=description,
                on_behalf_of=on_behalf_of,
            )
        except FhirNotFoundError as exc:
            raise NotFoundError("task", task.id) from exc
        return StoredTask(task, resource)

    async def _closed_order(self, stored: StoredTask, task: Task) -> Resource | None:
        """The order of `task` with its new status (completed -> completed, cancelled -> revoked), if it must change.

        A failed step keeps its active order (R4 has no "failed" request status; the coordinator decides what next).
        """
        status = _ORDER_STATUS.get(task.status)
        reference = str((stored.resource.get("focus") or {}).get("reference", ""))
        if status is None or task.status is stored.task.status or not reference.startswith("ServiceRequest/"):
            return None
        order = await self._repo.read("ServiceRequest", reference.split("/", 1)[1])
        await self._repo.audit_read([reference], subtype="read")
        return {**order, "status": status}


def _is_step(resource: Resource) -> bool:
    """Pathway steps and ad-hoc tasks, not the other Tasks of a case (e.g. report requests, F2-1)."""
    return any(i.get("system") == SID_CASE_STEP for i in resource.get("identifier", []))


def _put_entry(resource_type: str, resource: Resource, version_id: object) -> Resource:
    request: Resource = {"method": "PUT", "url": f"{resource_type}/{resource['id']}"}
    if version_id:
        request["ifMatch"] = f'W/"{version_id}"'
    return {"resource": resource, "request": request}


_ORDER_STATUS = {TaskStatus.COMPLETED: "completed", TaskStatus.CANCELLED: "revoked"}


def _entry_id(entry: Resource) -> str:
    location = entry.get("response", {}).get("location")
    if not location:
        raise FhirError("pathway transaction entry has no location")
    return reference_from_location(str(location))[1]


def _sorted(stored: Iterable[StoredTask]) -> list[StoredTask]:
    return sorted(stored, key=lambda s: due_order(s.task))
