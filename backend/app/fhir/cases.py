"""Read side of cases: FHIR (coordinating Task + Patient + Coverage + DocumentReference) -> domain models.

Every successful read of clinical content writes one AuditEvent (action R) through the repository.

Two facts are read back from what the workflow recorded with its transitions (`CaseActivity`): when the referring GP
first opened the MDT conclusion (the audit-only `gp_opened` event) and which blocking readiness items a KOC physician
waived at `mark_ready_mdt` (waiver Provenance). The searches run only in the states where those facts can exist.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from app.domain.case import Case, CaseState
from app.domain.document import SourceDocument
from app.domain.errors import NotFoundError
from app.domain.evidence import Evidence
from app.domain.pathway import RecordedWaiver
from app.fhir.audit import domain_event_code
from app.fhir.client import Resource
from app.fhir.errors import FhirNotFoundError
from app.fhir.mappers.case import case_from_fhir
from app.fhir.mappers.document import document_content, document_from_fhir
from app.fhir.mappers.patient import insurer_code_from_coverage, patient_from_fhir
from app.fhir.mappers.readiness import waiver_from_provenance
from app.fhir.mappers.referral import diagnosis_from_service_request
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_AUDIT_EVENT_CODE, CS_TASK_CODE, SID_CASE_TASK, TASK_CODE_COORDINATE_CASE

# `gp_opened` is accepted only in zpetna_vazba_odeslana (case_machine), so it can exist only from there on.
GP_OPENED_STATES = frozenset({CaseState.ZPETNA_VAZBA_ODESLANA, CaseState.UZAVRENO})
# Waivers are written by `mark_ready_mdt` (-> pripraveno_mdt); `reopen` takes the case back to kompletni.
WAIVER_STATES = frozenset(
    {CaseState.PRIPRAVENO_MDT, CaseState.ZAVER_MDT, CaseState.ZPETNA_VAZBA_ODESLANA, CaseState.UZAVRENO}
)
EVENT_GP_OPENED = "gp_opened"
EVENT_REOPEN = "reopen"


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
    gp_opened_at: datetime | None = None  # first audited `gp_opened`; None = not recorded (or not yet possible)


@dataclass(frozen=True)
class CaseActivity:
    """Facts read back from the workflow's own records (AuditEvent, Provenance) of one case."""

    gp_opened_at: datetime | None = None
    readiness_waivers: tuple[RecordedWaiver, ...] = ()
    references: tuple[str, ...] = ()  # the Provenance resources read; the caller names them in its audit


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
    readiness_waivers: tuple[RecordedWaiver, ...] = ()


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
        resources, activity = await asyncio.gather(
            self._repo.search("DocumentReference", {"encounter": _focus(task), "_count": "100"}),
            self.activity(task, case),
        )
        documents = sorted((document_from_fhir(r) for r in resources), key=lambda d: (d.received_at, d.doc_id))
        await self._repo.audit_read(
            [*_audit_entities([task]), *(f"DocumentReference/{r['id']}" for r in resources), *activity.references],
            subtype="read",
        )
        return CaseDetailView(
            case=case,
            documents=documents,
            extras=replace(extras, gp_opened_at=activity.gp_opened_at),
            readiness_waivers=activity.readiness_waivers,
        )

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

    async def activity(self, task: Resource, case: Case, *, waivers: bool = True) -> CaseActivity:
        """When the GP first opened the conclusion and the waivers in force (latest per item, none written before the
        last `reopen`). Not audited here: the caller names `references` in its own audited read or export."""
        codes = [EVENT_GP_OPENED] if case.state in GP_OPENED_STATES else []
        want_waivers = waivers and case.state in WAIVER_STATES
        if want_waivers:
            codes.append(EVENT_REOPEN)
        events = await self._domain_events(task, codes)
        opened = [_instant(e["recorded"]) for e in events.get(EVENT_GP_OPENED, [])]
        result = CaseActivity(gp_opened_at=min(opened) if opened else None)
        if not want_waivers:
            return result
        provenances = await self._repo.search("Provenance", {"target": f"Task/{task['id']}", "_count": "100"})
        found = [(r, w) for r in provenances if (w := waiver_from_provenance(r)) is not None]
        reopens = events.get(EVENT_REOPEN, [])
        if reopens:
            last = max(reopens, key=lambda e: _written(e, _instant(e["recorded"])))
            found = [(r, w) for r, w in found if _written_after(r, w.at, last)]
        latest: dict[str, tuple[Resource, RecordedWaiver]] = {}
        for resource, waiver in sorted(found, key=lambda pair: _written(pair[0], pair[1].at)):
            latest[waiver.item] = (resource, waiver)
        kept = sorted(latest.values(), key=lambda pair: (pair[1].at, pair[1].item))
        return replace(
            result,
            readiness_waivers=tuple(w for _, w in kept),
            references=tuple(f"Provenance/{r['id']}" for r, _ in kept if r.get("id")),
        )

    async def _domain_events(self, task: Resource, codes: Sequence[str]) -> dict[str, list[Resource]]:
        """The case's business AuditEvents with these workflow event codes, by code (filtered on the server by
        `subtype`, and again here: every audited read of the case names the same Task)."""
        if not codes:
            return {}
        found = await self._repo.search(
            "AuditEvent",
            {
                "entity": f"Task/{task['id']}",
                "subtype": ",".join(f"{CS_AUDIT_EVENT_CODE}|{code}" for code in codes),
                "_count": "100",
            },
        )
        events: dict[str, list[Resource]] = {}
        for event in found:
            code = domain_event_code(event)
            if code is not None and code in codes and event.get("recorded"):
                events.setdefault(code, []).append(event)
        return events

    async def _overview(self, task: Resource) -> CaseOverview:
        case, document_count, extras = await asyncio.gather(
            self._case(task),
            self._repo.count("DocumentReference", {"encounter": _focus(task)}),
            self._extras(task),
        )
        if case.state in GP_OPENED_STATES:
            activity = await self.activity(task, case, waivers=False)
            extras = replace(extras, gp_opened_at=activity.gp_opened_at)
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


def _instant(value: object) -> datetime:
    return datetime.fromisoformat(str(value))


def _last_updated(resource: Resource) -> datetime | None:
    value = resource.get("meta", {}).get("lastUpdated")
    return _instant(value) if value else None


def _written(resource: Resource, recorded: datetime) -> datetime:
    """Write order: the server's `meta.lastUpdated` (wall clock, so it orders writes even while the demo clock stands
    still); the business time when the server gave none."""
    return _last_updated(resource) or recorded


def _written_after(resource: Resource, recorded: datetime, event: Resource) -> bool:
    """Was this waiver written after that AuditEvent? Without server times the business times are compared in whole
    seconds (Provenance.recorded has no milliseconds), so a waiver from the same second counts as later."""
    mine, theirs = _last_updated(resource), _last_updated(event)
    if mine is not None and theirs is not None:
        return mine > theirs
    return recorded >= _instant(event["recorded"]).replace(microsecond=0)


def _audit_entities(tasks: list[Resource]) -> list[str]:
    entities: list[str] = []
    for task in tasks:
        entities += [f"Task/{task['id']}", _patient(task), _focus(task)]
    return entities
