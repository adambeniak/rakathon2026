"""Provenance of an MDT readiness waiver: who waived which readiness item, why and when (AGENTS rule 5)."""

from __future__ import annotations

from datetime import datetime

from app.domain.common import PartyRef
from app.domain.pathway import RecordedWaiver, Waiver
from app.fhir.client import Resource
from app.fhir.mappers.handover import practitioner_reference
from app.fhir.systems import (
    CS_PROVENANCE_ACTIVITY,
    CS_WORKFLOW_ROLE,
    EXT_READINESS_ITEM,
    PROVENANCE_AGENT_TYPE,
)

ACTIVITY_WAIVE_READINESS = "waive-readiness"


def waiver_provenance(waiver: Waiver, *, target: str, signer: PartyRef, recorded: datetime) -> Resource:
    """`target` is the coordinating Task (`Task/<id>`); `signer` is the acting KOC physician, never a client value."""
    return {
        "resourceType": "Provenance",
        "target": [{"reference": target}],
        "recorded": recorded.isoformat(timespec="seconds"),
        "activity": {"coding": [{"system": CS_PROVENANCE_ACTIVITY, "code": ACTIVITY_WAIVE_READINESS}]},
        "reason": [{"text": waiver.reason}],
        "agent": [
            {
                "type": {"coding": [{"system": PROVENANCE_AGENT_TYPE, "code": "verifier"}]},
                "role": [{"coding": [{"system": CS_WORKFLOW_ROLE, "code": signer.role.value}]}],
                "who": practitioner_reference(signer),
            }
        ],
        "extension": [{"url": EXT_READINESS_ITEM, "valueCode": waiver.item}],
    }


def waiver_from_provenance(resource: Resource) -> RecordedWaiver | None:
    """Inverse of `waiver_provenance`; None for any other Provenance (or one without item, reason or time)."""
    codes = {
        c.get("code")
        for c in resource.get("activity", {}).get("coding", [])
        if c.get("system") == CS_PROVENANCE_ACTIVITY
    }
    if ACTIVITY_WAIVE_READINESS not in codes:
        return None
    item = next((e.get("valueCode") for e in resource.get("extension", []) if e.get("url") == EXT_READINESS_ITEM), None)
    reason = next((r.get("text") for r in resource.get("reason", []) if r.get("text")), None)
    recorded = resource.get("recorded")
    if not item or not reason or not recorded:
        return None
    who = (resource.get("agent") or [{}])[0].get("who", {})
    return RecordedWaiver(
        item=str(item),
        reason=str(reason),
        by_id=who.get("identifier", {}).get("value"),
        by_display=who.get("display"),
        at=datetime.fromisoformat(str(recorded)),
    )
