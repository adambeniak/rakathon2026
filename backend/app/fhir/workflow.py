"""Write side of the case workflow: state transitions, document requests, received reports.

Every operation is ONE transaction Bundle (case Task update with optimistic locking + the business AuditEvent), so
a failed or raced write never leaves a half-applied state. The state machine itself lives in `app.domain`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.documents.ingest import UploadedDocument
from app.domain import case_machine, document_request
from app.domain.case import Case, CaseState
from app.domain.common import PartyRef, Role
from app.domain.directory import OrganizationKind
from app.domain.document import SourceDocument
from app.domain.errors import ConflictError, ForbiddenError, InvalidInputError, NotFoundError
from app.domain.events import DomainEvent, EventKind, TransitionError
from app.domain.task import Task
from app.fhir.audit import build_domain_audit_event
from app.fhir.bundles import BundleBuilder
from app.fhir.cases import CaseReader, LoadedCase
from app.fhir.directory import Directory, RoleEntry
from app.fhir.mappers.case import case_task_to_fhir
from app.fhir.mappers.document import document_to_fhir
from app.fhir.mappers.document_request import (
    communication_request_to_fhir,
    request_exam_date,
    request_task_from_fhir,
    request_task_to_fhir,
)
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_TASK_CODE, SID_REQUEST_TASK, SID_SOURCE_DOCUMENT, TASK_CODE_REQUEST_REPORT
from app.security.actor import SYSTEM_ACTOR

# Events whose guards need data that has no endpoint yet; they are refused instead of being half-supported.
SUPPORTED_EVENTS = frozenset(
    {"accept", "request_documents", "mark_complete", "docs_received", "missing_found", "postpone", "resume"}
)
OPEN_TASK_STATUSES = "requested,accepted,in-progress"
OPEN_STATUSES = frozenset(OPEN_TASK_STATUSES.split(","))


@dataclass(frozen=True)
class TransitionOutcome:
    case: Case
    events: tuple[DomainEvent, ...]


def assign_holder(case: Case, actor: PartyRef, directory: Directory, loaded: LoadedCase) -> Case:
    """Pick the concrete holder for the machine's baton role.

    The acting person when they hold that role; the case's GP (Task.requester) for a GP baton; otherwise the managing
    KOC's default holder of the role with a role-level display ("Koordinátor KOC 2"), as the seed does for the MDT.
    """
    role = case.baton_role
    if role is None:
        return case.model_copy(update={"baton_holder": None})
    if case.baton_holder is not None and case.baton_holder.role is role:
        return case
    if actor.role is role and directory.role(actor.id) is not None:
        return case.model_copy(update={"baton_holder": actor})
    if role is Role.GP:
        entry = _requester(loaded, directory)
        return case.model_copy(update={"baton_holder": entry.party() if entry else None})
    koc = managing_koc_id(loaded, directory)
    holder = directory.role_holder(koc, role) if koc else None
    return case.model_copy(update={"baton_holder": holder})


def managing_koc_id(loaded: LoadedCase, directory: Directory) -> str | None:
    """Business id of the KOC that manages the case (EpisodeOfCare.managingOrganization -> directory)."""
    reference = loaded.episode.get("managingOrganization", {}).get("reference")
    entry = next((o for o in directory.orgs if o.ref == reference), None)
    return entry.org.id if entry else None


def _requester(loaded: LoadedCase, directory: Directory) -> RoleEntry | None:
    """The referring GP: Task.requester is a PractitionerRole reference."""
    reference = loaded.task.get("requester", {}).get("reference")
    return next((r for r in directory.roles if r.ref == reference), None) if reference else None


def authorize_case(loaded: LoadedCase, actor: PartyRef, directory: Directory) -> None:
    """Case membership: the referring GP, or staff of the managing KOC (the system actor always passes).

    Without this any identified actor could read or change any case by guessing its id.
    """
    if actor.role is Role.SYSTEM:
        return
    if actor.role is Role.GP:
        requester = _requester(loaded, directory)
        if requester is not None and requester.role.id == actor.id:
            return
    elif actor.role in (Role.COORDINATOR, Role.KOC_PHYSICIAN, Role.KOC_STAFF):
        entry = directory.role(actor.id)
        if entry is not None and entry.role.organization_id == managing_koc_id(loaded, directory):
            return
    raise ForbiddenError("the actor is not a participant of this case")


class CaseWorkflow:
    def __init__(self, repository: FhirRepository, reader: CaseReader) -> None:
        self._repo = repository
        self._reader = reader

    async def open_request_count(self, loaded: LoadedCase) -> int:
        return await self._repo.count(
            "Task",
            {
                "code": f"{CS_TASK_CODE}|{TASK_CODE_REQUEST_REPORT}",
                "part-of": f"Task/{loaded.task['id']}",
                "status": OPEN_TASK_STATUSES,
            },
        )

    async def transition(
        self,
        case_id: str,
        event: str,
        *,
        actor: PartyRef,
        directory: Directory,
        now: datetime,
        reason: str | None = None,
        resume_on: str | None = None,
    ) -> TransitionOutcome:
        if event not in SUPPORTED_EVENTS:
            raise InvalidInputError(f"event {event!r} is not available through this endpoint")
        loaded = await self._reader.load(case_id)
        authorize_case(loaded, actor, directory)
        open_requests = await self.open_request_count(loaded)
        ctx = case_machine.CaseContext(
            reason=reason, resume_on=resume_on, open_request_tasks=open_requests, missing_blockers=open_requests
        )
        result = case_machine.transition(loaded.case, event, actor.role, ctx, now)
        new_case = assign_holder(result.case, actor, directory, loaded)
        if event == "accept" and actor.role is Role.COORDINATOR:
            new_case = new_case.model_copy(update={"baton_holder": actor})
        await self.save_case(loaded, new_case, result.events, actor=actor, directory=directory, status_reason=reason)
        return TransitionOutcome(new_case, result.events)

    async def save_case(
        self,
        loaded: LoadedCase,
        case: Case,
        events: tuple[DomainEvent, ...],
        *,
        actor: PartyRef,
        directory: Directory,
        status_reason: str | None = None,
        bundle: BundleBuilder | None = None,
    ) -> None:
        """PUT the coordinating Task (If-Match on the version read) + business AuditEvents in one transaction."""
        builder = bundle if bundle is not None else BundleBuilder()
        holder = directory.role(case.baton_holder.id) if case.baton_holder else None
        owner_reference = holder.ref if holder else None
        task = case_task_to_fhir(
            case,
            episode_reference=_ref(loaded.task, "focus"),
            patient_reference=_ref(loaded.task, "for"),
            requester_reference=loaded.task.get("requester", {}).get("reference"),
            owner_reference=owner_reference,
            based_on_reference=(loaded.task.get("basedOn") or [{}])[0].get("reference"),
            status_reason=status_reason,
        )
        # Keep what the case mapper does not own (id, meta, identifiers beyond the key, authoredOn).
        task["id"] = loaded.task["id"]
        _keep_meta(task, loaded.task)
        builder.put(task, version_id=loaded.task.get("meta", {}).get("versionId"))
        for event in events:
            if event.kind is EventKind.AUDIT:
                builder.post(build_domain_audit_event(event, actor=actor, entities=[f"Task/{loaded.task['id']}"]))
        await self._repo.transaction(builder.build())


def _ref(task: dict[str, object], key: str) -> str:
    reference = task.get(key)
    if not isinstance(reference, dict) or "reference" not in reference:
        raise ValueError(f"coordinating Task has no {key} reference")
    return str(reference["reference"])


@dataclass(frozen=True)
class RequestItem:
    label: str
    recipient_org_id: str
    exam_date: date | None = None


@dataclass(frozen=True)
class RequestView:
    task: Task
    exam_date: date | None


@dataclass(frozen=True)
class RequestsOutcome:
    case: Case
    requests: list[RequestView]


@dataclass(frozen=True)
class ReceivedOutcome:
    case: Case
    document: SourceDocument
    open_requests_remaining: int
    case_event: str | None  # 'podklady_kompletni' when the last open request was fulfilled


REQUESTING_STATES = (CaseState.TRIAGE, CaseState.CEKA_NA_PODKLADY)
UPLOAD_ROLES = frozenset({Role.COORDINATOR, Role.KOC_PHYSICIAN, Role.KOC_STAFF, Role.GP, Role.SYSTEM})
CASE_EVENT_COMPLETE = "podklady_kompletni"  # the brief's name of the machine event `docs_received`


class RequestWorkflow(CaseWorkflow):
    """Report requests of a case and the reports that fulfil them."""

    async def list_requests(self, case_id: str, *, actor: PartyRef, directory: Directory) -> list[RequestView]:
        loaded = await self._reader.load(case_id)
        authorize_case(loaded, actor, directory)
        resources = await self._request_resources(loaded)
        entities = [f"Task/{loaded.task['id']}", *(f"Task/{r['id']}" for r in resources)]
        await self._repo.audit_read(entities, subtype="search-type")  # also when the list is empty
        return [RequestView(request_task_from_fhir(r), request_exam_date(r)) for r in resources]

    async def create_requests(
        self,
        case_id: str,
        items: list[RequestItem],
        *,
        actor: PartyRef,
        directory: Directory,
        now: datetime,
    ) -> RequestsOutcome:
        if actor.role is not Role.COORDINATOR:
            raise TransitionError("forbidden_role", f"role {actor.role.value!r} may not request documents")
        if not items:
            raise InvalidInputError("at least one request is required")
        loaded = await self._reader.load(case_id)
        authorize_case(loaded, actor, directory)
        if loaded.case.state not in REQUESTING_STATES:
            raise TransitionError(
                "invalid_transition", f"documents cannot be requested in state {loaded.case.state.value!r}"
            )
        owner = directory.role(actor.id)
        if owner is None:
            raise InvalidInputError("the actor is not in the directory")
        patient_ref, episode_ref = _ref(loaded.task, "for"), _ref(loaded.task, "focus")
        existing = await self._request_resources(loaded)
        open_before = sum(1 for r in existing if r.get("status") in OPEN_STATUSES)

        builder = BundleBuilder()
        views: list[RequestView] = []
        events: list[DomainEvent] = []
        for offset, item in enumerate(items, start=1):
            recipient = directory.org(item.recipient_org_id)
            if recipient is None or recipient.org.kind in (OrganizationKind.INSURER, OrganizationKind.KOC):
                raise InvalidInputError(f"unknown workplace {item.recipient_org_id!r}")
            task, event = document_request.new_request(
                case_id=case_id,
                number=len(existing) + offset,
                label=item.label,
                recipient_name=recipient.org.name,
                owner=actor,
                now=now,
            )
            message = builder.post(
                communication_request_to_fhir(
                    task.id,
                    label=item.label,
                    exam_date=item.exam_date,
                    patient_reference=patient_ref,
                    episode_reference=episode_ref,
                    requester=actor,
                    requester_reference=owner.ref,
                    recipient_reference=recipient.ref,
                    authored_on=now,
                )
            )
            task_ref = builder.post(
                request_task_to_fhir(
                    task,
                    case_task_reference=f"Task/{loaded.task['id']}",
                    patient_reference=patient_ref,
                    communication_request_reference=message,
                    owner_reference=owner.ref,
                    recipient_reference=recipient.ref,
                    exam_date=item.exam_date,
                )
            )
            builder.post(build_domain_audit_event(event, actor=actor, entities=[task_ref, f"Task/{loaded.task['id']}"]))
            events.append(event)
            views.append(RequestView(task, item.exam_date))

        case = loaded.case
        if case.state is CaseState.TRIAGE:  # one click: the requests and the move to "Čeká na podklady" together
            ctx = case_machine.CaseContext(open_request_tasks=open_before + len(items))
            result = case_machine.transition(case, "request_documents", actor.role, ctx, now)
            case = assign_holder(result.case, actor, directory, loaded)
            await self.save_case(loaded, case, result.events, actor=actor, directory=directory, bundle=builder)
        else:  # still PUT the case Task (If-Match): concurrent request numbering/fulfilment is serialised
            await self.save_case(loaded, case, (), actor=actor, directory=directory, bundle=builder)
        return RequestsOutcome(case, views)

    async def receive_document(
        self,
        case_id: str,
        upload: UploadedDocument,
        *,
        authored_at: date,
        request_id: str | None,
        actor: PartyRef,
        directory: Directory,
        now: datetime,
    ) -> ReceivedOutcome:
        if actor.role not in UPLOAD_ROLES:
            raise ForbiddenError(f"role {actor.role.value!r} may not upload documents")
        loaded = await self._reader.load(case_id)
        authorize_case(loaded, actor, directory)
        patient_ref, episode_ref = _ref(loaded.task, "for"), _ref(loaded.task, "focus")
        duplicate = await self._repo.count(
            "DocumentReference",
            {"identifier": f"{SID_SOURCE_DOCUMENT}|{upload.doc.doc_id}", "encounter": episode_ref},
        )
        if duplicate:
            raise ConflictError(f"document {upload.doc.doc_id!r} is already part of the case")

        if request_id is not None and actor.role is not Role.COORDINATOR:
            raise ForbiddenError("only the coordinator links a report to a request")
        requests = await self._request_resources(loaded)
        open_requests = [r for r in requests if r.get("status") in OPEN_STATUSES]
        target = None
        if request_id is not None:
            target = next((r for r in requests if _request_task_id(r) == request_id), None)
            if target is None:
                raise NotFoundError("request", request_id)
            if target.get("status") not in OPEN_STATUSES:
                raise ConflictError(f"request {request_id!r} is already fulfilled")

        builder = BundleBuilder()
        recipient_name = None
        events: list[DomainEvent] = []
        document_ref = ""
        if target is not None:
            recipient_name = request_task_from_fhir(target).location
        document_ref = builder.post(
            document_to_fhir(
                SourceDocument(
                    doc_id=upload.doc.doc_id,
                    title=upload.file_name,
                    authored_at=authored_at,
                    received_at=now,
                    custodian=recipient_name,
                    file_name=upload.file_name,
                    content_type=upload.content_type,
                ),
                upload.content,
                patient_reference=patient_ref,
                episode_reference=episode_ref,
                custodian_reference=None,
                author_reference=None,
            )
        )
        remaining = len(open_requests)
        if target is not None:
            done, event = document_request.fulfil(
                request_task_from_fhir(target), result_doc_id=upload.doc.doc_id, actor=actor.role, now=now
            )
            fhir_task = request_task_to_fhir(
                done,
                case_task_reference=f"Task/{loaded.task['id']}",
                patient_reference=patient_ref,
                communication_request_reference=_ref_first(target, "basedOn"),
                owner_reference=_ref_owner(target),
                recipient_reference=_ref_recipient(target),
                exam_date=request_exam_date(target),
                result_document_reference=document_ref,
            )
            fhir_task["id"] = target["id"]
            _keep_meta(fhir_task, target)
            builder.put(fhir_task, version_id=target.get("meta", {}).get("versionId"))
            await self._complete_communication(builder, target)
            builder.post(build_domain_audit_event(event, actor=actor, entities=[f"Task/{target['id']}", document_ref]))
            events.append(event)
            remaining -= 1

        case = loaded.case
        case_event: str | None = None
        if target is not None and remaining == 0 and case.state is CaseState.CEKA_NA_PODKLADY:
            result = case_machine.transition(
                case,
                "docs_received",
                Role.SYSTEM,
                case_machine.CaseContext(open_request_tasks=0),
                now,
            )
            case = assign_holder(result.case, SYSTEM_ACTOR, directory, loaded)
            case_event = CASE_EVENT_COMPLETE
            await self.save_case(loaded, case, result.events, actor=SYSTEM_ACTOR, directory=directory, bundle=builder)
        elif target is not None:
            await self.save_case(loaded, case, (), actor=actor, directory=directory, bundle=builder)
        else:
            await self._repo.transaction(builder.build())
        document = SourceDocument(
            doc_id=upload.doc.doc_id,
            title=upload.file_name,
            authored_at=authored_at,
            received_at=now,
            custodian=recipient_name,
            file_name=upload.file_name,
            content_type=upload.content_type,
        )
        return ReceivedOutcome(case, document, remaining, case_event)

    async def _complete_communication(self, builder: BundleBuilder, request_task: dict[str, Any]) -> None:
        reference = _ref_first(request_task, "basedOn")
        resource = await self._repo.read(*reference.split("/", 1))
        resource["status"] = "completed"
        builder.put(resource, version_id=resource.get("meta", {}).get("versionId"))

    async def _request_resources(self, loaded: LoadedCase) -> list[dict[str, Any]]:
        return await self._repo.search(
            "Task",
            {
                "code": f"{CS_TASK_CODE}|{TASK_CODE_REQUEST_REPORT}",
                "part-of": f"Task/{loaded.task['id']}",
                "_count": "100",
            },
        )


def _keep_meta(new: dict[str, Any], old: dict[str, Any]) -> None:
    """A PUT replaces the resource: carry over tags and security labels (demo reset relies on the tag)."""
    meta = {k: v for k, v in old.get("meta", {}).items() if k in ("tag", "security") and v}
    if meta:
        new["meta"] = meta


def _request_task_id(resource: dict[str, Any]) -> str | None:
    return next((i["value"] for i in resource.get("identifier", []) if i.get("system") == SID_REQUEST_TASK), None)


def _ref_first(resource: dict[str, Any], key: str) -> str:
    return str(resource[key][0]["reference"])


def _ref_owner(resource: dict[str, Any]) -> str:
    return str(resource["owner"]["reference"])


def _ref_recipient(resource: dict[str, Any]) -> str:
    return str(resource["restriction"]["recipient"][0]["reference"])
