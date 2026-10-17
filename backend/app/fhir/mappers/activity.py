"""AuditEvent / Communication / CommunicationRequest -> the case activity records of `app.domain.activity`.

Read-only mappers. Only structured fields are read: `entity.detail` is read for the keys `event`, `from`, `to`,
`task_id`, `result_doc_id` and `receipt_id` (never `reason` / `waived`, which hold free text), and `outcomeDesc` is
never copied out; it only classifies the few fixed descriptions the backend itself writes (export, vector index, ...).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from app.domain.activity import AuditAction, AuditRecord, MessageKind, MessageRecord, WorkflowEvent
from app.domain.common import Role
from app.fhir.audit import domain_event_code
from app.fhir.client import Resource
from app.fhir.mappers.feedback import SID_FEEDBACK, SID_MESSAGE_ID
from app.fhir.systems import (
    CS_WORKFLOW_ROLE,
    EXT_ON_BEHALF_OF,
    RESTFUL_INTERACTION,
    SID_CASE_STEP,
    SID_COMMUNICATION_REQUEST,
    SID_REQUEST_TASK,
)

_ACTIONS: Final[frozenset[str]] = frozenset({"C", "R", "U", "D", "E"})
_DETAIL_KEYS: Final = ("event", "from", "to", "task_id", "result_doc_id", "receipt_id")
# Fixed `outcomeDesc` prefixes written by the backend -> operation code (the text itself is never returned).
_DESCRIBED_OPERATIONS: Final = (
    ("MDT record exported", "export"),
    ("Stafeta.DocChunk", "index"),
    ("pathway launched", "launch_pathway"),
    ("document sent for extraction", "extract"),
    ("reset of tag", "reset"),
)


def audit_record_from_fhir(resource: Resource) -> AuditRecord:
    agent = (resource.get("agent") or [{}])[0]
    event_code = domain_event_code(resource)
    action = str(resource.get("action", "E"))
    return AuditRecord(
        recorded=datetime.fromisoformat(str(resource["recorded"])),
        action=_action(action),
        operation=event_code or _operation(resource),
        actor_display=(agent.get("who") or {}).get("display"),
        actor_role=_role(agent.get("type", {}).get("coding", [])),
        on_behalf_of=next(
            (
                (e.get("valueReference") or {}).get("display")
                for e in agent.get("extension", [])
                if e.get("url") == EXT_ON_BEHALF_OF
            ),
            None,
        ),
        entity_types=tuple(dict.fromkeys(t for e in resource.get("entity", []) if (t := _entity_type(e)))),
        outcome="success" if str(resource.get("outcome", "0")) == "0" else "failure",
        workflow_event=event_code is not None,
        written_at=_last_updated(resource),
    )


def workflow_event_from_fhir(resource: Resource, case_task_reference: str) -> WorkflowEvent | None:
    """A business AuditEvent (type `domain-event`) as a workflow event; None for any other AuditEvent."""
    code = domain_event_code(resource)
    if code is None or not resource.get("recorded"):
        return None
    entities = resource.get("entity", [])
    details = _details(entities[0]) if entities else {}
    first = str((entities[0].get("what") or {}).get("reference", "")) if entities else ""
    agent = (resource.get("agent") or [{}])[0]
    return WorkflowEvent(
        code=code,
        at=datetime.fromisoformat(str(resource["recorded"])),
        on_case=first == case_task_reference,
        from_state=details.get("from"),
        to_state=details.get("to"),
        task_id=details.get("task_id"),
        result_doc_id=details.get("result_doc_id"),
        receipt_id=details.get("receipt_id"),
        actor_display=(agent.get("who") or {}).get("display"),
        actor_role=_role(agent.get("type", {}).get("coding", [])),
    )


def message_from_communication_request(resource: Resource) -> MessageRecord | None:
    """A report request sent to a workplace; None for a CommunicationRequest that is not one of ours."""
    request_id = _identifier(resource, SID_COMMUNICATION_REQUEST)
    if request_id is None:
        return None
    authored = resource.get("authoredOn")
    return MessageRecord(
        id=request_id,
        kind=MessageKind.DOCUMENT_REQUEST,
        fhir_status=str(resource.get("status", "unknown")),
        sent_at=datetime.fromisoformat(str(authored)) if authored else None,
        sender=(resource.get("requester") or {}).get("display"),
        recipient=_first_display(resource.get("recipient")),
        text=_payload(resource),
        reference=f"CommunicationRequest/{resource['id']}" if resource.get("id") else "",
    )


def message_from_communication(resource: Resource) -> MessageRecord | None:
    """The MDT feedback e-mail to the GP (category `mdt-feedback`); None for any other Communication."""
    feedback_id = _identifier(resource, SID_FEEDBACK)
    if feedback_id is None:
        return None
    sent = resource.get("sent")
    return MessageRecord(
        id=feedback_id,
        kind=MessageKind.MDT_FEEDBACK,
        fhir_status=str(resource.get("status", "unknown")),
        sent_at=datetime.fromisoformat(str(sent)) if sent else None,
        sender=(resource.get("sender") or {}).get("display"),
        recipient=_first_display(resource.get("recipient")),
        text=_payload(resource),
        receipt_id=_identifier(resource, SID_MESSAGE_ID),
        reference=f"Communication/{resource['id']}" if resource.get("id") else "",
    )


def recipient_reference(resource: Resource) -> str | None:
    """The first recipient's literal reference ('Organization/3'), to resolve a name from the directory."""
    recipients = resource.get("recipient") or [{}]
    reference = recipients[0].get("reference")
    return str(reference) if reference else None


