"""Builder for FHIR R4 `AuditEvent` resources (pure function, no I/O)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from app.domain.common import PartyRef, Role
from app.domain.events import DomainEvent
from app.fhir.client import Resource
from app.fhir.systems import (
    AUDIT_EVENT_TYPE,
    CS_AUDIT_EVENT_CODE,
    CS_AUDIT_TYPE,
    CS_WORKFLOW_ROLE,
    EXT_ON_BEHALF_OF,
    RESTFUL_INTERACTION,
    SECURITY_SOURCE_TYPE,
    SID_PRACTITIONER_ROLE,
    SID_USER,
)

AuditAction = Literal["C", "R", "U", "D", "E"]
# http://hl7.org/fhir/restful-interaction codes used by the backend.
AuditSubtype = Literal["create", "read", "search-type", "update", "delete", "transaction", "extract"]

OBSERVER_DISPLAY = "Štafeta backend"


def build_audit_event(
    *,
    action: AuditAction,
    subtype: AuditSubtype,
    actor: PartyRef,
    entities: Sequence[str],
    recorded: datetime,
    description: str | None = None,
    on_behalf_of: str | None = None,
) -> Resource:
    """AuditEvent for one interaction. `entities` are FHIR references ('Patient/12'); `recorded` must be aware.

    `on_behalf_of` names the workplace the actor recorded a step for (R4 AuditEvent.agent has no onBehalfOf, so it
    is an extension carrying a display-only Reference).
    """
    if recorded.tzinfo is None:
        raise ValueError("recorded must be timezone-aware")
    event: Resource = {
        "resourceType": "AuditEvent",
        "type": {"system": AUDIT_EVENT_TYPE, "code": "rest", "display": "RESTful Operation"},
        "subtype": [{"system": CS_AUDIT_EVENT_CODE if subtype == "extract" else RESTFUL_INTERACTION, "code": subtype}],
        "action": action,
        "recorded": recorded.isoformat(timespec="milliseconds"),
        "outcome": "0",
        "agent": [
            {
                "type": {"coding": [{"system": CS_WORKFLOW_ROLE, "code": actor.role.value}]},
                "who": {"identifier": {"system": _actor_system(actor), "value": actor.id}, "display": actor.display},
                "requestor": True,
            }
        ],
        "source": {
            "observer": {"display": OBSERVER_DISPLAY},
            "type": [{"system": SECURITY_SOURCE_TYPE, "code": "4", "display": "Application Server"}],
        },
    }
    if on_behalf_of:
        event["agent"][0]["extension"] = [{"url": EXT_ON_BEHALF_OF, "valueReference": {"display": on_behalf_of}}]
    if entities:  # FHIR JSON forbids empty arrays
        event["entity"] = [{"what": {"reference": reference}} for reference in entities]
    if description:
        event["outcomeDesc"] = description
    return event


def _actor_system(actor: PartyRef) -> str:
    """People are identified like in `Task.owner` (PractitionerRole business id); technical actors as users."""
    return SID_USER if actor.role is Role.SYSTEM else SID_PRACTITIONER_ROLE


_DOMAIN_ACTIONS: dict[str, AuditAction] = {"create": "C", "read": "R", "update": "U", "delete": "D"}


def build_domain_audit_event(event: DomainEvent, *, actor: PartyRef, entities: Sequence[str]) -> Resource:
    """Business-level AuditEvent for a `DomainEvent` of kind audit (state transitions, request lifecycle).

    The payload carries ids, states and roles only (domain contract); it is stored as `entity.detail`.
    """
    result = build_audit_event(
        action=_DOMAIN_ACTIONS.get(event.action, "U"),
        subtype="update",
        actor=actor,
        entities=entities,
        recorded=event.at,
    )
    result["type"] = {"system": CS_AUDIT_TYPE, "code": "domain-event", "display": "Workflow event"}
    result["subtype"] = [{"system": CS_AUDIT_EVENT_CODE, "code": str(event.payload.get("event", event.action))}]
    details = [
        {"type": key, "valueString": str(value)} for key, value in sorted(event.payload.items()) if value is not None
    ]
    if details and result.get("entity"):
        result["entity"][0]["detail"] = details
    return result


def domain_event_code(resource: Resource) -> str | None:
    """The workflow event (`gp_opened`, `reopen`, ...) of a business AuditEvent written by `build_domain_audit_event`;
    None for any other AuditEvent (e.g. an audited read)."""
    if resource.get("type", {}).get("code") != "domain-event":
        return None
    return next(
        (
            str(s["code"])
            for s in resource.get("subtype", [])
            if s.get("system") == CS_AUDIT_EVENT_CODE and s.get("code")
        ),
        None,
    )
