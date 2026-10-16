"""Builder for FHIR R4 `AuditEvent` resources (pure function, no I/O)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from app.domain.common import PartyRef, Role
from app.fhir.client import Resource
from app.fhir.systems import (
    AUDIT_EVENT_TYPE,
    CS_WORKFLOW_ROLE,
    RESTFUL_INTERACTION,
    SECURITY_SOURCE_TYPE,
    SID_PRACTITIONER_ROLE,
    SID_USER,
)

AuditAction = Literal["C", "R", "U", "D", "E"]
# http://hl7.org/fhir/restful-interaction codes used by the backend.
AuditSubtype = Literal["create", "read", "search-type", "update", "delete", "transaction"]

OBSERVER_DISPLAY = "Štafeta backend"


def build_audit_event(
    *,
    action: AuditAction,
    subtype: AuditSubtype,
    actor: PartyRef,
    entities: Sequence[str],
    recorded: datetime,
    description: str | None = None,
) -> Resource:
    """AuditEvent for one interaction. `entities` are FHIR references ('Patient/12'); `recorded` must be aware."""
    if recorded.tzinfo is None:
        raise ValueError("recorded must be timezone-aware")
    event: Resource = {
        "resourceType": "AuditEvent",
        "type": {"system": AUDIT_EVENT_TYPE, "code": "rest", "display": "RESTful Operation"},
        "subtype": [{"system": RESTFUL_INTERACTION, "code": subtype}],
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
    if entities:  # FHIR JSON forbids empty arrays
        event["entity"] = [{"what": {"reference": reference}} for reference in entities]
    if description:
        event["outcomeDesc"] = description
    return event


def _actor_system(actor: PartyRef) -> str:
    """People are identified like in `Task.owner` (PractitionerRole business id); technical actors as users."""
    return SID_USER if actor.role is Role.SYSTEM else SID_PRACTITIONER_ROLE
