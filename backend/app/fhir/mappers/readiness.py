"""Provenance of an MDT readiness waiver: who waived which readiness item, why and when (AGENTS rule 5)."""

from __future__ import annotations

from datetime import datetime

from app.domain.common import PartyRef
from app.domain.pathway import Waiver
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