def is_about(resource: Resource, reference: str) -> bool:
    """Does `about` name this reference (e.g. the case's EpisodeOfCare)? `about` is not an R4 search parameter."""
    return any(a.get("reference") == reference for a in resource.get("about", []))


def task_kind(resource: Resource) -> str | None:
    """'step' (pathway step / ad-hoc task), 'request' (report request) or None, by the business identifier."""
    systems = {i.get("system") for i in resource.get("identifier", [])}
    if SID_CASE_STEP in systems:
        return "step"
    if SID_REQUEST_TASK in systems:
        return "request"
    return None


def _action(value: str) -> AuditAction:
    if value == "C":
        return "C"
    if value == "R":
        return "R"
    if value == "U":
        return "U"
    if value == "D":
        return "D"
    return "E"


def _operation(resource: Resource) -> str:
    description = str(resource.get("outcomeDesc", ""))
    for prefix, code in _DESCRIBED_OPERATIONS:
        if description.startswith(prefix):
            return code
    subtype = next(
        (
            str(s["code"])
            for s in resource.get("subtype", [])
            if s.get("code") and s.get("system") == RESTFUL_INTERACTION
        ),
        None,
    )
    if subtype:
        return subtype
    return next((str(s["code"]) for s in resource.get("subtype", []) if s.get("code")), "unknown")


def _role(codings: list[dict[str, Any]]) -> Role | None:
    for coding in codings:
        if coding.get("system") == CS_WORKFLOW_ROLE:
            try:
                return Role(str(coding.get("code")))
            except ValueError:
                return None
    return None


def _entity_type(entity: dict[str, Any]) -> str | None:
    reference = str((entity.get("what") or {}).get("reference", ""))
    if not reference or reference.startswith(("urn:", "#")) or "/" not in reference:
        return None
    parts = [p for p in reference.split("/") if p]
    if "_history" in parts:
        parts = parts[: parts.index("_history")]
    return parts[-2] if len(parts) >= 2 else None


def _details(entity: dict[str, Any]) -> dict[str, str]:
    return {
        str(d["type"]): str(d["valueString"])
        for d in entity.get("detail", [])
        if d.get("type") in _DETAIL_KEYS and d.get("valueString") is not None
    }


def _identifier(resource: Resource, system: str) -> str | None:
    return next((str(i["value"]) for i in resource.get("identifier", []) if i.get("system") == system), None)


def _first_display(recipients: Any) -> str | None:
    if not isinstance(recipients, list) or not recipients:
        return None
    display = recipients[0].get("display")
    return str(display) if display else None


def _payload(resource: Resource) -> str:
    return "\n".join(str(p["contentString"]) for p in resource.get("payload", []) if p.get("contentString"))


def _last_updated(resource: Resource) -> datetime | None:
    value = (resource.get("meta") or {}).get("lastUpdated")
    return datetime.fromisoformat(str(value)) if value else None
