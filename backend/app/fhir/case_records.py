"""Read side of what happened on a case: its audit trail, its workflow events and its messages (FHIR -> domain).

Nothing new is stored: everything is read back from what the workflow wrote (AuditEvent, Communication,
CommunicationRequest, Task, DocumentReference). Every method audits its own read (AGENTS.md non-negotiable 6), naming
the coordinating Task and EpisodeOfCare plus every record it disclosed; reading the audit trail is audited too.

Search patterns (standard R4, not yet verified on IRIS):
- `AuditEvent?entity=<ref>,<ref>,...` in chunks of `ENTITY_CHUNK` references, merged by id and sorted in code (no
  `_sort`). The trail of a case = AuditEvents naming its coordinating Task, its EpisodeOfCare, its steps and report
  requests, its documents and its messages. Writes that name only other resources (e.g. a handover Composition) are not
  in it.
- `AuditEvent?entity=<task refs>&type=<audit-type>|domain-event` for the business events.
- `Communication?subject=<patient>` / `CommunicationRequest?subject=<patient>`, kept when `about` names the case's
  EpisodeOfCare (`about` is not an R4 search parameter).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, replace

from app.domain.activity import AuditRecord, MessageRecord, RequestRecord, WorkflowEvent
from app.domain.document import SourceDocument
from app.domain.task import Task
from app.fhir.cases import LoadedCase
from app.fhir.client import Resource
from app.fhir.directory import Directory
from app.fhir.mappers.activity import (
    audit_record_from_fhir,
    is_about,
    message_from_communication,
    message_from_communication_request,
    recipient_reference,
    task_kind,
    workflow_event_from_fhir,
)
from app.fhir.mappers.document import document_from_fhir
from app.fhir.mappers.document_request import request_exam_date, request_task_from_fhir
from app.fhir.mappers.task import task_from_fhir
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_AUDIT_TYPE

# References per `entity=` search: keeps the URL short (IRIS / proxies limit the request line).
ENTITY_CHUNK = 20
REQUEST_TITLE_PREFIX = "Vyžádat výsledek: "


@dataclass(frozen=True)
class AuditTrail:
    records: list[AuditRecord]  # newest first


@dataclass(frozen=True)
class TimelineSources:
    documents: list[SourceDocument]
    steps: list[Task]
    requests: list[RequestRecord]
    events: list[WorkflowEvent]


@dataclass(frozen=True)
class CaseMessages:
    messages: list[MessageRecord]
    requests: dict[str, RequestRecord]  # by request task id


class CaseRecordsReader:
    def __init__(self, repository: FhirRepository) -> None:
        self._repo = repository

    async def audit_trail(self, loaded: LoadedCase) -> AuditTrail:
        tasks, documents, (requests, communications) = await asyncio.gather(
            self._part_of_tasks(loaded), self._documents(loaded), self._communications(loaded)
        )
        refs = [
            _case_task(loaded),
            _episode(loaded),
            *(f"Task/{r['id']}" for r in tasks),
            *(f"DocumentReference/{r['id']}" for r in documents),
            *(f"CommunicationRequest/{r['id']}" for r in requests),
            *(f"Communication/{r['id']}" for r in communications),
        ]
        events = await self._audit_events(refs)
        records = [audit_record_from_fhir(e) for e in events if e.get("recorded")]
        records.sort(key=lambda r: (r.recorded, r.written_at or r.recorded), reverse=True)
        # The trail discloses who touched the case, not clinical content: the read names the case itself.
        await self._repo.audit_read([_case_task(loaded), _patient(loaded), _episode(loaded)], subtype="search-type")
        return AuditTrail(records)

    async def timeline_sources(self, loaded: LoadedCase) -> TimelineSources:
        tasks, documents, (comm_requests, _) = await asyncio.gather(
            self._part_of_tasks(loaded), self._documents(loaded), self._communications(loaded, feedback=False)
        )
        task_refs = [_case_task(loaded), *(f"Task/{r['id']}" for r in tasks)]
        found = await self._audit_events(task_refs, {"type": f"{CS_AUDIT_TYPE}|domain-event"})
        events = [e for r in found if (e := workflow_event_from_fhir(r, _case_task(loaded))) is not None]
        events.sort(key=lambda e: e.at)
        steps = [task_from_fhir(r) for r in tasks if task_kind(r) == "step"]
        requests = _requests(tasks, comm_requests)
        await self._repo.audit_read(
            [
                *task_refs,
                _patient(loaded),
                _episode(loaded),
                *(f"DocumentReference/{r['id']}" for r in documents),
                *(f"CommunicationRequest/{r['id']}" for r in comm_requests),
            ],
            subtype="search-type",
        )
        return TimelineSources(
            documents=sorted((document_from_fhir(r) for r in documents), key=lambda d: (d.received_at, d.doc_id)),
            steps=steps,
            requests=requests,
            events=events,
        )

    async def messages(self, loaded: LoadedCase, directory: Directory) -> CaseMessages:
        tasks, (comm_requests, communications) = await asyncio.gather(
            self._part_of_tasks(loaded), self._communications(loaded)
        )
        messages: list[MessageRecord] = []
        for resource in comm_requests:
            message = message_from_communication_request(resource)
            if message is not None:
                messages.append(_with_recipient(message, resource, directory))
        for resource in communications:
            message = message_from_communication(resource)
            if message is not None:
                messages.append(_with_recipient(message, resource, directory))
        messages.sort(key=lambda m: (m.sent_at is None, m.sent_at, m.id))
        requests = {r.task_id: r for r in _requests(tasks, comm_requests)}
        await self._repo.audit_read(
            [
                _case_task(loaded),
                _patient(loaded),
                _episode(loaded),
                *(f"Task/{r['id']}" for r in tasks if task_kind(r) == "request"),
                *(m.reference for m in messages if m.reference),
            ],
            subtype="search-type",
        )
        return CaseMessages(messages, requests)

    # --- searches (not audited here: the public methods audit what they disclose) ---

    async def _part_of_tasks(self, loaded: LoadedCase) -> list[Resource]:
        found = await self._repo.search("Task", {"part-of": _case_task(loaded), "_count": "100"})
        return [r for r in found if task_kind(r) is not None]

    async def _documents(self, loaded: LoadedCase) -> list[Resource]:
        return await self._repo.search("DocumentReference", {"encounter": _episode(loaded), "_count": "100"})

    async def _communications(
        self, loaded: LoadedCase, *, feedback: bool = True
    ) -> tuple[list[Resource], list[Resource]]:
        patient, episode = _patient(loaded), _episode(loaded)
        requests_found = self._repo.search("CommunicationRequest", {"subject": patient, "_count": "100"})
        if feedback:
            found_requests, found_communications = await asyncio.gather(
                requests_found, self._repo.search("Communication", {"subject": patient, "_count": "100"})
            )
        else:
            found_requests, found_communications = await requests_found, []
        return (
            [r for r in found_requests if is_about(r, episode)],
            [c for c in found_communications if is_about(c, episode)],
        )

    async def _audit_events(self, references: Sequence[str], extra: dict[str, str] | None = None) -> list[Resource]:
        unique = list(dict.fromkeys(references))
        chunks = [unique[i : i + ENTITY_CHUNK] for i in range(0, len(unique), ENTITY_CHUNK)]
        pages = await asyncio.gather(
            *(
                self._repo.search("AuditEvent", {"entity": ",".join(chunk), **(extra or {}), "_count": "100"})
                for chunk in chunks
            )
        )
        merged: dict[str, Resource] = {}
        for page in pages:
            for resource in page:
                merged.setdefault(str(resource.get("id", id(resource))), resource)
        return list(merged.values())


def _requests(tasks: list[Resource], comm_requests: list[Resource]) -> list[RequestRecord]:
    sent = {m.id: m.sent_at for r in comm_requests if (m := message_from_communication_request(r)) is not None}
    records: list[RequestRecord] = []
    for resource in tasks:
        if task_kind(resource) != "request":
            continue
        task = request_task_from_fhir(resource)
        records.append(
            RequestRecord(
                task_id=task.id,
                label=task.title.removeprefix(REQUEST_TITLE_PREFIX),
                recipient=task.location,
                sent_at=sent.get(task.id),
                status=task.status.value,
                due=task.due,
                exam_date=request_exam_date(resource),
                result_doc_id=task.result_doc_id,
            )
        )
    return sorted(records, key=lambda r: r.task_id)


def _with_recipient(message: MessageRecord, resource: Resource, directory: Directory) -> MessageRecord:
    """Recipients are written as bare references: their display comes from the directory (no clinical content)."""
    if message.recipient:
        return message
    reference = recipient_reference(resource)
    if reference is None:
        return message
    org = next((o for o in directory.orgs if o.ref == reference), None)
    role = next((r for r in directory.roles if r.ref == reference), None)
    name = org.org.name if org else role.display if role else None
    return replace(message, recipient=name)


def _case_task(loaded: LoadedCase) -> str:
    return f"Task/{loaded.task['id']}"


def _patient(loaded: LoadedCase) -> str:
    return str(loaded.task["for"]["reference"])


def _episode(loaded: LoadedCase) -> str:
    return str(loaded.task["focus"]["reference"])
